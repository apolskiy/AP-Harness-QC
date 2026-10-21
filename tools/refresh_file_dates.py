# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Writes the creation and update dates into every module docstring that needs them.

Created: 2026-10-21
Last updated: 2026-10-21

This file contains ``refresh``, which gives an undated module both its
``Created:`` and ``Last updated:`` lines and moves ``Last updated`` to today on
every module changed since its last commit, returning the modules it changed;
and ``main``, the command line, which writes the dates or, under ``--check``,
only reports the problems ``cmn.file_dates.file_date_problems`` finds.

**An author runs it before committing**, after the edits and after
``tools/refresh_case_summaries.py``, so every changed file says it changed
today. The Model Repository runs the same tool with ``--root``.

Run from a repository root::

    python tools/refresh_file_dates.py
    python tools/refresh_file_dates.py --check
    python <harness>/tools/refresh_file_dates.py --root .

**``Created`` is never moved.** A new module takes the day git first recorded
it, or today when git has no record yet; a module that already carries the line
keeps it. **Idempotent**: a second run on the same day changes nothing.

Specified by ``.claude/rules/code-style.md`` section 3.1.2.
``MQC_CMN_UNI_112526`` and ``MQC_CAS_UNI_115773`` fail the run when a date is
missing or stale, which is what makes this a tool rather than a convention.
"""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from cmn.code_standards import python_sources
from cmn.file_dates import (
    changed_files,
    date_lines,
    file_date_problems,
    first_added,
    stamped_source,
)

logger = logging.getLogger(__name__)

_EXIT_CLEAN = 0
_EXIT_STALE = 1
_EXIT_REFUSED = 4


def refresh(root: Path, today: date) -> list[str]:
    """Date every undated module and move every changed module's update to today.

    Args:
        root (Path): The repository root.
        today (date): The date written as the update.

    Returns:
        list[str]: One entry per module rewritten.
    """
    stamp = today.isoformat()
    changed = changed_files(root) or set()
    rewritten: list[str] = []
    for path in python_sources(root):
        name = path.relative_to(root).as_posix()
        current = path.read_text(encoding="utf-8")
        created, updated = date_lines(current)
        if created is None:
            created = first_added(root, name) or stamp
            updated = stamp
        elif updated is None or name in changed:
            updated = stamp
        wanted = stamped_source(current, created, updated)
        if wanted == current:
            continue
        path.write_text(wanted, encoding="utf-8", newline="\n")
        rewritten.append(name)
    return rewritten


def main(argv: Optional[list[str]] = None) -> int:
    """Refresh the dates, or report that they are missing or stale.

    Args:
        argv (Optional[list]): Arguments, for calling in-process from a case.

    Returns:
        int: ``0`` nothing to do, ``1`` problems under ``--check``, ``4`` refused.
    """
    parser = argparse.ArgumentParser(
        prog="refresh-file-dates",
        description="Write each module's Created and Last updated dates",
    )
    parser.add_argument("--root", type=Path, default=Path("."), help="The repository root")
    parser.add_argument(
        "--check", action="store_true", help="Report problems and write nothing"
    )
    parsed = parser.parse_args(argv)

    root = parsed.root.resolve()
    if not python_sources(root):
        logger.error(
            "QC_HARNESS_PARSER_ERROR: %s holds no Python files, so there is nothing to date",
            root,
        )
        return _EXIT_REFUSED

    today = date.today()
    if parsed.check:
        problems = file_date_problems(root, today)
        for problem in problems:
            logger.error("%s", problem)
        logger.info("%d file date problem(s)", len(problems))
        return _EXIT_STALE if problems else _EXIT_CLEAN

    rewritten = refresh(root, today)
    for name in rewritten:
        logger.info("dated %s", name)
    logger.info("%d module(s) dated, %d already current",
                len(rewritten), len(python_sources(root)) - len(rewritten))
    return _EXIT_CLEAN


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(main())
