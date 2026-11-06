# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Fake OpenAI Responses replies, shaped like the real SDK's, for the adapter cases.

Created: 2026-11-06
Last updated: 2026-11-06

This file contains :func:`responses_response`, which builds a Responses reply
carrying text, refusal parts, function calls, a reasoning item and a status,
and :func:`responses_judgement`, which builds a schema-constrained judgement.
:mod:`tests.execution.provider_doubles` enrols both under the ``openai`` engine
in ``ADAPTER_DOUBLES``, so the conformance battery and the per-adapter cases
feed them to :class:`~execution.adapters.openai_responses.OpenAIResponsesAdapter`
in place of a provider. `pytest.ini` collects only `mqc_*.py`, so nothing here
is collected.

**The shape is the protocol's, not Chat Completions' reordered.** The answer
and every tool call are items of one ``output`` list, a reasoning item comes
first on a reasoning model and carries no text, and the reason a reply stopped
is a ``status`` with ``incomplete_details``. A tool call refuses to be invoked,
as every double's does.

Specified by ``docs/design/tier2_execution.md`` section 3.5.4.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from tests.execution.doubles_shared import (
    DEFAULT_CACHED,
    DEFAULT_INPUT,
    DEFAULT_MODEL,
    DEFAULT_TEXT,
    DEFAULT_THINKING,
    DEFAULT_TOKENS,
    InvocationLog,
)


@dataclass
class _ResponsesPart:
    """One content part of a message item.

    Attributes:
        type (str): ``output_text`` or ``refusal``.
        text (Optional[str]): Populated on an ``output_text`` part.
        refusal (Optional[str]): Populated on a ``refusal`` part.
    """

    type: str
    text: Optional[str] = None
    refusal: Optional[str] = None


@dataclass
class _ResponsesMessage:
    """A message item in ``output``.

    Attributes:
        content (list): Text and refusal parts, in order.
        type (str): Always ``message``.
        role (str): Always ``assistant``.
    """

    content: list[_ResponsesPart]
    type: str = "message"
    role: str = "assistant"


@dataclass
class _ResponsesReasoning:
    """A reasoning item, which a reasoning model emits before its answer.

    Attributes:
        type (str): Always ``reasoning``.
        summary (list): Empty unless a summary was asked for, which the
            harness never asks.
    """

    type: str = "reasoning"
    summary: list[Any] = field(default_factory=list)


@dataclass
class _ResponsesFunctionCall:
    """A function call item in ``output``.

    Attributes:
        name (str): The tool named.
        arguments (str): **A JSON string**, as on Chat Completions.
        call_id (str): The identifier a tool result would answer.
        id (str): The item's own identifier.
        type (str): Always ``function_call``.
        log (Optional[InvocationLog]): Where an execution attempt is recorded.
    """

    name: str
    arguments: str
    call_id: str
    id: str
    type: str = "function_call"
    log: Optional[InvocationLog] = None

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        """Refuse an attempt to invoke this call.

        Args:
            *args (Any): Ignored.
            **kwargs (Any): Ignored.

        Returns:
            None

        Raises:
            MQCToolWasExecuted: Always.
        """
        if self.log is not None:
            self.log.executed(self.name)


@dataclass
class _OutputDetails:
    """The nested reasoning count.

    Attributes:
        reasoning_tokens (int): Thinking, included in ``output_tokens``.
    """

    reasoning_tokens: int = DEFAULT_THINKING


@dataclass
class _InputDetails:
    """The nested cache count.

    Attributes:
        cached_tokens (int): Input served from cache.
    """

    cached_tokens: int = DEFAULT_CACHED


@dataclass
class _ResponsesUsage:
    """Token usage under this protocol's names, and only those.

    **No Chat Completions spelling is present**, so an adapter still reading
    ``prompt_tokens`` reads nothing and the count it reports is zero.

    Attributes:
        input_tokens (int): Input, cached input included.
        output_tokens (int): Output, reasoning included.
        input_tokens_details (_InputDetails): Where cached input is reported.
        output_tokens_details (_OutputDetails): Where reasoning is reported.
    """

    input_tokens: int = DEFAULT_INPUT
    output_tokens: int = DEFAULT_TOKENS
    input_tokens_details: _InputDetails = field(default_factory=_InputDetails)
    output_tokens_details: _OutputDetails = field(default_factory=_OutputDetails)


@dataclass
class _IncompleteDetails:
    """Why a reply stopped before it finished.

    Attributes:
        reason (str): ``max_output_tokens`` or ``content_filter``.
    """

    reason: str


@dataclass
class _ResponsesResponse:
    """An OpenAI Responses reply.

    Attributes:
        output (list): A reasoning item, then message and function call items.
        model (str): The resolved identifier.
        usage (_ResponsesUsage): Token counts.
        id (str): The pointer normalization keeps.
        status (str): ``completed`` or ``incomplete``.
        incomplete_details (Optional[_IncompleteDetails]): Present when
            incomplete.
        invocations (list): Tools an adapter tried to execute.
    """

    output: list[Any]
    model: str
    usage: _ResponsesUsage
    id: str
    status: str
    incomplete_details: Optional[_IncompleteDetails]
    invocations: list[str]


def responses_response(
    text: str = DEFAULT_TEXT,
    tool_calls: Optional[list[tuple[str, dict[str, Any]]]] = None,
    resolved_model: str = DEFAULT_MODEL,
    incomplete_reason: Optional[str] = None,
    arguments_text: Optional[str] = None,
    parts: Optional[list[tuple[str, str]]] = None,
) -> _ResponsesResponse:
    """Build a Responses reply double.

    Args:
        text (str): The single text part's content.
        tool_calls (Optional[list]): Name and argument pairs, serialized to a
            JSON string because that is what this protocol sends.
        resolved_model (str): What the provider reports serving.
        incomplete_reason (Optional[str]): Marks the reply incomplete for this
            reason.
        arguments_text (Optional[str]): Raw argument text, where the case is
            about a string the model malformed.
        parts (Optional[list]): Kind and content pairs, ``output_text`` or
            ``refusal``, where the case is about several parts.

    Returns:
        _ResponsesResponse: The double, its reasoning item first.
    """
    log = InvocationLog()
    message_parts = [
        _ResponsesPart(type=kind, text=content)
        if kind == "output_text"
        else _ResponsesPart(type=kind, refusal=content)
        for kind, content in (parts if parts is not None else [("output_text", text)])
    ]
    output: list[Any] = [_ResponsesReasoning(), _ResponsesMessage(content=message_parts)]
    for index, (name, arguments) in enumerate(tool_calls or []):
        output.append(
            _ResponsesFunctionCall(
                name=name,
                arguments=arguments_text if arguments_text is not None
                else json.dumps(arguments),
                call_id=f"call_{index}",
                id=f"fc_{index}",
                log=log,
            )
        )
    return _ResponsesResponse(
        output=output,
        model=resolved_model,
        usage=_ResponsesUsage(),
        id="resp_0001",
        status="incomplete" if incomplete_reason else "completed",
        incomplete_details=_IncompleteDetails(incomplete_reason)
        if incomplete_reason else None,
        invocations=log.invocations,
    )


def responses_judgement(payload: dict[str, Any]) -> _ResponsesResponse:
    """Build a Responses judgement double.

    The payload arrives as JSON text in a message item, which is what a reply
    constrained by ``text.format`` looks like on this protocol.

    Args:
        payload (dict): The judgement the adapter should read back.

    Returns:
        _ResponsesResponse: The double.
    """
    return responses_response(text=json.dumps(payload))
