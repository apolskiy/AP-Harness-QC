# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The requested-test resolver, which validates named tests before a debug run.

Created: 2026-10-29
Last updated: 2026-10-29

This file contains ``requested_names``, which splits the identifiers a caller
supplied on commas and newlines; ``unmatched_names``, which reports those the
suite does not collect; ``selection_expression``, which joins the survivors
into the expression pytest's keyword selector takes; and ``main``, the command
line the workflow step runs.

The ``resolve`` step of ``debug-failures-on-demand.yml`` runs it before the
run step, and writes its output to the file named by ``--output``, which the
step sets to the Actions output file. Its exit status gates the run: a refusal
stops the workflow before any test or any provider request.

Specified by ``docs/design/harness_ci_pipeline.md`` section 8.10.

**A mistyped identifier is the defect this exists to catch.** It selects
nothing, and pytest then exits cleanly having run zero tests, which reads
exactly like a run where everything passed. Refusing before the run turns a
silent non-result into a failed step.

**It was 29 lines of Python inline in the workflow until 2026-10-29.** Nothing
linted it, nothing covered it, and it could not be run outside a workflow.
"""

import argparse
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Final, Optional

logger = logging.getLogger(__name__)

_ENCODING: Final[str] = "utf-8"
_SEPARATORS: Final[re.Pattern] = re.compile(r"[,\n]")

# Section 7.3 keeps the verdict codes clear of argparse, which exits 2. A
# refusal here is a precondition failure: nothing was measured and nothing
# should be.
_EXIT_RESOLVED: Final[int] = 0
_EXIT_REFUSED: Final[int] = 3


def requested_names(supplied: str) -> list[str]:
    """Split the identifiers a caller supplied, dropping blanks.

    Args:
        supplied (str): The raw input, comma or newline separated.

    Returns:
        list[str]: The names, stripped, in the order given. Order is kept
        because the expression it builds reads back to the caller.
    """
    return [entry.strip() for entry in _SEPARATORS.split(supplied) if entry.strip()]


def collected_tests(root: Path) -> str:
    """Return what the suite collects, as pytest's quiet collection prints it.

    Args:
        root (Path): The repository to collect in.

    Returns:
        str: pytest's standard output. **Its exit status is deliberately not
        read**: a collection naming no match still prints the tests that do
        exist, and the caller's question is whether a name appears in them.
    """
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        capture_output=True, text=True, encoding=_ENCODING, cwd=root,
        stdin=subprocess.DEVNULL, timeout=600, check=False, shell=False,
    )
    return str(completed.stdout or "")


def unmatched_names(names: list[str], collected: str) -> list[str]:
    """Return the requested names the collection does not contain.

    Args:
        names (list[str]): The requested identifiers.
        collected (str): What the suite collects.

    Returns:
        list[str]: Those matching nothing, in the order requested.
    """
    return [name for name in names if name not in collected]


def selection_expression(names: list[str]) -> str:
    """Join the requested names into pytest's keyword expression.

    Args:
        names (list[str]): The requested identifiers.

    Returns:
        str: The names joined by ``or``, which selects their union.
    """
    return " or ".join(names)


def main(argv: Optional[list[str]] = None) -> int:
    """Validate the requested tests and write the step's outputs.

    Args:
        argv (Optional[list]): Arguments, for calling in-process from a case.

    Returns:
        int: ``0`` once every name resolved, ``3`` when none were supplied or
        one matched nothing.
    """
    parser = argparse.ArgumentParser(
        prog="resolve-requested-tests",
        description="Validate the named tests a debug run was asked for",
    )
    parser.add_argument("--tests", required=True, help="The identifiers supplied")
    parser.add_argument(
        "--output", required=True, type=Path,
        help="The file to append the resolved outputs to",
    )
    parser.add_argument(
        "--root", default=Path("."), type=Path,
        help="The repository to collect in",
    )
    parsed = parser.parse_args(argv)

    names = requested_names(str(parsed.tests))
    if not names:
        logger.error("::error::no test identifiers were supplied")
        return _EXIT_REFUSED

    unmatched = unmatched_names(names, collected_tests(Path(parsed.root)))
    if unmatched:
        logger.error(
            "::error::these identifiers matched no collected test: %s",
            ", ".join(unmatched),
        )
        return _EXIT_REFUSED

    # APPENDED, because the Actions output file accumulates across steps and a
    # write would discard what an earlier step put there.
    lines = f"expression={selection_expression(names)}\ncount={len(names)}\n"
    with Path(parsed.output).open("a", encoding=_ENCODING, newline="\n") as handle:
        handle.write(lines)
    logger.info("resolved %d requested test(s)", len(names))
    return _EXIT_RESOLVED


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
