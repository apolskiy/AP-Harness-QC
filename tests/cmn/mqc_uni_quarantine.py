# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""V5 and the quarantine model it reads: expiry, provenance and the record.

Covers ``MQC_CMN_UNI_112010`` to ``112012``, ``112037``, ``112038`` to ``112042``,
inventoried in ``docs/design/cmn_verdict_and_cli.md`` section 10 and designed in
section 4.6.

**Extracted 2026-10-02**, when reworking the quarantine model took
``mqc_uni_verdict.py`` past the thousand-line ceiling. The subject is one
mechanism: what expires an entry, what an entry must carry to be evaluated at
all, and what the run records about the entries it consulted.

A failure here is our defect, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

import json
from datetime import date, timedelta
import logging
from pathlib import Path
from typing import Any

import pytest

from cmn.config import load_quarantine_for
from cmn.observations import Observation, RunContext
from cmn.prerequisites import quarantine_digest
from cmn.quarantine import DROPPED, STAMPED, UNDECIDED, reconcile
from cmn.verdict import QuarantineEntry, VerdictConfig, verdict
from cmn.verdict_tool import EXIT_GREEN, EXIT_RED, main, report_exclusions
from tests.cmn.verdict_support import (
    QUARANTINED_CASE,
    TODAY,
    gated_artifact,
    graded,
    passing_suite,
)

pytestmark = pytest.mark.unit


class TestMQCQuarantine:
    """V5: the model that changed, the window that lapsed, and an entry we broke."""

    def MQC_CMN_UNI_112010_red_when_quarantine_entry_expired(self) -> None:
        """An entry past the window fails the run rather than going on excluding.

        The pass floor stops meaning anything once everything inconvenient has
        left the denominator, which is why a lapsed entry is red.

        Returns:
            None
        """
        entry = QuarantineEntry(
            QUARANTINED_CASE, "flaky", date(2026, 9, 1), observed_model="gemini-3.8-flash"
        )
        result = verdict(
            passing_suite(), VerdictConfig(quarantine=[entry]), TODAY
        )
        assert result.green is False
        assert "V5" in result.breached_rules

    def MQC_CMN_UNI_112011_green_when_quarantine_entry_current(self) -> None:
        """A current entry excludes without failing.

        Returns:
            None
        """
        entry = QuarantineEntry(
            QUARANTINED_CASE, "flaky", TODAY, observed_model="gemini-3.8-flash"
        )
        result = verdict(passing_suite(), VerdictConfig(quarantine=[entry]), TODAY)
        assert result.green is True
        assert result.quarantined == [QUARANTINED_CASE]
        assert not result.unconfirmed_quarantine

    @pytest.mark.parametrize(
        "elapsed,expired",
        [(19, False), (20, False), (21, True), (22, True)],
    )
    def MQC_CMN_UNI_112012_expiry_boundary_evaluated_against_injected_date(
        self, elapsed: int, expired: Any
    ) -> None:
        """The window boundary is testable only because the date is injected.

        A function calling the system clock could not be exercised at its own
        boundary without manipulating the machine.

        **Day 21 is the first expired day**, so an entry is valid for 21 days
        and lapses on reaching the window rather than after passing it.

        Args:
            elapsed (int): Days between the entry's date and the evaluation.
            expired (bool): Whether the entry should have lapsed.

        Returns:
            None
        """
        entry = QuarantineEntry(
            QUARANTINED_CASE, "flaky", TODAY - timedelta(days=elapsed),
            observed_model="gemini-3.8-flash",
        )
        result = verdict(passing_suite(), VerdictConfig(quarantine=[entry]), TODAY)

        assert ("V5" in result.breached_rules) is expired

    def MQC_CMN_UNI_112037_an_entry_whose_model_changed_is_expired(self) -> None:
        """A changed model expires an entry inside its window.

        An entry records an accepted finding about one model, so a different
        resolved model leaves it saying nothing about what is now running.

        **A mixed corpus does not expire on model change.** Which of two models
        to compare against has no answer, and `mixed_model_engines` already
        reports that run as mixed.

        Design: ``cmn_verdict_and_cli.md`` section 4.6.2.

        Returns:
            None
        """
        entry = QuarantineEntry(
            QUARANTINED_CASE, "flaky", TODAY, observed_model="gemini-3.8-flash"
        )
        suite = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")] + [
            graded(f"MQC_TASK_{index}::MQC_RULE_r", resolved_model="gemini-4.0-pro")
            for index in range(10)
        ]

        result = verdict(suite, VerdictConfig(quarantine=[entry]), TODAY)

        assert result.green is False, (
            "an entry observed against one model survived a run reporting "
            "another, so an accepted finding outlived the model it was about"
        )
        assert "V5" in result.breached_rules

        # THE SAME MODEL LEAVES IT ALONE, which is what makes the comparison a
        # trigger rather than an unconditional expiry.
        same = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")] + [
            graded(f"MQC_TASK_{index}::MQC_RULE_r", resolved_model="gemini-3.8-flash")
            for index in range(10)
        ]
        assert verdict(same, VerdictConfig(quarantine=[entry]), TODAY).green is True

        # A MIXED CORPUS LEAVES THE TRIGGER UNEVALUATED, so the window alone
        # applies and this entry is inside it.
        mixed = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")] + [
            graded(
                f"MQC_TASK_{index}::MQC_RULE_r",
                resolved_model="gemini-3.8-flash" if index % 2 else "gemini-4.0-pro",
            )
            for index in range(10)
        ]
        assert verdict(mixed, VerdictConfig(quarantine=[entry]), TODAY).green is True

    def MQC_CMN_UNI_112038_an_unconfirmed_entry_is_honoured_and_never_red(
        self,
    ) -> None:
        """An entry missing its date or model excludes without failing the run.

        Its expiry cannot be evaluated, which is the quarantine mechanism
        failing rather than a finding about a model, and ``QC_HARNESS_*``
        resolves to skip or broken and never to a failure. Failing the run would
        attribute our bookkeeping defect to the model under test.

        **The exclusion still stands**, because dropping it would let an
        already-accepted failure fail the run.

        Design: ``cmn_verdict_and_cli.md`` section 4.6.4.

        Returns:
            None
        """
        for entry in (
            QuarantineEntry(QUARANTINED_CASE, "flaky"),
            QuarantineEntry(QUARANTINED_CASE, "flaky", date(2020, 1, 1)),
            QuarantineEntry(QUARANTINED_CASE, "flaky", observed_model="gemini-3.8-flash"),
        ):
            result = verdict(
                passing_suite(), VerdictConfig(quarantine=[entry]), TODAY
            )

            assert result.green is True, (
                "an unconfirmed entry failed the run, so our bookkeeping defect "
                "was reported as a finding about the model"
            )
            assert "V5" not in result.breached_rules
            assert result.quarantined == [QUARANTINED_CASE], (
                "an unconfirmed entry stopped excluding, so an accepted failure "
                "would fail the run"
            )
            assert result.unconfirmed_quarantine == [QUARANTINED_CASE]

class TestMQCQuarantineFiles:
    """One file per engine, an absent file, and the digest that records it."""

    def MQC_CMN_UNI_112039_an_absent_quarantine_file_is_an_empty_quarantine(
        self, tmp_path: Path
    ) -> None:
        """Quarantine is read per engine and an absent file yields nothing.

        An absent file is the default state, so no file is needed to say an
        engine has nothing quarantined, and an unnamed engine reads nothing at
        all rather than guessing which file to open.

        Design: ``cmn_verdict_and_cli.md`` section 4.6.3.

        Args:
            tmp_path (Path): A directory standing in for ``config/``.

        Returns:
            None
        """
        assert not load_quarantine_for(tmp_path, "gemini")
        assert not load_quarantine_for(tmp_path, "")

        folder = tmp_path / "quarantine"
        folder.mkdir()
        folder.joinpath("gemini.yaml").write_text(
            "quarantine:\n"
            "  - case_id: MQC_TASK_a::MQC_RULE_r\n"
            "    reason: flaky under load\n"
            "    quarantined_on: 2026-09-20\n"
            "    observed_model: gemini-3.8-flash\n"
            "    ticket: MQC-41\n",
            encoding="utf-8",
        )
        folder.joinpath("openai.yaml").write_text(
            "quarantine:\n"
            "  - case_id: MQC_TASK_b::MQC_RULE_r\n"
            "    reason: rate limited\n",
            encoding="utf-8",
        )

        loaded = load_quarantine_for(tmp_path, "gemini")
        assert [entry.case_id for entry in loaded] == ["MQC_TASK_a::MQC_RULE_r"]
        assert loaded[0].observed_model == "gemini-3.8-flash"
        assert loaded[0].ticket == "MQC-41"
        assert loaded[0].confirmed is True

        # ONE ENGINE'S FILE IS NOT ANOTHER'S, which is the point of the split.
        other = load_quarantine_for(tmp_path, "openai")
        assert [entry.case_id for entry in other] == ["MQC_TASK_b::MQC_RULE_r"]
        assert other[0].confirmed is False, (
            "an entry with no date and no model read as confirmed, so its "
            "expiry would be evaluated against nothing"
        )

    def MQC_CMN_UNI_112040_the_consulted_quarantine_hash_is_recorded(self) -> None:
        """The entries a run consulted are recorded by hash in its metadata.

        Quarantine changes the pass-rate denominator, so a stored pass rate
        cannot be read without knowing which entries were excluded.

        **Over the parsed entries**, so the digest moves when an entry's claim
        moves and not when a comment is reworded. No entries hash to the empty
        string, which is the default state rather than a suspicious zero.

        Design: ``cmn_verdict_and_cli.md`` section 4.6.6.

        Returns:
            None
        """
        assert quarantine_digest([]) == ""

        entry = QuarantineEntry(
            "MQC_TASK_a::MQC_RULE_r", "flaky", date(2026, 9, 20),
            observed_model="gemini-3.8-flash",
        )
        digest = quarantine_digest([entry])
        assert digest.startswith("sha256:")

        # ORDER IS NOT A DIFFERENT QUARANTINE, so the digest is stable under it.
        second = QuarantineEntry(
            "MQC_TASK_b::MQC_RULE_r", "slow", date(2026, 9, 21),
            observed_model="gemini-3.8-flash",
        )
        assert quarantine_digest([entry, second]) == quarantine_digest([second, entry])

        # A CHANGED CLAIM IS A DIFFERENT QUARANTINE, which is what it detects.
        moved = QuarantineEntry(
            "MQC_TASK_a::MQC_RULE_r", "flaky", date(2026, 9, 21),
            observed_model="gemini-3.8-flash",
        )
        assert quarantine_digest([moved]) != digest

        # AND IT REACHES THE RECORD, beside the rule set hash it mirrors.
        fields = RunContext(
            "ci", "full", True, rule_set_hash="sha256:abc", quarantine_hash=digest
        ).as_fields()
        assert fields["quarantine_hash"] == digest

    def MQC_CMN_UNI_112041_a_malformed_ticket_reference_is_reported(
        self, tmp_path: Path
    ) -> None:
        """A ticket reference is validated although nothing reads it.

        The field is inert by design, pending a tracking system. It is
        validated anyway because an annotation nothing reads is where a typo
        survives indefinitely, and the point of the field is that somebody can
        follow it later.

        An absent reference is accepted: the field is optional.

        Design: ``cmn_verdict_and_cli.md`` section 4.6.7.

        Args:
            tmp_path (Path): A directory standing in for ``config/``.

        Returns:
            None
        """
        folder = tmp_path / "quarantine"
        folder.mkdir()
        target = folder / "gemini.yaml"

        for accepted in ("MQC-41", "https://tracker.example/browse/MQC-41", ""):
            target.write_text(
                "quarantine:\n"
                "  - case_id: MQC_TASK_a::MQC_RULE_r\n"
                "    reason: flaky\n"
                f"    ticket: {accepted!r}\n",
                encoding="utf-8",
            )
            assert load_quarantine_for(tmp_path, "gemini")[0].ticket == accepted

        for rejected in ("see the board", "mqc-41", "MQC41", "tracker/MQC-41"):
            target.write_text(
                "quarantine:\n"
                "  - case_id: MQC_TASK_a::MQC_RULE_r\n"
                "    reason: flaky\n"
                f"    ticket: {rejected!r}\n",
                encoding="utf-8",
            )
            with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR"):
                load_quarantine_for(tmp_path, "gemini")

        # A REASON IS STILL MANDATORY, which the date no longer is.
        target.write_text(
            "quarantine:\n  - case_id: MQC_TASK_a::MQC_RULE_r\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="carries no reason"):
            load_quarantine_for(tmp_path, "gemini")


class TestMQCQuarantineThroughTheTool:
    """The evaluation date arriving on a command line, deciding an expiry."""
    def MQC_CMN_UNI_112042_the_named_evaluation_date_reaches_quarantine_expiry(
        self, tmp_path: Path
    ) -> None:
        """``--as-of`` is the date the tool evaluates quarantine expiry against.

        The verdict reads no clock, so the date arrives on the command line.
        Before the window the entry excludes and the run is green; on reaching
        it the entry has lapsed and the run is red.

        **Driven through ``main`` with an injected configuration directory.**
        The shipped quarantine is empty, so without the injection there is
        nothing for the flag to decide and the end-to-end path could not be
        exercised at all.

        Design: ``cmn_verdict_and_cli.md`` sections 4.6.2 and 4.6.6.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        config = tmp_path / "config"
        (config / "quarantine").mkdir(parents=True)
        (config / "quarantine" / "gemini.yaml").write_text(
            "quarantine:\n"
            "  - case_id: MQC_TASK_a::MQC_RULE_r\n"
            "    reason: flaky under load\n"
            "    quarantined_on: 2026-09-01\n"
            "    observed_model: gemini-3.8-flash\n",
            encoding="utf-8",
        )

        # A SECOND GRADED CASE, UNQUARANTINED. With only the quarantined one,
        # excluding it empties the pass-rate denominator and V6 reports the run
        # as having measured nothing, which is correct and not what this covers.
        artifact = gated_artifact(results=[
            {"case_id": "MQC_TASK_pre::MQC_RULE_pre", "layer": "UNI",
             "outcome": "pass"},
            {"case_id": "MQC_TASK_a::MQC_RULE_r", "layer": "EVAL",
             "outcome": "pass", "priority": 2, "engine": "gemini",
             "resolved_model": "gemini-3.8-flash"},
            {"case_id": "MQC_TASK_b::MQC_RULE_r", "layer": "EVAL",
             "outcome": "pass", "priority": 2, "engine": "gemini",
             "resolved_model": "gemini-3.8-flash"},
        ])
        path = tmp_path / "results.json"
        path.write_text(json.dumps(artifact), encoding="utf-8")

        # DAY 20 OF A 21-DAY WINDOW, so the entry still holds.
        assert main(
            ["--as-of", "2026-09-21", str(path)], config_dir=config
        ) == EXIT_GREEN

        # DAY 21, where it lapses and the run goes red.
        assert main(
            ["--as-of", "2026-09-22", str(path)], config_dir=config
        ) == EXIT_RED, (
            "the named date did not reach quarantine expiry, so the flag "
            "decided nothing and an entry could never lapse"
        )


class TestMQCQuarantineReconciliation:
    """What re-observing a quarantined case decides about its entry."""

    def MQC_CMN_UNI_112043_reconciling_decides_each_entry_from_what_was_observed(
        self,
    ) -> None:
        """Each entry is dropped, re-stamped or left alone by what was observed.

        A case that passed throughout loses its entry; one that failed any
        observation is re-stamped with the date and model of this run; one that
        produced no observations is kept unchanged and reported as undecided,
        because nothing was measured and so nothing is decided.

        **Any failure re-stamps rather than a majority.** The within-case rule
        is binary, so a case failing one of five still has a finding.

        **Undecided is why an action accompanies each entry.** A case nobody
        ran and a case that passed are indistinguishable from the surviving
        entries alone, and the difference is between fixed and not asked.

        Design: ``cmn_verdict_and_cli.md`` section 4.6.10.

        Returns:
            None
        """
        stale = date(2026, 9, 1)
        entries = [
            QuarantineEntry("MQC_TASK_fixed::MQC_RULE_r", "flaky", stale,
                            observed_model="gemini-3.8-flash", ticket="MQC-7"),
            QuarantineEntry("MQC_TASK_still::MQC_RULE_r", "flaky", stale,
                            observed_model="gemini-3.8-flash"),
            QuarantineEntry("MQC_TASK_unrun::MQC_RULE_r", "flaky", stale,
                            observed_model="gemini-3.8-flash"),
        ]
        remaining, actions = reconcile(
            entries,
            {
                "MQC_TASK_fixed::MQC_RULE_r": [True, True, True],
                "MQC_TASK_still::MQC_RULE_r": [True, False, True, True, True],
                "MQC_TASK_unrun::MQC_RULE_r": [],
            },
            TODAY,
            "gemini-4.0-pro",
        )

        assert actions == {
            "MQC_TASK_fixed::MQC_RULE_r": DROPPED,
            "MQC_TASK_still::MQC_RULE_r": STAMPED,
            "MQC_TASK_unrun::MQC_RULE_r": UNDECIDED,
        }
        assert [entry.case_id for entry in remaining] == [
            "MQC_TASK_still::MQC_RULE_r", "MQC_TASK_unrun::MQC_RULE_r",
        ]

        # THE SURVIVOR CARRIES THIS RUN, which is what makes its window restart
        # and its model comparison current.
        restamped = remaining[0]
        assert restamped.quarantined_on == TODAY
        assert restamped.observed_model == "gemini-4.0-pro"

        # AND THE UNDECIDED ONE IS UNTOUCHED, so a run that did not ask cannot
        # silently extend an entry's window.
        untouched = remaining[1]
        assert untouched.quarantined_on == stale
        assert untouched.observed_model == "gemini-3.8-flash"

        # A CASE MISSING FROM THE MAPPING IS NOT MEASURED EITHER, which is what
        # a selection narrower than the file produces.
        remaining, actions = reconcile(entries, {}, TODAY, "gemini-4.0-pro")
        assert set(actions.values()) == {UNDECIDED}
        assert len(remaining) == len(entries)

        # THE ENTRY IS REPLACED, NEVER MUTATED: the record is frozen and the
        # ticket survives a re-stamp.
        assert entries[0].quarantined_on == stale
        stamped_ticket = reconcile(
            entries[:1], {"MQC_TASK_fixed::MQC_RULE_r": [False]}, TODAY, "gemini-4.0-pro"
        )[0][0]
        assert stamped_ticket.ticket == "MQC-7"


class TestMQCExclusionReporting:
    """What a pass says about the cases it left out of the denominator."""

    def MQC_CMN_UNI_112147_a_pass_reports_the_bands_it_excluded(
        self, caplog: pytest.LogCaptureFixture, tmp_path: Path
    ) -> None:
        """A passing verdict carries every exclusion and the band of each.

        Quarantine removes a case from the pass rate, so a green is green over
        what was measured. A run that said nothing about its exclusions read
        exactly like one that excluded nothing.

        **Quarantine never exempts V1**, which this also pins: a failing P0 is
        red whatever the quarantine file says, so a blocking band surviving
        into a pass means the case passed and the entry is stale, or it
        skipped.

        **A case with no observations reports no band**, because nothing ran it.

        Design: ``cmn_verdict_and_cli.md`` sections 4.6.11 to 4.6.11.2.

        Args:
            caplog (pytest.LogCaptureFixture): Captures what the run reports.
            tmp_path (Path): For the artifact and the injected configuration.

        Returns:
            None
        """
        stale = QuarantineEntry(
            "MQC_TASK_stale::MQC_RULE_r", "no longer reproduces", TODAY,
            observed_model="gemini-3.8-flash",
        )
        minor = QuarantineEntry(
            "MQC_TASK_minor::MQC_RULE_r", "cosmetic, open with the vendor", TODAY,
            observed_model="gemini-3.8-flash",
        )
        absent = QuarantineEntry(
            "MQC_TASK_absent::MQC_RULE_r", "not in this selection", TODAY,
            observed_model="gemini-3.8-flash",
        )

        suite = passing_suite() + [
            graded("MQC_TASK_stale::MQC_RULE_r", priority=0),
            graded("MQC_TASK_minor::MQC_RULE_r", "fail", priority=3),
        ]
        result = verdict(
            suite, VerdictConfig(quarantine=[stale, minor, absent]), TODAY
        )

        assert result.green is True, (
            "the suite was built to pass, so this case cannot tell a reported "
            "exclusion from a reported breach"
        )

        # THE BANDS COME FROM THE OBSERVATIONS, and a case nobody ran has none.
        assert result.excluded_bands == {
            "MQC_TASK_stale::MQC_RULE_r": 0,
            "MQC_TASK_minor::MQC_RULE_r": 3,
        }
        assert "MQC_TASK_absent::MQC_RULE_r" in result.quarantined

        with caplog.at_level(logging.INFO, logger="cmn.verdict_tool"):
            report_exclusions(result)

        blocking = [
            entry for entry in caplog.records if entry.levelno == logging.WARNING
        ]
        assert len(blocking) == 1, (
            "a release-blocking band left the denominator and nothing warned, "
            "so a green reads as green over everything"
        )
        assert "MQC_TASK_stale::MQC_RULE_r (P0)" in blocking[0].getMessage()

        reported = " | ".join(
            entry.getMessage() for entry in caplog.records
            if entry.levelno == logging.INFO
        )
        assert "MQC_TASK_minor::MQC_RULE_r (P3)" in reported
        assert "MQC_TASK_absent::MQC_RULE_r (not run)" in reported

        # A RUN THAT EXCLUDED NOTHING SAYS NOTHING, so the report is a signal
        # rather than a line every run carries.
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="cmn.verdict_tool"):
            report_exclusions(verdict(passing_suite(), VerdictConfig(), TODAY))
        # FROM THE REPORTER, NOT FROM EVERYTHING. The claim is that
        # `report_exclusions` says nothing, and `verdict` above it logs its own
        # distribution note: asserting on every record made this case depend on
        # nothing else in the project ever logging at INFO.
        assert not [
            entry for entry in caplog.records if entry.name == "cmn.verdict_tool"
        ], (
            "a run that excluded nothing reported an exclusion, so the report "
            "is a line every run carries rather than a signal"
        )

        # AND QUARANTINE NEVER EXEMPTS V1. A failing P0 is red whatever the
        # file says, which is why a blocking band in a pass means something
        # else entirely.
        blocked = verdict(
            passing_suite() + [graded("MQC_TASK_stale::MQC_RULE_r", "fail", priority=0)],
            VerdictConfig(quarantine=[stale]),
            TODAY,
        )

        assert blocked.green is False
        assert "V1" in blocked.breached_rules, (
            "a quarantined P0 failure did not fail the run, so an accepted "
            "release blocker can be turned into a green"
        )

        # AND `main` HAS TO CALL IT. Asserting the reporter alone left this
        # case passing with the call removed from the tool, which is a check
        # covering one of two halves.
        config = tmp_path / "config"
        (config / "quarantine").mkdir(parents=True)
        (config / "quarantine" / "gemini.yaml").write_text(
            "quarantine:\n"
            "  - case_id: MQC_TASK_a::MQC_RULE_r\n"
            "    reason: no longer reproduces\n"
            "    quarantined_on: 2026-10-01\n"
            "    observed_model: gemini-3.8-flash\n",
            encoding="utf-8",
        )
        artifact = gated_artifact(results=[
            {"case_id": "MQC_TASK_pre::MQC_RULE_pre", "layer": "UNI",
             "outcome": "pass"},
            {"case_id": "MQC_TASK_a::MQC_RULE_r", "layer": "EVAL",
             "outcome": "pass", "priority": 0, "engine": "gemini",
             "resolved_model": "gemini-3.8-flash"},
            {"case_id": "MQC_TASK_b::MQC_RULE_r", "layer": "EVAL",
             "outcome": "pass", "priority": 2, "engine": "gemini",
             "resolved_model": "gemini-3.8-flash"},
        ])
        path = tmp_path / "results.json"
        path.write_text(json.dumps(artifact), encoding="utf-8")

        caplog.clear()
        with caplog.at_level(logging.INFO, logger="cmn.verdict_tool"):
            assert main(
                ["--as-of", "2026-10-02", str(path)], config_dir=config
            ) == EXIT_GREEN

        warned = [
            entry.getMessage() for entry in caplog.records
            if entry.levelno == logging.WARNING
        ]
        assert any("MQC_TASK_a::MQC_RULE_r (P0)" in note for note in warned), (
            "the tool passed and never reported the blocking band it excluded, "
            "so a green over a filtered denominator reads as a clean green"
        )
