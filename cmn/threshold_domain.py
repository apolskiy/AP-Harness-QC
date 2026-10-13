# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The domain every threshold lives in, and the refusal when one leaves it.

Designed in ``docs/design/cmn_verdict_and_cli.md`` section 8.1, which records
what was measured before this existed: a ``pass_floor`` of ``0`` or ``-1``
turned every run green at exit 0 with no breach recorded, and a string broke
the run part-way through evaluating it.

**It lives beside the verdict rather than inside it** because the domain is a
statement about configuration that no rule reads, and because ``verdict.py``
was at 992 of its thousand lines (``code-style.md`` section 5.1).
"""

import dataclasses
from typing import Any, Final

# A SHARE OF A POPULATION, so the unit interval and not zero. Zero is refused
# for the ceilings as well as the floors: a ceiling of zero leaves no band, and
# the rule it reaches for is V1, which decides per observation and names the
# case rather than reporting a percentage. Design section 8.1.
RATE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "pass_floor",
        "skip_ceiling",
        "priority_skip_ceiling",
        "inconsistency_ceiling",
        "p0_share_ceiling",
        "p1_share_ceiling",
        "combined_share_ceiling",
    }
)

# A POPULATION OR A SPAN OF DAYS, so whole and at least one. A minimum of zero
# would mean the distribution check never abstains, which is the opposite of
# what the field is for.
COUNT_FIELDS: Final[frozenset[str]] = frozenset(
    {"distribution_minimum", "quarantine_window_days"}
)


def _is_number(value: Any) -> bool:
    """Report whether a value is a number a threshold may be.

    ``bool`` is excluded although it subclasses ``int``: ``pass_floor=True``
    would otherwise be accepted as a floor of 1.0, which is a real standard and
    certainly not what was meant.

    Args:
        value (Any): The supplied value.

    Returns:
        bool: True when it is an int or a float and not a bool.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_rate(name: str, value: Any) -> None:
    """Refuse a rate outside ``0 < value <= 1``.

    Args:
        name (str): The field, named in the message so the message identifies
            the edit rather than the comparison that would have tripped later.
        value (Any): The supplied value.

    Returns:
        None

    Raises:
        ValueError: When the value is not a number, or lies outside the unit
            interval, or is zero.
    """
    if not _is_number(value):
        raise ValueError(
            f"{name} must be a number between 0 and 1, not {value!r}"
        )
    if not 0 < value <= 1:
        raise ValueError(
            f"{name} must be above 0 and at most 1, not {value!r}. A rate is a "
            f"share of a population; outside that range it decides every run "
            f"the same way and reports no breach"
        )


def check_count(name: str, value: Any) -> None:
    """Refuse a population count below one, or one that is not whole.

    Args:
        name (str): The field, named in the message.
        value (Any): The supplied value.

    Returns:
        None

    Raises:
        ValueError: When the value is not a whole number, or is below one.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(
            f"{name} must be a whole number of at least 1, not {value!r}"
        )
    if value < 1:
        raise ValueError(
            f"{name} must be at least 1, not {value!r}. A count of zero or "
            f"less names no population, so the check it governs never abstains"
        )


def check_domain(thresholds: Any) -> None:
    """Refuse any field of a thresholds record that leaves its domain.

    **Every field is checked, including the two retired ones.**
    ``skip_ceiling`` and ``priority_skip_ceiling`` are read by nothing since
    2026-10-08, but both are still emitted into ``effective_thresholds`` as
    part of the standard a run claims to have applied, and whoever reads that
    artifact cannot tell which fields were live. Their defaults are in range,
    so no stored configuration is broken by checking them.

    Args:
        thresholds (Any): A ``Thresholds`` instance, read through
            ``dataclasses.fields`` so this module does not import the verdict.

    Returns:
        None

    Raises:
        ValueError: On the first field outside its domain, naming the field
            and the value it was given, or on a field registered in neither
            set.
    """
    for entry in dataclasses.fields(thresholds):
        value = getattr(thresholds, entry.name)
        if entry.name in RATE_FIELDS:
            check_rate(entry.name, value)
        elif entry.name in COUNT_FIELDS:
            check_count(entry.name, value)
        else:
            # A FIELD IN NEITHER SET IS THE DEFECT, not an exemption. Skipping
            # it would make a new threshold unchecked by default, which is how
            # this module came to be needed; refusing makes adding one a
            # decision somebody has to write down.
            raise ValueError(
                f"{entry.name} is a threshold in neither RATE_FIELDS nor "
                f"COUNT_FIELDS, so its domain was never declared"
            )
