# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Registry case coverage check, whether every registry member has a case of its own.

Created: 2026-10-16
Last updated: 2026-10-21

This file contains ``covered_arguments``, which reads from a test module's
syntax the first argument each ``MQC_`` case passes to a shared helper, and
``uncovered_members``, which reports the registry members no case passes.

A case split from a parametrisation over a registry passes its member to that
helper, so precondition cases call ``uncovered_members`` with the module and the
registry, and a member added without a case of its own fails the unit layer.

Design: ``harness_test_taxonomy.md`` section 1.1.
"""

import ast
import logging
import re
from pathlib import Path
from typing import Any, Final, Iterable

logger = logging.getLogger(__name__)

_CASE: Final[re.Pattern[str]] = re.compile(r"^MQC_[A-Z]{3}_[A-Z]{3,5}_\d{6}_")


def covered_arguments(module: Path, helper: str) -> set[Any]:
    """Return the first argument each ``MQC_`` case passes to ``self.<helper>``.

    Args:
        module (Path): The test module to read.
        helper (str): The private helper the split cases call.

    Returns:
        set: Each constant first argument, from calls inside case methods only.
        A call from the helper itself or from a non-case method covers nothing.
    """
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    covered: set[Any] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not _CASE.match(node.name):
            continue
        for call in ast.walk(node):
            if _calls_helper(call, helper) and isinstance(call.args[0], ast.Constant):
                covered.add(call.args[0].value)
    return covered


def _calls_helper(node: ast.AST, helper: str) -> bool:
    """Return whether a node is ``self.<helper>(...)`` with at least one argument.

    Args:
        node (ast.AST): Any node of the case's body.
        helper (str): The helper's name.

    Returns:
        bool: True for a positional call on ``self`` to that helper.
    """
    if not isinstance(node, ast.Call) or not node.args:
        return False
    target = node.func
    return (isinstance(target, ast.Attribute) and target.attr == helper
            and isinstance(target.value, ast.Name) and target.value.id == "self")


def uncovered_members(module: Path, helper: str, members: Iterable[Any]) -> list[Any]:
    """Return every registry member no case in the module passes to the helper.

    Args:
        module (Path): The test module holding the split cases.
        helper (str): The helper each case calls with its member first.
        members (Iterable): The registry's members.

    Returns:
        list: The uncovered members, sorted by their text.
    """
    covered = covered_arguments(module, helper)
    missing = sorted((member for member in members if member not in covered), key=str)
    if missing:
        logger.warning("%s: %d registry member(s) with no case: %s",
                       module.name, len(missing), missing)
    return missing
