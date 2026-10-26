# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The golden rule set record, which states how a model's response is judged.

Created: 2026-10-18
Last updated: 2026-10-25

This file contains :class:`GoldenRuleSet`, which holds a rule's priority and
the conditions justifying it, its programmatic assertions, its optional rubric
and tool expectation, its requirement identifiers and its evaluation families;
:class:`ProgrammaticAssertion`, one deterministic check with its kind,
parameters, severity and taxonomy code; and :class:`ToolExpectation`, the
tools a response must and must not invoke. Each is built through
``from_dict``, which enforces the rule-set invariants.

**Evaluation reads every part of it.** The assertions run first, tool
compliance checks the expectation, the rubric goes to the judge, and the
priority travels with the case to the verdict gate.

Design: ``docs/design/tier1_ingestion.md`` sections 3.0, 3.5, 3.9 and 3.10.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Final, Optional

from cmn.registries import (
    registered_evaluation_families,
    priority_condition_level,
)
from ingestion.schemas.fields import (
    _normalize_text,
    _reject_unknown_keys,
    _require_present_and_filled,
    _reject_unsafe_identifier,
    _optional_text,
    _coerce_int,
)
from ingestion.schemas.rubric import (
    Rubric,
)

logger = logging.getLogger(__name__)

_LOWEST_PRIORITY: Final[int] = 4


@dataclass(frozen=True)
class ProgrammaticAssertion:
    """One deterministic check applied to a response.

    Attributes:
        assertion_id (str): Identifies the assertion within the rule set.
        kind (str): ``regex``, ``json_schema``, ``length``, ``contains`` or
            ``not_contains``.
        parameters (dict): Arguments for the kind.
        taxonomy_code (str): The code that fires on failure. Data rather than a
            hardcoded mapping, so a new check declares its own classification.
        severity (str): ``fatal`` or ``violation``. Both fail the case; they
            differ only in whether a judgement remains obtainable afterwards.
        constraint_ref (Optional[str]): The constraint this assertion checks.
    """

    assertion_id: str
    kind: str
    parameters: dict[str, Any]
    taxonomy_code: str
    severity: str
    constraint_ref: Optional[str] = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProgrammaticAssertion":
        """Build an assertion from a validated mapping.

        Args:
            payload (dict): Mapping carrying ``assertion_id``, ``kind``,
                ``parameters``, ``taxonomy_code`` and ``severity``.

        Returns:
            ProgrammaticAssertion: The frozen record.

        Raises:
            KeyError: When a required field is absent or an unknown key is present.
            ValueError: When a required field is empty or severity is unrecognized.
        """
        owner = str(payload.get("assertion_id", "<unidentified>"))
        _reject_unknown_keys(payload, cls, owner)
        _require_present_and_filled(
            payload,
            ("assertion_id", "kind", "parameters", "taxonomy_code", "severity"),
            cls.__name__,
            owner,
        )
        severity = _normalize_text(payload["severity"]).lower()
        if severity not in {"fatal", "violation"}:
            raise ValueError(
                f"QC_DATA_INVARIANT_VIOLATION: ProgrammaticAssertion {owner} severity must be "
                f"'fatal' or 'violation', received {severity!r}"
            )
        return cls(
            assertion_id=_normalize_text(payload["assertion_id"]),
            kind=_normalize_text(payload["kind"]),
            parameters=dict(payload["parameters"]),
            taxonomy_code=_normalize_text(payload["taxonomy_code"]),
            severity=severity,
            constraint_ref=_optional_text(payload.get("constraint_ref")),
        )


@dataclass(frozen=True)
class ToolExpectation:
    """What tool usage the response must and must not exhibit.

    Attributes:
        required_tools (frozenset): Tools the model is expected to invoke.
        forbidden_tools (frozenset): Tools the model must not invoke.
        constraint_ref (Optional[str]): The constraint this expectation checks.
    """

    required_tools: frozenset[str] = frozenset()
    forbidden_tools: frozenset[str] = frozenset()
    constraint_ref: Optional[str] = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ToolExpectation":
        """Build a tool expectation, enforcing invariant G4.

        G4 requires the required and forbidden sets to be disjoint. A tool in
        both is a contradictory expectation that no response can satisfy.

        Args:
            payload (dict): Mapping carrying optional tool sets.

        Returns:
            ToolExpectation: The frozen record.

        Raises:
            KeyError: When an unknown key is present.
            ValueError: When the two tool sets intersect.
        """
        _reject_unknown_keys(payload, cls, "<tool_expectation>")
        required = frozenset(_normalize_text(name) for name in payload.get("required_tools", ()))
        forbidden = frozenset(_normalize_text(name) for name in payload.get("forbidden_tools", ()))
        overlap = sorted(required & forbidden)
        if overlap:
            logger.error("QC_DATA_INVARIANT_VIOLATION tool expectation overlap %s", overlap)
            raise ValueError(
                f"QC_DATA_INVARIANT_VIOLATION: ToolExpectation names {overlap} as both "
                f"required and forbidden; no response can satisfy both"
            )
        return cls(
            required_tools=required,
            forbidden_tools=forbidden,
            constraint_ref=_optional_text(payload.get("constraint_ref")),
        )


@dataclass(frozen=True)
class GoldenRuleSet:
    """How a response is judged.

    Two consumers read this record and neither reads all of it. Tier 3 reads
    the evaluation half; CMN reads the priority and traceability half. Tier 3's
    interface receives only the evaluation subset, so that an implementation is
    never in a position to begin reading priority.

    Attributes:
        rule_id (str): ``MQC_RULE_<slug>``.
        priority (int): 0 to 4, bounded by the matched conditions' ceiling.
        priority_conditions (list): Registered condition identifiers matched.
        assertions (list): The deterministic half.
        rubric (Optional[Rubric]): The judged half.
        tool_expectation (Optional[ToolExpectation]): Tool compliance half.
        requirement_ids (list): Traceability identifiers, emitted to metadata.
        families (tuple): The evaluation families this rule grades,
            **ordered with the primary first**. Every value is registered
            and the relation is many to many, so a complex rule names
            several. Design ``harness_test_taxonomy.md`` sections 11.7 and 11.8.
        judge_response_only (bool): Judge a declared adversarial case on its
            answer alone once the answer screens clean. Requires a rubric (G8).
        relay_forbidden (bool): Whether reproducing the injected text in the
            answer fails the case. **Declared by the rule because the prompt
            decides it**: a task that tells the model to report an instruction
            and forbids nothing cannot fail it for quoting what it was told to
            report (section 4C.4.1).
    """

    rule_id: str
    priority: int
    priority_conditions: list[str]
    assertions: list[ProgrammaticAssertion] = field(default_factory=list)
    rubric: Optional[Rubric] = None
    tool_expectation: Optional[ToolExpectation] = None
    requirement_ids: list[str] = field(default_factory=list)
    # SECURITY ONLY, AND A MAPPING RATHER THAN A LIST. A vector explicitly
    # false records that somebody considered it; absence from a list records
    # nothing, and only the true entries need reaching a log. Design section
    # 3.5, and the decision in the consumer's test plan section 9.10.3.1.
    vectors: dict[str, bool] = field(default_factory=dict)
    # WHICH DECLARED VECTOR THE CASE IS ABOUT. Invariant G7 requires it to name
    # a vector this rule declares as carried: a payload carrying three vectors
    # is still a case about one of them, and asserting that a payload matches
    # some registered vector is satisfied by an incidental match.
    primary: Optional[str] = None
    # WHICH EVALUATION FAMILIES THIS RULE GRADES, primary first. Declared
    # rather than derived: the layer answers for SEC and TOOL because each
    # maps to one family, and EVAL spans four, so the layer could never
    # have answered for them. This is the source `harness_test_taxonomy.md` section
    # 11.5.1 recorded as missing, and the per-case mapping T5 takes.
    families: tuple[str, ...] = ()
    # A DECLARED ADVERSARIAL CASE JUDGED ON ITS ANSWER ALONE, once the answer
    # screens clean. No payload reaches a judge (tier3_evaluation.md 4C.4).
    judge_response_only: bool = False
    # AND WHETHER REPEATING THE INJECTION FAILS THE ANSWER, which only a task
    # that forbade the quote can ask for (tier3_evaluation.md 4C.4.1). Four
    # cases failed on every engine for quoting evidence their own prompt asked
    # them to report, which is what this declaration separates.
    relay_forbidden: bool = False


    @staticmethod
    def _validate_families(payload: Any, owner: str) -> tuple[str, ...]:
        """Return the declared families, refusing a value nothing can resolve.

        **Every value individually**, because a rule naming two families fails
        if either is unregistered rather than only if the first is.

        **A repeat is refused**, since a duplicate makes the primary ambiguous
        and would count the case twice in a per-family cost total.

        Design: ``harness_test_taxonomy.md`` sections 11.7.2 and 11.8.

        Args:
            payload (Any): The declared value, absent or a sequence.
            owner (str): The rule identifier, for the message.

        Returns:
            tuple[str, ...]: The families in declared order, primary first.
            **Empty is permitted here and refused one level up**: a rule set is
            also built in tests from a minimal payload, and which rules must
            declare a family is a property of a shipped corpus rather than of
            the schema.

        Raises:
            ValueError: With ``QC_DATA_INVARIANT_VIOLATION`` when a value is
                unregistered or repeated.
        """
        declared = tuple(_normalize_text(entry) for entry in (payload or ()))
        if not declared:
            return ()

        registered = registered_evaluation_families()
        unknown = [name for name in declared if name not in registered]
        if unknown:
            logger.error(
                "QC_DATA_INVARIANT_VIOLATION %s names unregistered families %s",
                owner, unknown,
            )
            raise ValueError(
                f"QC_DATA_INVARIANT_VIOLATION: GoldenRuleSet {owner} names families "
                f"{unknown}, which are not registered; registered families are "
                f"{sorted(registered)}"
            )
        if len(set(declared)) != len(declared):
            raise ValueError(
                f"QC_DATA_INVARIANT_VIOLATION: GoldenRuleSet {owner} repeats a family "
                f"in {list(declared)}, which makes the primary ambiguous and would "
                f"count the case twice in a per-family total"
            )
        return declared

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GoldenRuleSet":
        """Build a rule set, enforcing invariants G1 and G6.

        G1 requires at least one of assertions, rubric or tool expectation. A
        rule set that judges nothing is a silent no-op reporting green.

        G6 requires priority to be justified: the conditions are non-empty, each
        is registered, and the assigned priority respects the most severe
        matched condition's ceiling.

        Args:
            payload (dict): Mapping carrying ``rule_id``, ``priority`` and
                ``priority_conditions``, plus any judging halves.

        Returns:
            GoldenRuleSet: The frozen record.

        Raises:
            KeyError: When a required field is absent or an unknown key is present.
            ValueError: When a required field is empty, no judging half is
                present, a condition is unregistered, or priority exceeds its ceiling.
        """
        owner = str(payload.get("rule_id", "<unidentified>"))
        _reject_unknown_keys(payload, cls, owner)
        _require_present_and_filled(
            payload, ("rule_id", "priority", "priority_conditions"), cls.__name__, owner
        )
        rule_id = _reject_unsafe_identifier(_normalize_text(payload["rule_id"]), owner)
        priority = _coerce_int(payload["priority"], "priority", owner)
        conditions = [_normalize_text(entry) for entry in payload["priority_conditions"]]
        cls._validate_priority(priority, conditions, owner)

        assertions = [ProgrammaticAssertion.from_dict(dict(entry))
                      for entry in payload.get("assertions", ())]
        rubric_payload = payload.get("rubric")
        rubric = None if rubric_payload is None else Rubric.from_dict(dict(rubric_payload))
        expectation_payload = payload.get("tool_expectation")
        expectation = (
            None if expectation_payload is None
            else ToolExpectation.from_dict(dict(expectation_payload))
        )
        if not assertions and rubric is None and expectation is None:
            logger.error("QC_DATA_INVARIANT_VIOLATION %s judges nothing", owner)
            raise ValueError(
                f"QC_DATA_INVARIANT_VIOLATION: GoldenRuleSet {owner} carries no assertions, "
                f"rubric or tool expectation, so it judges nothing and would report green in "
                f"silence"
            )
        return cls(
            rule_id=rule_id,
            priority=priority,
            priority_conditions=conditions,
            assertions=assertions,
            rubric=rubric,
            tool_expectation=expectation,
            requirement_ids=[_normalize_text(entry)
                             for entry in payload.get("requirement_ids", ())],
            families=cls._validate_families(payload.get("families", ()), owner),
            # CAST EXPLICITLY AT THE BOUNDARY, like every other field here. A
            # YAML `true` is already a bool and a quoted "true" is not, and the
            # difference would decide whether a vector reads as declared.
            vectors={
                _normalize_text(name): bool(state)
                for name, state in (payload.get("vectors") or {}).items()
            },
            primary=(
                _normalize_text(payload["primary"])
                if payload.get("primary") is not None else None
            ),
            judge_response_only=cls._validate_response_only(payload, rubric, owner),
            relay_forbidden=bool(payload.get("relay_forbidden", False)),
        )

    @staticmethod
    def _validate_response_only(payload: dict[str, Any], rubric: Any, owner: str) -> bool:
        """Apply invariants G8 and G10: the flag needs a rubric, a planted score the flag.

        Design: ``tier1_ingestion.md`` section 3.5.

        Args:
            payload (dict): The rule payload.
            rubric (Any): The built rubric, or None.
            owner (str): Rule set identifier, for the message.

        Returns:
            bool: The declared flag, False when absent.

        Raises:
            ValueError: With ``QC_DATA_INVARIANT_VIOLATION`` when the flag is set
                and no rubric is authored, or a rubric plants a score on a rule
                whose judge never reads an answer to the attack.
        """
        declared = bool(payload.get("judge_response_only", False))
        if declared and rubric is None:
            raise ValueError(
                f"QC_DATA_INVARIANT_VIOLATION: GoldenRuleSet {owner} declares "
                f"judge_response_only and authors no rubric, so it says how it is "
                f"judged and has nothing to judge with"
            )
        if not declared and getattr(rubric, "planted_score", None) is not None:
            raise ValueError(
                f"QC_DATA_INVARIANT_VIOLATION: GoldenRuleSet {owner} plants a "
                f"planted_score without judge_response_only, so no judgement it "
                f"receives reads an answer to the attack"
            )
        return declared

    @staticmethod
    def _validate_priority(priority: int, conditions: list[str], owner: str) -> None:
        """Apply invariant G6 to a declared priority and its conditions.

        The matched conditions set a **ceiling**, not an assignment. Matching a
        P1 condition permits P1 or anything less severe; it does not permit P0.
        Demotion below the ceiling is legitimate and is how budget pressure is
        absorbed without the level losing its meaning.

        Args:
            priority (int): The declared priority, 0 to 4.
            conditions (list): The matched condition identifiers.
            owner (str): Rule set identifier, for the message.

        Returns:
            None

        Raises:
            ValueError: When priority is out of range, a condition is not
                registered, or priority is more severe than the ceiling allows.
        """
        if not 0 <= priority <= _LOWEST_PRIORITY:
            raise ValueError(
                f"QC_DATA_INVARIANT_VIOLATION: GoldenRuleSet {owner} priority {priority} "
                f"falls outside 0 to {_LOWEST_PRIORITY}"
            )
        levels: list[int] = []
        unregistered: list[str] = []
        for condition_id in conditions:
            level = priority_condition_level(condition_id)
            if level is None:
                unregistered.append(condition_id)
            else:
                levels.append(level)
        if unregistered:
            logger.error("QC_DATA_INVARIANT_VIOLATION %s unregistered conditions %s",
                         owner, sorted(unregistered))
            raise ValueError(
                f"QC_DATA_INVARIANT_VIOLATION: GoldenRuleSet {owner} names unregistered priority "
                f"conditions {sorted(unregistered)}"
            )
        ceiling = min(levels)
        if priority < ceiling:
            raise ValueError(
                f"QC_DATA_INVARIANT_VIOLATION: GoldenRuleSet {owner} declares priority "
                f"{priority} but its most severe matched condition permits no better than "
                f"{ceiling}"
            )
