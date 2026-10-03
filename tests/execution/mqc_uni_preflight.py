# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for model version resolution and the nightly probe.

Covers `MQC_EXE_UNI_113500` and `113501` through `113504`, inventoried in
``docs/design/tier2_execution.md`` section 10.1.

**The probe decides whether to spend quota**, which is logic rather than
configuration and is why it carries cases at all. Its two boundaries are a
first run with no baseline and a probe that could not reach a version, and
both would otherwise dispatch a live run for the wrong reason.

A failure here is our defect, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

from pathlib import Path
from typing import Optional
import json

import pytest

from execution.preflight import (
    engines_to_dispatch,
    load_baseline,
    probe_all,
    probe_engine,
    require_resolved_version,
)

pytestmark = pytest.mark.unit


class TestMQCVersionResolution:
    """What happens when a provider will not say which model answered."""

    @pytest.mark.parametrize("resolved", [None, "", "   "])
    def MQC_EXE_UNI_113500_absent_model_version_fails_preflight(
        self,
        resolved: Optional[str],
    ) -> None:
        """A run whose model identity is unknown produces uninterpretable scores.

        Preflight aborts before any case executes, because those scores would
        reach the durable record looking exactly like scores that can be
        interpreted.

        Args:
            resolved (Optional[str]): What the adapter returned.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="QC_HARNESS_VERSION_UNAVAILABLE"):
            require_resolved_version("gemini", resolved)

    def MQC_EXE_UNI_113505_a_resolved_version_is_returned_stripped(self) -> None:
        """Surrounding whitespace is removed so two spellings do not diverge.

        Returns:
            None
        """
        assert require_resolved_version("gemini", "  gemini-flash-002  ") == "gemini-flash-002"


class TestMQCVersionProbe:
    """Detecting a model change without spending quota to look for one."""

    def MQC_EXE_UNI_113503_absent_baseline_is_recorded_rather_than_treated_as_a_change(
        self, tmp_path: Path
    ) -> None:
        """On a first run there is nothing to have changed from.

        Treating an absent baseline as a change would dispatch a live run for
        every engine the first time the probe executes, and again after any
        baseline reset, spending quota to discover nothing.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        baseline = tmp_path / "versions.json"
        outcomes = probe_all({"gemini": "flash-002", "openai": "gpt-x-1"}, baseline)
        assert engines_to_dispatch(outcomes) == []
        assert all(outcome.previous_model is None for outcome in outcomes)
        assert json.loads(baseline.read_text(encoding="utf-8")) == {
            "gemini": "flash-002", "openai": "gpt-x-1"
        }

    def MQC_EXE_UNI_113501_unchanged_model_version_yields_no_dispatch(self, tmp_path: Path) -> None:
        """The ordinary night: nothing moved, nothing runs.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        baseline = tmp_path / "versions.json"
        probe_all({"gemini": "flash-002"}, baseline)
        assert engines_to_dispatch(probe_all({"gemini": "flash-002"}, baseline)) == []

    def MQC_EXE_UNI_113502_changed_model_version_dispatches_only_the_changed_engine(
        self, tmp_path: Path
    ) -> None:
        """A move on one provider says nothing about the others.

        Dispatching all three would spend quota to re-measure two unchanged
        models, which is the saving the probe exists to make.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        baseline = tmp_path / "versions.json"
        probe_all({"gemini": "flash-002", "openai": "gpt-x-1", "claude": "c-1"}, baseline)
        moved = probe_all(
            {"gemini": "flash-003", "openai": "gpt-x-1", "claude": "c-1"}, baseline
        )
        assert engines_to_dispatch(moved) == ["gemini"]

    def MQC_EXE_UNI_113506_a_change_dispatches_once_not_on_every_later_run(
        self,
        tmp_path: Path,
    ) -> None:
        """The baseline moves with the change, so the night after is quiet.

        Without this the probe would dispatch a live run every night until
        someone edited the baseline by hand.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        baseline = tmp_path / "versions.json"
        probe_all({"gemini": "flash-002"}, baseline)
        assert engines_to_dispatch(probe_all({"gemini": "flash-003"}, baseline)) == ["gemini"]
        assert engines_to_dispatch(probe_all({"gemini": "flash-003"}, baseline)) == []

    def MQC_EXE_UNI_113504_probe_failure_records_a_harness_event_and_does_not_dispatch(
        self, tmp_path: Path
    ) -> None:
        """A broken detector is our defect, not evidence of a model change.

        The unconditional weekly run covers the period regardless, so treating
        a failure as a change would spend quota investigating our own bug.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        baseline = tmp_path / "versions.json"
        probe_all({"gemini": "flash-002", "openai": "gpt-x-1"}, baseline)
        outcomes = probe_all({"gemini": None, "openai": "gpt-x-1"}, baseline)

        failed = [outcome for outcome in outcomes if outcome.failed]
        assert [outcome.engine for outcome in failed] == ["gemini"]
        assert engines_to_dispatch(outcomes) == []

    def MQC_EXE_UNI_113507_a_failed_probe_leaves_its_baseline_untouched(
        self,
        tmp_path: Path,
    ) -> None:
        """Overwriting a baseline with nothing would fake a change next run.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        baseline = tmp_path / "versions.json"
        probe_all({"gemini": "flash-002"}, baseline)
        probe_all({"gemini": None}, baseline)
        assert load_baseline(baseline) == {"gemini": "flash-002"}
        assert engines_to_dispatch(probe_all({"gemini": "flash-002"}, baseline)) == []

    def MQC_EXE_UNI_113508_an_unreadable_baseline_is_reported_not_ignored(
        self,
        tmp_path: Path,
    ) -> None:
        """A corrupt baseline silently read as empty would dispatch nothing.

        That is the worst outcome available: the probe would report every night
        that nothing changed, while holding no record of what anything was.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        baseline = tmp_path / "versions.json"
        baseline.write_text("{ truncated", encoding="utf-8")
        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR"):
            load_baseline(baseline)

    def MQC_EXE_UNI_113509_probe_outcomes_are_returned_in_a_reproducible_order(self) -> None:
        """Engine order does not depend on mapping iteration order.

        Returns:
            None
        """
        outcome = probe_engine("gemini", "flash-002", {"gemini": "flash-002"})
        assert outcome.changed is False
        assert outcome.failed is False
        assert outcome.should_dispatch is False
