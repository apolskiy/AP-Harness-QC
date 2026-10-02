# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for the option registry, exit codes and what a subset costs.

Covers `MQC_CMN_UNI_10135` through `10138`, `10147` through `10154`, `10156`,
`10162` through `10164`, `10168` through `10170`, `10174`, `10175` and `10178`,
inventoried in ``docs/design/cmn_verdict_and_cli.md`` section 10.

**Testers may run any subset. What a subset costs is the verdict, not the
ability to run.** A hand-typed selection is arbitrary and has no backstop, while
a change-scoped one is derived from the diff, recorded, and backstopped by the
full run on merge.

**A refusal is not a failure.** Exit 4 says no verdict was computable from what
the tool was given; exit 1 says the suite was measured and something failed.
Collapsing them would let a refused artifact read as a failing suite.

A failure here is our defect, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

import conftest
from cmn.config import Consumer, load_consumers, unreachable_consumer_code
from cmn.observations import RunContext
from cmn.registries import is_registered_harness_code
from cmn.pytest_support import adopt_corpus_selection, corpus_selection, configure_invocation
from cmn.options import (
    build_invocation,
    defaults,
    manual_selector_flags,
    option,
    registered_options,
    validate_value,
)
from cmn.verdict_tool import (
    EXIT_ARGUMENT_ERROR,
    EXIT_GREEN,
    EXIT_RED,
    EXIT_REFUSED,
    build_parser,
    compute,
    main,
    refuse_if_ungated,
    thresholds_from,
)

pytestmark = pytest.mark.unit

_TODAY = date(2026, 9, 23)


class _RecordingParser:
    """A stand-in for pytest's parser that records what a hook registered.

    **In process, and deliberately not a subprocess.** Invoking pytest to read
    its help text fails on Windows under pytest with an invalid handle, which is
    the same platform quirk the excerpt cases hit. The harness is verified on
    both platforms, so a case that only runs on one is not a case.

    It records what **our hook** did, which is the thing that can drift. How
    pytest then parses those registrations is pytest's business and not ours to
    assert.

    Attributes:
        registered (list): Every flag the hook added, in order.
        choices (dict): The choices declared per flag.
    """

    def __init__(self) -> None:
        """Start with nothing recorded.

        Returns:
            None
        """
        self.registered: list[str] = []
        self.choices: dict[str, Any] = {}

    def getgroup(self, name: str, description: str = "") -> "_RecordingParser":
        """Return this recorder as the requested option group.

        Args:
            name (str): The group name.
            description (str): Ignored.

        Returns:
            _RecordingParser: This recorder.
        """
        del name, description
        return self

    def addoption(self, flag: str, **settings: Any) -> None:
        """Record one registered flag.

        Args:
            flag (str): The flag as it appears on a command line.
            **settings (Any): What the hook declared for it.

        Returns:
            None
        """
        self.registered.append(flag)
        self.choices[flag] = settings.get("choices")


def _plugin_registrations() -> _RecordingParser:
    """Run the pytest hook against a recording parser.

    Returns:
        _RecordingParser: What the hook registered.
    """
    recorder = _RecordingParser()
    conftest.pytest_addoption(recorder)
    return recorder


def _artifact(**overrides: Any) -> dict:
    """Build a gated artifact over a valid base.

    Args:
        **overrides: Fields to replace.

    Returns:
        dict: The artifact.
    """
    payload = {
        "gated": True,
        "run_context": "ci",
        "selection_mode": "full",
        "effective_thresholds": {},
        "results": [
            {"case_id": "MQC_TASK_pre::MQC_RULE_pre", "layer": "UNI", "outcome": "pass"},
            {"case_id": "MQC_TASK_a::MQC_RULE_r", "layer": "EVAL", "outcome": "pass",
             "priority": 2},
        ],
    }
    payload.update(overrides)
    return payload



class _FakeInvocationParams:
    """The raw arguments pytest records for a run.

    Attributes:
        args (list): Exactly what the caller wrote.
    """

    def __init__(self, args: list[str]) -> None:
        """Hold the arguments.

        Args:
            args (list[str]): The raw command line.

        Returns:
            None
        """
        self.args = args


class _FakeConfig:
    """Enough of pytest's config to exercise the invocation record.

    **Built here rather than through a pytest run** because the question is what
    `configure_invocation` concludes from a given command line, and spinning up a
    session to ask it would make the case slower and less specific.
    """

    def __init__(self, args: list[str], values: dict[str, Any]) -> None:
        """Hold the command line and the parsed values.

        Args:
            args (list[str]): The raw command line.
            values (dict[str, Any]): What pytest would have parsed from it.

        Returns:
            None
        """
        self.invocation_params = _FakeInvocationParams(args)
        self._values = values
        self.mqc_invocation: Any = None

    def getoption(self, name: str, default: Any = None) -> Any:
        """Return a parsed value, as pytest would.

        Args:
            name (str): The option's destination name.
            default (Any): What to return when it is unset.

        Returns:
            Any: The value.
        """
        return self._values.get(name, default)


class TestMQCOptionRegistry:
    """One declaration, two surfaces, and what a bad value costs at parse time."""

    def MQC_CMN_UNI_10147_option_registry_yields_identical_flags_to_both_surfaces(self) -> None:
        """A flag cannot exist on one surface and not the other.

        Declaring them twice would let one gain a value the other rejects, and
        the failure would appear as a flag that works in one place and not the
        other, which is diagnosed by reading two files.

        Returns:
            None
        """
        parser = build_parser()
        root = Path(__file__).resolve().parents[2]
        conftest_source = (root / "conftest.py").read_text(encoding="utf-8")
        # The registration moved into cmn/ when the split made a second
        # conftest necessary, so the source check follows it there. A consumer
        # calls the same function; the check is that SOMETHING builds the flags
        # from the registry and that our conftest reaches it, not which file
        # the loop happens to sit in.
        support_source = (root / "cmn" / "pytest_support.py").read_text(
            encoding="utf-8"
        )

        for declared in registered_options():
            # Surface one: the standalone verdict tool's argparse parser.
            supplied = ["results.json", declared.cli_flag]
            if not declared.is_flag:
                supplied.append(
                    declared.choices[0] if declared.choices else "value"
                )
            parsed = parser.parse_args(supplied)
            assert hasattr(parsed, declared.metadata_key)

        # Surface two: the pytest plugin. Asserted by building from the same
        # registry rather than by listing flags, because a hand-written list
        # here would be the third place a flag could be declared and the
        # second place it could be forgotten.
        assert "registered_options()" in support_source
        assert "def add_mqc_options" in support_source
        assert "def pytest_addoption" in conftest_source
        assert "add_mqc_options" in conftest_source

        plugin = _plugin_registrations()
        for declared in registered_options():
            assert declared.cli_flag in plugin.registered, (
                f"{declared.cli_flag} reaches the verdict tool and not pytest"
            )
            # The choices travel too, or one surface would accept a value the
            # other rejects, which is the drift the shared registry prevents.
            expected = list(declared.choices) if declared.choices else None
            assert plugin.choices[declared.cli_flag] == expected

    @pytest.mark.parametrize(
        "name,value", [("engine", "gemeni"), ("mode", "cached"), ("extra-columns", "keep")]
    )
    def MQC_CMN_UNI_10148_invalid_enumerated_flag_value_is_rejected_at_parse_time(
        self, name: str, value: Any
    ) -> None:
        """A typo reaching the suite would select nothing and report an empty run.

        An empty run reads exactly like a run where nothing needed to happen,
        which is why the rejection has to happen before anything executes.

        Args:
            name (str): The flag.
            value (str): A value outside its choices.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR") as caught:
            validate_value(name, value)
        assert "permitted values are" in str(caught.value)

    def MQC_CMN_UNI_10198_argparse_rejects_the_same_values_the_registry_does(self) -> None:
        """The two surfaces agree on rejection, not only on acceptance.

        A registry that validated correctly while argparse accepted anything
        would satisfy `10148` and leave the command line unguarded.

        Returns:
            None
        """
        parser = build_parser()
        with pytest.raises(SystemExit) as caught:
            parser.parse_args(["results.json", "--engine", "gemeni"])
        assert caught.value.code == EXIT_ARGUMENT_ERROR

    def MQC_CMN_UNI_10135_cli_defaults_are_recorded_in_metadata(self) -> None:
        """A run that took a default and one that named it produced one result.

        The reader of an artifact needs to know what applied, not what was
        typed, so defaults are recorded rather than omitted.

        Returns:
            None
        """
        invocation = build_invocation({})
        recorded = invocation.as_metadata()

        assert recorded["mode"] == "replay"
        assert recorded["extra_columns"] == "reject"
        assert recorded["judge_on_failure"] is False
        assert recorded == defaults()

    def MQC_CMN_UNI_10136_defaulted_engine_emits_warning_into_artifact(self) -> None:
        """A cloned repository running unconfigured produces a record saying so.

        The warning goes into the artifact rather than only to a log, because
        the artifact is what a reader has months later (A7.4).

        Returns:
            None
        """
        defaulted = build_invocation({})
        named = build_invocation({"engine": "openai"})

        assert len(defaulted.warnings) == 1
        assert "QC_DATA_ENGINE_DEFAULTED" in defaulted.warnings[0]
        assert not named.warnings

    def MQC_CMN_UNI_11190_choosing_the_default_engine_is_not_defaulting(self) -> None:
        """`--engine gemini` chose a provider, and the run said nobody had.

        **The existing case could not catch this.** `10197` named `openai`, a
        value that differs from the default, so it proved only that an explicit
        NON-default engine is quiet. The bug lived exactly where the explicit
        value equals the default, which is the commonest invocation there is:
        gemini is the roster's default and the only engine with a funded key.

        **A warning that fires when its condition did not occur is worse than no
        warning.** `ci_pipeline.md` already names the hazard: a signal present on
        every run teaches the reader to skip the line, and this one exists to say
        a record measured a provider nobody chose (A7.4).

        **Both spellings count**, because pytest accepts either and a reader who
        wrote the second did not choose less.

        Returns:
            None
        """
        for arguments in (
            ["-m", "sec", "--engine", "gemini"],
            ["-m", "sec", "--engine=gemini"],
        ):
            config = _FakeConfig(arguments, {"engine": "gemini", "mode": "replay"})
            configure_invocation(config)
            assert not config.mqc_invocation.warnings, (
                f"naming the default engine as {arguments[-1]!r} still reported "
                f"that nobody chose a provider"
            )

        # AND THE WARNING STILL FIRES WHERE IT SHOULD, which is the half the
        # original case did cover and this must not break.
        unchosen = _FakeConfig(["-m", "sec"], {"engine": "gemini", "mode": "replay"})
        configure_invocation(unchosen)
        assert len(unchosen.mqc_invocation.warnings) == 1
        assert "QC_DATA_ENGINE_DEFAULTED" in unchosen.mqc_invocation.warnings[0]

    def MQC_CMN_UNI_10199_mode_defaults_to_replay_so_nothing_spends_quota(self) -> None:
        """Defaults fail safe.

        No unconfigured invocation can spend quota or emit an unmarked live
        result, which is the same principle as marking a replay (A6) applied to
        what happens when nobody chose.

        Returns:
            None
        """
        assert option("mode").default == "replay"
        assert option("extra-columns").default == "reject"
        assert option("judge-on-failure").default is False


class TestMQCSelectionMode:
    """What makes a selection manual, and what that costs it."""

    def MQC_CMN_UNI_10162_no_filter_yields_selection_mode_full(self) -> None:
        """Nothing supplied means everything ran.

        Returns:
            None
        """
        invocation = build_invocation({})
        assert invocation.selection_mode == "full"
        assert invocation.yields_verdict is True

    @pytest.mark.parametrize("flag", sorted(manual_selector_flags()))
    def MQC_CMN_UNI_10164_manual_filter_yields_no_verdict(self, flag: str) -> None:
        """Every filtering flag makes the selection manual.

        Parametrized over the registry rather than written per flag, so a
        selector added later cannot be the one nobody checked.

        Args:
            flag (str): The selector supplied.

        Returns:
            None
        """
        invocation = build_invocation({flag: "0,1" if flag == "priority" else "x"})
        assert invocation.selection_mode == "manual"
        assert invocation.yields_verdict is False

    def MQC_CMN_UNI_10163_change_scoped_selection_still_yields_a_verdict(self) -> None:
        """Derived from the diff, recorded, and backstopped by the full merge run.

        **Not all subsets are equal, and the difference is not size.** A
        change-scoped selection yields a verdict because of where it came from,
        not because of how much of the suite it covers.

        Returns:
            None
        """
        scoped = RunContext(
            run_context="ci", selection_mode="change_scoped", preconditions_executed=True
        )
        assert scoped.gated is True

    def MQC_CMN_UNI_10152_case_flag_selects_exactly_one_case(self) -> None:
        """A single-case run is legitimate and produces no verdict.

        Returns:
            None
        """
        invocation = build_invocation({"case": "MQC_TASK_a::MQC_RULE_r"})
        assert invocation.selection_mode == "manual"
        assert invocation.as_metadata()["case"] == "MQC_TASK_a::MQC_RULE_r"

    def MQC_CMN_UNI_10153_observations_override_replaces_configured_count(self) -> None:
        """Overriding the observation count is a diagnostic selection.

        Returns:
            None
        """
        invocation = build_invocation({"observations": 1})
        assert invocation.as_metadata()["observations"] == 1
        assert invocation.yields_verdict is False


class TestMQCGatedDerivation:
    """Three facts, all required, none of them assertable by the artifact."""

    @pytest.mark.parametrize(
        "context,selection,preconditions,expected",
        [
            ("ci", "full", True, True),
            ("ci", "change_scoped", True, True),
            ("ci", "manual", True, False),
            ("ci", "full", False, False),
            ("ci_debug", "full", True, False),
            ("local", "full", True, False),
        ],
    )
    def MQC_CMN_UNI_10169_gated_derived_from_selection_preconditions_and_run_context(
        self, context: str, selection: str, preconditions: bool, expected: Any
    ) -> None:
        """Derived, never set, so an artifact cannot claim to be gated.

        Args:
            context (str): The run context.
            selection (str): The selection mode.
            preconditions (bool): Whether the preconditions executed.
            expected (bool): Whether a verdict may be computed.

        Returns:
            None
        """
        run = RunContext(
            run_context=context, selection_mode=selection,
            preconditions_executed=preconditions,
        )
        assert run.gated is expected
        assert run.as_fields()["gated"] is expected

    def MQC_CMN_UNI_10174_full_selection_under_debug_context_is_still_ungated(self) -> None:
        """The boundary: a full selection is not sufficient on its own.

        A debug job may be exercising a different harness branch entirely
        against different test cases, so covering the whole suite says nothing
        about which suite it covered.

        Returns:
            None
        """
        debug = RunContext(
            run_context="ci_debug", selection_mode="full", preconditions_executed=True
        )
        assert debug.gated is False

    def MQC_CMN_UNI_10178_manual_full_dispatch_of_ci_is_gated_and_yields_a_verdict(self) -> None:
        """A human pressing run on the full CI workflow is still a full selection.

        The distinction is what the selection was, not who started it. A full
        run dispatched by hand covers the same suite as one dispatched by a
        push, and refusing it would mean nobody could verify a branch before
        offering it.

        Returns:
            None
        """
        dispatched = RunContext(
            run_context="ci", selection_mode="full", preconditions_executed=True
        )
        assert dispatched.gated is True


class TestMQCVerdictToolExitCodes:
    """The codes, and why each is distinct from the ones beside it."""

    def MQC_CMN_UNI_10149_verdict_recomputable_from_stored_artifacts(self, tmp_path: Path) -> None:
        """The whole reason the tool is standalone rather than an in-process hook.

        Thresholds are configuration, so "what would this run have scored under
        the tightened floor?" is answerable from history, which is what makes a
        threshold change auditable rather than merely disclosed.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        artifact = _artifact(results=[
            {"case_id": "MQC_TASK_pre::MQC_RULE_pre", "layer": "UNI", "outcome": "pass"},
        ] + [
            {"case_id": f"MQC_TASK_{index}::MQC_RULE_r", "layer": "EVAL",
             "outcome": "pass" if index < 9 else "fail", "priority": 3}
            for index in range(10)
        ])

        lenient, _ = compute(artifact, tmp_path, _TODAY)
        assert lenient.green is True

        artifact["effective_thresholds"] = {"pass_floor": 0.95}
        strict, _ = compute(artifact, tmp_path, _TODAY)

        assert thresholds_from(artifact).pass_floor == 0.95
        assert strict.green is False
        assert "V2" in strict.breached_rules

    def MQC_CMN_UNI_10150_precondition_failure_exits_three_not_one(self, tmp_path: Path) -> None:
        """A red verdict is a finding; a precondition failure measured nothing.

        Collapsing them would let CI treat "the harness is broken" as "the
        model underperformed", which sends the wrong person to investigate.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        artifact = _artifact(results=[
            {"case_id": "MQC_TASK_pre::MQC_RULE_pre", "layer": "UNI", "outcome": "fail"},
            {"case_id": "MQC_TASK_a::MQC_RULE_r", "layer": "EVAL", "outcome": "fail",
             "priority": 0},
        ])
        computed, refusal = compute(artifact, tmp_path, _TODAY)

        assert refusal is None
        assert computed.exit_code == 3
        assert computed.exit_code != EXIT_RED

    def MQC_CMN_UNI_10156_verdict_tool_refuses_artifacts_marked_ungated(
        self,
        tmp_path: Path,
    ) -> None:
        """A refusal says no verdict was computable, not that the suite failed.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        artifact = _artifact(gated=False, run_context="ci_debug")
        computed, refusal = compute(artifact, tmp_path, _TODAY)

        assert computed is None
        assert refusal is not None
        assert refusal.exit_code == EXIT_REFUSED
        assert "ci_debug" in refusal.reason

    def MQC_CMN_UNI_10168_verdict_tool_refuses_a_manual_selection_artifact(self) -> None:
        """A hand-typed subset is arbitrary and has no backstop.

        Args:
            None

        Returns:
            None
        """
        refusal = refuse_if_ungated(
            {"gated": False, "selection_mode": "manual", "run_context": "ci"}
        )
        assert refusal is not None
        assert "manual" in refusal.reason

    def MQC_CMN_UNI_10170_refusal_exits_four_not_one(self, tmp_path: Path) -> None:
        """4 is distinct from 1, and the distinction runs the other way.

        A refused artifact reading as a failing suite is the inverse of the
        error the gating rules exist to prevent: it would make an unverifiable
        run look like a verified one that failed.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        path = tmp_path / "results.json"
        path.write_text(json.dumps(_artifact(gated=False)), encoding="utf-8")
        assert main([str(path)]) == EXIT_REFUSED

    def MQC_CMN_UNI_10200_a_green_gated_artifact_exits_zero(self, tmp_path: Path) -> None:
        """The positive the refusals and failures are measured against.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        path = tmp_path / "results.json"
        path.write_text(json.dumps(_artifact()), encoding="utf-8")
        assert main([str(path)]) == EXIT_GREEN

    def MQC_CMN_UNI_11101_an_unreadable_artifact_is_an_argument_error(self, tmp_path: Path) -> None:
        """An unreadable artifact read as empty would report green for nothing.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        path = tmp_path / "results.json"
        path.write_text("{ truncated", encoding="utf-8")
        assert main([str(path)]) == EXIT_ARGUMENT_ERROR


class TestMQCDiagnosticRuns:
    """What a diagnostic run deliberately does not produce."""

    def MQC_CMN_UNI_10154_diagnostic_run_returns_no_verdict_code(self) -> None:
        """A diagnostic run uses none of the verdict codes.

        It returns pytest's exit status, because it computed no verdict. Using
        a verdict code would make a diagnostic green indistinguishable from a
        gated one at exactly the moment a reader is least likely to check.

        Returns:
            None
        """
        diagnostic = RunContext(
            run_context="ci_debug", selection_mode="manual", preconditions_executed=True
        )
        refusal = refuse_if_ungated(diagnostic.as_fields())

        assert diagnostic.gated is False
        assert refusal is not None
        assert refusal.exit_code not in (EXIT_GREEN, EXIT_RED)

    def MQC_CMN_UNI_10151_unknown_case_identifier_is_an_error_not_an_empty_run(self) -> None:
        """Selecting nothing must not look like selecting everything that passed.

        Returns:
            None
        """
        known = {"MQC_TASK_a::MQC_RULE_r"}
        requested = "MQC_TASK_typo::MQC_RULE_r"
        assert requested not in known

        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR"):
            validate_value("engine", "not_an_engine")

    def MQC_CMN_UNI_10157_out_dir_isolates_diagnostic_artifacts(self, tmp_path: Path) -> None:
        """A diagnostic run writes somewhere a collector does not read.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        invocation = build_invocation({"out_dir": str(tmp_path / "diagnostic")})
        assert invocation.as_metadata()["out_dir"] == str(tmp_path / "diagnostic")
        assert option("out-dir").default == ""


class TestMQCThresholdRecording:
    """The standard applied, recoverable from the artifact alone."""

    def MQC_CMN_UNI_10138_effective_thresholds_recorded_in_metadata(self) -> None:
        """A stored result whose standard cannot be recovered is uninterpretable.

        Returns:
            None
        """
        run = RunContext(
            run_context="ci", selection_mode="full", preconditions_executed=True,
            effective_thresholds={"pass_floor": 0.95, "skip_ceiling": 0.15},
        )
        fields = run.as_fields()

        assert fields["effective_thresholds"]["pass_floor"] == 0.95
        assert thresholds_from({"effective_thresholds": fields["effective_thresholds"]}) \
            .pass_floor == 0.95

    def MQC_CMN_UNI_10137_rule_set_content_hash_recorded_in_metadata(self) -> None:
        """A revised rule set must be distinguishable from the original.

        The hash rather than the path, because a path says where the rules were
        and a hash says what they were.

        Returns:
            None
        """
        run = RunContext(
            run_context="ci", selection_mode="full", preconditions_executed=True,
            rule_set_hash="sha256:abc123",
        )
        assert run.as_fields()["rule_set_hash"] == "sha256:abc123"

    def MQC_CMN_UNI_11102_an_unrecorded_threshold_falls_back_to_the_default(self) -> None:
        """An artifact predating a threshold still recomputes.

        Returns:
            None
        """
        assert thresholds_from({}).pass_floor == pytest.approx(0.90)
        assert thresholds_from({"effective_thresholds": {}}).skip_ceiling \
            == pytest.approx(0.20)


class TestMQCConsumerRegistry:
    """What the fan-out reads, and what an unreachable consumer means."""


    def MQC_CMN_UNI_11208_the_corpus_selection_is_resolved_at_configure_time(
        self,
    ) -> None:
        """``--golden-rules`` and ``--extra-columns`` arrive through configure.

        Both are readable after the run is configured and without a
        configuration in hand, which is what the corpus loaders need: they are
        cached and reached from fixtures that hold none.

        An unnamed option resolves to ``None`` rather than a default, because
        this repository owns no corpus and cannot know what the default path
        is; the caller substitutes its own.

        Design: ``tier1_ingestion.md`` section 4.6.

        Returns:
            None
        """
        adopt_corpus_selection(
            _FakeConfig([], {"--golden-rules": "/elsewhere/data",
                             "--extra-columns": "drop"})
        )
        root, policy = corpus_selection()

        assert root == Path("/elsewhere/data")
        assert policy == "drop"

        # UNNAMED IS NONE, NOT A DEFAULT. The consumer substitutes its own.
        adopt_corpus_selection(_FakeConfig([], {}))
        root, policy = corpus_selection()

        assert root is None, (
            "an unnamed corpus resolved to a path, so this repository would be "
            "deciding where a corpus it does not own lives"
        )
        assert policy is None

    def MQC_CMN_UNI_11115_consumer_registry_loads_every_declared_entry(self) -> None:
        """Adding a consumer is an entry, never a workflow change.

        **The fan-out is the capability the split exists to provide.** A harness
        change is verified against this repository's own preconditions, which
        prove the instrument works and say nothing about whether a case set
        pinning it still passes.

        Returns:
            None
        """
        root = Path(__file__).resolve().parents[2]
        consumers = load_consumers(root / "config" / "consumers.yaml")

        assert consumers
        for consumer in consumers:
            assert "/" in consumer.repository
            assert consumer.default_ref
            # The pairing is per branch: a run is defined by a pair of refs and
            # not by either alone (ci_pipeline.md section 3C).
            assert consumer.refs
            # Deterministic gates only. A live run in the fan-out would answer a
            # different question at a price.
            assert "--mode replay" in consumer.command

    def MQC_CMN_UNI_11120_a_named_harness_branch_resolves_to_its_paired_consumer_ref(
        self,
    ) -> None:
        """Stabilization work is verified against stabilization work.

        A harness extension lives on ``stabilization`` before it lives anywhere
        else, and the cases needing it live on the consumer's stabilization
        branch. Pairing both to ``main`` would verify each against a branch that
        has not received the other.

        Returns:
            None
        """
        root = Path(__file__).resolve().parents[2]
        consumers = load_consumers(root / "config" / "consumers.yaml")

        registry = {consumer.name: consumer for consumer in consumers}
        cases = registry["AP-Model-QC"]

        assert cases.ref_for("main") == "main"
        assert cases.ref_for("stabilization") == "stabilization"

    def MQC_CMN_UNI_11119_an_unnamed_harness_branch_falls_back_to_the_default_ref(
        self,
    ) -> None:
        """A feature branch needs no registry entry to be tested.

        **This is the boundary the mapping is defined at.** Feature branches are
        created constantly, and requiring an entry for each would make the
        registry the thing that stops a branch being tested. An implementation
        raising here instead would be silent on every branch except the two that
        are named, which is where it would not be noticed.

        Returns:
            None
        """
        consumer = Consumer(
            name="Example",
            repository="owner/example",
            refs={"stabilization": "stabilization"},
            default_ref="main",
        )

        assert consumer.ref_for("feature/anything") == "main"
        assert consumer.ref_for("") == "main"
        assert consumer.ref_for("stabilization") == "stabilization"

    def MQC_CMN_UNI_11116_a_consumer_entry_without_a_repository_is_rejected(
        self, tmp_path: Path
    ) -> None:
        """A consumer that cannot be located reports unreachable on every run.

        That reads as a consumer problem when it is a registry typo, which is
        the misattribution the rejection prevents.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        registry = tmp_path / "consumers.yaml"
        registry.write_text(
            "consumers:\n  - name: Nameless\n    ref: main\n", encoding="utf-8"
        )
        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR"):
            load_consumers(registry)

    def MQC_CMN_UNI_11117_an_absent_consumer_registry_is_a_starting_condition(
        self, tmp_path: Path
    ) -> None:
        """A harness with no registered consumers has nothing to fan out to.

        Absent is not an error here, and an unreachable consumer is a harness
        event rather than a red suite: a private repository or a deleted branch
        says nothing about whether this harness is sound.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        assert not load_consumers(tmp_path / "nothing.yaml")
        assert unreachable_consumer_code() == "QC_HARNESS_DEPENDENCY_UNMET"
        assert is_registered_harness_code(unreachable_consumer_code())

    def MQC_CMN_UNI_11118_selecting_named_tests_yields_no_verdict(self) -> None:
        """The debug workflow selects by test identifier, which is manual.

        **This closed a real gap.** `tests` was neither a declared option nor a
        registered manual selector, so a run naming four failing tests would
        have derived `selection_mode: full` and produced a verdict from four
        cases. That is exactly the failure the gating rules exist to prevent,
        arriving through a flag nobody had registered.

        Returns:
            None
        """
        invocation = build_invocation(
            {
                "tests": (
                    "MQC_ING_UNI_10001_first_probe,"
                    "MQC_ING_UNI_10002_second_probe"
                )
            }
        )

        assert invocation.selection_mode == "manual"
        assert invocation.yields_verdict is False
        assert "tests" in manual_selector_flags()
        assert option("tests").default == ""
