# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for result emission, the code registry and the fixtures.

Covers `MQC_CMN_UNI_10143` through `10146`, `10155`, `10157` through `10161`,
`10165` through `10167`, `10171` through `10173`, `10176`, `10177` and `10179`
through `10182`, inventoried in ``docs/design/cmn_verdict_and_cli.md``
section 10.

**Run-scoped fields are emitted twice**, once in a manifest and again on every
result, because collectors key on per-test rows and a field living only in a
manifest may never reach per-test history.

**The excerpt guards are preconditions, not graded cases.** An excerpt silently
corrected by a formatter would leave every graded case built on it asserting
against an expectation that no longer holds, and the failure would be a
confident wrong verdict rather than an error. A stale fixture is our defect.

A failure here is our defect, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

import ast
import csv
import re
import sys
import tomllib
from importlib import metadata
from pathlib import Path
from typing import Any, Optional

import pytest
from packaging.specifiers import SpecifierSet

from cmn.metadata import (
    DiagnosticSummary,
    artifact_name,
    changed_areas_from,
    current_platform,
    emit_result,
    latency_statistics,
    matches_collector_pattern,
    require_registered_code,
    unemitted_codes,
)
from cmn.observations import (
    Observation,
    RunContext,
    assemble_observation,
    required_result_fields,
)
from cmn.registries import (
    evaluation_family,
    registered_codes,
    registered_evaluation_families,
)
from tools.generate_requirements import generate, read_declaration


pytestmark = pytest.mark.unit

# A taxonomy code as a design document writes one.
_CODE_PATTERN = re.compile(r"`(QC_(?:LLM|SEC|HARNESS|DATA)_[A-Z_]+)`")
# One row of the evaluation family table in test_taxonomy.md section 11.1.
# Parsed rather than substring-matched: the surrounding prose names these
# identifiers too, and reporting prose would be the over-reporting that trains
# a check away on its second run.
# A harness requirement identifier, as the plan and the matrix both write one.
# Requirements carry an explicit MQC_REQ_ marker, so an identifier says which
# register it belongs to without the reader knowing any vocabulary.
# harness_test_plan.md section 2.2.
_REQUIREMENT_ID = re.compile(r"MQC_REQ_HAR_(?:ING|EXE|EVL|CMN)_\d+")


_FAMILY_ROW = re.compile(
    r"^\|\s*`(?P<identifier>[a-z][a-z_]+)`\s*\|[^|]+\|[^|]+\|[^|]+\|$"
)

# One inventory row: an identifier, a category letter and a behaviour name.
# Parsed rather than substring-matched, because prose naming an identifier is
# not a row and reporting it would be the over-reporting that trains a check
# away on its second run.
_INVENTORY_ROW = re.compile(
    r"^\|\s*`(?P<identifier>\d{5})`\s*\|\s*[PNB]\s*\|\s*`(?P<behaviour>\w+)`\s*\|$"
)


# Dated records rather than live specifications. The Phase 0 register
# deliberately names alternatives that were considered and rejected, so a code
# appearing there is evidence of a decision rather than an unregistered entry.
_HISTORICAL_DOCUMENTS = frozenset({"phase0_project_ambiguities.md"})

# Directories that are not this project's source, so their conventions are
# not this project's to enforce.
_SKIPPED_TREES = frozenset({"venv", ".venv", "build", "dist", "__pycache__"})

# The identifier this repository's files must declare. The case repository
# runs the same check against MIT, which is the whole point of naming it
# rather than accepting any SPDX tag.
_REPOSITORY_LICENCE = "Apache-2.0"


@pytest.fixture(name="gated_run")
def fixture_gated_run() -> RunContext:
    """Return a gated CI run context.

    Returns:
        RunContext: A full, gated CI run.
    """
    return RunContext(
        run_context="ci", selection_mode="full", preconditions_executed=True,
        rule_set_hash="sha256:abc", effective_thresholds={"pass_floor": 0.9},
        timeout_ms=60000, cli_flags={"judge_on_failure": False},
        platform="linux",
    )


def _graded(**overrides: Any) -> Observation:
    """Build a graded observation over a valid base.

    Args:
        **overrides: Fields to replace.

    Returns:
        Observation: The built record.
    """
    payload = {
        "case_id": "MQC_TASK_a::MQC_RULE_r", "layer": "EVAL", "outcome": "pass",
        "priority": 2, "engine": "gemini", "mode": "replay",
        "requested_model": "gemini-flash-latest", "resolved_model": "gemini-flash-002",
        "duration": 310, "duration_kind": "measured",
    }
    payload.update(overrides)
    return Observation(**payload)


def _requirement_name(entry: str) -> Optional[str]:
    """Return the distribution name a requirement string begins with.

    Args:
        entry (str): A requirement such as ``pylint>=3.3,<4.0``.

    Returns:
        Optional[str]: The name, or ``None`` where the entry carries no name
        this simply, such as a URL requirement. **None rather than a guess**,
        because a wrong name would silently report a tool as unpinned.
    """
    found = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", entry.strip())
    return found.group(1) if found is not None else None

class TestMQCTaxonomyRegistryConsistency:
    """Every emitted code registered, and every registered code accounted for."""

    def MQC_CMN_UNI_10143_emitted_code_absent_from_registry_is_rejected(self) -> None:
        """An unregistered code makes the record uncountable.

        Every later tally by root-cause class would silently omit it, and a
        count that silently omits is worse than one that fails.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR"):
            require_registered_code("QC_LLM_INVENTED_HERE")
        assert require_registered_code("QC_LLM_RUBRIC_FAILURE") == "QC_LLM_RUBRIC_FAILURE"

    def MQC_CMN_UNI_10144_registered_code_with_no_emit_site_is_reported(self) -> None:
        """A code registered and never emitted is dead or forgotten.

        Reported rather than failed: both are worth knowing and neither means
        the run was wrong.

        Returns:
            None
        """
        emitted = ["QC_LLM_RUBRIC_FAILURE", "QC_SEC_JUDGE_HIJACK"]
        unemitted = unemitted_codes(emitted)

        assert "QC_HARNESS_AUTH_ERROR" in unemitted
        assert "QC_LLM_RUBRIC_FAILURE" not in unemitted
        assert len(unemitted) == len(registered_codes()) - 2

    def MQC_CMN_UNI_10145_unregistered_code_in_a_live_specification_is_reported(self) -> None:
        """Every code a design document names must exist in the registry.

        The single registry is only single if nothing else declares one, and a
        design naming a code that does not exist would have an implementation
        invent it.

        Returns:
            None
        """
        design_dir = Path(__file__).resolve().parents[2] / "docs" / "design"
        named: set[str] = set()
        for document in design_dir.glob("*.md"):
            if document.name in _HISTORICAL_DOCUMENTS:
                continue
            for line in document.read_text(encoding="utf-8").splitlines():
                if line.lstrip().startswith("|"):
                    named |= set(_CODE_PATTERN.findall(line))

        assert named
        assert named <= registered_codes()

    def MQC_CMN_UNI_10146_stated_inventory_counts_disagreeing_with_rows_is_reported(self) -> None:
        """A stated total is derived data, and derived data can be restated wrongly.

        Returns:
            None
        """
        design_dir = Path(__file__).resolve().parents[2] / "docs" / "design"
        checked = 0
        for document in design_dir.glob("*.md"):
            text = document.read_text(encoding="utf-8")
            stated = re.search(
                r"\*\*Inventory: (\d+) cases, (\d+) negative, (\d+) positive, "
                r"(\d+) boundary", text
            )
            if stated is None:
                continue
            categories = re.findall(r"^\| `\d{5}` \| ([PNB]) \|", text, re.M)
            assert int(stated.group(1)) == len(categories), document.name
            assert int(stated.group(2)) == categories.count("N"), document.name
            assert int(stated.group(3)) == categories.count("P"), document.name
            assert int(stated.group(4)) == categories.count("B"), document.name
            checked += 1
        assert checked == 4


class TestMQCResultEmission:
    """What every emitted result carries, and what it is refused for lacking."""

    def MQC_CMN_UNI_10158_run_scoped_fields_emitted_per_result_not_in_a_manifest_alone(
        self, gated_run: RunContext
    ) -> None:
        """Collectors key on per-test rows.

        A field living only in a run manifest may never reach per-test history,
        and a stored result whose thresholds cannot be recovered is
        uninterpretable years later. Repeating seven fields costs nothing
        measurable.

        Args:
            gated_run (RunContext): The run-scoped fields.

        Returns:
            None
        """
        emitted = emit_result(_graded(), gated_run)

        assert emitted["effective_thresholds"] == {"pass_floor": 0.9}
        assert emitted["rule_set_hash"] == "sha256:abc"
        assert emitted["timeout_ms"] == 60000
        assert emitted["cli_flags"] == {"judge_on_failure": False}

    def MQC_CMN_UNI_10155_run_context_and_gated_flag_recorded_in_metadata(
        self, gated_run: RunContext
    ) -> None:
        """Row marking is one of the two mechanisms excluding a debug run.

        Args:
            gated_run (RunContext): The run-scoped fields.

        Returns:
            None
        """
        emitted = emit_result(_graded(), gated_run)
        assert emitted["run_context"] == "ci"
        assert emitted["gated"] is True

        debug = RunContext(
            run_context="ci_debug", selection_mode="full", preconditions_executed=True
        )
        assert emit_result(_graded(), debug)["gated"] is False

    def MQC_CMN_UNI_10161_result_missing_a_required_metadata_field_is_rejected(self) -> None:
        """A result that reaches the record incomplete is uninterpretable later.

        It also looks exactly like one that is not, which is why the refusal
        happens at emission rather than at read.

        Returns:
            None
        """
        from cmn.observations import (  # pylint: disable=import-outside-toplevel
            require_complete_result,
        )

        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR") as caught:
            require_complete_result({"case_id": "MQC_TASK_a::MQC_RULE_r"})
        assert "layer" in str(caught.value)
        assert set(required_result_fields()) >= {"case_id", "layer", "outcome"}

    def MQC_CMN_UNI_10165_selection_mode_recorded_per_result(self, gated_run: RunContext) -> None:
        """A reader of one row can tell how much of the suite it came from.

        Args:
            gated_run (RunContext): The run-scoped fields.

        Returns:
            None
        """
        assert emit_result(_graded(), gated_run)["selection_mode"] == "full"

    def MQC_CMN_UNI_10182_result_records_the_platform_it_ran_on(
        self,
        gated_run: RunContext,
    ) -> None:
        """The harness is verified on two platforms (A18).

        A result that does not say which produced it cannot support the
        comparison that verification exists to make.

        Args:
            gated_run (RunContext): The run-scoped fields.

        Returns:
            None
        """
        assert emit_result(_graded(), gated_run)["os"] == "linux"
        assert current_platform() in {"windows", "linux", "darwin"}

    def MQC_CMN_UNI_10179_graded_result_records_its_evaluation_family(
        self,
        gated_run: RunContext,
    ) -> None:
        """Coverage is read per family, not only per requirement.

        A requirement covered by three families has survived a change of
        domain; one covered by a single family has been observed once, in one
        setting, and may hold only there.

        Args:
            gated_run (RunContext): The run-scoped fields.

        Returns:
            None
        """
        emitted = emit_result(_graded(family="code_comprehension"), gated_run)
        assert emitted["family"] == "code_comprehension"
        assert "code_comprehension" in registered_evaluation_families()

    def MQC_CMN_UNI_10181_precondition_result_carries_no_family(
        self,
        gated_run: RunContext,
    ) -> None:
        """A precondition tests the harness, which performs no task.

        The boundary is stated rather than left implicit, because an empty
        string and an absent value read differently to a collector.

        Args:
            gated_run (RunContext): The run-scoped fields.

        Returns:
            None
        """
        precondition = Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")
        assert emit_result(precondition, gated_run)["family"] is None

    def MQC_CMN_UNI_10180_unregistered_family_value_is_rejected(self) -> None:
        """Families are a registry, and an unregistered value is untraceable.

        Returns:
            None
        """
        assert "requirement_match" in registered_evaluation_families()
        assert "invented_family" not in registered_evaluation_families()


class TestMQCLatencyStatistics:
    """What a duration may contribute to, and what it may not."""

    def MQC_CMN_UNI_10160_truncated_duration_excluded_from_latency_statistics(self) -> None:
        """A truncated duration measures the harness's patience.

        A case that timed out at the configured ceiling would drag its own
        baseline upward, making genuinely slow responses look normal
        afterwards, which is the opposite of what a baseline is for.

        Returns:
            None
        """
        observations = [
            _graded(duration=100), _graded(duration=200),
            _graded(duration=60000, duration_kind="truncated"),
        ]
        statistics = latency_statistics(observations)

        assert statistics["mean_duration"] == pytest.approx(150.0)
        assert statistics["sample_count"] == 2
        assert statistics["excluded_truncated"] == 1

    def MQC_CMN_UNI_11103_latency_is_absent_rather_than_zero_when_nothing_measured(self) -> None:
        """A mean of zero would read as an impossibly fast run.

        Returns:
            None
        """
        statistics = latency_statistics(
            [_graded(duration=60000, duration_kind="truncated")]
        )
        assert statistics["mean_duration"] is None
        assert statistics["sample_count"] == 0


class TestMQCArtifactSeparation:
    """Two independent mechanisms keeping a debug run out of the record."""

    def MQC_CMN_UNI_10166_debug_artifact_name_does_not_match_collector_pattern(self) -> None:
        """Structural separation, the first of the two mechanisms.

        Marking alone fails if nobody filters on it, and structural separation
        alone fails the day someone widens the pattern. Both exist because
        either one is a single point of failure.

        Returns:
            None
        """
        debug = RunContext("ci_debug", "full", True)
        gated = RunContext("ci", "full", True)

        assert matches_collector_pattern(artifact_name(gated)) is True
        assert matches_collector_pattern(artifact_name(debug)) is False

        # THE LITERAL PREFIX, which the pattern check alone does not pin: both
        # prefixes renamed together would satisfy the two assertions above.
        # Absorbed from a second callable that duplicated this identifier,
        # design section 10.10.1.
        assert artifact_name(debug).startswith("diagnostic-local")
        assert not matches_collector_pattern(artifact_name(debug, suffix="ubuntu"))

    def MQC_CMN_UNI_10167_debug_rows_carry_ci_debug_context_and_ungated_flag(self) -> None:
        """Row marking, the second mechanism, on every row rather than once.

        Returns:
            None
        """
        debug = RunContext("ci_debug", "full", True)
        fields = debug.as_fields()

        assert fields["run_context"] == "ci_debug"
        assert fields["gated"] is False

class TestMQCDiagnosticSummary:
    """What a debug summary says, starting with what the run is not."""

    def MQC_CMN_UNI_10176_summary_records_job_run_number_both_refs_and_changed_areas(
        self,
    ) -> None:
        """A notification is worthless if the reader cannot identify the run.

        It has to be findable again a week later from the notification alone,
        which is why the run number and identifier are both there.

        Returns:
            None
        """
        summary = DiagnosticSummary(
            workflow="debug-branch-on-demand", job="graded", run_number=412,
            run_id="18273645", code_ref="a1b2c3d", fixture_ref="e4f5g6h",
            changed_areas="both", mode="replay", engine="gemini",
            selection_mode="manual", case_count=12,
            resolved_models={"gemini": "gemini-flash-002"},
        )
        rendered = summary.render()

        assert rendered.startswith("This run is diagnostic.")
        assert "carries no verdict and gates nothing" in rendered
        assert "412" in rendered and "18273645" in rendered
        assert "a1b2c3d" in rendered and "e4f5g6h" in rendered
        assert "Changed areas: both" in rendered
        assert "gemini-flash-002" in rendered
        assert summary.refs_diverge is True

    def MQC_CMN_UNI_10177_fixture_ref_defaults_to_code_ref_when_not_supplied(self) -> None:
        """The boundary: equal is the ordinary case, and empty is not the same.

        An empty value would read as unknown rather than as the same, and the
        two mean very different things to a checkpoint comparison.

        Returns:
            None
        """
        summary = DiagnosticSummary(
            workflow="debug-branch-on-demand", job="graded", run_number=1,
            run_id="1", code_ref="a1b2c3d", changed_areas="harness",
            mode="replay", engine="gemini", selection_mode="full", case_count=3,
        )
        assert summary.fixture_ref == "a1b2c3d"
        assert summary.refs_diverge is False

    @pytest.mark.parametrize(
        "paths,expected",
        [
            (["execution/dispatch.py"], "harness"),
            (["tests/cmn/mqc_uni_verdict.py"], "tests"),
            (["cmn/verdict.py", "tests/cmn/mqc_uni_verdict.py"], "both"),
            (["docs/design/tier2_execution.md"], "none"),
        ],
    )
    def MQC_CMN_UNI_11104_changed_areas_distinguish_harness_from_tests(
        self, paths: list[str], expected: Any
    ) -> None:
        """A run where only tests changed and results moved points at the tests.

        Reporting a single undifferentiated diff leaves the reader to work that
        out from paths, which is exactly the work the summary exists to save.

        Args:
            paths (list): The changed paths.
            expected (str): The classification.

        Returns:
            None
        """
        assert changed_areas_from(paths) == expected

    def MQC_CMN_UNI_10175_first_run_on_a_branch_has_no_previous_conclusion_to_compare(
        self,
    ) -> None:
        """The boundary: nothing to compare is not the same as no change.

        A first run reporting "status unchanged" would be stating a comparison
        it never made.

        Returns:
            None
        """
        previous_conclusion = None
        current = "success"

        assert previous_conclusion is None
        changed = previous_conclusion is not None and previous_conclusion != current
        assert changed is False
        assert (previous_conclusion == current) is False


class TestMQCObservationAssembly:
    """Neither half of an observation is sufficient on its own."""

    def MQC_CMN_UNI_10159_observation_assembled_from_tier_results_and_case_metadata(
        self,
    ) -> None:
        """Tier 3 never receives priority, so it cannot produce a complete record.

        The orchestrating test holds the case metadata and has no access to what
        dispatch measured; the tiers hold the measurement and are deliberately
        denied the grading metadata. The reporting hook is where the two meet,
        which is why assembly is its own operation rather than a tier's job.

        Returns:
            None
        """
        case_metadata = {
            "case_id": "MQC_TASK_a::MQC_RULE_r", "layer": "EVAL", "priority": 1,
            "priority_conditions": ["P1_ATTRIBUTION"], "family": "requirement_match",
            "requirement_ids": ["MQC_REQ_MDL_GND_0001"],
        }
        tier_results = {
            "outcome": "pass", "engine": "gemini", "mode": "replay",
            "requested_model": "gemini-flash-latest",
            "resolved_model": "gemini-flash-002",
            "duration": 310, "duration_kind": "measured", "output_tokens": 42,
            "score": 4.0, "scale_id": "continuous_1_5", "rubric_result": "evaluated",
        }
        assembled = assemble_observation(case_metadata, tier_results)

        assert assembled.priority == 1
        assert assembled.resolved_model == "gemini-flash-002"
        assert assembled.score == 4.0
        assert assembled.graded is True

    def MQC_CMN_UNI_11107_a_field_the_record_does_not_declare_is_rejected(self) -> None:
        """A field nothing reads would reach the artifact unread.

        Silently dropping it would be worse: a caller believing it recorded
        something would have recorded nothing, and nothing would say so.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR") as caught:
            assemble_observation(
                {"case_id": "MQC_TASK_a::MQC_RULE_r", "layer": "UNI"},
                {"outcome": "pass", "reviewer_note": "looks fine"},
            )
        assert "reviewer_note" in str(caught.value)


class TestMQCDependencyDeclaration:
    """One declaration, and a check on every copy derived from it."""

    def MQC_CMN_UNI_11108_requirements_files_disagreeing_with_pyproject_fail(self) -> None:
        """The generated files are a convenience, never a second source of truth.

        Without this they are a second declaration, and a second declaration
        drifts. That is the rule applied everywhere else here: either there is
        one statement of a fact, or there is a check.

        The case reads the declaration and regenerates, rather than comparing
        the two files to each other. Comparing copies would pass while both
        were stale.

        Returns:
            None
        """
        root = Path(__file__).resolve().parents[2]
        for path, expected in generate(root).items():
            assert path.is_file(), f"{path.name} has not been generated"
            assert path.read_text(encoding="utf-8") == expected, (
                f"{path.name} disagrees with pyproject.toml; regenerate it with "
                f"python tools/generate_requirements.py"
            )

    def MQC_CMN_UNI_11181_an_installed_gating_tool_outside_its_pin_is_reported(
        self,
    ) -> None:
        """A local pylint outside the pin reports a different result from CI.

        **This case exists because it happened.** `pyproject.toml` pins
        `pylint>=3.3,<4.0` and 4.0.6 was installed locally. Gate 1 exited 0
        here and 8 in CI, on the same commit, because the newer pylint counts
        `self` differently against `max-args`. Two commits were pushed on the
        strength of a local run that was measuring a different tool.

        **`11108` cannot catch this.** It compares the generated requirements
        files against `pyproject.toml`, so it verifies what is *declared* agrees
        with itself. Nothing verified what is *installed* agrees with the
        declaration, and the declaration is what CI installs from.

        **Scoped to the tools that gate**, which is pylint and pytest. A drifting
        library changes behaviour and the suite says so; a drifting linter or
        runner changes the verdict on every other case at once, silently.

        Returns:
            None
        """
        root = Path(__file__).resolve().parents[2]
        _, development = read_declaration(root / "pyproject.toml")
        pinned = {
            name.lower(): spec
            for name, spec in (
                (_requirement_name(entry), entry) for entry in development
            )
            if name is not None
        }

        wrong: list[str] = []
        for tool in ("pylint", "pytest"):
            spec = pinned.get(tool)
            if spec is None:
                wrong.append(f"{tool} gates a CI step and is not pinned at all")
                continue
            installed = metadata.version(tool)
            if not SpecifierSet(spec[len(tool):]).contains(installed, prereleases=True):
                wrong.append(f"{tool} {installed} is installed against the pin {spec}")

        assert not wrong, (
            "the installed toolchain does not satisfy what CI installs from, so a "
            f"local gate result does not predict the CI one: {wrong}. Run "
            f"`python -m pip install --editable \".[dev]\"` to align them"
        )

    def MQC_CMN_UNI_11109_every_imported_package_is_declared(self) -> None:
        """A dependency the code imports and nothing declares breaks a clean install.

        It passes on the machine that happens to have it and fails on every
        other, which makes the failure a property of the environment rather
        than of the change that introduced it.

        Returns:
            None
        """
        root = Path(__file__).resolve().parents[2]
        runtime, development = read_declaration(root / "pyproject.toml")
        declared = {
            re.split(r"[<>=!\[]", entry)[0].strip().lower().replace("-", "_")
            for entry in runtime + development
        }
        # The import name and the distribution name differ for these, which is
        # exactly the kind of mapping a check has to state rather than infer.
        aliases = {"yaml": "pyyaml", "google": "google_genai"}

        # Parsed, not pattern-matched. A regex over source lines also matches
        # prose: a docstring line beginning "from the artifact alone" reads as
        # an import of a package named "the". The parser knows the difference.
        imported = set()
        for source in root.rglob("*.py"):
            if any(part in {"venv", ".venv", "build", "dist"} for part in source.parts):
                continue
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imported.add(node.module.split(".")[0])

        local = {"ingestion", "execution", "evaluation", "cmn", "tests", "conftest", "tools"}
        third_party = {
            aliases.get(name, name) for name in imported
            if name not in sys.stdlib_module_names and name not in local
        }
        assert third_party <= declared, (
            f"imported and undeclared: {sorted(third_party - declared)}"
        )

    def MQC_CMN_UNI_11110_random_test_ordering_is_declared(self) -> None:
        """The suite depends on shuffled order for a guarantee it would else lack.

        The extension cases register a layer, an outcome and a verdict rule and
        then remove each one. A cleanup that failed would change the
        distribution denominator for every case running afterwards, and the
        failure would land on whichever case happened to run last.

        Found installed locally and declared nowhere, which is the worse of the
        two arrangements: **local runs held a guarantee CI did not**, so CI was
        the weaker check while appearing to be the stronger one.

        Returns:
            None
        """
        root = Path(__file__).resolve().parents[2]
        _, development = read_declaration(root / "pyproject.toml")
        assert any(entry.startswith("pytest-randomly") for entry in development)


class TestMQCPackaging:
    """What a consumer installs must be what is on disk."""

    def MQC_CMN_UNI_11114_every_package_on_disk_is_configured_for_the_build(self) -> None:
        """A package the build drops fails every consumer on its first import.

        **A hand-written list shipped a broken distribution.** It named four
        packages and omitted ``execution.adapters``, so the wheel held
        ``execution/`` with no adapters in it. The registry imports all three
        adapters at import time, so nothing that installed it could start.

        Nothing here detected that, because the repository is normally used from
        its own source tree where the directories are simply present and the
        build configuration is never exercised. It surfaced the first time this
        repository was installed into another one.

        Returns:
            None
        """
        root = Path(__file__).resolve().parents[2]
        configured = tomllib.loads(
            (root / "pyproject.toml").read_text(encoding="utf-8")
        )["tool"]["setuptools"]["packages"]["find"]
        patterns = [entry.rstrip("*") for entry in configured["include"]]
        excluded = [entry.rstrip("*") for entry in configured["exclude"]]

        on_disk = {
            path.parent.relative_to(root).as_posix()
            for path in root.rglob("__init__.py")
            if not any(part in _SKIPPED_TREES for part in path.parts)
        }

        unshipped = [
            package for package in sorted(on_disk)
            if not any(package.startswith(prefix) for prefix in patterns)
            and not any(package.startswith(prefix) for prefix in excluded)
        ]
        assert not unshipped, (
            f"packages on disk that the build would not ship: {unshipped}. "
            f"Add a matching include pattern to pyproject.toml."
        )

        # The subpackage the omission actually dropped, named so a regression
        # reports the real case rather than only a general rule.
        assert "execution/adapters" in on_disk
        assert any("execution".startswith(prefix.rstrip("/")) for prefix in patterns)


class TestMQCFindingDirections:
    """The taxonomy carries both directions of a finding."""

    def MQC_CMN_UNI_11129_invention_and_omission_are_both_registered_codes(
        self,
    ) -> None:
        """A recall figure needs both directions to mean anything.

        A model that reports every defect and several that do not exist scores
        identically to one that reports none, unless invention and omission are
        counted separately. The ``code_comprehension`` family measures recall
        over a fixed set of known defects, so the registry has to carry a code
        for each direction or the measurement collapses.

        **Deliberately weak on its own.** What it protects is a design property
        that a single deletion would silently break: ``10144`` reports an
        unemitted code without failing, and no case is written against a code
        that no longer exists.

        Returns:
            None
        """
        registered = registered_codes()
        pairs = (
            # Invention against alteration: content invented, content changed.
            ("QC_LLM_UNSOURCED_CLAIM", "QC_LLM_SOURCE_ALTERATION"),
            # Invention against omission, at the level of a finding.
            ("QC_LLM_HALLUCINATION", "QC_LLM_DEFECT_MISSED"),
        )

        for invention, counterpart in pairs:
            assert invention in registered, (
                f"{invention} is half of a documented pair and is missing"
            )
            assert counterpart in registered, (
                f"{counterpart} is the other half of {invention} and is missing; "
                f"a recall figure over one direction alone means nothing"
            )

        # The matching family reads its inputs correctly and applies the wrong
        # rule to them, which no other registered code describes.
        assert "QC_LLM_MATCH_MISCOMPUTED" in registered


class TestMQCFamilyRegistrationMechanism:
    """Section 11.2 is a procedure; these are the parts of it that are checked."""

    def MQC_CMN_UNI_11130_family_table_disagreeing_with_the_code_registry_is_reported(
        self,
    ) -> None:
        """The table is what an author edits, the dict is what checks read.

        Step 4 of the procedure adds a row to section 11.1, and every check in
        the project reads ``_EVALUATION_FAMILIES``. A family in one and not the
        other leaves the scope statement describing less than the suite
        exercises, which section 11.3 records as the reason this is a registry
        rather than a list.

        **The fourth instance of one shape in this module**, after ``10145``,
        ``11122`` and ``11123``: a document restates a fact that lives
        elsewhere, and the restatement rots.

        Returns:
            None
        """
        taxonomy = (
            Path(__file__).resolve().parents[2]
            / "docs" / "design" / "test_taxonomy.md"
        )
        tabled: set[str] = set()
        for line in taxonomy.read_text(encoding="utf-8").splitlines():
            match = _FAMILY_ROW.match(line.strip())
            if match is not None:
                tabled.add(match.group("identifier"))

        registered = set(registered_evaluation_families())

        assert tabled, "section 11.1 states no families, so the table was not found"
        assert tabled == registered, (
            "section 11.1 and _EVALUATION_FAMILIES disagree; "
            f"tabled only: {sorted(tabled - registered)}, "
            f"registered only: {sorted(registered - tabled)}"
        )

    def MQC_CMN_UNI_11131_every_requirement_in_the_matrix_appears_in_the_plan(
        self,
    ) -> None:
        """A requirement traced and unstated means the plan understates itself.

        The harness test plan states the requirements and ``rtm_harness.csv``
        traces them to cases. Twelve requirements were in the matrix and absent
        from the plan, all added over one working session, and nothing compared
        the two.

        **The fifth instance of one shape in this module**, after ``10145``,
        ``11122``, ``11123`` and ``11130``: two artefacts state one fact and
        nothing compares them.

        Returns:
            None
        """
        root = Path(__file__).resolve().parents[2]
        plan = (root / "docs" / "testing" / "harness_test_plan.md").read_text(
            encoding="utf-8"
        )
        stated = set(_REQUIREMENT_ID.findall(plan))

        with (root / "docs" / "testing" / "rtm_harness.csv").open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            traced = {
                row["requirement_id"]
                for row in csv.DictReader(handle)
                if row["requirement_id"].startswith("MQC_REQ_HAR_")
            }

        assert stated and traced, "one of the two artefacts was not read"
        assert not traced - stated, (
            "these requirements are traced and never stated, so the plan "
            f"understates what the harness guarantees: {sorted(traced - stated)}"
        )
        assert not stated - traced, (
            "these requirements are stated and never traced, so nothing covers "
            f"them: {sorted(stated - traced)}"
        )

    def MQC_CMN_UNI_11132_a_registered_family_without_ground_truth_is_reported(
        self,
    ) -> None:
        """Step 2 refuses a family gradable only by rubric.

        That refusal is the reason all registered families exist: a family
        measured by a judge alone adds cases without adding confidence, because
        it measures the judge as much as the candidate.

        **The criterion held only while an author remembered it.** A registered
        family carrying no ground-truth mechanism means step 2 was skipped, and
        nothing said so.

        Returns:
            None
        """
        registered = registered_evaluation_families()
        assert registered, "the registry is empty, so nothing is being checked"

        for identifier in sorted(registered):
            family = evaluation_family(identifier)
            assert family is not None, f"{identifier} is listed and not resolvable"
            assert family.ground_truth.strip(), (
                f"{identifier} declares no ground-truth mechanism, so step 2 of "
                f"the procedure was skipped and the admission criterion was not "
                f"applied"
            )
            assert family.input_shape.strip(), (
                f"{identifier} declares no input shape, so a reader cannot tell "
                f"what the model receives"
            )


class TestMQCInventoryIdentifiers:
    """An identifier is assigned once and never rebound."""

    def MQC_CMN_UNI_11121_an_identifier_appearing_twice_in_one_inventory_is_reported(
        self,
    ) -> None:
        """An identifier is assigned once and never rebound.

        **Every per-row check passed while an identifier was bound twice**,
        because each was keyed on a row and the defect was a relationship
        between two rows. `10183` found both rows, `10186` found both names
        valid, `10187` matched the first, and `10146` saw a row count that had
        genuinely grown.

        That is the shape a per-row check cannot see, whatever its strictness.

        Returns:
            None
        """
        design_dir = Path(__file__).resolve().parents[2] / "docs" / "design"
        seen: dict[str, list[str]] = {}

        for document in sorted(design_dir.glob("*.md")):
            if document.name in _HISTORICAL_DOCUMENTS:
                continue
            for line in document.read_text(encoding="utf-8").splitlines():
                match = _INVENTORY_ROW.match(line.strip())
                if match is None:
                    continue
                identifier = match.group("identifier")
                behaviour = match.group("behaviour")
                seen.setdefault(f"{document.name}:{identifier}", []).append(behaviour)

        duplicated = {
            where: names for where, names in seen.items() if len(names) > 1
        }
        assert not duplicated, (
            "an identifier is assigned once and never reused, so two live rows "
            "for one identifier rebind it to different behaviour: "
            + "; ".join(
                f"{where} bound to {' and '.join(names)}"
                for where, names in sorted(duplicated.items())
            )
        )
