# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""What a run cost, computed from tokens and a dated price table.

**A pure function of usage, prices and an injected date**, for the same reason
the verdict is: no clock, no network, no filesystem beyond the one load. A cost
that varies between two readings of the same corpus is not a measurement.

**Absent is not free.** An unpriced model yields ``None`` rather than zero, so a
run against something this file does not know about reports as unmeasured. Zero
would read as a run that cost nothing, which is the one wrong answer that looks
like a right one.

**The unit is a token count, never a request count.** Requests are the free
tier's unit and tokens are the paid tier's, and confusing them is how an estimate
lands an order out: 297 requests carrying 64,000 input tokens costs what the
tokens cost.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Final, Optional

from cmn.config import coerce_date, load_yaml_config
from cmn.tokens import CaseUsage, TokenUsage

logger = logging.getLogger(__name__)

_PER_MILLION: Final[int] = 1_000_000


@dataclass(frozen=True)
class ModelPrice:
    """One model's rates for one window of time.

    Attributes:
        model (str): The model these rates apply to.
        input_per_million (float): Rate for uncached input.
        output_per_million (float): Rate for output, and therefore for thinking.
        cached_input_per_million (float): Rate for input served from cache.
        priced_on (date): When the figures were read from the provider.
        effective_until (Optional[date]): The last day these rates hold, where
            the provider published an end. ``None`` means open-ended.
    """

    model: str
    input_per_million: float
    output_per_million: float
    cached_input_per_million: float
    priced_on: date
    effective_until: Optional[date] = None


@dataclass(frozen=True)
class PriceTable:
    """Every model's rates, across every published window.

    Attributes:
        tiers (dict): Model name to its windows, earliest first.
        retired (frozenset): Models priced for historical corpora only.
    """

    tiers: dict[str, list[ModelPrice]] = field(default_factory=dict)
    retired: frozenset[str] = frozenset()

    def price_for(self, model: str, as_of: date) -> Optional[ModelPrice]:
        """Return the rates in force for a model on a date.

        Args:
            model (str): The model as the provider reported it. **A trailing
                ISO date is stripped when the exact name is absent**, so a
                dated snapshot prices at its base's rates (section 12.5).
            as_of (date): The date to price against, injected rather than read
                from a clock so that two readings of one corpus agree.

        Returns:
            Optional[ModelPrice]: The applicable rates, or ``None`` where the
            model is unpriced or no window covers the date. **None rather than
            the nearest window**, because extrapolating across a published price
            change is inventing a figure.
        """
        windows = self.tiers.get(model) or self.tiers.get(_base_model(model))
        if not windows:
            return None
        for window in windows:
            if window.effective_until is None or as_of <= window.effective_until:
                return window
        return None


# A PROVIDER'S PINNED SNAPSHOT, which prices as the model it names. openai
# answers a request for `gpt-4.1` with `gpt-4.1-2025-04-14`, and spend is
# priced against what was served rather than what was asked for, so the table
# missed and the model read as unpriced. A ceiling against an unpriced model
# cannot be honoured (section 12.4), so every live openai run with
# `--max-spend` stopped before dispatching anything.
#
# ONLY AN ISO DATE IS STRIPPED. `gpt-4.1-mini` is a different model and must
# never price as `gpt-4.1`, so the suffix has to be a date and nothing else.
_SNAPSHOT_SUFFIX: Final[re.Pattern[str]] = re.compile(
    r"-(\d{4})-(\d{2})-(\d{2})$"
)


def _base_model(model: str) -> str:
    """Return the base a dated snapshot names, or the name unchanged.

    Args:
        model (str): The model as the provider reported it.

    Returns:
        str: The name with a trailing ``-YYYY-MM-DD`` removed, or the original
        when it carries none. **The caller still has to find the result in the
        table**, so an unknown base stays unpriced and the ceiling keeps
        failing closed.
    """
    stripped = _SNAPSHOT_SUFFIX.sub("", model)
    if stripped != model:
        logger.info(
            "pricing %s at the rates for %s, its base: the provider pinned a "
            "dated snapshot and the table carries the base",
            model, stripped,
        )
    return stripped


def load_price_table(path: Path) -> PriceTable:
    """Load the dated price table.

    Args:
        path (Path): The pricing file.

    Returns:
        PriceTable: Every model's windows. **An absent file yields an empty
        table**, which prices nothing and therefore reports nothing, rather than
        raising: a clone with no pricing file can still run replay.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when an entry carries no
            usable rates. A malformed price is worse than an absent one, because
            it produces a number.
    """
    loaded = load_yaml_config(path)
    tiers: dict[str, list[ModelPrice]] = {}
    retired: set[str] = set()

    for model, entry in (loaded.get("models") or {}).items():
        if not isinstance(entry, dict):
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: model {model!r} in {path} is not a mapping"
            )
        if entry.get("retired"):
            retired.add(str(model))
        windows: list[ModelPrice] = []
        for window in entry.get("tiers") or []:
            windows.append(_read_window(str(model), window, path))
        if not windows:
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: model {model!r} in {path} states no rates"
            )
        tiers[str(model)] = sorted(
            windows, key=lambda rates: rates.effective_until or date.max
        )
    return PriceTable(tiers=tiers, retired=frozenset(retired))


def _read_window(model: str, window: Any, path: Path) -> ModelPrice:
    """Build one price window, refusing an incomplete one.

    Args:
        model (str): Which model, for the failure message.
        window (Any): The parsed entry.
        path (Path): The file, for the failure message.

    Returns:
        ModelPrice: The rates.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when a rate or the date is
            missing. **Every field is required**: a defaulted rate of zero would
            silently discount whatever it priced.
    """
    if not isinstance(window, dict):
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: a price window for {model!r} in {path} "
            f"is not a mapping"
        )
    for required in ("input", "output", "cached_input", "priced_on"):
        if window.get(required) is None:
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: a price window for {model!r} in "
                f"{path} states no {required!r}"
            )
    return ModelPrice(
        model=model,
        input_per_million=float(window["input"]),
        output_per_million=float(window["output"]),
        cached_input_per_million=float(window["cached_input"]),
        priced_on=coerce_date(window["priced_on"], path),
        effective_until=(
            coerce_date(window["effective_until"], path)
            if window.get("effective_until") is not None
            else None
        ),
    )


def cost_of(usage: TokenUsage, model: str, table: PriceTable, as_of: date) -> Optional[float]:
    """Return what one usage cost, in the table's currency.

    Args:
        usage (TokenUsage): What was consumed.
        model (str): The model that consumed it, as the provider reported it.
        table (PriceTable): The rates.
        as_of (date): The date to price against.

    Returns:
        Optional[float]: The cost, or ``None`` where the model is unpriced.
        **None rather than zero**, so an unpriced run reads as unmeasured.
    """
    rates = table.price_for(model, as_of)
    if rates is None:
        return None
    uncached = max(usage.input_tokens - usage.cached_input_tokens, 0)
    return (
        uncached * rates.input_per_million
        + usage.cached_input_tokens * rates.cached_input_per_million
        + usage.billable_output * rates.output_per_million
    ) / _PER_MILLION


def stale_prices(table: PriceTable, as_of: date) -> list[str]:
    """Return every model whose applicable window has already closed.

    **A closed window is the failure this exists for.** The rates in force are
    the ones whose window covers the date, and where none does the table has
    been overtaken by a price change the provider published in advance. Pricing
    against the last known window would then report the older, smaller figure.

    Args:
        table (PriceTable): The rates.
        as_of (date): The date being priced against.

    Returns:
        list[str]: Model names with no window covering the date, sorted. Empty
        where every priced model is current.
    """
    return sorted(
        model
        for model in table.tiers
        if table.price_for(model, as_of) is None
    )

@dataclass(frozen=True)
class CostLine:
    """What one case cost, with the judge kept apart from the candidate.

    Attributes:
        case_id (str): Which case.
        families (tuple): Its evaluation families, empty where it has none.
            Many to many, per ``test_taxonomy.md`` section 11.7.
        observations (int): How many times it was observed, so a per-observation
            figure is derivable without re-reading the corpus.
        candidate (TokenUsage): What the model under test consumed.
        judge (TokenUsage): What the judge consumed. **Separate on purpose**: a
            judged case bills on two prompts, and one combined number hides
            which half is expensive. For this corpus the judge's input is the
            larger of the two, because it carries the rubric and the anchors as
            well as the response.
        cost (Optional[float]): The two priced together, or ``None`` where a
            model involved is unpriced.
    """

    case_id: str
    families: tuple[str, ...]
    observations: int
    candidate: TokenUsage
    judge: TokenUsage
    cost: Optional[float]


@dataclass(frozen=True)
class CostReport:
    """What a run cost, per case and in total.

    Attributes:
        lines (list): One entry per case, heaviest first, so the expensive cases
            are the ones a reader sees.
        total (float): Every priced case added up.
        unpriced (frozenset): Models a case ran against that the table does not
            know. **Named rather than counted**, because the remedy is to price
            that model and a number does not say which.
    """

    lines: list[CostLine] = field(default_factory=list)
    total: float = 0.0
    unpriced: frozenset[str] = frozenset()

    def by_family(self) -> dict[str, float]:
        """Return the priced total per family, overlapping where a case is shared.

        **The totals do not sum to the run total, and that is correct.** A case
        addressing two families is attributed in full to each, because the
        figure answers what a family costs to run rather than how the bill
        divides: dropping either family still saves what that case costs. A
        division would need an attribution rule for shared cases that nothing
        could justify. Design ``test_taxonomy.md`` section 11.7.3.

        Returns:
            dict[str, float]: Family to its cost, for every case carrying one.
            **A case with no family is omitted** rather than grouped under a
            placeholder: preconditions perform no task and have no family, and
            inventing one would put them in a denominator they do not belong in.
        """
        totals: dict[str, float] = {}
        for line in self.lines:
            if line.cost is None:
                continue
            for name in line.families:
                totals[name] = totals.get(name, 0.0) + line.cost
        return totals


def cost_report(
    observations: list[Any], table: PriceTable, as_of: date
) -> CostReport:
    """Return what each case cost and what the run cost.

    **A run total answers whether a weekly run is affordable; this answers which
    family is expensive.** The second is the decision a corpus owner makes, and it
    cannot be derived from the first.

    Args:
        observations (list[Any]): Every observation in the run, each carrying the
            token counts its dispatch recorded.
        table (PriceTable): The rates.
        as_of (date): The date to price against, injected rather than read from a
            clock so two readings of one corpus agree.

    Returns:
        CostReport: Per case, heaviest first, with the run total and every
        unpriced model named. **A replayed observation contributes nothing**,
        because a replayed response was paid for when it was recorded; counting it
        again would make a replay run look like it spent money.
    """
    gathered: dict[str, dict[str, Any]] = {}
    for entry in observations:
        if getattr(entry, "mode", "") != "live":
            continue
        held = gathered.setdefault(
            entry.case_id,
            {
                "families": list(getattr(entry, "families", ())),
                "model": getattr(entry, "resolved_model", ""),
                "observations": 0,
                "tokens": CaseUsage(),
            },
        )
        held["observations"] += 1
        usage = getattr(entry, "tokens", CaseUsage())
        held["tokens"] = CaseUsage(
            candidate=held["tokens"].candidate + usage.candidate,
            judge=held["tokens"].judge + usage.judge,
        )

    lines: list[CostLine] = []
    total = 0.0
    unpriced: set[str] = set()
    for case, held in gathered.items():
        tokens: CaseUsage = held["tokens"]
        priced = cost_of(tokens.billable, held["model"], table, as_of)
        if priced is None and held["model"]:
            unpriced.add(held["model"])
        if priced is not None:
            total += priced
        lines.append(
            CostLine(
                case_id=case,
                families=tuple(held["families"]),
                observations=held["observations"],
                candidate=tokens.candidate,
                judge=tokens.judge,
                cost=priced,
            )
        )

    lines.sort(key=lambda line: (line.cost is None, -(line.cost or 0.0), line.case_id))
    return CostReport(lines=lines, total=total, unpriced=frozenset(unpriced))
