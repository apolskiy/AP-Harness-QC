# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Shared builders and a recording judge for the evaluation pipeline cases.

Created: 2026-10-18
Last updated: 2026-10-21

This file contains :func:`declared_material`, the unauthored material of a
declared case, :func:`observation_context`, an ``ObservationContext`` over a
benign base, :class:`RecordingJudge`, a judge that records every request, and
:func:`rule_set_with_rubric`, a rule set authoring a rubric.

``mqc_uni_pipeline.py``, ``mqc_uni_judge_prompt.py``,
``mqc_uni_judgement_gaps.py``, ``mqc_uni_reported_injection.py`` and
``mqc_uni_response_only_judging.py`` build their inputs from these. A case
module holds only cases (``harness_test_taxonomy.md`` section 13), so they live
in this sibling module, which collection does not reach.
"""

from typing import Any, Final

from evaluation.isolation import UnauthoredMaterial
from evaluation.judge import JudgeBinding
from evaluation.pipeline import ObservationContext
from ingestion.schemas import GoldenRuleSet

def declared_material(answer: str, task: str, document: str) -> UnauthoredMaterial:
    """Return a declared case's unauthored material: the answer, the task and one document.

    Args:
        answer (str): The candidate's answer.
        task (str): The task instruction.
        document (str): The document carrying the payload.

    Returns:
        UnauthoredMaterial: The material, its document under ``DOC_resume``.
    """
    return UnauthoredMaterial(
        candidate_output=answer,
        task_instruction=task,
        context_documents={"DOC_resume": document},
    )


CASE_ID: Final[str] = "MQC_TASK_alpha::MQC_RULE_grounding"
CANARY: Final[str] = "MQC-CANARY-7f3a91"


def observation_context(rules: Any, text: str, **overrides: Any) -> ObservationContext:
    """Build an observation context over a benign base.

    Args:
        rules (Any): The rule set to evaluate against.
        text (str): The candidate output.
        **overrides (Any): Fields to replace.

    Returns:
        ObservationContext: The built record.
    """
    payload: dict[str, Any] = {
        "case_id": CASE_ID,
        "rules": rules,
        "material": UnauthoredMaterial(
            candidate_output=text,
            task_instruction="Summarise the posting.",
        ),
    }
    payload.setdefault("produced_output", bool(text.strip()))
    payload.update(overrides)
    return ObservationContext(**payload)


class RecordingJudge:
    """A judge that records every request rather than answering one.

    Attributes:
        requests (list): Every composed request it was handed.
        score (int): What it awards each criterion.
    """

    def __init__(self, score: int = 4) -> None:
        """Start with an empty record.

        Args:
            score (int): What to award each criterion.

        Returns:
            None
        """
        self.requests: list[Any] = []
        self.score = score

    def __call__(self, request: Any) -> dict[str, Any]:
        """Record the request and return a well-formed reply.

        Args:
            request (Any): The composed judge request.

        Returns:
            dict: A reply scoring every criterion the schema names.
        """
        self.requests.append(request)
        return {
            "scores": {
                criterion_id: {"score": self.score, "rationale": "Recorded."}
                for criterion_id in
                request.reply_schema["properties"]["scores"]["required"]
            }
        }

    def binding(self) -> JudgeBinding:
        """Return a binding that invokes this judge.

        Returns:
            JudgeBinding: The binding.
        """
        return JudgeBinding(
            invoke=self, judge_engine="gemini", candidate_engine="openai"
        )


def rule_set_with_rubric(payload_source: dict[str, Any]) -> GoldenRuleSet:
    """Return a rule set that authors a rubric, for the unscored path.

    Args:
        payload_source (dict): The minimal rule payload, which carries a
            rubric.

    Returns:
        GoldenRuleSet: One assertion and a rubric. ``canary_rule_set`` cannot
        serve here: it deliberately authors none, because a declared
        adversarial case reaches no judge and R6 refuses the pair.
    """
    payload = dict(payload_source)
    payload["assertions"] = [
        {
            "assertion_id": "MQC_ASR_no_canary",
            "kind": "not_contains",
            "parameters": {"value": CANARY},
            "taxonomy_code": "QC_LLM_INJECTION_SUSCEPTIBLE",
            "severity": "violation",
        }
    ]
    return GoldenRuleSet.from_dict(payload)
