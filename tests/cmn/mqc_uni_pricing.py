# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for what a run cost.

Covers `MQC_CMN_UNI_112232` through `112238`, inventoried in
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
from typing import Final

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

# A NAME NO PROVIDER WILL EVER SERVE, so pricing a real model cannot
# invalidate the case that asserts what an unpriced one costs. It did
# once: `claude-opus-5-5` sat here until a credential was funded on
# 2026-10-01 and it was priced within the hour.
_ABSENT_MODEL: Final[str] = "no-such-model-is-priced-here"

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

    def MQC_CMN_UNI_112232_a_price_window_that_has_closed_is_reported(
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

    def MQC_CMN_UNI_112233_the_published_increase_is_priced_from_its_own_date(
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

    def MQC_CMN_UNI_112234_an_unpriced_model_yields_no_figure_rather_than_zero(
        self, table: PriceTable
    ) -> None:
        """Zero is the one wrong answer that looks like a right one.

        A run against an unpriced model has not been measured, and reporting
        nothing spent would read as a run that was free.

        **The subject is a synthetic name, and was a real model until
        2026-10-01.** This case named `claude-opus-5-5`, which was absent from
        the table because no credential was provisioned for it. One was funded,
        the model was priced the same day, and the case failed: it had been
        asserting a property of the table through an example, and the example
        moved.

        **Every model the shipped roster names is now priced**, so no real name
        can serve here. A synthetic one states the property directly, which is
        what the case was always about.

        **The real hazard is guarded elsewhere and deliberately not here.**
        `MQC_EXE_UNI_113702` refuses a budgeted run whose model has no price, so
        funding a credential without pricing its model stops the run rather than
        under-reporting it. A precondition asserting that every roster model is
        priced would be the wrong rule: an engine with no credential runs replay
        and bills nothing, and pricing its model would state a figure nobody can
        spend against.

        Args:
            table (PriceTable): The shipped table.

        Returns:
            None
        """
        usage = TokenUsage(input_tokens=1_000, output_tokens=1_000)

        assert cost_of(usage, _ABSENT_MODEL, table, _BEFORE_THE_RISE) is None
        assert cost_of(usage, _FLASH, table, _BEFORE_THE_RISE) is not None

        # AND IT IS ABSENT BECAUSE NOTHING PRICES IT, not because the lookup
        # rejects the shape of the name.
        assert _ABSENT_MODEL not in table.tiers


    def MQC_CMN_UNI_112334_a_dated_model_snapshot_prices_as_its_base(
        self, table: PriceTable
    ) -> None:
        """A provider pins a date onto the name; the bill is the same bill.

        **A boundary, and the boundary is the suffix.** openai answers a
        request for ``gpt-4.1`` with ``gpt-4.1-2025-04-14``, and spend is
        priced against what was served rather than what was asked for. The
        table keys the base, so the served name missed and the model read as
        unpriced.

        **An unpriced model closes the ceiling** (section 12.4), so every live
        openai run carrying ``--max-spend`` stopped before dispatching
        anything and reported ``QC_HARNESS_BUDGET_EXHAUSTED`` against a budget
        it had not touched. Three engines re-recorded a changed task on
        2026-10-06 and the fourth silently did not.

        Design: ``cmn_verdict_and_cli.md`` section 12.5.

        Args:
            table (PriceTable): The shipped table.

        Returns:
            None
        """
        served = "gpt-4.1-2025-04-14"
        snapshot = table.price_for(served, _BEFORE_THE_RISE)
        assert snapshot is not None, (
            f"{served} is unpriced, so a ceiling against it cannot be honoured "
            f"and every live run naming it stops before spending anything"
        )
        assert snapshot == table.price_for("gpt-4.1", _BEFORE_THE_RISE), (
            "the snapshot prices at different rates from the base it names, so "
            "two names for one model would report two bills"
        )

        # ONLY A DATE IS STRIPPED. A sibling model sharing the prefix is a
        # different model, and pricing it as this one would invent a figure,
        # which is the one thing an absent price exists to prevent.
        for sibling in ("gpt-4.1-mini", "gpt-4.1-mini-2025-01-01"):
            assert table.price_for(sibling, _BEFORE_THE_RISE) is None, (
                f"{sibling} priced as gpt-4.1, so a prefix is being read as a "
                f"family and a cheaper model now reports the dearer bill"
            )

        # AND THE CEILING STILL FAILS CLOSED for a model the table never had,
        # so this narrows which models are unpriced rather than weakening what
        # being unpriced means.
        assert table.price_for(_ABSENT_MODEL, _BEFORE_THE_RISE) is None, (
            "an unknown model became priced, so the guarantee section 12.4 "
            "rests on is gone"
        )
        assert table.price_for(f"{_ABSENT_MODEL}-2026-01-01", _BEFORE_THE_RISE) is None, (
            "an unknown model with a date became priced, so the fallback "
            "reaches past the table instead of into it"
        )


class TestMQCCostArithmetic:
    """What the four token categories cost, and which rate each takes."""

    def MQC_CMN_UNI_112235_thinking_is_billed_at_the_output_rate(
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

    def MQC_CMN_UNI_112236_cached_input_is_discounted_and_never_double_counted(
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

    def MQC_CMN_UNI_112237_a_judged_case_reports_its_judge_apart_from_its_candidate(
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
                mode="live", priority=2, families=("code_comprehension",),
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

    def MQC_CMN_UNI_112238_a_replayed_observation_contributes_nothing(
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

    def MQC_CMN_UNI_112242_a_shared_case_counts_toward_every_family_it_addresses(
        self,
        table: PriceTable,
    ) -> None:
        """Per-family totals overlap, because the question they answer does.

        **The totals do not sum to the run total and that is correct.** The
        figure answers which family is expensive, which is the decision a
        corpus owner makes: dropping either family still saves what a shared
        case costs to run. Dividing the bill would need an attribution rule for
        a shared case that nothing could justify.

        A secondary family counts the same as a primary one here. Primacy says
        what a case is about, not who pays for it.

        Design: ``test_taxonomy.md`` section 11.7.3.

        Args:
            table (PriceTable): The shipped table.

        Returns:
            None
        """
        shared = [
            Observation(
                case_id="MQC_TASK_cod::MQC_RULE_cod", layer="EVAL", outcome="pass",
                mode="live", priority=2,
                families=("code_comprehension", "requirement_match"),
                resolved_model=_FLASH, output_tokens=400,
                tokens=CaseUsage(
                    candidate=TokenUsage(input_tokens=154, output_tokens=400)
                ),
            )
        ]

        report = cost_report(shared, table, _BEFORE_THE_RISE)
        totals = report.by_family()

        assert sorted(totals) == ["code_comprehension", "requirement_match"]
        assert totals["code_comprehension"] == totals["requirement_match"], (
            "a shared case was split between its families, which answers how "
            "the bill divides rather than what a family costs to run"
        )

        # THE OVERLAP IS THE POINT. A reader adding the per-family figures gets
        # more than the run total, and the design says so rather than leaving
        # it to be discovered.
        assert report.total == pytest.approx(totals["code_comprehension"])
        assert sum(totals.values()) == pytest.approx(2 * report.total)
