# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Identifier capacity check, how full each case identifier category and block is.

Created: 2026-10-18
Last updated: 2026-10-21

This file contains ``assigned_identifiers``, which reads every identifier the
inventory tables assign, live or retired; ``select_blocks``, which keeps those
whose layer and module digits a repository owns; and ``capacity_warnings``,
which reports a category or block at its warning threshold.

Precondition cases in both repositories call these over their own inventories
and raise each line as a warning rather than a failure, so an author learns a
category is filling before it runs out of numbers.

A category is the first four digits and holds 100 identifiers; a block is the
first three, a module in one layer, and holds 1,000. Retired identifiers are
never reused, so a struck inventory row is assigned exactly as a live one is.

Design: ``docs/design/harness_test_taxonomy.md`` section 11.9.6.
"""

import re
from collections import Counter
from pathlib import Path
from typing import Final, Iterable

# AN INVENTORY ROW, LIVE OR STRUCK THROUGH. A retired identifier keeps its
# slot, so unlike the binding checks this reader matches both.
_ASSIGNED_ROW: Final[re.Pattern[str]] = re.compile(r"^\|\s*(?:~~)?`(\d{6})`(?:~~)?\s*\|")

# THE THRESHOLDS, section 11.9.6: ten numbers left in a category, two
# categories' worth left in a block.
CATEGORY_WARNING: Final[int] = 90
BLOCK_WARNING: Final[int] = 800


def assigned_identifiers(documents: Iterable[Path]) -> set[str]:
    """Return every identifier an inventory row assigns, live or retired.

    Args:
        documents (Iterable[Path]): The documents holding inventory tables.

    Returns:
        set[str]: Six-digit identifiers, each once.
    """
    assigned: set[str] = set()
    for document in documents:
        for line in document.read_text(encoding="utf-8").splitlines():
            match = _ASSIGNED_ROW.match(line.strip())
            if match is not None:
                assigned.add(match.group(1))
    return assigned


def select_blocks(identifiers: Iterable[str], *, layers: str, modules: str) -> set[str]:
    """Return the identifiers whose layer and module digits a repository owns.

    Args:
        identifiers (Iterable[str]): Six-digit identifiers.
        layers (str): The layer digits owned, such as ``"12"``.
        modules (str): The module digits owned, such as ``"1234"``.

    Returns:
        set[str]: Those whose second digit is in ``layers`` and third in
        ``modules``.
    """
    return {
        identifier for identifier in identifiers
        if identifier[1] in layers and identifier[2] in modules
    }


def capacity_warnings(identifiers: Iterable[str]) -> list[str]:
    """Return one line per category or block at its warning threshold.

    Args:
        identifiers (Iterable[str]): The assigned six-digit identifiers.

    Returns:
        list[str]: Categories holding ``CATEGORY_WARNING`` or more, then
        blocks holding more than ``BLOCK_WARNING``, each sorted, each line
        naming the count and what is left.
    """
    unique = set(identifiers)
    categories = Counter(identifier[:4] for identifier in unique)
    blocks = Counter(identifier[:3] for identifier in unique)
    lines = [
        f"category {prefix}xx holds {count} of 100 identifiers, {100 - count} left; "
        f"choose the next category for its subject"
        for prefix, count in sorted(categories.items()) if count >= CATEGORY_WARNING
    ]
    lines += [
        f"block {prefix}xxx holds {count} of 1000 identifiers, {1000 - count} left; "
        f"an allocation decision is due"
        for prefix, count in sorted(blocks.items()) if count > BLOCK_WARNING
    ]
    return lines
