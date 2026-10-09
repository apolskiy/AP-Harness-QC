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

# WHAT EACH SKIP CODE MEANS IN WORDS, so a line states the cause and not the
# family it belongs to. "For a reason of ours" covered nineteen codes taking
# five different remedies, and the project owner read it and inferred the wrong
# one (design section 7.11.3).
#
# KEYED ON THE REGISTERED CODE, which `test_taxonomy.md` section 6 owns. A code
# absent from this map is reported as itself rather than folded into a
# catch-all: unrecognised and named is informative, unrecognised and grouped is
# how the vague phrase happened.
_SKIP_CAUSES: Final[dict[str, str]] = {
    "QC_HARNESS_DEPENDENCY_UNMET": "blocked by a failure in a higher priority band",
    "QC_HARNESS_QUARANTINED": "a known failure in quarantine, not dispatched",
    "QC_HARNESS_FIXTURE_MISSING": "no recorded response for this engine",
    "QC_HARNESS_FIXTURE_STALE": "the recorded response no longer answers this request",
    "QC_HARNESS_BUDGET_EXHAUSTED": "the run reached its spending ceiling",
    "QC_HARNESS_CREDIT_EXHAUSTED": "the account has no credit left",
    "QC_HARNESS_ENGINE_UNREACHABLE": "the provider could not be reached",
    "QC_HARNESS_PROVIDER_UNAVAILABLE": "the provider declined to serve the request",
    "QC_HARNESS_RATE_LIMIT": "the provider rate limited the run",
    "QC_HARNESS_CANDIDATE_TIMEOUT": "the model did not answer in time",
    "QC_HARNESS_JUDGE_TIMEOUT": "the judge did not answer in time",
    "QC_HARNESS_AUTH_ERROR": "the credential was refused",
    "QC_HARNESS_PARSER_ERROR": "the response could not be parsed",
}

_UNSTATED: Final[str] = "no cause recorded, which is itself a defect"


def skip_detail_lines(skips: list[tuple[str, str]]) -> list[str]:
    """Return one line per skipped case, naming the case and why it skipped.

    **One line per case, not one per cause.** The project owner's instruction
    of 2026-10-09: a line per case simplifies the parsing, because a reader or
    an analyser keys on the case and finds its reason beside it rather than
    joining a count back to names it does not have.

    **Three comma-separated fields after one colon**: the case, the registered
    code, and what the code means. One colon keeps each line a single statement
    (`code-style.md` section 7).

    Design: ``cmn_verdict_and_cli.md`` section 7.11.3.

    Args:
        skips (list): One ``(case, reason)`` pair per skipped case, the reason
            opening with its registered taxonomy code.

    Returns:
        list[str]: ``"skipped <n> of <total>: <case>, <CODE>, <meaning>"``,
        sorted by case so the order does not depend on which ran first. Empty
        where nothing skipped.
    """
    ordered = sorted(skips, key=lambda pair: (pair[0], pair[1]))
    return [
        f"skipped {index} of {len(ordered)}: {case or 'an unnamed case'}, "
        f"{_code_in(reason) or 'no code'}, {_meaning_of(reason)}"
        for index, (case, reason) in enumerate(ordered, 1)
    ]


def _meaning_of(reason: str) -> str:
    """Return what a skip reason's code means, in words.

    Args:
        reason (str): The skip message.

    Returns:
        str: The described meaning, a statement that the code is registered and
        undescribed, or that none was recorded. **Never silence**: a skip whose
        cause nobody wrote down is itself a defect and the line says so.
    """
    code = _code_in(reason)
    if not code:
        return _UNSTATED
    return _SKIP_CAUSES.get(code, "cause not described here")


def _code_in(reason: str) -> str:
    """Return the taxonomy code a skip message opens with.

    Args:
        reason (str): The skip message.

    Returns:
        str: The code, or an empty string where the message names none. **The
        first token before a colon**, which is the shape every emitted code
        already follows.
    """
    head = str(reason or "").strip()
    for prefix in ("Skipped: ", "skipped: "):
        if head.startswith(prefix):
            head = head[len(prefix):]
    token = head.split(":", 1)[0].strip()
    return token if token.startswith("QC_") else ""


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


def result_lines(
    *,
    passed: int,
    failed: int,
    skips: list[tuple[str, str]],
    priority: str = "",
    engine: str = "",
    preconditions_skipped: int = 0,
) -> list[str]:
    """Return a band's result as a header and one labelled fact per line.

    **One fact per line, each labelled**, so a reader finds a number without
    parsing a sentence and a tool finds it without a regex over prose. The
    project owner's instruction of 2026-10-09: separate lines are easier for an
    analyser to find and parse, and a header saying which band and which engine
    is what makes a line attributable at all.

    ```
    Test results for Band P1 on claude
    total: 11
    executed: 7
    passed: 7
    failed: 0
    skipped: 4
    skip 1 of 1: 4 QC_HARNESS_FIXTURE_MISSING, no recorded response for this engine
    execution pass: 100.0% (7 of 7)
    total pass: 63.6% (7 of 11)
    ```

    **All five counts, always, a zero included.** pytest omits an empty
    category, so its line cannot answer "how many were selected" or "were any
    skipped"; this one always can.

    Design: ``cmn_verdict_and_cli.md`` sections 7.11.2 and 7.11.3.

    Args:
        passed (int): Cases that passed.
        failed (int): Cases that failed.
        skips (list): One ``(case, reason)`` pair per skipped case, so each
            skip is reported on its own line against the case it belongs to.
        priority (str): The ``--priority`` value, for the header.
        engine (str): The engine measured, for the header. **Absent is
            ordinary**: a precondition run measures no engine and the header
            says so by leaving it out rather than by naming a default.
        preconditions_skipped (int): How many skips were ungraded
            preconditions, named apart because no cause excuses one.

    Returns:
        list[str]: The header and the facts. **An empty selection yields
        nothing rather than a row of zeroes**, because zeroes read as a clean
        result.
    """
    skipped = len(skips)
    selected = passed + failed + skipped
    if not selected:
        return []

    executed = passed + failed
    # LOWERCASED WHERE IT IS NOT A BAND NAME. "Band P1" is a name and keeps
    # its capital; "Whole selection" is a description and reads as prose here.
    subject = band_label(priority)
    if not subject.startswith("Band"):
        subject = f"the {subject[0].lower()}{subject[1:]}"
    heading = f"Test results for {subject}"
    if engine:
        heading += f" on {engine}"

    lines = [
        heading,
        f"total: {selected}",
        f"executed: {executed}",
        f"passed: {passed}",
        f"failed: {failed}",
        f"skipped: {skipped}",
    ]
    required = max(0, min(preconditions_skipped, skipped))
    if required:
        lines.append(f"preconditions skipped: {required}, so the run exits 3")
    lines.extend(skip_detail_lines(skips))
    lines.append(f"execution pass: {_stated(passed, executed)}")
    lines.append(f"total pass: {_stated(passed, selected)}")
    return lines


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


def skipped_cases_from(reports: list[object]) -> list[tuple[str, str]]:
    """Return one ``(case, reason)`` pair per skipped report.

    **The callable's name, not the whole node identifier.** The module and the
    class are in the identifier too, and a line carrying all three is wider
    than a terminal; the announcement at setup already gave the full path
    (`harness_test_taxonomy.md` section 8.3.1).

    Args:
        reports (list): The skipped reports.

    Returns:
        list: One pair per report, in report order.
    """
    return [
        (str(getattr(report, "nodeid", "")).rsplit("::", 1)[-1], reason)
        for report, reason in zip(reports, skip_reasons_from(reports))
    ]


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
            one ``(case, reason)`` pair per skip. **The length is what this
            reads**, so the pair shape costs it nothing and keeps one input
            type across every caller.

    Returns:
        list[str]: Markdown lines, empty when nothing was measured at all.
    """
    rows: list[str] = []
    totals = [0, 0, 0, 0]
    blocking_failures = 0

    for priority, passed, failed, skips in measured:
        skipped = len(skips)
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
