# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Broken cases, a case that crashed rather than failed, and the exit 3 it forces.

Created: 2026-10-15
Last updated: 2026-10-21

This file contains ``mark_broken``, which marks a phase report broken when its
exception was not an assertion or a deliberate ``pytest.fail``, logging it under
``QC_HARNESS_UNANTICIPATED_EXCEPTION``; ``is_broken``, ``broken_count`` and
``broken_detail_lines``, which read and report the marks; and
``refuse_broken``, which makes the run exit 3 where any case broke.

Both repositories' ``conftest.py`` call these from the report, session-end and
summary hooks, so a crash is never counted as a model failure and the run says nothing
trustworthy was measured.

Design: ``docs/design/harness_test_taxonomy.md`` section 5.1.1.
"""

import logging
from typing import Any, Final

import pytest

logger = logging.getLogger(__name__)

_CODE: Final[str] = "QC_HARNESS_UNANTICIPATED_EXCEPTION"
_PROPERTY: Final[tuple[str, str]] = ("mqc_outcome", "broken")
_REASON: Final[str] = "mqc_broken_reason"
# EXIT 3 IS "NOTHING TRUSTWORTHY WAS MEASURED", the code a skipped
# precondition already takes.
_BROKEN_EXIT: Final[int] = 3


def mark_broken(report: Any, call: Any) -> bool:
    """Mark a phase report broken where its exception was not a measurement.

    Args:
        report (Any): The phase report pytest produced.
        call (Any): The phase's call information, carrying its exception.

    Returns:
        bool: True where the report was marked: the call phase failing with an
        exception other than an ``AssertionError`` or a deliberate
        ``pytest.fail``, or setup or teardown failing with any exception.
        The report gains a user property, and the crash is logged under
        ``QC_HARNESS_UNANTICIPATED_EXCEPTION`` with its type and message.
    """
    excinfo = getattr(call, "excinfo", None)
    if excinfo is None or not getattr(report, "failed", False):
        return False
    measured = (AssertionError, pytest.fail.Exception)
    if getattr(report, "when", "") == "call" and excinfo.errisinstance(measured):
        return False
    reason = f"{excinfo.typename}: {' '.join(str(excinfo.value).split())[:300]}"
    report.user_properties.extend([_PROPERTY, (_REASON, reason)])
    logger.error("%s %s raised %s", _CODE, getattr(report, "nodeid", "?"), reason)
    return True


def is_broken(report: Any) -> bool:
    """Report whether a phase report was marked broken.

    Args:
        report (Any): A phase report from the reporter's statistics.

    Returns:
        bool: True where :func:`mark_broken` marked it.
    """
    return _PROPERTY in (getattr(report, "user_properties", None) or [])


def broken_count(stats: dict[str, list[Any]]) -> tuple[int, int]:
    """Count broken reports among the failures and among the errors.

    Args:
        stats (dict): The terminal reporter's statistics.

    Returns:
        tuple[int, int]: Broken call-phase failures, which pytest filed under
        ``failed`` and the result block takes out of it, and broken setup or
        teardown errors, which pytest filed under ``error``.
    """
    return (
        sum(1 for report in stats.get("failed", []) if is_broken(report)),
        sum(1 for report in stats.get("error", []) if is_broken(report)),
    )


def broken_detail_lines(stats: dict[str, list[Any]]) -> list[str]:
    """Return one line per broken case, naming it, the code and the exception.

    Args:
        stats (dict): The terminal reporter's statistics.

    Returns:
        list[str]: ``broken 1 of 2: <node>, QC_HARNESS_UNANTICIPATED_EXCEPTION,
        <type>: <message>``, empty where nothing broke.
    """
    broken = [
        report for outcome in ("failed", "error")
        for report in stats.get(outcome, []) if is_broken(report)
    ]
    return [
        f"broken {index} of {len(broken)}: {getattr(report, 'nodeid', '?')}, {_CODE}, "
        f"{dict(report.user_properties).get(_REASON, '')}"
        for index, report in enumerate(broken, start=1)
    ]


def refuse_broken(session: Any) -> int:
    """Make the run exit 3 where any case broke.

    Args:
        session (Any): The finishing session, whose exit status is raised.

    Returns:
        int: How many reports broke. **Zero leaves the exit status alone.**
    """
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return 0
    broken = sum(broken_count(reporter.stats))
    if broken:
        logger.error("%d case(s) broke, so the run exits 3: %s", broken, _CODE)
        session.exitstatus = _BROKEN_EXIT
    return broken
