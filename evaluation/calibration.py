# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Calibration: whether the judge still means what the anchors say.

Specified by ``docs/design/tier3_evaluation.md`` section 9.

**An anchor states what a level means; an exemplar shows it.** This module sends
each exemplar through the judge and compares the returned score to the level the
exemplar was written for.

**Deviation is recorded even when it passes.** A rubric drifting steadily by one
level looks healthy on any single run and obvious across twenty, and only the
record makes the second view possible.

**Calibration runs on the schedule, not on pull requests**, because it requires
live judge invocation and would otherwise spend quota on every change.
"""

import logging
from dataclasses import dataclass
from typing import Final, Optional

logger = logging.getLogger(__name__)

# One level of deviation is tolerated and recorded. Two is a failure: an anchor
# and a judge disagreeing by two levels on a five-point scale are not applying
# the same rubric at all.
_TOLERANCE: Final[int] = 1


@dataclass(frozen=True)
class CalibrationResult:
    """One exemplar, judged and compared to the level it was written for.

    Attributes:
        criterion_id (str): Which criterion the exemplar belongs to.
        intended_level (int): The anchor level it exemplifies.
        observed_score (float): What the judge awarded.
        deviation (float): Absolute distance between the two.
        passed (bool): Whether the deviation is within tolerance.
    """

    criterion_id: str
    intended_level: int
    observed_score: float
    deviation: float
    passed: bool

    @property
    def exact(self) -> bool:
        """Report whether the judge landed on the intended level.

        Returns:
            bool: True on an exact match.
        """
        return self.deviation == 0

    @property
    def drifted_within_tolerance(self) -> bool:
        """Report a pass that nonetheless deviated.

        Returns:
            bool: True when the result passed but was not exact. **This is the
            trend signal.** A run of these is what distinguishes a rubric
            drifting steadily from one that is stable, and neither looks
            different on a single run.
        """
        return self.passed and not self.exact


def compare_to_anchor(
    criterion_id: str, intended_level: int, observed_score: float
) -> CalibrationResult:
    """Compare one judged exemplar to the level it was written for.

    Args:
        criterion_id (str): Which criterion.
        intended_level (int): The anchor level the exemplar exemplifies.
        observed_score (float): What the judge awarded.

    Returns:
        CalibrationResult: Exact and one-level deviations pass; more than one
        level fails, because the rubric or the judge has drifted far enough
        that scores from it cannot be compared with earlier ones.
    """
    deviation = abs(float(observed_score) - float(intended_level))
    passed = deviation <= _TOLERANCE
    if not passed:
        logger.error(
            "Calibration failed on %s: level %d exemplar scored %s",
            criterion_id, intended_level, observed_score,
        )
    elif deviation > 0:
        logger.info(
            "Calibration on %s deviated by %s within tolerance, recorded for trend",
            criterion_id, deviation,
        )
    return CalibrationResult(
        criterion_id=criterion_id,
        intended_level=intended_level,
        observed_score=float(observed_score),
        deviation=deviation,
        passed=passed,
    )


def calibrate_rubric(rubric: object, observed: dict[str, dict[int, float]]) -> list:
    """Compare every anchored exemplar in a rubric to what the judge awarded.

    Args:
        rubric (object): The rubric whose anchors carry exemplars.
        observed (dict): Criterion identifier to level to the observed score.

    Returns:
        list[CalibrationResult]: One result per exemplar that exists and was
        judged. **An anchor carrying no exemplar yields no result**, rather than
        a passing one: nothing was measured, and a manufactured pass would make
        an uncalibrated rubric look verified.
    """
    results: list[CalibrationResult] = []
    for criterion in getattr(rubric, "criteria", []):
        scored = observed.get(criterion.criterion_id, {})
        for level in sorted(criterion.anchors):
            if criterion.anchors[level].exemplar is None or level not in scored:
                continue
            results.append(compare_to_anchor(criterion.criterion_id, level, scored[level]))
    return results


def tolerance() -> int:
    """Return the deviation tolerated before calibration fails.

    Returns:
        int: One level.
    """
    return _TOLERANCE


def observation_variance(scores: list[float]) -> Optional[float]:
    """Return the spread across A4's repeat observations.

    **High variance on identical input means the anchors are not
    discriminating**, which is a drift signal needing no new machinery: the
    three observations already exist.

    Args:
        scores (list): One score per observation.

    Returns:
        Optional[float]: The range between the highest and lowest, or ``None``
        with fewer than two observations, where spread is undefined rather than
        zero. Reporting zero would make a single observation look maximally
        consistent.
    """
    if len(scores) < 2:
        return None
    return max(scores) - min(scores)
