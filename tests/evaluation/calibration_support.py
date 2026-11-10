# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""A rubric with exemplars, a rule's material, and a stand-in judge, for calibration cases.

Created: 2026-11-10
Last updated: 2026-11-10

This file contains ``EXEMPLARS``, the exemplars of a two-criterion rubric;
:func:`calibration_rubric`, which builds that rubric with the second criterion
carrying no level 3 exemplar; :func:`rule_material`, the material a rule's
graded request carries; and :class:`StandInJudge`, a judge scoring every
requested criterion by a rule and keeping each request it received.

``mqc_uni_calibration.py`` uses them to send exemplars through
``evaluation.calibration.calibrate`` without calling a provider.

**The judge reads the criteria out of the request**, as
``judge_doubles.scoring_judge`` does, so a request carrying the wrong schema
produces a ``KeyError`` here instead of a passing case.
"""

from typing import Any, Callable

from evaluation.isolation import UnauthoredMaterial
from ingestion.schemas import Rubric

# TWO CRITERIA, AND THE SECOND HAS NO EXEMPLAR AT LEVEL 3, so a case can tell
# one request per exemplar from one per anchor.
EXEMPLARS: dict[str, dict[int, str]] = {
    "C_SOURCE": {
        1: "The report covers five regions, and Antarctica leads at 90 million.",
        3: "Three regions are named; the fourth is probably near 20 million.",
        5: "The report names three regions and states no figure for any other.",
    },
    "C_ARITHMETIC": {
        1: "The total is 140 million, with no working shown.",
        5: "41.2 plus 38.0 plus 21.5 is 100.7 million, as the report states.",
    },
}


def calibration_rubric() -> Rubric:
    """Build a rubric whose anchors carry ``EXEMPLARS``.

    Returns:
        Rubric: Two criteria; the second carries no level 3 exemplar.
    """
    criteria = []
    for criterion_id, exemplars in EXEMPLARS.items():
        anchors: dict[int, dict[str, str]] = {}
        for level in (1, 3, 5):
            anchors[level] = {"description": f"{criterion_id} at level {level}"}
            if level in exemplars:
                anchors[level]["exemplar"] = exemplars[level]
        criteria.append({
            "criterion_id": criterion_id,
            "name": criterion_id,
            "description": f"Whether the response meets {criterion_id}",
            "anchors": anchors,
        })
    return Rubric.from_dict({"criteria": criteria, "threshold": 3.0})


def rule_material() -> UnauthoredMaterial:
    """Return the material the rule's graded request carries.

    Returns:
        UnauthoredMaterial: A task, a system instruction and one document.
    """
    return UnauthoredMaterial(
        candidate_output="",
        task_instruction="Summarize regional revenue using only the report.",
        context_documents={"report": "North America 41.2, EMEA 38.0, APAC 21.5."},
        system_instruction="Answer from the supplied report only.",
    )


class StandInJudge:
    """A judge that scores every requested criterion by a rule, and counts.

    Attributes:
        calls (list): Every request it received, in order.
    """

    def __init__(self, score_for: Callable[[int], int]) -> None:
        """Hold the scoring rule.

        Args:
            score_for (Callable): Called with the request's observation index,
                which a calibration request sets to the exemplar's level,
                returning the score awarded.

        Returns:
            None
        """
        self._score_for = score_for
        self.calls: list[Any] = []

    def __call__(self, request: Any) -> dict[str, Any]:
        """Score one request.

        Args:
            request (Any): The composed judge request.

        Returns:
            dict: A reply in the shape the reply schema requires.
        """
        self.calls.append(request)
        score = self._score_for(request.observation_index)
        return {"scores": {
            criterion_id: {"score": score, "rationale": "ok"}
            for criterion_id in request.reply_schema["properties"]["scores"]["required"]
        }}
