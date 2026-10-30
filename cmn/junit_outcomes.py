# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The failure lister, which names the cases a run reported as failed or broken.

Created: 2026-10-29
Last updated: 2026-10-29

This file contains ``outcomes``, which reads one JUnit report and returns its
failing and its erroring cases apart from each other, ``report_lines``, which
renders that for a reader, and ``main``, the command line both run behind.

An operator runs it after a leg, on the report that leg wrote, when the
question is **which** cases went red. Why one went red is read from Allure or
from the ``vendor-report`` attachment a failing case carries. It reads a file
and dispatches nothing, so it costs no quota and needs no credentials, and its
exit status reports whether the report could be read rather than whether the
run was green.

Specified by ``docs/design/cmn_verdict_and_cli.md`` section 7.12.

**A failure and an error are listed apart, because they implicate different
code.** A failure is a case whose assertions did not hold, which for a graded
case is a finding about the model; an error is a case that raised something
else, which is an instrument defect meaning nothing about a model was measured.
That is the same division the exit codes rest on, at section 7.3.

**It lives here and not in either repository's tools, because both runbooks
documented it.** One implementation called from each root is the arrangement
the encoding, annotation, header and naming rules already use, and a convenience
copied into two repositories is a copy that drifts.
"""

import argparse
import logging
from pathlib import Path
from typing import Final, Optional
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

# Section 7.3 keeps the verdict codes clear of argparse, which exits 2. A
# report naming a red case is a result rather than a tool failure, so only an
# unreadable report refuses.
_EXIT_READ: Final[int] = 0
_EXIT_REFUSED: Final[int] = 4


def outcomes(report: Path) -> tuple[list[str], list[str]]:
    """Return the failing and the erroring cases one report names.

    Args:
        report (Path): The JUnit XML a leg wrote.

    Returns:
        tuple: The failing cases and the erroring cases, each as
        ``"<classname> <name>"`` in report order.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the report is absent
            or will not parse. **Refused rather than reported as no
            failures**: a leg that wrote no report measured nothing, and an
            empty list would read as a clean run.
    """
    if not report.is_file():
        raise ValueError(f"QC_HARNESS_PARSER_ERROR: no report at {report}")
    try:
        tree = ElementTree.parse(report)
    except ElementTree.ParseError as error:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: the report at {report} will not parse"
        ) from error

    failed: list[str] = []
    broken: list[str] = []
    for element in tree.getroot().iter("testcase"):
        named = f"{element.get('classname', '')} {element.get('name', '')}".strip()
        # A CASE CARRYING BOTH IS COUNTED AS BROKEN ONCE. pytest writes an
        # error for a failure in setup or teardown around an already failing
        # call, and the instrument defect is the one that decides the remedy.
        if element.find("error") is not None:
            broken.append(named)
        elif element.find("failure") is not None:
            failed.append(named)
    return failed, broken


def report_lines(report: Path, failed: list[str], broken: list[str]) -> list[str]:
    """Render what one report found, counts first.

    Args:
        report (Path): The report the lines describe.
        failed (list[str]): Its failing cases.
        broken (list[str]): Its erroring cases.

    Returns:
        list[str]: The lines to print. **A clean report still produces its
        count line**, so a reader is never left deciding whether the tool ran
        or found nothing.
    """
    lines = [f"{report}: {len(failed)} failed, {len(broken)} broken"]
    lines.extend(f"  failed  {entry}" for entry in failed)
    # NAMED APART AND SECOND. An errored case measured nothing, so a reader
    # scanning for model findings must not meet one inside that list.
    lines.extend(f"  broken  {entry}" for entry in broken)
    return lines


def main(argv: Optional[list[str]] = None) -> int:
    """List the failing and erroring cases in every report named.

    Args:
        argv (Optional[list]): Arguments, for calling in-process from a case.

    Returns:
        int: ``0`` once every report was read, ``4`` when one could not be.
    """
    parser = argparse.ArgumentParser(
        prog="junit-outcomes",
        description="Name the cases a run reported as failed or broken",
    )
    parser.add_argument(
        "report", type=Path, nargs="+", help="The JUnit XML a leg wrote"
    )
    parsed = parser.parse_args(argv)

    refused = False
    for report in parsed.report:
        try:
            failed, broken = outcomes(report)
        except ValueError as error:
            logger.error("%s", error)
            refused = True
            continue
        for line in report_lines(report, failed, broken):
            logger.info("%s", line)
    return _EXIT_REFUSED if refused else _EXIT_READ


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
