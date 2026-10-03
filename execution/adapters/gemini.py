# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The Gemini adapter.

Implements the interface in :mod:`execution.adapters.base` against the Google
Gen AI API. Replay-only under A3 until a key is provisioned, which changes
nothing here: every operation except :meth:`GeminiAdapter.dispatch` runs against
a response object and needs no credential.

**One request per case. No loop, no tool execution.** The SDK offers automatic
function calling, which would execute the model's tool calls and return the
result of a multi-turn exchange. It is switched off explicitly, because tool
usage is behaviour under test and executing a call would both destroy the
measurement and act on the model's intent.

**This provider reports no tool-call finish reason.** It ends a
function-calling turn with the ordinary stop reason and carries the calls in the
content parts, where the other two providers signal it in the finish reason
itself. Normalization reconciles that here, or a cross-engine comparison of
tool-use rates would be comparing vendor conventions.
"""

import logging
from typing import Any, Final

import httpx
from google import genai

from cmn.tokens import TokenUsage
from execution.adapters.base import (
    Capabilities,
    ConfiguredAdapter,
    ProviderFacts,
    require_json_object,
)
from execution.normalize import NormalizedResponse, ToolCall

logger = logging.getLogger(__name__)

_ENGINE_NAME: Final[str] = "gemini"

# Supplied at execution time per B8, never hardcoded into a case. This is the
# fallback when configuration names no model, so an unconfigured run is still
# reproducible rather than failing at the boundary.
_DEFAULT_MODEL: Final[str] = "gemini-3.8-flash"

# This provider's finish reasons, mapped into the canonical vocabulary. Three
# distinct refusal-shaped outcomes collapse into one canonical value because the
# canonical question is whether the content was withheld, and the provider's
# reason for withholding it belongs in the record rather than in the taxonomy.
_FINISH_REASONS: Final[dict[str, str]] = {
    "STOP": "stop",
    "MAX_TOKENS": "length",
    "SAFETY": "content_filter",
    "RECITATION": "content_filter",
    "BLOCKLIST": "content_filter",
    "PROHIBITED_CONTENT": "content_filter",
    "MALFORMED_FUNCTION_CALL": "error",
    "OTHER": "unknown",
}

class GeminiAdapter(ConfiguredAdapter):
    """Gemini, behind the one interface Tier 2 knows about.

    Construction, the two identity properties and the canonical-record
    assembly come from the shared base, per design section 3.2.1. What
    remains here is what actually differs between providers.

    Attributes:
        ENGINE_NAME (str): The engine this adapter serves.
        DEFAULT_MODEL (str): Requested when configuration names none.
    """

    ENGINE_NAME = _ENGINE_NAME
    DEFAULT_MODEL = _DEFAULT_MODEL

    # WHAT THIS SDK CARRIES IN A CLASS RATHER THAN A STATUS. Every
    # status meaning comes from the shared table instead.
    # WHAT THIS SDK READS FOR ITSELF. The Gen AI client resolves its
    # own credential rather than taking one through client_options, so
    # both names it accepts are declared here for the orphan check to
    # read (design section 10.34.6).
    API_KEY_ENV = "GEMINI_API_KEY"
    ALSO_READS = ("GOOGLE_API_KEY",)

    ERROR_CLASSES = (
        (httpx.TimeoutException, "QC_HARNESS_CANDIDATE_TIMEOUT"),
        # WE NEVER REACHED IT, so it reported nothing.
        (httpx.ConnectError, "QC_HARNESS_ENGINE_UNREACHABLE"),
    )

    # THE QUOTA IDS THAT NAME A PERIOD NO RUN CAN OUTWAIT. Gemini spells the
    # period into the id, so the substring is the whole test. Measured
    # 2026-09-26 against the free tier, which allows 20 requests per day per
    # model: `GenerateRequestsPerDayPerProjectPerModel-FreeTier`.
    _SPENT_PERIODS: Final[tuple[str, ...]] = ("PerDay", "PerMonth")

    def period_quota_exhausted(self, error: Exception) -> bool:
        """Report whether the named quota covers a day or longer.

        **Read from the message rather than a field**, because the Gen AI SDK
        surfaces the violation body as text on the exception and offers no
        parsed accessor for it. That makes this a substring test, which is
        why it is written to fail closed: an unrecognised body is not an
        exhausted period.

        Args:
            error (Exception): The provider failure.

        Returns:
            bool: ``True`` where the quota id names a day or a month, so no
            backoff this run could afford would clear it.
        """
        body = str(error)
        return any(period in body for period in self._SPENT_PERIODS)

    def compose_request(self, case: Any) -> dict[str, Any]:
        """Build a Gen AI request from an evaluation case.

        The case is typed loosely so Tier 2 does not import Tier 1's record and
        invert the dependency.

        Args:
            case (Any): An ``EvaluationCase``.

        Returns:
            dict: The request, as a plain mapping so it can be hashed for
            replay without a provider object reaching the hash. The SDK accepts
            the configuration as a mapping, so nothing is lost by keeping it in
            a form the hash can consume.
        """
        task = case.task
        parts: list[dict[str, Any]] = [
            {
                "text": f"<document id={document.document_id}>\n"
                        f"{document.content}\n</document>"
            }
            for document in task.context_documents
        ]
        parts.append({"text": task.user_prompt})

        config: dict[str, Any] = {"automatic_function_calling": {"disable": True}}
        if task.system_instruction is not None:
            config["system_instruction"] = task.system_instruction
        if task.available_tools:
            config["tools"] = [
                {
                    "function_declarations": [
                        {
                            "name": tool.tool_name,
                            "description": tool.description,
                            "parameters": tool.parameters_schema,
                        }
                        for tool in task.available_tools
                    ]
                }
            ]
        return {
            "model": self._model,
            "contents": [{"role": "user", "parts": parts}],
            "config": config,
        }

    def dispatch(self, request: dict[str, Any]) -> Any:
        """Issue exactly one request and return the provider's response.

        Args:
            request (dict): The composed request.

        Returns:
            Any: The provider response object, which stops at this adapter.
        """
        if self._client is None:
            self._client = genai.Client()
        return self._client.models.generate_content(**request)

    def normalize_response(self, response: Any, case_id: str) -> NormalizedResponse:
        """Convert a Gen AI response into the canonical shape.

        Args:
            response (Any): The provider response.
            case_id (str): The case this answers.

        Returns:
            NormalizedResponse: The only shape that crosses into Tier 3.
        """
        tool_calls = self.extract_tool_calls(response)
        return self.build_response(
            case_id,
            ProviderFacts(
                text="".join(
                    part.text for part in _content_parts(response)
                    if getattr(part, "text", None)
                ),
                tool_calls=tool_calls,
                usage=self.read_usage(response),
                block_reason=self._block_reason(response),
                block_stage=self._block_stage(response),
                finish_reason=self._finish_reason(response, tool_calls),
                raw_reference=self.raw_reference_of(response),
                resolved_model=self.resolve_model_version(response),
            ),
        )

    @staticmethod
    def _block_reason(response: Any) -> str:
        """Return the provider's reason for refusing, at either stage.

        **Zero candidates is the shape of a prompt-stage block here**, not a
        candidate carrying empty content. `154002` was reported as a model failure
        for three runs because the harness saw an empty response while the reason
        sat unread in `prompt_feedback`.

        Args:
            response (Any): A Gen AI response.

        Returns:
            str: The reason's name, or empty where nothing was blocked.
        """
        feedback = getattr(response, "prompt_feedback", None)
        reported = getattr(feedback, "block_reason", None)
        if reported is not None:
            return str(getattr(reported, "name", None) or reported)

        # RESPONSE STAGE. Generation began and the provider stopped it, which it
        # reports on the candidate rather than on the prompt.
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            finish = getattr(candidates[0], "finish_reason", None)
            name = str(getattr(finish, "name", None) or finish or "")
            if _FINISH_REASONS.get(name) == "content_filter":
                return name
        return ""

    @staticmethod
    def _block_stage(response: Any) -> str:
        """Return where a refusal happened, as far as the provider reveals it.

        **Both stages count as resistance today**, and they are still separated:
        a prompt refused before generation and a response stopped midway are
        different events, and a corpus that recorded only "blocked" could not be
        split afterwards if the requirement changed.

        Args:
            response (Any): A Gen AI response.

        Returns:
            str: ``prompt``, ``response``, or empty where nothing was blocked.
        """
        feedback = getattr(response, "prompt_feedback", None)
        if getattr(feedback, "block_reason", None) is not None:
            return "prompt"
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            finish = getattr(candidates[0], "finish_reason", None)
            name = str(getattr(finish, "name", None) or finish or "")
            if _FINISH_REASONS.get(name) == "content_filter":
                return "response"
        return ""

    def usage_from(self, usage: Any) -> TokenUsage:
        """Return Gen AI's four counts.

        **`thoughts_token_count` is the count that was costing money
        invisibly.** Gen AI reports thinking apart from `candidates_token_count`
        and bills it at the output rate, so reading only the visible count
        understates the bill by however much the model thought.

        Args:
            usage (Any): A `usage_metadata` object.

        Returns:
            TokenUsage: The counts.
        """
        return TokenUsage(
            input_tokens=int(getattr(usage, "prompt_token_count", 0) or 0),
            output_tokens=int(getattr(usage, "candidates_token_count", 0) or 0),
            thinking_tokens=int(getattr(usage, "thoughts_token_count", 0) or 0),
            cached_input_tokens=int(
                getattr(usage, "cached_content_token_count", 0) or 0
            ),
        )

    def extract_tool_calls(self, response: Any) -> list[ToolCall]:
        """Capture the tool calls the model intended.

        **This provider supplies arguments already parsed**, as OpenAI does not.
        They still pass through the canonical constructor, so a provider that
        changes its mind about the shape is absorbed here rather than surfacing
        in Tier 3.

        Args:
            response (Any): The provider response.

        Returns:
            list[ToolCall]: Intent only, in the order the model produced it.
        """
        requested = [
            part.function_call for part in _content_parts(response)
            if getattr(part, "function_call", None)
        ]
        return [
            ToolCall.from_provider(
                tool_name=call.name,
                arguments=call.args or {},
                sequence=sequence,
                call_id=getattr(call, "id", None),
            )
            for sequence, call in enumerate(requested)
        ]

    def resolve_model_version(self, response: Any) -> str:
        """Return the model the provider reported serving.

        **This provider names the field differently from the other two**, and
        the requested identifier is frequently an alias that floats to a dated
        build, which is precisely the event A8 exists to record.

        Args:
            response (Any): The provider response.

        Returns:
            str: The resolved identifier.

        Raises:
            ValueError: With ``QC_HARNESS_VERSION_UNAVAILABLE`` when the
                response carries no usable model, which fails preflight.
        """
        resolved = getattr(response, "model_version", None)
        if resolved is None or not str(resolved).strip():
            logger.error("QC_HARNESS_VERSION_UNAVAILABLE gemini returned no model identifier")
            raise ValueError(
                "QC_HARNESS_VERSION_UNAVAILABLE: gemini returned no model identifier"
            )
        return str(resolved).strip()

    # KEYWORDS GEN AI'S `response_schema` REJECTS. Its structured output takes a
    # restricted OpenAPI subset rather than JSON Schema, and an unsupported
    # keyword is a 400 naming the field rather than a warning.
    #
    # EVIDENCE-DRIVEN, AND DELIBERATELY SHORT. `additionalProperties` is here
    # because a request carrying it was rejected, not because a list somewhere
    # says so. An entry is added when a request fails for it, so this never
    # claims knowledge nobody verified.
    _SCHEMA_KEYWORDS_REJECTED: Final[frozenset[str]] = frozenset({"additionalProperties"})

    @classmethod
    def _wire_schema(cls, schema: Any) -> Any:
        """Return the schema with keywords this provider cannot parse removed.

        **The caller's schema is not modified.** Tier 3 keeps
        `additionalProperties: false` because the reply validation needs it: a
        judge returning a criterion nobody asked for must fail, and that check
        reads the same schema this method copies.

        Args:
            schema (Any): The reply schema as Tier 3 composed it.

        Returns:
            Any: A copy the provider accepts, structurally identical otherwise.
        """
        if isinstance(schema, dict):
            return {
                key: cls._wire_schema(value)
                for key, value in schema.items()
                if key not in cls._SCHEMA_KEYWORDS_REJECTED
            }
        if isinstance(schema, list):
            return [cls._wire_schema(entry) for entry in schema]
        return schema

    def compose_judgement(self, prompt: str, reply_schema: dict[str, Any]) -> Any:
        """Build a Gen AI request constrained to the reply schema.

        ``response_mime_type`` and ``response_schema`` are this protocol's
        native structured-output controls, so the constraint is enforced by the
        provider rather than asked for in prose.

        **Function calling stays disabled and no tools are offered.** A judge
        has nothing to call, and a judge that called something would be acting
        on text an attacker may have written.

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
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "config": {
                "automatic_function_calling": {"disable": True},
                "response_mime_type": "application/json",
                "response_schema": self._wire_schema(reply_schema),
            },
        }

    def parse_judgement(self, response: Any) -> dict[str, Any]:
        """Read a Gen AI reply into a mapping.

        **A parse, not an attribute read.** A provider honouring a schema still
        returns it as text.

        Args:
            response (Any): The provider-shaped reply.

        Returns:
            dict[str, Any]: The reply as a mapping.

        Raises:
            ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the reply is not
                a JSON object. **Not treated as hijack here**: Tier 3 owns that
                call, and an adapter deciding it would be a second evaluator
                with no rubric.
        """
        return require_json_object(
            "".join(part.text or "" for part in _content_parts(response)),
            self.ENGINE_NAME,
        )

    def declare_capabilities(self) -> Capabilities:
        """Return what this provider supports.

        Returns:
            Capabilities: Tool calling and structured output are supported, and
            a system instruction is a configuration field rather than something
            folded into the prompt.
        """
        return Capabilities(
            tool_calling=True, structured_output=True, system_instruction=True
        )

    @staticmethod
    def _finish_reason(response: Any, tool_calls: list[ToolCall]) -> str:
        """Reconcile this provider's finish reason with the canonical set.

        **A function-calling turn ends with the ordinary stop reason here**,
        while the other two providers say so in the finish reason. Reporting
        the literal value would make a cross-engine comparison of tool-use rates
        a comparison of vendor conventions, so the presence of captured calls
        decides it.

        The override is deliberately narrow: it applies only where the provider
        said the turn stopped normally. A truncated or filtered turn keeps its
        own reason even when calls were captured, because that reason is the
        more important fact about the response.

        Args:
            response (Any): The provider response.
            tool_calls (list): What was captured from the content parts.

        Returns:
            str: A registered canonical finish reason.
        """
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return "unknown"
        reported = getattr(candidates[0], "finish_reason", None)
        canonical = _FINISH_REASONS.get(
            getattr(reported, "name", None) or str(reported), "unknown"
        )
        if canonical == "stop" and tool_calls:
            return "tool_calls"
        return canonical


def _content_parts(response: Any) -> list[Any]:
    """Return the first candidate's content parts, tolerating their absence.

    A blocked or empty candidate carries no content at all rather than an empty
    list, so every access here is guarded. Raising instead would turn a model
    behaviour we want to record into a harness failure that records nothing.

    Args:
        response (Any): The provider response.

    Returns:
        list: The parts, or an empty list when the response carries none.
    """
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return []
    content = getattr(candidates[0], "content", None)
    return list(getattr(content, "parts", None) or [])
