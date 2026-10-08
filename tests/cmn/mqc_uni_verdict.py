# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for verdict computation.

Covers `MQC_CMN_UNI_112000` through `112101`, inventoried in
``docs/design/cmn_verdict_and_cli.md`` section 10.

**Every case here is synthetic and deterministic.** The verdict is a pure
function of observations, configuration and an injected date, which is exactly
what makes these cases possible without a suite run or a network.

**Boundaries are stated at the threshold, never near it.** A rule expressed as
below 90% is tested *at* 90%, because off-by-one at a boundary is the likeliest
defect in any gate and the one a percentage invites.

A failure here is **not a model finding**, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

import inspect
from datetime import date

import pytest

from cmn import verdict as verdict_module
from cmn.layers import outcome_properties, skip_blocks
from cmn.observations import Observation
from cmn.verdict import (
    QuarantineEntry,
    Thresholds,
    VerdictConfig,
    evaluate_distribution,
    verdict,
)
from tests.cmn.verdict_support import TODAY, graded, passing_suite

pytestmark = pytest.mark.unit


class TestMQCPriorityGate:
    """V1: what a P0 or P1 failure costs, and what a P2 failure does not."""

    def MQC_CMN_UNI_112000_green_when_all_rules_satisfied(self) -> None:
        """The positive every negative below is measured against.

        Returns:
            None
        """
        result = verdict(passing_suite(), VerdictConfig(), TODAY)
        assert result.green is True
        assert result.exit_code == 0
        assert not result.breaches

    @pytest.mark.parametrize("priority", [0, 1])
    def MQC_CMN_UNI_112001_red_when_p0_observation_fails(self, priority: int) -> None:
        """A P0 or P1 failure fails the run whatever the pass rate.

        Both bands are covered here rather than in two cases, because the rule
        treats them identically and splitting it would suggest otherwise.

        Args:
            priority (int): The band that failed.

        Returns:
            None
        """
        observations = passing_suite(20)
        observations.append(graded("MQC_TASK_x::MQC_RULE_r", "fail", priority=priority))

        result = verdict(observations, VerdictConfig(), TODAY)
        assert result.green is False
        assert "V1" in result.breached_rules
        assert result.pass_rate > 0.90

    def MQC_CMN_UNI_112002_red_when_p1_observation_fails(self) -> None:
        """Stated separately because the inventory does, and it is not a duplicate.

        `112001` asserts the shared rule over both bands; this asserts that P1
        alone is sufficient, which a rule reading only P0 would pass.

        Returns:
            None
        """
        observations = passing_suite(20)
        observations.append(graded("MQC_TASK_x::MQC_RULE_r", "fail", priority=1))
        assert "V1" in verdict(observations, VerdictConfig(), TODAY).breached_rules

    def MQC_CMN_UNI_112003_green_when_p2_fails_within_pass_floor(self) -> None:
        """A P2 failure is absorbed by the pass rate, not by the gate.

        This is what the priority scheme is for: not every failure blocks, and
        a scheme where every failure blocked would have no use for bands.

        Returns:
            None
        """
        observations = passing_suite(20)
        observations.append(graded("MQC_TASK_x::MQC_RULE_r", "fail", priority=2))

        result = verdict(observations, VerdictConfig(), TODAY)
        assert result.green is True
        assert result.pass_rate >= 0.90


class TestMQCRateThresholds:
    """V2, V3 and V4 at their exact boundaries."""

    def MQC_CMN_UNI_112004_green_at_exactly_ninety_percent_pass_rate(self) -> None:
        """Stated at the boundary: 90% passes, and the rule says below 90 fails.

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [graded(f"MQC_TASK_{index}::MQC_RULE_r") for index in range(9)]
        observations.append(graded("MQC_TASK_9::MQC_RULE_r", "fail", priority=3))

        result = verdict(observations, VerdictConfig(), TODAY)
        assert result.pass_rate == pytest.approx(0.90)
        assert "V2" not in result.breached_rules

    def MQC_CMN_UNI_112005_red_just_below_ninety_percent_pass_rate(self) -> None:
        """One case the other side of the same boundary.

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [graded(f"MQC_TASK_{index}::MQC_RULE_r") for index in range(8)]
        observations += [
            graded(f"MQC_TASK_f{index}::MQC_RULE_r", "fail", priority=3)
            for index in range(2)
        ]

        result = verdict(observations, VerdictConfig(), TODAY)
        assert result.pass_rate == pytest.approx(0.80)
        assert "V2" in result.breached_rules

    # `112006` THROUGH `112009` ARE RETIRED, 2026-10-08 with V3 and V4
    # (`harness_test_taxonomy.md` section 7.4.1.0). Two asserted that a retired rule
    # fires; the other two asserted that it does not, which a retired rule
    # satisfies by doing nothing at all. `112044` replaces all four with the
    # one statement still worth making, and the identifiers stay retired.

    def MQC_CMN_UNI_112044_the_retired_skip_ceilings_never_fire(self) -> None:
        """A population that breached both old ceilings breaches neither rule.

        30% of the skippable population skipped and every skip is in a blocking
        band, which is three times the old total ceiling and ten times the
        blocking-band one.

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [
            graded(f"MQC_TASK_{index}::MQC_RULE_r", priority=1) for index in range(7)
        ]
        observations += [
            graded(f"MQC_TASK_s{index}::MQC_RULE_r", "skip", priority=1,
                    skip_reason="environmental")
            for index in range(3)
        ]

        result = verdict(observations, VerdictConfig(), TODAY)
        assert result.skip_rate == pytest.approx(0.30)
        assert "V3" not in result.breached_rules
        assert "V4" not in result.breached_rules
        # AND THE RUN IS GREEN, which is the point of the retirement rather
        # than a side effect: an unreachable provider is not the model's
        # failure, so it leaves the rate the floor is measured over.
        assert result.green, f"an outage was charged to the model: {result.breaches}"




class TestMQCNothingMeasured:
    """V6: every way a run can measure nothing and look fine doing it."""

    def MQC_CMN_UNI_112013_red_when_no_observations_at_all(self) -> None:
        """A run that measured nothing must never report green.

        Every other rule passes vacuously over an empty set, which is exactly
        why this one exists.

        Returns:
            None
        """
        result = verdict([], VerdictConfig(), TODAY)
        assert result.green is False
        assert "V6" in result.breached_rules

    def MQC_CMN_UNI_112014_red_when_no_graded_observations(self) -> None:
        """Preconditions passing is not a measurement of the model.

        Returns:
            None
        """
        observations = [
            Observation(f"MQC_TASK_{index}::MQC_RULE_pre", "UNI", "pass")
            for index in range(5)
        ]
        result = verdict(observations, VerdictConfig(), TODAY)
        assert result.green is False
        assert "V6" in result.breached_rules

    def MQC_CMN_UNI_112015_red_when_every_graded_case_quarantined(self) -> None:
        """A suite that measured nothing is red, and now says 0% rather than none.

        **The mechanism changed on 2026-10-08, not the behaviour.** Quarantine
        used to empty the pass-rate denominator, so the run was red by V6 with
        no rate at all. A quarantined case now skips before dispatch and that
        skip counts as the failure it is, so the run is red by the floor and
        reports a rate of zero, which is the stronger statement: nobody has to
        know what V6 means to read it.

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [
            graded(
                f"MQC_TASK_{index}::MQC_RULE_r",
                outcome="skip",
                skip_reason="quarantined",
            )
            for index in range(3)
        ]
        quarantine = [
            QuarantineEntry(entry.case_id, "parked", date(2026, 9, 20))
            for entry in observations if entry.graded
        ]
        result = verdict(observations, VerdictConfig(quarantine=quarantine), TODAY)

        assert result.green is False
        assert "V2" in result.breached_rules
        assert result.pass_rate == pytest.approx(0.0)

    def MQC_CMN_UNI_112016_red_when_every_pair_unsupported(self) -> None:
        """The skip denominator is zero, which is not the same as no skips.

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [
            graded(f"MQC_TASK_{index}::MQC_RULE_r", "skip", skip_reason="unsupported")
            for index in range(4)
        ]

        result = verdict(observations, VerdictConfig(), TODAY)
        assert result.green is False
        assert "V6" in result.breached_rules
        assert result.skip_rate is None


class TestMQCDenominators:
    """What each metric counts, and what it deliberately does not."""

    def MQC_CMN_UNI_112017_dependency_skips_excluded_from_skip_denominator(self) -> None:
        """A foundational failure cascades, and counting the cascade misleads.

        The run is already red from V1. Counting the dependent skips would
        breach V3 as well, adding a derived failure on top of the real one and
        pointing diagnosis at the environment.

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [graded(f"MQC_TASK_{index}::MQC_RULE_r") for index in range(5)]
        observations += [
            graded(f"MQC_TASK_d{index}::MQC_RULE_r", "skip", skip_reason="dependency")
            for index in range(20)
        ]

        result = verdict(observations, VerdictConfig(), TODAY)
        assert result.skip_rate == pytest.approx(0.0)
        assert "V3" not in result.breached_rules

    def MQC_CMN_UNI_112018_unsupported_pairs_excluded_from_skip_denominator(self) -> None:
        """A declared capability gap is not an environmental failure (A13).

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [graded(f"MQC_TASK_{index}::MQC_RULE_r") for index in range(5)]
        observations += [
            graded(f"MQC_TASK_u{index}::MQC_RULE_r", "skip", skip_reason="unsupported")
            for index in range(20)
        ]

        result = verdict(observations, VerdictConfig(), TODAY)
        assert result.skip_rate == pytest.approx(0.0)
        assert "V3" not in result.breached_rules

    # `112019` IS RETIRED, 2026-10-08. Quarantine no longer leaves the
    # pass-rate denominator: it saves the cost of asking again about a known
    # failure and does not stop it being one (design section 4.6.12). The
    # identifier stays retired, and `112046` and `112048` state what replaced
    # it: a quarantined skip counts as a failure, and a recorded dispensation
    # is the one thing that releases it.

    def MQC_CMN_UNI_112020_security_layer_excluded_from_distribution_ceiling(self) -> None:
        """Security coverage does not compete with functional coverage.

        A ceiling exists to prevent priority inflation, and a security test
        going unwritten because the P0 quota was full is the ceiling doing
        harm. The exemption is read from the layer registration, not from the
        layer's name.

        Returns:
            None
        """
        measured = [
            Observation(f"MQC_TASK_{index}::MQC_RULE_r", "EVAL", "pass", priority=3)
            for index in range(40)
        ]
        security = [
            Observation(f"MQC_TASK_s{index}::MQC_RULE_r", "SEC", "pass", priority=0)
            for index in range(40)
        ]

        report = evaluate_distribution(measured + security, Thresholds())
        assert report.case_definitions == 40
        assert report.p0_share == pytest.approx(0.0)


class TestMQCPreconditionGate:
    """Preconditions sit above the scale, and what that costs when they fail."""

    def MQC_CMN_UNI_112021_precondition_failure_blocks_graded_evaluation(self) -> None:
        """Exit 3, not 1. Nothing was measured rather than something failing.

        Collapsing them would let CI treat a broken harness as an
        underperforming model, which sends the wrong person to investigate.

        Returns:
            None
        """
        observations = [
            Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "fail"),
            graded("MQC_TASK_x::MQC_RULE_r", "fail", priority=0),
        ]
        result = verdict(observations, VerdictConfig(), TODAY)

        assert result.exit_code == 3
        assert result.breached_rules == ["PRECONDITION_FAILED"]
        assert "V1" not in result.breached_rules

    def MQC_CMN_UNI_112022_precondition_skip_is_a_failure(self) -> None:
        """A unit test has nothing external to block it.

        A skip therefore means something is broken rather than unavailable,
        which is why zero skips are permitted rather than merely discouraged.

        Returns:
            None
        """
        observations = [
            Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "skip",
                        skip_reason="environmental"),
            graded("MQC_TASK_x::MQC_RULE_r"),
        ]
        assert verdict(observations, VerdictConfig(), TODAY).exit_code == 3


class TestMQCVerdictProperties:
    """What the function guarantees about itself."""

    def MQC_CMN_UNI_112023_reports_every_breached_rule_not_only_the_first(self) -> None:
        """Short-circuiting would cost a cycle per rediscovered breach.

        For a suite whose live runs are scheduled rather than on demand, fixing
        V1 and meeting V2 on the next run and the distribution on the one after
        is three cycles to reach a state one run could have reported.

        **The four rules it reads changed on 2026-10-08**, when V3 and V4 were
        retired: three failing P0 cases out of six breach V1, the pass floor,
        the P0 share ceiling and the combined share ceiling.

        Returns:
            None
        """
        # THIRTY DEFINITIONS, because the distribution rules report counts
        # without a verdict below that and a rule reporting no verdict cannot
        # demonstrate that every breach is reported.
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [
            graded(f"MQC_TASK_f{index}::MQC_RULE_r", "fail", priority=0)
            for index in range(4)
        ]
        observations += [
            graded(f"MQC_TASK_a{index}::MQC_RULE_r", priority=1) for index in range(7)
        ]
        observations += [
            graded(f"MQC_TASK_b{index}::MQC_RULE_r") for index in range(19)
        ]

        breached = verdict(observations, VerdictConfig(), TODAY).breached_rules
        assert {"V1", "V2", "V7", "V8", "V9"} <= set(breached)
        assert len(breached) >= 5

    def MQC_CMN_UNI_112024_verdict_is_pure_for_identical_input(self) -> None:
        """Identical input yields an identical verdict, every time.

        Returns:
            None
        """
        observations = passing_suite()
        first = verdict(observations, VerdictConfig(), TODAY)
        second = verdict(list(observations), VerdictConfig(), TODAY)
        assert first == second

    def MQC_CMN_UNI_112025_verdict_does_not_read_system_clock(self) -> None:
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

        entry = QuarantineEntry(
            "MQC_TASK_q::MQC_RULE_r", "flaky", date(2026, 10, 1),
            observed_model="gemini-3.8-flash",
        )
        past = verdict(passing_suite(), VerdictConfig(quarantine=[entry]), date(2026, 1, 1))
        future = verdict(
            passing_suite(), VerdictConfig(quarantine=[entry]), date(2027, 1, 1)
        )
        assert past.green is True
        assert future.green is False


class TestMQCDistribution:
    """The ceilings, and the population they are meaningful over."""

    def MQC_CMN_UNI_112026_distribution_check_returns_no_verdict_below_thirty_cases(self) -> None:
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
            VerdictConfig(), TODAY,
        ).green is True

    def MQC_CMN_UNI_112027_red_when_p0_share_exceeds_ten_percent(self) -> None:
        """An inflated P0 population turns the must-pass gate into a hair-trigger.

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [
            graded(f"MQC_TASK_p{index}::MQC_RULE_r", priority=0) for index in range(10)
        ]
        observations += [
            graded(f"MQC_TASK_{index}::MQC_RULE_r", priority=3) for index in range(30)
        ]

        result = verdict(observations, VerdictConfig(), TODAY)
        assert "V7" in result.breached_rules
        assert result.distribution.p0_share == pytest.approx(0.25)

    def MQC_CMN_UNI_112028_red_when_combined_p0_p1_exceeds_thirty_percent(self) -> None:
        """The combined ceiling catches inflation split across two bands.

        Without it, 10% at P0 and 20% at P1 would each pass while a third of
        the suite blocked every run.

        Returns:
            None
        """
        observations = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        observations += [
            graded(f"MQC_TASK_a{index}::MQC_RULE_r", priority=0) for index in range(4)
        ]
        observations += [
            graded(f"MQC_TASK_b{index}::MQC_RULE_r", priority=1) for index in range(12)
        ]
        observations += [
            graded(f"MQC_TASK_{index}::MQC_RULE_r", priority=3) for index in range(24)
        ]

        result = verdict(observations, VerdictConfig(), TODAY)
        assert result.distribution.combined_share == pytest.approx(0.40)
        assert "V9" in result.breached_rules

    def MQC_CMN_UNI_112029_distribution_check_reports_the_demoted_case_count(self) -> None:
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

    def MQC_CMN_UNI_112030_a_broken_graded_observation_blocks_and_exits_three(
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
        suite = passing_suite(20)
        suite.append(graded("MQC_TASK_x::MQC_RULE_r", outcome="broken", priority=3))

        result = verdict(suite, as_of_date=TODAY)

        assert not result.green
        assert result.exit_code == 3, (
            "a broken observation exited 1, which reads as a model regression"
        )
        assert any("broke" in breach.reason for breach in result.breaches)

        # ONE IS ENOUGH, at the lowest priority there is. A rule that only
        # fired at P0 would let the cheapest cases hide our own defects.
        single = passing_suite(50)
        single.append(graded("MQC_TASK_y::MQC_RULE_r", outcome="broken", priority=4))
        assert verdict(single, as_of_date=TODAY).exit_code == 3

        # AND IT IS OUT OF THE PASS RATE, so harness flakiness does not read as
        # model degradation in the headline number.
        assert outcome_properties("broken").counts_in_pass_rate is False

    def MQC_CMN_UNI_112031_an_incomplete_skip_blocks_however_few_there_are(
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

        suite = passing_suite(50)
        suite.append(
            graded(
                "MQC_TASK_z::MQC_RULE_r",
                outcome="skip",
                priority=4,
                skip_reason="incomplete",
            )
        )

        result = verdict(suite, as_of_date=TODAY)

        assert not result.green
        assert result.exit_code == 3
        assert any("unfinished" in breach.reason for breach in result.breaches)

    # `112032` IS RETIRED, 2026-10-08. It named a ceiling that no longer
    # exists and asserted a run over that ceiling was red, which the
    # reason-dependent treatment makes green: an outage is not the model's
    # failure at any rate. `112045` states the replacement.

    def MQC_CMN_UNI_112045_a_skip_we_caused_leaves_the_pass_rate(self) -> None:
        """An outage is not an unwritten case, and the reason says so.

        **Half the population skipping changes the rate by nothing**, which is
        the whole of the exclusion: a fixture that would not load and a
        provider that could not be reached say nothing about a model.

        Returns:
            None
        """
        suite = passing_suite(10)
        suite.extend(
            graded(
                f"MQC_TASK_e{index}::MQC_RULE_r",
                outcome="skip",
                priority=3,
                skip_reason="environmental",
            )
            for index in range(10)
        )

        result = verdict(suite, as_of_date=TODAY)

        assert result.pass_rate == pytest.approx(1.0), (
            "an outage entered the pass-rate denominator and was charged to "
            "the model"
        )
        assert result.green, f"an outage failed the run: {result.breaches}"
        assert result.exit_code == 0

    @pytest.mark.parametrize("reason", ["quarantined", "dependency", None])
    def MQC_CMN_UNI_112046_a_skip_the_model_caused_counts_as_a_failure(
        self, reason: object
    ) -> None:
        """Each reason naming a non-pass the model owns enters the denominator.

        ``None`` is included deliberately: a skip nobody attributed is not
        evidence that the model was blameless, so the default is to count it.

        **`incomplete` is absent because it blocks rather than rates.**
        Unfinished work makes the run unsound and leaves no pass rate at all to
        count it in, which `112031` asserts.

        Returns:
            None
        """
        suite = passing_suite(9)
        suite.append(
            graded(
                "MQC_TASK_z::MQC_RULE_r",
                outcome="skip",
                priority=3,
                skip_reason=reason,
            )
        )

        result = verdict(suite, as_of_date=TODAY)

        assert result.pass_rate == pytest.approx(0.90), (
            f"a {reason} skip left the pass-rate denominator"
        )

    def MQC_CMN_UNI_112047_a_counted_skip_never_reaches_the_numerator(self) -> None:
        """A skip is a non-pass whatever its reason, which no cause changes.

        Returns:
            None
        """
        for reason in ("quarantined", "dependency", "incomplete", "environmental",
                       "unsupported"):
            assert not outcome_properties("skip").is_pass, reason

        # AND A SUITE OF NOTHING BUT COUNTED SKIPS RATES AT ZERO, rather than
        # at the empty-population rate a filtered denominator would produce.
        suite = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
        suite.extend(
            graded(
                f"MQC_TASK_q{index}::MQC_RULE_r",
                outcome="skip",
                priority=3,
                skip_reason="quarantined",
            )
            for index in range(4)
        )

        assert verdict(suite, as_of_date=TODAY).pass_rate == pytest.approx(0.0)

    def MQC_CMN_UNI_112048_a_dispensed_quarantine_skip_leaves_the_pass_rate(
        self,
    ) -> None:
        """Product management's recorded decision is the one thing that excuses.

        **The entry has to be confirmed as well.** An entry carrying no
        observed date or model is our bookkeeping failing, and a dispensation
        on top of that accepts a release against a finding whose expiry cannot
        be evaluated.

        Returns:
            None
        """
        suite = passing_suite(9)
        suite.append(
            graded(
                "MQC_TASK_z::MQC_RULE_r",
                outcome="skip",
                priority=3,
                skip_reason="quarantined",
            )
        )
        entry = QuarantineEntry(
            case_id="MQC_TASK_z::MQC_RULE_r",
            reason="a finding under repair",
            quarantined_on=date(2026, 9, 20),
            observed_model="gemini-2.5-flash",
            release_accepted_in="MQC-914",
        )

        released = verdict(suite, VerdictConfig(quarantine=[entry]), TODAY)
        assert released.pass_rate == pytest.approx(1.0), (
            "a recorded dispensation did not release the skip"
        )

        # UNCONFIRMED, SO NOT HONOURED: the same reference on an entry with no
        # observed model leaves the skip exactly where it was.
        unconfirmed = QuarantineEntry(
            case_id="MQC_TASK_z::MQC_RULE_r",
            reason="a finding under repair",
            release_accepted_in="MQC-914",
        )
        refused = verdict(suite, VerdictConfig(quarantine=[unconfirmed]), TODAY)
        assert refused.pass_rate == pytest.approx(0.90), (
            "an unconfirmed entry released a blocker"
        )
