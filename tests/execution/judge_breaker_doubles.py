# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Doubles for driving a live judge channel through a scripted provider.

Created: 2026-11-06
Last updated: 2026-11-11

This file contains a judge request double, a provider that answers from a
script and counts what reached it, a builder for a live gemini channel wired
to that provider, and the two provider failures the breaker cases raise.

**Used by** ``tests/execution/mqc_uni_judge_breaker.py``, whose cases check
when a judge channel stops asking a judge that will not answer, and
``tests/execution/mqc_uni_judge_usage.py``, whose case checks the usage line
each live judgement logs. Kept out of the case modules because collection reads
only cases there.

Specified by ``docs/design/tier2_execution.md`` section 8.3.3.
"""

from typing import Any

import pytest
from google.genai import errors as genai_errors

from execution.judge_channel import JudgeChannel
from tests.execution.provider_doubles import gemini_judgement

MODEL: str = "gemini-4-argon"
AWARDED: dict[str, Any] = {"scores": {"C_ONE": {"score": 4, "rationale": "Mostly."}}}


class JudgeRequestDouble:
    """The shape a judge request presents to a channel.

    Attributes:
        case_id (str): The case being judged.
        reply_schema (dict): What the judge must reply in.
        observation_index (int): Which observation this is.
    """

    case_id = "MQC_TASK_alpha::MQC_RULE_grounding"
    reply_schema: dict[str, Any] = {"type": "object"}
    observation_index = 0

    def rendered(self) -> str:
        """Return the composed prompt.

        Returns:
            str: The prompt text.
        """
        return "Score the response against the rubric."


class ScriptedJudge:
    """A judge provider answering from a script, counting what it was sent.

    Attributes:
        script (list): One entry per call, an exception to raise or a reply.
        sent (int): How many requests reached it.
    """

    def __init__(self, script: list[Any]) -> None:
        """Hold the script.

        Args:
            script (list): What each successive call does.

        Returns:
            None
        """
        self.script = list(script)
        self.sent = 0

    def dispatch(self, request: Any) -> Any:
        """Answer one request from the script, or award once the script is spent.

        Bound to one provider, so it replaces the adapter's ``dispatch``
        directly and receives only the composed request.

        Args:
            request (Any): The composed request, unused.

        Returns:
            Any: The scripted reply.

        Raises:
            Exception: The scripted failure.
        """
        assert request is not None
        self.sent += 1
        entry = self.script.pop(0) if self.script else gemini_judgement(AWARDED)
        if isinstance(entry, Exception):
            _fail(entry)
        return entry


def _fail(error: Exception) -> None:
    """Raise a scripted provider failure.

    Args:
        error (Exception): The failure.

    Returns:
        None

    Raises:
        Exception: Always, the failure given.
    """
    raise error


def scripted_channel(monkeypatch: pytest.MonkeyPatch, provider: ScriptedJudge) -> JudgeChannel:
    """Return a live gemini judge channel whose provider is the script.

    Args:
        monkeypatch (pytest.MonkeyPatch): pytest's patcher.
        provider (ScriptedJudge): The scripted provider.

    Returns:
        JudgeChannel: The channel.
    """
    channel = JudgeChannel("gemini", model=MODEL)
    monkeypatch.setattr(channel.adapter, "dispatch", provider.dispatch)
    return channel


def rejected() -> Exception:
    """Return the 400 a provider sends for a request it will never accept.

    Returns:
        Exception: The failure, which maps to ``QC_HARNESS_REQUEST_REJECTED``.
    """
    return genai_errors.ClientError(code=400, response_json={"error": {"code": 400}})


def busy() -> Exception:
    """Return the 503 a busy provider sends.

    Returns:
        Exception: The failure, which maps to ``QC_HARNESS_PROVIDER_UNAVAILABLE``.
    """
    return genai_errors.ServerError(code=503, response_json={"error": {"code": 503}})
