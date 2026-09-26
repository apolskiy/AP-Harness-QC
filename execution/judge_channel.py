# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The judge's own connection, kept apart from the candidate's.

Specified by ``docs/design/tier2_execution.md`` section 7.7.3.

**This module hands out a callable and nothing else.** Tier 3 holds the judge
binding and knows only that ``invoke`` can be called with a composed request;
it does not import this module and this module does not import it. Neither tier
imports the other today, in either direction, and a factory returning a
``JudgeBinding`` would have been the first breach.

**The channel builds its own adapter rather than accepting one.** A judge
frequently names the same provider as the candidate under the zero-cost
configuration (A3), which is exactly what makes sharing a client tempting and
wrong: it blurs which call spent which part of one free-tier quota, and it puts
the judge's request on the socket that has just carried adversarial content.

**And it paces itself.** Judge calls were previously unpaced while candidate
calls waited out a configured interval, both against the same quota.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Optional

from cmn.config import (
    load_engines,
    load_judge_engine,
    load_judge_model,
    resolve_judge_engine,
)
from execution.adapters.registry import (
    JUDGE_ROLE,
    adapter_for,
    engines_for_role,
)
from execution.dispatch import DispatchSession
from execution.replay import (
    JudgementKey,
    hash_request,
    load_judgement,
    record_judgement,
)

logger = logging.getLogger(__name__)



@dataclass(frozen=True)
class JudgementPlan:
    """How a judge channel obtains a judgement, as opposed to which judge.

    Mirrors :class:`~execution.dispatch.DispatchPlan`, and is separate from the
    channel for the same reason: the channel holds an adapter and a connection,
    while this holds the run's choices.

    Attributes:
        mode (str): ``live`` or ``replay``, already resolved by
            :func:`cmn.options.resolve_judge_mode`, which defaults it to
            ``--mode`` and refuses the incoherent quadrant (design 5A.5).
        fixture_root (Optional[Path]): Where judgements are stored. **Required
            for replay**, and absent means a live channel that records nothing,
            which is what a test wants.
        record (bool): Whether a live judgement is stored for later replay.
    """

    mode: str = "live"
    fixture_root: Optional[Path] = None
    record: bool = False

    def __post_init__(self) -> None:
        """Refuse a plan that cannot do what it says.

        Returns:
            None

        Raises:
            ValueError: With ``QC_HARNESS_PARSER_ERROR`` for an unregistered
                mode, or for replay with nowhere to read from. **Refused here
                rather than at the first judgement**, so a misconfigured run
                does not spend candidate quota before discovering it cannot
                grade what it bought.
        """
        if self.mode not in ("live", "replay"):
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: {self.mode!r} is not a judge mode"
            )
        if self.mode == "replay" and self.fixture_root is None:
            raise ValueError(
                "QC_HARNESS_PARSER_ERROR: judge replay names no fixture root, "
                "so there is nothing to replay from"
            )


class JudgeChannel:
    """One judge engine, with its own adapter, pacing and release.

    Usable as a context manager, which is the form that releases on the way out
    of an exception as well as a return.

    Attributes:
        engine (str): The engine that grades.
    """

    def __init__(
        self,
        engine: str,
        model: Optional[str] = None,
        spacing_sec: float = 0.0,
        *,
        keep_connection: bool = False,
        plan: Optional[JudgementPlan] = None,
    ) -> None:
        """Construct a judge channel and the adapter it owns.

        **The adapter is built here, never passed in.** Accepting one would
        make sharing the candidate's client a caller's decision, and the point
        of this class is that it is not available as a decision.

        Args:
            engine (str): The registered engine that grades.
            model (Optional[str]): The model to request, or the adapter's
                declared default.
            spacing_sec (float): Minimum interval between judge requests, from
                the engine roster. **The judge's own budget**, tracked
                separately from the candidate's so neither absorbs the other's
                waiting.
            keep_connection (bool): Whether to hold the connection between
                judgements. Default false, matching the candidate rule in
                design section 7.7.2.
            plan (Optional[JudgementPlan]): How judgements are obtained.
                Absent means live with no recording.

        Returns:
            None
        """
        self._adapter = adapter_for(engine)(model)
        self._session = DispatchSession(spacing_sec=spacing_sec)
        self._keep_connection = keep_connection
        self._plan = plan or JudgementPlan()

    @property
    def engine(self) -> str:
        """Return the engine that grades.

        Returns:
            str: The registered engine name.
        """
        return self._adapter.engine_name

    @property
    def adapter(self) -> Any:
        """Return the adapter this channel owns.

        Exposed so that ``MQC_EXE_UNI_10277`` can establish it is not the
        candidate's. **Reading it is not borrowing it**: nothing dispatches
        through an adapter it did not build.

        Returns:
            Any: The :class:`ProviderAdapter` constructed for this channel.
        """
        return self._adapter

    def invoke(self, request: Any) -> dict[str, Any]:
        """Issue one judge request, paced on the judge's own interval.

        **One call, like every other.** A judgement is a single request with no
        loop, for the same reason a candidate dispatch is (A19).

        **The prompt arrives already composed.** Tier 3 owns the isolation
        split, so this renders what it was given and never rebuilds it: an
        adapter composing the instruction itself could put candidate output
        into it, which is the one thing isolation exists to prevent.

        Args:
            request (Any): A ``JudgeRequest``, typed loosely so Tier 2 does not
                import Tier 3's record and invert the dependency.

        Returns:
            dict[str, Any]: The reply as a mapping, which is what
            ``validate_judge_reply`` reads. **Parsed, not validated**: whether
            the scores are in range and whether the shape is evidence of hijack
            both belong to Tier 3.
        """
        composed = self._adapter.compose_judgement(
            request.rendered(), request.reply_schema
        )
        key = JudgementKey(
            case_id=request.case_id,
            judge_engine=self.engine,
            observation_index=getattr(request, "observation_index", 0),
        )
        request_hash = hash_request(composed)

        if self._plan.mode == "replay":
            # NO FALL BACK TO A LIVE CALL. load_judgement raises rather than
            # returning anything mistakable for a score, and catching it here
            # would create the fail-open path section 7.9.1 says must not
            # exist: a replay run that quietly judges spends quota on every
            # pull request.
            return self._stored_reply(key, request_hash)

        self._session.wait_for_slot()
        try:
            reply = self._adapter.parse_judgement(self._adapter.dispatch(composed))
        except ValueError:
            # ALREADY OURS AND ALREADY SHAPED. `parse_judgement` raises this
            # carrying its own code, and the pipeline reads it.
            #
            # A HIJACK FINDING CANNOT ARRIVE HERE and is deliberately not
            # named: it is raised by `validate_judge_reply`, which runs in
            # Tier 3 after this returns. Naming it would make `execution/`
            # import `evaluation/`, which neither tier does in either
            # direction (design section 7.7.3).
            raise
        except Exception as error:
            # THE SAME TAXONOMY THE CANDIDATE PATH USES, reached through the
            # same adapter method. Before this, every provider failure during
            # judging escaped as a raw SDK exception, so a busy provider that
            # the candidate path handles as a retryable skip crashed a judged
            # case outright (design section 8.5.5).
            #
            # Raised as a ValueError because that is what the pipeline already
            # records as `judge_reply_unusable`: a harness event on the judge
            # path is a skip with a code, as it is everywhere else.
            code = self._adapter.map_error(error)
            logger.warning(
                "%s judging %s: %s", code, request.case_id, type(error).__name__
            )
            raise ValueError(
                f"{code}: the judge could not be reached for {request.case_id}"
            ) from error
        finally:
            self._session.last_request_at = self._session.monotonic()
            if not self._keep_connection:
                self._adapter.release()

        if self._plan.record and self._plan.fixture_root is not None:
            record_judgement(
                self._plan.fixture_root, key, request_hash,
                self._adapter.requested_model, reply,
            )
        return reply

    def _stored_reply(self, key: JudgementKey, request_hash: str) -> dict[str, Any]:
        """Return a recorded judgement, refusing a stale one.

        Args:
            key (JudgementKey): What to load.
            request_hash (str): Hash of the request that would be sent now.

        Returns:
            dict[str, Any]: The stored reply.

        Raises:
            FixtureMissing: When none exists, which a replay run records as a
                skip.
            FixtureStale: When the request or the judge model has moved.
        """
        stored = load_judgement(
            self._plan.fixture_root, key, request_hash, self._adapter.requested_model
        )
        return dict(stored.reply)

    def release(self) -> None:
        """Drop the judge's connection.

        Idempotent, and safe before any judgement.

        Returns:
            None
        """
        self._adapter.release()

    def __enter__(self) -> "JudgeChannel":
        """Enter the channel's scope.

        Returns:
            JudgeChannel: This channel.
        """
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """Release the connection on the way out, raised or returned.

        Args:
            exc_type (Optional[type]): The exception class, if one is in
                flight.
            exc_value (Optional[BaseException]): The exception.
            traceback (Optional[TracebackType]): Its traceback.

        Returns:
            None
        """
        self.release()


def judge_channel_from_roster(
    roster_path: Path,
    engine: Optional[str] = None,
    *,
    keep_connection: bool = False,
    plan: Optional[JudgementPlan] = None,
) -> JudgeChannel:
    """Build a judge channel from the configured roster.

    **The resolution already existed and had no caller.** ``cmn/config.py``
    could name a judge engine, refuse one that does not declare the capability
    and fall back to the roster model, and nothing in production built a judge
    from it. This is that caller.

    Args:
        roster_path (Path): The engine roster file.
        engine (Optional[str]): Overrides the configured judge, as
            ``--judge-engine`` does. Absent means the configured one.
        keep_connection (bool): Whether to hold the connection between
            judgements. Default false, matching the candidate rule.
        plan (Optional[JudgementPlan]): How judgements are obtained. Absent
            means live with no recording.

    Returns:
        JudgeChannel: Paced from the roster entry for the resolved engine, and
        carrying its own adapter.

    Raises:
        ValueError: With ``QC_HARNESS_PREFLIGHT_FAILURE`` when the engine is
            not on the roster or does not declare structured output. **Refused
            here rather than at the first judgement**, which is the difference
            between a run that does not start and a run that spends candidate
            quota and then cannot grade what it bought.
    """
    roster = load_engines(roster_path)
    resolved = resolve_judge_engine(
        engine or load_judge_engine(roster_path),
        roster,
        can_judge=lambda name: name in engines_for_role(JUDGE_ROLE),
    )
    entry = roster.get(resolved)
    return JudgeChannel(
        resolved,
        model=load_judge_model(roster_path, roster) if engine is None else None,
        spacing_sec=entry.spacing_sec if entry is not None else 0.0,
        keep_connection=keep_connection,
        plan=plan,
    )
