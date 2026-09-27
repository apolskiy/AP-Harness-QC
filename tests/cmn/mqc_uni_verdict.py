# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for verdict computation.

Covers `MQC_CMN_UNI_10101` through `10131`, inventoried in
``docs/design/cmn_verdict_and_cli.md`` section 10.

**Every case here is synthetic and deterministic.** The verdict is a pure
function of observations, configuration and an injected date, which is exactly
what makes these cases possible without a suite run or a network.

**Boundaries are stated at the threshold, never near it.** A rule expressed as
below 90% is tested *at* 90%, because off-by-one at a boundary is the likeliest
defect in any gate and the one a percentage invites.

A failure here is our defect, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

from typing import Any
import inspect
from datetime import date

import pytest

from cmn import verdict as verdict_module
from cmn.observations import Observation
from cmn.layers import outcome_properties, skip_blocks
from cmn.verdict import (
    inconsistent_cases,
    inconsistency_rate,
    score_spread,
    QuarantineEntry,
    Thresholds,
    VerdictConfig,
    evaluate_distribution,
    verdict,
)

pytestmark = pytest.mark.unit

_TODAY = date(2026, 9, 23)


def _graded(case_id: str, outcome: str = "pass", priority: int = 2, **extra: Any) -> Observation:
    """Build one graded observation.

    Args:
        case_id (str): Which case.
        outcome (str): What it produced.
        priority (int): Its priority band.
        **extra: Any further field to set.

    Returns:
        Observation: The built record.
    """
    return Observation(
        case_id=case_id, layer="EVAL", outcome=outcome, priority=priority, **extra
    )


def _passing_suite(count: int = 10) -> list[Observation]:
    """Build a suite that satisfies every rule.

    Args:
        count (int): How many graded observations to produce.

    Returns:
        list[Observation]: One passing precondition plus passing graded cases.
    """
    return [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")] + [
        _graded(f"MQC_TASK_{index}::MQC_RULE_r") for index in range(count)
    ]


class TestMQCPriorityGate:
    """V1: what a P0 or P1 failure costs, and what a P2 failure does not."""

    def MQC_CMN_UNI_10101_green_when_all_rules_satisfied(self) -> None:
        """The positive every negative below is measured against.

        Returns:
            None
        """
        result = verdict(_passing_suite(), VerdictConfig(), _TODAY)
        assert result.green is True
        assert result.exit_code == 0
        assert not result.breaches

    @pytest.mark.parametrize("priority", [0, 1])
    def MQC_CMN_UNI_10102_red_when_p0_observation_fails(self, priority: int) -> None:
        """A P0 or P1 failure fails the run whatever the pass rate.

        Both bands are covered here rather than in two cases, because the rule
        treats them identically and splitting it would suggest otherwise.

        Args:
            priority (int): The band that failed.

        Returns:
            None
        """
        observations = _passing_suite(20)
        observations.append(_graded("MQC_TASK_x::MQC_RULE_r", "fail", priority=priority))

        result = verdict(observations, VerdictConfig(), _TODAY)
        assert result.green is False
        assert "V1" in result.breached_rules
        assert result.pass_rate > 0.90

    def MQC_CMN_UNI_10103_red_when_p1_observation_fails(self) -> None:
        """Stated separately because the inventory does, and it is not a duplicate.

        `10102` asserts the shared rule over both bands; this asserts that P1
        alone is sufficient, which a rule reading only P0 would pass.

        Returns:
            None
        """
        observations = _passing_suite(20)
        observations.append(_graded("MQC_TASK_x::MQC_RULE_r", "fail", priority=1))
        assert "V1" in verdict(observations, VerdictConfig(), _TODAY).breached_rules

    def MQC_CMN_UNI_10104_green_when_p2_fails_within_pass_floor(self) -> None:
        """A P2 failure is absorbed by the pass rate, not by the gate.

        This is what the priority scheme is for: not every failure blocks, and
        a scheme where every failure blocked would have no use for bands.

        Returns:
            None
        """
        observations = _passing_suite(20)
        observations.append(_graded("MQC_TASK_x::MQC_RULE_r", "fail", priority=2))

        result = verdict(observations, VerdictConfig(), _TODAY)
        assert result.green is True
        assert result.pass_rate >= 0.90


class TestMQCRateThresholds:
    """V2, V3 and V4 at their exact boundaries."""

    def MQC_CMN_UNI_10105_green_at_exactly_ninety_percent_pass_rate(self) -> None:
        """Stated at the boundary: 90% passes, and the rule says below 90 fails.

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [_graded(f"MQC_TASK_{index}::MQC_RULE_r") for index in range(9)]
        observations.append(_graded("MQC_TASK_9::MQC_RULE_r", "fail", priority=3))

        result = verdict(observations, VerdictConfig(), _TODAY)
        assert result.pass_rate == pytest.approx(0.90)
        assert "V2" not in result.breached_rules

    def MQC_CMN_UNI_10106_red_just_below_ninety_percent_pass_rate(self) -> None:
        """One case the other side of the same boundary.

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [_graded(f"MQC_TASK_{index}::MQC_RULE_r") for index in range(8)]
        observations += [
            _graded(f"MQC_TASK_f{index}::MQC_RULE_r", "fail", priority=3)
            for index in range(2)
        ]

        result = verdict(observations, VerdictConfig(), _TODAY)
        assert result.pass_rate == pytest.approx(0.80)
        assert "V2" in result.breached_rules

    def MQC_CMN_UNI_10107_green_at_exactly_twenty_percent_skips(self) -> None:
        """The skip ceiling holds at 20% and fails above it.

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [_graded(f"MQC_TASK_{index}::MQC_RULE_r") for index in range(8)]
        observations += [
            _graded(f"MQC_TASK_s{index}::MQC_RULE_r", "skip", priority=3,
                    skip_reason="environmental")
            for index in range(2)
        ]

        result = verdict(observations, VerdictConfig(), _TODAY)
        assert result.skip_rate == pytest.approx(0.20)
        assert "V3" not in result.breached_rules

    def MQC_CMN_UNI_10108_red_just_above_twenty_percent_skips(self) -> None:
        """One skip the other side of the same boundary.

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [_graded(f"MQC_TASK_{index}::MQC_RULE_r") for index in range(7)]
        observations += [
            _graded(f"MQC_TASK_s{index}::MQC_RULE_r", "skip", priority=3,
                    skip_reason="environmental")
            for index in range(3)
        ]

        result = verdict(observations, VerdictConfig(), _TODAY)
        assert result.skip_rate == pytest.approx(0.30)
        assert "V3" in result.breached_rules

    def MQC_CMN_UNI_10109_green_at_exactly_ten_percent_priority_skips(self) -> None:
        """The P0 and P1 skip ceiling is tighter, and is its own denominator.

        A skip in a blocking band is worse than a skip elsewhere, because the
        band exists precisely to be measured every run.

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [
            _graded(f"MQC_TASK_{index}::MQC_RULE_r", priority=1) for index in range(9)
        ]
        observations.append(
            _graded("MQC_TASK_s::MQC_RULE_r", "skip", priority=1,
                    skip_reason="environmental")
        )

        result = verdict(observations, VerdictConfig(), _TODAY)
        assert "V4" not in result.breached_rules

    def MQC_CMN_UNI_10110_red_just_above_ten_percent_priority_skips(self) -> None:
        """One priority skip the other side of the same boundary.

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [
            _graded(f"MQC_TASK_{index}::MQC_RULE_r", priority=1) for index in range(8)
        ]
        observations += [
            _graded(f"MQC_TASK_s{index}::MQC_RULE_r", "skip", priority=1,
                    skip_reason="environmental")
            for index in range(2)
        ]

        assert "V4" in verdict(observations, VerdictConfig(), _TODAY).breached_rules


class TestMQCQuarantine:
    """V5, and the date the expiry is evaluated against."""

    def MQC_CMN_UNI_10111_red_when_quarantine_entry_expired(self) -> None:
        """Without expiry, quarantine becomes where failures go to be forgotten.

        The pass floor stops meaning anything once everything inconvenient has
        left the denominator, which is why a lapsed entry fails the run rather
        than quietly continuing to exclude.

        Returns:
            None
        """
        entry = QuarantineEntry("MQC_TASK_q::MQC_RULE_r", "flaky", date(2026, 9, 1))
        result = verdict(
            _passing_suite(), VerdictConfig(quarantine=[entry]), _TODAY
        )
        assert result.green is False
        assert "V5" in result.breached_rules

    def MQC_CMN_UNI_10112_green_when_quarantine_entry_current(self) -> None:
        """A current entry excludes without failing.

        Returns:
            None
        """
        entry = QuarantineEntry("MQC_TASK_q::MQC_RULE_r", "flaky", date(2026, 12, 1))
        result = verdict(_passing_suite(), VerdictConfig(quarantine=[entry]), _TODAY)
        assert result.green is True
        assert result.quarantined == ["MQC_TASK_q::MQC_RULE_r"]

    @pytest.mark.parametrize(
        "as_of,expired",
        [(date(2026, 9, 30), False), (date(2026, 10, 1), False), (date(2026, 10, 2), True)],
    )
    def MQC_CMN_UNI_10113_expiry_boundary_evaluated_against_injected_date(
        self, as_of: date, expired: Any
    ) -> None:
        """The boundary is testable only because the date is injected.

        A function calling the system clock could not be exercised at its own
        boundary without manipulating the machine, which is why the date is a
        parameter rather than something the function reaches for.

        The entry lapses **after** its expiry date, not on it: an entry good
        until the first is good on the first.

        Args:
            as_of (date): The injected evaluation date.
            expired (bool): Whether the entry should have lapsed.

        Returns:
            None
        """
        entry = QuarantineEntry("MQC_TASK_q::MQC_RULE_r", "flaky", date(2026, 10, 1))
        result = verdict(_passing_suite(), VerdictConfig(quarantine=[entry]), as_of)
        assert ("V5" in result.breached_rules) is expired


class TestMQCNothingMeasured:
    """V6: every way a run can measure nothing and look fine doing it."""

    def MQC_CMN_UNI_10114_red_when_no_observations_at_all(self) -> None:
        """A run that measured nothing must never report green.

        Every other rule passes vacuously over an empty set, which is exactly
        why this one exists.

        Returns:
            None
        """
        result = verdict([], VerdictConfig(), _TODAY)
        assert result.green is False
        assert "V6" in result.breached_rules

    def MQC_CMN_UNI_10115_red_when_no_graded_observations(self) -> None:
        """Preconditions passing is not a measurement of the model.

        Returns:
            None
        """
        observations = [
            Observation(f"MQC_TASK_{index}::MQC_RULE_pre", "UNI", "pass")
            for index in range(5)
        ]
        result = verdict(observations, VerdictConfig(), _TODAY)
        assert result.green is False
        assert "V6" in result.breached_rules

    def MQC_CMN_UNI_10116_red_when_every_graded_case_quarantined(self) -> None:
        """The pass-rate denominator is zero, so the suite verified nothing.

        Returns:
            None
        """
        observations = _passing_suite(3)
        quarantine = [
            QuarantineEntry(entry.case_id, "parked", date(2026, 12, 1))
            for entry in observations if entry.graded
        ]
        result = verdict(observations, VerdictConfig(quarantine=quarantine), _TODAY)

        assert result.green is False
        assert "V6" in result.breached_rules
        assert result.pass_rate is None

    def MQC_CMN_UNI_10117_red_when_every_pair_unsupported(self) -> None:
        """The skip denominator is zero, which is not the same as no skips.

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [
            _graded(f"MQC_TASK_{index}::MQC_RULE_r", "skip", skip_reason="unsupported")
            for index in range(4)
        ]

        result = verdict(observations, VerdictConfig(), _TODAY)
        assert result.green is False
        assert "V6" in result.breached_rules
        assert result.skip_rate is None


class TestMQCDenominators:
    """What each metric counts, and what it deliberately does not."""

    def MQC_CMN_UNI_10118_dependency_skips_excluded_from_skip_denominator(self) -> None:
        """A foundational failure cascades, and counting the cascade misleads.

        The run is already red from V1. Counting the dependent skips would
        breach V3 as well, adding a derived failure on top of the real one and
        pointing diagnosis at the environment.

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [_graded(f"MQC_TASK_{index}::MQC_RULE_r") for index in range(5)]
        observations += [
            _graded(f"MQC_TASK_d{index}::MQC_RULE_r", "skip", skip_reason="dependency")
            for index in range(20)
        ]

        result = verdict(observations, VerdictConfig(), _TODAY)
        assert result.skip_rate == pytest.approx(0.0)
        assert "V3" not in result.breached_rules

    def MQC_CMN_UNI_10119_unsupported_pairs_excluded_from_skip_denominator(self) -> None:
        """A declared capability gap is not an environmental failure (A13).

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [_graded(f"MQC_TASK_{index}::MQC_RULE_r") for index in range(5)]
        observations += [
            _graded(f"MQC_TASK_u{index}::MQC_RULE_r", "skip", skip_reason="unsupported")
            for index in range(20)
        ]

        result = verdict(observations, VerdictConfig(), _TODAY)
        assert result.skip_rate == pytest.approx(0.0)
        assert "V3" not in result.breached_rules

    def MQC_CMN_UNI_10120_quarantined_cases_excluded_from_pass_denominator(self) -> None:
        """Excluded from the denominator, never deleted from the suite.

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [_graded(f"MQC_TASK_{index}::MQC_RULE_r") for index in range(9)]
        observations.append(_graded("MQC_TASK_q::MQC_RULE_r", "fail", priority=3))

        quarantine = [QuarantineEntry("MQC_TASK_q::MQC_RULE_r", "parked", date(2026, 12, 1))]
        result = verdict(observations, VerdictConfig(quarantine=quarantine), _TODAY)

        assert result.pass_rate == pytest.approx(1.0)
        assert result.green is True

    def MQC_CMN_UNI_10121_security_layer_excluded_from_distribution_ceiling(self) -> None:
        """Security coverage does not compete with functional coverage.

        A ceiling exists to prevent priority inflation, and a security test
        going unwritten because the P0 quota was full is the ceiling doing
        harm. The exemption is read from the layer registration, not from the
        layer's name.

        Returns:
            None
        """
        graded = [
            Observation(f"MQC_TASK_{index}::MQC_RULE_r", "EVAL", "pass", priority=3)
            for index in range(40)
        ]
        security = [
            Observation(f"MQC_TASK_s{index}::MQC_RULE_r", "SEC", "pass", priority=0)
            for index in range(40)
        ]

        report = evaluate_distribution(graded + security, Thresholds())
        assert report.case_definitions == 40
        assert report.p0_share == pytest.approx(0.0)


class TestMQCPreconditionGate:
    """Preconditions sit above the scale, and what that costs when they fail."""

    def MQC_CMN_UNI_10122_precondition_failure_blocks_graded_evaluation(self) -> None:
        """Exit 3, not 1. Nothing was measured rather than something failing.

        Collapsing them would let CI treat a broken harness as an
        underperforming model, which sends the wrong person to investigate.

        Returns:
            None
        """
        observations = [
            Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "fail"),
            _graded("MQC_TASK_x::MQC_RULE_r", "fail", priority=0),
        ]
        result = verdict(observations, VerdictConfig(), _TODAY)

        assert result.exit_code == 3
        assert result.breached_rules == ["PRECONDITION_FAILED"]
        assert "V1" not in result.breached_rules

    def MQC_CMN_UNI_10123_precondition_skip_is_a_failure(self) -> None:
        """A unit test has nothing external to block it.

        A skip therefore means something is broken rather than unavailable,
        which is why zero skips are permitted rather than merely discouraged.

        Returns:
            None
        """
        observations = [
            Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "skip",
                        skip_reason="environmental"),
            _graded("MQC_TASK_x::MQC_RULE_r"),
        ]
        assert verdict(observations, VerdictConfig(), _TODAY).exit_code == 3


class TestMQCVerdictProperties:
    """What the function guarantees about itself."""

    def MQC_CMN_UNI_10124_reports_every_breached_rule_not_only_the_first(self) -> None:
        """Short-circuiting would cost a cycle per rediscovered breach.

        For a suite whose live runs are scheduled rather than on demand, fixing
        V1 and meeting V3 on the next run and V4 on the one after is three
        cycles to reach a state one run could have reported.

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [
            _graded(f"MQC_TASK_f{index}::MQC_RULE_r", "fail", priority=0)
            for index in range(3)
        ]
        observations += [
            _graded(f"MQC_TASK_s{index}::MQC_RULE_r", "skip", priority=1,
                    skip_reason="environmental")
            for index in range(3)
        ]

        breached = verdict(observations, VerdictConfig(), _TODAY).breached_rules
        assert {"V1", "V2", "V3", "V4"} <= set(breached)
        assert len(breached) >= 4

    def MQC_CMN_UNI_10125_verdict_is_pure_for_identical_input(self) -> None:
        """Identical input yields an identical verdict, every time.

        Returns:
            None
        """
        observations = _passing_suite()
        first = verdict(observations, VerdictConfig(), _TODAY)
        second = verdict(list(observations), VerdictConfig(), _TODAY)
        assert first == second

    def MQC_CMN_UNI_10126_verdict_does_not_read_system_clock(self) -> None:
        """Asserted structurally rather than by trusting the docstring.

        A verdict function that reached for the clock would make quarantine
        expiry depend on when it happened to run, and a case written at a
        boundary would pass or fail by the calendar.

        Returns:
            None
        """
        source = inspect.getsource(verdict_module)
        for forbidden in ("date.today()", "datetime.now()", "time.time()", "os.environ"):
            assert forbidden not in source

        entry = QuarantineEntry("MQC_TASK_q::MQC_RULE_r", "flaky", date(2026, 10, 1))
        past = verdict(_passing_suite(), VerdictConfig(quarantine=[entry]), date(2026, 1, 1))
        future = verdict(
            _passing_suite(), VerdictConfig(quarantine=[entry]), date(2027, 1, 1)
        )
        assert past.green is True
        assert future.green is False


class TestMQCDistribution:
    """The ceilings, and the population they are meaningful over."""

    def MQC_CMN_UNI_10127_distribution_check_returns_no_verdict_below_thirty_cases(self) -> None:
        """Below thirty, one case moves the share by over three percent.

        A ceiling expressed as a percentage then says more about the population
        size than about priority inflation, so the check reports counts and
        returns no verdict rather than a number that would mislead.

        Returns:
            None
        """
        small = [
            Observation(f"MQC_TASK_{index}::MQC_RULE_r", "EVAL", "pass", priority=0)
            for index in range(29)
        ]
        report = evaluate_distribution(small, Thresholds())

        assert report.verdict_returned is False
        assert report.case_definitions == 29
        assert report.p0_share is None
        assert verdict(
            [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")] + small,
            VerdictConfig(), _TODAY,
        ).green is True

    def MQC_CMN_UNI_10128_red_when_p0_share_exceeds_ten_percent(self) -> None:
        """An inflated P0 population turns the must-pass gate into a hair-trigger.

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [
            _graded(f"MQC_TASK_p{index}::MQC_RULE_r", priority=0) for index in range(10)
        ]
        observations += [
            _graded(f"MQC_TASK_{index}::MQC_RULE_r", priority=3) for index in range(30)
        ]

        result = verdict(observations, VerdictConfig(), _TODAY)
        assert "V7" in result.breached_rules
        assert result.distribution.p0_share == pytest.approx(0.25)

    def MQC_CMN_UNI_10129_red_when_combined_p0_p1_exceeds_thirty_percent(self) -> None:
        """The combined ceiling catches inflation split across two bands.

        Without it, 10% at P0 and 20% at P1 would each pass while a third of
        the suite blocked every run.

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [
            _graded(f"MQC_TASK_a{index}::MQC_RULE_r", priority=0) for index in range(4)
        ]
        observations += [
            _graded(f"MQC_TASK_b{index}::MQC_RULE_r", priority=1) for index in range(12)
        ]
        observations += [
            _graded(f"MQC_TASK_{index}::MQC_RULE_r", priority=3) for index in range(24)
        ]

        result = verdict(observations, VerdictConfig(), _TODAY)
        assert result.distribution.combined_share == pytest.approx(0.40)
        assert "V9" in result.breached_rules

    def MQC_CMN_UNI_10184_distribution_check_reports_the_demoted_case_count(self) -> None:
        """A suite meeting its ceilings only by demoting has not met them.

        This closes the loop the ceilings open. The ceilings exist so an
        inflated P0 population cannot turn the gate into a hair-trigger;
        demotion is how a breach gets resolved, and an unreported demotion
        resolves it by making the number smaller rather than the suite better.

        Returns:
            None
        """
        observations = [
            Observation(f"MQC_TASK_{index}::MQC_RULE_r", "EVAL", "pass", priority=3,
                        demoted=index < 11)
            for index in range(40)
        ]
        report = evaluate_distribution(observations, Thresholds())

        assert report.verdict_returned is True
        assert report.demoted_count == 11
        assert report.p0_share == pytest.approx(0.0)


class TestMQCRunSoundness:
    """Our defects and the model's are different findings.

    Designed in ``docs/design/cmn_verdict_and_cli.md`` section 10.24.
    """

    def MQC_CMN_UNI_11149_a_broken_graded_observation_blocks_and_exits_three(
        self,
    ) -> None:
        """Broken was distinguished at the observation and lost at the verdict.

        **Exit 1 says a suite measured something and it failed**, which is a
        finding about a third party. A broken observation says our code failed
        while measuring, so the run is red and the code says whose defect it
        was.

        **No proportion is tolerated.** Broken means something needs a fix, so
        a ceiling would be a tolerated quantity of unfixed defects.

        Returns:
            None
        """
        suite = _passing_suite(20)
        suite.append(_graded("MQC_TASK_x::MQC_RULE_r", outcome="broken", priority=3))

        result = verdict(suite, as_of_date=_TODAY)

        assert not result.green
        assert result.exit_code == 3, (
            "a broken observation exited 1, which reads as a model regression"
        )
        assert any("broke" in breach.reason for breach in result.breaches)

        # ONE IS ENOUGH, at the lowest priority there is. A rule that only
        # fired at P0 would let the cheapest cases hide our own defects.
        single = _passing_suite(50)
        single.append(_graded("MQC_TASK_y::MQC_RULE_r", outcome="broken", priority=4))
        assert verdict(single, as_of_date=_TODAY).exit_code == 3

        # AND IT IS OUT OF THE PASS RATE, so harness flakiness does not read as
        # model degradation in the headline number.
        assert outcome_properties("broken").counts_in_pass_rate is False

    def MQC_CMN_UNI_11150_an_incomplete_skip_blocks_however_few_there_are(
        self,
    ) -> None:
        """Unfinished work was the most tolerated skip in the system.

        A case that skipped because nobody had written it took ``unsupported``,
        which is excluded from the skip denominator entirely, so **the one
        thing that must never merge was the one thing no ceiling could see**.

        Returns:
            None
        """
        assert skip_blocks("incomplete")
        assert not skip_blocks("environmental")
        assert not skip_blocks("dependency")
        assert not skip_blocks("unsupported")
        assert not skip_blocks(None)

        suite = _passing_suite(50)
        suite.append(
            _graded(
                "MQC_TASK_z::MQC_RULE_r",
                outcome="skip",
                priority=4,
                skip_reason="incomplete",
            )
        )

        result = verdict(suite, as_of_date=_TODAY)

        assert not result.green
        assert result.exit_code == 3
        assert any("unfinished" in breach.reason for breach in result.breaches)

    def MQC_CMN_UNI_11151_an_environmental_skip_is_tolerated_to_its_ceiling(
        self,
    ) -> None:
        """A provider outage is not an unwritten case, and the reason says so.

        **Named at the threshold exactly**, on both sides. The skip ceiling is
        20% of the skippable population, so 20% passes and anything above it
        does not.

        Returns:
            None
        """
        # 16 passing graded plus 4 environmental skips is exactly 20%.
        at_ceiling = _passing_suite(16)
        at_ceiling.extend(
            _graded(
                f"MQC_TASK_e{index}::MQC_RULE_r",
                outcome="skip",
                priority=3,
                skip_reason="environmental",
            )
            for index in range(4)
        )
        result = verdict(at_ceiling, as_of_date=_TODAY)
        assert result.green, (
            f"an outage at exactly the ceiling was refused: {result.breaches}"
        )
        assert result.exit_code == 0

        # One more crosses it, and it is a ceiling breach rather than a
        # soundness failure: exit 1, because the run did measure.
        over = _passing_suite(15)
        over.extend(
            _graded(
                f"MQC_TASK_e{index}::MQC_RULE_r",
                outcome="skip",
                priority=3,
                skip_reason="environmental",
            )
            for index in range(5)
        )
        breached = verdict(over, as_of_date=_TODAY)
        assert not breached.green
        assert breached.exit_code == 1, (
            "an outage over the ceiling exited 3, which says nothing was "
            "measured when 15 cases were"
        )


class TestMQCObservationConsistency:
    """A model that answers one question three ways, and what that costs."""

    @staticmethod
    def _observed(case_id: str, outcomes: list[str]) -> list[Observation]:
        """Return one case observed several times.

        Args:
            case_id (str): The case.
            outcomes (list[str]): One outcome per observation, in order.

        Returns:
            list[Observation]: The observations, indexed from zero.
        """
        return [
            Observation(
                case_id=case_id,
                layer="EVAL",
                outcome=outcome,
                observation_index=index,
                priority=2,
                priority_conditions=["P2_DOCUMENTED_BEHAVIOUR"],
            )
            for index, outcome in enumerate(outcomes)
        ]

    def MQC_CMN_UNI_11171_a_case_whose_observations_disagree_is_a_finding(
        self,
    ) -> None:
        """Two passes and a fail is not a pass, and no majority is taken.

        **A majority would discard the finding the repeats exist to produce.**
        The result is not "this model does this"; it is "this model does this
        sometimes", which is a defect and is what a reader needs to see.

        **A harness event is not a disagreement.** A case measured twice and
        skipped once is one measurement short, which the skip rules already
        count; calling it an inconsistency would report our infrastructure as
        a model defect.

        Returns:
            None
        """
        disagreeing = self._observed("MQC_CASE_alpha", ["pass", "pass", "fail"])
        assert inconsistent_cases(disagreeing) == {"MQC_CASE_alpha": {"pass", "fail"}}

        agreeing = self._observed("MQC_CASE_beta", ["pass", "pass", "pass"])
        assert not inconsistent_cases(agreeing)
        assert not inconsistent_cases(
            self._observed("MQC_CASE_gamma", ["fail", "fail", "fail"])
        )

        # A SKIP IS NOT A DISAGREEMENT, and neither is a broken observation.
        assert not inconsistent_cases(
            self._observed("MQC_CASE_delta", ["pass", "skip", "pass"])
        )
        assert not inconsistent_cases(
            self._observed("MQC_CASE_epsilon", ["pass", "broken", "pass"])
        )

        # A CASE OBSERVED ONCE CANNOT DISAGREE WITH ITSELF, which is the
        # honest answer rather than a false negative: with one sample there is
        # nothing to compare, and that is why A4.1 decided on three.
        assert not inconsistent_cases(self._observed("MQC_CASE_zeta", ["fail"]))

    def MQC_CMN_UNI_11172_inconsistency_at_the_ceiling_unsounds_the_run(
        self,
    ) -> None:
        """A boundary case, stated at the ceiling exactly.

        **Exit 3, not 1.** An inconsistent model does not merely score badly:
        every single-sample result from it is a draw from a distribution
        nobody characterised, so the run's other numbers would overstate what
        they established. That is the difference between a measured failure
        and a run that cannot be trusted to have measured anything.

        Returns:
            None
        """
        # TEN CASES, ONE INCONSISTENT: a rate of exactly 0.10, which is the
        # ceiling. A boundary is tested AT the threshold, never near it.
        observations: list[Observation] = self._observed(
            "MQC_CASE_wobbly", ["pass", "fail", "pass"]
        )
        for number in range(9):
            observations += self._observed(
                f"MQC_CASE_steady_{number}", ["pass", "pass", "pass"]
            )

        assert inconsistency_rate(observations) == 0.10
        result = verdict(observations, as_of_date=_TODAY)

        assert result.exit_code == 3, (
            f"an inconsistency rate at the ceiling exited {result.exit_code}, "
            f"so an unreliable model reads as a measured failure"
        )
        assert not result.green
        assert [entry.rule for entry in result.breaches] == ["RUN_UNSOUND"]
        assert "consistently" in result.breaches[0].reason
        assert "MQC_CASE_wobbly" in result.breaches[0].reason

        # BELOW THE CEILING THE RUN PROCEEDS, or the rule would block every
        # run rather than the ones it is for.
        tolerant = list(observations)
        for number in range(9, 20):
            tolerant += self._observed(
                f"MQC_CASE_steady_{number}", ["pass", "pass", "pass"]
            )
        assert inconsistency_rate(tolerant) < 0.10
        assert verdict(tolerant, as_of_date=_TODAY).exit_code != 3

        # AND AN EMPTY RUN IS NOT PERFECTLY INCONSISTENT, which would make the
        # ceiling fail on a run that measured nothing.
        assert inconsistency_rate([]) == 0.0


    def MQC_CMN_UNI_11175_a_score_moving_inside_the_band_is_recorded_not_gated(
        self,
    ) -> None:
        """Three observations scoring 4, 4 and 5 all pass, and the spread is real.

        **The consistency check compares verdicts, so it cannot see this.**
        Against a threshold of 4 every observation clears it, so the outcomes
        agree and `inconsistent_cases` finds nothing. That is correct about
        the verdict and blind about the judge.

        **Recorded, never gated.** The case passed on every observation, which
        is what the threshold was set to decide, and gating a spread would need
        a second threshold nobody has evidence for (design section 4.9.4).

        **Zero is recorded and absence is not.** A spread of zero says the judge
        agreed with itself; a case observed once has no range, and reporting
        zero for it would be indistinguishable from agreement.

        Returns:
            None
        """
        def scored(case: str, index: int, value: float) -> Observation:
            """Return one judged observation.

            Args:
                case (str): The case identifier.
                index (int): Which observation.
                value (float): The score awarded.

            Returns:
                Observation: The record.
            """
            return Observation(
                case_id=case,
                layer="EVAL",
                outcome="pass",
                observation_index=index,
                score=value,
                priority=2,
                priority_conditions=["P2_DOCUMENTED_BEHAVIOUR"],
            )

        wobbling = [
            scored("MQC_CASE_wobbly", index, value)
            for index, value in enumerate((4.0, 4.0, 5.0))
        ]
        steady = [scored("MQC_CASE_steady", index, 4.0) for index in range(3)]
        once = [scored("MQC_CASE_once", 0, 3.0)]
        observations = wobbling + steady + once

        spread = score_spread(observations)
        assert spread["MQC_CASE_wobbly"] == 1.0
        assert spread["MQC_CASE_steady"] == 0.0, (
            "agreement is a result and must be recorded, or it could not be "
            "told from a case that was never observed twice"
        )
        assert "MQC_CASE_once" not in spread, (
            "a case observed once was given a range, which reads as agreement"
        )

        # THE CONSISTENCY CHECK IS BLIND TO IT, which is why the spread
        # exists and is not a bug in the consistency rule.
        assert not inconsistent_cases(observations)

        # AND IT GATES NOTHING. The run is green with a spread recorded.
        result = verdict(observations, as_of_date=_TODAY)
        assert result.exit_code == 0, (
            f"a score spread inside the passing band exited "
            f"{result.exit_code}, so information became a failure"
        )
        assert result.green
        assert result.score_spread == spread, (
            "the verdict did not carry the spread, so it is computed and lost"
        )
