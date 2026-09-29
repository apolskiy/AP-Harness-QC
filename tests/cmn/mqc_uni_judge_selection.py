# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Which engine grades, which model it uses, and how a change is detected.

Covers ``MQC_CMN_UNI_11124`` through ``11127`` and ``11133`` through ``11135``,
inventoried in ``docs/design/cmn_verdict_and_cli.md`` sections 10.13 and 10.18.

**Split from the CLI module on 2026-09-24**, when that module crossed the
thousand line ceiling. The split follows the subject rather than the line
count: these cases are about configuration, and the judge is configuration
(``tier3_evaluation.md`` section 5A).

**They sit in the CMN inventory rather than the Tier 3 one** because the
resolution lives in ``cmn/config.py``: ``evaluation/`` imports nothing from
``execution/``, and resolving a judge needs an engine's declared capabilities,
which are a Tier 2 record.

A failure here is our defect, so the module carries no priority marker.
"""

import tomllib
from pathlib import Path

import pytest

from cmn.config import (
    JUDGE_PROBE_SUBJECT,
    EngineConfig,
    load_engines,
    load_harness_config,
    load_judge_engine,
    load_judge_model,
    packaged_roster_path,
    probe_subjects,
    resolve_judge_engine,
)
from cmn.options import option, resolve_judge_mode
from cmn.registries import is_registered_harness_code

pytestmark = pytest.mark.unit


class TestMQCJudgeResolution:
    """Which engine grades, and what disqualifies one."""

    def MQC_CMN_UNI_11124_the_default_judge_engine_is_gemini(self) -> None:
        """A3 decided this on 2026-09-19 and no file named it until now.

        The decision lived in prose while ``JudgeBinding`` defaulted to unbound
        and a run recorded ``no_judge_configured``, which is correct for an
        absent judge and wrong for a project that had chosen one.

        Returns:
            None
        """
        root = Path(__file__).resolve().parents[2]
        loaded = load_harness_config(root / "config")

        assert loaded.judge_engine == "gemini"
        # The shipped roster must actually carry the engine it nominates, or
        # the default would refuse itself on the first run.
        assert "gemini" in loaded.engines

    def MQC_CMN_UNI_11125_a_configured_judge_engine_overrides_the_default(
        self, tmp_path: Path
    ) -> None:
        """Selecting another judge is a configuration entry, never a code change.

        **This is what keeps the interface open.** A3 expects the judge to move
        once a second key exists, and a constant in ``evaluation/`` would make
        that a change to the module that must stay indifferent to which engine
        it is talking to.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        roster = tmp_path / "engines.yaml"
        roster.write_text(
            "\n".join(
                [
                    "engines:",
                    "  claude:",
                    "    model: claude-opus-5-5",
                    "judge:",
                    "  engine: claude",
                ]
            ),
            encoding="utf-8",
        )

        assert load_judge_engine(roster) == "claude"
        # An absent judge block falls back rather than failing: an unconfigured
        # clone still runs, as each adapter's DEFAULT_MODEL also ensures.
        bare = tmp_path / "bare.yaml"
        bare.write_text("engines:\n  gemini:\n    model: x\n", encoding="utf-8")
        assert load_judge_engine(bare) == "gemini"

    def MQC_CMN_UNI_11126_a_judge_engine_absent_from_the_roster_is_rejected(
        self,
    ) -> None:
        """Usually a typo, and refused before any quota is spent.

        Refusing at load time rather than at the first judge call is the
        difference between a run that does not start and a run that dispatches
        every candidate and then cannot grade one.

        Returns:
            None
        """
        roster = {"gemini": EngineConfig(engine="gemini", model="gemini-2.5-flash")}

        with pytest.raises(ValueError, match="QC_HARNESS_PREFLIGHT_FAILURE"):
            resolve_judge_engine("gemmini", roster, can_judge=lambda name: True)

        # A harness event, never a finding about a model: the instrument is
        # misconfigured and nothing was measured.
        assert is_registered_harness_code("QC_HARNESS_PREFLIGHT_FAILURE")

    def MQC_CMN_UNI_11127_an_engine_without_structured_output_cannot_judge(
        self,
    ) -> None:
        """The harder refusal, and the reason there are two cases.

        The name is real and the engine works as a candidate; only the declared
        capability disqualifies it. A single case asserting that a bad engine
        is rejected would pass against an implementation checking nothing but
        roster membership.

        Returns:
            None
        """
        roster = {
            "gemini": EngineConfig(engine="gemini", model="gemini-2.5-flash"),
            "plain": EngineConfig(engine="plain", model="plain-1"),
        }

        # On the roster, and still refused.
        with pytest.raises(ValueError, match="structured_output"):
            resolve_judge_engine("plain", roster, can_judge=lambda name: name != "plain")

        # The capability is the ONLY qualifier. No list of permitted judge
        # engines exists, because one would need editing whenever an adapter is
        # added (tier3_evaluation.md section 5A.2).
        assert resolve_judge_engine(
            "plain", roster, can_judge=lambda name: True
        ) == "plain"


    def MQC_CMN_UNI_11133_an_absent_judge_model_falls_back_to_the_roster_entry(
        self, tmp_path: Path
    ) -> None:
        """The behaviour every existing configuration relies on.

        Before a judge model could be named, the judge resolved to whatever
        model the roster gave its engine. A fallback returning nothing would
        leave the judge unresolvable and every graded run reporting a
        misconfigured instrument.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        roster = tmp_path / "engines.yaml"
        roster.write_text(
            "\n".join(
                [
                    "engines:",
                    "  gemini:",
                    "    model: gemini-2.5-flash",
                    "judge:",
                    "  engine: gemini",
                ]
            ),
            encoding="utf-8",
        )
        loaded = load_engines(roster)

        assert load_judge_model(roster, loaded) == "gemini-2.5-flash"

    def MQC_CMN_UNI_11134_a_judge_model_distinct_from_the_candidate_is_expressible(
        self, tmp_path: Path
    ) -> None:
        """The configuration the probe could not see before section 5A.4.

        A stronger model grading a cheaper one shares an engine with the
        candidate and differs in model. The probe walks the roster, so that
        judge model appears nowhere in it and a version change would go
        undetected.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        roster = tmp_path / "engines.yaml"
        roster.write_text(
            "\n".join(
                [
                    "engines:",
                    "  gemini:",
                    "    model: gemini-2.5-flash",
                    "judge:",
                    "  engine: gemini",
                    "  model: gemini-2.5-pro",
                ]
            ),
            encoding="utf-8",
        )
        loaded = load_engines(roster)
        judge_model = load_judge_model(roster, loaded)

        assert judge_model == "gemini-2.5-pro"
        # Distinct from the candidate on the same engine, which is the whole
        # point: one engine, two models, two subjects.
        assert judge_model != loaded["gemini"].model

    def MQC_CMN_UNI_11135_a_probe_that_omits_the_judge_subject_is_reported(
        self,
    ) -> None:
        """A probe walking only the roster reports nothing and misses drift.

        **The subject is the role, not the engine filling it.** Re-pointing the
        judge registers as a version change and dispatches a live run, which is
        correct: a different judge is a different instrument, and every score
        recorded under the previous one was produced by something that no
        longer exists.

        Returns:
            None
        """
        roster = {
            "gemini": EngineConfig(engine="gemini", model="gemini-2.5-flash"),
            "claude": EngineConfig(engine="claude", model="claude-opus-5-5"),
        }

        subjects = probe_subjects(roster, "gemini", "gemini-2.5-pro")

        assert JUDGE_PROBE_SUBJECT in subjects, (
            "the probe would walk the roster only, and a judge model absent "
            "from it would never be compared against a baseline"
        )
        assert subjects[JUDGE_PROBE_SUBJECT] == "gemini-2.5-pro"
        # Every candidate stays a subject in its own right.
        assert set(subjects) == {"gemini", "claude", JUDGE_PROBE_SUBJECT}

        # The shipped configuration is covered too, not only a constructed one.
        loaded = load_harness_config(Path(__file__).resolve().parents[2] / "config")
        shipped = probe_subjects(
            loaded.engines, loaded.judge_engine, loaded.judge_model
        )
        assert JUDGE_PROBE_SUBJECT in shipped


class TestMQCJudgeMode:
    """Which of the four quadrants a run is asking for."""

    def MQC_CMN_UNI_11141_judge_mode_defaults_to_whatever_mode_is(self) -> None:
        """Every existing invocation keeps its meaning.

        A fixed default would silently change what ``--mode live`` meant, and
        the two common quadrants need no flag at all. Empty is therefore the
        default and is deliberately not one of the two real values.

        Returns:
            None
        """
        assert resolve_judge_mode("replay", "") == "replay"
        assert resolve_judge_mode("live", "") == "live"

        # The quadrant the flag exists for: a replayed candidate judged live,
        # which isolates judge drift on real cases.
        assert resolve_judge_mode("replay", "live") == "live"

        # Declared with an empty choice, so the registry accepts "follow".
        assert "" in (option("judge-mode").choices or ())

    def MQC_CMN_UNI_11142_a_live_candidate_with_a_replayed_judge_is_refused(
        self,
    ) -> None:
        """A judgement is a score of a specific response.

        **A live run exists to evaluate output.** If the output drifted,
        scoring it with a judgement computed for earlier text measures
        neither: not the candidate, because the score was not computed from
        what it just said, and not the judge, because the judge is not the
        subject when the candidate is the thing that moved.

        **Judge drift already has its own quadrant**, `replay` with
        `--judge-mode live`, where the candidate is held still precisely so
        the judge can be the only variable. Asking it while the candidate
        moves is asking two questions with one answer.

        The fixture machinery would catch it as staleness on every case,
        **which reads as a corpus problem rather than an impossible request**,
        so it is refused at parsing instead.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR"):
            resolve_judge_mode("live", "replay")

        # The other three quadrants all resolve, so the refusal is narrow.
        assert {
            resolve_judge_mode(mode, judge)
            for mode, judge in (("replay", ""), ("live", ""), ("replay", "live"))
        } == {"replay", "live"}


class TestMQCPackagedConfiguration:
    """Where a consumer finds this harness's own configuration."""

    def MQC_CMN_UNI_11191_the_roster_is_found_through_the_installed_package(
        self,
    ) -> None:
        """A consumer read the roster from the directory next door.

        `AP-Model-QC` located it at `../AP-Harness-QC/config/engines.yaml`,
        true only where both repositories are checked out side by side. CI
        installs this harness from a pinned commit, so the path did not exist,
        an absent file loaded as an empty mapping the way an optional one
        does, and the gate failed reporting `judge engine 'gemini' is not on
        the roster` — a true statement about a roster never read.

        Returns:
            None
        """
        located = packaged_roster_path()

        assert located.is_file()
        assert located.name == "engines.yaml"
        # POPULATED, NOT MERELY PRESENT, because an empty roster was the shape
        # the original failure took.
        assert sorted(load_engines(located))

    def MQC_CMN_UNI_11192_the_shipped_distribution_carries_the_configuration(
        self,
    ) -> None:
        """Package data is configured, or the consumer install has no roster.

        **The build must be asked, not the source tree.** `config/` is present
        on disk whatever the build says, so a check that it exists proves
        nothing: `MQC_CMN_UNI_11114` learned the same lesson about packages the
        first time this repository was installed into another one. What
        matters is that the packaging configuration would carry it into a
        wheel.

        Returns:
            None
        """
        root = Path(__file__).resolve().parents[2]
        configured = tomllib.loads(
            (root / "pyproject.toml").read_text(encoding="utf-8")
        )["tool"]["setuptools"]

        found = configured["packages"]["find"]
        assert any(entry.rstrip("*") == "config" for entry in found["include"]), (
            "config/ is not in the package list, so a wheel would omit the "
            "roster and every consumer would resolve an empty one"
        )
        # A NAMESPACE PORTION, because `config/` carries no `__init__.py` and
        # acquiring one would make a data directory importable to say so.
        assert found.get("namespaces") is True
        assert "*.yaml" in configured["package-data"]["config"]
        assert "config" not in [entry.rstrip("*") for entry in found["exclude"]]
