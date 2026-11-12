# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Compares a consumer's graded replay before and after a harness change, case by case.

Created: 2026-10-01
Last updated: 2026-11-12

This file contains ``case_outcomes``, which reads a JUnit report and returns
each case's outcome with its codes; ``baseline_not_run``, which says why the
replay against the harness before the change did not run, or nothing when it
ran; ``changed_outcomes``, which lists every case whose outcome differs
between a replay against the harness before the change and one against the
change; ``summary_lines``, which renders the comparison for the run page; and
``main``, the command line that exits 0 when no outcome changed, 1 when one
did, 0 with ``QC_HARNESS_DEPENDENCY_UNMET`` when the baseline did not run,
and 4 when the candidate report is missing, will not parse or holds no case,
and appends the summary to ``--summary`` when given.

**The candidate is read first** (section 3B.3.4): it is the change under
test, so a candidate report that cannot be read refuses whatever the
baseline did. **A baseline that did not run skips**: its report is missing,
will not parse or holds no case, or pytest wrote a ``collection failure`` or
``internal error`` testcase, the two it writes for a session that stopped
early. Nothing was compared, so the skip is not a finding about the change.

**The summary says what was compared** (section 3B.3.3): the verdict in its
heading, each side's harness commit and its passed, passw, failed, skipped
and error counts, and every changed case before and after the change. A
refusal gives its reason and says nothing was compared.

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

Specified by ``docs/design/harness_ci_pipeline.md`` sections 3B.3.1, 3B.3.3 and 3B.3.4.
"""

import argparse
import logging
import re
from pathlib import Path
from typing import Final, Optional
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

_ENCODING: Final[str] = "utf-8"
_CODE: Final[re.Pattern[str]] = re.compile(r"QC_[A-Z]+(?:_[A-Z]+)+")
_PROBLEMS: Final[tuple[tuple[str, str], ...]] = (
    ("error", "error"), ("failure", "failed"), ("skipped", "skipped"))
_ABSENT: Final[str] = "absent"
_COUNTED: Final[tuple[str, ...]] = ("passed", "passw", "failed", "skipped", "error")
_HEADING: Final[str] = "## Outcomes across the harness change: "
_PARSER_ERROR: Final[str] = "QC_HARNESS_PARSER_ERROR"
_UNMET: Final[str] = "QC_HARNESS_DEPENDENCY_UNMET"
_SESSION_ERRORS: Final[tuple[str, ...]] = ("collection failure", "internal error")
_TABLE_HEAD: Final[tuple[str, str]] = (
    "| | Harness commit | " + " | ".join(_COUNTED) + " |", "|---|---|" + "---|" * len(_COUNTED))

_EXIT_UNCHANGED: Final[int] = 0
_EXIT_CHANGED: Final[int] = 1
_EXIT_SKIPPED: Final[int] = 0
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
        raise ValueError(f"{_PARSER_ERROR}: no consumer report at {report}")
    try:
        tree = ElementTree.parse(report)
    except ElementTree.ParseError as error:
        raise ValueError(
            f"{_PARSER_ERROR}: consumer report at {report} will not parse"
        ) from error
    outcomes = {f"{case.get('classname', '')}::{case.get('name', '(unnamed)')}": _outcome(case)
                for case in tree.iter("testcase")}
    if not outcomes:
        raise ValueError(f"{_PARSER_ERROR}: consumer report at {report} holds no case")
    return outcomes


def baseline_not_run(report: Path) -> Optional[str]:
    """Return why the baseline replay did not run, or ``None`` when it ran.

    Args:
        report (Path): The graded JUnit XML replayed on the harness before the change.

    Returns:
        Optional[str]: The reason, without a code, when the report is
        missing, will not parse or holds no case, or holds a testcase whose
        error pytest wrote as ``collection failure`` or ``internal error``;
        otherwise ``None``.
    """
    try:
        case_outcomes(report)
    except ValueError as error:
        return str(error).removeprefix(f"{_PARSER_ERROR}: ")
    stopped = [f"{problem.get('message')} in {case.get('name', '(unnamed)')}"
               for case in ElementTree.parse(report).iter("testcase")
               for problem in case.findall("error")
               if problem.get("message") in _SESSION_ERRORS]
    if stopped:
        return f"pytest stopped before running a case, reporting {', '.join(stopped)}"
    return None


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


def _count_row(label: str, commit: str, outcomes: dict[str, str]) -> str:
    """Return one summary table row: a side, its commit and its outcome counts.

    Args:
        label (str): ``Before the change`` or ``After it``.
        commit (str): The harness commit that side ran on.
        outcomes (dict[str, str]): That side's outcomes, from :func:`case_outcomes`.

    Returns:
        str: A Markdown table row.
    """
    firsts = [outcome.split(" ", 1)[0] for outcome in outcomes.values()]
    counts = " | ".join(str(firsts.count(kind)) for kind in _COUNTED)
    return f"| {label} | `{commit}` | {counts} |"


def summary_lines(baseline: Path, candidate: Path,
                  baseline_commit: str, candidate_commit: str) -> list[str]:
    """Render the comparison for the run page.

    Args:
        baseline (Path): The replay against the harness before the change.
        candidate (Path): The replay against the change.
        baseline_commit (str): The harness commit before the change.
        candidate_commit (str): The harness commit under test.

    Returns:
        list[str]: Markdown lines: the verdict as a heading, both sides'
        commits and counts, and every changed case; the skip, its reason and
        the candidate's commit and counts; or the refusal and its reason.
    """
    try:
        after = case_outcomes(candidate)
    except ValueError as error:
        return [f"{_HEADING}refused", "", f"**Refused:** {error}. Nothing was compared.", ""]
    reason = baseline_not_run(baseline)
    if reason is not None:
        return [f"{_HEADING}skipped", "",
                f"**Skipped, {_UNMET}:** the replay against the harness before the change "
                f"did not run: {reason}. Nothing was compared, so this is not a finding "
                "about the change.", "", *_TABLE_HEAD,
                _count_row("After it", candidate_commit, after), ""]

    before = case_outcomes(baseline)
    changed = changed_outcomes(baseline, candidate)
    lines = [f"{_HEADING}{'changed' if changed else 'unchanged'}", "", *_TABLE_HEAD,
             _count_row("Before the change", baseline_commit, before),
             _count_row("After it", candidate_commit, after), ""]
    if changed:
        lines += [f"**{len(changed)} outcome(s) changed with the harness**, so this change "
                  "broke the consumer:", ""]
        lines += [f"- `{name}`:{rest}" for name, rest in
                  (line.split(":", 1) for line in changed)]
    else:
        lines.append("No outcome changed. Any failure above is the consumer's to review.")
    return [*lines, ""]


def main(argv: Optional[list[str]] = None) -> int:
    """Report whether a harness change altered any outcome of a consumer's graded replay.

    Args:
        argv (Optional[list]): Arguments, for calling in-process from a case.

    Returns:
        int: ``0`` unchanged or skipped, ``1`` changed, ``4`` refused.
    """
    parser = argparse.ArgumentParser(
        prog="consumer-regression",
        description="Fail when a harness change alters an outcome of a consumer's graded replay",
    )
    parser.add_argument("baseline", type=Path,
                        help="The graded JUnit XML replayed on the harness before the change")
    parser.add_argument("candidate", type=Path,
                        help="The graded JUnit XML replayed on the change")
    parser.add_argument("--summary", type=Path,
                        help="A Markdown file to append the comparison to, the run page's")
    parser.add_argument("--baseline-commit", default="before the change",
                        help="The harness commit the baseline replay ran on")
    parser.add_argument("--candidate-commit", default="the change",
                        help="The harness commit under test")
    parsed = parser.parse_args(argv)

    if parsed.summary is not None:
        with parsed.summary.open("a", encoding=_ENCODING) as page:
            page.write("\n".join(summary_lines(parsed.baseline, parsed.candidate,
                                               parsed.baseline_commit,
                                               parsed.candidate_commit)))

    try:
        case_outcomes(parsed.candidate)
    except ValueError as error:
        logger.error("%s", error)
        return _EXIT_REFUSED
    reason = baseline_not_run(parsed.baseline)
    if reason is not None:
        logger.warning("%s: the replay against the harness before the change did not run: "
                       "%s; nothing was compared", _UNMET, reason)
        return _EXIT_SKIPPED

    changed = changed_outcomes(parsed.baseline, parsed.candidate)
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
