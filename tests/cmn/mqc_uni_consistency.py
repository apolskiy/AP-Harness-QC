# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Repeat observations that disagree, and what a run does about it.

Covers the cases design section 4.9 specifies: a case whose observations
disagree is a finding, enough of them unsound the run, a score moving inside
the passing band is recorded and gates nothing, and a single failure earns two
further observations.

**Split from ``mqc_uni_verdict.py`` on 2026-10-01**, which crossed the
thousand-line ceiling. The two subjects are separable: that module decides what
a verdict is from outcomes it is given, and this one decides whether those
outcomes characterise anything.

A failure here is our defect, so the module carries no priority marker.
"""

from datetime import date

import pytest

from cmn.observations import Observation, further_observations
from cmn.verdict import (
    inconsistency_rate,
    inconsistent_cases,
    score_spread,
    verdict,
)

pytestmark = pytest.mark.unit

_TODAY = date(2026, 9, 23)


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

    def MQC_CMN_UNI_112033_a_case_whose_observations_disagree_is_a_finding(
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

    def MQC_CMN_UNI_112034_inconsistency_at_the_ceiling_unsounds_the_run(
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
        # FIVE CASES, ONE INCONSISTENT: a rate of exactly 0.20, which is the
        # ceiling as of 2026-10-01. A boundary is tested AT the threshold,
        # never near it, so the denominator moved with the ceiling rather than
        # the case being left to pass by a margin.
        observations: list[Observation] = self._observed(
            "MQC_CASE_wobbly", ["pass", "fail", "pass"]
        )
        for number in range(4):
            observations += self._observed(
                f"MQC_CASE_steady_{number}", ["pass", "pass", "pass"]
            )

        assert inconsistency_rate(observations) == 0.20
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


    def MQC_CMN_UNI_112035_a_score_moving_inside_the_band_is_recorded_not_gated(
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

    def MQC_CMN_UNI_112036_one_disagreement_earns_two_further_observations(
        self,
    ) -> None:
        """One failed observation of three earns two more; nothing else earns any.

        The boundary is one failure exactly. Zero, two and three earn none, and
        a case already at five earns none because the rule escalates once.
        Fewer than two outcomes earn none, there being nothing to compare.

        Counts failures rather than the smaller group, so two failures of three
        do not escalate as though one had.

        Design: ``cmn_verdict_and_cli.md`` sections 4.9.2.1 and 4.9.2.2.

        Returns:
            None
        """
        # THE BOUNDARY, AT ITS VALUE. One failure of three earns two more.
        assert further_observations([True, True, False]) == 2

        # AND EVERY NEIGHBOUR EARNS NOTHING.
        assert further_observations([True, True, True]) == 0
        assert further_observations([True, False, False]) == 0
        assert further_observations([False, False, False]) == 0

        # ONCE ONLY: a fifth is the legible number the decision asked for.
        assert further_observations([True, True, True, True, False]) == 0

        # A SINGLE SAMPLE CANNOT DISAGREE WITH ITSELF, which is what
        # `consistent` answers for the same reason.
        assert further_observations([True]) == 0
        assert further_observations([]) == 0
