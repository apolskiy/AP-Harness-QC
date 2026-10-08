# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""What a band run established, in the band's own terms.

Specified by ``docs/design/cmn_verdict_and_cli.md`` section 7.11.

**pytest reports the selection it did not run.** A P1 band job ends with
``3 failed, 7 passed, 146 deselected``, and the 146 is every precondition plus
every case in the other bands. It is the largest number on the line, it is not
a result, and **no rate can be computed from it**: a reader has to subtract it
from a total nothing states to find the denominator.

**A band job is read for its band.** The job exists because a workflow run has
one conclusion and a band is the unit a remedy attaches to, so the summary this
emits counts only what the band selected. Totals across bands belong to the
verdict, which has every observation and the rules for weighing them.

**Two rates, because a skip is not a non-event.** The project owner's
correction, 2026-10-06: a dependent is skipped **to save cost**, not because
the case stopped mattering, and the reason it skipped is a failure upstream, an
environment that was not set, or a defect in our own scripts. A single rate
that dropped skips from its denominator would flatter the run by exactly the
number of cases it declined to measure.

| Rate | Over | Answers |
|---|---|---|
| **Execution** | passed plus failed | Of what ran, how much held |
| **Total** | passed plus failed plus skipped | Of what the band set out
  to establish, how much it established |

**The gap between them is the cost of the skips**, and it is the figure a
reader should see rather than infer. A band at 100% execution and 40% total
measured two cases in five and passed both.

**An empty denominator yields no rate rather than a hundred per cent**, which
is the rule section 1 of the verdict design states.
"""

import logging
from typing import Final, Optional

logger = logging.getLogger(__name__)

# A SKIP THAT IS NOT A RESULT. The cascade skips a dependent when its
# foundation failed, which is a consequence of a result rather than one of its
# own, so it is named separately and kept out of the rate. `framework-rules.md`
# section 3.4 and `cmn/layers.py`.
_DEPENDENCY_SKIP: Final[str] = "QC_HARNESS_DEPENDENCY_UNMET"

# A QUARANTINED SKIP IS A MODEL FINDING UNDER REPAIR, not our infrastructure
# wobbling, and the line says which because the remedy differs (design section
# 7.11). Matched on the code the skip message carries.
_QUARANTINE_SKIP: Final[str] = "QC_HARNESS_QUARANTINED"


def band_label(priority: str) -> str:
    """Return how a selection names itself.

    Args:
        priority (str): The ``--priority`` value, empty when none was given.

    Returns:
        str: ``"Band P0"`` for a single band, ``"Bands P2,P3,P4"`` for several,
        and ``"Whole selection"`` where no band filter applied.
    """
    bands = [part.strip() for part in str(priority).split(",") if part.strip()]
    if not bands:
        return "Whole selection"
    if len(bands) == 1:
        return f"Band P{bands[0]}"
    return "Bands " + ",".join(f"P{band}" for band in bands)


def band_lines(
    passed: int, failed: int, skip_reasons: list[str], priority: str = ""
) -> list[str]:
    """Return the two lines a band job is read for.

    Reports the band's total, what executed, what passed, what failed and what
    was skipped, each skip carrying its cause, then both rates with their
    fractions. ``code-style.md`` section 7.1 holds the vocabulary.

    Args:
        passed (int): Cases that passed.
        failed (int): Cases that failed.
        skip_reasons (list[str]): One reason per skipped case, so a skip behind
            a failed foundation, one in quarantine and one of ours can each be
            named by the remedy it takes.
        priority (str): The ``--priority`` value, for the label.

    Returns:
        list[str]: Two lines, or empty when the selection was empty. **An empty
        selection prints nothing rather than zeroes**, because a row of zeroes
        reads as a clean result.
    """
    skipped = len(skip_reasons)
    selected = passed + failed + skipped
    if not selected:
        return []

    executed = passed + failed
    blocked = sum(1 for reason in skip_reasons if _DEPENDENCY_SKIP in reason)
    parked = sum(1 for reason in skip_reasons if _QUARANTINE_SKIP in reason)
    other = skipped - blocked - parked

    # TOTAL, EXECUTED, PASSED, FAILED, SKIPPED, in the project owner's
    # vocabulary (`code-style.md` section 7.1). "Selected" sat next to pytest's
    # "deselected" and invited the reader to subtract one from the other.
    counted = [f"{selected} total", f"{executed} executed",
               f"{passed} passed", f"{failed} failed"]
    if blocked:
        counted.append(f"{blocked} skipped behind a higher band failure")
    if parked:
        counted.append(f"{parked} skipped as a known failure in quarantine")
    if other:
        counted.append(f"{other} skipped for a reason of ours")

    label = band_label(priority)
    return [
        f"{label}: " + ", ".join(counted),
        f"{label}: execution pass {_stated(passed, executed)}, "
        f"total pass {_stated(passed, selected)}",
    ]


def _stated(passed: int, denominator: int) -> str:
    """Return a rate with its fraction, or why there is none.

    **The fraction is printed beside the percentage** so a reader checks the
    arithmetic rather than trusting it, which is the same reason the register
    carries a population beside a finding.

    Args:
        passed (int): The numerator.
        denominator (int): What it is over.

    Returns:
        str: Such as ``"75.0% (9 of 12)"``, or a statement that nothing was
        measured.
    """
    rate = pass_rate(passed, denominator)
    if rate is None:
        return "no rate, nothing measured"
    return f"{rate:.1f}% ({passed} of {denominator})"


def pass_rate(passed: int, denominator: int) -> Optional[float]:
    """Return a pass percentage over whichever denominator is asked for.

    **No metric divides without testing its denominator for zero**, which is
    the rule section 1 of the verdict design states: a zero denominator means
    the question is unanswerable, and that is never the same as a hundred per
    cent.

    Args:
        passed (int): Cases that passed.
        denominator (int): What executed, or everything selected, depending on
            which of the two rates the caller is stating.

    Returns:
        Optional[float]: The percentage, or ``None`` when the denominator is
        zero.
    """
    if denominator <= 0:
        return None
    return 100.0 * passed / denominator


def skip_reasons_from(reports: list[object]) -> list[str]:
    """Return one reason per skipped report, however pytest spelled it.

    **A skip's reason is a tuple of path, line and message**, and reading only
    the message would lose the cases where pytest carries a string instead.

    Args:
        reports (list): The skipped reports.

    Returns:
        list[str]: One reason per report, empty strings included so the count
        matches the number of skips.
    """
    reasons: list[str] = []
    for report in reports:
        longrepr = getattr(report, "longrepr", None)
        if isinstance(longrepr, tuple) and len(longrepr) >= 3:
            reasons.append(str(longrepr[2]))
        else:
            reasons.append(str(longrepr or ""))
    return reasons


# WHICH BANDS BLOCK A RELEASE. P0 and P1 are release blocking and a lower band
# is a bug to open and quarantine while review sets the date, per
# `testing-standards.md` section 2. The distinction is what makes a per-band
# table worth more than a total: a run at 95% overall with one P0 failure does
# not ship.
BLOCKING_BANDS: Final[frozenset[str]] = frozenset({"0", "1"})


def band_table(measured: list[tuple[str, int, int, list[str]]]) -> list[str]:
    """Return a per-band table with totals, as Markdown.

    **The total is last and decides nothing.** A release question is answered
    by the blocking bands: a run at 95% overall with one P0 failure does not
    ship, and a table whose only honest row was the last one would say the
    opposite.

    Args:
        measured (list): One entry per band, as priority, passed, failed and
            the reason of each skip.

    Returns:
        list[str]: Markdown lines, empty when nothing was measured at all.
    """
    rows: list[str] = []
    totals = [0, 0, 0, 0]
    blocking_failures = 0

    for priority, passed, failed, reasons in measured:
        skipped = len(reasons)
        selected = passed + failed + skipped
        if not selected:
            continue
        executed = passed + failed
        totals = [
            totals[0] + selected, totals[1] + executed,
            totals[2] + passed, totals[3] + failed,
        ]
        if failed and any(part.strip() in BLOCKING_BANDS
                          for part in str(priority).split(",")):
            blocking_failures += failed
        rows.append(
            f"| {band_label(priority)} | {selected} | {executed} | {passed} "
            f"| {failed} | {skipped} | {_percentage(passed, executed)} "
            f"| {_percentage(passed, selected)} |"
        )

    if not rows:
        return []

    skipped_total = totals[0] - totals[1]
    rows.append(
        f"| **Total** | **{totals[0]}** | **{totals[1]}** | **{totals[2]}** "
        f"| **{totals[3]}** | **{skipped_total}** "
        f"| **{_percentage(totals[2], totals[1])}** "
        f"| **{_percentage(totals[2], totals[0])}** |"
    )

    verdict = (
        f"**Release blocking: {blocking_failures} failure(s) in P0 or P1.**"
        if blocking_failures
        else "**No release blocking failure.** P0 and P1 are clean."
    )
    return [
        "| Band | Total | Executed | Passed | Failed | Skipped "
        "| Execution pass | Total pass |",
        "|---|---|---|---|---|---|---|---|",
        *rows,
        "",
        verdict,
        "",
        "**The total decides nothing.** A release question is answered by the "
        "blocking bands: P0 and P1 block, and a lower band is a bug to open "
        "and quarantine while review sets the date.",
    ]


def _percentage(passed: int, denominator: int) -> str:
    """Return a percentage for a table cell, or a dash where there is none.

    Args:
        passed (int): The numerator.
        denominator (int): What it is over.

    Returns:
        str: Such as ``"75.0%"``, or ``"n/a"`` when nothing was measured.
    """
    rate = pass_rate(passed, denominator)
    return "n/a" if rate is None else f"{rate:.1f}%"
