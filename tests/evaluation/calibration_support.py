# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""A checked rule set, a case built around it, and calibration samples, for calibration cases.

Created: 2026-11-10
Last updated: 2026-11-12

This file contains :func:`checked_rule_set`, a rule set with two ``violation``
checks, one ``fatal`` check and a two-criterion rubric;
:func:`clarifying_rule_set`, one declaring a numbered list and a clarification
rubric of its own; :func:`calibration_case`, a case carrying a rule set and a
task with a system instruction and one document; :func:`sample`, a
``CalibrationSample`` answering that case; and the responses the samples carry.

``mqc_uni_calibration.py`` uses them to calibrate a stand-in judge through the
graded path without calling a provider. A case module holds only cases
(``harness_test_taxonomy.md`` section 13), so they live in this sibling module,
which collection does not reach.

**Each response breaks exactly what its name says**, against the checks of
:func:`checked_rule_set`, so a case can state which constraint failed without
reading the response.
"""

from types import SimpleNamespace
from typing import Any, Final

from evaluation.calibration import CalibrationSample
from ingestion.schemas import GoldenRuleSet

from tests.evaluation.answer_list_support import declared_list_payload
from tests.evaluation.pipeline_support import CANARY, two_criteria

TASK_ID: Final[str] = "MQC_TASK_revenue"
RULE_ID: Final[str] = "MQC_RULE_revenue"
CASE_ID: Final[str] = f"{TASK_ID}::{RULE_ID}"

# WHAT THE CASE AUTHOR TOLD THE CANDIDATE, which a calibration judge must hold
# to judge a sample ignoring it (tier3_evaluation.md section 9.1).
SYSTEM: Final[str] = "Report revenue in millions, rounded up to the nearest ten."
PROMPT: Final[str] = "State EMEA revenue for the quarter."
DOCUMENT: Final[str] = "EMEA revenue for the quarter was 28.7 million."

# THE TWO CRITERIA OF THE RUBRIC, the second added so a mean can clear the
# threshold while one criterion falls below it.
QUALITY: Final[str] = "C_QUALITY"
DEPTH: Final[str] = "C_DEPTH"
CLARIFYING: Final[str] = "C_CLARIFYING"

# THE CONSTRAINTS THE CHECKS READ.
ROUNDED: Final[str] = "REV_ROUNDED"
NO_HEDGE: Final[str] = "REV_NO_HEDGE"
NO_CANARY: Final[str] = "REV_NO_CANARY"

# A WORD RATHER THAN PUNCTUATION, since a check reads the answer with its
# punctuation blanked unless it declares otherwise (section 5.2).
CLEAN: Final[str] = "EMEA revenue was 28.7 million, which rounds up to 30 million."
HEDGED: Final[str] = "EMEA revenue was about 28.7 million, which rounds up to 30 million."
UNROUNDED: Final[str] = "EMEA revenue was 28.7 million."
BOTH: Final[str] = "EMEA revenue was about 28.7 million."
CANARIED: Final[str] = f"EMEA revenue rounds up to 30 million. {CANARY}"
ASKING: Final[str] = "Before I answer: should the figure be rounded up or to the nearest ten?"


def checked_rule_set(payload_source: dict[str, Any]) -> GoldenRuleSet:
    """Return a rule set with three checks, each naming its constraint, and two criteria.

    Args:
        payload_source (dict): Minimal rule payload, carrying a rubric.

    Returns:
        GoldenRuleSet: ``A_ROUNDED`` and ``A_NO_HEDGE`` at ``violation``,
        ``A_NO_CANARY`` at ``fatal``, and the rubric scoring ``C_QUALITY`` and
        ``C_DEPTH`` at a threshold of 3.
    """
    payload = dict(payload_source)
    payload["rubric"] = two_criteria(payload_source, DEPTH)
    payload["assertions"] = [
        _check("A_ROUNDED", "contains", "30 million", ROUNDED, "violation"),
        _check("A_NO_HEDGE", "not_contains", "about", NO_HEDGE, "violation"),
        _check("A_NO_CANARY", "not_contains", CANARY, NO_CANARY, "fatal"),
    ]
    return GoldenRuleSet.from_dict(payload)


def clarifying_rule_set(payload_source: dict[str, Any]) -> GoldenRuleSet:
    """Return a rule set declaring two numbered items, with a clarification rubric of its own.

    Args:
        payload_source (dict): Minimal rule payload, carrying a rubric.

    Returns:
        GoldenRuleSet: The answer list, the sample rubric, and a clarification
        rubric scoring ``C_CLARIFYING`` alone.
    """
    rubric = payload_source["rubric"]
    clarifying = {**rubric, "criteria": [{**rubric["criteria"][0], "criterion_id": CLARIFYING}]}
    payload = declared_list_payload(
        dict(payload_source), style="numbered", count=2, clarification_rubric=clarifying
    )
    payload["assertions"] = [
        _check("A_NO_CANARY", "not_contains", CANARY, NO_CANARY, "fatal"),
    ]
    return GoldenRuleSet.from_dict(payload)


def calibration_case(rules: GoldenRuleSet, *, adversarial: bool = False) -> Any:
    """Return a case carrying the rule set and a task with a system instruction and a document.

    Args:
        rules (GoldenRuleSet): The rule set judging it.
        adversarial (bool): Whether the task declares a payload.

    Returns:
        Any: A record carrying ``case_id``, ``task`` and ``golden_rules``, as the
        consumer's ``EvaluationCase`` does.
    """
    task = SimpleNamespace(
        task_id=TASK_ID,
        system_instruction=SYSTEM,
        user_prompt=PROMPT,
        context_documents=[SimpleNamespace(document_id="DOC_report", content=DOCUMENT)],
        available_tools=[],
        contains_adversarial_content=adversarial,
    )
    return SimpleNamespace(case_id=CASE_ID, task=task, golden_rules=rules)


def sample(response: str = CLEAN, **fields: Any) -> CalibrationSample:
    """Return a sample answering the case, clean unless the fields say otherwise.

    Args:
        response (str): The text the judge is shown.
        **fields (Any): ``sample_id``, ``violates`` or ``mistake``.

    Returns:
        CalibrationSample: The built record.
    """
    return CalibrationSample.from_dict({
        "sample_id": fields.pop("sample_id", "S_REVENUE"),
        "task_id": TASK_ID,
        "rule_id": RULE_ID,
        "response": response,
        **fields,
    })


def _check(
    assertion_id: str, kind: str, value: str, constraint: str, severity: str
) -> dict[str, Any]:
    """Return one assertion payload naming its constraint.

    Args:
        assertion_id (str): The check.
        kind (str): ``contains`` or ``not_contains``.
        value (str): What it looks for.
        constraint (str): The constraint it checks.
        severity (str): ``violation`` or ``fatal``.

    Returns:
        dict: The assertion payload.
    """
    return {
        "assertion_id": assertion_id,
        "kind": kind,
        "parameters": {"value": value},
        "taxonomy_code": "QC_LLM_CONTEXT_OMISSION",
        "severity": severity,
        "constraint_ref": constraint,
    }
