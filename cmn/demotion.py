# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Demotion ordering, and why a demotion is reported rather than absorbed.

Specified by ``docs/design/harness_test_taxonomy.md`` sections 4.1.4 and 4.1.4.1.

**Qualifying conditions set a ceiling, not an assignment.** A case may sit below
the most severe condition it matches, and that is legitimate. What is not
legitimate is resolving a breached distribution ceiling by quietly making the
number smaller.

**The ceilings exist so an inflated P0 population cannot turn the must-pass gate
into a hair-trigger.** Demotion is how a breach gets resolved, and an unreported
demotion resolves it by shrinking the count rather than by improving the suite.
The distribution check therefore reports the demoted count alongside the shares.

**Match count is claim strength.** A case satisfying three P0 conditions has a
materially better claim than one qualifying on a single condition, which makes
the ordering mechanical rather than an argument.

**Security is never demoted.** Security coverage does not compete with
functional coverage for a budget, so it cannot be what gives way when one binds.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from cmn.layers import layer_properties
from cmn.registries import priority_condition_level

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DemotionCandidate:
    """One case considered for demotion when a ceiling binds.

    Attributes:
        case_id (str): Which case.
        layer (str): Which layer, from which the security exemption is read.
        assigned_priority (int): The level it currently carries.
        matched_conditions (list): Every condition identifier it matched.
    """

    case_id: str
    layer: str
    assigned_priority: int
    matched_conditions: list[str]

    @property
    def ceiling(self) -> Optional[int]:
        """Return the most severe level any matched condition permits.

        Returns:
            Optional[int]: The lowest numeric level among matched conditions,
            or ``None`` when nothing matched. **This is a ceiling**: the case
            may sit at or below it, never above.
        """
        levels = [
            priority_condition_level(condition)
            for condition in self.matched_conditions
            if priority_condition_level(condition) is not None
        ]
        return min(levels) if levels else None

    @property
    def claim_strength(self) -> int:
        """Return how many conditions support the assigned level or better.

        **Counted at or above the assigned level**, which is the strength of the
        claim to being *at least* this priority. Counting every match regardless
        of level would let three P4 conditions inflate a P1's apparent claim.

        Returns:
            int: The count of qualifying conditions.
        """
        # The comparison is written against an explicit None rather than a
        # falsy default, because P0 is level zero and `level or 99` discards
        # every P0 condition silently. That is the one value this count most
        # needs to see, so the shorter form is wrong in exactly the case that
        # matters.
        levels = [
            priority_condition_level(condition)
            for condition in self.matched_conditions
        ]
        return len([
            level for level in levels
            if level is not None and level <= self.assigned_priority
        ])

    @property
    def demotable(self) -> bool:
        """Report whether this case may be demoted at all.

        Returns:
            bool: False for a case in a distribution-exempt layer. Read from
            the layer registration rather than by naming the layer, so a later
            exempt layer inherits the protection without a change here.
        """
        return not layer_properties(self.layer).distribution_exempt

    @property
    def demoted(self) -> bool:
        """Report whether this case already sits below its ceiling.

        **Nothing extra has to be stored.** A priority below the most severe
        matched condition is exactly what demotion produces, so the signal is
        derivable from the record the case already carries.

        Returns:
            bool: True when the assigned level is less severe than the ceiling.
        """
        ceiling = self.ceiling
        return ceiling is not None and self.assigned_priority > ceiling


def demotion_order(candidates: list[DemotionCandidate]) -> list[DemotionCandidate]:
    """Return the candidates in the order a binding ceiling would demote them.

    Args:
        candidates (list): Every case eligible for consideration.

    Returns:
        list[DemotionCandidate]: **Weakest claim first.** A single-condition
        match is demoted before a multiple-condition match, because the second
        has a materially stronger claim to the level it holds. Ties break on the
        case identifier so the order is reproducible rather than dependent on
        input ordering. **Security cases are excluded entirely**, never merely
        ordered last: appearing at the end of a list is one budget change away
        from being demoted.
    """
    eligible = [candidate for candidate in candidates if candidate.demotable]
    excluded = len(candidates) - len(eligible)
    if excluded:
        logger.info("%d security cases excluded from demotion ordering", excluded)
    return sorted(eligible, key=lambda entry: (entry.claim_strength, entry.case_id))


def count_demoted(candidates: list[DemotionCandidate]) -> int:
    """Return how many cases sit below the ceiling their conditions permit.

    **Reported alongside the distribution shares.** A suite that meets its
    ceilings only because eleven cases were demoted has not met them in the
    sense the ceilings were written for, and a clean percentage would say it
    had.

    Args:
        candidates (list): Every case in the distribution population.

    Returns:
        int: The demoted count.
    """
    return len([candidate for candidate in candidates if candidate.demoted])


def exceeds_ceiling(candidate: DemotionCandidate) -> bool:
    """Report whether a case claims a level no matched condition permits.

    Args:
        candidate (DemotionCandidate): The case to check.

    Returns:
        bool: True when the assigned level is more severe than the ceiling, or
        when nothing matched at all. **A priority without a named condition is
        not assignable** (G6), so an unmatched case is a breach rather than an
        unconstrained one.
    """
    ceiling = candidate.ceiling
    if ceiling is None:
        return True
    return candidate.assigned_priority < ceiling
