# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Checks whether the LLM judge still scores each rubric exemplar at the level it shows.

Created: 2026-09-26
Last updated: 2026-11-11

This file contains ``calibrate``, which sends every exemplar of a rule's
rubric to a judge and returns a :class:`CalibrationResult` for each;
``calibration_requests``, which composes those judge requests as
:class:`CalibrationRequest` records; ``calibrate_rubric``, which compares
scores already obtained; ``compare_to_anchor``, which compares one score to
its intended level and passes it within ``tolerance``, one level; and
``observation_variance``, the spread across a case's repeat observations.

**Calibration sits beside the graded run rather than inside it.** A consumer
calls ``calibrate`` with a rule's rubric, the material its graded request
carries and the judge's ``invoke``. A failed result means the judge or the
rubric has drifted, so scores from it cannot be compared with earlier ones.
No step of the evaluation pipeline calls this file.

Specified by ``docs/design/tier3_evaluation.md`` sections 9 and 9.1.

**An anchor states what a level means; an exemplar shows it.** Each exemplar
is sent through the judge, and this module compares the returned score to the
level the exemplar was written for.

**Deviation is recorded even when it passes.** A rubric drifting steadily by one
level looks healthy on any single run and obvious across twenty, and only the
record makes the second view possible.

**Calibration runs on the schedule, not on pull requests**, because it requires
live judge invocation and would otherwise spend quota on every change.
"""

import logging
from dataclasses import dataclass, replace
from typing import Any, Callable, Final, Optional

from evaluation.isolation import JudgeRequest, UnauthoredMaterial, compose_judge_request
from evaluation.judge import JudgeBinding, validate_judge_reply

logger = logging.getLogger(__name__)

# One level of deviation is tolerated and recorded. Two is a failure: an anchor
# and a judge disagreeing by two levels on a five-point scale are not applying
# the same rubric at all.
_TOLERANCE: Final[int] = 1

# The prefix on a calibration request's task, which no graded judgement's task
# carries, so a recording judge stores the two apart (design section 9.1.1).
_CALIBRATION_PREFIX: Final[str] = "calibration."


@dataclass(frozen=True)
class CalibrationRequest:
    """One exemplar, composed as a judge request.

    Attributes:
        criterion_id (str): The criterion the exemplar shows.
        intended_level (int): The anchor level it was written for.
        judge_request (JudgeRequest): What the judge is sent.
    """

    criterion_id: str
    intended_level: int
    judge_request: JudgeRequest


@dataclass(frozen=True)
class _OneCriterion:
    """A rubric narrowed to one criterion, which is all composition reads.

    Attributes:
        criteria (list): The single criterion.
    """

    criteria: list[Any]


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


def calibration_case_id(case_id: str, criterion_id: str) -> str:
    """Return the identifier a calibration request is judged and stored under.

    Design: ``tier3_evaluation.md`` section 9.1.1.

    Args:
        case_id (str): The rule's graded case identifier, ``<task>::<rule>``.
        criterion_id (str): The criterion the exemplar shows.

    Returns:
        str: ``calibration.<task>::<rule>.<criterion>``, whose task part no
        graded judgement shares.
    """
    task_id, _, rule_id = case_id.partition("::")
    return f"{_CALIBRATION_PREFIX}{task_id}::{rule_id or '_'}.{criterion_id}"


def calibration_requests(
    case_id: str, rubric: Any, material: UnauthoredMaterial
) -> list[CalibrationRequest]:
    """Compose one judge request for every anchor that carries an exemplar.

    Design: ``tier3_evaluation.md`` section 9.1.

    Args:
        case_id (str): The rule's graded case identifier, ``<task>::<rule>``.
        rubric (Any): The rule's ``Rubric``.
        material (UnauthoredMaterial): What the rule's graded request carries.
            Its candidate output is replaced by each exemplar in turn.

    Returns:
        list[CalibrationRequest]: In rubric order, then level order. Each
        request carries the exemplar as the candidate output, the rule's
        other material unchanged, the exemplar's criterion alone, and the
        level as its observation index. An anchor without an exemplar yields
        none.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when an exemplar reached
            the instruction text, as ``compose_judge_request`` refuses.
    """
    requests: list[CalibrationRequest] = []
    for criterion in rubric.criteria:
        narrowed = _OneCriterion(criteria=[criterion])
        for level in sorted(criterion.anchors):
            exemplar = criterion.anchors[level].exemplar
            if exemplar is None:
                continue
            judge_request = compose_judge_request(
                calibration_case_id(case_id, criterion.criterion_id),
                narrowed,
                replace(material, candidate_output=exemplar),
                observation_index=level,
            )
            requests.append(CalibrationRequest(
                criterion_id=criterion.criterion_id,
                intended_level=level,
                judge_request=judge_request,
            ))
    return requests


def calibrate(
    case_id: str,
    rubric: Any,
    material: UnauthoredMaterial,
    invoke: Callable[[Any], Any],
    *,
    judge_engine: str = "",
) -> list[CalibrationResult]:
    """Send every exemplar of a rule's rubric to a judge and compare the scores.

    Design: ``tier3_evaluation.md`` section 9.1.

    Args:
        case_id (str): The rule's graded case identifier, ``<task>::<rule>``.
        rubric (Any): The rule's ``Rubric``.
        material (UnauthoredMaterial): What the rule's graded request carries.
        invoke (Callable): The judge, called once per exemplar with the
            composed request and returning its reply.
        judge_engine (str): Which engine judges, recorded on each reply.

    Returns:
        list[CalibrationResult]: One per exemplar, in rubric order, then level
        order.

    Raises:
        JudgeHijackSuspected: When a reply is out of shape or off the scale,
            as ``validate_judge_reply`` refuses a graded one.
        ValueError: When the judge could not be reached, as ``invoke`` raises,
            or a reply omits the criterion.
    """
    binding = JudgeBinding(invoke=invoke, judge_engine=judge_engine)
    observed: dict[str, dict[int, float]] = {}
    for item in calibration_requests(case_id, rubric, material):
        request = item.judge_request
        reply = validate_judge_reply(
            invoke(request),
            _OneCriterion(criteria=[_criterion(rubric, item.criterion_id)]),
            binding,
            case_id=request.case_id,
            observation_index=request.observation_index,
        )
        observed.setdefault(item.criterion_id, {})[item.intended_level] = (
            reply.scores[0].score
        )
    return calibrate_rubric(rubric, observed)


def uncalibrated_message(family: str, failures: list[str]) -> str:
    """Return the report for a family whose exemplars the judge placed off their levels.

    Design: ``tier3_evaluation.md`` section 9.3.

    Args:
        family (str): The rubric family calibrated.
        failures (list[str]): One line per exemplar that missed, naming its
            case, criterion, level and score.

    Returns:
        str: The message, led by ``QC_HARNESS_JUDGE_UNCALIBRATED``.
    """
    return (
        f"QC_HARNESS_JUDGE_UNCALIBRATED: the judge placed {len(failures)} {family} "
        f"exemplar(s) more than one level from the level each was written for: "
        + "; ".join(failures)
    )


def _criterion(rubric: Any, criterion_id: str) -> Any:
    """Return one criterion of a rubric by identifier.

    Args:
        rubric (Any): The rubric.
        criterion_id (str): Which criterion.

    Returns:
        Any: The criterion.
    """
    return next(
        criterion for criterion in rubric.criteria if criterion.criterion_id == criterion_id
    )


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
