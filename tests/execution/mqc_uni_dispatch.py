# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for pacing, retry and the circuit breaker.

Covers `MQC_EXE_UNI_10226` through `10234`, inventoried in
``docs/design/tier2_execution.md`` section 10.1.

**Pacing decides whether a run completes at all** on a free tier (A7.3), which
is what makes it logic rather than configuration and why it carries cases.

**The clock and the sleep are injected** (design section 8.2), so these cases
assert the decision rather than spending the wall-clock proving that waiting
works. A precondition suite that sleeps is a precondition suite people start
skipping.

A failure here is our defect, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

from pathlib import Path
from typing import Any, Iterator

import pytest

from execution.adapters.claude import ClaudeAdapter
from execution.adapters.registry import registered_adapters
from execution.judge_channel import JudgeChannel
from execution.dispatch import (
    CircuitBreakerTripped,
    DispatchPlan,
    DispatchSession,
    dispatch_case,
)
from execution.normalize import NormalizedResponse
from execution.replay import FixtureKey, hash_request, record_fixture
from tests.execution.provider_doubles import claude_response, claude_error
from ingestion.schemas import EvaluationCase

pytestmark = pytest.mark.unit



class _FakeClock:
    """A monotonic clock that advances only when asked.

    Real time would make a spacing case a sleeping case, and a bounded-backoff
    case a case that sleeps repeatedly.

    Attributes:
        now (float): The current reading, in seconds.
    """

    def __init__(self) -> None:
        """Start the clock at zero.

        Returns:
            None
        """
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        """Return the current reading.

        Returns:
            float: Seconds since the clock started.
        """
        return self.now

    def sleep(self, seconds: float) -> None:
        """Advance the clock instead of waiting.

        Args:
            seconds (float): How long the dispatcher asked to wait.

        Returns:
            None
        """
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture(name="clock")
def fixture_clock() -> _FakeClock:
    """Return a clock that records what it was asked to wait.

    Returns:
        _FakeClock: The clock, wired into a session by the caller.
    """
    return _FakeClock()


@pytest.fixture(name="session")
def fixture_session(clock: _FakeClock) -> DispatchSession:
    """Return a session driven by the fake clock.

    Args:
        clock (_FakeClock): The injected clock.

    Returns:
        DispatchSession: A session that never touches real time.
    """
    return DispatchSession(monotonic=clock.monotonic, delay=clock.sleep)


@pytest.fixture(name="scripted")
def fixture_scripted(monkeypatch: Any) -> Iterator[Any]:
    """Return a helper that scripts what one adapter's dispatch does.

    Patching the adapter rather than registering a test double keeps the
    registry, and therefore the conformance battery, exactly as it ships.

    Args:
        monkeypatch (Any): pytest's patcher.

    Yields:
        Any: A callable taking the sequence of results or exceptions to serve.
    """
    calls: list[Any] = []

    def script(*results: Any) -> list[Any]:
        """Install a scripted dispatch and return its call log.

        Args:
            *results (Any): Responses to return or exceptions to raise, in
                order. The last is repeated once exhausted.

        Returns:
            list: Every request the adapter was asked to dispatch.
        """
        remaining = list(results)

        def fake_dispatch(_self: Any, request: Any) -> Any:
            calls.append(request)
            outcome = remaining.pop(0) if len(remaining) > 1 else remaining[0]
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        monkeypatch.setattr(ClaudeAdapter, "dispatch", fake_dispatch)
        return calls

    yield script


def _plan(tmp_path: Any, mode: str = "live", record: bool = False) -> DispatchPlan:
    """Build a dispatch plan rooted in a temporary fixture store.

    Args:
        tmp_path (Any): pytest's temporary directory.
        mode (str): ``live`` or ``replay``.
        record (bool): Whether a live response is recorded.

    Returns:
        DispatchPlan: The plan.
    """
    return DispatchPlan(mode=mode, fixture_root=tmp_path, record=record)


class TestMQCRequestSpacing:
    """What the dispatcher waits for, and what it does not."""

    def MQC_EXE_UNI_10226_replay_mode_applies_no_request_spacing(
        self, minimal_case: EvaluationCase, session: DispatchSession, clock: Any, tmp_path: Path
    ) -> None:
        """Replay consumes no quota, so spacing is inapplicable rather than idle.

        This is why the deterministic gates run identically on a pull request
        and on a schedule: a replay leg paced like a live one would make the
        cheapest gate the slowest.

        Args:
            minimal_case (Any): The case to replay.
            session (DispatchSession): Paced at a wide interval deliberately.
            clock (_FakeClock): The injected clock.
            tmp_path (Any): pytest's temporary directory.

        Returns:
            None
        """
        session.spacing_sec = 30.0
        plan = _plan(tmp_path, mode="replay")
        adapter = ClaudeAdapter()
        request = adapter.compose_request(minimal_case)
        stored = adapter.normalize_response(claude_response(), minimal_case.case_id)
        for index in range(2):
            record_fixture(
                tmp_path,
                FixtureKey(minimal_case.case_id, "claude", index),
                hash_request(request),
                stored.as_mapping(),
                stored.resolved_model,
            )

        for index in range(2):
            outcome = dispatch_case(minimal_case, "claude", plan, session, index)
            assert outcome.measured
        assert clock.slept == []
        assert session.slept_intervals == []

    def MQC_EXE_UNI_10227_request_spacing_honoured_at_configured_interval(
        self,
        minimal_case: EvaluationCase,
        session: DispatchSession,
        clock: Any,
        tmp_path: Path,
        scripted: Any,
    ) -> None:
        """Stated at the configured interval exactly, not near it.

        A boundary case per `testing-standards.md`: off-by-one at a threshold
        is the likeliest defect in any gate, and a spacing that waited a
        fraction too little would exceed a free-tier ceiling that a spacing
        waiting a fraction too long would not.

        Args:
            minimal_case (Any): The case to dispatch.
            session (DispatchSession): The paced session.
            clock (_FakeClock): The injected clock.
            tmp_path (Any): pytest's temporary directory.
            scripted (Any): Dispatch scripting helper.

        Returns:
            None
        """
        session.spacing_sec = 4.0
        scripted(claude_response())
        plan = _plan(tmp_path)

        dispatch_case(minimal_case, "claude", plan, session)
        assert clock.slept == []

        clock.now += 4.0
        dispatch_case(minimal_case, "claude", plan, session)
        assert clock.slept == []

        clock.now += 1.5
        dispatch_case(minimal_case, "claude", plan, session)
        assert clock.slept == [2.5]


class TestMQCRetryAndBackoff:
    """What the dispatcher retries, and what it refuses to retry."""

    def MQC_EXE_UNI_10228_exhausted_backoff_skips_case_with_rate_limit_code(
        self, minimal_case: EvaluationCase, session: DispatchSession, tmp_path: Path, scripted: Any
    ) -> None:
        """Exhausted backoff skips and continues; it never fails the case.

        The objective is measuring a model, not load-testing a provider. A
        failure here would also attribute our pacing problem to the model.

        Args:
            minimal_case (Any): The case to dispatch.
            session (DispatchSession): The paced session.
            tmp_path (Any): pytest's temporary directory.
            scripted (Any): Dispatch scripting helper.

        Returns:
            None
        """
        session.max_attempts = 3
        calls = scripted(claude_error("rate_limit"))
        outcome = dispatch_case(minimal_case, "claude", _plan(tmp_path), session)

        assert outcome.measured is False
        assert outcome.taxonomy_code == "QC_HARNESS_RATE_LIMIT"
        assert outcome.attempts == 3
        assert len(calls) == 3

    def MQC_EXE_UNI_10231_rate_limit_encounters_are_counted_and_reported(
        self, minimal_case: EvaluationCase, session: DispatchSession, tmp_path: Path, scripted: Any
    ) -> None:
        """Retry must not absorb the encounter silently.

        A run that succeeded after twelve rate limits and a run that succeeded
        after none look identical without this count, and the first is one
        spacing change away from failing entirely.

        Args:
            minimal_case (Any): The case to dispatch.
            session (DispatchSession): The paced session.
            tmp_path (Any): pytest's temporary directory.
            scripted (Any): Dispatch scripting helper.

        Returns:
            None
        """
        scripted(claude_error("rate_limit"), claude_response())
        outcome = dispatch_case(minimal_case, "claude", _plan(tmp_path), session)

        assert outcome.measured is True
        assert outcome.attempts == 2
        assert outcome.rate_limit_encounters == 1
        assert session.rate_limit_encounters == 1

    def MQC_EXE_UNI_10295_a_spent_quota_period_abandons_its_remaining_attempts(
        self, minimal_case: EvaluationCase, session: DispatchSession, tmp_path: Path,
        scripted: Any, monkeypatch: Any
    ) -> None:
        """A 429 naming a day is not retried, because no backoff reaches a day.

        **The status alone does not decide this.** A per-minute rate clears on
        its own and is worth a retry; a per-day allowance does not, and the
        two further attempts would ask a question already answered. Measured
        live on 2026-09-26, where a free tier allowing twenty requests a day
        stalled a recording run at nineteen fixtures.

        Args:
            minimal_case (Any): The case to dispatch.
            session (DispatchSession): The paced session.
            tmp_path (Any): pytest's temporary directory.
            scripted (Any): Dispatch scripting helper.
            monkeypatch (Any): To make the adapter report a spent period.

        Returns:
            None
        """
        session.max_attempts = 3
        monkeypatch.setattr(
            ClaudeAdapter, "period_quota_exhausted", lambda _self, _error: True
        )
        calls = scripted(claude_error("rate_limit"))
        outcome = dispatch_case(minimal_case, "claude", _plan(tmp_path), session)

        assert outcome.measured is False
        assert outcome.taxonomy_code == "QC_HARNESS_RATE_LIMIT"
        # ONE ATTEMPT, NOT THREE, and the encounter still counted.
        assert outcome.attempts == 1
        assert len(calls) == 1
        assert outcome.rate_limit_encounters == 1

    def MQC_EXE_UNI_10296_a_rate_limit_of_unknown_period_keeps_its_retries(
        self, minimal_case: EvaluationCase, session: DispatchSession, tmp_path: Path,
        scripted: Any
    ) -> None:
        """An adapter that cannot tell keeps the retry rather than losing it.

        **The default has to fail open**, because the useful case is the
        per-minute rate that a retry does clear. An adapter whose provider does
        not name the quota answers "unknown", and unknown must not silently
        become "give up": that would trade a recoverable condition away to
        handle an unrecoverable one.

        Args:
            minimal_case (Any): The case to dispatch.
            session (DispatchSession): The paced session.
            tmp_path (Any): pytest's temporary directory.
            scripted (Any): Dispatch scripting helper.

        Returns:
            None
        """
        session.max_attempts = 3
        calls = scripted(claude_error("rate_limit"), claude_response())

        outcome = dispatch_case(minimal_case, "claude", _plan(tmp_path), session)

        assert outcome.measured is True
        assert outcome.attempts == 2
        assert len(calls) == 2

    def MQC_EXE_UNI_10233_candidate_timeout_maps_to_candidate_code_not_generic(
        self, minimal_case: EvaluationCase, session: DispatchSession, tmp_path: Path, scripted: Any
    ) -> None:
        """A timeout keeps its own code rather than collapsing into a parser error.

        Repeated candidate timeouts say something about the model or its
        provider; repeated parser errors say something about us. Collapsing
        them would make both unreadable.

        Args:
            minimal_case (Any): The case to dispatch.
            session (DispatchSession): The paced session.
            tmp_path (Any): pytest's temporary directory.
            scripted (Any): Dispatch scripting helper.

        Returns:
            None
        """
        session.max_attempts = 2
        scripted(claude_error("timeout"))
        outcome = dispatch_case(minimal_case, "claude", _plan(tmp_path), session)
        assert outcome.taxonomy_code == "QC_HARNESS_CANDIDATE_TIMEOUT"

    def MQC_EXE_UNI_10234_timeout_records_duration_kind_truncated(
        self, minimal_case: EvaluationCase, session: DispatchSession, tmp_path: Path, scripted: Any
    ) -> None:
        """On a timeout the duration is how long we waited, not how long it took.

        Averaging a truncated duration into a latency baseline measures the
        harness's patience, and a case that timed out at the ceiling would drag
        its own baseline upward until genuinely slow responses looked normal
        (`test_taxonomy.md` section 9.3).

        Args:
            minimal_case (Any): The case to dispatch.
            session (DispatchSession): The paced session.
            tmp_path (Any): pytest's temporary directory.
            scripted (Any): Dispatch scripting helper.

        Returns:
            None
        """
        session.max_attempts = 1
        scripted(claude_error("timeout"))
        timed_out = dispatch_case(minimal_case, "claude", _plan(tmp_path), session)
        assert timed_out.duration_kind == "truncated"

        scripted(claude_response())
        measured = dispatch_case(minimal_case, "claude", _plan(tmp_path), session)
        assert measured.duration_kind == "measured"


class TestMQCCircuitBreaker:
    """When the run stops rather than spending quota to confirm a failure."""

    def MQC_EXE_UNI_10229_circuit_breaker_aborts_after_consecutive_failures(
        self, minimal_case: EvaluationCase, session: DispatchSession, tmp_path: Path, scripted: Any
    ) -> None:
        """Consecutive, not cumulative.

        A long run against a flaky provider legitimately accumulates scattered
        failures while still producing a usable measurement. A streak means the
        provider stopped answering, and a success resets it.

        Args:
            minimal_case (Any): The case to dispatch.
            session (DispatchSession): The paced session.
            tmp_path (Any): pytest's temporary directory.
            scripted (Any): Dispatch scripting helper.

        Returns:
            None
        """
        session.max_attempts = 1
        session.breaker_threshold = 3
        plan = _plan(tmp_path)

        scripted(claude_error("rate_limit"))
        dispatch_case(minimal_case, "claude", plan, session)
        dispatch_case(minimal_case, "claude", plan, session)
        assert session.consecutive_failures == 2

        scripted(claude_response())
        dispatch_case(minimal_case, "claude", plan, session)
        assert session.consecutive_failures == 0

        scripted(claude_error("rate_limit"))
        dispatch_case(minimal_case, "claude", plan, session)
        dispatch_case(minimal_case, "claude", plan, session)
        with pytest.raises(CircuitBreakerTripped, match="consecutively"):
            dispatch_case(minimal_case, "claude", plan, session)

    def MQC_EXE_UNI_10230_auth_error_aborts_immediately(
        self, minimal_case: EvaluationCase, session: DispatchSession, tmp_path: Path, scripted: Any
    ) -> None:
        """An auth failure will not resolve by waiting, so the streak is irrelevant.

        Every subsequent case fails identically, so accumulating a streak would
        issue requests that were all going to fail.

        Args:
            minimal_case (Any): The case to dispatch.
            session (DispatchSession): The paced session.
            tmp_path (Any): pytest's temporary directory.
            scripted (Any): Dispatch scripting helper.

        Returns:
            None
        """
        session.breaker_threshold = 99
        scripted(claude_error("auth"))
        with pytest.raises(CircuitBreakerTripped, match="QC_HARNESS_AUTH_ERROR"):
            dispatch_case(minimal_case, "claude", _plan(tmp_path), session)
        assert session.consecutive_failures == 0


class TestMQCDispatcherRestraint:
    """What the dispatcher and its adapters deliberately do not do."""

    def MQC_EXE_UNI_10232_adapter_performs_no_scoring_or_interpretation(self) -> None:
        """An adapter that interprets output is a second evaluator with no rubric.

        Asserted structurally over the registry rather than by reading one
        adapter, so a future adapter cannot pass by being the one nobody
        checked. Nothing downstream would know its opinion had been mixed into
        a score.

        Returns:
            None
        """
        forbidden = {"score", "judge", "evaluate", "grade", "verdict", "assess"}
        for adapter_class in registered_adapters():
            members = {name.lower() for name in dir(adapter_class) if not name.startswith("_")}
            assert not members & forbidden
        assert not {field.lower() for field in NormalizedResponse.__annotations__} & forbidden

    def MQC_EXE_UNI_10271_an_unregistered_mode_is_rejected_before_any_adapter(
        self, tmp_path: Path
    ) -> None:
        """Mode selection is independent of engine selection.

        Rejecting it on the plan means an invalid mode cannot be absorbed by
        whichever adapter happened to be chosen, which would make the error
        depend on the engine.

        Args:
            tmp_path (Any): pytest's temporary directory.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR"):
            DispatchPlan(mode="cached", fixture_root=tmp_path)


class TestMQCConnectionLifecycle:
    """A connection belongs to one case, and the judge never borrows it."""

    @staticmethod
    def _spy(monkeypatch: Any) -> list[Any]:
        """Make dispatch open a client, and record every adapter that ran.

        ``dispatch_case`` builds its own adapter, so a case cannot reach it any
        other way. **The double opens a client rather than asserting one was
        opened**, which is what makes the release observable at all: the real
        client is constructed lazily on first dispatch and a test that never
        dispatches has nothing to release.

        Args:
            monkeypatch (Any): pytest's patcher.

        Returns:
            list: Populated with each adapter instance that dispatched.
        """
        ran: list[Any] = []

        class _Client:
            """A client that records being closed."""

            def __init__(self) -> None:
                """Start open.

                Returns:
                    None
                """
                self.closed = False

            def close(self) -> None:
                """Record the close.

                Returns:
                    None
                """
                self.closed = True

        def fake_dispatch(self: Any, request: Any) -> Any:
            """Open a client, as a real dispatch does, then answer.

            Args:
                self (Any): The adapter.
                request (Any): The composed request, unused.

            Returns:
                Any: A response double.
            """
            if self._client is None:  # pylint: disable=protected-access
                self._client = _Client()  # pylint: disable=protected-access
            assert request is not None, "dispatch was handed no request"
            ran.append(self)
            return claude_response()

        monkeypatch.setattr(ClaudeAdapter, "dispatch", fake_dispatch)
        return ran

    def MQC_EXE_UNI_10275_a_connection_left_open_after_a_response_is_reported(
        self,
        minimal_case: EvaluationCase,
        session: DispatchSession,
        tmp_path: Path,
        monkeypatch: Any,
    ) -> None:
        """The client is released once the case has its answer.

        **The cost this saves was already being paid.** ``dispatch_case``
        constructs a fresh adapter per call, so a run already opened one
        connection per case; it simply never released any of them, which is the
        setup cost of isolation without the isolation.

        **Two cases, so accumulation is what is observed** rather than a single
        release. One case passing says nothing about a pool that grows.

        Args:
            minimal_case (EvaluationCase): The case to dispatch.
            session (DispatchSession): Run-level pacing state.
            tmp_path (Path): pytest's temporary directory.
            monkeypatch (Any): pytest's patcher.

        Returns:
            None
        """
        ran = self._spy(monkeypatch)
        plan = _plan(tmp_path, mode="live")

        for index in range(2):
            assert dispatch_case(minimal_case, "claude", plan, session, index).measured

        assert len(ran) == 2, "each case should build its own adapter"
        assert ran[0] is not ran[1]
        for adapter in ran:
            assert not adapter.connected, (
                "the adapter still holds a client, so a run accumulates one "
                "connection pool per case for its whole length"
            )

    def MQC_EXE_UNI_10276_keeping_the_connection_is_opt_in_and_recorded(
        self,
        minimal_case: EvaluationCase,
        session: DispatchSession,
        tmp_path: Path,
        monkeypatch: Any,
    ) -> None:
        """Retained only when the invocation asks, which is the boundary.

        **Stated at the flag exactly.** The default and the flag are asserted
        against one another in one case, because a release test passing while
        the option does nothing is the failure mode worth excluding: an option
        nobody reads looks identical to an option set correctly.

        Args:
            minimal_case (EvaluationCase): The case to dispatch.
            session (DispatchSession): Run-level pacing state.
            tmp_path (Path): pytest's temporary directory.
            monkeypatch (Any): pytest's patcher.

        Returns:
            None
        """
        ran = self._spy(monkeypatch)
        held = DispatchPlan(
            mode="live", fixture_root=tmp_path, keep_connection=True
        )

        assert dispatch_case(minimal_case, "claude", held, session, 0).measured
        assert ran[-1].connected, "--keep-connection was supplied and ignored"

        # THE DEFAULT IS THE OTHER WAY, asserted here so neither branch can
        # pass by the option being unread.
        assert not DispatchPlan(mode="live", fixture_root=tmp_path).keep_connection
        assert dispatch_case(minimal_case, "claude", _plan(tmp_path, mode="live"),
                             session, 1).measured
        assert not ran[-1].connected

    def MQC_EXE_UNI_10277_a_judge_sharing_the_candidate_adapter_is_reported(
        self, tmp_path: Path
    ) -> None:
        """The judge builds its own adapter, on the candidate's own engine.

        **Same engine deliberately.** Under the zero-cost configuration judge
        and candidate frequently name one provider (A3), which is the case
        where sharing a client is tempting and where the test is worth
        anything. A channel built for a different engine would differ for an
        uninteresting reason.

        Args:
            tmp_path (Path): pytest's temporary directory, unused but keeping
                the signature uniform with its neighbours.

        Returns:
            None
        """
        assert tmp_path.is_dir()
        channel = JudgeChannel("claude", spacing_sec=1.0)
        candidate = ClaudeAdapter()

        assert channel.engine == candidate.engine_name
        assert channel.adapter is not candidate, (
            "the judge dispatches through the candidate's adapter, so the "
            "isolation holds in the composed request and not in the transport"
        )

        # AND IT PACES ITSELF. An unpaced judge spends the candidate's quota
        # from a second, uncounted direction.
        assert channel._session.spacing_sec == 1.0  # pylint: disable=protected-access

        # Two channels never share either, or one judge engine would serialize
        # every run in the process.
        assert JudgeChannel("claude").adapter is not channel.adapter


class TestMQCRecordingEconomy:
    """What a recording run spends, and on what."""

    def MQC_EXE_UNI_10293_filling_gaps_dispatches_only_what_is_missing(
        self,
        minimal_case: EvaluationCase,
        session: DispatchSession,
        tmp_path: Path,
        monkeypatch: Any,
    ) -> None:
        """An observation already recorded is replayed, not asked again.

        **Under a rate limit this is what stops a corpus converging.** Quota
        spent re-dispatching an observation that exists is quota not spent on
        one that does not: a 27-observation corpus with nine recorded would
        cost 27 requests to complete rather than 18.

        **The provider is made to fail if reached for a recorded index**, which
        asserts that it must not happen rather than counting how often it did.

        Args:
            minimal_case (EvaluationCase): The case to dispatch.
            session (DispatchSession): Run-level pacing state.
            tmp_path (Path): The fixture root.
            monkeypatch (Any): pytest's patcher.

        Returns:
            None
        """
        adapter = ClaudeAdapter()
        request = adapter.compose_request(minimal_case)
        stored = adapter.normalize_response(claude_response(), minimal_case.case_id)

        # OBSERVATION 0 IS RECORDED; 1 IS NOT.
        record_fixture(
            tmp_path,
            FixtureKey(minimal_case.case_id, "claude", 0),
            hash_request(request),
            stored.as_mapping(),
            stored.resolved_model,
        )

        dispatched: list[int] = []

        def counted(self: Any, composed: Any) -> Any:
            """Record that the provider was reached.

            Args:
                self (Any): The adapter.
                composed (Any): The request.

            Returns:
                Any: A response double.
            """
            assert self is not None and composed is not None
            dispatched.append(len(dispatched))
            return claude_response()

        monkeypatch.setattr(ClaudeAdapter, "dispatch", counted)
        plan = DispatchPlan(mode="live", fixture_root=tmp_path, fill_gaps=True)

        recorded = dispatch_case(minimal_case, "claude", plan, session, 0)
        assert recorded.measured
        assert not dispatched, (
            "a recorded observation was dispatched again, so a recording run "
            "spends quota replacing what it already had"
        )

        absent = dispatch_case(minimal_case, "claude", plan, session, 1)
        assert absent.measured
        assert len(dispatched) == 1, "the missing observation was not dispatched"

        # WITHOUT THE FLAG, LIVE MEANS LIVE. A run asking what the model says
        # now must not answer from a file.
        dispatched.clear()
        assert dispatch_case(
            minimal_case, "claude",
            DispatchPlan(mode="live", fixture_root=tmp_path), session, 0,
        ).measured
        assert len(dispatched) == 1, (
            "--mode live answered observation 0 from a fixture without being "
            "asked to fill gaps"
        )

    def MQC_EXE_UNI_10294_a_retry_attempt_opens_its_own_connection(
        self,
        minimal_case: EvaluationCase,
        session: DispatchSession,
        tmp_path: Path,
        monkeypatch: Any,
    ) -> None:
        """A failed attempt's connection is discarded before the next.

        **A failed attempt can leave the connection worse than it found it**: a
        half-open socket, a stuck stream, or a pool entry pinned to the
        instance that just returned 503. Retrying on it asks the same unhealthy
        path the same question.

        **Asserted as a sequence, not a count.** What matters is that a client
        opened for one attempt is gone before the next opens its own, which a
        tally of releases would not establish.

        Args:
            minimal_case (EvaluationCase): The case to dispatch.
            session (DispatchSession): Run-level pacing state.
            tmp_path (Path): The fixture root.
            monkeypatch (Any): pytest's patcher.

        Returns:
            None
        """
        journal: list[str] = []

        class _Client:
            """A client that records being closed."""

            def close(self) -> None:
                """Record the close.

                Returns:
                    None
                """
                journal.append("closed")

        def flaky(self: Any, composed: Any) -> Any:
            """Open a client, note it, and fail retryably.

            Args:
                self (Any): The adapter.
                composed (Any): The request.

            Returns:
                Any: Never; this always raises.

            Raises:
                Exception: A retryable provider failure.
            """
            assert composed is not None
            if self._client is None:  # pylint: disable=protected-access
                self._client = _Client()  # pylint: disable=protected-access
                journal.append("opened")
            raise claude_error("unavailable_503")

        monkeypatch.setattr(ClaudeAdapter, "dispatch", flaky)
        session.max_attempts = 3
        session.backoff_sec = 0.0

        outcome = dispatch_case(
            minimal_case, "claude",
            DispatchPlan(mode="live", fixture_root=tmp_path), session, 0,
        )

        assert not outcome.measured
        assert outcome.taxonomy_code == "QC_HARNESS_PROVIDER_UNAVAILABLE"

        # OPENED AND CLOSED, THREE TIMES OVER, alternating. A connection is
        # never carried from one attempt into the next.
        assert journal == ["opened", "closed"] * 3, (
            f"the connection journal was {journal}, so an attempt inherited "
            f"the connection state of the one before it"
        )


class TestMQCRetainedRequest:
    """The call a finding is filed from, kept where the outcome is."""

    def MQC_EXE_UNI_10310_an_outcome_carries_the_request_that_produced_it(
        self, minimal_case: EvaluationCase, session: DispatchSession, tmp_path: Path
    ) -> None:
        """Every dispatch outcome carries the composed request.

        A finding is filed with the provider, and a ticket needs the exact
        call rather than a description of it. The request was hashed for the
        fixture store and discarded with the context that held it.

        **On every outcome, not only a failing one.** A case's verdict is not
        known while its observations are being taken, and the passing
        observations of a failing case are what its report needs.

        **Including an outcome that measured nothing**, because a harness event
        is the case where knowing what was sent matters most.

        Design: ``tier2_execution.md`` section 7.8.

        Args:
            minimal_case (Any): The case to dispatch.
            session (DispatchSession): The run's session.
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        plan = _plan(tmp_path, mode="replay")
        adapter = ClaudeAdapter()
        composed = adapter.compose_request(minimal_case)
        stored = adapter.normalize_response(claude_response(), minimal_case.case_id)
        record_fixture(
            tmp_path,
            FixtureKey(minimal_case.case_id, "claude", 0),
            hash_request(composed),
            stored.as_mapping(),
            stored.resolved_model,
        )

        replayed = dispatch_case(minimal_case, "claude", plan, session, 0)

        assert replayed.measured
        assert replayed.request == composed, (
            "a measured outcome carries no request, so a finding cannot be "
            "filed from the artifact without reconstructing the call by hand"
        )

        # AND WHEN NOTHING WAS MEASURED. Observation 1 has no fixture, so this
        # is the missing-fixture path, which is a harness event.
        unmeasured = dispatch_case(minimal_case, "claude", plan, session, 1)

        assert not unmeasured.measured
        assert unmeasured.taxonomy_code == "QC_HARNESS_FIXTURE_MISSING"
        assert unmeasured.request == composed, (
            "an outcome that measured nothing carries no request, which is the "
            "case where what was sent matters most"
        )

        # THE REQUEST IS SERIALIZABLE, which `hash_request` already requires: a
        # provider object here would have escaped the adapter.
        assert hash_request(replayed.request) == hash_request(composed)
