# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The task records, which hold everything sent to the model under test.

Created: 2026-10-18
Last updated: 2026-10-21

This file contains :class:`TaskDataSet`, which holds the prompt, the optional
system instruction, the rubrics that judge it, its tags and its adversarial
declaration; and the records it carries, :class:`Constraint` for an
instruction that must be checkable, :class:`ContextDocument` for a retrieval
payload and :class:`ToolDefinition` for a tool offered to the model.

**Execution composes each provider request from a task.** Before that, the
ingest screen reads its authored text, and
referential integrity checks its constraints and tools against the rule sets
that judge it.

**The boundary rule**: :class:`TaskDataSet` is what is sent, and
:class:`~ingestion.schemas.rules.GoldenRuleSet` is how the response is judged.
Design: ``docs/design/tier1_ingestion.md`` sections 3.0 and 3.1 to 3.4.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from ingestion.schemas.fields import (
    _normalize_text,
    _reject_unknown_keys,
    _require_present_and_filled,
    _reject_unsafe_identifier,
    _optional_text,
)

logger = logging.getLogger(__name__)


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
