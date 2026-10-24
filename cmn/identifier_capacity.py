# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The identifier space: what a six-digit number means, and how much is spent.

Created: 2026-10-18
Last updated: 2026-10-24

This file contains ``PARTITIONS`` and ``partition_of``, the ranges declared
with a start and an end rather than derived from digit positions;
``identifier_block_problems``, which reports a callable whose digits or
whose partition contradict its tokens; ``assigned_identifiers``, every
identifier the inventory tables assign, live or retired; ``select_blocks``,
those whose layer and module a repository owns; and ``capacity_warnings``,
which reports a category, block or partition at its warning threshold.

Precondition cases in both repositories call these over their own inventories.
The capacity lines are raised as warnings rather than failures, so an author
learns a category is filling before it runs out of numbers, and a contradicted
identifier fails the unit layer.

**Two ways to read a number, and the record wins.** In domain 1 the digits are
positional: a category is the first four digits and holds 100 identifiers, a
block is the first three, a module in one layer, and holds 1,000. A declared
partition carries neither, so its record states the layer and the module.
Retired identifiers are never reused, so a struck inventory row is assigned
exactly as a live one is.

Design: ``docs/design/harness_test_taxonomy.md`` sections 3.2.1.4, 3.2.1.5 and
11.9.6.
"""

import ast
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Iterable, Optional

from cmn.code_standards import walked_nodes

# AN INVENTORY ROW, LIVE OR STRUCK THROUGH. A retired identifier keeps its
# slot, so unlike the binding checks this reader matches both.
_ASSIGNED_ROW: Final[re.Pattern[str]] = re.compile(r"^\|\s*(?:~~)?`(\d{6})`(?:~~)?\s*\|")

# THE THRESHOLDS, section 11.9.6: ten numbers left in a category, two
# categories' worth left in a block, a tenth of a partition left.
CATEGORY_WARNING: Final[int] = 90
BLOCK_WARNING: Final[int] = 800
_PARTITION_WARNING_IN_TENTHS: Final[int] = 9


@dataclass(frozen=True)
class Partition:
    """A range of identifiers declared with a start and an end.

    Attributes:
        start (int): The first identifier in the range.
        end (int): The last identifier in the range.
        layer (str): The layer token every identifier here carries.
        module (str): The module token every identifier here carries.
        subject (str): What the partition holds.
        continues (str): The category it took over from.
        allocated (str): The day it was allocated, in ISO form.
    """

    start: int
    end: int
    layer: str
    module: str
    subject: str
    continues: str
    allocated: str

    @property
    def width(self) -> int:
        """Return how many identifiers the range holds.

        Returns:
            int: The count, inclusive of both bounds.
        """
        return self.end - self.start + 1

    def holds(self, identifier: str) -> bool:
        """Return whether this range holds an identifier.

        Args:
            identifier (str): Six digits.

        Returns:
            bool: True when the number falls between the bounds.
        """
        return self.start <= int(identifier) <= self.end


# THE DECLARED PARTITIONS, which section 3.2.1.5 tabulates and `112804`
# compares against this. A subject that fills its category continues here
# rather than in the next free category, of which `CMN`/`UNI` has none.
#
# CUT FROM `400000` AND NOT `200000`, because section 3.2.1.0 promised `2` to
# performance and `3` to networking on 2026-10-02 and said why in the same
# sentence: recording a reserved domain is a commitment not to spend its
# numbers on something else.
PARTITIONS: Final[tuple[Partition, ...]] = (
    Partition(
        start=400000,
        end=409999,
        layer="UNI",
        module="CMN",
        subject="governance and traceability",
        continues="1123xx",
        allocated="2026-10-22",
    ),
    Partition(
        start=410000,
        end=419999,
        layer="UNI",
        module="CMN",
        subject="the mutation audit and its declarations",
        continues="1123xx, then 1124xx",
        allocated="2026-10-23",
    ),
    Partition(
        start=420000,
        end=429999,
        layer="UNI",
        module="CMN",
        subject="the grouping tree a readiness view is read from",
        continues="nothing, the first subject to begin in a partition",
        allocated="2026-10-24",
    ),
    Partition(
        start=430000,
        end=439999,
        layer="UNI",
        module="CAS",
        subject="the grouping tree in the case repository",
        continues="nothing, a subject beginning now takes a partition",
        allocated="2026-10-24",
    ),
)


def partition_of(identifier: str) -> Optional[Partition]:
    """Return the declared partition holding an identifier, if one does.

    Args:
        identifier (str): Six digits.

    Returns:
        Optional[Partition]: The partition, or ``None`` where the identifier is
        positional and its digits carry the layer and module themselves.
    """
    for partition in PARTITIONS:
        if partition.holds(identifier):
            return partition
    return None


# THE POSITIONAL SCHEME, as `harness_test_taxonomy.md` section 3.2.1 states it.
# Held here rather than in the document alone, because a scheme nothing reads is
# the state the hundred-slot partition was in when it broke in three places.
_LAYER_DIGIT: Final[dict[str, str]] = {
    "UNI": "1", "SYS": "2", "EVAL": "3", "TOOL": "4", "SEC": "5", "MUT": "6",
}
_MODULE_DIGIT: Final[dict[str, str]] = {
    "ING": "1", "CMN": "2", "EXE": "3", "EVL": "4", "CAS": "5",
}

_IDENTIFIED = re.compile(r"^MQC_([A-Z]{3})_([A-Z]{3,5})_(\d+)_[a-z0-9_]+$")


def identifier_block_problems(root: Path) -> list[str]:
    """Report every collected callable whose digits contradict its tokens.

    An identifier is six positional digits: the domain, the layer, the module,
    the category and the case. This reads the layer and module tokens from the
    name and checks the digits that encode them.

    **A declared partition carries neither digit, so its record is checked
    instead.** An identifier inside one is compared against the layer and
    module that partition declares, which is the same comparison between two
    halves of one name.

    **It compares two halves of one name**, which is what makes it different
    from the duplicate-binding check: two modules occupying one block are two
    distinct identifiers, so counting bindings cannot see it.

    Design: ``harness_test_taxonomy.md`` sections 3.2.1.4 and 3.2.1.5.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per disagreement. Empty when every identifier's
        digits, or the partition holding it, say what its tokens say.
    """
    problems: list[str] = []
    for source in sorted((root / "tests").rglob("*.py")):
        if "__pycache__" in source.parts:
            continue
        for node in walked_nodes(source):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            matched = _IDENTIFIED.match(node.name)
            if matched is None:
                continue
            module, layer, digits = matched.groups()
            where = f"{source.relative_to(root).as_posix()}::{node.name}"
            if len(digits) != 6:
                problems.append(
                    f"{where} carries {len(digits)} digits, and the scheme is six"
                )
                continue
            problems.extend(_token_disagreements(where, layer, module, digits))
    return problems


def _token_disagreements(
    where: str, layer: str, module: str, digits: str
) -> list[str]:
    """Return every disagreement between an identifier's tokens and its number.

    Args:
        where (str): The file and callable, for the message.
        layer (str): The layer token read from the name.
        module (str): The module token read from the name.
        digits (str): The six digits.

    Returns:
        list[str]: One entry per disagreement, empty where they agree.
    """
    held = partition_of(digits)
    if held is not None:
        if (held.layer, held.module) == (layer, module):
            return []
        return [
            f"{where} sits in the partition {held.start} to {held.end}, "
            f"which holds {held.module} and {held.layer}"
        ]
    problems: list[str] = []
    expected_layer = _LAYER_DIGIT.get(layer)
    expected_module = _MODULE_DIGIT.get(module)
    if expected_layer is not None and digits[1] != expected_layer:
        problems.append(
            f"{where} says layer {layer}, whose digit is "
            f"{expected_layer}, and carries {digits[1]}"
        )
    if expected_module is not None and digits[2] != expected_module:
        problems.append(
            f"{where} says module {module}, whose digit is "
            f"{expected_module}, and carries {digits[2]}"
        )
    return problems


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
        ``modules``, and those a declared partition assigns to a layer and
        module this repository owns.
    """
    kept: set[str] = set()
    for identifier in identifiers:
        held = partition_of(identifier)
        if held is None:
            if identifier[1] in layers and identifier[2] in modules:
                kept.add(identifier)
            continue
        # A DECLARED PARTITION CARRIES NEITHER DIGIT, so the record says whose
        # it is. Reading the digits here would drop every such identifier out
        # of both repositories' counts and leave the partition unwatched.
        if (_LAYER_DIGIT.get(held.layer, "") in layers
                and _MODULE_DIGIT.get(held.module, "") in modules):
            kept.add(identifier)
    return kept


def capacity_warnings(identifiers: Iterable[str]) -> list[str]:
    """Return one line per category or block at its warning threshold.

    Args:
        identifiers (Iterable[str]): The assigned six-digit identifiers.

    Returns:
        list[str]: Categories holding ``CATEGORY_WARNING`` or more, then
        blocks holding more than ``BLOCK_WARNING``, then declared partitions
        holding nine tenths of their own width, each sorted, each line naming
        the count and what is left.
    """
    unique = set(identifiers)
    # A DECLARED PARTITION IS COUNTED AS ITSELF. Its first four digits are not
    # a category and counting them as one would compare 10,000 numbers against
    # a threshold written for 100.
    positional = {one for one in unique if partition_of(one) is None}
    categories = Counter(identifier[:4] for identifier in positional)
    blocks = Counter(identifier[:3] for identifier in positional)
    lines = [
        f"category {prefix}xx holds {count} of 100 identifiers, {100 - count} left; "
        f"choose the next category for its subject, or declare a partition "
        f"where the block has none free"
        for prefix, count in sorted(categories.items()) if count >= CATEGORY_WARNING
    ]
    lines += [
        f"block {prefix}xxx holds {count} of 1000 identifiers, {1000 - count} left; "
        f"an allocation decision is due"
        for prefix, count in sorted(blocks.items()) if count > BLOCK_WARNING
    ]
    for partition in PARTITIONS:
        count = len([one for one in unique if partition.holds(one)])
        threshold = partition.width * _PARTITION_WARNING_IN_TENTHS // 10
        if count >= threshold:
            lines.append(
                f"partition {partition.start} to {partition.end} holds {count} "
                f"of {partition.width} identifiers, {partition.width - count} "
                f"left; declare the next partition for {partition.subject}"
            )
    return lines
