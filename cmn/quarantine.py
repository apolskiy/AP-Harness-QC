# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""What a quarantine entry is, and when it stops holding.

Specified in ``docs/design/cmn_verdict_and_cli.md`` section 4.6.

**Extracted 2026-10-02**, when reworking the model took ``cmn/verdict.py`` past
the thousand-line ceiling. The entry and the window it is measured against are
one subject; ``V5`` stays with the other verdict rules, because the rule
registry is what makes a rule a rule.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
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


# WHAT RECONCILING DECIDED ABOUT ONE ENTRY. Returned alongside the entries
# because a case nobody ran looks identical to a case that passed if the only
# output is the survivors, and the difference is "fixed" against "not asked".
# Design section 4.6.10.
DROPPED: Final[str] = "dropped"
STAMPED: Final[str] = "stamped"
UNDECIDED: Final[str] = "undecided"


def reconcile(
    entries: Sequence[QuarantineEntry],
    outcomes: Mapping[str, Sequence[bool]],
    as_of: date,
    resolved_model: str,
) -> tuple[list[QuarantineEntry], dict[str, str]]:
    """Decide what each quarantine entry becomes after re-observing its case.

    An entry whose case passed every observation is dropped; one whose case
    failed any observation is re-stamped with ``as_of`` and ``resolved_model``;
    one whose case produced no observations is kept unchanged and reported as
    undecided.

    **Any failure re-stamps rather than a majority**, because the within-case
    rule is binary: a case whose observations disagree has a finding, and a
    majority would discard the disagreement the repeats exist to produce.

    Pure, and therefore testable without running a case or writing a file. The
    running and the writing belong to the case repository, which owns the cases
    and the entries.

    Design: ``cmn_verdict_and_cli.md`` section 4.6.10.

    Args:
        entries (Sequence[QuarantineEntry]): The entries as they stand.
        outcomes (Mapping[str, Sequence[bool]]): Per case identifier, whether
            each observation passed. A case absent from this mapping, or
            present with no observations, was not measured.
        as_of (date): The date to stamp a surviving entry with.
        resolved_model (str): The model the re-observation ran against.

    Returns:
        tuple: The entries that remain, in their input order, and one action
        per entry keyed by case identifier, each
        :data:`DROPPED`, :data:`STAMPED` or :data:`UNDECIDED`.
    """
    remaining: list[QuarantineEntry] = []
    actions: dict[str, str] = {}

    for entry in entries:
        observed = list(outcomes.get(entry.case_id) or ())
        if not observed:
            actions[entry.case_id] = UNDECIDED
            remaining.append(entry)
            continue
        if all(observed):
            actions[entry.case_id] = DROPPED
            continue
        actions[entry.case_id] = STAMPED
        remaining.append(
            replace(entry, quarantined_on=as_of, observed_model=resolved_model)
        )

    return remaining, actions
