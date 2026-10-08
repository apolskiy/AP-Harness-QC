# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""What a run hands to the artifact, and what a failing case attaches.

Covers ``MQC_CMN_UNI_112251`` through ``112253``, inventoried in
``docs/design/cmn_verdict_and_cli.md`` section 10 and designed in sections 5.2
to 5.4.1.

**Written 2026-10-03, closing the gap section 5.1 recorded.** Every part of the
record shipped and nothing published it, so a real Allure result carried empty
parameters and a severity label and a collector could not say which engine
produced it.

``112253`` runs a real pytest invocation with a real reporter, because the
claim is about what reaches the artifact and the earlier defect was invisible
to every case that asserted against the builders.

A failure here is **not a model finding**, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

import json
import sys
from pathlib import Path
from typing import Any, Optional

import pytest

from cmn import emission
from cmn.observations import Observation, RunContext

from tests.cmn.subprocess_support import run_bounded

pytestmark = pytest.mark.unit


class _Recorder:
    """A stand-in for the Allure runtime, recording what was published."""

    def __init__(self) -> None:
        """Hold the parameters, labels and attachments a hook emits.

        Returns:
            None
        """
        self.parameters: dict[str, str] = {}
        self.labels: dict[str, str] = {}
        self.attachments: list[tuple[str, str]] = []
        self.dynamic = self
        self.attachment_type = self

    JSON = "application/json"

    def parameter(self, name: str, value: str) -> None:
        """Record a published parameter.

        Args:
            name (str): The parameter name.
            value (str): Its rendered value.

        Returns:
            None
        """
        self.parameters[name] = value

    def label(self, name: str, value: str) -> None:
        """Record a published label.

        Args:
            name (str): The label name.
            value (str): Its value.

        Returns:
            None
        """
        self.labels[name] = value

    def attach(
        self, body: str, name: str = "", attachment_type: Any = None
    ) -> None:
        """Record an attachment.

        Args:
            body (str): The attachment body.
            name (str): What it is called.
            attachment_type (Any): Its media type.

        Returns:
            None
        """
        del attachment_type
        self.attachments.append((name, body))


class _Report:
    """The phase report the hook reads."""

    def __init__(
        self, *, when: str = "call", passed: bool = True, skipped: bool = False
    ) -> None:
        """Hold the phase and the outcome.

        Args:
            when (str): Which phase this reports.
            passed (bool): Whether the case passed.
            skipped (bool): Whether it skipped. **A skipped report is not
                passed either**, which is what made reading ``passed`` alone
                insufficient once a skip began recording an observation.

        Returns:
            None
        """
        self.when = when
        self.passed = passed
        self.skipped = skipped


class _Item:
    """The pytest item the hook names the case from."""

    def __init__(self, name: str) -> None:
        """Hold the test's name.

        Args:
            name (str): The callable's name.

        Returns:
            None
        """
        self.name = name


class _Response:
    """A normalized response, as a dispatch outcome carries one."""

    def __init__(self, resolved: str, text: str) -> None:
        """Hold what a vendor report reads off a response.

        Args:
            resolved (str): The model that served the call.
            text (str): What came back.

        Returns:
            None
        """
        self.requested_model = "asked-for"
        self.resolved_model = resolved
        self._text = text

    def as_mapping(self) -> dict[str, Any]:
        """Return the response as a serializable mapping.

        Returns:
            dict: The response fields.
        """
        return {"text": self._text, "finish_reason": "stop"}


class _Outcome:
    """A dispatch outcome, as the vendor report reads one."""

    def __init__(
        self, index: int, *, resolved: str = "served", text: str = "answer",
        request: Optional[dict[str, Any]] = None,
    ) -> None:
        """Hold one observation's call.

        Args:
            index (int): Which observation this is.
            resolved (str): The model that served it.
            text (str): What came back.
            request (Optional[dict]): What was sent.

        Returns:
            None
        """
        self.observation_index = index
        self.engine = "gemini"
        self.mode = "live"
        self.response = _Response(resolved, text)
        self.request = request or {"prompt": "Summarise"}
        self.taxonomy_code = None


def _observation(index: int, *, outcome: str = "pass", **overrides: Any) -> Observation:
    """Return a graded observation at the given index.

    Args:
        index (int): Which observation this is.
        outcome (str): ``pass`` or ``fail``.
        **overrides (Any): Further fields.

    Returns:
        Observation: The record.
    """
    fields: dict[str, Any] = {
        "case_id": "MQC_TASK_a::MQC_RULE_r",
        "layer": "SEC",
        "outcome": outcome,
        "observation_index": index,
        "priority": 1,
        "priority_conditions": ["P1_SOURCED_FIGURE"],
        "engine": "gemini",
        "mode": "live",
        "requested_model": "asked-for",
        "resolved_model": "served",
        "families": ("injection_resistance",),
    }
    fields.update(overrides)
    return Observation(**fields)


class TestMQCPublishedRecord:
    """The record this project builds, as something a collector reads."""

    def MQC_CMN_UNI_112251_a_recorded_observation_publishes_its_fields(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Every field reaches a parameter, with the case's population beside it.

        **The parameters describe the case and the attachment the
        observations.** Allure parameters are one flat list per test and a case
        takes three observations or five, so the fields come from the
        representative observation: the first failing one, and the first
        otherwise.

        ``resolved_models`` appears only where more than one model served the
        case, which is the unsound-run condition section 4.9.6 gates on and is
        otherwise already published as ``resolved_model``.

        **A precondition publishes nothing**, which is correct rather than a
        gap: it measures the harness and has no observation of a model.

        Design: ``cmn_verdict_and_cli.md`` section 5.2.1.

        Returns:
            None
        """
        recorder = _Recorder()
        monkeypatch.setattr(emission, "allure", recorder)
        emission.begin_case(RunContext(
            run_context="ci", selection_mode="full", preconditions_executed=True,
        ))
        emission.record_observation(_observation(0), _Outcome(0))
        emission.record_observation(_observation(1), _Outcome(1))

        published = emission.publish_result(_Item("MQC_EVL_SEC_154100_x"), _Report())

        assert published == 2
        assert recorder.parameters["engine"] == "gemini"
        assert recorder.parameters["resolved_model"] == "served"
        assert recorder.parameters["layer"] == "SEC"
        assert recorder.parameters["observations_taken"] == "2"
        assert recorder.parameters["observations_passed"] == "2"
        assert recorder.parameters["primary_family"] == "injection_resistance"

        # ONE MODEL SERVED THE CASE, so the aggregate is not published: it
        # would repeat `resolved_model` and say nothing.
        assert "resolved_models" not in recorder.parameters

        # A PASS CARRIES NO CODE, so no label and no attachment.
        assert not recorder.labels
        assert not recorder.attachments

        # A SECOND MODEL IS WHAT MAKES THE AGGREGATE WORTH PUBLISHING.
        emission.begin_case()
        emission.record_observation(_observation(0), _Outcome(0))
        emission.record_observation(
            _observation(1, resolved_model="served-later"), _Outcome(1, resolved="served-later")
        )
        emission.publish_result(_Item("MQC_EVL_SEC_154100_x"), _Report())

        assert recorder.parameters["resolved_models"] == "served;served-later"

        # AND A CASE THAT RECORDED NOTHING PUBLISHES NOTHING, rather than
        # republishing its predecessor's measurements.
        emission.begin_case()
        assert emission.publish_result(_Item("MQC_CMN_UNI_112251_x"), _Report()) == 0

        # NOR DOES A PHASE THAT IS NOT THE CALL, where no verdict is known.
        emission.record_observation(_observation(0), _Outcome(0))
        assert emission.publish_result(
            _Item("MQC_EVL_SEC_154100_x"), _Report(when="setup")
        ) == 0

    def MQC_CMN_UNI_112050_a_skipped_case_publishes_and_files_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The observation reaches the artifact and no vendor report is written.

        **A skipped report is not a passing one**, so the attachment condition
        could not read ``passed`` alone once a skip began recording an
        observation: every quarantined case would have filed a report about a
        response nobody received.

        Design: ``cmn_verdict_and_cli.md`` section 5.3, and
        ``test_taxonomy.md`` section 7.4.1.2 for what the skip records.

        Returns:
            None
        """
        recorder = _Recorder()
        monkeypatch.setattr(emission, "allure", recorder)
        emission.begin_case(RunContext(
            run_context="ci", selection_mode="full", preconditions_executed=True,
        ))
        emission.record_observation(
            _observation(
                0, outcome="skip", taxonomy_code="QC_HARNESS_QUARANTINED"
            ),
            None,
        )

        published = emission.publish_result(
            _Item("MQC_EVL_SEC_154100_x"), _Report(passed=False, skipped=True)
        )

        # THE OBSERVATION IS PUBLISHED, which is what gives the pass rate a
        # skip to count at all.
        assert published == 1, (
            "a skipped case published nothing, so the rate has no skip to count"
        )
        assert recorder.labels["taxonomy_code"] == "QC_HARNESS_QUARANTINED"

        # AND NOTHING IS FILED. A skip holds no response for a provider to
        # read, so a vendor report about one is noise in a durable record.
        assert not recorder.attachments, (
            f"a skipped case filed a vendor report about a response nobody "
            f"received: {recorder.attachments}"
        )

    def MQC_CMN_UNI_112252_a_failing_case_attaches_its_history(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failing case attaches every call, and the representative is the failure.

        **Every observation, including the ones that passed.** A single
        disagreement earns two more, so the failing call is frequently not the
        first, and ``QC_LLM_INCONSISTENT`` is a claim about the set that no
        single call can support.

        The representative observation is the first failing one, so the
        published ``taxonomy_code`` describes the failure rather than whichever
        observation was dispatched first.

        Design: ``cmn_verdict_and_cli.md`` sections 5.2.1 and 5.3.

        Returns:
            None
        """
        recorder = _Recorder()
        monkeypatch.setattr(emission, "allure", recorder)
        emission.begin_case(RunContext(
            run_context="ci", selection_mode="full", preconditions_executed=True,
        ))
        emission.record_observation(
            _observation(0), _Outcome(0, text="right", request={"api_key": "sk-live-secret"})
        )
        emission.record_observation(
            _observation(1, outcome="fail", taxonomy_code="QC_LLM_SOURCE_ALTERATION"),
            _Outcome(1, text="wrong"),
        )

        emission.publish_result(_Item("MQC_EVL_SEC_154100_x"), _Report(passed=False))

        # THE REPRESENTATIVE IS THE FAILURE, not the first observation.
        assert recorder.parameters["taxonomy_code"] == "QC_LLM_SOURCE_ALTERATION"
        assert recorder.parameters["observations_passed"] == "1"
        assert recorder.labels["taxonomy_code"] == "QC_LLM_SOURCE_ALTERATION"

        assert len(recorder.attachments) == 1
        name, body = recorder.attachments[0]
        assert name == "vendor-report"
        attached = json.loads(body)

        # EVERY CALL, INCLUDING THE ONE THAT PASSED.
        assert attached["observations_taken"] == 2
        assert [entry["passed"] for entry in attached["calls"]] == [True, False]
        assert attached["calls"][0]["response"]["text"] == "right"

        # AND THE CREDENTIAL IS GONE, because a credential in a durable record
        # is disclosed to everyone who can read it.
        assert attached["calls"][0]["request"]["api_key"] == "[REDACTED]"
        assert "sk-live-secret" not in body


class TestMQCPublishedToARealReporter:
    """The claim is about the artifact, so a real reporter produces one."""

    def MQC_CMN_UNI_112253_the_published_fields_reach_a_real_allure_result(
        self, tmp_path: Path
    ) -> None:
        """A real run writes a result carrying the parameters and the attachment.

        **Every earlier case asserted against the builders**, and the builders
        were never the gap: ``emit_result`` returned the whole section 9
        mapping and had no caller, so a published result carried empty
        parameters while every case about the mapping passed. Section 5.1 was
        established by reading a raw result rather than the code meant to
        produce it, and this is that reading, automated.

        It also establishes where the emission is possible: a parameter, a
        label and an attachment all reach the open result from
        ``pytest_runtest_makereport`` on the call phase, which is the only hook
        holding both halves.

        Design: ``cmn_verdict_and_cli.md`` sections 5.2.1.2 and 5.4.

        Returns:
            None
        """
        root = Path(__file__).resolve().parents[2]
        (tmp_path / "conftest.py").write_text(
            "\n".join([
                '"""A reporting hook and nothing else."""',
                "",
                "from typing import Any",
                "",
                "import pytest",
                "",
                "from cmn.emission import begin_case, publish_result",
                "",
                "",
                "def pytest_runtest_setup(item: pytest.Item) -> None:",
                '    """Clear the previous case.',
                "",
                "    Args:",
                "        item (pytest.Item): The test about to run.",
                "",
                "    Returns:",
                "        None",
                '    """',
                "    del item",
                "    begin_case()",
                "",
                "",
                "@pytest.hookimpl(hookwrapper=True)",
                "def pytest_runtest_makereport(item: pytest.Item, call: Any) -> Any:",
                '    """Publish what the case recorded.',
                "",
                "    Args:",
                "        item (pytest.Item): The test that ran.",
                "        call (Any): The phase being reported.",
                "",
                "    Returns:",
                "        Any: The hook result.",
                '    """',
                "    del call",
                "    outcome = yield",
                "    publish_result(item, outcome.get_result())",
            ]) + "\n",
            encoding="utf-8",
        )
        (tmp_path / "test_emits.py").write_text(
            "\n".join([
                '"""One failing case that records two observations."""',
                "",
                "from cmn.emission import record_observation",
                "from cmn.observations import Observation, RunContext",
                "",
                "",
                "def test_a_failing_case() -> None:",
                '    """Record two observations and fail.',
                "",
                "    Returns:",
                "        None",
                '    """',
                "    shared = dict(",
                '        case_id="MQC_TASK_a::MQC_RULE_r", layer="SEC", priority=1,',
                '        priority_conditions=["P1_SOURCED_FIGURE"], engine="gemini",',
                '        mode="live", resolved_model="gemini-3.8-flash",',
                '        families=("injection_resistance",),',
                "    )",
                "    record_observation(Observation(",
                '        outcome="pass", observation_index=0, **shared',
                "    ))",
                "    record_observation(Observation(",
                '        outcome="fail", observation_index=1,',
                '        taxonomy_code="QC_LLM_SOURCE_ALTERATION", **shared',
                "    ))",
                '    assert False, "deliberate"',
            ]) + "\n",
            encoding="utf-8",
        )

        results = tmp_path / "allure"
        completed = run_bounded(
            [
                sys.executable, "-m", "pytest", "-q", "-p", "no:randomly",
                "-p", "allure_pytest",
                "--alluredir", str(results), str(tmp_path / "test_emits.py"),
            ],
            cwd=root,
            env={**_environment(), "PYTHONPATH": str(root)},
        )
        assert "1 failed" in completed.stdout + completed.stderr, (
            f"the probe suite did not run:\n{(completed.stdout + completed.stderr)[-700:]}"
        )

        written = sorted(results.glob("*-result.json"))
        assert len(written) == 1, f"expected one result, found {len(written)}"
        published = json.loads(written[0].read_text(encoding="utf-8"))
        parameters = {
            entry["name"]: entry["value"]
            for entry in published.get("parameters", [])
        }

        # THE THREE FIELDS SECTION 5.1 FOUND MISSING, which is what made the
        # engine comparison unattributable from the artifact.
        assert parameters, "the result carried no parameters, which is the defect itself"
        assert parameters["engine"] == "'gemini'"
        assert parameters["mode"] == "'live'"
        assert parameters["resolved_model"] == "'gemini-3.8-flash'"

        # AND THE REPRESENTATIVE IS THE FAILURE, with its code as a label.
        assert parameters["taxonomy_code"] == "'QC_LLM_SOURCE_ALTERATION'"
        assert parameters["observations_passed"] == "'1'"
        assert any(
            entry["name"] == "taxonomy_code"
            and entry["value"] == "QC_LLM_SOURCE_ALTERATION"
            for entry in published.get("labels", [])
        ), "the taxonomy code reached no label, so root-cause class is unfilterable"

        # AND THE REPRODUCTION TRAVELS WITH IT.
        assert [entry["name"] for entry in published.get("attachments", [])] == [
            "vendor-report"
        ]


def _environment() -> dict[str, str]:
    """Return the parent environment, for a subprocess that needs the path.

    Returns:
        dict[str, str]: The current environment.
    """
    import os  # pylint: disable=import-outside-toplevel

    return dict(os.environ)
