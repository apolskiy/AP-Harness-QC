# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""What a quarantine entry is, and when it stops holding.

Specified in ``docs/design/cmn_verdict_and_cli.md`` section 4.6.

**Extracted 2026-10-02**, when reworking the model took ``cmn/verdict.py`` past
the thousand-line ceiling. The entry and the window it is measured against are
one subject; ``V5`` stays with the other verdict rules, because the rule
registry is what makes a rule a rule.
"""

from dataclasses import dataclass
from datetime import date
from typing import Final, Optional

# HOW LONG A QUARANTINE ENTRY STAYS VALID when the model has not changed.
# Three weeks: the scheduled cadence is weekly, so this is three runs of
# grace and still two if one is missed, and a multiple of seven keeps
# expiry from drifting off the run day. Design section 4.6.2.
QUARANTINE_WINDOW_DAYS: Final[int] = 21


@dataclass(frozen=True)
class QuarantineEntry:
    """One case excluded from the pass-rate denominator, with its provenance.

    **Never deleted from the suite.** A quarantined case still runs and is
    listed in the report; it only leaves the denominator.

    Attributes:
        case_id (str): Which case.
        reason (str): Why it is quarantined.
        quarantined_on (Optional[date]): When the failure was observed and
            accepted. Absent means the entry is unconfirmed.
        observed_model (str): The model it was observed against. Absent means
            the entry is unconfirmed.
        ticket (str): An optional tracker reference or URL. **Nothing reads
            it**, by design: it carries the human context an entry needs,
            pending a tracking system (design section 4.6.7).
    """

    case_id: str
    reason: str
    quarantined_on: Optional[date] = None
    observed_model: str = ""
    ticket: str = ""

    @property
    def confirmed(self) -> bool:
        """Report whether this entry carries enough to evaluate its expiry.

        Returns:
            bool: True when both the date and the observed model are present.
        """
        return self.quarantined_on is not None and bool(self.observed_model)

    def expired(self, as_of: date, resolved_model: str, window_days: int) -> bool:
        """Report whether this entry has lapsed.

        Expired when the resolved model differs from the one it was observed
        against, or when ``as_of`` reaches ``window_days`` past
        ``quarantined_on``. **The window boundary is inclusive**, so a 21-day
        window makes day 21 the first expired day.

        An unconfirmed entry never expires here: there is nothing to measure
        against, and the condition is reported separately rather than resolved
        by guessing. An empty ``resolved_model`` leaves the model trigger
        unevaluated and the window alone applies.

        Design: ``cmn_verdict_and_cli.md`` section 4.6.2.

        Args:
            as_of (date): The injected evaluation date.
            resolved_model (str): The model this run reported, empty when the
                run named none or named several.
            window_days (int): How long an entry stays valid.

        Returns:
            bool: True when the entry has lapsed.
        """
        if self.quarantined_on is None or not self.observed_model:
            return False
        if resolved_model and resolved_model != self.observed_model:
            return True
        return (as_of - self.quarantined_on).days >= window_days
