# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The canonical shapes a provider response is normalized into.

Specified by ``docs/design/tier2_execution.md`` section 4.

**A vendor SDK object reaching Tier 3 is a design defect.** It would make the
judge depend on which provider produced the output it is judging, so every
provider-shaped value stops at its adapter and only these records cross the
boundary.

**`raw_reference` is a pointer, never the payload.** Carrying the vendor object
forward would defeat that rule; discarding it entirely would make a
normalization defect undiagnosable. A pointer keeps the original findable
without letting it travel.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Final, Optional

from cmn.tokens import TokenUsage

logger = logging.getLogger(__name__)

# Finish reasons, normalized across providers. Vendors spell the same outcome
# differently, and leaving the difference visible would make a downstream
# comparison of truncation rates a comparison of vocabularies.
_FINISH_REASONS: Final[frozenset[str]] = frozenset(
    {"stop", "length", "tool_calls", "content_filter", "error", "unknown"}
)

_EXECUTION_MODES: Final[frozenset[str]] = frozenset({"live", "replay"})


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation the model intended, captured and never executed.

    Attributes:
        tool_name (str): The canonical tool name.
        arguments (dict): **Parsed**, never a JSON string. Providers differ
            here, and leaving the difference visible would mean Tier 3 handling
            two shapes for one fact.
        call_id (Optional[str]): Provider-assigned identifier, absent where a
            provider supplies none.
        sequence (int): Order within the response, zero based.
    """

    tool_name: str
    arguments: dict[str, Any]
    sequence: int
    call_id: Optional[str] = None

    @classmethod
    def from_provider(
        cls, tool_name: str, arguments: Any, sequence: int, call_id: Optional[str] = None
    ) -> "ToolCall":
        """Build a tool call, parsing arguments if the provider sent a string.

        Args:
            tool_name (str): The tool the model named.
            arguments (Any): A mapping, or a JSON string to be parsed.
            sequence (int): Order within the response.
            call_id (Optional[str]): Provider identifier, where one exists.

        Returns:
            ToolCall: The canonical record.

        Raises:
            ValueError: When arguments are a string that will not parse, or
                parse to something other than a mapping. The code is
                ``QC_LLM_SCHEMA_VIOLATION`` and **not** a harness code: the
                provider transported the response correctly and the model
                emitted malformed JSON, which is a finding about the model.
        """
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError as error:
                logger.error("QC_LLM_SCHEMA_VIOLATION tool %s arguments do not parse", tool_name)
                raise ValueError(
                    f"QC_LLM_SCHEMA_VIOLATION: tool {tool_name} arguments are not valid JSON"
                ) from error
        else:
            parsed = arguments
        if not isinstance(parsed, dict):
            raise ValueError(
                f"QC_LLM_SCHEMA_VIOLATION: tool {tool_name} arguments parsed to "
                f"{type(parsed).__name__} rather than a mapping"
            )
        return cls(
            tool_name=str(tool_name).strip(),
            arguments=dict(parsed),
            sequence=int(sequence),
            call_id=None if call_id is None else str(call_id).strip(),
        )


@dataclass(frozen=True)
class NormalizedResponse:
    """One provider response, in the only shape Tier 3 ever sees.

    Attributes:
        case_id (str): Which case produced it.
        engine (str): Which adapter produced it.
        mode (str): ``live`` or ``replay``. A replayed result must never be
            mistaken for an observation (A6).
        requested_model (str): What was asked for.
        resolved_model (str): What the provider returned (A8). Aliases float,
            and recording only the request hides the event that makes a score
            change uninterpretable.
        text (str): The primary output.
        tool_calls (list): Captured intent, empty when none.
        output_tokens (int): Recorded alongside duration, because latency is
            dominated by verbosity (A7.2).
        input_tokens (int): Everything sent. **The larger half for this
            corpus**, and read from the same usage object that already gave the
            output count, where it sat unread until 2026-09-27.
        thinking_tokens (int): Reasoning the provider billed and did not return
            in the text. Counted apart from ``output_tokens`` because providers
            report it apart, and billed at the output rate because they bill it
            that way.
        cached_input_tokens (int): The part of the input served from the
            provider's cache, at a tenth of the input rate. **Included in
            ``input_tokens``**, never added to it, so the two cannot
            double-count.
        duration_ms (int): Measured here, normalized downstream.
        finish_reason (str): Normalized across providers.
        block_reason (str): The provider's own word for refusing, empty where it
            did not. **Verbatim rather than mapped**, because it is evidence: a
            refusal counts as resistance for a security case, and a pass awarded
            on a provider's say-so should name what the provider said.
        block_stage (str): Where the refusal happened, as far as the provider
            reveals it. ``prompt`` where it refused before generating anything,
            ``response`` where generation began and was stopped, empty where
            nothing was blocked. **Recorded even though today both count the
            same**, so a later change of requirements is a re-reading of the
            corpus rather than a re-run of it.
        raw_reference (str): Pointer to the stored original.
    """

    case_id: str
    engine: str
    mode: str
    requested_model: str
    resolved_model: str
    text: str
    output_tokens: int
    duration_ms: int
    finish_reason: str
    raw_reference: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    # ADDITIVE, AND THAT IS THE POINT. Nineteen fixtures were recorded before
    # these existed, and a required field would have made every one of them
    # unreplayable. They read as zero, which is honest: nobody captured the
    # count at the time.
    input_tokens: int = 0
    thinking_tokens: int = 0
    cached_input_tokens: int = 0
    block_reason: str = ""
    block_stage: str = ""

    @property
    def usage(self) -> TokenUsage:
        """Return the four counts as the record the cost function prices.

        Returns:
            TokenUsage: The usage, structured. **Flat on the wire, structured
            in use**: the fixture format stays additive while the caller is
            handed something it cannot get the field order wrong in.
        """
        return TokenUsage(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            thinking_tokens=self.thinking_tokens,
            cached_input_tokens=self.cached_input_tokens,
        )

    def __post_init__(self) -> None:
        """Refuse a record that could not be interpreted downstream.

        Validation happens on construction rather than at the boundary, because
        every adapter builds one of these and a check in one adapter would not
        constrain the others.

        Returns:
            None

        Raises:
            ValueError: When mode or finish reason is unregistered.
        """
        if self.mode not in _EXECUTION_MODES:
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: {self.case_id} carries mode {self.mode!r}, "
                f"which is neither live nor replay"
            )
        if self.finish_reason not in _FINISH_REASONS:
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: {self.case_id} carries finish reason "
                f"{self.finish_reason!r}, which is not one of {sorted(_FINISH_REASONS)}"
            )

    def as_mapping(self) -> dict[str, Any]:
        """Return the record as a plain mapping, for the fixture store.

        A fixture stores the normalized record rather than the provider payload
        (design section 7.3), so it stays provider-agnostic and survives an SDK
        shape change.

        Returns:
            dict: Built-in types only, so it serializes without a custom
            encoder and without a vendor object reaching the file.
        """
        return {
            "case_id": self.case_id,
            "engine": self.engine,
            "mode": self.mode,
            "requested_model": self.requested_model,
            "resolved_model": self.resolved_model,
            "text": self.text,
            "output_tokens": self.output_tokens,
            "input_tokens": self.input_tokens,
            "thinking_tokens": self.thinking_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "block_reason": self.block_reason,
            "block_stage": self.block_stage,
            "duration_ms": self.duration_ms,
            "finish_reason": self.finish_reason,
            "raw_reference": self.raw_reference,
            "tool_calls": [
                {
                    "tool_name": call.tool_name,
                    "arguments": call.arguments,
                    "sequence": call.sequence,
                    "call_id": call.call_id,
                }
                for call in self.tool_calls
            ],
        }

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "NormalizedResponse":
        """Rebuild a record from a stored mapping.

        **Deserialization goes back through the constructor**, so a fixture
        hand-edited to carry an unregistered mode or finish reason is rejected
        on read rather than replayed as though it were a real observation.

        Args:
            payload (dict): What :meth:`as_mapping` produced.

        Returns:
            NormalizedResponse: The rebuilt record.

        Raises:
            ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the stored
                mapping is missing a field the record requires.
        """
        try:
            return cls(
                case_id=str(payload["case_id"]),
                engine=str(payload["engine"]),
                mode=str(payload["mode"]),
                requested_model=str(payload["requested_model"]),
                resolved_model=str(payload["resolved_model"]),
                text=str(payload["text"]),
                output_tokens=int(payload["output_tokens"]),
                # READ WITH A DEFAULT, never subscripted. A fixture recorded
                # before these fields existed has no key to read.
                input_tokens=int(payload.get("input_tokens", 0) or 0),
                thinking_tokens=int(payload.get("thinking_tokens", 0) or 0),
                cached_input_tokens=int(payload.get("cached_input_tokens", 0) or 0),
                block_reason=str(payload.get("block_reason", "") or ""),
                block_stage=str(payload.get("block_stage", "") or ""),
                duration_ms=int(payload["duration_ms"]),
                finish_reason=str(payload["finish_reason"]),
                raw_reference=str(payload["raw_reference"]),
                tool_calls=[
                    ToolCall.from_provider(
                        tool_name=entry["tool_name"],
                        arguments=entry["arguments"],
                        sequence=entry["sequence"],
                        call_id=entry.get("call_id"),
                    )
                    for entry in payload.get("tool_calls", [])
                ],
            )
        except (KeyError, TypeError) as error:
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: a stored response is missing a required "
                f"field, {error}"
            ) from error

    def replace(self, **changes: Any) -> "NormalizedResponse":
        """Return a copy with named fields replaced.

        The record is frozen, and the dispatcher legitimately needs to stamp a
        measured duration or re-declare a replayed mode onto one an adapter
        built.

        Args:
            **changes (Any): Fields to replace.

        Returns:
            NormalizedResponse: The copy, revalidated by the constructor so a
            replacement cannot introduce an unregistered value.
        """
        fields = self.as_mapping()
        fields["tool_calls"] = self.tool_calls
        fields.update(changes)
        return NormalizedResponse(**fields)

    @property
    def blocked_by_provider(self) -> bool:
        """Report whether the provider refused, at either stage.

        **An affirmative refusal, not an absence.** The provider said why it
        declined, which is a different fact from a model that answered with
        nothing: section 4.2.1 refuses to read the second as resistance, and this
        is the first.

        Returns:
            bool: True where the provider named a reason.
        """
        return bool(self.block_reason)

    @property
    def produced_output(self) -> bool:
        """Report whether this response carries anything to evaluate.

        **Error is error: output could not be produced, so there is nothing to
        judge** (tier 3 design section 4.2.1). A turn the provider reported as
        failed, and a turn that completed while returning neither text nor a
        tool call, are the same condition from Tier 3's point of view.

        Returns:
            bool: False when there is nothing to evaluate. **Truncated and
            filtered responses return True**: truncation is partial output and
            a refusal is an outcome, and treating either as an absence would
            discard a real measurement. A tool call with no text is output too,
            since a tool case that emitted only a call behaved as asked.
        """
        if self.finish_reason == "error":
            return False
        return bool(self.text.strip()) or bool(self.tool_calls)

    @property
    def model_alias_floated(self) -> bool:
        """Report whether the provider served a different model than requested.

        Returns:
            bool: True when resolved and requested differ. **This is not an
            error.** It is the signal A8 exists to capture, and a score change
            across a run where it is true has an explanation a score change
            without it does not.
        """
        return self.requested_model != self.resolved_model


def registered_finish_reasons() -> frozenset[str]:
    """Return the normalized finish reasons every adapter maps into.

    Returns:
        frozenset[str]: The registered vocabulary.
    """
    return _FINISH_REASONS


def registered_execution_modes() -> frozenset[str]:
    """Return the execution modes a response may declare.

    Returns:
        frozenset[str]: ``live`` and ``replay``.
    """
    return _EXECUTION_MODES
