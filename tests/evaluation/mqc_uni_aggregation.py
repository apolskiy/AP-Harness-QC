# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for aggregation strategies and the scales they declare.

Covers `MQC_EVL_UNI_114000` through `114004`, inventoried in
``docs/design/tier3_evaluation.md`` section 11.1, and the strategy conformance
battery of section 10.

**Scores across different scale identifiers are not comparable.** The strategy
declares its scale, which travels with the result, making incomparability a
machine-checkable fact rather than a convention someone has to remember.

**The battery is parametrized over the registry**, so a strategy added to it is
covered the moment it is registered.

A failure here is **not a model finding**, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

import pytest

from cmn.registries import registered_aggregation_strategies
from evaluation.aggregation import (
    CriterionScore,
    aggregate,
    combinable,
    registered_strategies,
    strategy_scale,
)

pytestmark = pytest.mark.unit

_STRATEGIES = sorted(registered_strategies())


def _scores(*values: float) -> list[CriterionScore]:
    """Build criterion scores with equal weight.

    Args:
        *values (float): The scores.

    Returns:
        list[CriterionScore]: One record per value.
    """
    return [
        CriterionScore(criterion_id=f"MQC_CRT_{index}", score=value)
        for index, value in enumerate(values)
    ]


class TestMQCStrategyConformance:
    """The battery of design section 10, over every registered strategy."""

    @pytest.mark.parametrize("strategy", _STRATEGIES)
    def MQC_EVL_UNI_114000_aggregation_strategy_emits_scale_id(self, strategy: str) -> None:
        """A strategy declares its scale, and the result carries it.

        Without this a consumer comparing two scores has no mechanical way to
        tell whether it may, and the answer depends on someone remembering.

        Args:
            strategy (str): The registered strategy.

        Returns:
            None
        """
        result = aggregate(strategy, _scores(4.0, 2.0))
        assert result.scale_id == strategy_scale(strategy)
        assert result.strategy == strategy
        assert result.scale_id

    @pytest.mark.parametrize("strategy", _STRATEGIES)
    def MQC_EVL_UNI_114005_a_strategy_is_deterministic_for_identical_input(
        self,
        strategy: str,
    ) -> None:
        """Identical input yields an identical score, every time.

        A strategy that was not deterministic would make a same-commit
        comparison meaningless, and every reliability signal downstream reads
        exactly that comparison.

        Args:
            strategy (str): The registered strategy.

        Returns:
            None
        """
        scores = _scores(5.0, 3.0, 1.0)
        first = aggregate(strategy, scores, threshold=3.0)
        second = aggregate(strategy, list(scores), threshold=3.0)
        assert first == second

    @pytest.mark.parametrize("strategy", _STRATEGIES)
    def MQC_EVL_UNI_114003_aggregation_handles_single_criterion(self, strategy: str) -> None:
        """A rubric may legitimately carry one criterion.

        A mean over one value and a minimum over one value are both that value,
        and a strategy dividing by a count it assumed was larger fails here.

        Args:
            strategy (str): The registered strategy.

        Returns:
            None
        """
        result = aggregate(strategy, _scores(4.0))
        assert result.evaluated is True
        assert result.criterion_count == 1
        assert result.value is not None

    @pytest.mark.parametrize("strategy", _STRATEGIES)
    def MQC_EVL_UNI_114004_aggregation_handles_empty_after_filtering(self, strategy: str) -> None:
        """Nothing survived filtering, so nothing was measured.

        **Absent, never zero.** A zero would be indistinguishable from a
        response that scored badly, which would turn a rubric that measured
        nothing into a quality finding.

        Args:
            strategy (str): The registered strategy.

        Returns:
            None
        """
        result = aggregate(strategy, [], threshold=3.0)
        assert result.value is None
        assert result.evaluated is False
        assert result.criterion_count == 0
        assert result.passed is None

    def MQC_EVL_UNI_114006_every_declared_strategy_has_an_implementation(self) -> None:
        """The two halves of a registry entry must both exist.

        A strategy named in the scale table with no implementation, or the
        reverse, is a registration error rather than a runtime surprise, and a
        rubric naming it would fail deep inside a run.

        Returns:
            None
        """
        assert registered_strategies() == registered_aggregation_strategies()
        for strategy in _STRATEGIES:
            assert strategy_scale(strategy)

    def MQC_EVL_UNI_114007_an_unregistered_strategy_is_rejected_by_name(self) -> None:
        """A rubric naming a strategy nobody wrote fails with both lists.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR") as caught:
            aggregate("geometric_mean", _scores(3.0))
        assert "geometric_mean" in str(caught.value)


class TestMQCScaleComparability:
    """What may be compared, and what only looks as though it may."""

    def MQC_EVL_UNI_114001_scores_of_differing_scale_id_are_not_combined(self) -> None:
        """Two strategies on different scales produce numbers that look alike.

        A verdict of 1.0 and a mean of 1.0 are not the same claim, and nothing
        about the numbers says so. The scale travelling with the score is what
        makes the difference machine-checkable.

        Returns:
            None
        """
        continuous = aggregate("weighted_mean", _scores(4.0, 2.0))
        verdict = aggregate("all_must_pass", _scores(4.0, 2.0))
        tally = aggregate("threshold_count", _scores(4.0, 2.0))

        assert combinable(continuous, verdict) is False
        assert combinable(verdict, tally) is False
        assert combinable(continuous, aggregate("min", _scores(4.0))) is True
        assert len({continuous.scale_id, verdict.scale_id, tally.scale_id}) == 3

    def MQC_EVL_UNI_114002_score_recorded_on_pass_as_well_as_failure(self) -> None:
        """A pass at 3.1 and a pass at 4.8 are materially different signals.

        That distinction disappears entirely if only failures carry scores, and
        it is the distinction a trend over history is built from.

        Returns:
            None
        """
        marginal = aggregate("unweighted_mean", _scores(3.1, 3.1), threshold=3.0)
        strong = aggregate("unweighted_mean", _scores(4.8, 4.8), threshold=3.0)

        assert marginal.passed is True
        assert strong.passed is True
        assert marginal.value != strong.value
        assert marginal.evaluated and strong.evaluated

    def MQC_EVL_UNI_114008_weighting_changes_the_result_it_claims_to_weight(self) -> None:
        """The counterweight the weighted strategy needs.

        A weighted mean that ignored its weights would satisfy every case above,
        because equal weights make it identical to the unweighted one.

        Returns:
            None
        """
        weighted = [
            CriterionScore("MQC_CRT_major", 1.0, weight=4.0),
            CriterionScore("MQC_CRT_minor", 5.0, weight=1.0),
        ]
        assert aggregate("weighted_mean", weighted).value == pytest.approx(1.8)
        assert aggregate("unweighted_mean", weighted).value == pytest.approx(3.0)

    def MQC_EVL_UNI_114009_all_weights_zero_falls_back_rather_than_dividing(self) -> None:
        """A rubric declaring no criterion matters still has to produce a number.

        Dividing by a zero total would raise, and a silent zero would read as a
        quality finding. The unweighted mean is the only answer that is neither.

        Returns:
            None
        """
        unweighted_all = [
            CriterionScore("MQC_CRT_one", 2.0, weight=0.0),
            CriterionScore("MQC_CRT_two", 4.0, weight=0.0),
        ]
        assert aggregate("weighted_mean", unweighted_all).value == pytest.approx(3.0)
