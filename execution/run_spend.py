# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""What a run has spent, against its ceiling, by role.

Created: 2026-11-11
Last updated: 2026-11-11

This file contains ``RunSpend``, the spending half of a run's
``DispatchSession``: the ceiling, what the run has been billed and how much
of it the judge spent, the candidate's tokens, the price table and the models
it could not price. ``ceiling_reached`` is asked before each request of either
role, ``record_spend`` takes a candidate response, ``charge_judgement`` a live
judgement, and ``spend_summary`` renders the split for the run's artifacts.

**Extracted from ``execution/dispatch.py`` on 2026-11-11**, when the judge's
share would have taken that module past its 900-line runway
(``code-style.md`` section 5.1). Spending is its own subject; ``DispatchSession``
inherits it, so every field and method is reached on the session as before.

Specified by ``docs/design/tier2_execution.md`` sections 7.7.3 and 8, and
``docs/design/cmn_verdict_and_cli.md`` section 5.6.4.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from cmn.pricing import PriceTable, cost_of, spend_fields
from cmn.tokens import TokenUsage


@dataclass
class RunSpend:
    """A run's spending state, which every request of either role reads and charges.

    Attributes:
        max_spend (float): The run's ceiling in the price table's currency.
            **Zero means no ceiling**, which is the default and what every
            replay run uses: replay spends nothing, so a ceiling there would
            only be a number to get wrong.
        spent (float): What the run has been billed so far, both roles,
            accumulated from each measured response rather than estimated.
        judge_spent (float): The judge's share of ``spent``, so the
            candidate's is the difference.
        usage (TokenUsage): Every token the candidate has consumed, kept so a
            run can report its own cost without re-reading the corpus.
        prices (Optional[PriceTable]): The rates, or ``None`` for a run that
            prices nothing. **A replay run leaves this unset**, because a
            replayed response was paid for when it was recorded.
        priced_on (Optional[date]): The date rates are read against, injected
            for the reason the verdict injects its date: a cost that changes
            between two readings of one corpus is not a measurement.
        unpriced (set): Models this run met that the table does not price.
            **A ceiling cannot be honoured against these**, so their presence
            stops a budgeted run rather than being noted: a cap that cannot be
            enforced must not look enforced.
    """

    max_spend: float = 0.0
    spent: float = 0.0
    judge_spent: float = 0.0
    usage: TokenUsage = field(default_factory=TokenUsage)
    prices: Optional[PriceTable] = None
    priced_on: Optional[date] = None
    unpriced: set[str] = field(default_factory=set)

    def ceiling_reached(self) -> bool:
        """Report whether the run has already spent its ceiling.

        **Asked before each request, and it overshoots by at most one.** The
        alternative is to compare the ceiling against an estimate of the request
        about to be sent, which means inventing token counts for a prompt the
        provider has not answered: an estimate that is too low defeats the
        ceiling while appearing to enforce it. Stopping one request late is
        cheaper than a guess that can be wrong in the unsafe direction, and at
        the measured rates one request is a small fraction of a cent.

        Returns:
            bool: True where a ceiling is set and spending has reached it.
            **False when no ceiling is set**, so an unconfigured run behaves
            exactly as it did before this existed, and every replay run is
            unaffected because replay spends nothing.
        """
        if self.max_spend <= 0:
            return False
        # AN UNPRICED MODEL STOPS A BUDGETED RUN. Its responses cost `None`, so
        # `spent` never grows and the ceiling would never engage: the run would
        # spend without limit while reporting a cap. `claude-opus-5-5` is exactly
        # that case, deliberately unpriced and with thinking it cannot disable.
        if self.unpriced:
            return True
        return self.spent >= self.max_spend

    def record_spend(self, usage: TokenUsage, model: str) -> None:
        """Add one candidate response's tokens, and its cost where the model is priced.

        **The session prices this, not the caller.** The dispatch path should not
        have to hold a price table to report a measurement, and keeping the
        lookup here means the ceiling and the total are computed from one place.

        Args:
            usage (TokenUsage): What the response consumed.
            model (str): The model the provider reported serving, which is what
                is priced. **Resolved, never requested**: an alias that floated
                would otherwise be billed at the price of a model nobody served.

        Returns:
            None: **An unpriced model still contributes its tokens.** A run
            against something the table does not know reports usage it cannot
            price, rather than reporting nothing and reading as free.
        """
        self.usage = self.usage + usage
        self.charge(usage, model)

    def charge(self, usage: TokenUsage, model: str) -> None:
        """Add one response's cost to ``spent``, without counting its tokens in ``usage``.

        The pricing half of :meth:`record_spend` and of :meth:`charge_judgement`,
        so ``spent`` covers both roles and ``usage`` stays the candidate's.
        Design: ``tier2_execution.md`` section 7.7.3.

        Args:
            usage (TokenUsage): What the response consumed.
            model (str): The model the provider reported serving.

        Returns:
            None: Nothing without a price table; an unpriced model is added to
            ``unpriced``, so a budgeted run stops and names it.
        """
        if self.prices is None or self.priced_on is None:
            return
        cost = cost_of(usage, model, self.prices, self.priced_on)
        if cost is None:
            if model:
                self.unpriced.add(model)
            return
        self.spent += cost

    def charge_judgement(self, usage: TokenUsage, model: str) -> None:
        """Add one live judgement's cost to ``spent`` and to ``judge_spent``.

        Design: ``tier2_execution.md`` section 7.7.3.

        Args:
            usage (TokenUsage): What the judgement consumed.
            model (str): The model the judge reply reports serving.

        Returns:
            None: An unpriced judge model adds nothing to either total and is
            added to ``unpriced``, as :meth:`charge` does.
        """
        before = self.spent
        self.charge(usage, model)
        self.judge_spent += self.spent - before

    def spend_summary(self) -> dict[str, str]:
        """Return the run's spend by role, as ``cmn.pricing.spend_fields`` renders it.

        Design: ``tier2_execution.md`` section 7.7.3.

        Returns:
            dict[str, str]: The candidate, judge and total spend, the ceiling
            and any unpriced model; the candidate and judge figures sum to
            ``spent``.
        """
        return spend_fields(
            candidate=self.spent - self.judge_spent,
            judge=self.judge_spent,
            max_spend=self.max_spend,
            priced=self.prices is not None and self.priced_on is not None,
            unpriced=set(self.unpriced),
        )
