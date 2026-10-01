# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Judge a consumer's graded replay by taxonomy family, not by failure count.

Specified by ``docs/design/ci_pipeline.md`` section 3B.3.

**A model finding must not fail this job.** A harness regression that went red
because the model under test overstates a figure would be reporting the wrong
subject, permanently, for something no harness change can fix. That is how a
signal stops being read.

**Our codes fail it.** A ``QC_HARNESS_*`` message, or an ``error`` rather than a
failure, means the harness change broke the consumer, which is the only question
this job asks. `framework-rules.md` section 4 used as a gate rather than as a
label: the families split by what the code asserts about.

**Why it exists.** Three harness defects reached the case repository on
2026-09-28 and two of them broke the graded path, which the regression did not
run. Both were found when the consumer's own gate went red after a later push,
attributing the failure to whoever pushed the consumer rather than to the change
that caused it.
"""

import argparse
import logging
import re
from pathlib import Path
from typing import Final, Optional
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

_ENCODING: Final[str] = "utf-8"

# Only our own family turns this red. `QC_LLM_*`, `QC_SEC_*` and `QC_DATA_*` all
# assert about something other than the harness.
_OURS: Final[re.Pattern[str]] = re.compile(r"QC_HARNESS_[A-Z_]+")

# The one harness code that is not a harness fault here. A dependent skipped
# because a model finding failed its foundation is the cascade working, and the
# finding itself belongs to the consumer's own gate.
_CASCADE: Final[str] = "QC_HARNESS_DEPENDENCY_UNMET"

_EXIT_GREEN: Final[int] = 0
_EXIT_OURS: Final[int] = 1
_EXIT_REFUSED: Final[int] = 4


def harness_faults(report: Path) -> list[str]:
    """Return every harness-attributable problem a graded replay reported.

    Args:
        report (Path): The consumer's JUnit XML.

    Returns:
        list[str]: One message per fault, empty when nothing is ours.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the report is absent
            or will not parse. **A regression that produced no report verified
            nothing**, and an empty finding list would read as a pass.
    """
    if not report.is_file():
        raise ValueError(f"QC_HARNESS_PARSER_ERROR: no consumer report at {report}")
    try:
        tree = ElementTree.parse(report)
    except ElementTree.ParseError as error:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: consumer report at {report} will not parse"
        ) from error

    faults: list[str] = []
    for case in tree.iter("testcase"):
        name = case.get("name", "(unnamed)")
        for problem in case.iter("error"):
            faults.append(
                f"{name} reported an error rather than a failure: "
                f"{(problem.get('message') or '').strip()[:160]}"
            )
        for problem in case.iter("failure"):
            message = (problem.get("message") or "") + (problem.text or "")
            found = _OURS.findall(message)
            ours = [code for code in found if code != _CASCADE]
            if ours:
                faults.append(f"{name} failed with {', '.join(sorted(set(ours)))}")
    return faults


def main(argv: Optional[list[str]] = None) -> int:
    """Report whether a consumer's graded replay blames this harness.

    Args:
        argv (Optional[list]): Arguments, for calling in-process from a case.

    Returns:
        int: ``0`` nothing of ours, ``1`` our fault, ``4`` refused.
    """
    parser = argparse.ArgumentParser(
        prog="consumer-regression",
        description="Fail only on harness-attributable outcomes in a consumer run",
    )
    parser.add_argument("report", type=Path, help="The consumer's graded JUnit XML")
    parsed = parser.parse_args(argv)

    try:
        faults = harness_faults(parsed.report)
    except ValueError as error:
        logger.error("%s", error)
        return _EXIT_REFUSED

    if faults:
        for fault in faults:
            logger.error("%s", fault)
        logger.error(
            "%d harness-attributable outcome(s): this change broke the consumer",
            len(faults),
        )
        return _EXIT_OURS

    logger.info(
        "no harness-attributable outcome in the consumer's graded replay; any "
        "failures there are findings about the model and belong to its own gate"
    )
    return _EXIT_GREEN


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
