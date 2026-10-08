# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The numbered steps an observation passes through, and where it stopped.

Covers ``MQC_CMN_UNI_112336`` and ``112337``, inventoried in
``docs/design/cmn_verdict_and_cli.md`` section 12 and specified by
``docs/design/test_taxonomy.md`` section 8.

**Section 8 specified this from the project's beginning and nothing emitted a
step.** Zero of sixty-nine test modules across both repositories called
`allure.step`, and neither matrix carried a row for section 8, so nothing
reported the absence: a requirement nobody wrote has no case to trace.

A failure here is **not a model finding**, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

from types import SimpleNamespace
from typing import Final

import pytest

from cmn.steps import ledger, stopped_at, stopped_line, summary

from tests.cmn.steps_support import dispatched, evaluated

pytestmark = pytest.mark.unit

_CASE: Final[str] = "MQC_TASK_alpha::MQC_RULE_alpha"

# FOURTEEN PHASES: seven steps, each an action and a verification. Section 8
# requires both, and a step declaring only an action is one nobody verified.
_PHASES: Final[int] = 14


class TestMQCStepLedger:
    """What a reader is told when a case failed partway through."""

    def MQC_CMN_UNI_112336_a_ledger_names_every_step_and_the_phase_it_stopped_at(
        self,
    ) -> None:
        """Seven steps, two phases each, and the ones that never ran.

        **An early stop hides every later failure**, in the harness and in the
        model both, so the steps nobody reached are reported rather than
        omitted. Section 8.1 keeps the two phases apart because a step can fail
        in either and the diagnoses differ: an action that could not be
        performed is ours and skips, a verification that did not hold is a
        measurement and fails.

        Design: ``test_taxonomy.md`` section 8.

        Returns:
            None
        """
        # A CASE THAT PASSED: every phase ran and nothing stopped.
        entries = ledger(dispatched(), evaluated())
        assert len(entries) == _PHASES, (
            f"a ledger of {len(entries)} phases cannot be seven steps of two, "
            f"so a step is declared without a verification or the reverse"
        )
        assert stopped_at(entries) is None, (
            "a passing observation reports a stop, so every failing one is "
            "indistinguishable from it"
        )
        assert not stopped_line(entries), (
            "a passing observation carries a stopped line, which would reach "
            "every failure message that appends one"
        )

        # AN ASSERTION THAT DID NOT HOLD: the verification fails and the judge
        # steps never run.
        failed = ledger(dispatched(), evaluated(
            assertion_results=[
                SimpleNamespace(
                    passed=False, assertion_id="A_ALPHA",
                    detail="required substring absent",
                    taxonomy_code="QC_LLM_SOURCE_ALTERATION",
                )
            ],
            score=None,
            judge_skipped_reason="assertions failed",
        ))
        halt = stopped_at(failed)
        assert halt is not None and halt.number == 5 and halt.phase == "VERIFY", (
            f"the stop is not reported at the verification of step 5: {halt}"
        )
        assert halt.taxonomy_code == "QC_LLM_SOURCE_ALTERATION", (
            f"the stop carries no model code, so a reader cannot classify it: "
            f"{halt}"
        )
        unrun = [entry for entry in failed if entry.outcome == "not run"]
        assert len(unrun) == 4, (
            f"{len(unrun)} phases are reported as unrun where steps 6 and 7 "
            f"are four, so the steps an early stop hides are not all named"
        )
        assert "4 later phase(s) did not run" in stopped_line(failed), (
            f"the line does not say how much went unmeasured: "
            f"{stopped_line(failed)}"
        )

        # A STEP THAT COULD NOT BE PERFORMED, which is ours and not the
        # model's: section 8.1 makes it a skip, and every later step is unrun.
        stale = ledger(
            dispatched(taxonomy_code="QC_HARNESS_FIXTURE_STALE", response=None),
            None,
        )
        halt = stopped_at(stale)
        assert halt is not None and halt.number == 2, (
            f"a response that never arrived is not reported at step 2: {halt}"
        )
        assert halt.taxonomy_code == "QC_HARNESS_FIXTURE_STALE", (
            f"the stop does not name the harness code, so an instrument defect "
            f"reads as "
            f"a model finding: {halt}"
        )

        # AND EVERY LINE CARRIES THE CASE, per section 8.2.
        lines = summary(_CASE, failed)
        assert all(line.startswith(_CASE) for line in lines), (
            "a line omits the case identifier, so a collector cannot attribute "
            "it"
        )
        assert all("STEP_" in line for line in lines[:_PHASES]), (
            "a phase line carries no STEP_ name, so nothing parses it"
        )

    def MQC_CMN_UNI_112337_a_rule_without_a_rubric_reports_its_judge_steps_inapplicable(
        self,
    ) -> None:
        """A suite decided by its assertions did not stop short.

        **Twenty-one security rules and eight tool rules author no rubric**,
        declaring themselves decided by their deterministic checks. Reading
        their unjudged steps as an early halt would report every one of them as
        having stopped early, which is the boundary this case holds.

        Design: ``test_taxonomy.md`` section 8.2.1.

        Returns:
            None
        """
        entries = ledger(
            dispatched(), evaluated(rubric_authored=False, score=None)
        )
        judge = [entry for entry in entries if entry.number >= 6]
        assert len(judge) == 4, "steps 6 and 7 are not four phases"
        assert all(entry.outcome == "not applicable" for entry in judge), (
            f"a rubricless rule reports its judge steps as something other "
            f"than inapplicable: {[entry.outcome for entry in judge]}"
        )
        assert stopped_at(entries) is None, (
            "a rule decided by its assertions is reported as having stopped "
            "early, which would describe the whole security suite that way"
        )
        assert not stopped_line(entries), (
            "a rubricless rule carries a stopped line, which would append to "
            "every security failure message"
        )
        assert "not applicable" in summary(_CASE, entries)[-1], (
            f"the closing line does not say the rest was inapplicable: "
            f"{summary(_CASE, entries)[-1]}"
        )

        # AND A RULE THAT DOES AUTHOR ONE STILL REPORTS A MISSING JUDGEMENT,
        # or this exemption would swallow the gap it was written beside.
        absent = ledger(dispatched(), evaluated(
            score=None, judge_skipped_reason="judgement_unavailable",
            taxonomy_codes=["QC_HARNESS_FIXTURE_MISSING"],
        ))
        halt = stopped_at(absent)
        assert halt is not None and halt.number == 6, (
            f"a rubric that went unscored is not reported: {halt}"
        )
        assert halt.taxonomy_code == "QC_HARNESS_FIXTURE_MISSING", (
            f"the missing judgement does not name its code: {halt}"
        )
