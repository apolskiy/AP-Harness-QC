# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Reading a normative Markdown table, for the cases comparing a registry with it.

Specified in ``docs/design/harness_test_taxonomy.md`` sections 3, 4.1.0, 6.5
and 7.4.0.
"""

import re
from pathlib import Path
from typing import Final

from cmn.layers import (
    layer_properties,
    outcome_properties,
    registered_layers,
    registered_outcomes,
)
from cmn.registries import registered_codes, unranked_codes

ROOT: Final[Path] = Path(__file__).resolve().parents[2]
TAXONOMY: Final[Path] = ROOT / "docs" / "design" / "harness_test_taxonomy.md"

_ROW: Final[re.Pattern[str]] = re.compile(r"^\|(.+)\|\s*$")
_RULE: Final[re.Pattern[str]] = re.compile(r"^\|[\s|:-]+\|\s*$")


def table_after(path: Path, heading: str) -> list[dict[str, str]]:
    """Return the first table after a heading, one mapping per row.

    Args:
        path (Path): The Markdown document.
        heading (str): The heading text, matched at the start of a heading
            line after its hashes.

    Returns:
        list[dict[str, str]]: Each row keyed by its column header, cells
        stripped. Empty when the heading or its table is absent.

    Raises:
        ValueError: When the heading appears more than once, since the
            comparison would then read whichever came first.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [
        index for index, line in enumerate(lines)
        if line.startswith("#") and line.lstrip("#").strip().startswith(heading)
    ]
    if len(starts) > 1:
        raise ValueError(f"heading {heading!r} appears {len(starts)} times in {path.name}")
    if not starts:
        return []
    header: list[str] = []
    rows: list[dict[str, str]] = []
    for line in lines[starts[0] + 1:]:
        if line.startswith("#"):
            break
        if not _ROW.match(line):
            if header:
                break
            continue
        if _RULE.match(line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not header:
            header = cells
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def bare(cell: str) -> str:
    """Return a cell without Markdown emphasis or code marks.

    Args:
        cell (str): The cell as written.

    Returns:
        str: The text, with backticks and asterisks removed.
    """
    return cell.replace("`", "").replace("*", "").strip()


def yes(cell: str) -> bool:
    """Read a Yes or No cell, a qualifier after the first word allowed.

    Args:
        cell (str): The cell as written.

    Returns:
        bool: True when the cell begins Yes.

    Raises:
        ValueError: When the cell begins with neither, so a typo cannot read
            as No.
    """
    word = bare(cell).split(",")[0].split()[0].lower() if bare(cell) else ""
    if word not in {"yes", "no"}:
        raise ValueError(f"cell {cell!r} is neither Yes nor No")
    return word == "yes"


def ranked_codes() -> set[str]:
    """Return every finding code the harness ranks, read through public accessors.

    Returns:
        set[str]: Each registered model or security code not reported unranked.
    """
    unranked = unranked_codes()
    return {
        code for code in registered_codes()
        if code.startswith(("QC_LLM_", "QC_SEC_")) and code not in unranked
    }


_BLOCK: Final[re.Pattern[str]] = re.compile(r"(\d{6})\s+to\s+(\d{6})")


def layer_table_problems() -> list[str]:
    """Return every way the layer registry disagrees with taxonomy section 3.

    Returns:
        list[str]: One entry per differing layer, and per layer in only one.
    """
    rows = table_after(TAXONOMY, "3. Layer Registry")
    if not rows:
        return ["the layer table was not found, so nothing is compared"]
    problems: list[str] = []
    tabled: set[str] = set()
    for row in rows:
        token = bare(row["Layer"]).split("_")[1]
        tabled.add(token)
        block = _BLOCK.search(row["ID block"])
        expected = (
            bare(row["Marker"]), yes(row["Graded"]), yes(row["Distribution exempt"]),
            yes(row["Blocking"]), (int(block.group(1)), int(block.group(2))) if block else None,
        )
        try:
            code = layer_properties(token)
        except (KeyError, ValueError):
            problems.append(f"layer {token} is in the table and not registered")
            continue
        actual = (code.marker, code.graded, code.distribution_exempt, code.blocking,
                  tuple(code.id_block))
        if actual != expected:
            problems.append(f"layer {token}: code {actual}, table {expected}")
    problems.extend(f"layer {token} is registered and not in the table"
                    for token in sorted(set(registered_layers()) - tabled))
    return problems


def outcome_table_problems() -> list[str]:
    """Return every way the outcome registry disagrees with taxonomy section 7.4.0.

    Returns:
        list[str]: One entry per differing outcome, and per outcome in only one.
    """
    rows = table_after(TAXONOMY, "7.4.0 How each outcome is counted")
    if not rows:
        return ["the outcome table was not found, so nothing is compared"]
    problems: list[str] = []
    named: set[str] = set()
    for row in rows:
        outcome = bare(row["Outcome"])
        named.add(outcome)
        expected = (yes(row["In the pass-rate denominator"]), yes(row["Counts as a pass"]),
                    yes(row["In the skip-rate numerator"]),
                    yes(row["In the distribution denominator"]))
        code = outcome_properties(outcome)
        actual = (code.counts_in_pass_rate, code.is_pass, code.counts_in_skip_rate,
                  code.counts_in_distribution)
        if actual != expected:
            problems.append(f"outcome {outcome}: code {actual}, table {expected}")
    problems.extend(f"outcome {outcome} is registered and not in the table"
                    for outcome in sorted(set(registered_outcomes()) - named))
    return problems
