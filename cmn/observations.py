# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The observation record, and the run-scoped fields every result repeats.

Field definitions are normative in ``docs/design/test_taxonomy.md`` section 9.
``docs/design/cmn_verdict_and_cli.md`` section 3 states what the verdict does
with them, and this module is the executable form of both.

**Observations are assembled, not emitted by tiers.** Tier 3 never receives
priority, so it cannot produce a complete observation. The orchestrating test
holds the case metadata and the reporting hook merges it with the tier results.

**Run-scoped fields are emitted twice**, once in a manifest and again on every
result. Collectors key on per-test rows, so a field living only in a manifest
may never reach per-test history, and a stored result whose thresholds cannot be
recovered is uninterpretable years later.

**`gated` is derived, never set.** An artifact that could claim to be gated by
asserting it would defeat the rule, so it is computed from three facts that are
each recorded independently.
"""

import dataclasses
import logging
from dataclasses import dataclass, field
from typing import Any, Final, Optional

from cmn.tokens import CaseUsage
from cmn.layers import layer_properties, outcome_properties
from cmn.registries import registered_evaluation_families

logger = logging.getLogger(__name__)

_RUN_CONTEXTS: Final[frozenset[str]] = frozenset({"ci", "ci_debug", "local"})
_SELECTION_MODES: Final[frozenset[str]] = frozenset({"full", "change_scoped", "manual"})

# The only selection modes a verdict may be computed from. A hand-typed subset
# is arbitrary and has no backstop, so a verdict from one is a partial verdict.
_VERDICT_SELECTIONS: Final[frozenset[str]] = frozenset({"full", "change_scoped"})

_DURATION_KINDS: Final[frozenset[str]] = frozenset({"measured", "truncated"})

# Required on every emitted result. A result missing one of these cannot be
# interpreted from the artifact alone, which is the entire purpose of the
# durable record.
_REQUIRED_RESULT_FIELDS: Final[tuple[str, ...]] = (
    "case_id", "layer", "observation_index", "engine", "mode", "outcome",
    "requested_model", "resolved_model", "duration", "duration_kind",
)


@dataclass(frozen=True)
class RunContext:
    """The run-scoped fields, repeated onto every result.

    Attributes:
        run_context (str): ``ci``, ``ci_debug`` or ``local``.
        selection_mode (str): ``full``, ``change_scoped`` or ``manual``.
        preconditions_executed (bool): Whether the precondition layers ran.
        rule_set_hash (str): Which rules produced this run.
        effective_thresholds (dict): The standard the run was judged against,
            so a verdict is recomputable from stored artifacts.
        timeout_ms (int): Changing it changes results.
        cli_flags (dict): Every flag that can change a result.
        platform (str): Which platform produced it. The harness is verified on
            two (A18).
    """

    run_context: str
    selection_mode: str
    preconditions_executed: bool
    rule_set_hash: str = ""
    effective_thresholds: dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 0
    cli_flags: dict[str, Any] = field(default_factory=dict)
    platform: str = ""

    def __post_init__(self) -> None:
        """Refuse a context carrying an unregistered value.

        Returns:
            None

        Raises:
            ValueError: With ``QC_HARNESS_PARSER_ERROR`` for an unregistered
                run context or selection mode.
        """
        if self.run_context not in _RUN_CONTEXTS:
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: run context {self.run_context!r} is not one "
                f"of {sorted(_RUN_CONTEXTS)}"
            )
        if self.selection_mode not in _SELECTION_MODES:
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: selection mode {self.selection_mode!r} is not "
                f"one of {sorted(_SELECTION_MODES)}"
            )

    @property
    def gated(self) -> bool:
        """Report whether a verdict may be computed from this run.

        **Derived from three facts, never set.** All must hold:

        * the selection was computed by the harness rather than typed by hand,
          because a hand-typed subset has no backstop and yields a partial
          verdict;
        * the preconditions executed, because graded results from a run whose
          harness was never verified are suspect anyway;
        * the run context is ``ci``, because a debug job may be exercising a
          different harness branch entirely against different test cases.

        Returns:
            bool: True only when all three hold.
        """
        return (
            self.selection_mode in _VERDICT_SELECTIONS
            and self.preconditions_executed
            and self.run_context == "ci"
        )

    def as_fields(self) -> dict[str, Any]:
        """Return the run-scoped fields for repetition onto a result.

        Returns:
            dict: The fields, including the derived ``gated`` flag so a
            consumer reading one row need not recompute it.
        """
        return {
            "run_context": self.run_context,
            "selection_mode": self.selection_mode,
            "gated": self.gated,
            "rule_set_hash": self.rule_set_hash,
            "effective_thresholds": dict(self.effective_thresholds),
            "timeout_ms": self.timeout_ms,
            "cli_flags": dict(self.cli_flags),
            "os": self.platform,
        }


@dataclass(frozen=True)
class Observation:
    """One measured execution of one case, as the verdict function reads it.

    Attributes:
        case_id (str): Which case.
        layer (str): Which layer, from which graded status is read.
        outcome (str): ``pass``, ``fail``, ``broken`` or ``skip``.
        observation_index (int): Which of the repeat observations (A4).
        priority (Optional[int]): P0 to P4 on graded results, absent on a
            precondition, which sits above the scale rather than below it.
        priority_conditions (list): The matched condition identifiers (G6).
        skip_reason (Optional[str]): Why it skipped, counted differently by
            reason (A13).
        taxonomy_code (Optional[str]): Root-cause class.
        family (Optional[str]): The evaluation family, on graded results only.
        engine (str): Which provider produced it.
        mode (str): ``live`` or ``replay`` (A6).
        requested_model (str): What was asked for.
        resolved_model (str): What the provider returned (A8).
        duration (int): Milliseconds.
        duration_kind (str): ``measured`` or ``truncated``.
        output_tokens (int): Latency is dominated by verbosity (A7.2).
        tokens (CaseUsage): Every token this observation consumed, on both
            sides of a judged case. **One field rather than six**, for the reason
            `.pylintrc` gives about its attribute limit: what a case consumed is
            one fact about an execution. ``output_tokens`` stays beside it
            because A7.2 reads it as a latency signal rather than a cost one, and
            that predates any of this.
        score (Optional[float]): Recorded on passes as well as failures.
        scale_id (Optional[str]): Scores of differing scale are not comparable.
        rubric_result (Optional[str]): ``evaluated``, or not evaluated with a
            reason.
        requirement_ids (list): RTM traceability.
        demoted (bool): Whether the case was demoted from a higher priority.
    """

    case_id: str
    layer: str
    outcome: str
    observation_index: int = 0
    priority: Optional[int] = None
    priority_conditions: list[str] = field(default_factory=list)
    skip_reason: Optional[str] = None
    taxonomy_code: Optional[str] = None
    family: Optional[str] = None
    engine: str = ""
    mode: str = "replay"
    requested_model: str = ""
    resolved_model: str = ""
    duration: int = 0
    duration_kind: str = "measured"
    output_tokens: int = 0
    tokens: CaseUsage = field(default_factory=CaseUsage)
    score: Optional[float] = None
    scale_id: Optional[str] = None
    rubric_result: Optional[str] = None
    requirement_ids: list[str] = field(default_factory=list)
    demoted: bool = False

    def __post_init__(self) -> None:
        """Refuse an observation the verdict function could not interpret.

        Returns:
            None

        Raises:
            ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the layer or
                outcome is unregistered, when a graded result carries no
                priority, when a precondition carries one, or when a duration
                kind is unregistered.
        """
        properties = layer_properties(self.layer)
        outcome_properties(self.outcome)

        if properties.carries_priority and self.priority is None:
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: {self.case_id} is graded and carries no "
                f"priority; a priority without a named condition is not assignable, and "
                f"a graded case without one cannot be gated"
            )
        if not properties.carries_priority and self.priority is not None:
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: {self.case_id} is a precondition carrying "
                f"priority {self.priority}; preconditions sit above the scale, and "
                f"marking them would put them in a distribution denominator measured "
                f"over graded cases"
            )
        if self.family is not None:
            if not properties.graded:
                raise ValueError(
                    f"QC_HARNESS_PARSER_ERROR: {self.case_id} is a precondition carrying "
                    f"family {self.family!r}; a precondition tests the harness, which "
                    f"performs no task"
                )
            if self.family not in registered_evaluation_families():
                raise ValueError(
                    f"QC_HARNESS_PARSER_ERROR: family {self.family!r} is not registered; "
                    f"registered families are {sorted(registered_evaluation_families())}"
                )
        if self.duration_kind not in _DURATION_KINDS:
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: {self.case_id} carries duration kind "
                f"{self.duration_kind!r}, which is neither measured nor truncated"
            )

    @property
    def graded(self) -> bool:
        """Report whether this observation measures the model.

        Returns:
            bool: Read from the layer registration, never from the token.
        """
        return layer_properties(self.layer).graded

    @property
    def passed(self) -> bool:
        """Report whether this counts as a passing execution.

        Returns:
            bool: Read from the outcome registration.
        """
        return outcome_properties(self.outcome).is_pass

    @property
    def counts_in_latency(self) -> bool:
        """Report whether this duration may enter a latency statistic.

        Returns:
            bool: False for a truncated duration. It records how long the
            harness waited, not how long the model took, and averaging it in
            would measure our own patience while dragging the baseline upward
            until genuinely slow responses looked normal.
        """
        return self.duration_kind == "measured"


def assemble_observation(
    case_metadata: dict[str, Any], tier_results: dict[str, Any]
) -> Observation:
    """Merge case metadata with what the tiers produced.

    **Neither half is sufficient alone.** Tier 3 never receives priority, so it
    cannot produce a complete observation; the orchestrating test holds the case
    metadata and has no access to what dispatch measured.

    Args:
        case_metadata (dict): Identity and grading metadata, held by the test.
        tier_results (dict): What execution and evaluation produced.

    Returns:
        Observation: The merged record.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the merged record is
            missing a field the durable record requires.
    """
    merged = {**case_metadata, **tier_results}
    permitted = {entry.name for entry in dataclasses.fields(Observation)}
    unknown = sorted(set(merged) - permitted)
    if unknown:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: an observation cannot carry {', '.join(unknown)}; "
            f"a field the record does not declare would reach the artifact unread"
        )
    return Observation(**merged)


def require_complete_result(emitted: dict[str, Any]) -> dict[str, Any]:
    """Refuse an emitted result missing a field required for interpretation.

    Args:
        emitted (dict): The result about to be written.

    Returns:
        dict: The same mapping, once it is known to be complete.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` naming every missing
            field. A result that reaches the durable record incomplete is
            uninterpretable later and looks exactly like one that is not.
    """
    missing = [name for name in _REQUIRED_RESULT_FIELDS if name not in emitted]
    if missing:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: a result is missing {', '.join(missing)}, so it "
            f"could not be interpreted from the artifact alone"
        )
    return emitted


def registered_run_contexts() -> frozenset[str]:
    """Return every registered run context.

    Returns:
        frozenset[str]: The three contexts.
    """
    return _RUN_CONTEXTS


def registered_selection_modes() -> frozenset[str]:
    """Return every registered selection mode.

    Returns:
        frozenset[str]: The three modes.
    """
    return _SELECTION_MODES


def required_result_fields() -> tuple[str, ...]:
    """Return the fields every emitted result must carry.

    Returns:
        tuple[str, ...]: The required names.
    """
    return _REQUIRED_RESULT_FIELDS


# TWO, AND NOT "UNTIL IT IS CERTAIN". Two more takes a case from three
# observations to five, where one disagreement reads as a fifth. Sampling until
# some confidence was reached would spend unboundedly on exactly the cases
# hardest to characterise, and quota is the binding constraint on every
# recording run this project does. Design section 4.9.2.2.
_ESCALATION: Final[int] = 2


def further_observations(outcomes: list[bool]) -> int:
    """Return how many more observations a pattern of outcomes earns.

    **Exactly one disagreement earns two more, and nothing else earns any.**
    Three observations can only put a case at 0, 33, 67 or 100 percent
    disagreement. Of those, only the 33 is worth refining: zero has nothing to
    refine, and 67 or 100 is already established far above any ceiling. Design
    section 4.9.2.1 carries the decision and the arithmetic.

    **It does not change the verdict.** The case is inconsistent either way, by
    the binary rule in section 4.9.1 which a majority would undo. What the two
    further observations buy is the **severity**: one in five and three in five
    are different findings although both fail.

    **It escalates once.** Five observations showing one disagreement are not
    taken to ten, because the decision is that a fifth is a legible number and
    not that a tenth is needed. A second escalation is a later decision with its
    own arithmetic, so this function is not a loop.

    Args:
        outcomes (list[bool]): Whether each observation so far passed, in the
            order observed. **Outcomes only**, because the rule reads agreement
            and nothing else about a result.

    Returns:
        int: How many further observations to dispatch. **Zero for fewer than
        two outcomes**: one sample cannot disagree with itself, which is the
        same answer :func:`consistent` gives for the same reason.
    """
    if len(outcomes) < 2:
        return 0
    # FAILURES, NOT THE MINORITY. A case is asked to pass every time, so a
    # disagreement is an observation that failed. Reading the minority instead
    # made two failures of three escalate, which is already two thirds and
    # established.
    failures = len(outcomes) - sum(outcomes)
    if failures != 1:
        return 0
    # ONCE ONLY. Reached five, the rule has said what it has to say.
    if len(outcomes) >= 2 + _ESCALATION + 1:
        return 0
    return _ESCALATION
