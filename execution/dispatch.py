# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Mode routing, pacing and the one request each case is allowed.

Specified by ``docs/design/tier2_execution.md`` sections 3.2, 8, 8.1, 8.2
and 8.3.

**One request per case. No loop, no agentic cycle, no tool execution** (A9). A
retry after a rate limit is the same request issued again, not a second turn,
and ``attempts`` records that it happened.

**The objective is evaluation, never load-testing a provider.** On a free tier
pacing decides whether a run completes at all (A7.3), which is why spacing,
bounded backoff and the circuit breaker live here rather than in each adapter.

**Replay applies no spacing and consumes no quota**, which is why the
deterministic gates run identically on a pull request and on a schedule.
"""

import logging
import time
from datetime import date
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Final, Optional

from cmn.pricing import PriceTable, cost_of
from cmn.tokens import TokenUsage
from execution.adapters.base import ProviderAdapter
from execution.adapters.registry import adapter_for
from execution.normalize import NormalizedResponse
from execution.replay import (
    FixtureKey,
    FixtureMissing,
    FixtureStale,
    hash_request,
    load_fixture,
    record_fixture,
)

logger = logging.getLogger(__name__)

# Exactly the codes design section 8 names as retryable. A retry against
# anything else spends quota to receive the same answer.
#
# THE THIRD ARRIVED FROM A LIVE RUN. A provider reporting itself busy is a
# condition where the same request later plausibly succeeds, which is the only
# thing that makes a retry worth its quota (section 8.5).
_RETRYABLE_CODES: Final[frozenset[str]] = frozenset(
    {
        "QC_HARNESS_RATE_LIMIT",
        "QC_HARNESS_CANDIDATE_TIMEOUT",
        "QC_HARNESS_PROVIDER_UNAVAILABLE",
        "QC_HARNESS_GATEWAY_FAILURE",
    }
)

_MODES: Final[frozenset[str]] = frozenset({"live", "replay"})

_DEFAULT_MAX_ATTEMPTS: Final[int] = 3
_DEFAULT_BACKOFF_SEC: Final[float] = 2.0
_DEFAULT_BREAKER_THRESHOLD: Final[int] = 5


class CircuitBreakerTripped(RuntimeError):
    """The run aborted because the provider stopped answering usefully.

    Raised rather than returned, because it ends the run instead of describing
    one case. Every further request would spend quota to confirm what is
    already known.
    """


@dataclass(frozen=True)
class DispatchOutcome:
    """What one dispatched case produced, whether or not it measured anything.

    ``response`` and ``taxonomy_code`` are mutually exclusive and one is always
    present. Both would leave downstream code choosing which to believe;
    neither would be a case that produced no measurement and no reason.

    Attributes:
        case_id (str): Which case.
        engine (str): Which adapter.
        mode (str): ``live`` or ``replay``.
        duration_ms (int): Measured by the dispatcher, per design section 4.4.
        duration_kind (str): ``measured`` or ``truncated``.
        attempts (int): Requests issued, so a retried case is visible.
        rate_limit_encounters (int): Counted rather than absorbed by retry.
        response (Optional[NormalizedResponse]): Absent exactly when skipped.
        taxonomy_code (Optional[str]): Present exactly when skipped.
    """

    case_id: str
    engine: str
    mode: str
    duration_ms: int
    duration_kind: str
    attempts: int
    rate_limit_encounters: int
    response: Optional[NormalizedResponse] = None
    taxonomy_code: Optional[str] = None

    def __post_init__(self) -> None:
        """Refuse an outcome that is both a measurement and a skip, or neither.

        Returns:
            None

        Raises:
            ValueError: When exactly one of the two is not present.
        """
        if (self.response is None) == (self.taxonomy_code is None):
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: {self.case_id} must carry either a response "
                f"or a taxonomy code, never both and never neither"
            )

    @property
    def measured(self) -> bool:
        """Report whether this case produced a measurement.

        Returns:
            bool: True when a response was obtained.
        """
        return self.response is not None


@dataclass(frozen=True)
class DispatchPlan:
    """How a run dispatches, as opposed to what it has spent so far.

    Separate from :class:`DispatchSession` because these values are fixed for
    the run while the session's are consumed by it. Holding both in one mutable
    record would put the mode and the fixture root next to a counter that
    changes on every case.

    Attributes:
        mode (str): ``live`` or ``replay``. **Independent of engine selection**,
            so an invalid mode is rejected here rather than absorbed by
            whichever adapter happened to be chosen.
        fixture_root (Path): Where replay fixtures live.
        model (Optional[str]): The model to request, supplied at execution time
            per B8. The adapter's declared default applies when absent.
        record (bool): Whether a live response is written to the fixture store.
        keep_connection (bool): Whether to leave the provider connection open
            after the response is captured. **Default false**, so an
            unconfigured run releases what it opened and each case is isolated
            from the one before it (design section 7.7).
        fill_gaps (bool): In live mode, whether to replay an observation that
            is already recorded instead of dispatching it again. **Default
            false**, because `--mode live` means call the provider and a run
            asking what a model says now should not answer from a file
            (design section 7.10).
    """

    mode: str
    fixture_root: Path
    model: Optional[str] = None
    record: bool = False
    keep_connection: bool = False
    fill_gaps: bool = False

    def __post_init__(self) -> None:
        """Refuse a mode the dispatcher does not recognise.

        Returns:
            None

        Raises:
            ValueError: When the mode is neither live nor replay.
        """
        if self.mode not in _MODES:
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: mode {self.mode!r} is neither live nor replay"
            )


@dataclass
class DispatchSession:
    """Run-level pacing state, which no single case can hold.

    Spacing is an interval **between** requests and the circuit breaker counts a
    streak **across** cases, so both need somewhere to live that outlasts one
    dispatch.

    Attributes:
        spacing_sec (float): Minimum interval between live requests, per engine
            configuration. Inapplicable in replay, which spends no quota.
        max_attempts (int): Requests per case before backoff is exhausted.
        backoff_sec (float): Base delay, doubled per attempt.
        breaker_threshold (int): Consecutive case failures that abort the run.
        monotonic (Callable): Injected clock, so spacing is testable without
            waiting. See design section 8.2.
        delay (Callable): Injected sleep, for the same reason.
        rate_limit_encounters (int): Summed across the run and reported.
        consecutive_failures (int): Reset by any measured case.
        last_request_at (Optional[float]): When the previous live request went.
        slept_intervals (list): Every interval actually waited, so a test can
            assert the spacing decision without spending the wall-clock.
        max_spend (float): The run's ceiling in the price table's currency.
            **Zero means no ceiling**, which is the default and what every
            replay run uses: replay spends nothing, so a ceiling there would
            only be a number to get wrong.
        spent (float): What the run has been billed so far, accumulated from
            each measured response rather than estimated.
        usage (TokenUsage): Every token the run has consumed, kept so a run can
            report its own cost without re-reading the corpus.
        prices (Optional[PriceTable]): The rates, or ``None`` for a run that
            prices nothing. **A replay run leaves this unset**, because a
            replayed response was paid for when it was recorded.
        priced_on (Optional[date]): The date rates are read against, injected
            for the reason the verdict injects its date: a cost that changes
            between two readings of one corpus is not a measurement.
        unpriced (set): Models this run met that the table does not price.
            **A ceiling cannot be honoured against these**, so their presence
            stops a budgeted run rather than being noted: a cap that cannot be
            enforced must not look enforced.
    """

    spacing_sec: float = 0.0
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS
    backoff_sec: float = _DEFAULT_BACKOFF_SEC
    breaker_threshold: int = _DEFAULT_BREAKER_THRESHOLD
    monotonic: Callable[[], float] = time.monotonic
    delay: Callable[[float], None] = time.sleep
    rate_limit_encounters: int = 0
    consecutive_failures: int = 0
    last_request_at: Optional[float] = None
    slept_intervals: list[float] = field(default_factory=list)
    max_spend: float = 0.0
    spent: float = 0.0
    usage: TokenUsage = field(default_factory=TokenUsage)
    prices: Optional[PriceTable] = None
    priced_on: Optional[date] = None
    unpriced: set[str] = field(default_factory=set)

    def wait_for_slot(self) -> None:
        """Pause until the configured spacing has elapsed since the last request.

        Returns:
            None
        """
        if self.spacing_sec <= 0 or self.last_request_at is None:
            return
        remaining = self.spacing_sec - (self.monotonic() - self.last_request_at)
        if remaining > 0:
            self.slept_intervals.append(remaining)
            self.delay(remaining)

    def ceiling_reached(self) -> bool:
        """Report whether the run has already spent its ceiling.

        **Asked before each request, and it overshoots by at most one.** The
        alternative is to compare the ceiling against an estimate of the request
        about to be sent, which means inventing token counts for a prompt the
        provider has not answered: an estimate that is too low defeats the
        ceiling while appearing to enforce it. Stopping one request late is
        cheaper than a guess that can be wrong in the unsafe direction, and at
        the measured rates one request is a small fraction of a cent.

        Returns:
            bool: True where a ceiling is set and spending has reached it.
            **False when no ceiling is set**, so an unconfigured run behaves
            exactly as it did before this existed, and every replay run is
            unaffected because replay spends nothing.
        """
        if self.max_spend <= 0:
            return False
        # AN UNPRICED MODEL STOPS A BUDGETED RUN. Its responses cost `None`, so
        # `spent` never grows and the ceiling would never engage: the run would
        # spend without limit while reporting a cap. `claude-opus-5-5` is exactly
        # that case, deliberately unpriced and with thinking it cannot disable.
        if self.unpriced:
            return True
        return self.spent >= self.max_spend

    def record_spend(self, usage: TokenUsage, model: str) -> None:
        """Add one response's tokens, and its cost where the model is priced.

        **The session prices this, not the caller.** The dispatch path should not
        have to hold a price table to report a measurement, and keeping the
        lookup here means the ceiling and the total are computed from one place.

        Args:
            usage (TokenUsage): What the response consumed.
            model (str): The model the provider reported serving, which is what
                is priced. **Resolved, never requested**: an alias that floated
                would otherwise be billed at the price of a model nobody served.

        Returns:
            None: **An unpriced model still contributes its tokens.** A run
            against something the table does not know reports usage it cannot
            price, rather than reporting nothing and reading as free.
        """
        self.usage = self.usage + usage
        if self.prices is None or self.priced_on is None:
            return
        cost = cost_of(usage, model, self.prices, self.priced_on)
        if cost is None:
            # RECORDED, so a budgeted run can stop and say which model it could
            # not price. An unbudgeted run carries on and reports usage it cannot
            # price, which is the honest answer when nobody asked for a cap.
            if model:
                self.unpriced.add(model)
            return
        self.spent += cost

    def record_request(self) -> None:
        """Note that a request has just been issued.

        Returns:
            None
        """
        self.last_request_at = self.monotonic()

    def note_outcome(self, outcome: DispatchOutcome) -> None:
        """Fold one case's result into the run-level counters.

        Args:
            outcome (DispatchOutcome): What the case produced.

        Returns:
            None

        Raises:
            CircuitBreakerTripped: On an auth error immediately, or once the
                consecutive-failure streak reaches its threshold.
        """
        self.rate_limit_encounters += outcome.rate_limit_encounters
        if outcome.measured:
            self.consecutive_failures = 0
            return

        if outcome.taxonomy_code == "QC_HARNESS_AUTH_ERROR":
            logger.error("QC_HARNESS_AUTH_ERROR aborting the run at %s", outcome.case_id)
            raise CircuitBreakerTripped(
                f"QC_HARNESS_AUTH_ERROR: {outcome.engine} rejected our credentials at "
                f"{outcome.case_id}, so every remaining case would fail identically"
            )

        self.consecutive_failures += 1
        if self.consecutive_failures >= self.breaker_threshold:
            logger.error(
                "Circuit breaker tripped after %d consecutive failures on %s",
                self.consecutive_failures, outcome.engine,
            )
            raise CircuitBreakerTripped(
                f"{outcome.engine} failed {self.consecutive_failures} cases consecutively, "
                f"so the run aborts rather than spending quota to confirm it"
            )


@dataclass(frozen=True)
class _CaseContext:
    """One case, bound to the adapter and request that will serve it.

    Attributes:
        adapter (ProviderAdapter): The adapter dispatching this case.
        case (Any): The ``EvaluationCase``, typed loosely so Tier 2 does not
            import Tier 1's record and invert the dependency.
        request (dict): The composed request.
        plan (DispatchPlan): The run's dispatch configuration.
        observation_index (int): Which of the repeat observations this is (A4).
    """

    adapter: ProviderAdapter
    case: Any
    request: dict[str, Any]
    plan: DispatchPlan
    observation_index: int

    @property
    def key(self) -> FixtureKey:
        """Return what locates this observation in the fixture store.

        Returns:
            FixtureKey: The tuple identity, which the store splits into a path.
        """
        return FixtureKey(
            self.case.case_id, self.adapter.engine_name, self.observation_index
        )


@dataclass
class _AttemptTally:
    """What one case has spent so far.

    Attributes:
        attempts (int): Requests issued, so a retried case is visible.
        rate_limits (int): Encountered rather than absorbed silently by retry.
        code (str): The most recent harness code, carried into a skip.
        period_exhausted (bool): Set where a rate limit named a period no
            backoff can outwait, which separates "come back in a minute" from
            "come back tomorrow" in the run's own record. **The count alone
            cannot carry this**: three rate limits look identical whether the
            allowance returns in seconds or at midnight, and the remedies
            differ (design section 8.6.4).
    """

    attempts: int = 0
    rate_limits: int = 0
    code: str = "QC_HARNESS_PARSER_ERROR"
    period_exhausted: bool = False


def dispatch_case(
    case: Any,
    engine: str,
    plan: DispatchPlan,
    session: DispatchSession,
    observation_index: int = 0,
) -> DispatchOutcome:
    """Execute one case against one engine in one mode.

    Args:
        case (Any): An ``EvaluationCase``.
        engine (str): The registered engine name.
        plan (DispatchPlan): The run's dispatch configuration.
        session (DispatchSession): Run-level pacing state.
        observation_index (int): Which of the repeat observations this is (A4).

    Returns:
        DispatchOutcome: A measurement or a skip carrying its reason.

    Raises:
        CircuitBreakerTripped: Propagated from the session, on an auth error or
            once the consecutive-failure streak reaches its threshold.
    """
    adapter = adapter_for(engine)(plan.model)
    context = _CaseContext(
        adapter=adapter,
        case=case,
        request=adapter.compose_request(case),
        plan=plan,
        observation_index=observation_index,
    )

    try:
        if plan.mode == "replay":
            outcome = _replay_case(context)
        else:
            # ALREADY RECORDED IS ALREADY ANSWERED. Under a rate limit, quota
            # spent re-dispatching an observation that exists is quota not
            # spent on one that does not, which is what stops a corpus
            # converging (design section 7.10).
            outcome = _recorded_or_dispatched(context, session)
    finally:
        # RELEASED EVEN WHEN THE CASE RAISED, which is the path that matters
        # most: a circuit breaker trips by propagating, and an adapter left
        # holding a socket on the way out is exactly the leak this closes.
        # Design section 7.7.
        if not plan.keep_connection:
            adapter.release()
    session.note_outcome(outcome)
    return outcome



def _recorded_or_dispatched(
    context: _CaseContext, session: DispatchSession
) -> DispatchOutcome:
    """Replay an observation already recorded, or dispatch it.

    **Only when the run asked to fill gaps.** Otherwise a live run dispatches,
    which is what live means.

    Args:
        context (_CaseContext): The case and its composed request.
        session (DispatchSession): Run-level pacing state.

    Returns:
        DispatchOutcome: The stored observation where one loads cleanly,
        otherwise a fresh measurement. **A stale fixture is a gap**: the
        question or the instrument moved, so what is stored answers something
        else and dispatching is exactly right.
    """
    if context.plan.fill_gaps:
        try:
            stored = load_fixture(
                context.plan.fixture_root,
                context.key,
                hash_request(context.request),
            )
        except (FixtureMissing, FixtureStale, FileNotFoundError, ValueError):
            pass
        else:
            # LOADED CLEANLY, so there is nothing to learn by asking again.
            del stored
            logger.info(
                "%s observation %d already recorded, not dispatched",
                context.case.case_id, context.observation_index,
            )
            return _replay_case(context)
    return _dispatch_live(context, session)

def _replay_case(context: _CaseContext) -> DispatchOutcome:
    """Reproduce one recorded observation.

    **No spacing, no retry, no clock.** Replay consumes no quota, so every
    pacing control is inapplicable rather than merely unnecessary.

    The stored payload is the normalized record rather than a provider payload
    (design section 7.3), so no adapter takes part and rebuilding goes through
    the record's own constructor. A fixture hand-edited to carry an unregistered
    mode is therefore rejected on read rather than replayed as an observation.

    Args:
        context (_CaseContext): The case and its composed request.

    Returns:
        DispatchOutcome: The replayed measurement, or a skip when the fixture is
        missing or stale. **Both are reported, never silently replayed**,
        because replaying a recorded answer to a different question corrupts the
        result.
    """
    case_id = context.case.case_id
    engine = context.adapter.engine_name
    try:
        stored = load_fixture(
            context.plan.fixture_root, context.key, hash_request(context.request)
        )
    except (FixtureMissing, FixtureStale, FileNotFoundError, ValueError) as error:
        # THE STORE'S OWN EXCEPTIONS COME FIRST, and their absence here was the
        # defect: both inherit from Exception alone, so the handler never fired
        # and a missing fixture escaped dispatch as an error. A QC_HARNESS_*
        # event is a skip, never a failure (framework-rules.md section 4).
        # The builtins stay for a fixture file that is corrupt rather than
        # absent. tier2_execution.md section 7.6.
        code = _fixture_error_code(error)
        logger.warning("%s replaying %s", code, case_id)
        return DispatchOutcome(
            case_id=case_id, engine=engine, mode="replay", duration_ms=0,
            duration_kind="measured", attempts=0, rate_limit_encounters=0,
            taxonomy_code=code,
        )

    replayed = NormalizedResponse.from_mapping(stored.response).replace(
        mode="replay", resolved_model=stored.resolved_model
    )
    return DispatchOutcome(
        case_id=case_id, engine=engine, mode="replay",
        duration_ms=replayed.duration_ms, duration_kind="measured", attempts=0,
        rate_limit_encounters=0, response=replayed,
    )


def _dispatch_live(context: _CaseContext, session: DispatchSession) -> DispatchOutcome:
    """Issue the request, retrying a retryable failure within the bound.

    A retry is **the same request issued again**, not a second turn. A9 forbids
    a loop, and ``attempts`` records that the request went twice so a retried
    case stays distinguishable from a first-try success.

    Args:
        context (_CaseContext): The case and its composed request.
        session (DispatchSession): Run-level pacing state.

    Returns:
        DispatchOutcome: The measurement, or a skip once backoff is exhausted.
        **Exhausted backoff skips and continues**, because the objective is
        measuring a model rather than load-testing a provider.
    """
    tally = _AttemptTally()
    started = session.monotonic()
    for attempt in range(1, session.max_attempts + 1):
        tally.attempts = attempt
        # THE CEILING IS CHECKED BEFORE SPENDING, not after. A run that has
        # reached it stops rather than finishing the corpus, and says so with its
        # own code: this is us declining, not the provider, and the remedy is a
        # decision about the budget rather than about pacing.
        if session.ceiling_reached():
            tally.code = "QC_HARNESS_BUDGET_EXHAUSTED"
            if session.unpriced:
                logger.error(
                    "%s: a ceiling of %.4f was set and %s is unpriced, so the "
                    "ceiling could not be honoured and the run stops rather "
                    "than spending without one",
                    tally.code, session.max_spend, ", ".join(sorted(session.unpriced)),
                )
            else:
                logger.warning(
                    "%s: the run has spent %.4f against a ceiling of %.4f, so "
                    "this case was not dispatched",
                    tally.code, session.spent, session.max_spend,
                )
            return _skip(context, session, tally, started)

        session.wait_for_slot()
        started = session.monotonic()
        session.record_request()
        try:
            raw = context.adapter.dispatch(context.request)
        except Exception as error:  # pylint: disable=broad-exception-caught
            tally.code = context.adapter.map_error(error)
            futile = False
            if tally.code == "QC_HARNESS_RATE_LIMIT":
                tally.rate_limits += 1
                # A PERIOD NO BACKOFF CAN OUTWAIT ENDS THE ATTEMPTS HERE. The
                # status is retryable in general because a per-minute rate
                # clears on its own; a per-day allowance does not, and two
                # further attempts two and four seconds later ask a question
                # already answered (design section 8.6.4).
                futile = context.adapter.period_quota_exhausted(error)
                if futile:
                    tally.period_exhausted = True
                    logger.warning(
                        "%s: the quota period is spent, so the remaining "
                        "attempts are abandoned rather than spent",
                        context.adapter.engine_name,
                    )
            if (
                futile
                or tally.code not in _RETRYABLE_CODES
                or attempt == session.max_attempts
            ):
                return _skip(context, session, tally, started)
            # A NEW CONNECTION FOR THE NEXT ATTEMPT. A failed attempt can
            # leave the connection worse than it found it: a half-open socket,
            # a stuck stream, or a pool entry pinned to the instance that just
            # returned 503. Retrying on it asks the same unhealthy path the
            # same question. This does not fix a rate limit, whose quota is
            # keyed to the credential (design section 7.11).
            context.adapter.release()
            session.delay(session.backoff_sec * (2 ** (attempt - 1)))
            continue

        return _measured(context, session, tally, started, raw)

    return _skip(context, session, tally, started)


def _measured(
    context: _CaseContext,
    session: DispatchSession,
    tally: _AttemptTally,
    started: float,
    raw: Any,
) -> DispatchOutcome:
    """Normalize a successful response and record it if the plan says to.

    Args:
        context (_CaseContext): The case that succeeded.
        session (DispatchSession): For the clock.
        tally (_AttemptTally): What the case spent.
        started (float): When the successful attempt began.
        raw (Any): The provider response, which stops at the adapter.

    Returns:
        DispatchOutcome: The measurement.
    """
    elapsed_ms = int((session.monotonic() - started) * 1000)
    response = context.adapter.normalize_response(
        raw, context.case.case_id
    ).replace(duration_ms=elapsed_ms)

    # WHAT THIS RESPONSE COST, added before the outcome is returned so the
    # ceiling sees it on the next case. A replayed response never reaches here.
    session.record_spend(response.usage, response.resolved_model)

    if context.plan.record:
        record_fixture(
            context.plan.fixture_root, context.key, hash_request(context.request),
            response.as_mapping(), response.resolved_model,
        )

    return DispatchOutcome(
        case_id=context.case.case_id,
        engine=context.adapter.engine_name,
        mode="live",
        duration_ms=elapsed_ms,
        duration_kind="measured",
        attempts=tally.attempts,
        rate_limit_encounters=tally.rate_limits,
        response=response,
    )


def _skip(
    context: _CaseContext,
    session: DispatchSession,
    tally: _AttemptTally,
    started: float,
) -> DispatchOutcome:
    """Build the outcome for a case that produced no measurement.

    Args:
        context (_CaseContext): The case that failed.
        session (DispatchSession): For the clock.
        tally (_AttemptTally): What the case spent.
        started (float): When the final attempt began.

    Returns:
        DispatchOutcome: The skip. **A timeout records a truncated duration**,
        because the interval measures how long the harness waited rather than
        how long the model took, and averaging the two would measure our own
        patience (``test_taxonomy.md`` section 9.3).
    """
    truncated = tally.code == "QC_HARNESS_CANDIDATE_TIMEOUT"
    return DispatchOutcome(
        case_id=context.case.case_id,
        engine=context.adapter.engine_name,
        mode="live",
        duration_ms=int((session.monotonic() - started) * 1000),
        duration_kind="truncated" if truncated else "measured",
        attempts=tally.attempts,
        rate_limit_encounters=tally.rate_limits,
        taxonomy_code=tally.code,
    )


def _fixture_error_code(error: Exception) -> str:
    """Return the harness code a fixture failure carries.

    Args:
        error (Exception): What the replay store raised.

    Returns:
        str: The code named in the message, or the parser code when the message
        names none.
    """
    text = str(error)
    for code in ("QC_HARNESS_FIXTURE_STALE", "QC_HARNESS_FIXTURE_MISSING"):
        if code in text:
            return code
    return "QC_HARNESS_PARSER_ERROR"
