# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Passes with a warning, a case that passed because the answer corrected itself.

Created: 2026-11-06
Last updated: 2026-11-06

This file contains ``mark_passw``, which marks a passing call-phase report
``passw`` where the case recorded an observation with that outcome, and
``is_passw`` and ``passw_count``, which read the marks.

Both repositories' ``conftest.py`` call these from the report and summary
hooks, so the result block counts a pass with a warning apart from a clean pass
and JUnit carries the mark and the warning codes for a filing tool to read. The exit status is not
touched: a warning is not a failure.

Design: ``docs/design/harness_test_taxonomy.md`` section 5.1.2.
"""

import logging
from typing import Any, Final

from cmn.emission import recorded_observations

logger = logging.getLogger(__name__)

_OUTCOME: Final[str] = "passw"
_PROPERTY: Final[tuple[str, str]] = ("mqc_outcome", _OUTCOME)
_WARNING_CODE: Final[str] = "mqc_warning_code"


def mark_passw(report: Any, item: Any = None) -> bool:
    """Mark a passing call-phase report where the case recorded a passw observation.

    Args:
        report (Any): The phase report pytest produced.
        item (Any): The test item, whose properties the teardown report copies
            and JUnit writes. Without it only the call report is marked.

    Returns:
        bool: True where the report was marked: the call phase passed and at
        least one observation the case recorded has the outcome ``passw``. The
        report and the item gain the user property ``mqc_outcome`` ``passw`` and
        one ``mqc_warning_code`` per distinct code those observations carry.
    """
    if getattr(report, "when", "") != "call" or not getattr(report, "passed", False):
        return False
    warned = [
        observation for observation, _ in recorded_observations()
        if observation.outcome == _OUTCOME
    ]
    if not warned:
        return False
    codes = sorted({str(observation.taxonomy_code) for observation in warned
                    if observation.taxonomy_code})
    marks = [_PROPERTY] + [(_WARNING_CODE, code) for code in codes]
    report.user_properties.extend(marks)
    # JUNIT WRITES THE TEARDOWN REPORT'S PROPERTIES, which are copied from the
    # item, so a mark on the call report alone never reaches the XML.
    if item is not None:
        item.user_properties.extend(marks)
    logger.info("%s passed with a warning: %s", getattr(report, "nodeid", "?"),
                ", ".join(codes) or "no code")
    return True


def is_passw(report: Any) -> bool:
    """Report whether a phase report was marked passw.

    Args:
        report (Any): A phase report from the reporter's statistics.

    Returns:
        bool: True where :func:`mark_passw` marked it.
    """
    return _PROPERTY in (getattr(report, "user_properties", None) or [])


def passw_count(stats: dict[str, list[Any]]) -> int:
    """Count the passing reports marked passw.

    Args:
        stats (dict): The terminal reporter's statistics.

    Returns:
        int: How many of the ``passed`` reports carry the mark, which the
        result block takes out of ``passed`` and prints as ``passw``.
    """
    return sum(1 for report in stats.get("passed", []) if is_passw(report))
