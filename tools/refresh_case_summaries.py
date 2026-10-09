# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Write each test module's case block from the module's own syntax tree.

Run from a repository root::

    python tools/refresh_case_summaries.py
    python tools/refresh_case_summaries.py --check

**Idempotent.** A module whose block is already correct is left untouched and
reported as unchanged, so running it twice changes nothing and running it after
every case is cheap.

Specified in ``.claude/rules/testing-standards.md``, "A Test Module Lists The
Cases It Holds". ``MQC_CMN_UNI_112348`` and ``MQC_CAS_UNI_115719`` fail the run
when a block disagrees with its module, which is what makes this a tool rather
than a convention.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from cmn.case_summary import case_modules, refreshed_source, summary_problems

logger = logging.getLogger(__name__)

_EXIT_CLEAN = 0
_EXIT_STALE = 1
_EXIT_REFUSED = 4


def refresh(root: Path, *, write: bool = True) -> list[str]:
    """Bring every module's case block into agreement with its cases.

    Args:
        root (Path): The repository root.
        write (bool): False reports without writing, for a gate.

    Returns:
        list[str]: One entry per module that changed, or would have.
    """
    changed: list[str] = []
    for path in case_modules(root):
        current = path.read_text(encoding="utf-8")
        wanted = refreshed_source(path)
        if wanted == current:
            continue
        changed.append(path.relative_to(root).as_posix())
        if write:
            path.write_text(wanted, encoding="utf-8", newline="\n")
    return changed


def main(argv: Optional[list[str]] = None) -> int:
    """Refresh the blocks, or report that they are stale.

    Args:
        argv (Optional[list]): Arguments, for calling in-process from a case.

    Returns:
        int: ``0`` nothing to do, ``1`` stale under ``--check``, ``4`` refused.
    """
    parser = argparse.ArgumentParser(
        prog="refresh-case-summaries",
        description="Write each test module's case block from its own cases",
    )
    parser.add_argument(
        "--root", type=Path, default=Path("."), help="The repository root"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report disagreement and write nothing",
    )
    parsed = parser.parse_args(argv)

    root = parsed.root.resolve()
    if not (root / "tests").is_dir():
        logger.error(
            "QC_HARNESS_PARSER_ERROR: %s holds no tests directory, so there is "
            "nothing to summarise", root
        )
        return _EXIT_REFUSED

    if parsed.check:
        problems = summary_problems(root)
        for problem in problems:
            logger.error("%s", problem)
        logger.info("%d module(s) disagree with their cases", len(problems))
        return _EXIT_STALE if problems else _EXIT_CLEAN

    changed = refresh(root)
    for name in changed:
        logger.info("refreshed %s", name)
    logger.info(
        "%d module(s) refreshed, %d already correct",
        len(changed), len(case_modules(root)) - len(changed),
    )
    return _EXIT_CLEAN


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(main())
