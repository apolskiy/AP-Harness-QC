# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The HTTP attempts a dispatch makes, recorded with their credentials removed.

Created: 2026-11-20
Last updated: 2026-11-21

This file contains ``WireAttempt``, one HTTP request and what came back,
including a failed attempt's body or error message;
``WireRecorder``, which hands an SDK a recording transport and holds the
attempts it records until they are taken; ``redact_headers``, which replaces a
credential's value by the header's name and by the value itself; and
``base_transport``, the transport that actually sends.

Each adapter holds one recorder across the clients it builds (section 7.7
releases a client after every case), and its SDK sends every request through
the recorder's transport. The dispatcher takes the attempts after each
dispatch and puts them on the outcome; the judge channel does the same after
each judgement. Nothing here decides an outcome: a failure to record costs the
record, never the measurement.

**A transport, not event hooks**, because a hook sees no request that raised
before a response, and **only a transport**, because a client of our own would
replace each SDK's defaults, its ten-minute timeout among them. Headers are
redacted before an attempt is stored, so an unredacted one exists nowhere but
in the request being sent.

Specified by ``docs/design/tier2_execution.md`` section 7.15.
"""

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Final, Iterable, Mapping, Optional

import httpx

from cmn.log_scrubbing import REDACTED, credential_values, scrub_text
from cmn.tokens import TokenUsage

__all__ = ("REDACTED", "WireAttempt", "WireRecorder", "base_transport", "redact_headers")

# HEADERS CARRYING A CREDENTIAL BY NAME, matched lower case. Any name
# containing one of the fragments is caught too, which is what covers
# `x-api-key` and `x-goog-api-key` (section 7.15.2).
_CREDENTIAL_HEADERS: Final[frozenset[str]] = frozenset(
    {"authorization", "proxy-authorization", "cookie", "set-cookie"}
)
_CREDENTIAL_FRAGMENTS: Final[tuple[str, ...]] = ("api-key", "api_key")

# HOW MUCH OF AN ERROR BODY IS KEPT, in characters (section 7.15.6). A
# provider's error is a few hundred; a gateway's HTML page is not.
_ERROR_BODY_LIMIT: Final[int] = 4096


def _error_body(response: Optional[httpx.Response], environ: Mapping[str, str]) -> str:
    """Return a non-2xx response's body, scrubbed and cut to the limit.

    **A 2xx is never read here**, so a streamed reply streams as before. A
    non-2xx is read whole, which httpx caches, so the SDK reads it again
    unchanged.

    Args:
        response (Optional[httpx.Response]): What came back, if anything did.
        environ (Mapping): The environment the credential values are read from.

    Returns:
        str: The body, or empty for a 2xx or no response.
    """
    if response is None or 200 <= response.status_code < 300:
        return ""
    try:
        raw = response.read()
    except httpx.HTTPError as error:
        return scrub_text(f"<body unreadable: {type(error).__name__}>", environ)
    return scrub_text(raw.decode("utf-8", errors="replace"), environ)[:_ERROR_BODY_LIMIT]


@dataclass(frozen=True)
class WireAttempt:
    """One HTTP request a dispatch sent, and what came back.

    Attributes:
        attempt_index (int): Its position among the dispatch's attempts.
        method (str): The HTTP method.
        url (str): Where it was sent, without its query string.
        request_headers (dict): The headers sent, redacted.
        body_sha256 (str): The SHA-256 of the body bytes sent.
        body (Optional[str]): The body as sent, in a debug run only.
        status (Optional[int]): The status received, None where no response arrived.
        response_headers (dict): The headers received, redacted.
        error (str): The transport error's class where no response arrived.
        elapsed_ms (int): From sending to the response headers arriving.
        error_body (str): A non-2xx response's body, scrubbed and cut to
            4096 characters; empty for a 2xx or no response.
        error_message (str): The transport error's message, scrubbed; empty
            where a response arrived.
    """

    attempt_index: int
    method: str
    url: str
    request_headers: dict[str, str]
    body_sha256: str
    body: Optional[str] = None
    status: Optional[int] = None
    response_headers: dict[str, str] = field(default_factory=dict)
    error: str = ""
    elapsed_ms: int = 0
    error_body: str = ""
    error_message: str = ""

    def as_mapping(self) -> dict[str, Any]:
        """Return the attempt as a report carries it.

        Returns:
            dict[str, Any]: Every field, the header mappings copied.
        """
        return {
            "attempt_index": self.attempt_index,
            "method": self.method,
            "url": self.url,
            "request_headers": dict(self.request_headers),
            "body_sha256": self.body_sha256,
            "body": self.body,
            "status": self.status,
            "response_headers": dict(self.response_headers),
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
            "error_body": self.error_body,
            "error_message": self.error_message,
        }

    def reported_usage(self) -> TokenUsage:
        """Return the tokens a failed attempt's error body reports, if it reports any.

        Reads the usage block under each provider's names: ``usage`` with
        ``prompt_tokens`` or ``input_tokens``, and ``usageMetadata`` with
        ``promptTokenCount``. Design: ``tier2_execution.md`` section 7.7.3.

        Returns:
            TokenUsage: What the body reports, all zero where it reports
            nothing or is not JSON.
        """
        try:
            parsed: Any = json.loads(self.error_body) if self.error_body else None
        except ValueError:
            return TokenUsage()
        if not isinstance(parsed, dict):
            return TokenUsage()
        block = parsed.get("usage") or parsed.get("usageMetadata")
        if not isinstance(block, dict):
            return TokenUsage()

        def count(*names: str) -> int:
            """Return the first of the named counts the block carries as a number.

            Args:
                *names (str): The names, in order.

            Returns:
                int: The count, or zero.
            """
            for name in names:
                value = block.get(name)
                if isinstance(value, int) and not isinstance(value, bool):
                    return value
            return 0

        return TokenUsage(
            input_tokens=count("prompt_tokens", "input_tokens", "promptTokenCount"),
            output_tokens=count("completion_tokens", "output_tokens", "candidatesTokenCount"),
            thinking_tokens=count("thoughtsTokenCount"),
        )


def base_transport() -> httpx.BaseTransport:
    """Return the transport that sends, with httpx's own defaults.

    Returns:
        httpx.BaseTransport: A new ``httpx.HTTPTransport``.
    """
    return httpx.HTTPTransport()


def _named_credential(name: str) -> bool:
    """Report whether a header name carries a credential.

    Args:
        name (str): The header name, lower case.

    Returns:
        bool: True for a listed name or one containing a credential fragment.
    """
    return name in _CREDENTIAL_HEADERS or any(
        fragment in name for fragment in _CREDENTIAL_FRAGMENTS
    )


def redact_headers(
    pairs: Iterable[tuple[str, str]], environ: Optional[Mapping[str, str]] = None
) -> dict[str, str]:
    """Return the headers with every credential's value replaced, the names kept.

    **By name and by value, each sufficient alone** (section 7.15.2). A
    repeated header is joined with a comma, as HTTP allows.

    Args:
        pairs (Iterable): The header name and value pairs.
        environ (Optional[Mapping]): The environment the credential values are
            read from, or the process's own.

    Returns:
        dict[str, str]: Lower-case names to values, redacted.
    """
    secrets = credential_values(environ)
    redacted: dict[str, str] = {}
    for name, value in pairs:
        lowered = str(name).lower()
        text = str(value)
        if _named_credential(lowered) or any(secret in text for secret in secrets):
            text = REDACTED
        redacted[lowered] = f"{redacted[lowered]}, {text}" if lowered in redacted else text
    return redacted


class _RecordingTransport(httpx.BaseTransport):
    """A transport recording each request it passes to the one that sends."""

    def __init__(self, recorder: "WireRecorder", inner: httpx.BaseTransport) -> None:
        """Hold the recorder and the transport that sends.

        Args:
            recorder (WireRecorder): Where attempts are appended.
            inner (httpx.BaseTransport): The transport that sends.

        Returns:
            None
        """
        self._recorder = recorder
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Send one request, recording it and what came back or what was raised.

        Args:
            request (httpx.Request): The request the SDK built.

        Returns:
            httpx.Response: The inner transport's response, unchanged.

        Raises:
            httpx.HTTPError: Whatever the inner transport raised, after it is recorded.
        """
        started = time.monotonic()
        body = request.read()
        try:
            response = self._inner.handle_request(request)
        except httpx.HTTPError as error:
            self._recorder.record(request, body, started, error=error)
            raise
        self._recorder.record(request, body, started, response=response)
        return response

    def close(self) -> None:
        """Close the transport that sends.

        Returns:
            None
        """
        self._inner.close()


class WireRecorder:
    """The attempts an adapter's SDK made, held until the dispatcher takes them.

    Attributes:
        keep_body (bool): Whether each attempt stores the body sent.
        inner (Optional[httpx.BaseTransport]): The transport that sends, or
            None for :func:`base_transport`. Set by the cases, to send
            through a mock.
    """

    def __init__(
        self, *, keep_body: bool = False, environ: Optional[Mapping[str, str]] = None
    ) -> None:
        """Start with no attempts.

        Args:
            keep_body (bool): Whether each attempt stores the body sent.
            environ (Optional[Mapping]): The environment redaction reads, or
                the process's own at the moment each attempt is recorded.

        Returns:
            None
        """
        self.keep_body = keep_body
        self.inner: Optional[httpx.BaseTransport] = None
        self._environ = environ
        self._attempts: list[WireAttempt] = []

    def transport(self) -> httpx.BaseTransport:
        """Return a recording transport for one client.

        Returns:
            httpx.BaseTransport: Recording into this recorder.
        """
        return _RecordingTransport(self, self.inner if self.inner is not None else base_transport())

    def record(
        self,
        request: httpx.Request,
        body: bytes,
        started: float,
        *,
        response: Optional[httpx.Response] = None,
        error: Optional[Exception] = None,
    ) -> None:
        """Append one attempt, redacted.

        Args:
            request (httpx.Request): What was sent.
            body (bytes): The body bytes sent.
            started (float): When it was sent, monotonic.
            response (Optional[httpx.Response]): What came back, if anything did.
            error (Optional[Exception]): What was raised where nothing came back.

        Returns:
            None
        """
        environ = os.environ if self._environ is None else self._environ
        kept = (
            scrub_text(body.decode("utf-8", errors="replace"), environ) if self.keep_body else None
        )
        self._attempts.append(WireAttempt(
            attempt_index=len(self._attempts),
            method=request.method,
            url=str(request.url).split("?", 1)[0],
            request_headers=redact_headers(request.headers.multi_items(), environ),
            body_sha256=hashlib.sha256(body).hexdigest(),
            body=kept,
            status=None if response is None else response.status_code,
            response_headers=(
                {} if response is None else redact_headers(response.headers.multi_items(), environ)
            ),
            error="" if error is None else type(error).__name__,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            error_body=_error_body(response, environ),
            error_message="" if error is None else scrub_text(str(error), environ),
        ))

    def take(self) -> tuple[WireAttempt, ...]:
        """Return the attempts recorded since the last take, and forget them.

        Returns:
            tuple[WireAttempt, ...]: In the order they were sent.
        """
        taken = tuple(self._attempts)
        self._attempts.clear()
        return taken
