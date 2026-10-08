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

A failure here is **not a model finding**, so the module carries no priority marker.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from cmn.observations import Observation, further_observations
from cmn.replay_audit import divergent_recordings
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

    def MQC_CMN_UNI_112036_any_failure_earns_two_further_observations(
        self,
    ) -> None:
        """Three runs to pass; any failure earns two more, and five is the floor.

        The boundary is between zero failures and one. Agreement earns none
        because there is nothing to refine and nothing to report; one, two and
        three failures of three each earn two, and a case already at five earns
        none because the rule escalates once.

        **Three of three escalates too**, which the earlier rule did not do. It
        asked what the verdict needs, and the verdict is binary and settled by
        the first disagreement; what escalation serves is the figure a reader
        outside this project weighs, where "always, on three attempts" and
        "five of five" are different claims.

        Design: ``cmn_verdict_and_cli.md`` sections 4.9.2.1 and 4.9.2.2.

        Returns:
            None
        """
        # THE BOUNDARY, EITHER SIDE OF IT. Agreement earns nothing; the first
        # failure earns the escalation.
        assert further_observations([True, True, True]) == 0, (
            "three passes earned further observations, which buys a more "
            "precise zero on a case that produced no finding"
        )
        for outcomes in (
            [True, True, False],
            [True, False, False],
            [False, False, False],
        ):
            passed = sum(outcomes)
            assert further_observations(outcomes) == 2, (
                f"{passed} of 3 passed earned no escalation, so the finding "
                f"would be filed as a third rather than a fifth"
            )

        # ONCE ONLY: a fifth is the legible number the decision asked for, and
        # a tenth is a later decision with its own arithmetic.
        assert further_observations([True, True, True, True, False]) == 0
        assert further_observations([False, False, False, False, False]) == 0

        # A SINGLE SAMPLE CANNOT DISAGREE WITH ITSELF, which is what
        # `consistent` answers for the same reason.
        assert further_observations([True]) == 0
        assert further_observations([False]) == 0
        assert further_observations([]) == 0


    def MQC_CMN_UNI_112335_a_case_whose_recordings_disagree_on_the_request_is_reported(
        self, tmp_path: Path
    ) -> None:
        """Recordings for one case answer one request, or the store says so.

        **The defect this guards was unread for a day.** Observations four and
        five of one task carried a request hash from before a prompt changed,
        and the escalation rule never drew them, so nothing complained.
        Widening that rule at 4.9.2.1 draws them, and the case would have
        skipped on ``QC_HARNESS_FIXTURE_STALE`` at the moment it was trying to
        establish a rate.

        Design: ``cmn_verdict_and_cli.md`` section 12.4.1.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        folder = tmp_path / "claude" / "MQC_TASK_alpha" / "MQC_RULE_alpha"
        folder.mkdir(parents=True)
        for index, digest in enumerate(("aaa111", "aaa111", "bbb222")):
            (folder / f"{index}.json").write_text(
                json.dumps({"request_hash": digest, "response": {}}),
                encoding="utf-8",
            )

        problems = divergent_recordings(tmp_path)
        assert len(problems) == 1, (
            f"a half refreshed store was not reported, so the stale half waits "
            f"for an escalation to find it: {problems}"
        )
        assert "MQC_TASK_alpha" in problems[0], (
            f"the report does not name the case, so nobody can act on it: "
            f"{problems[0]}"
        )
        assert "2" in problems[0], (
            f"the report does not name which observation diverged: "
            f"{problems[0]}"
        )

        # AND A STORE THAT AGREES IS SILENT, or the check reports every case.
        (folder / "2.json").write_text(
            json.dumps({"request_hash": "aaa111", "response": {}}),
            encoding="utf-8",
        )
        assert not divergent_recordings(tmp_path), (
            "a consistent store was reported, so the check cannot tell a "
            "refreshed case from a stale one"
        )

        # A JUDGEMENT SCORES ONE RESPONSE, so its request carries that
        # response and every observation's judgement answers a legitimately
        # different request. Requiring agreement there reported the whole
        # store on its first run against real fixtures.
        judged = (tmp_path / "judgements" / "claude" / "gemini"
                  / "MQC_TASK_alpha" / "MQC_RULE_alpha")
        judged.mkdir(parents=True)
        for index, digest in enumerate(("ddd444", "eee555", "fff666")):
            (judged / f"{index}.json").write_text(
                json.dumps({"request_hash": digest, "reply": {}}),
                encoding="utf-8",
            )
        assert not divergent_recordings(tmp_path), (
            "judgements were required to answer one request, which reports "
            "every case in the store and hides the candidate recordings that "
            "genuinely diverged"
        )

        # ONE RECORDING CANNOT DISAGREE WITH ITSELF, which is the answer
        # `further_observations` gives a single observation for the same reason.
        lone = tmp_path / "grok" / "MQC_TASK_beta" / "MQC_RULE_beta"
        lone.mkdir(parents=True)
        (lone / "0.json").write_text(
            json.dumps({"request_hash": "ccc333", "response": {}}),
            encoding="utf-8",
        )
        assert not divergent_recordings(tmp_path), (
            "a case holding one recording was reported as disagreeing"
        )
