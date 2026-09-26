# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Frozen schema records and the validation applied at the ingestion boundary.

Specified by ``docs/design/tier1_ingestion.md`` sections 3 and 5. Every record
is a frozen dataclass with a ``from_dict`` classmethod, because an ingested
record is evidence rather than working state.

**The boundary rule** the field placement follows: :class:`TaskDataSet` is what
is sent to the model, :class:`GoldenRuleSet` is how the response is judged. The
same tool legitimately appears in both, as a definition on one side and an
expectation on the other.

Validation here reports **every** problem it finds rather than the first, on the
grounds that an author fixing hand-written data wants the whole list. Missing
and empty are different authoring errors carrying different codes: a missing
field was forgotten, an empty one had a placeholder left in it, and the fix
differs.
"""

import logging
import unicodedata
from dataclasses import dataclass, field, fields
from typing import Any, Final, Optional

from cmn.registries import (
    aggregation_scale,
    is_windows_reserved_name,
    priority_condition_level,
)

logger = logging.getLogger(__name__)

_ANCHOR_REQUIRED_LEVELS: Final[frozenset[int]] = frozenset({1, 3, 5})
_ANCHOR_PERMITTED_LEVELS: Final[frozenset[int]] = frozenset({1, 2, 3, 4, 5})
_LOWEST_PRIORITY: Final[int] = 4


def _normalize_text(value: Any) -> str:
    """Cast a value to text and strip surrounding whitespace.

    Stripping happens before any emptiness check, so that a whitespace-only
    value is caught rather than passing as three characters. Line endings are
    normalized to LF so that a value read on Windows and the same value read on
    Linux produce identical records, and therefore identical request hashes.

    Args:
        value (Any): The incoming value, of unknown type by assumption.

    Returns:
        str: The cast, newline-normalized, stripped text.
    """
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def _reject_unknown_keys(payload: dict[str, Any], record_type: type, owner: str) -> None:
    """Raise when a payload carries keys the record does not declare.

    A typo in a required field is caught by the required-field check. A typo in
    an **optional** field would otherwise take a default silently, and the case
    would be scored against criteria nobody wrote. That is the reason this check
    exists at all.

    Args:
        payload (dict): The incoming mapping.
        record_type (type): The dataclass whose fields are permitted.
        owner (str): Identifier used in the message, for locating the record.

    Returns:
        None

    Raises:
        KeyError: Naming every unknown key, sorted, with ``QC_DATA_UNKNOWN_FIELD``.
    """
    declared = {entry.name for entry in fields(record_type)}
    unknown = sorted(set(payload) - declared)
    if unknown:
        logger.error("QC_DATA_UNKNOWN_FIELD %s unknown keys %s", owner, unknown)
        raise KeyError(
            f"QC_DATA_UNKNOWN_FIELD: {record_type.__name__} {owner} "
            f"carries unknown keys {unknown}"
        )


def _require_present_and_filled(
    payload: dict[str, Any], required: tuple[str, ...], record_name: str, owner: str
) -> None:
    """Raise when required fields are absent or present but empty.

    Both problems are collected across the whole payload before raising, because
    an author correcting hand-written data wants every error at once rather than
    one per run.

    Args:
        payload (dict): The incoming mapping.
        required (tuple): Field names that must be present and non-empty.
        record_name (str): The record type name, for the message.
        owner (str): Identifier used in the message, for locating the record.

    Returns:
        None

    Raises:
        KeyError: When any required field is absent, naming all of them.
        ValueError: When any required field is present but empty, naming all of
            them. Raised only once no field is missing, so that the two codes
            never contend for one message.
    """
    missing = sorted(name for name in required if name not in payload)
    if missing:
        logger.error("QC_DATA_REQUIRED_FIELD_MISSING %s absent %s", owner, missing)
        raise KeyError(
            f"QC_DATA_REQUIRED_FIELD_MISSING: {record_name} {owner} "
            f"is missing required fields {missing}"
        )

    empty = sorted(name for name in required if _is_empty(payload[name]))
    if empty:
        logger.error("QC_DATA_REQUIRED_FIELD_EMPTY %s empty %s", owner, empty)
        raise ValueError(
            f"QC_DATA_REQUIRED_FIELD_EMPTY: {record_name} {owner} "
            f"carries empty required fields {empty}"
        )


def _is_empty(value: Any) -> bool:
    """Report whether a value counts as empty for a mandatory field.

    Presence alone is insufficient: ``user_prompt: ""`` supplies the key and
    satisfies a presence check while carrying nothing. Whitespace-only text is
    empty for the same reason, which is why text is stripped before the test.

    Args:
        value (Any): The supplied value.

    Returns:
        bool: True when the value carries nothing usable. ``False`` and ``0``
        are **not** empty; they are legitimate values that happen to be falsy,
        and treating them as empty would reject valid data.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, frozenset, dict)):
        return not value
    return False


def _reject_unsafe_identifier(identifier: str, owner: str) -> str:
    """Return an identifier after refusing forms that break on a platform.

    Two rules, both from A18, and both guarding a failure that occurs on exactly
    one supported platform:

    * A Windows reserved device name cannot become a directory at all, so an
      identifier that reaches a fixture path must not take one.
    * Identifiers are compared case-sensitively by this harness, and a
      filesystem may not agree. The canonical form returned here is what callers
      compare, so that a collision is detected rather than discovered.

    Args:
        identifier (str): The identifier as authored.
        owner (str): Identifier used in the message, for locating the record.

    Returns:
        str: The identifier, unchanged, once it is known to be safe.

    Raises:
        ValueError: When the identifier collides with a reserved device name.
    """
    if is_windows_reserved_name(identifier):
        logger.error("QC_DATA_IDENTIFIER_UNSAFE %s reserved device name %s", owner, identifier)
        raise ValueError(
            f"QC_DATA_IDENTIFIER_UNSAFE: {owner} identifier {identifier!r} collides with a "
            f"Windows reserved device name and cannot become a path segment"
        )
    return identifier


def canonical_identifier(identifier: str) -> str:
    """Return the form used to detect identifiers that collide on a filesystem.

    Case folding rather than lowercasing, because ``str.casefold`` handles
    scripts where the two differ. Unicode is normalized first so that two
    spellings of one character do not present as distinct identifiers.

    Args:
        identifier (str): The identifier as authored.

    Returns:
        str: The canonical form. Two identifiers sharing one canonical form
        coexist on Linux and collide on Windows, which is why they are rejected
        at ingest rather than left to a later platform-specific surprise.
    """
    return unicodedata.normalize("NFKC", identifier).casefold()


@dataclass(frozen=True)
class Constraint:
    """A rule sent to the model that must be checkable.

    Attributes:
        constraint_id (str): Referenced by checks; the basis of integrity check R2.
        text (str): The instruction exactly as sent.
        kind (str): Open vocabulary. Registered core kinds are in the design's
            section 8; an unregistered kind warns rather than fails.
    """

    constraint_id: str
    text: str
    kind: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Constraint":
        """Build a constraint from a validated mapping.

        Args:
            payload (dict): Mapping carrying ``constraint_id``, ``text`` and ``kind``.

        Returns:
            Constraint: The frozen record.

        Raises:
            KeyError: When a required field is absent or an unknown key is present.
            ValueError: When a required field is present but empty.
        """
        owner = str(payload.get("constraint_id", "<unidentified>"))
        _reject_unknown_keys(payload, cls, owner)
        _require_present_and_filled(payload, ("constraint_id", "text", "kind"), cls.__name__, owner)
        return cls(
            constraint_id=_normalize_text(payload["constraint_id"]),
            text=_normalize_text(payload["text"]),
            kind=_normalize_text(payload["kind"]),
        )


@dataclass(frozen=True)
class ContextDocument:
    """A retrieval payload supplied alongside the prompt.

    Attributes:
        document_id (str): Identifies the document within the task.
        content (str): The document body as the model receives it.
        title (Optional[str]): Display title, absent by default.
    """

    document_id: str
    content: str
    title: Optional[str] = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ContextDocument":
        """Build a context document from a validated mapping.

        Args:
            payload (dict): Mapping carrying ``document_id`` and ``content``.

        Returns:
            ContextDocument: The frozen record.

        Raises:
            KeyError: When a required field is absent or an unknown key is present.
            ValueError: When a required field is present but empty.
        """
        owner = str(payload.get("document_id", "<unidentified>"))
        _reject_unknown_keys(payload, cls, owner)
        _require_present_and_filled(payload, ("document_id", "content"), cls.__name__, owner)
        supplied_title = payload.get("title")
        return cls(
            document_id=_normalize_text(payload["document_id"]),
            content=_normalize_text(payload["content"]),
            title=None if supplied_title is None else _normalize_text(supplied_title),
        )


@dataclass(frozen=True)
class ToolDefinition:
    """A tool offered to the model, in canonical form.

    Gemini, OpenAI and Claude express tool definitions differently. Translation
    is a Tier 2 adapter responsibility; this record carries the canonical shape
    so that Tier 1 knows nothing about engines.

    Attributes:
        tool_name (str): The name the model invokes.
        description (str): What the tool does, as the model sees it.
        parameters_schema (dict): JSON Schema for the tool's arguments.
    """

    tool_name: str
    description: str
    parameters_schema: dict[str, Any]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ToolDefinition":
        """Build a tool definition from a validated mapping.

        Args:
            payload (dict): Mapping carrying ``tool_name``, ``description`` and
                ``parameters_schema``.

        Returns:
            ToolDefinition: The frozen record.

        Raises:
            KeyError: When a required field is absent or an unknown key is present.
            ValueError: When a required field is present but empty, or the schema
                is not a mapping.
        """
        owner = str(payload.get("tool_name", "<unidentified>"))
        _reject_unknown_keys(payload, cls, owner)
        _require_present_and_filled(
            payload, ("tool_name", "description", "parameters_schema"), cls.__name__, owner
        )
        schema = payload["parameters_schema"]
        if not isinstance(schema, dict):
            raise ValueError(
                f"QC_DATA_MALFORMED_SOURCE: ToolDefinition {owner} parameters_schema must be a "
                f"mapping, received {type(schema).__name__}"
            )
        return cls(
            tool_name=_normalize_text(payload["tool_name"]),
            description=_normalize_text(payload["description"]),
            parameters_schema=dict(schema),
        )


@dataclass(frozen=True)
class Anchor:
    """What one point on a rubric scale means.

    Attributes:
        description (str): What a response scoring at this level looks like.
        exemplar (Optional[str]): A response that should score here, used by
            calibration to detect judge drift.
    """

    description: str
    exemplar: Optional[str] = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Anchor":
        """Build an anchor from a validated mapping.

        Args:
            payload (dict): Mapping carrying ``description``.

        Returns:
            Anchor: The frozen record.

        Raises:
            KeyError: When a required field is absent or an unknown key is present.
            ValueError: When a required field is present but empty.
        """
        _reject_unknown_keys(payload, cls, "<anchor>")
        _require_present_and_filled(payload, ("description",), cls.__name__, "<anchor>")
        supplied_exemplar = payload.get("exemplar")
        return cls(
            description=_normalize_text(payload["description"]),
            exemplar=None if supplied_exemplar is None else _normalize_text(supplied_exemplar),
        )


@dataclass(frozen=True)
class RubricCriterion:
    """One judged dimension, with the anchors that define its scale.

    Attributes:
        criterion_id (str): Identifies the criterion within the rubric.
        name (str): Short label.
        description (str): What the criterion measures.
        anchors (dict): Level to :class:`Anchor`. Invariant G3 applies.
        weight (float): Relative contribution under weighted aggregation.
        constraint_ref (Optional[str]): The constraint this criterion judges,
            checked by referential integrity rule R2.
    """

    criterion_id: str
    name: str
    description: str
    anchors: dict[int, Anchor]
    weight: float = 1.0
    constraint_ref: Optional[str] = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RubricCriterion":
        """Build a criterion from a validated mapping, enforcing invariant G3.

        G3 requires anchors at levels 1, 3 and 5; levels 2 and 4 are permitted.
        Requiring all five is authoring burden without proportional benefit, and
        a judge discriminates better against few sharply distinguished anchors
        than five similar ones.

        Args:
            payload (dict): Mapping carrying ``criterion_id``, ``name``,
                ``description`` and ``anchors``.

        Returns:
            RubricCriterion: The frozen record.

        Raises:
            KeyError: When a required field is absent or an unknown key is present.
            ValueError: When a required field is empty, an anchor level falls
                outside 1 to 5, a required level is absent, or the weight is not
                numeric.
        """
        owner = str(payload.get("criterion_id", "<unidentified>"))
        _reject_unknown_keys(payload, cls, owner)
        _require_present_and_filled(
            payload, ("criterion_id", "name", "description", "anchors"), cls.__name__, owner
        )
        anchors = cls._build_anchors(payload["anchors"], owner)
        return cls(
            criterion_id=_normalize_text(payload["criterion_id"]),
            name=_normalize_text(payload["name"]),
            description=_normalize_text(payload["description"]),
            anchors=anchors,
            weight=_coerce_float(payload.get("weight", 1.0), "weight", owner),
            constraint_ref=_optional_text(payload.get("constraint_ref")),
        )

    @staticmethod
    def _build_anchors(supplied: Any, owner: str) -> dict[int, Anchor]:
        """Validate and build the anchor mapping for one criterion.

        Args:
            supplied (Any): The authored anchors, expected as a mapping of level
                to anchor payload.
            owner (str): Criterion identifier, for the message.

        Returns:
            dict[int, Anchor]: Anchors keyed by integer level.

        Raises:
            ValueError: When the anchors are not a mapping, a level is not an
                integer in 1 to 5, or levels 1, 3 and 5 are not all present.
        """
        if not isinstance(supplied, dict):
            raise ValueError(
                f"QC_DATA_MALFORMED_SOURCE: RubricCriterion {owner} anchors must be a mapping, "
                f"received {type(supplied).__name__}"
            )
        anchors: dict[int, Anchor] = {}
        for raw_level, anchor_payload in supplied.items():
            level = _coerce_int(raw_level, "anchor level", owner)
            if level not in _ANCHOR_PERMITTED_LEVELS:
                raise ValueError(
                    f"QC_DATA_INVARIANT_VIOLATION: RubricCriterion {owner} anchor level {level} "
                    f"falls outside 1 to 5"
                )
            anchors[level] = Anchor.from_dict(dict(anchor_payload))

        absent = sorted(_ANCHOR_REQUIRED_LEVELS - set(anchors))
        if absent:
            raise ValueError(
                f"QC_DATA_REQUIRED_FIELD_MISSING: RubricCriterion {owner} is missing required "
                f"anchor levels {absent}; 1, 3 and 5 are mandatory"
            )
        return anchors


@dataclass(frozen=True)
class Rubric:
    """The judged half of a rule set.

    Attributes:
        criteria (list): The judged dimensions. Invariant G2 requires at least one.
        threshold (float): The score at or above which the rubric passes.
        aggregation (str): Registered strategy name.
        aggregation_params (dict): Parameters for that strategy.
    """

    criteria: list[RubricCriterion]
    threshold: float
    aggregation: str = "weighted_mean"
    aggregation_params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Rubric":
        """Build a rubric from a validated mapping, enforcing invariant G2.

        Args:
            payload (dict): Mapping carrying ``criteria`` and ``threshold``.

        Returns:
            Rubric: The frozen record.

        Raises:
            KeyError: When a required field is absent or an unknown key is present.
            ValueError: When criteria is empty, or the threshold is not numeric.
        """
        _reject_unknown_keys(payload, cls, "<rubric>")
        _require_present_and_filled(payload, ("criteria", "threshold"), cls.__name__, "<rubric>")
        aggregation = _normalize_text(payload.get("aggregation", "weighted_mean"))
        if aggregation_scale(aggregation) is None:
            raise ValueError(
                f"QC_DATA_INVARIANT_VIOLATION: Rubric names unregistered aggregation strategy "
                f"{aggregation!r}; a score with no declared scale cannot be compared"
            )
        criteria = [
            RubricCriterion.from_dict(dict(entry)) for entry in payload["criteria"]
        ]
        return cls(
            criteria=criteria,
            threshold=_coerce_float(payload["threshold"], "threshold", "<rubric>"),
            aggregation=aggregation,
            aggregation_params=dict(payload.get("aggregation_params", {})),
        )


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
class TaskDataSet:
    """What is sent to the model.

    Attributes:
        task_id (str): ``MQC_TASK_<slug>``.
        rubric_ids (list): Rule sets that judge this task. At least one.
        user_prompt (str): The prompt as sent.
        system_instruction (Optional[str]): System-level instruction, if any.
        constraints (list): Rules sent to the model. YAML-only.
        context_documents (list): Retrieval payloads. YAML-only.
        available_tools (list): Tools offered to the model. YAML-only.
        tags (frozenset): Grouping labels, carrying control-pair identifiers.
        contains_adversarial_content (bool): Opt out of the ingest injection
            screen, for a case whose payload must contain an injection.
    """

    task_id: str
    rubric_ids: list[str]
    user_prompt: str
    system_instruction: Optional[str] = None
    constraints: list[Constraint] = field(default_factory=list)
    context_documents: list[ContextDocument] = field(default_factory=list)
    available_tools: list[ToolDefinition] = field(default_factory=list)
    tags: frozenset[str] = frozenset()
    contains_adversarial_content: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TaskDataSet":
        """Build a task from a validated mapping.

        Args:
            payload (dict): Mapping carrying ``task_id``, ``rubric_ids`` and
                ``user_prompt``, plus any optional fields.

        Returns:
            TaskDataSet: The frozen record.

        Raises:
            KeyError: When a required field is absent or an unknown key is present.
            ValueError: When a required field is empty, or the identifier is
                unusable as a path segment on a supported platform.
        """
        owner = str(payload.get("task_id", "<unidentified>"))
        _reject_unknown_keys(payload, cls, owner)
        _require_present_and_filled(
            payload, ("task_id", "rubric_ids", "user_prompt"), cls.__name__, owner
        )
        task_id = _reject_unsafe_identifier(_normalize_text(payload["task_id"]), owner)
        return cls(
            task_id=task_id,
            rubric_ids=[_normalize_text(entry) for entry in payload["rubric_ids"]],
            user_prompt=_normalize_text(payload["user_prompt"]),
            system_instruction=_optional_text(payload.get("system_instruction")),
            constraints=[Constraint.from_dict(dict(entry))
                         for entry in payload.get("constraints", ())],
            context_documents=[ContextDocument.from_dict(dict(entry))
                               for entry in payload.get("context_documents", ())],
            available_tools=[ToolDefinition.from_dict(dict(entry))
                             for entry in payload.get("available_tools", ())],
            tags=frozenset(_normalize_text(entry) for entry in payload.get("tags", ())),
            contains_adversarial_content=bool(payload.get("contains_adversarial_content", False)),
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
    """

    rule_id: str
    priority: int
    priority_conditions: list[str]
    assertions: list[ProgrammaticAssertion] = field(default_factory=list)
    rubric: Optional[Rubric] = None
    tool_expectation: Optional[ToolExpectation] = None
    requirement_ids: list[str] = field(default_factory=list)

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
        )

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


@dataclass(frozen=True)
class EvaluationCase:
    """One (task by rubric) unit, derived rather than authored.

    Invariant G5: this stays a data type. No scoring, no dispatch, no engine
    knowledge. It has no ``from_dict`` because nobody authors one; a factory
    builds it from a task and a rule set after the join.

    Attributes:
        case_id (str): ``<task_id>::<rule_id>``, stable across runs.
        task (TaskDataSet): What was sent.
        golden_rules (GoldenRuleSet): How it is judged.
        priority (int): Carried from the rule set, for the verdict gate.
    """

    case_id: str
    task: TaskDataSet
    golden_rules: GoldenRuleSet
    priority: int


def _optional_text(value: Any) -> Optional[str]:
    """Normalize an optional text field, preserving absence.

    Args:
        value (Any): The supplied value, possibly ``None``.

    Returns:
        Optional[str]: ``None`` when absent, otherwise the normalized text. An
        explicitly supplied empty string stays an empty string rather than
        becoming ``None``: for an optional field the two are different authoring
        statements, and collapsing them would discard one.
    """
    return None if value is None else _normalize_text(value)


def _coerce_int(value: Any, field_name: str, owner: str) -> int:
    """Cast a value to an integer at the boundary, refusing what will not cast.

    Args:
        value (Any): The supplied value.
        field_name (str): Field name, for the message.
        owner (str): Record identifier, for the message.

    Returns:
        int: The cast value.

    Raises:
        ValueError: When the value is not an integer or an integral string.
    """
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"QC_DATA_MALFORMED_SOURCE: {owner} field {field_name} expects an integer, "
            f"received {value!r}"
        ) from error


def _coerce_float(value: Any, field_name: str, owner: str) -> float:
    """Cast a value to a float at the boundary, refusing what will not cast.

    Args:
        value (Any): The supplied value.
        field_name (str): Field name, for the message.
        owner (str): Record identifier, for the message.

    Returns:
        float: The cast value.

    Raises:
        ValueError: When the value is not numeric.
    """
    try:
        return float(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"QC_DATA_MALFORMED_SOURCE: {owner} field {field_name} expects a number, "
            f"received {value!r}"
        ) from error
