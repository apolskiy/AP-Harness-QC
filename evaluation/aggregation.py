# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Aggregation strategies, each declaring the scale it produces.

Specified by ``docs/design/tier3_evaluation.md`` sections 8 and 10.

**Scores across different scale identifiers are not comparable.** A strategy
declares its scale, which is emitted with the result, making incomparability a
machine-checkable fact rather than a convention someone has to remember.

**Scores are recorded for passes as well as failures.** A pass at 3.1 against a
3.0 threshold is a materially different signal from a pass at 4.8, and that
distinction disappears if only failures carry scores.

**Registration enrols a strategy in its conformance battery automatically**
(``harness_extensibility_standard.md`` section 10). The battery asserts that a strategy
declares a scale, is deterministic for identical input, and handles both a
single criterion and an empty-after-filtering set.
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Final, Optional

from cmn.registries import aggregation_scale, registered_aggregation_strategies

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CriterionScore:
    """One criterion's score, with the weight it carries.

    Attributes:
        criterion_id (str): Which criterion.
        score (float): What the judge awarded.
        weight (float): Its weight within the rubric.
    """

    criterion_id: str
    score: float
    weight: float = 1.0


@dataclass(frozen=True)
class AggregateScore:
    """One rubric's aggregated result, carrying the scale it is on.

    Attributes:
        value (Optional[float]): The aggregated score, absent only when
            nothing survived filtering.
        scale_id (str): The scale this number lives on. **Emitted with the
            result**, so a consumer comparing two scores can tell mechanically
            whether it may.
        strategy (str): Which registered strategy produced it.
        criterion_count (int): How many criteria contributed.
        passed (Optional[bool]): Whether it cleared the threshold, absent when
            there is no value to compare.
    """

    value: Optional[float]
    scale_id: str
    strategy: str
    criterion_count: int
    passed: Optional[bool] = None

    @property
    def evaluated(self) -> bool:
        """Report whether a score was actually produced.

        Returns:
            bool: True when a value exists. **Absent is not zero**: a missing
            score and a score of zero are different facts, and conflating them
            would let a diagnostic gap read as a quality finding.
        """
        return self.value is not None


def _weighted_mean(scores: list[CriterionScore], parameters: dict[str, Any]) -> float:
    """Combine scores in proportion to their weights.

    Args:
        scores (list): The criterion scores, never empty.
        parameters (dict): Unused by this strategy.

    Returns:
        float: The weighted mean.
    """
    del parameters
    total_weight = sum(entry.weight for entry in scores)
    if total_weight == 0:
        # Every weight zero is a rubric that declared no criterion matters. The
        # unweighted mean is the only answer that is not a division by zero and
        # not a silent zero, which would read as a quality finding.
        return _unweighted_mean(scores, {})
    return sum(entry.score * entry.weight for entry in scores) / total_weight


def _unweighted_mean(scores: list[CriterionScore], parameters: dict[str, Any]) -> float:
    """Combine scores with every criterion counting once.

    Args:
        scores (list): The criterion scores, never empty.
        parameters (dict): Unused by this strategy.

    Returns:
        float: The arithmetic mean.
    """
    del parameters
    return sum(entry.score for entry in scores) / len(scores)


def _minimum(scores: list[CriterionScore], parameters: dict[str, Any]) -> float:
    """Take the worst criterion as the result.

    Args:
        scores (list): The criterion scores, never empty.
        parameters (dict): Unused by this strategy.

    Returns:
        float: The lowest score.
    """
    del parameters
    return min(entry.score for entry in scores)


def _all_must_pass(scores: list[CriterionScore], parameters: dict[str, Any]) -> float:
    """Return a verdict rather than a magnitude.

    On ``verdict_only`` the number is one or zero and **must not be read as a
    quality measure**, which is exactly what the scale identifier exists to
    signal to whatever consumes it.

    Args:
        scores (list): The criterion scores, never empty.
        parameters (dict): ``minimum`` each criterion must reach.

    Returns:
        float: One when every criterion reached the minimum, zero otherwise.
    """
    minimum = float(parameters.get("minimum", 3.0))
    return 1.0 if all(entry.score >= minimum for entry in scores) else 0.0


def _threshold_count(scores: list[CriterionScore], parameters: dict[str, Any]) -> float:
    """Count how many criteria reached the minimum.

    Args:
        scores (list): The criterion scores, never empty.
        parameters (dict): ``minimum`` a criterion must reach to count.

    Returns:
        float: The count, on the ``count_of_n`` scale where the magnitude is a
        tally rather than a rating.
    """
    minimum = float(parameters.get("minimum", 3.0))
    return float(len([entry for entry in scores if entry.score >= minimum]))


_STRATEGIES: Final[dict[str, Callable[[list[CriterionScore], dict[str, Any]], float]]] = {
    "weighted_mean": _weighted_mean,
    "unweighted_mean": _unweighted_mean,
    "min": _minimum,
    "all_must_pass": _all_must_pass,
    "threshold_count": _threshold_count,
}


def registered_strategies() -> frozenset[str]:
    """Return every registered strategy name.

    **The conformance battery parametrizes over this.** A strategy added to the
    registry is covered the moment it is registered, with no list to update.

    Returns:
        frozenset[str]: The names.
    """
    return frozenset(_STRATEGIES)


def strategy_scale(strategy: str) -> str:
    """Return the scale a strategy declares.

    Args:
        strategy (str): The strategy name.

    Returns:
        str: Its registered scale identifier.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the strategy is not
            registered, or is registered in one place and not the other. The
            implementation and the scale table are two halves of one entry, and
            a strategy present in only one of them is a registration error
            rather than a runtime surprise.
    """
    scale = aggregation_scale(strategy)
    if scale is None or strategy not in _STRATEGIES:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: aggregation strategy {strategy!r} is not fully "
            f"registered; implementations are {sorted(_STRATEGIES)} and declared scales "
            f"are {sorted(registered_aggregation_strategies())}"
        )
    return scale


def aggregate(
    strategy: str,
    scores: list[CriterionScore],
    *,
    threshold: Optional[float] = None,
    parameters: Optional[dict[str, Any]] = None,
) -> AggregateScore:
    """Combine criterion scores through a registered strategy.

    Args:
        strategy (str): The registered strategy to apply.
        scores (list): The criterion scores, possibly empty after filtering.
        threshold (Optional[float]): The rubric's passing threshold.
        parameters (Optional[dict]): Strategy parameters from the rubric.

    Returns:
        AggregateScore: The result, carrying its scale. **An empty set yields
        no value rather than zero**, because a rubric whose criteria all
        filtered out measured nothing, and a zero would be indistinguishable
        from a response that scored badly.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` for an unregistered
            strategy.
    """
    scale = strategy_scale(strategy)
    if not scores:
        logger.info("Aggregation for %s had no criteria after filtering", strategy)
        return AggregateScore(
            value=None, scale_id=scale, strategy=strategy, criterion_count=0
        )

    value = _STRATEGIES[strategy](list(scores), dict(parameters or {}))
    return AggregateScore(
        value=value,
        scale_id=scale,
        strategy=strategy,
        criterion_count=len(scores),
        passed=None if threshold is None else value >= threshold,
    )


def combinable(first: AggregateScore, second: AggregateScore) -> bool:
    """Report whether two aggregate scores may be compared or combined.

    Args:
        first (AggregateScore): One score.
        second (AggregateScore): Another.

    Returns:
        bool: True only when both declare the same scale. Two rubrics
        aggregating on different scales produce numbers that **look** comparable
        and are not, which is why the scale travels with the score.
    """
    return first.scale_id == second.scale_id
