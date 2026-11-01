# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The sources a traceability check compares a matrix against.

Created: 2026-11-01
Last updated: 2026-11-01

This file contains ``plan_requirements``, which returns the requirement
identifiers a test plan states, and ``collected_test_names``, which returns
every test callable a suite defines. Both read a repository other than the
matrix under check.

``cmn.traceability`` runs the checks and this supplies their second input, so a
check runs against a shipped matrix rather than against data derived from it.
A caller passing the matrix its own rows in place of these establishes only
that the matrix is self-consistent, which is the defect
``cmn_verdict_and_cli.md`` section 10.11 records.

Specified by ``docs/design/cmn_verdict_and_cli.md`` section 6.0.2.
"""

import ast
import re
from pathlib import Path
from typing import Final

# A requirement identifier, in either repository's register.
_REQUIREMENT: Final[re.Pattern[str]] = re.compile(r"MQC_REQ_[A-Z]{3}_[A-Z]{2,4}_\d{4}")

# A test callable, as pytest.ini and .pylintrc both define one.
_TEST_CALLABLE: Final[re.Pattern[str]] = re.compile(
    r"^MQC_([A-Z]{3})_([A-Z]{3,5})_(\d{6})_([a-z0-9_]{3,})$"
)


def plan_requirements(plan: Path, scope: str = "") -> set[str]:
    """Return every requirement identifier a test plan states.

    Args:
        plan (Path): The test plan to read.
        scope (str): A prefix to keep, such as ``MQC_REQ_HAR_``. Empty keeps
            every identifier, which is what a plan stating one register wants.

    Returns:
        set[str]: The identifiers found, deduplicated. A plan naming a
        requirement several times states it once.

    Raises:
        FileNotFoundError: If the plan is not there, because an empty set would
            read as a plan declaring nothing and pass every check silently.
    """
    stated = set(_REQUIREMENT.findall(plan.read_text(encoding="utf-8")))
    return {entry for entry in stated if entry.startswith(scope)}


def collected_test_names(tests_root: Path) -> set[str]:
    """Return every test callable the suite under a root defines.

    **Parsed, not matched.** A ``def MQC_...`` inside a string literal is data,
    and this project embeds two deliberately: a traceability case exercising a
    stale reference, and a fixture sub-suite run in a subprocess. A regex
    cannot tell either from a definition.

    A module that will not parse yields nothing here and fails its own
    collection separately, which keeps one defect from being reported as two.

    Args:
        tests_root (Path): The directory holding the suite.

    Returns:
        set[str]: Each callable's full name, as a matrix row names it.
    """
    found: set[str] = set()
    for module in sorted(tests_root.rglob("*.py")):
        try:
            tree = ast.parse(module.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if _TEST_CALLABLE.match(node.name) is not None:
                found.add(node.name)
    return found
