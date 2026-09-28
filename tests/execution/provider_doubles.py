# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Provider-shaped response and error doubles, one per registered adapter.

Support code for the conformance battery and the per-adapter cases. Not a test
module: `pytest.ini` collects only `mqc_*.py`, so nothing here is collected.

**Shapes come from each provider's published API documentation**, not from a
recorded live call. A3 keeps the suite at zero cost, and a double built from the
documented contract is what lets an adapter be exercised before a key exists.

**Each double is deliberately a different shape**, because that is the whole
point. A double set that normalised the three providers before the adapters saw
them would make the battery assert that our own test helper is consistent.

**A tool call is captured, never executed.** Every double records invocations on
itself and exposes them, so an adapter that acted on the model's intent is
caught by the absence of an empty list rather than by a side effect nobody
checked.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Final, Optional

import anthropic
import httpx
import openai
from google.genai import errors as genai_errors

# The four provider failure classes every adapter maps, and the harness code
# each one must produce. Named once here so the battery cannot test a provider
# against a code that provider never raises.
ERROR_CLASS_CODES: Final[dict[str, str]] = {
    "rate_limit": "QC_HARNESS_RATE_LIMIT",
    "timeout": "QC_HARNESS_CANDIDATE_TIMEOUT",
    "auth": "QC_HARNESS_AUTH_ERROR",
    "not_found": "QC_HARNESS_VERSION_UNAVAILABLE",
    # THE PROVIDER REPORTING ITSELF BUSY. Added after a live run met it and
    # the artifact reported a parser error (tier2 section 8.5).
    # ONE KIND PER TRANSIENT STATUS, rather than one standing for the family.
    # The SDK protocols collapse every 5xx into one exception class, so a
    # single entry would prove the mapping for whichever status happened to be
    # chosen and say nothing about the rest; gemini maps them individually and
    # is where a missing row would actually hide (tier2 section 8.5.2).
    "unavailable_500": "QC_HARNESS_PROVIDER_UNAVAILABLE",
    "unavailable_502": "QC_HARNESS_GATEWAY_FAILURE",
    "unavailable_503": "QC_HARNESS_PROVIDER_UNAVAILABLE",
    "unavailable_504": "QC_HARNESS_GATEWAY_FAILURE",
    # OURS: the provider rejected what we composed.
    "bad_request": "QC_HARNESS_REQUEST_REJECTED",
}

# An error class no adapter recognises. It must map to the parser code and be
# preserved in the log, so an unanticipated failure stays diagnosable.
UNRECOGNISED_ERROR: Final[Exception] = RuntimeError("a failure nobody anticipated")

_DEFAULT_TEXT: Final[str] = "The answer, grounded in the supplied document."
_DEFAULT_MODEL: Final[str] = "served-build-001"
_DEFAULT_TOKENS: Final[int] = 42

# DISTINCT FROM EACH OTHER ON PURPOSE. Equal defaults would let an adapter
# read the wrong count and still pass.
_DEFAULT_INPUT: Final[int] = 137
_DEFAULT_THINKING: Final[int] = 41
_DEFAULT_CACHED: Final[int] = 19


class MQCToolWasExecuted(AssertionError):
    """An adapter invoked a tool the model merely intended to call.

    Raised by the doubles rather than recorded quietly, because executing a
    model's tool call is the one failure in Tier 2 that acts on the world.
    """


@dataclass
class _InvocationLog:
    """What an adapter tried to execute, which must always be nothing.

    Attributes:
        invocations (list): Tool names an adapter attempted to run.
    """

    invocations: list[str] = field(default_factory=list)

    def executed(self, tool_name: str) -> None:
        """Record and refuse an execution attempt.

        Args:
            tool_name (str): The tool an adapter tried to run.

        Returns:
            None

        Raises:
            MQCToolWasExecuted: Always. Tool usage is behaviour under test.
        """
        self.invocations.append(tool_name)
        raise MQCToolWasExecuted(
            f"the adapter executed {tool_name}, which A9 forbids: tool-call intent "
            f"is the recorded artifact and is never acted on"
        )


@dataclass
class _ClaudeBlock:
    """One content block, as the Anthropic SDK returns it.

    Attributes:
        type (str): ``text`` or ``tool_use``.
        text (Optional[str]): Populated on a text block.
        name (Optional[str]): Populated on a tool-use block.
        input (Optional[dict]): **Already a parsed mapping** on this provider.
        id (Optional[str]): The provider's call identifier.
        log (Optional[_InvocationLog]): Where an execution attempt is recorded.
    """

    type: str
    text: Optional[str] = None
    name: Optional[str] = None
    input: Optional[dict[str, Any]] = None
    id: Optional[str] = None
    log: Optional[_InvocationLog] = None

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        """Refuse an attempt to invoke this block as a callable tool.

        Args:
            *args (Any): Ignored.
            **kwargs (Any): Ignored.

        Returns:
            None

        Raises:
            MQCToolWasExecuted: Always.
        """
        if self.log is not None:
            self.log.executed(self.name or "unnamed")


@dataclass
class _CompletionDetails:
    """OpenAI's nested reasoning count.

    Attributes:
        reasoning_tokens (int): Thinking, which this protocol reports inside a
            details object rather than beside the total.
    """

    reasoning_tokens: int = _DEFAULT_THINKING


@dataclass
class _PromptDetails:
    """OpenAI's nested cache count.

    Attributes:
        cached_tokens (int): Input served from cache.
    """

    cached_tokens: int = _DEFAULT_CACHED


@dataclass
class _Usage:
    """Token usage, under whichever name a provider gives it.

    **Every spelling, including the ones nobody read until 2026-09-27.** A
    double that omits the field under test cannot fail when the adapter stops
    reading it, so the counts below exist to be asserted rather than to look
    plausible.

    Attributes:
        output_tokens (int): Anthropic's name. **Already includes thinking**,
            which is why there is no separate Anthropic thinking count.
        completion_tokens (int): OpenAI's name.
        candidates_token_count (int): Gemini's name for visible output.
        input_tokens (int): Anthropic's name.
        prompt_tokens (int): OpenAI's name.
        prompt_token_count (int): Gemini's name.
        thoughts_token_count (int): Gemini's name for thinking, reported apart
            from the visible count and billed as output.
        cache_read_input_tokens (int): Anthropic's name for cached input.
        cached_content_token_count (int): Gemini's name for the same.
        completion_tokens_details (_CompletionDetails): Where OpenAI puts
            reasoning.
        prompt_tokens_details (_PromptDetails): Where OpenAI puts cached input.
    """

    output_tokens: int = _DEFAULT_TOKENS
    completion_tokens: int = _DEFAULT_TOKENS
    candidates_token_count: int = _DEFAULT_TOKENS
    input_tokens: int = _DEFAULT_INPUT
    prompt_tokens: int = _DEFAULT_INPUT
    prompt_token_count: int = _DEFAULT_INPUT
    thoughts_token_count: int = _DEFAULT_THINKING
    cache_read_input_tokens: int = _DEFAULT_CACHED
    cached_content_token_count: int = _DEFAULT_CACHED
    completion_tokens_details: _CompletionDetails = field(
        default_factory=_CompletionDetails
    )
    prompt_tokens_details: _PromptDetails = field(default_factory=_PromptDetails)


@dataclass
class _ClaudeResponse:
    """An Anthropic Messages response.

    Attributes:
        content (list): Text and tool-use blocks, in order.
        model (str): The resolved identifier, on this provider's field name.
        stop_reason (str): This provider's stop vocabulary.
        usage (_Usage): Token counts.
        id (str): The pointer normalization keeps.
        invocations (list): Tools an adapter tried to execute.
    """

    content: list[_ClaudeBlock]
    model: str
    stop_reason: str
    usage: _Usage
    id: str
    invocations: list[str]


@dataclass
class _OpenAIFunction:
    """The function half of an OpenAI tool call.

    Attributes:
        name (str): The tool named.
        arguments (str): **A JSON string** on this provider, not a mapping.
    """

    name: str
    arguments: str


@dataclass
class _OpenAIToolCall:
    """One OpenAI tool call.

    Attributes:
        id (str): The provider's call identifier.
        function (_OpenAIFunction): Name and serialized arguments.
        log (Optional[_InvocationLog]): Where an execution attempt is recorded.
    """

    id: str
    function: _OpenAIFunction
    log: Optional[_InvocationLog] = None

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
            self.log.executed(self.function.name)


@dataclass
class _OpenAIMessage:
    """The assistant message on an OpenAI choice.

    Attributes:
        content (Optional[str]): The text, absent on a pure tool-call turn.
        tool_calls (Optional[list]): **Absent entirely** when none, which is
            this provider's convention and not an empty list.
    """

    content: Optional[str]
    tool_calls: Optional[list[_OpenAIToolCall]] = None


@dataclass
class _OpenAIChoice:
    """One OpenAI choice.

    Attributes:
        message (_OpenAIMessage): The assistant turn.
        finish_reason (str): This provider's vocabulary.
    """

    message: _OpenAIMessage
    finish_reason: str


@dataclass
class _OpenAIResponse:
    """An OpenAI Chat Completions response.

    Attributes:
        choices (list): One choice, since the harness requests one.
        model (str): The resolved identifier.
        usage (_Usage): Token counts.
        id (str): The pointer normalization keeps.
        invocations (list): Tools an adapter tried to execute.
    """

    choices: list[_OpenAIChoice]
    model: str
    usage: _Usage
    id: str
    invocations: list[str]


@dataclass
class _GeminiFunctionCall:
    """One Gemini function call.

    Attributes:
        name (str): The tool named.
        args (dict): **Already a parsed mapping** on this provider.
        id (Optional[str]): The provider's call identifier.
        log (Optional[_InvocationLog]): Where an execution attempt is recorded.
    """

    name: str
    args: dict[str, Any]
    id: Optional[str] = None
    log: Optional[_InvocationLog] = None

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
class _GeminiPart:
    """One Gemini content part.

    Attributes:
        text (Optional[str]): Populated on a text part.
        function_call (Optional[_GeminiFunctionCall]): Populated on a call.
    """

    text: Optional[str] = None
    function_call: Optional[_GeminiFunctionCall] = None


@dataclass
class _GeminiContent:
    """The content of a Gemini candidate.

    Attributes:
        parts (list): Text and function-call parts, in order.
    """

    parts: list[_GeminiPart]


@dataclass
class _GeminiFinishReason:
    """A Gemini finish reason, which arrives as an enum carrying a name.

    Attributes:
        name (str): The enum member name, such as ``STOP``.
    """

    name: str


@dataclass
class _GeminiCandidate:
    """One Gemini candidate.

    Attributes:
        content (Optional[_GeminiContent]): **Absent entirely** on a blocked
            candidate, which is this provider's convention and not empty
            content.
        finish_reason (_GeminiFinishReason): This provider's vocabulary.
    """

    content: Optional[_GeminiContent]
    finish_reason: _GeminiFinishReason



@dataclass
class _BlockedReason:
    """The enum member a provider reports for refusing a prompt.

    Attributes:
        name (str): The member name, which is what the adapter reads.
    """

    name: str


@dataclass
class _PromptFeedback:
    """What the provider says about a prompt it declined.

    Attributes:
        block_reason (Optional[_BlockedReason]): Present only on a refusal.
    """

    block_reason: Optional[Any] = None

@dataclass
class _GeminiResponse:
    """A Gemini generate-content response.
    prompt_feedback: Optional[Any] = None

    Attributes:
        candidates (list): One candidate, since the harness requests one.
        model_version (str): The resolved identifier, on **this provider's own
            field name**, which differs from the other two.
        usage_metadata (_Usage): Token counts.
        response_id (str): The pointer normalization keeps.
        invocations (list): Tools an adapter tried to execute.
    """

    candidates: list[_GeminiCandidate]
    model_version: str
    usage_metadata: _Usage
    response_id: str
    invocations: list[str]
    prompt_feedback: Optional[Any] = None


def claude_response(
    text: str = _DEFAULT_TEXT,
    tool_calls: Optional[list[tuple[str, dict[str, Any]]]] = None,
    resolved_model: str = _DEFAULT_MODEL,
    stop_reason: Optional[str] = None,
    text_blocks: Optional[list[str]] = None,
) -> _ClaudeResponse:
    """Build an Anthropic response double.

    Args:
        text (str): The single text block's content.
        tool_calls (Optional[list]): Name and argument pairs.
        resolved_model (str): What the provider reports serving.
        stop_reason (Optional[str]): Overrides the reason derived from the
            presence of tool calls.
        text_blocks (Optional[list]): Several text blocks, where the case is
            about concatenation rather than a single block.

    Returns:
        _ClaudeResponse: The double.
    """
    log = _InvocationLog()
    blocks = [
        _ClaudeBlock(type="text", text=entry)
        for entry in (text_blocks if text_blocks is not None else [text])
    ]
    for index, (name, arguments) in enumerate(tool_calls or []):
        blocks.append(
            _ClaudeBlock(
                type="tool_use", name=name, input=arguments, id=f"toolu_{index}", log=log
            )
        )
    derived = "tool_use" if tool_calls else "end_turn"
    return _ClaudeResponse(
        content=blocks,
        model=resolved_model,
        stop_reason=stop_reason or derived,
        usage=_Usage(),
        id="msg_0001",
        invocations=log.invocations,
    )


def openai_response(
    text: str = _DEFAULT_TEXT,
    tool_calls: Optional[list[tuple[str, dict[str, Any]]]] = None,
    resolved_model: str = _DEFAULT_MODEL,
    finish_reason: Optional[str] = None,
    arguments_text: Optional[str] = None,
) -> _OpenAIResponse:
    """Build an OpenAI response double.

    Args:
        text (str): The message content.
        tool_calls (Optional[list]): Name and argument pairs, serialized to a
            JSON string because that is what this provider sends.
        resolved_model (str): What the provider reports serving.
        finish_reason (Optional[str]): Overrides the derived reason.
        arguments_text (Optional[str]): Raw argument text, where the case is
            about a string the model malformed.

    Returns:
        _OpenAIResponse: The double.
    """
    log = _InvocationLog()
    calls = [
        _OpenAIToolCall(
            id=f"call_{index}",
            function=_OpenAIFunction(
                name=name,
                arguments=arguments_text if arguments_text is not None
                else json.dumps(arguments),
            ),
            log=log,
        )
        for index, (name, arguments) in enumerate(tool_calls or [])
    ]
    derived = "tool_calls" if calls else "stop"
    return _OpenAIResponse(
        choices=[
            _OpenAIChoice(
                message=_OpenAIMessage(content=text, tool_calls=calls or None),
                finish_reason=finish_reason or derived,
            )
        ],
        model=resolved_model,
        usage=_Usage(),
        id="chatcmpl-0001",
        invocations=log.invocations,
    )


def gemini_response(
    text: str = _DEFAULT_TEXT,
    tool_calls: Optional[list[tuple[str, dict[str, Any]]]] = None,
    resolved_model: str = _DEFAULT_MODEL,
    finish_reason: str = "STOP",
    blocked: bool = False,
) -> _GeminiResponse:
    """Build a Gemini response double.

    Args:
        text (str): The text part's content.
        tool_calls (Optional[list]): Name and argument pairs.
        resolved_model (str): What the provider reports serving.
        finish_reason (str): This provider's enum member name. **Defaults to
            the ordinary stop reason even on a tool-calling turn**, which is
            the provider convention the adapter reconciles.
        blocked (bool): When true the candidate carries no content at all,
            which is what this provider sends on a safety block.

    Returns:
        _GeminiResponse: The double.
    """
    log = _InvocationLog()
    if blocked:
        candidate = _GeminiCandidate(
            content=None, finish_reason=_GeminiFinishReason(finish_reason)
        )
    else:
        parts = [_GeminiPart(text=text)]
        for index, (name, arguments) in enumerate(tool_calls or []):
            parts.append(
                _GeminiPart(
                    function_call=_GeminiFunctionCall(
                        name=name, args=arguments, id=f"fc_{index}", log=log
                    )
                )
            )
        candidate = _GeminiCandidate(
            content=_GeminiContent(parts=parts),
            finish_reason=_GeminiFinishReason(finish_reason),
        )
    return _GeminiResponse(
        candidates=[candidate],
        model_version=resolved_model,
        usage_metadata=_Usage(),
        response_id="resp_0001",
        invocations=log.invocations,
    )


def _http_response(status: int) -> httpx.Response:
    """Build the HTTP response an SDK exception needs to carry.

    Args:
        status (int): The status code.

    Returns:
        httpx.Response: A response with a request attached, which the SDK
        constructors require.
    """
    return httpx.Response(
        status_code=status, request=httpx.Request("POST", "https://example.invalid/v1")
    )


def claude_error(kind: str) -> Exception:
    """Build an Anthropic failure of the named kind.

    Args:
        kind (str): One of the keys in :data:`ERROR_CLASS_CODES`.

    Returns:
        Exception: The provider's own exception class.
    """
    if kind == "timeout":
        return anthropic.APITimeoutError(request=httpx.Request("POST", "https://x.invalid"))
    classes: dict[str, Any] = {
        "rate_limit": (anthropic.RateLimitError, 429),
        "auth": (anthropic.AuthenticationError, 401),
        "not_found": (anthropic.NotFoundError, 404),
        # THE TWO ADDED AFTER A LIVE RUN. A busy provider was reported as an
        # unanticipated failure, and a malformed request had nowhere of its
        # own to go (tier2 sections 8.5 and 8.5.3).
        "unavailable_500": (anthropic.InternalServerError, 500),
        "unavailable_502": (anthropic.InternalServerError, 502),
        "unavailable_503": (anthropic.InternalServerError, 503),
        "unavailable_504": (anthropic.InternalServerError, 504),
        "bad_request": (anthropic.BadRequestError, 400),
    }
    error_class, status = classes[kind]
    return error_class(
        message=f"provider says {kind}", response=_http_response(status), body=None
    )


def openai_error(kind: str) -> Exception:
    """Build an OpenAI failure of the named kind.

    Args:
        kind (str): One of the keys in :data:`ERROR_CLASS_CODES`.

    Returns:
        Exception: The provider's own exception class.
    """
    if kind == "timeout":
        return openai.APITimeoutError(request=httpx.Request("POST", "https://x.invalid"))
    classes: dict[str, Any] = {
        "rate_limit": (openai.RateLimitError, 429),
        "auth": (openai.AuthenticationError, 401),
        "not_found": (openai.NotFoundError, 404),
        # THE TWO ADDED AFTER A LIVE RUN. A busy provider was reported as an
        # unanticipated failure, and a malformed request had nowhere of its
        # own to go (tier2 sections 8.5 and 8.5.3).
        "unavailable_500": (openai.InternalServerError, 500),
        "unavailable_502": (openai.InternalServerError, 502),
        "unavailable_503": (openai.InternalServerError, 503),
        "unavailable_504": (openai.InternalServerError, 504),
        "bad_request": (openai.BadRequestError, 400),
    }
    error_class, status = classes[kind]
    return error_class(
        message=f"provider says {kind}", response=_http_response(status), body=None
    )


def gemini_error(kind: str) -> Exception:
    """Build a Gemini failure of the named kind.

    **This provider raises one class for every client failure** and carries the
    distinction in the status code, which is why the adapter maps statuses
    rather than exception types.

    Args:
        kind (str): One of the keys in :data:`ERROR_CLASS_CODES`.

    Returns:
        Exception: The provider's own exception class.
    """
    if kind == "timeout":
        return httpx.TimeoutException("the provider did not answer in time")
    statuses = {
        "rate_limit": 429,
        "auth": 401,
        "not_found": 404,
        "bad_request": 400,
    }
    if kind.startswith("unavailable_"):
        # A SERVER ERROR, which this SDK raises as its own class and carries
        # the status in. The status is read from the kind so the battery
        # exercises each one rather than a representative.
        transient = int(kind.rsplit("_", 1)[1])
        return genai_errors.ServerError(
            code=transient,
            response_json={
                "error": {"code": transient, "message": "high demand"}
            },
        )
    status = statuses[kind]
    return genai_errors.ClientError(
        code=status,
        response_json={"error": {"code": status, "message": f"provider says {kind}"}},
    )


def claude_judgement(payload: dict[str, Any]) -> _ClaudeResponse:
    """Build an Anthropic judgement double.

    **A forced tool call**, because that is how this protocol constrains a
    reply: the payload arrives as the call's already-parsed input rather than
    as text.

    Args:
        payload (dict): The judgement the adapter should read back.

    Returns:
        _ClaudeResponse: The double.
    """
    return claude_response(text="", tool_calls=[("mqc_judgement", payload)])


def openai_judgement(payload: dict[str, Any]) -> _OpenAIResponse:
    """Build a Chat Completions judgement double.

    The payload arrives as JSON text, which is what a schema-constrained reply
    looks like on this protocol.

    Args:
        payload (dict): The judgement the adapter should read back.

    Returns:
        _OpenAIResponse: The double.
    """
    return openai_response(text=json.dumps(payload))


def gemini_judgement(payload: dict[str, Any]) -> _GeminiResponse:
    """Build a Gen AI judgement double.

    Args:
        payload (dict): The judgement the adapter should read back.

    Returns:
        _GeminiResponse: The double.
    """
    return gemini_response(text=json.dumps(payload))


@dataclass(frozen=True)
class _AdapterDoubles:
    """One provider's response and error builders.

    Attributes:
        response (Callable): Builds a response double.
        error (Callable): Builds a failure of a named kind.
        judgement (Callable): Builds a schema-constrained judgement carrying a
            given payload. **Per protocol rather than per vendor**, because
            where the payload sits is a protocol property: JSON text on most,
            a forced tool call's parsed input on Anthropic Messages.
    """

    response: Callable[..., Any]
    error: Callable[[str], Exception]
    judgement: Callable[[dict[str, Any]], Any]


ADAPTER_DOUBLES: Final[dict[str, _AdapterDoubles]] = {
    "claude": _AdapterDoubles(
            response=claude_response,
            error=claude_error,
            judgement=claude_judgement,
        ),
    "openai": _AdapterDoubles(
            response=openai_response,
            error=openai_error,
            judgement=openai_judgement,
        ),
    "gemini": _AdapterDoubles(
            response=gemini_response,
            error=gemini_error,
            judgement=gemini_judgement,
        ),
    # SHARED WITH OPENAI BY PROTOCOL, not by coincidence. xAI serves the Chat
    # Completions shape, so the same response and error doubles exercise it.
    # An engine added on this protocol reuses this line with its name changed,
    # which is the conformance half of design section 3.3.
    "grok": _AdapterDoubles(
            response=openai_response,
            error=openai_error,
            judgement=openai_judgement,
        ),
}


def gemini_blocked_prompt(reason: str = "OTHER") -> _GeminiResponse:
    """Build the response a provider returns when it refuses the prompt.

    **Zero candidates, not a candidate carrying nothing.** `gemini_response`
    already had a `blocked` flag that produced a candidate whose content was
    absent, which is the shape of a blocked *candidate*. A prompt refused before
    generation returns no candidate at all and explains itself in
    `prompt_feedback`, and the difference is why `50015` was reported as a model
    failure for three runs: the double tested a shape the provider does not
    produce.

    Args:
        reason (str): The provider's own word for refusing.

    Returns:
        _GeminiResponse: A response with no candidates and a block reason.
    """
    return _GeminiResponse(
        candidates=[],
        model_version=_DEFAULT_MODEL,
        usage_metadata=_Usage(candidates_token_count=0),
        response_id="resp_blocked",
        invocations=[],
        prompt_feedback=_PromptFeedback(block_reason=_BlockedReason(reason)),
    )
