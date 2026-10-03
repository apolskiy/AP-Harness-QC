# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for calibration against anchored exemplars.

Covers `MQC_EVL_UNI_114200` through `114203`, inventoried in
``docs/design/tier3_evaluation.md`` section 11.1.

**An anchor states what a level means; an exemplar shows it.** Calibration asks
whether the judge still agrees with the anchor it was given.

**Deviation is recorded even when it passes.** A rubric drifting steadily by one
level looks healthy on any single run and obvious across twenty, and only the
record makes the second view possible.

A failure here is our defect, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

import pytest

from evaluation.calibration import (
    calibrate_rubric,
    compare_to_anchor,
    observation_variance,
    tolerance,
)
from ingestion.schemas import Rubric

pytestmark = pytest.mark.unit

_CRITERION = "MQC_CRT_grounding"


class TestMQCCalibrationTolerance:
    """How far the judge may drift before the rubric is no longer usable."""

    def MQC_EVL_UNI_114200_calibration_exact_match_passes(self) -> None:
        """The judge landed on the level the exemplar was written for.

        Returns:
            None
        """
        result = compare_to_anchor(_CRITERION, 3, 3.0)
        assert result.passed is True
        assert result.exact is True
        assert result.deviation == 0
        assert result.drifted_within_tolerance is False

    @pytest.mark.parametrize("observed", [2.0, 4.0])
    def MQC_EVL_UNI_114201_calibration_one_level_deviation_passes_and_records(
        self, observed: float
    ) -> None:
        """The boundary, stated at one level exactly and in both directions.

        A single level of disagreement between an anchor and a judge is within
        what a five-point scale can be expected to resolve. Two is not.

        Args:
            observed (float): What the judge awarded a level 3 exemplar.

        Returns:
            None
        """
        result = compare_to_anchor(_CRITERION, 3, observed)
        assert result.passed is True
        assert result.exact is False
        assert result.deviation == 1.0
        assert result.drifted_within_tolerance is True

    @pytest.mark.parametrize("observed", [1.0, 5.0])
    def MQC_EVL_UNI_114202_calibration_two_level_deviation_fails(self, observed: float) -> None:
        """Two levels apart means the rubric or the judge has drifted.

        Scores from a rubric in that state cannot be compared with earlier
        ones, which is the whole purpose of running calibration at all.

        Args:
            observed (float): What the judge awarded a level 3 exemplar.

        Returns:
            None
        """
        result = compare_to_anchor(_CRITERION, 3, observed)
        assert result.passed is False
        assert result.deviation == 2.0
        assert tolerance() == 1

    def MQC_EVL_UNI_114203_deviation_within_tolerance_is_recorded_for_trend(self) -> None:
        """Recording a tolerated deviation is what makes trend visible.

        A rubric drifting steadily by one level passes every run and is obvious
        only across many. Discarding the deviation because it passed would
        discard the only signal that distinguishes drift from stability.

        Returns:
            None
        """
        drifting = [compare_to_anchor(_CRITERION, 3, 4.0) for _ in range(5)]
        stable = [compare_to_anchor(_CRITERION, 3, 3.0) for _ in range(5)]

        assert all(result.passed for result in drifting + stable)
        assert sum(result.deviation for result in drifting) == 5.0
        assert sum(result.deviation for result in stable) == 0.0
        assert all(result.drifted_within_tolerance for result in drifting)


class TestMQCCalibrationOverARubric:
    """Applying calibration to every anchor that carries an exemplar."""

    def MQC_EVL_UNI_114204_an_anchor_without_an_exemplar_yields_no_result(
        self, sample_rubric_record: Rubric
    ) -> None:
        """Nothing was measured, so nothing passes.

        A manufactured pass would make an uncalibrated rubric look verified,
        which is worse than reporting that it was never checked.

        Args:
            sample_rubric_record (Rubric): The rubric to calibrate.

        Returns:
            None
        """
        criterion = sample_rubric_record.criteria[0]
        observed = {criterion.criterion_id: {level: 3.0 for level in criterion.anchors}}
        results = calibrate_rubric(sample_rubric_record, observed)

        exemplars = [
            level for level in criterion.anchors
            if criterion.anchors[level].exemplar is not None
        ]
        assert len(results) == len(exemplars)

    def MQC_EVL_UNI_114205_an_unjudged_exemplar_yields_no_result(
        self, sample_rubric_record: Rubric
    ) -> None:
        """A calibration run that reached no judge measured nothing.

        Args:
            sample_rubric_record (Rubric): The rubric to calibrate.

        Returns:
            None
        """
        assert not calibrate_rubric(sample_rubric_record, {})


class TestMQCObservationVariance:
    """The second drift signal, which needs no new machinery."""

    def MQC_EVL_UNI_114206_variance_across_observations_is_reported(self) -> None:
        """High variance on identical input means the anchors do not discriminate.

        A4 already produces three observations, so this signal costs nothing
        beyond reading what is there.

        Returns:
            None
        """
        assert observation_variance([3.0, 3.0, 3.0]) == 0.0
        assert observation_variance([1.0, 3.0, 5.0]) == 4.0

    def MQC_EVL_UNI_114207_variance_is_undefined_below_two_observations(self) -> None:
        """Reporting zero would make one observation look maximally consistent.

        Returns:
            None
        """
        assert observation_variance([]) is None
        assert observation_variance([4.0]) is None
