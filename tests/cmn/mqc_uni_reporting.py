# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""What a run publishes about an observation, and about a case that failed.

Covers ``MQC_CMN_UNI_112239`` and ``112240``, inventoried in
``docs/design/cmn_verdict_and_cli.md`` section 10 and designed in sections 5.1
to 5.4.

**Written 2026-10-02, after reading a real Allure result.** The mapping these
build has always been complete and nothing handed it to the artifact: a
published result carried empty parameters and a severity label, so a collector
could not say which engine produced it.

A failure here is **not a model finding**, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

from pathlib import Path
from typing import Any, Final, Optional

import allure
import pytest

from cmn.code_standards import required_result_fields
from cmn.metadata import emit_result
from cmn.observations import Observation, RunContext
from cmn.reporting import observation_parameters, vendor_report

from cmn.band_summary import band_label, band_lines, band_table, pass_rate

pytestmark = pytest.mark.unit

# FIELDS THE CODE DERIVES RATHER THAN THE TABLE DECLARING THEM. `gated` is
# computed from three others and 9.1 says so in its own row; the token counts
# are the nested `tokens` record flattened for the wire, which 9.1 covers as
# `output_tokens` and the emitter spells out. Design section 9.5.
_DERIVED_FIELDS: Final[frozenset[str]] = frozenset({
    "input_tokens", "thinking_tokens", "cached_input_tokens",
    "judge_input_tokens", "judge_output_tokens", "judge_thinking_tokens",
    "demoted", "self_preference", "provider_refusal", "tokens",
})

# FIELDS LEGITIMATELY ABSENT FROM A PARAMETER SET. An absent value is omitted
# rather than published empty, because an empty parameter reads as
# measured-and-empty; so a field the observation under test does not carry
# cannot be required of its parameters. Design `cmn_verdict_and_cli.md`
# section 5.2.
_ABSENT_WHEN_UNSET: Final[frozenset[str]] = frozenset({
    "families", "primary_family", "requirement_ids", "skip_reason", "score", "scale_id",
    "rubric_result", "quarantine_hash", "rule_set_hash", "timeout_ms",
    "cli_flags", "effective_thresholds",
})


class _FakeResponse:
    """A normalized response, as a dispatch outcome carries one."""

    def __init__(self, requested: str, resolved: str, text: str = "answer") -> None:
        """Hold what a vendor report reads off a response.

        Args:
            requested (str): The model asked for.
            resolved (str): The model served.
            text (str): What came back.

        Returns:
            None
        """
        self.requested_model = requested
        self.resolved_model = resolved
        self._text = text

    def as_mapping(self) -> dict[str, Any]:
        """Return the response as a serializable mapping.

        Returns:
            dict: The response fields.
        """
        return {
            "text": self._text,
            "requested_model": self.requested_model,
            "resolved_model": self.resolved_model,
            "finish_reason": "stop",
        }


class _FakeOutcome:
    """A dispatch outcome, as the vendor report reads one."""

    def __init__(
        self,
        index: int,
        *,
        response: Optional[_FakeResponse] = None,
        request: Optional[dict[str, Any]] = None,
        taxonomy_code: Optional[str] = None,
    ) -> None:
        """Hold one observation's call and what it produced.

        Args:
            index (int): Which observation this is.
            response (Optional[_FakeResponse]): What came back, absent on a
                harness event.
            request (Optional[dict]): What was sent.
            taxonomy_code (Optional[str]): The harness code, if any.

        Returns:
            None
        """
        self.observation_index = index
        self.engine = "gemini"
        self.mode = "live"
        self.response = response
        self.request = request
        self.taxonomy_code = taxonomy_code


class TestMQCResultEmission:
    """Every field the standard requires, as something a collector can read."""

    def MQC_CMN_UNI_112239_every_required_result_field_is_emitted(self) -> None:
        """Each field section 9 requires becomes a parameter to publish.

        Compared against the standard's list rather than against whatever the
        builder returns, so a field dropped from the builder is reported here
        instead of silently leaving the artifact.

        A structure is rendered to text, because a parameter is a column. An
        absent value is omitted rather than published empty: a precondition
        carries no priority and a pass carries no taxonomy code, and an empty
        parameter would read as measured-and-empty.

        Design: ``cmn_verdict_and_cli.md`` section 5.2.

        Returns:
            None
        """
        observation = Observation(
            case_id="MQC_TASK_a::MQC_RULE_r", layer="EVAL", outcome="fail",
            observation_index=2, priority=1, engine="gemini", mode="live",
            requested_model="gemini-3.8-flash-latest",
            resolved_model="gemini-3.8-flash",
            taxonomy_code="QC_LLM_SOURCE_ALTERATION",
            priority_conditions=["P1_SOURCED_FIGURE"],
            requirement_ids=["MQC_REQ_MDL_GND_0003"],
            duration=1.25, duration_kind="measured", output_tokens=96,
            families=("requirement_match",),
        )
        run = RunContext(
            run_context="ci", selection_mode="full", preconditions_executed=True,
            rule_set_hash="sha256:abc", platform="ubuntu-24.04",
        )

        parameters = observation_parameters(observation, run)

        # READ FROM THE STANDARD'S OWN TABLE, not from a copy of it. A case
        # asserting against its own list cannot report that the list moved,
        # which is how section 9 came to sit behind the code (section 9.5).
        required = required_result_fields(
            Path(__file__).resolve().parents[2]
            / "docs" / "design" / "test_taxonomy.md"
        )
        missing = [
            name for name in sorted(required)
            if name not in parameters and name not in _ABSENT_WHEN_UNSET
        ]
        assert not missing, (
            "fields the standard requires reach no parameter, so a collector "
            "cannot recover them from the artifact: " + ", ".join(missing)
        )

        # THE TWO THAT ATTRIBUTE A RESULT, which is what the artifact could not
        # say before this existed.
        assert parameters["engine"] == "gemini"
        assert parameters["resolved_model"] == "gemini-3.8-flash"
        assert parameters["mode"] == "live"

        # A STRUCTURE IS RENDERED, because a parameter is a column.
        assert parameters["priority_conditions"] == "P1_SOURCED_FIGURE"
        assert parameters["requirement_ids"] == "MQC_REQ_MDL_GND_0003"
        assert all(isinstance(value, str) for value in parameters.values())

        # AND AN ABSENT VALUE IS OMITTED, not published as empty.
        passing = Observation(
            case_id="MQC_TASK_a::MQC_RULE_r", layer="UNI", outcome="pass",
        )
        sparse = observation_parameters(passing)

        assert "taxonomy_code" not in sparse
        assert "priority" not in sparse
        assert sparse["outcome"] == "pass"


class TestMQCVendorReport:
    """A failing case publishes the calls a provider ticket is written from."""

    def MQC_CMN_UNI_112240_a_failing_case_reports_every_call_it_made(self) -> None:
        """A failing case reports every observation, not the failing one.

        Three observations with two more on a single disagreement means the
        failing call is frequently not the first, and an inconsistency finding
        is a claim about the set: a report carrying one call could not support
        it.

        An observation with no response contributes its taxonomy code and no
        call, which is what a skipped or broken one has to report. Credentials
        are removed before anything is returned.

        Design: ``cmn_verdict_and_cli.md`` section 5.3.

        Returns:
            None
        """
        calls = [
            _FakeOutcome(0, response=_FakeResponse("asked", "served", "right"),
                         request={"prompt": "Summarise", "api_key": "sk-live-secret"}),
            _FakeOutcome(1, response=_FakeResponse("asked", "served", "wrong"),
                         request={"prompt": "Summarise", "temperature": 0.0}),
            _FakeOutcome(2, taxonomy_code="QC_HARNESS_RATE_LIMIT"),
        ]
        report = vendor_report(
            "MQC_TASK_a::MQC_RULE_r", calls, [True, False, False]
        )

        assert report["case_id"] == "MQC_TASK_a::MQC_RULE_r"
        assert report["observations_taken"] == 3
        assert report["observations_passed"] == 1

        # EVERY CALL, INCLUDING THE ONE THAT PASSED. That observation is what
        # makes "answers the same question two ways" checkable.
        assert [entry["observation_index"] for entry in report["calls"]] == [0, 1, 2]
        assert [entry["passed"] for entry in report["calls"]] == [True, False, False]

        # THE PASSING CALL CARRIES ITS REQUEST AND RESPONSE, which is the half a
        # report built from the failure alone would omit.
        passed = report["calls"][0]
        assert passed["response"]["text"] == "right"
        assert passed["resolved_model"] == "served"

        # A HARNESS EVENT CARRIES ITS CODE AND NO CALL, because nothing was
        # measured and there is nothing to reproduce.
        broken = report["calls"][2]
        assert broken["taxonomy_code"] == "QC_HARNESS_RATE_LIMIT"
        assert "response" not in broken

        # AND THE CREDENTIAL IS GONE. A credential in a durable record is
        # disclosed to everyone who can read it.
        assert passed["request"]["api_key"] == "[REDACTED]"
        assert passed["request"]["prompt"] == "Summarise"
        assert "sk-live-secret" not in str(report)


class TestMQCNormativeFieldList:
    """The standard's own list, against what the code emits."""

    def MQC_CMN_UNI_112148_a_required_field_the_code_does_not_emit_is_reported(
        self,
    ) -> None:
        """Section 9.1's table and the emitted fields agree both ways.

        The list existed in three copies and nothing compared any pair, so
        adding a field to ``RunContext`` touched the code and neither list.

        **Both directions matter.** A field the standard requires and nothing
        emits is a promise to a reader that nothing keeps; a field the code
        emits and the standard never declared reached a durable record
        undocumented, which is how ``quarantine_hash`` arrived.

        **The scope column is load-bearing.** A run-scoped field is checked
        against ``RunContext.as_fields`` and a result-scoped one against
        ``emit_result``; comparing against the union would pass for the wrong
        reason.

        Design: ``test_taxonomy.md`` section 9.5.

        Returns:
            None
        """
        taxonomy = (
            Path(__file__).resolve().parents[2]
            / "docs" / "design" / "test_taxonomy.md"
        )
        declared = required_result_fields(taxonomy)

        observation = Observation(
            case_id="MQC_TASK_a::MQC_RULE_r", layer="EVAL", outcome="pass",
            priority=2, engine="gemini", mode="replay",
        )
        run = RunContext(
            run_context="ci", selection_mode="full", preconditions_executed=True,
        )
        emitted_result = set(emit_result(observation, run))
        emitted_run = set(run.as_fields())

        missing: list[str] = []
        for field, scope in sorted(declared.items()):
            against = emitted_run if scope == "Run" else emitted_result
            if field not in against:
                missing.append(f"{field} ({scope.lower()}-scoped)")
        assert not missing, (
            "section 9.1 requires fields the code does not emit, so the "
            "standard promises a reader what nothing delivers: "
            + ", ".join(missing)
        )

        # THE OTHER DIRECTION. `emit_result` folds the run-scoped half in, so a
        # field it carries is undeclared only when neither table scope has it.
        undeclared = sorted(
            (emitted_result | emitted_run) - set(declared) - _DERIVED_FIELDS
        )
        assert not undeclared, (
            "the code emits fields section 9.1 never declared, so they reach a "
            "durable record undocumented: " + ", ".join(undeclared)
        )


@allure.epic("AP-Harness-QC")
@allure.feature("Cross-cutting")
class TestMQCBandSummary:
    """What a band job states about its own selection."""

    @allure.story("A band states both of its denominators")
    def MQC_CMN_UNI_112332_a_band_summary_states_its_own_denominator(
        self,
    ) -> None:
        """The summary states an execution rate and a total rate, with fractions.

        **pytest's own last line reports what it declined to run.** A P1 job
        ended with 146 deselected, which is every precondition plus the other
        bands: the largest figure on the line, and nothing a rate divides into.

        **A skip is not a non-event, which is the correction of 2026-10-06.** A
        dependent is skipped to save cost, not because the case stopped
        mattering, and the reason is a failure upstream, an environment that
        was not set, or a defect in our scripts. A single rate dropping skips
        from its denominator flatters the run by exactly the number of cases it
        declined to measure.

        | Rate | Over | Answers |
        |---|---|---|
        | Execution | passed plus failed | Of what ran, how much held |
        | Total | everything selected | Of what the band set out to establish, how much it did |

        Design: ``cmn_verdict_and_cli.md`` section 7.11.

        Returns:
            None
        """
        blocked = ["QC_HARNESS_DEPENDENCY_UNMET: foundational case 1 did not hold"]
        reported = band_lines(
            passed=9, failed=3, skip_reasons=blocked * 3, priority="0"
        )
        assert len(reported) == 2, (
            f"a band states its counts and its rates, two lines: {reported}"
        )
        counts, rates = reported[0], reported[1]

        assert counts.startswith("Band P0: 15 total, 12 executed"), (
            f"the denominator is not the band's own selection: {counts}"
        )
        assert "3 skipped, 3 behind a higher band failure" in counts, (
            f"a dependency skip is not named, so a reader cannot tell it from "
            f"an environmental one: {counts}"
        )

        # BOTH RATES, AND THE GAP BETWEEN THEM IS THE COST OF THE SKIPS.
        assert "execution pass 75.0% (9 of 12)" in rates, (
            f"the execution rate is not over what ran: {rates}"
        )
        assert "total pass 60.0% (9 of 15)" in rates, (
            f"the total rate does not count the skips, so three cases the band "
            f"did not measure are invisible in its result: {rates}"
        )

        # NOTHING MEASURED YIELDS NO RATE. A zero denominator means the
        # question is unanswerable, which is never a hundred per cent.
        only_skips = band_lines(
            passed=0, failed=0, skip_reasons=blocked, priority="1"
        )[1]
        assert "execution pass no rate, nothing measured" in only_skips, (
            f"an empty execution denominator produced a rate: {only_skips}"
        )
        assert "total pass 0.0% (0 of 1)" in only_skips, (
            f"a band that measured nothing does not read as nothing "
            f"established: {only_skips}"
        )
        assert pass_rate(0, 0) is None, "a zero denominator returned a number"

        # AN EMPTY SELECTION SAYS NOTHING, because zeroes read as a clean run.
        assert not band_lines(passed=0, failed=0, skip_reasons=[], priority="4"), (
            "an empty selection printed a row of zeroes"
        )

        # AND THE LABEL FOLLOWS THE FILTER, so a reader knows what was asked.
        assert band_label("") == "Whole selection"
        assert band_label("2,3,4") == "Bands P2,P3,P4"

    @allure.story("A skip is named by the remedy it takes")
    def MQC_CMN_UNI_112049_each_kind_of_skip_is_named_by_its_remedy(self) -> None:
        """Three kinds, three phrases, and the counts add up to the total.

        A quarantined skip is a model finding somebody is already repairing; a
        cascaded one clears itself when the foundation is fixed; anything else
        is a fixture, a budget or a provider, which is ours. **Each takes a
        different act**, so a line collapsing two of them leaves a reader
        acting on the wrong one while the arithmetic stays right.

        Design: ``cmn_verdict_and_cli.md`` section 7.11.

        Returns:
            None
        """
        reasons = [
            "QC_HARNESS_DEPENDENCY_UNMET: foundational case 1 did not hold",
            "QC_HARNESS_QUARANTINED: MQC_TASK_a::MQC_RULE_r is quarantined",
            "QC_HARNESS_QUARANTINED: MQC_TASK_b::MQC_RULE_r is quarantined",
            "QC_HARNESS_FIXTURE_MISSING: no recording for this observation",
        ]
        counts = band_lines(
            passed=6, failed=0, skip_reasons=reasons, priority="1"
        )[0]

        assert "Band P1: 10 total, 6 executed" in counts, counts
        assert "4 skipped, 1 behind a higher band failure" in counts, (
            f"a cascaded skip is not named, so a reader cannot tell it from a "
            f"quarantined one: {counts}"
        )
        assert "2 a known failure in quarantine" in counts, (
            f"a quarantined skip read as our infrastructure wobbling, when it "
            f"is a model finding under repair: {counts}"
        )
        assert "1 for a reason of ours" in counts, counts

        # NO KIND IS COUNTED TWICE AND NONE IS LOST, which is what a reader
        # subtracting the named kinds from the total depends on.
        named = 1 + 2 + 1
        assert named == len(reasons)

        # AND A BAND WITH ONE KIND NAMES ONLY THAT KIND, so an absent phrase
        # means an absent cause rather than a suppressed one.
        parked_only = band_lines(
            passed=0, failed=0, skip_reasons=reasons[1:3], priority="0"
        )[0]
        assert "2 skipped, 2 a known failure in quarantine" in parked_only
        assert "higher band failure" not in parked_only
        assert "reason of ours" not in parked_only

        # A PRECONDITION IS THE FOURTH KIND AND NO REASON EXCUSES IT. "For a
        # reason of ours" reads as tolerated, and a precondition that did not
        # run measured nothing: the line says what followed instead
        # (`test_taxonomy.md` section 7.5.1).
        required = band_lines(
            passed=700,
            failed=0,
            skip_reasons=["a reason of ours"] * 4,
            preconditions_skipped=4,
        )[0]
        assert "704 total, 700 executed" in required, required
        assert "4 skipped, 4 a precondition, so the run exits 3" in required, (
            f"a skipped precondition reads as excused: {required}"
        )
        assert "reason of ours" not in required, (
            f"a precondition skip was offered a reason: {required}"
        )

    @allure.story("A healthy total never hides a blocking failure")
    def MQC_CMN_UNI_112333_a_band_table_total_overriding_a_blocking_band_is_reported(
        self,
    ) -> None:
        """The table names a blocking failure whatever the total says.

        **The total is the figure most likely to be quoted and the least able
        to answer the question.** A run can sit at 95% overall and carry a P0
        failure, and that run does not ship: P0 and P1 block, where a lower
        band is a bug to open and quarantine while review sets the date.

        **So the table states the blocking verdict separately**, and this case
        pins the one arrangement that would be worth nothing: a high total
        beside a silent blocking failure.

        Design: ``cmn_verdict_and_cli.md`` section 7.11.1.

        Returns:
            None
        """
        # ONE P0 FAILURE AMONG TWENTY-THREE PASSES. The total reads well and the
        # run does not ship.
        rendered = "\n".join(band_table([
            ("0", 4, 1, []),
            ("2,3,4", 19, 0, []),
        ]))
        assert "95.8%" in rendered, (
            f"the total is not stated, so a reader cannot see what the table "
            f"is warning them against reading: {rendered}"
        )
        assert "Release blocking: 1 failure(s) in P0 or P1." in rendered, (
            f"a P0 failure is not named beside a healthy total, which is the "
            f"one arrangement this table exists to prevent: {rendered}"
        )
        assert "The total decides nothing." in rendered, (
            "the table does not say what its own last row is worth"
        )

        # AND A CLEAN BLOCKING SET SAYS SO, rather than saying nothing.
        clean = "\n".join(band_table([("0", 5, 0, []), ("2,3,4", 1, 9, [])]))
        assert "No release blocking failure." in clean, (
            f"a clean P0 and P1 is not stated, so a reader cannot tell it from "
            f"a table that forgot to check: {clean}"
        )
