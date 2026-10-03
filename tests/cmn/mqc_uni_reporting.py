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

A failure here is our defect, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

from typing import Any, Optional

import pytest

from cmn.observations import Observation, RunContext
from cmn.reporting import observation_parameters, vendor_report

pytestmark = pytest.mark.unit

# Every field section 9 of `test_taxonomy.md` requires of a graded result,
# named here so the case compares against the standard rather than against
# whatever the builder happens to return.
_REQUIRED_RESULT_FIELDS = (
    "case_id", "layer", "observation_index", "engine", "mode",
    "requested_model", "resolved_model", "outcome", "taxonomy_code",
    "priority", "priority_conditions", "duration", "duration_kind",
    "output_tokens",
)

_REQUIRED_RUN_FIELDS = (
    "run_context", "selection_mode", "gated", "rule_set_hash", "os",
)


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
            family="requirement_match",
        )
        run = RunContext(
            run_context="ci", selection_mode="full", preconditions_executed=True,
            rule_set_hash="sha256:abc", platform="ubuntu-24.04",
        )

        parameters = observation_parameters(observation, run)

        missing = [
            name for name in _REQUIRED_RESULT_FIELDS + _REQUIRED_RUN_FIELDS
            if name not in parameters
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
