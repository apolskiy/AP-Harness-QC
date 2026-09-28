# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The Anthropic adapter.

Implements the interface in :mod:`execution.adapters.base` against the
Anthropic Messages API. Replay-only under A3 until a key is provisioned, which
changes nothing here: every operation except :meth:`ClaudeAdapter.dispatch` runs
against a response object and needs no credential.

**One request per case. No loop, no tool execution.** A tool call is captured as
intent and never acted on, because tool usage is behaviour under test rather
than a prohibition.

**This provider returns tool arguments already parsed.** The SDK hands back a
mapping on the content block, where other providers hand back a JSON string.
That difference is exactly what :meth:`extract_tool_calls` exists to absorb.
"""

import logging
from typing import Any, Final

import anthropic

from cmn.tokens import TokenUsage
from execution.adapters.base import Capabilities, ConfiguredAdapter, ProviderFacts
from execution.normalize import NormalizedResponse, ToolCall

logger = logging.getLogger(__name__)


_ERROR_CLASSES: Final[tuple[tuple[type, str], ...]] = (
    (anthropic.RateLimitError, "QC_HARNESS_RATE_LIMIT"),
    (anthropic.APITimeoutError, "QC_HARNESS_CANDIDATE_TIMEOUT"),
    (anthropic.AuthenticationError, "QC_HARNESS_AUTH_ERROR"),
    (anthropic.PermissionDeniedError, "QC_HARNESS_AUTH_ERROR"),
    (anthropic.BadRequestError, "QC_HARNESS_REQUEST_REJECTED"),
    (anthropic.NotFoundError, "QC_HARNESS_VERSION_UNAVAILABLE"),
    # THE PROVIDER REPORTING ITSELF BUSY, retryable and deliberately not a
    # rate limit: one says we asked too often and the other says the provider
    # is busy (design section 8.5.1).
    # A FALLBACK ONLY. The shared status table decides 500 from
    # 502 and 503 from 504; this catches a server error that
    # somehow carries no status.
    (anthropic.InternalServerError, "QC_HARNESS_PROVIDER_UNAVAILABLE"),
    # WE NEVER REACHED IT, so it reported nothing. Mis-filed as the
    # provider being busy when the transient family was added, which
    # is the same error 8.5.4 corrected for 502.
    (anthropic.APIConnectionError, "QC_HARNESS_ENGINE_UNREACHABLE"),
)

# The forced tool a judgement replies through, and the ceiling for that
# reply. A rubric object is small; this is headroom, not a target.
_JUDGE_TOOL: Final[str] = "mqc_judgement"
_JUDGE_MAX_TOKENS: Final[int] = 4096

_ENGINE_NAME: Final[str] = "claude"

# Supplied at execution time per B8, never hardcoded into a case. This is the
# fallback when configuration names no model, so an unconfigured run is still
# reproducible rather than failing at the boundary.
_DEFAULT_MODEL: Final[str] = "claude-opus-5-5"

# STATED, NEVER INHERITED. This model defaults the effort level to medium where
# its predecessor defaulted to high, so an adapter sending no output_config
# would have changed how much the model thinks without any line of this
# repository changing, and the observations would have been recorded as though
# nothing had moved.
#
# Naming it puts the value in the composed request and therefore in the request
# hash, so moving it reports QC_HARNESS_FIXTURE_STALE rather than replaying a
# response recorded under a setting that no longer applies. A value left to an
# API default cannot be detected that way, because nothing local changes.
#
# Same rule as py-version in .pylintrc and the explicit --engine in CI.
# tier2_execution.md section 5A.1 carries the reasoning.
_DEFAULT_EFFORT: Final[str] = "medium"

# Non-streaming, so the ceiling is kept below the SDK's HTTP timeout. A case
# needing more than this is asking for an essay rather than an evaluation.
_DEFAULT_MAX_TOKENS: Final[int] = 16000

# This provider's stop reasons, mapped into the canonical vocabulary. Anthropic
# distinguishes a policy refusal from an ordinary stop, which most providers do
# not; it maps to the canonical error rather than being flattened into stop,
# because a refusal that read as a normal completion would score as one.
_FINISH_REASONS: Final[dict[str, str]] = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
    "refusal": "content_filter",
    "pause_turn": "unknown",
}


class ClaudeAdapter(ConfiguredAdapter):
    """Anthropic, behind the one interface Tier 2 knows about.

    Construction, the two identity properties and the canonical-record
    assembly come from the shared base, per design section 3.2.1. What
    remains here is what actually differs between providers.

    Attributes:
        ENGINE_NAME (str): The engine this adapter serves.
        DEFAULT_MODEL (str): Requested when configuration names none.
    """

    ENGINE_NAME = _ENGINE_NAME
    DEFAULT_MODEL = _DEFAULT_MODEL

    # WHAT THIS SDK READS FOR ITSELF. The Anthropic client resolves its own
    # credential rather than taking one through a constructor argument, so
    # the name is declared here for the orphan check to read
    # (design section 10.34.6).
    API_KEY_ENV = "ANTHROPIC_API_KEY"
    ERROR_CLASSES = _ERROR_CLASSES

    def compose_request(self, case: Any) -> dict[str, Any]:
        """Build an Anthropic request from an evaluation case.

        The case is typed loosely so Tier 2 does not import Tier 1's record and
        invert the dependency.

        Args:
            case (Any): An ``EvaluationCase``.

        Returns:
            dict: The request, as a plain mapping so it can be hashed for
            replay without a provider object reaching the hash.
        """
        task = case.task
        content: list[dict[str, Any]] = []
        for document in task.context_documents:
            content.append(
                {"type": "text", "text": f"<document id={document.document_id}>\n"
                                         f"{document.content}\n</document>"}
            )
        content.append({"type": "text", "text": task.user_prompt})

        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": _DEFAULT_MAX_TOKENS,
            "output_config": {"effort": _DEFAULT_EFFORT},
            "messages": [{"role": "user", "content": content}],
        }
        if task.system_instruction is not None:
            request["system"] = task.system_instruction
        if task.available_tools:
            request["tools"] = [
                {
                    "name": tool.tool_name,
                    "description": tool.description,
                    "input_schema": tool.parameters_schema,
                }
                for tool in task.available_tools
            ]
        return request

    def dispatch(self, request: dict[str, Any]) -> Any:
        """Issue exactly one request and return the provider's response.

        Args:
            request (dict): The composed request.

        Returns:
            Any: The provider response object, which stops at this adapter.
        """
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client.messages.create(**request)

    def normalize_response(self, response: Any, case_id: str) -> NormalizedResponse:
        """Convert an Anthropic response into the canonical shape.

        Args:
            response (Any): The provider response.
            case_id (str): The case this answers.

        Returns:
            NormalizedResponse: The only shape that crosses into Tier 3.
        """
        return self.build_response(
            case_id,
            ProviderFacts(
                text="".join(
                    block.text for block in response.content
                    if getattr(block, "type", None) == "text"
                ),
                tool_calls=self.extract_tool_calls(response),
                usage=self.read_usage(response),
                finish_reason=_FINISH_REASONS.get(response.stop_reason, "unknown"),
                raw_reference=self.raw_reference_of(response),
                resolved_model=self.resolve_model_version(response),
            ),
        )

    def usage_from(self, usage: Any) -> TokenUsage:
        """Return Anthropic's counts.

        **No separate thinking count, and that is not an omission.** Anthropic
        includes thinking inside `output_tokens` rather than reporting it apart,
        so populating a thinking field here would double it. Section 5A.2 records
        that thinking cannot be disabled on this model, so the output count is
        always carrying some.

        Args:
            usage (Any): A Messages usage object.

        Returns:
            TokenUsage: The counts.
        """
        return TokenUsage(
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            cached_input_tokens=int(
                getattr(usage, "cache_read_input_tokens", 0) or 0
            ),
        )

    def extract_tool_calls(self, response: Any) -> list[ToolCall]:
        """Capture the tool calls the model intended.

        **This provider supplies arguments already parsed.** They still pass
        through the canonical constructor, so a provider that changes its mind
        about the shape is absorbed here rather than surfacing in Tier 3.

        Args:
            response (Any): The provider response.

        Returns:
            list[ToolCall]: Intent only, in the order the model produced it.
        """
        return [
            ToolCall.from_provider(
                tool_name=block.name,
                arguments=block.input,
                sequence=sequence,
                call_id=getattr(block, "id", None),
            )
            for sequence, block in enumerate(
                entry for entry in response.content
                if getattr(entry, "type", None) == "tool_use"
            )
        ]

    def resolve_model_version(self, response: Any) -> str:
        """Return the model the provider reported serving.

        Args:
            response (Any): The provider response.

        Returns:
            str: The resolved identifier.

        Raises:
            ValueError: With ``QC_HARNESS_VERSION_UNAVAILABLE`` when the
                response carries no usable model, which fails preflight.
        """
        resolved = getattr(response, "model", None)
        if resolved is None or not str(resolved).strip():
            logger.error("QC_HARNESS_VERSION_UNAVAILABLE claude returned no model identifier")
            raise ValueError(
                "QC_HARNESS_VERSION_UNAVAILABLE: claude returned no model identifier"
            )
        return str(resolved).strip()

    def compose_judgement(self, prompt: str, reply_schema: dict[str, Any]) -> Any:
        """Build a Messages request constrained to the reply schema.

        **A forced tool call is how this protocol constrains a reply.** There
        is no response-format control here, so the schema is offered as the
        single tool and ``tool_choice`` requires it.

        **The call is never executed**, which is the same rule Tier 2 applies
        to a candidate: it is read as the reply rather than acted on.

        Args:
            prompt (str): The rendered judge request, composed by Tier 3, which
                owns the isolation split. An adapter that rebuilt it could put
                candidate output into the instruction.
            reply_schema (dict): The structure the judge must reply in.

        Returns:
            Any: The request, as a plain mapping.
        """
        return {
            "model": self._model,
            "max_tokens": _JUDGE_MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
            "tools": [
                {
                    "name": _JUDGE_TOOL,
                    "description": "Return the judgement in the required shape.",
                    "input_schema": reply_schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": _JUDGE_TOOL},
        }

    def parse_judgement(self, response: Any) -> dict[str, Any]:
        """Read the forced tool call's input as the reply.

        **Already a mapping**, the provider having parsed it against the
        schema, so unlike the other protocols this is an attribute read rather
        than a JSON parse.

        Args:
            response (Any): The provider-shaped reply.

        Returns:
            dict[str, Any]: The reply as a mapping.

        Raises:
            ValueError: With ``QC_HARNESS_PARSER_ERROR`` when no forced call
                came back, which means the constraint was not honoured.
        """
        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                return dict(block.input)
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: {self.ENGINE_NAME} returned no forced "
            f"tool call, so the reply was not schema-constrained"
        )

    def declare_capabilities(self) -> Capabilities:
        """Return what this provider supports.

        Returns:
            Capabilities: Tool calling and structured output are supported, and
            a system instruction is a first-class request field rather than
            something folded into the prompt.
        """
        return Capabilities(
            tool_calling=True, structured_output=True, system_instruction=True
        )
