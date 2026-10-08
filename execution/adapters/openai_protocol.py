# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The Chat Completions wire protocol, which is not one vendor.

Implements the interface in :mod:`execution.adapters.base` against the
OpenAI Chat Completions API shape.

**A protocol is not a vendor**, which is the whole point of this module.
xAI (Grok), DeepSeek, Mistral, Groq, Together and OpenRouter all serve this
same shape, so each is a subclass naming an engine, a default model, an
endpoint and a credential variable. No protocol code is rewritten and no
conformance wiring is added: registration enrols the new engine in the
battery automatically (``harness_extensibility_standard.md`` section 10).

Replay-only under A3 until a key is provisioned, which changes nothing
here: every operation except :meth:`OpenAICompatibleAdapter.dispatch` runs
against a response object and needs no credential.

**One request per case. No loop, no tool execution.** A tool call is captured as
intent and never acted on, because tool usage is behaviour under test rather
than a prohibition.

**This provider returns tool arguments as a JSON string.** Anthropic returns a
parsed mapping for the same fact. The difference is absorbed in
:meth:`OpenAICompatibleAdapter.extract_tool_calls` so that Tier 3 handles one shape, and a
string that will not parse is a finding about the model rather than about us.
"""

import logging
import os
from typing import Any, Final, Optional

import openai

from cmn.tokens import TokenUsage
from execution.adapters.base import (
    Capabilities,
    ConfiguredAdapter,
    ProviderFacts,
    require_json_object,
)
from execution.normalize import NormalizedResponse, ToolCall

logger = logging.getLogger(__name__)


_ERROR_CLASSES: Final[tuple[tuple[type, str], ...]] = (
    (openai.RateLimitError, "QC_HARNESS_RATE_LIMIT"),
    (openai.APITimeoutError, "QC_HARNESS_CANDIDATE_TIMEOUT"),
    (openai.AuthenticationError, "QC_HARNESS_AUTH_ERROR"),
    (openai.PermissionDeniedError, "QC_HARNESS_AUTH_ERROR"),
    (openai.BadRequestError, "QC_HARNESS_REQUEST_REJECTED"),
    (openai.NotFoundError, "QC_HARNESS_VERSION_UNAVAILABLE"),
    # THE PROVIDER REPORTING ITSELF BUSY, retryable and deliberately not a
    # rate limit: one says we asked too often and the other says the provider
    # is busy (design section 8.5.1).
    # A FALLBACK ONLY. The shared status table decides 500 from
    # 502 and 503 from 504; this catches a server error that
    # somehow carries no status.
    (openai.InternalServerError, "QC_HARNESS_PROVIDER_UNAVAILABLE"),
    # WE NEVER REACHED IT, so it reported nothing. Mis-filed as the
    # provider being busy when the transient family was added, which
    # is the same error 8.5.4 corrected for 502.
    (openai.APIConnectionError, "QC_HARNESS_ENGINE_UNREACHABLE"),
)

# This provider's finish reasons, mapped into the canonical vocabulary. The
# superseded spelling is kept alongside the current one because an older
# deployment still emits it, and dropping it would record a successful tool call
# as an unknown outcome.
_FINISH_REASONS: Final[dict[str, str]] = {
    "stop": "stop",
    "length": "length",
    "tool_calls": "tool_calls",
    "function_call": "tool_calls",
    "content_filter": "content_filter",
}


class OpenAICompatibleAdapter(ConfiguredAdapter):
    """The Chat Completions protocol, which several vendors serve.

    **Subclass this to add an engine, do not copy it.** A subclass names an
    engine, a default model, an endpoint and a credential variable, and
    inherits the protocol entire, including judging (design section 3.5).

    Attributes:
        ENGINE_NAME (str): The engine this adapter serves.
        DEFAULT_MODEL (str): Requested when configuration names none.
        BASE_URL (Optional[str]): The endpoint, or ``None`` for the SDK's own
            default, which is OpenAI. **This is the only field that routes a
            request**, so an engine that forgets it silently reaches OpenAI
            with another vendor's key; ``MQC_EXE_UNI_113014`` reports that.
        API_KEY_ENV (str): The environment variable carrying this engine's
            credential. **A name, never a value**: credentials are read from
            the environment at runtime and never appear in configuration.
    """

    ENGINE_NAME = ""
    DEFAULT_MODEL = ""
    BASE_URL: Optional[str] = None
    API_KEY_ENV: str = "OPENAI_API_KEY"

    def client_options(self) -> dict[str, Any]:
        """Return the constructor arguments this engine's client needs.

        **The credential is read here and nowhere earlier**, so building an
        adapter still needs none and every offline operation stays testable.

        Returns:
            dict[str, Any]: ``base_url`` when the engine declares one, and
            ``api_key`` when its variable is set. **An absent variable is
            omitted rather than passed empty**, so the SDK raises its own
            authentication error naming what it looked for.
        """
        options: dict[str, Any] = {}
        if self.BASE_URL:
            options["base_url"] = self.BASE_URL
        credential = os.environ.get(self.API_KEY_ENV)
        if credential:
            options["api_key"] = credential
        return options

    ERROR_CLASSES = _ERROR_CLASSES

    def compose_request(self, case: Any) -> dict[str, Any]:
        """Build a Chat Completions request from an evaluation case.

        The case is typed loosely so Tier 2 does not import Tier 1's record and
        invert the dependency.

        Args:
            case (Any): An ``EvaluationCase``.

        Returns:
            dict: The request, as a plain mapping so it can be hashed for
            replay without a provider object reaching the hash.
        """
        task = case.task
        messages: list[dict[str, Any]] = []
        if task.system_instruction is not None:
            messages.append({"role": "system", "content": task.system_instruction})
        for document in task.context_documents:
            messages.append(
                {
                    "role": "user",
                    "content": f"<document id={document.document_id}>\n"
                               f"{document.content}\n</document>",
                }
            )
        messages.append({"role": "user", "content": task.user_prompt})

        request: dict[str, Any] = {"model": self._model, "messages": messages}
        if task.available_tools:
            request["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.tool_name,
                        "description": tool.description,
                        "parameters": tool.parameters_schema,
                    },
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
            self._client = openai.OpenAI(**self.client_options())
        return self._client.chat.completions.create(**request)

    def normalize_response(self, response: Any, case_id: str) -> NormalizedResponse:
        """Convert a Chat Completions response into the canonical shape.

        Args:
            response (Any): The provider response.
            case_id (str): The case this answers.

        Returns:
            NormalizedResponse: The only shape that crosses into Tier 3.
        """
        choice = response.choices[0]
        return self.build_response(
            case_id,
            ProviderFacts(
                text=choice.message.content or "",
                tool_calls=self.extract_tool_calls(response),
                usage=self.read_usage(response),
                finish_reason=_FINISH_REASONS.get(choice.finish_reason, "unknown"),
                raw_reference=self.raw_reference_of(response),
                resolved_model=self.resolve_model_version(response),
            ),
        )

    def usage_from(self, usage: Any) -> TokenUsage:
        """Return this protocol's counts.

        **Nested, unlike the other two.** Reasoning and cached input are
        reported inside `*_tokens_details`, which is absent on a response that
        had neither, so both reads tolerate the absence rather than assuming the
        object.

        Args:
            usage (Any): A completion usage object.

        Returns:
            TokenUsage: The counts.
        """
        return TokenUsage(
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            thinking_tokens=int(
                getattr(
                    getattr(usage, "completion_tokens_details", None),
                    "reasoning_tokens",
                    0,
                )
                or 0
            ),
            cached_input_tokens=int(
                getattr(
                    getattr(usage, "prompt_tokens_details", None),
                    "cached_tokens",
                    0,
                )
                or 0
            ),
        )

    def extract_tool_calls(self, response: Any) -> list[ToolCall]:
        """Capture the tool calls the model intended.

        **This provider supplies arguments as a JSON string.** Parsing happens
        in the canonical constructor, which maps a malformed string to
        ``QC_LLM_SCHEMA_VIOLATION``: the transport succeeded and the model
        emitted bad JSON, so the finding belongs to the model.

        Args:
            response (Any): The provider response.

        Returns:
            list[ToolCall]: Intent only, in the order the model produced it.
            **Empty rather than absent** when the model called nothing, because
            this provider omits the field entirely instead of sending a list.
        """
        requested = getattr(response.choices[0].message, "tool_calls", None)
        return [
            ToolCall.from_provider(
                tool_name=entry.function.name,
                arguments=entry.function.arguments,
                sequence=sequence,
                call_id=getattr(entry, "id", None),
            )
            for sequence, entry in enumerate(requested or [])
        ]

    def resolve_model_version(self, response: Any) -> str:
        """Return the model the provider reported serving.

        Args:
            response (Any): The provider response.

        Returns:
            str: The resolved identifier, which carries a dated suffix the
            requested alias does not.

        Raises:
            ValueError: With ``QC_HARNESS_VERSION_UNAVAILABLE`` when the
                response carries no usable model, which fails preflight.
        """
        resolved = getattr(response, "model", None)
        if resolved is None or not str(resolved).strip():
            # NAMED FROM THE SUBCLASS, not hardcoded: every engine on this
            # protocol shares this method, and a message naming OpenAI would
            # misattribute another vendor's failure.
            logger.error(
                "QC_HARNESS_VERSION_UNAVAILABLE %s returned no model identifier",
                self.ENGINE_NAME,
            )
            raise ValueError(
                f"QC_HARNESS_VERSION_UNAVAILABLE: {self.ENGINE_NAME} returned "
                f"no model identifier"
            )
        return str(resolved).strip()

    def compose_judgement(self, prompt: str, reply_schema: dict[str, Any]) -> Any:
        """Build a request constrained to the reply schema.

        ``json_schema`` with ``strict`` is this protocol's native control, so
        the constraint is enforced by the provider rather than asked for in
        prose. **No tools are offered**, because a judge has nothing to call
        and a judge that called something would be acting on text an attacker
        may have written.

        **Inherited by every engine on this protocol.** Adding Grok bought
        judging without a line of judging code, which is the property section
        3.3 exists for.

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
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "mqc_judgement",
                    "strict": True,
                    "schema": reply_schema,
                },
            },
        }

    def parse_judgement(self, response: Any) -> dict[str, Any]:
        """Read a Chat Completions reply into a mapping.

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
            response.choices[0].message.content or "", self.ENGINE_NAME
        )

    def declare_capabilities(self) -> Capabilities:
        """Return what this provider supports.

        Returns:
            Capabilities: Tool calling and structured output are supported, and
            the system instruction is a message role rather than a separate
            request field, which is still a first-class channel.
        """
        return Capabilities(
            tool_calling=True, structured_output=True, system_instruction=True
        )
