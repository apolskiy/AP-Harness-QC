# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for what a run cost.

Covers `MQC_CMN_UNI_11183` through `11189`, inventoried in
``docs/design/cmn_verdict_and_cli.md`` section 12.

**Every case here prices a fixed usage against a fixed table on a fixed date.**
Cost is a pure function of those three, for the reason the verdict is: a figure
that changes between two readings of one corpus is not a measurement. So nothing
here reads a clock, and the date is always injected.

**The shipped table is exercised, not a fixture of one.** The figures in
`config/pricing.yaml` were read from a provider's page and every one of them
changes on a published date, so the cases that matter are the ones asserting the
file the harness actually loads.

A failure here is our defect, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

from datetime import date
from pathlib import Path

import pytest

from cmn.observations import Observation
from cmn.pricing import (
    PriceTable,
    cost_of,
    cost_report,
    load_price_table,
    stale_prices,
)
from cmn.tokens import CaseUsage, TokenUsage

pytestmark = pytest.mark.unit

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_PRICING = _REPOSITORY_ROOT / "config" / "pricing.yaml"

# The model the roster configures and the only one a live run currently spends
# against: the other two engines have no credential provisioned (A3).
_FLASH = "gemini-3.8-flash"

# Inside the first published window, and inside the second. The provider
# announced the change in advance, which is the whole reason the table is dated.
_BEFORE_THE_RISE = date(2026, 9, 27)
_AFTER_THE_RISE = date(2027, 6, 1)


@pytest.fixture(name="table")
def fixture_table() -> PriceTable:
    """Return the shipped price table.

    Returns:
        PriceTable: What the harness loads, not a fixture standing in for it.
    """
    return load_price_table(_PRICING)


class TestMQCPriceTable:
    """What the shipped table says, and what it refuses to say."""

    def MQC_CMN_UNI_11183_a_price_window_that_has_closed_is_reported(
        self, table: PriceTable
    ) -> None:
        """A stale price does not report an error, it reports a smaller number.

        **That is why this is a case rather than a comment.** Every rate in the
        shipped table doubles on 1 January 2027, a date the provider published
        in advance. A table overtaken by that change would price a run at the
        older, smaller figure and read as correct, which is worse than refusing
        to produce a figure at all.

        Args:
            table (PriceTable): The shipped table.

        Returns:
            None
        """
        assert not stale_prices(table, _BEFORE_THE_RISE), (
            "the shipped table does not cover today, so every cost it reports "
            "is priced against a window that has closed"
        )
        assert not stale_prices(table, _AFTER_THE_RISE), (
            "the shipped table does not cover the announced increase, so a run "
            "after it would be priced at the superseded rate"
        )
        # A TABLE THAT ENDS IS REPORTED, which is the condition above guarding.
        ending = PriceTable(tiers={model: [window for window in windows
                                           if window.effective_until is not None]
                                  for model, windows in table.tiers.items()})
        assert stale_prices(ending, _AFTER_THE_RISE) == sorted(ending.tiers)

    def MQC_CMN_UNI_11184_the_published_increase_is_priced_from_its_own_date(
        self, table: PriceTable
    ) -> None:
        """One model, two windows, and the date decides which applies.

        **Not extrapolated from the nearest window.** Carrying yesterday's rate
        across a published change is inventing a figure, and the figure would be
        half the real one.

        Args:
            table (PriceTable): The shipped table.

        Returns:
            None
        """
        before = table.price_for(_FLASH, _BEFORE_THE_RISE)
        after = table.price_for(_FLASH, _AFTER_THE_RISE)

        assert before is not None and after is not None
        assert after.input_per_million == pytest.approx(before.input_per_million * 2)
        assert after.output_per_million == pytest.approx(before.output_per_million * 2)

    def MQC_CMN_UNI_11185_an_unpriced_model_yields_no_figure_rather_than_zero(
        self, table: PriceTable
    ) -> None:
        """Zero is the one wrong answer that looks like a right one.

        A run against an unpriced model has not been measured, and reporting
        nothing spent would read as a run that was free. `claude-opus-5-5` is
        deliberately absent from the table: no credential is provisioned, so it
        runs replay, and pricing it now would state a figure nobody can spend
        against and nobody would notice going stale.

        Args:
            table (PriceTable): The shipped table.

        Returns:
            None
        """
        usage = TokenUsage(input_tokens=1_000, output_tokens=1_000)

        assert cost_of(usage, "claude-opus-5-5", table, _BEFORE_THE_RISE) is None
        assert cost_of(usage, _FLASH, table, _BEFORE_THE_RISE) is not None


class TestMQCCostArithmetic:
    """What the four token categories cost, and which rate each takes."""

    def MQC_CMN_UNI_11186_thinking_is_billed_at_the_output_rate(
        self, table: PriceTable
    ) -> None:
        """The count that was costing money invisibly.

        **Reported apart from the visible output and billed as it.** Gen AI
        returns `thoughts_token_count` separately from
        `candidates_token_count`, so a harness reading only the second
        understates the bill by however much the model thought. On a reasoning
        model that is the larger number.

        Args:
            table (PriceTable): The shipped table.

        Returns:
            None
        """
        visible = TokenUsage(output_tokens=1_000)
        thought = TokenUsage(thinking_tokens=1_000)

        assert cost_of(visible, _FLASH, table, _BEFORE_THE_RISE) == pytest.approx(
            cost_of(thought, _FLASH, table, _BEFORE_THE_RISE)
        )
        assert TokenUsage(output_tokens=40, thinking_tokens=60).billable_output == 100

    def MQC_CMN_UNI_11187_cached_input_is_discounted_and_never_double_counted(
        self, table: PriceTable
    ) -> None:
        """Cached input is part of the input, not an addition to it.

        **The boundary case is the whole cache.** A request served entirely from
        cache costs the cached rate on every token, and the uncached remainder is
        zero rather than negative: an adapter reporting a cache count larger than
        its input count would otherwise produce a credit.

        Args:
            table (PriceTable): The shipped table.

        Returns:
            None
        """
        rates = table.price_for(_FLASH, _BEFORE_THE_RISE)
        assert rates is not None

        whole = TokenUsage(input_tokens=1_000, cached_input_tokens=1_000)
        assert cost_of(whole, _FLASH, table, _BEFORE_THE_RISE) == pytest.approx(
            1_000 * rates.cached_input_per_million / 1_000_000
        )
        # NEVER A CREDIT, even where a provider reports more cache than input.
        impossible = TokenUsage(input_tokens=10, cached_input_tokens=1_000)
        priced = cost_of(impossible, _FLASH, table, _BEFORE_THE_RISE)
        assert priced is not None and priced > 0


class TestMQCCostReport:
    """What each case cost, which is the question a corpus owner asks."""

    def MQC_CMN_UNI_11188_a_judged_case_reports_its_judge_apart_from_its_candidate(
        self, table: PriceTable
    ) -> None:
        """A judged case bills on two prompts, and one number hides which.

        **The judge's input is the larger half for this corpus**, because it
        carries the rubric, every criterion and anchor, and the candidate's
        response as well. Attributing both to one figure would leave a reader
        unable to tell an expensive model from an expensive rubric.

        Args:
            table (PriceTable): The shipped table.

        Returns:
            None
        """
        observations = [
            Observation(
                case_id="MQC_TASK_cod::MQC_RULE_cod", layer="EVAL", outcome="pass",
                mode="live", priority=2, family="code_comprehension",
                resolved_model=_FLASH, output_tokens=400,
                tokens=CaseUsage(
                    candidate=TokenUsage(
                        input_tokens=154, output_tokens=400, thinking_tokens=800
                    ),
                    judge=TokenUsage(input_tokens=890, output_tokens=200),
                ),
            )
        ]

        report = cost_report(observations, table, _BEFORE_THE_RISE)

        assert len(report.lines) == 1
        line = report.lines[0]
        assert line.candidate.input_tokens == 154
        assert line.judge.input_tokens == 890
        assert line.judge.input_tokens > line.candidate.input_tokens
        assert report.by_family() == {"code_comprehension": pytest.approx(line.cost)}

    def MQC_CMN_UNI_11189_a_replayed_observation_contributes_nothing(
        self, table: PriceTable
    ) -> None:
        """A replayed response was paid for when it was recorded.

        Counting it again would make a replay run report a bill, and replay is
        what every gate uses precisely because it spends nothing. **This is the
        case that keeps a pull request reporting zero**, which is the property
        the whole replay design rests on.

        Args:
            table (PriceTable): The shipped table.

        Returns:
            None
        """
        replayed = [
            Observation(
                case_id="MQC_TASK_sec::MQC_RULE_sec", layer="SEC", outcome="pass",
                mode="replay", priority=1, resolved_model=_FLASH,
                output_tokens=9_999,
                tokens=CaseUsage(
                    candidate=TokenUsage(input_tokens=9_999, output_tokens=9_999)
                ),
            )
        ]

        report = cost_report(replayed, table, _BEFORE_THE_RISE)

        assert not report.lines
        assert report.total == 0.0
