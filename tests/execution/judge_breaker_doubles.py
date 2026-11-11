# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Doubles for driving a live judge channel through a scripted provider.

Created: 2026-11-06
Last updated: 2026-11-11

This file contains a judge request double, a provider that answers from a
script and counts what reached it, a builder for a live gemini channel wired
to that provider, the two provider failures the breaker cases raise, a
judgement reporting the priced judge model, and a priced run session with a
ceiling.

**Used by** ``tests/execution/mqc_uni_judge_breaker.py``, whose cases check
when a judge channel stops asking a judge that will not answer, and
``tests/execution/mqc_uni_judge_usage.py``, whose cases check the usage line
each live judgement logs and what the judge spends against the run's ceiling.
Kept out of the case modules because collection reads
only cases there.

Specified by ``docs/design/tier2_execution.md`` section 8.3.3.
"""

import json
from datetime import date
from pathlib import Path
from typing import Any, Optional

import pytest
from google.genai import errors as genai_errors

from cmn.pricing import load_price_table
from execution.dispatch import DispatchSession
from execution.judge_channel import JudgeChannel, JudgementPlan
from tests.execution.provider_doubles import gemini_judgement, gemini_response

MODEL: str = "gemini-4-argon"
AWARDED: dict[str, Any] = {"scores": {"C_ONE": {"score": 4, "rationale": "Mostly."}}}
PRICING: Path = Path(__file__).resolve().parents[2] / "config" / "pricing.yaml"
# A DATE INSIDE THE JUDGE MODEL'S FIRST PRICED WINDOW, injected for the reason
# the verdict injects its date.
PRICED_ON: date = date(2026, 11, 10)


def priced_judgement() -> Any:
    """Return a judgement double whose reply reports serving the priced judge model.

    Returns:
        Any: A Gen AI response carrying the awarded judgement.
    """
    return gemini_response(text=json.dumps(AWARDED), resolved_model=MODEL)


def run_budget(ceiling: float) -> DispatchSession:
    """Return a run session with a ceiling, priced from the shipped table.

    Args:
        ceiling (float): The run's ``--max-spend``.

    Returns:
        DispatchSession: The session a judge channel spends against.
    """
    return DispatchSession(
        max_spend=ceiling, prices=load_price_table(PRICING), priced_on=PRICED_ON,
    )


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


def scripted_channel(
    monkeypatch: pytest.MonkeyPatch,
    provider: ScriptedJudge,
    budget: Optional[DispatchSession] = None,
) -> JudgeChannel:
    """Return a live gemini judge channel whose provider is the script.

    Args:
        monkeypatch (pytest.MonkeyPatch): pytest's patcher.
        provider (ScriptedJudge): The scripted provider.
        budget (Optional[DispatchSession]): The run's session the channel
            spends against, or none.

    Returns:
        JudgeChannel: The channel.
    """
    channel = JudgeChannel("gemini", model=MODEL, plan=JudgementPlan(budget=budget))
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
