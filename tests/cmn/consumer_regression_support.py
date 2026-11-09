# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The testcase elements the consumer regression's cases compare, and their writer.

Created: 2026-11-09
Last updated: 2026-11-09

This file contains ``PASSED``, ``PASSW``, ``FAILED`` and ``SKIPPED``, JUnit
testcase templates taking a ``name`` (and ``FAILED`` a ``code``); and
``junit_report``, which writes a report holding rendered testcases and returns
its path.

``mqc_uni_consumer_regression.py`` imports them. It sits in a sibling module
because collection does not reach this file, and `MQC_CMN_UNI_112328` reports
support code defined inside a collected case module.

Specified by ``docs/design/harness_ci_pipeline.md`` section 3B.3.1.
"""

from pathlib import Path
from typing import Final

PASSED: Final[str] = '<testcase classname="c" name="{name}"/>'
PASSW: Final[str] = (
    '<testcase classname="c" name="{name}"><properties>'
    '<property name="mqc_outcome" value="passw"/>'
    '<property name="mqc_warning_code" value="QC_LLM_MATCH_MISCOMPUTED"/>'
    '</properties></testcase>')
FAILED: Final[str] = ('<testcase classname="c" name="{name}"><failure message="'
                      'A_X ({code}): pattern found"/></testcase>')
SKIPPED: Final[str] = (
    '<testcase classname="c" name="{name}"><skipped message="'
    'QC_HARNESS_DEPENDENCY_UNMET: foundational case did not hold"/></testcase>')


def junit_report(path: Path, *cases: str) -> Path:
    """Write a JUnit report holding the given testcase elements.

    Args:
        path (Path): Where to write it.
        *cases (str): Testcase elements, already rendered.

    Returns:
        Path: ``path``.
    """
    path.write_text(f"<testsuites><testsuite>{''.join(cases)}</testsuite></testsuites>",
                    encoding="utf-8")
    return path
