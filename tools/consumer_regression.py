# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Compares a consumer's graded replay before and after a harness change, case by case.

Created: 2026-10-01
Last updated: 2026-11-09

This file contains ``case_outcomes``, which reads a JUnit report and returns
each case's outcome with its codes; ``changed_outcomes``, which lists every
case whose outcome differs between a replay against the harness before the
change and one against the change; and ``main``, the command line that exits
0 when no outcome changed, 1 when one did, and 4 when either report is
missing, will not parse or holds no case.

**The ``regress-consumers-on-merge`` workflow runs it** after replaying the
consumer's graded suite twice, against the harness commit before the change
and against the change. A replay reads recorded responses and judgements and
sends nothing to a model, so an outcome that differs between the two was
changed by the harness, whatever its code, and fails the job. An outcome that
matches is the consumer's, a model finding or a case defect, and its own
review decides which.

An outcome is ``passed``, ``passw``, ``failed``, ``skipped`` or ``error``,
followed by the sorted codes the case reported: a passw's warning codes, and
the ``QC_*`` codes in a failure, skip or error message. A case present on one
side only is ``absent`` on the other.

Specified by ``docs/design/harness_ci_pipeline.md`` section 3B.3.1.
"""

import argparse
import logging
import re
from pathlib import Path
from typing import Final, Optional
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

_CODE: Final[re.Pattern[str]] = re.compile(r"QC_[A-Z]+(?:_[A-Z]+)+")
_PROBLEMS: Final[tuple[tuple[str, str], ...]] = (
    ("error", "error"), ("failure", "failed"), ("skipped", "skipped"))
_ABSENT: Final[str] = "absent"

_EXIT_UNCHANGED: Final[int] = 0
_EXIT_CHANGED: Final[int] = 1
_EXIT_REFUSED: Final[int] = 4


def _outcome(case: ElementTree.Element) -> str:
    """Return one testcase's outcome followed by its sorted codes.

    Args:
        case (ElementTree.Element): A ``testcase`` element.

    Returns:
        str: For example ``passed`` or ``failed QC_LLM_SOURCE_ALTERATION``.
    """
    for tag, outcome in _PROBLEMS:
        problem = case.find(tag)
        if problem is not None:
            text = (problem.get("message") or "") + (problem.text or "")
            return " ".join([outcome, *sorted(set(_CODE.findall(text)))])
    properties = {prop.get("name"): prop.get("value") for prop in case.iter("property")}
    if properties.get("mqc_outcome") == "passw":
        codes = sorted({prop.get("value") or "" for prop in case.iter("property")
                        if prop.get("name") == "mqc_warning_code"})
        return " ".join(["passw", *codes])
    return "passed"


def case_outcomes(report: Path) -> dict[str, str]:
    """Return each case's outcome in a JUnit report, keyed by class and name.

    Args:
        report (Path): A consumer's graded JUnit XML.

    Returns:
        dict[str, str]: ``classname::name`` to its outcome with codes.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the report is
            absent, will not parse or holds no case. A replay that produced
            no case verified nothing, and an empty comparison would read as
            no change.
    """
    if not report.is_file():
        raise ValueError(f"QC_HARNESS_PARSER_ERROR: no consumer report at {report}")
    try:
        tree = ElementTree.parse(report)
    except ElementTree.ParseError as error:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: consumer report at {report} will not parse"
        ) from error
    outcomes = {f"{case.get('classname', '')}::{case.get('name', '(unnamed)')}": _outcome(case)
                for case in tree.iter("testcase")}
    if not outcomes:
        raise ValueError(f"QC_HARNESS_PARSER_ERROR: consumer report at {report} holds no case")
    return outcomes


def changed_outcomes(baseline: Path, candidate: Path) -> list[str]:
    """Return one line per case whose outcome differs across the harness change.

    Args:
        baseline (Path): The replay against the harness before the change.
        candidate (Path): The replay against the change.

    Returns:
        list[str]: ``name: <before> before the change, <after> after it``,
        sorted by case, empty when every outcome matches.

    Raises:
        ValueError: From :func:`case_outcomes`.
    """
    before = case_outcomes(baseline)
    after = case_outcomes(candidate)
    changed: list[str] = []
    for key in sorted(before.keys() | after.keys()):
        was = before.get(key, _ABSENT)
        now = after.get(key, _ABSENT)
        if was != now:
            changed.append(f"{key.split('::', 1)[1]}: {was} before the change, {now} after it")
    return changed


def main(argv: Optional[list[str]] = None) -> int:
    """Report whether a harness change altered any outcome of a consumer's graded replay.

    Args:
        argv (Optional[list]): Arguments, for calling in-process from a case.

    Returns:
        int: ``0`` unchanged, ``1`` changed, ``4`` refused.
    """
    parser = argparse.ArgumentParser(
        prog="consumer-regression",
        description="Fail when a harness change alters an outcome of a consumer's graded replay",
    )
    parser.add_argument("baseline", type=Path,
                        help="The graded JUnit XML replayed on the harness before the change")
    parser.add_argument("candidate", type=Path,
                        help="The graded JUnit XML replayed on the change")
    parsed = parser.parse_args(argv)

    try:
        changed = changed_outcomes(parsed.baseline, parsed.candidate)
    except ValueError as error:
        logger.error("%s", error)
        return _EXIT_REFUSED

    if changed:
        for line in changed:
            logger.error("%s", line)
        logger.error("%d outcome(s) changed with the harness: this change broke the consumer",
                     len(changed))
        return _EXIT_CHANGED

    logger.info("no outcome of the consumer's graded replay changed with the harness; "
                "any failure there is the consumer's to review")
    return _EXIT_UNCHANGED


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
