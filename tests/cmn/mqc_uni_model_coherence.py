# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for one corpus naming one model.

Covers `MQC_CMN_UNI_112320` through `112322`, inventoried in
``docs/design/cmn_verdict_and_cli.md`` section 4.9.6.

**Split out of ``mqc_uni_verdict.py`` on 2026-09-26**, which had reached 1043
lines against a 1000-line limit. The split is by subject rather than by size:
these cases ask whether a run has a single subject at all, which is a question
about the corpus and prior to any rule that scores it.

A failure here is **not a model finding**, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

from datetime import date
from typing import Any

import pytest

from cmn.observations import Observation
from cmn.verdict import VerdictConfig, mixed_model_engines, verdict

pytestmark = pytest.mark.unit

_TODAY = date(2026, 1, 15)


def _graded(
    case_id: str, outcome: str = "pass", priority: int = 2, **extra: Any
) -> Observation:
    """Build one graded observation.

    Args:
        case_id (str): Which case.
        outcome (str): What it produced.
        priority (int): Its priority band.
        **extra: Any further field to set.

    Returns:
        Observation: The built record.
    """
    return Observation(
        case_id=case_id, layer="EVAL", outcome=outcome, priority=priority, **extra
    )


def _passing_suite(count: int = 10) -> list[Observation]:
    """Build a suite that satisfies every rule.

    Args:
        count (int): How many graded observations to produce.

    Returns:
        list[Observation]: One passing precondition plus passing graded cases.
    """
    return [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")] + [
        _graded(f"MQC_TASK_{index}::MQC_RULE_r") for index in range(count)
    ]


class TestMQCOneCorpusOneModel:
    """A corpus spanning two model versions is not about either of them."""

    def MQC_CMN_UNI_112320_two_models_on_one_engine_unsounds_the_run(self) -> None:
        """A mixed corpus exits 3, because no result attributes to one model.

        **Newly reachable rather than theoretical.** A free-tier quota is keyed
        per model, so once the day's twenty requests are spent the obvious way
        to keep recording is to switch model, and the fixture store is keyed by
        engine (harness tier2_execution.md section 8.6.4). `resolved_models` is
        one value per engine and would silently keep whichever was written
        last.

        Returns:
            None
        """
        observations = _passing_suite(8)
        observations += [
            _graded("MQC_TASK_a::MQC_RULE_r", engine="gemini",
                    resolved_model="gemini-3.8-flash"),
            _graded("MQC_TASK_b::MQC_RULE_r", engine="gemini",
                    resolved_model="gemini-3.9-flash"),
        ]

        result = verdict(observations, VerdictConfig(), _TODAY)

        # EXIT 3, NOT 1. Nothing scored badly; the run has no single subject.
        assert result.exit_code == 3
        assert result.green is False
        assert "RUN_UNSOUND" in result.breached_rules
        reason = " ".join(breach.reason for breach in result.breaches)
        assert "gemini-3.8-flash" in reason and "gemini-3.9-flash" in reason

    def MQC_CMN_UNI_112321_one_model_per_engine_is_sound_across_engines(self) -> None:
        """Two engines each reporting their own model is the ordinary case.

        **The check is per engine, not across the run.** A run measuring two
        providers reports two models and is perfectly coherent; folding that
        into a mixture would make the ordinary multi-engine run unsound.

        Returns:
            None
        """
        observations = _passing_suite(8)
        observations += [
            _graded("MQC_TASK_a::MQC_RULE_r", engine="gemini",
                    resolved_model="gemini-3.8-flash"),
            _graded("MQC_TASK_b::MQC_RULE_r", engine="claude",
                    resolved_model="claude-opus-5"),
        ]

        assert not mixed_model_engines(observations)
        assert verdict(observations, VerdictConfig(), _TODAY).exit_code == 0

    def MQC_CMN_UNI_112322_an_observation_with_no_model_is_not_a_second_version(
        self,
    ) -> None:
        """A skip never reached a model, so its blank is not a mixture.

        **Counting the blank would report a mixture that did not happen**, and
        a rate-limited run is full of skips: the very condition that makes the
        real mixture tempting would otherwise fake one on its own.

        Returns:
            None
        """
        observations = _passing_suite(8)
        observations += [
            _graded("MQC_TASK_a::MQC_RULE_r", engine="gemini",
                    resolved_model="gemini-3.8-flash"),
            _graded("MQC_TASK_b::MQC_RULE_r", outcome="skip", engine="gemini",
                    resolved_model="", skip_reason="QC_HARNESS_RATE_LIMIT"),
        ]

        assert not mixed_model_engines(observations)
