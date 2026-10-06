# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Whether a judgement was available, and what a gap in the store measures.

Covers `MQC_EVL_UNI_114115`, inventoried in `tier3_evaluation.md` section 6.5.

**Split from `mqc_uni_pipeline.py` on 2026-10-06**, which stood at 895 lines
and would have passed the 1000-line ceiling with this case in it. The runway
rule is to move the next case out at 900 rather than to split on the day the
gate goes red, and this is the first case written under it.

**The subject is narrower than the pipeline's**: not what evaluation does with
a response, but what it does when the half of the measurement that needs a
recording has none. The answer is the project's oldest rule about its own
failures, that a `QC_HARNESS_*` event is a skip and never a failure.
"""

import pytest

from evaluation.pipeline import evaluate_observation
from execution.replay import FixtureMissing, FixtureStale
from ingestion.schemas import GoldenRuleSet

from tests.evaluation.judge_doubles import refusing_judge

# THE FIXTURE AND THE CONTEXT BUILDER ARE IMPORTED, NOT COPIED. A second
# copy of a fixture builder is the drift this project keeps paying for, and
# importing the decorated function registers the fixture it declares.
from tests.evaluation.mqc_uni_pipeline import (  # pylint: disable=unused-import
    _context,
    fixture_rules,  # the `rules` fixture this module's case requests
)

pytestmark = pytest.mark.unit


class TestMQCJudgementAvailability:
    """A gap in the judgement store, and what it is allowed to report."""

    def MQC_EVL_UNI_114115_an_unavailable_judgement_skips_and_keeps_its_assertions(
        self,
        rules: GoldenRuleSet,
    ) -> None:
        """A recording gap measures nothing, and says so without failing.

        **A `QC_HARNESS_*` event is a skip, never a failure**
        (`framework-rules.md` section 4). The candidate path learned this when
        both store exceptions escaped dispatch as errors, because each
        inherits from ``Exception`` alone and the handler was written for
        ``ValueError``. This is the judge side of the same gap.

        **It surfaced when an assertion was repaired.** Assertions gate
        judging, so a case whose assertion failed never reached the judge and
        no judgement was ever recorded for it. Fix the assertion and the
        observation arrives at a store that has nothing for it.

        **The assertion results travel with the skip**, which is the point: an
        observation that failed an assertion still reports that failure under
        its own model code, and only the judged half is missing.

        Design: ``tier3_evaluation.md`` section 6.5.

        Args:
            rules (GoldenRuleSet): The rule set.

        Returns:
            None
        """
        for error, expected in (
            (FixtureMissing("QC_HARNESS_FIXTURE_MISSING: no judgement"),
             "QC_HARNESS_FIXTURE_MISSING"),
            (FixtureStale("QC_HARNESS_FIXTURE_STALE: recorded elsewhere"),
             "QC_HARNESS_FIXTURE_STALE"),
        ):
            result = evaluate_observation(
                _context(
                    rules,
                    "It requires five years of Python.",
                    produced_output=True,
                ),
                refusing_judge(error),
            )
            assert result.judged is False, (
                f"a judgement that could not be replayed was counted as made, "
                f"so a gap in the recordings scores as a result: {expected}"
            )
            assert result.judge_skipped_reason == "judgement_unavailable", (
                f"the skip does not name itself, so a reader cannot tell a "
                f"recording gap from a judge that replied unusably: "
                f"{result.judge_skipped_reason!r}"
            )
            assert expected in result.taxonomy_codes, (
                f"the store's own code is absent, so the two gaps are "
                f"indistinguishable: {result.taxonomy_codes}"
            )

            # AND THE ASSERTIONS SURVIVED. Discarding them would throw away the
            # measurement that did happen along with the one that did not.
            assert result.assertion_results, (
                "the assertion results were dropped with the judgement, so an "
                "observation that failed an assertion now reports nothing"
            )
