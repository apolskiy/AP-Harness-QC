# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The reports the failure lister's precondition reads, and the helper writing them.

Created: 2026-10-29
Last updated: 2026-10-29

This file contains ``MIXED_REPORT``, a JUnit report carrying a passing case, a
failing one, an erroring one and one carrying both; ``CLEAN_REPORT``, one
carrying a passing case alone; and ``written``, which puts either under a
directory the caller owns and returns the path.

``mqc_uni_junit_outcomes.py`` imports all three. It sits in a sibling module
because collection does not reach this file, and `MQC_CMN_UNI_112328` reports
support code defined inside a collected case module.

Specified by ``docs/design/cmn_verdict_and_cli.md`` section 7.12.
"""

from pathlib import Path
from typing import Final

_ENCODING: Final[str] = "utf-8"

# THE PLANTED IDENTIFIERS ARE 999xxx, outside every declared partition, so a
# registry check reading this corpus cannot mistake one for a real case.
MIXED_REPORT: Final[str] = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="4">
    <testcase classname="pkg.mod.TestOne" name="MQC_CMN_UNI_999001_passes" />
    <testcase classname="pkg.mod.TestOne" name="MQC_CMN_UNI_999002_fails">
      <failure message="QC_LLM_PLANTED">planted failure</failure>
    </testcase>
    <testcase classname="pkg.mod.TestOne" name="MQC_CMN_UNI_999003_breaks">
      <error message="QC_HARNESS_PLANTED">planted error</error>
    </testcase>
    <testcase classname="pkg.mod.TestOne" name="MQC_CMN_UNI_999004_does_both">
      <failure message="QC_LLM_PLANTED">planted failure</failure>
      <error message="QC_HARNESS_PLANTED">planted error in teardown</error>
    </testcase>
  </testsuite>
</testsuites>
"""

CLEAN_REPORT: Final[str] = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="1">
    <testcase classname="pkg.mod.TestOne" name="MQC_CMN_UNI_999001_passes" />
  </testsuite>
</testsuites>
"""


def written(folder: Path, name: str, body: str) -> Path:
    """Write one report under a directory the caller owns and return its path.

    Args:
        folder (Path): The directory to write into, which is the case's own
            ``tmp_path`` rather than anything in the repository
            (`code-style.md` section 8.0).
        name (str): The file name to give it.
        body (str): The report's contents.

    Returns:
        Path: Where it was written.
    """
    path = folder / name
    path.write_text(body, encoding=_ENCODING, newline="\n")
    return path
