# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Provider replies at the HTTP level, for driving the real SDKs through a mock transport.

Created: 2026-11-20
Last updated: 2026-11-20

This file contains ``WIRE_ENGINES``, which maps each registered engine to the
environment variable its SDK reads, a minimal request its adapter dispatches,
the header its SDK sends the credential under, and the JSON body a successful
reply carries; ``reply_handler``, which builds a ``MockTransport`` handler
answering every request with one engine's reply after any scripted failures;
``PLANTED_KEY``, the credential every case plants; and ``serve_mock``,
``mock_recorder``, ``send_through`` and ``dispatch_minimal``, which send
through a recorder or a real adapter with the mock in place of the network.

The wire capture cases feed these to the real SDKs in place of a provider, so
the headers a case asserts are the ones each SDK builds, and nothing leaves the
process. `pytest.ini` collects only `mqc_*.py`, so nothing here is collected.

**Shapes come from each provider's published API reference**, trimmed to the
fields each SDK needs to parse a reply. Specified by
``docs/design/tier2_execution.md`` section 7.15.
"""

import json
from dataclasses import dataclass
from typing import Any, Callable, Final, Optional

import httpx
import pytest

from execution import wire
from execution.adapters.registry import adapter_for

# THE CREDENTIAL EVERY CASE PLANTS. Long and unlike any real prefix, so a match
# in a record can only be this value.
PLANTED_KEY: Final[str] = "mqc-planted-credential-6c1f0e9a7b"

# WHERE A REQUEST SENT THROUGH A BARE RECORDER GOES. A reserved top-level
# domain, so it resolves nowhere even if a mock were bypassed.
ECHO_URL: Final[str] = "https://wire.test/v1/echo"

_CHAT_REPLY: Final[dict[str, Any]] = {
    "id": "chatcmpl-wire", "object": "chat.completion", "created": 0, "model": "grok-wire",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"},
                 "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}

_RESPONSES_REPLY: Final[dict[str, Any]] = {
    "id": "resp-wire", "object": "response", "created_at": 0, "model": "gpt-wire",
    "status": "completed", "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
    "output": [{"type": "message", "id": "msg-wire", "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "ok", "annotations": []}]}],
    "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2,
              "input_tokens_details": {"cached_tokens": 0},
              "output_tokens_details": {"reasoning_tokens": 0}},
}

_MESSAGES_REPLY: Final[dict[str, Any]] = {
    "id": "msg_wire", "type": "message", "role": "assistant", "model": "claude-wire",
    "content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn",
    "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1},
}

_GENERATE_REPLY: Final[dict[str, Any]] = {
    "candidates": [{"content": {"role": "model", "parts": [{"text": "ok"}]},
                    "finishReason": "STOP"}],
    "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1, "totalTokenCount": 2},
    "modelVersion": "gemini-wire",
}


@dataclass(frozen=True)
class WireEngine:
    """What a case needs to drive one engine's real SDK through a mock transport.

    Attributes:
        key_variable (str): The environment variable the SDK reads its key from.
        request (dict): A minimal request the adapter's ``dispatch`` accepts.
        credential_header (str): The header the SDK sends the key under, lower case.
        reply (dict): The JSON body of a successful reply.
    """

    key_variable: str
    request: dict[str, Any]
    credential_header: str
    reply: dict[str, Any]


WIRE_ENGINES: Final[dict[str, WireEngine]] = {
    "claude": WireEngine(
        "ANTHROPIC_API_KEY",
        {"model": "claude-wire", "max_tokens": 8,
         "messages": [{"role": "user", "content": "hi"}]},
        "x-api-key", _MESSAGES_REPLY,
    ),
    "gemini": WireEngine(
        "GEMINI_API_KEY", {"model": "gemini-wire", "contents": "hi"},
        "x-goog-api-key", _GENERATE_REPLY,
    ),
    "grok": WireEngine(
        "XAI_API_KEY",
        {"model": "grok-wire", "messages": [{"role": "user", "content": "hi"}]},
        "authorization", _CHAT_REPLY,
    ),
    "openai": WireEngine(
        "OPENAI_API_KEY", {"model": "gpt-wire", "input": "hi"},
        "authorization", _RESPONSES_REPLY,
    ),
}


def reply_handler(
    reply: dict[str, Any],
    *,
    failures: tuple[Any, ...] = (),
    headers: tuple[tuple[str, str], ...] = (),
    sent: Optional[list[httpx.Request]] = None,
) -> Callable[[httpx.Request], httpx.Response]:
    """Return a handler answering with each scripted failure in turn, then the reply.

    Args:
        reply (dict): The JSON body of the successful reply.
        failures (tuple): Each either an ``int`` status answered with an empty
            JSON body and ``retry-after-ms: 0``, so an SDK retries at once, or
            an exception instance, which the handler raises.
        headers (tuple): Response headers the successful reply carries.
        sent (list): Where every request received is appended, when given.

    Returns:
        Callable: The handler for ``httpx.MockTransport``.
    """
    pending = list(failures)

    def handle(request: httpx.Request) -> httpx.Response:
        """Answer one request.

        Args:
            request (httpx.Request): What the SDK sent.

        Returns:
            httpx.Response: The scripted answer.

        Raises:
            Exception: A scripted transport failure.
        """
        request.read()
        if sent is not None:
            sent.append(request)
        if pending:
            failure = pending.pop(0)
            if isinstance(failure, Exception):
                raise failure
            return httpx.Response(
                int(failure), headers={"retry-after-ms": "0"}, json={"error": {}}
            )
        return httpx.Response(200, headers=dict(headers), content=json.dumps(reply).encode())

    return handle


def serve_mock(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    """Make every recorder built from now on send through a mock transport.

    Args:
        monkeypatch (pytest.MonkeyPatch): pytest's patcher.
        handler (Any): The ``MockTransport`` handler.

    Returns:
        None
    """
    monkeypatch.setattr(wire, "base_transport", lambda: httpx.MockTransport(handler))


def mock_recorder(handler: Any, *, keep_body: bool = False,
                  environ: Optional[dict[str, str]] = None) -> wire.WireRecorder:
    """Return a recorder sending through a mock transport, reading the given environment.

    Args:
        handler (Any): The ``MockTransport`` handler.
        keep_body (bool): Whether the body is stored.
        environ (dict): The environment the by-value redaction reads; empty
            unless given, so only the by-name mechanism can act.

    Returns:
        wire.WireRecorder: The recorder.
    """
    recorder = wire.WireRecorder(keep_body=keep_body, environ=environ or {})
    recorder.inner = httpx.MockTransport(handler)
    return recorder


def send_through(recorder: wire.WireRecorder, **request: Any) -> None:
    """Send one request through a recorder's transport.

    Args:
        recorder (wire.WireRecorder): The recorder.
        **request (Any): ``httpx.Client.request`` arguments; ``method`` and
            ``url`` default to a POST to ``ECHO_URL``.

    Returns:
        None
    """
    with httpx.Client(transport=recorder.transport()) as client:
        client.request(request.pop("method", "POST"), request.pop("url", ECHO_URL), **request)


def dispatch_minimal(engine: str) -> Any:
    """Dispatch one engine's minimal request through its real adapter and SDK.

    Args:
        engine (str): The registered engine.

    Returns:
        Any: The adapter, holding its recorded attempts.
    """
    adapter = adapter_for(engine)()
    adapter.dispatch(dict(WIRE_ENGINES[engine].request))
    adapter.release()
    return adapter
