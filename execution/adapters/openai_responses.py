# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The shared adapter for an engine that serves OpenAI's Responses API.

Created: 2026-11-06
Last updated: 2026-11-06

This file contains :class:`OpenAIResponsesAdapter`, which implements the
interface in :mod:`execution.adapters.base` against the Responses API shape.
It composes and dispatches the request, reads the answer, the tool calls, the
finish reason and the token usage from the reply's ``output`` items, composes
and parses a judge request, and names the reproduction endpoint and call.

**It is never registered itself.** :class:`~execution.adapters.openai.OpenAIAdapter`
subclasses it with the ``openai`` engine's name, default model and credential
variable, and the registry enrols that subclass.

**It subclasses the Chat Completions adapter and replaces only the wire
shape.** Both protocols are served by one SDK, so the client, the credential,
the error classes, the models endpoint and version resolution are inherited.

**One request per case. No loop, no tool execution**, and ``store`` is false
on every request: the harness never refers back to a response, so a copy kept
on the provider's side buys nothing.

Specified by ``docs/design/tier2_execution.md`` section 3.5.4.
"""

import logging
from typing import Any, Final

import openai

from cmn.tokens import TokenUsage
from execution.adapters.base import ProviderFacts, require_json_object
from execution.adapters.openai_protocol import (
    _SDK_DEFAULT_BASE_URL,
    OpenAICompatibleAdapter,
)
from execution.normalize import NormalizedResponse, ToolCall

logger = logging.getLogger(__name__)

# WHY AN INCOMPLETE REPLY STOPPED, mapped into the canonical vocabulary. A
# completed reply is "stop", or "tool_calls" where it carries a call.
_INCOMPLETE_REASONS: Final[dict[str, str]] = {
    "max_output_tokens": "length",
    "content_filter": "content_filter",
}

# THE PARTS OF A MESSAGE ITEM THAT ARE THE MODEL'S VISIBLE REPLY, and the
# attribute each carries its text on. A refusal is a reply (design 3.5.4).
_REPLY_PARTS: Final[dict[str, str]] = {"output_text": "text", "refusal": "refusal"}


class OpenAIResponsesAdapter(OpenAICompatibleAdapter):
    """The Responses protocol, which OpenAI serves for its own models.

    Attributes:
        ENGINE_NAME (str): The engine this adapter serves.
        DEFAULT_MODEL (str): Requested when configuration names none.
        BASE_URL (Optional[str]): The endpoint, or ``None`` for the SDK's own
            default.
        API_KEY_ENV (str): The variable carrying the credential.
    """

    REPRODUCTION_CALL = "client.responses.create"

    @classmethod
    def reproduction_endpoint(cls) -> str:
        """Return the responses endpoint this engine's requests go to.

        Returns:
            str: The full endpoint URL.
        """
        return f"{cls.BASE_URL or _SDK_DEFAULT_BASE_URL}/responses"

    @classmethod
    def reproduction_reply_fields(cls) -> str:
        """Return where a Responses reply holds the answer and any tool call.

        Returns:
            str: The item types of ``output`` that carry each.
        """
        return (
            "the `output_text` parts of each `message` item in `output`, and each "
            "`function_call` item in `output` for a tool call"
        )

    def compose_request(self, case: Any) -> dict[str, Any]:
        """Build a Responses request from an evaluation case.

        Args:
            case (Any): An ``EvaluationCase``.

        Returns:
            dict: The request, as a plain mapping so it can be hashed for
            replay without a provider object reaching the hash. Tools are flat
            and unstrict, so each is offered exactly as the case declares it.
        """
        task = case.task
        entries: list[dict[str, Any]] = []
        if task.system_instruction is not None:
            entries.append({"role": "system", "content": task.system_instruction})
        for document in task.context_documents:
            entries.append(
                {
                    "role": "user",
                    "content": f"<document id={document.document_id}>\n"
                               f"{document.content}\n</document>",
                }
            )
        entries.append({"role": "user", "content": task.user_prompt})

        request: dict[str, Any] = {"model": self._model, "input": entries, "store": False}
        if task.available_tools:
            request["tools"] = [
                {
                    "type": "function",
                    "name": tool.tool_name,
                    "description": tool.description,
                    "parameters": tool.parameters_schema,
                    "strict": False,
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
        return self._client.responses.create(**request)

    def normalize_response(self, response: Any, case_id: str) -> NormalizedResponse:
        """Convert a Responses reply into the canonical shape.

        Args:
            response (Any): The provider response.
            case_id (str): The case this answers.

        Returns:
            NormalizedResponse: The only shape that crosses into Tier 3.
        """
        calls = self.extract_tool_calls(response)
        return self.build_response(
            case_id,
            ProviderFacts(
                text=_reply_text(response),
                tool_calls=calls,
                usage=self.read_usage(response),
                finish_reason=_finish_reason(response, called=bool(calls)),
                raw_reference=self.raw_reference_of(response),
                resolved_model=self.resolve_model_version(response),
            ),
        )

    def usage_from(self, usage: Any) -> TokenUsage:
        """Return this protocol's counts.

        Args:
            usage (Any): A Responses usage object.

        Returns:
            TokenUsage: The counts. Reasoning is included in the output count
            and reported again in its details, as on Chat Completions.
        """
        return TokenUsage(
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            thinking_tokens=int(
                getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0)
                or 0
            ),
            cached_input_tokens=int(
                getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0)
                or 0
            ),
        )

    def extract_tool_calls(self, response: Any) -> list[ToolCall]:
        """Capture the tool calls the model intended.

        Args:
            response (Any): The provider response.

        Returns:
            list[ToolCall]: Intent only, one per ``function_call`` item, in the
            order the model produced them. Arguments arrive as a JSON string
            and a malformed one is the model's finding, as on Chat Completions.
        """
        requested = [
            item for item in getattr(response, "output", None) or []
            if getattr(item, "type", "") == "function_call"
        ]
        return [
            ToolCall.from_provider(
                tool_name=item.name,
                arguments=item.arguments,
                sequence=sequence,
                call_id=getattr(item, "call_id", None),
            )
            for sequence, item in enumerate(requested)
        ]

    def compose_judgement(self, prompt: str, reply_schema: dict[str, Any]) -> Any:
        """Build a request constrained to the reply schema through ``text.format``.

        Args:
            prompt (str): The rendered judge request, composed by Tier 3, which
                owns the isolation split.
            reply_schema (dict): The structure the judge must reply in.

        Returns:
            Any: The request, as a plain mapping. No tools are offered.
        """
        return {
            "model": self._model,
            "input": [{"role": "user", "content": prompt}],
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "mqc_judgement",
                    "strict": True,
                    "schema": reply_schema,
                }
            },
        }

    def parse_judgement(self, response: Any) -> dict[str, Any]:
        """Read a Responses reply into a mapping.

        Args:
            response (Any): The provider-shaped reply.

        Returns:
            dict[str, Any]: The reply as a mapping.

        Raises:
            ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the reply is not
                a JSON object.
        """
        return require_json_object(_reply_text(response), self.ENGINE_NAME)


def _reply_text(response: Any) -> str:
    """Join the text and refusal parts of every message item, in order.

    Args:
        response (Any): A Responses reply.

    Returns:
        str: The visible reply, empty where the model produced none. A
        reasoning item carries no part and adds nothing.
    """
    pieces: list[str] = []
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", "") != "message":
            continue
        for part in getattr(item, "content", None) or []:
            field_name = _REPLY_PARTS.get(getattr(part, "type", ""))
            if field_name:
                pieces.append(getattr(part, field_name, None) or "")
    return "".join(pieces)


def _finish_reason(response: Any, *, called: bool) -> str:
    """Map a reply's status to the canonical finish reason.

    Args:
        response (Any): A Responses reply.
        called (bool): Whether the reply carries a function call.

    Returns:
        str: ``tool_calls`` or ``stop`` for a completed reply, the mapped
        reason for an incomplete one, and ``unknown`` otherwise.
    """
    status = getattr(response, "status", None)
    if status == "completed":
        return "tool_calls" if called else "stop"
    if status == "incomplete":
        reason = getattr(getattr(response, "incomplete_details", None), "reason", "")
        return _INCOMPLETE_REASONS.get(reason, "unknown")
    return "unknown"
