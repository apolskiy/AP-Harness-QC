# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Reading the dataclass decorators, with the accumulator declaration ignored.

**A sibling module collection does not reach**, per `MQC_CMN_UNI_112328`: a
collected module holds cases and nothing else.

This exists so `MQC_CMN_UNI_112359` can assert that the declaration in
`cmn.code_standards` names exactly the records that need it. The checker
applies the declaration, so a case calling the checker cannot tell a correct
declaration from one that has outlived its reason.
"""

import ast
from pathlib import Path

from cmn.code_standards import (
    _declares_frozen,
    _is_dataclass_decorator,
    python_sources,
)


def unfrozen_class_names(root: Path) -> set[str]:
    """Return every production dataclass that is not frozen, declared or not.

    Args:
        root (Path): The repository root.

    Returns:
        set[str]: The class names.
    """
    found: set[str] = set()
    for source in python_sources(root):
        if "tests" in source.parts:
            continue
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.ClassDef):
                continue
            decorators = [entry for entry in node.decorator_list
                          if _is_dataclass_decorator(entry)]
            if decorators and not any(_declares_frozen(entry)
                                      for entry in decorators):
                found.add(node.name)
    return found
