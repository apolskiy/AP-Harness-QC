# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The one clock the project reads, which is UTC, and the check that it is the only one.

Created: 2026-10-28
Last updated: 2026-10-30

This file contains ``project_today``, the date every tool, check and case means
by today, and ``local_clock_reads``, which reports a module reading a clock of
its own. Both repositories call the first wherever they need a date and the
second with their own root, so a second clock fails the unit layer rather than
producing a date that differs by one for part of every day.

**UTC, at the project owner's ruling of 2026-10-28**, after
``refresh_file_dates.py`` stamped one date and ``CHANGELOG.md`` declared
another for the same change. The reasoning is in ``code-style.md`` section 8.3;
in short, every durable record this project keeps is already UTC and a
developer's offset is an environment difference like the default encoding.

**Nothing here caches.** ``project_today`` reads the clock on every call, so a
process running across midnight gives the later date to whatever asks next,
which is what a caller stamping a file wants.
"""

import ast
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Final

# THE CALLS THAT READ WHEREVER THE PROCESS HAPPENS TO SIT. `date.today` and
# `datetime.today` have no zone at all, and `datetime.now` has one only when it
# is given an argument, so the first two are reported wherever they appear and
# the third only when it is called bare.
_LOCAL_CALLS: Final[tuple[str, ...]] = ("date.today", "datetime.today")
_ZONELESS_NOW: Final[str] = "datetime.now"

# THIS MODULE, which reads the clock because that is its subject, and the
# verdict module's own ban, which names these calls as strings to forbid them
# rather than making them (`cmn_verdict_and_cli.md` section 4.2).
_CLOCK_MODULE: Final[str] = "project_clock.py"
_DIRECTORIES: Final[tuple[str, ...]] = (
    "cmn",
    "ingestion",
    "execution",
    "evaluation",
    "tools",
    "tests",
)

def project_today() -> date:
    """Return the date the project means by today, which is the UTC date.

    Every caller needing today's date calls this rather than ``date.today``,
    which returns wherever the process happens to sit. The two differ for part
    of every day, and for seven hours a day in the Pacific zone the local date
    is the one before.

    Design: ``code-style.md`` section 8.3.

    Returns:
        date: Today in UTC.
    """
    return datetime.now(timezone.utc).date()


def local_clock_reads(root: Path) -> list[str]:
    """Report every module reading a clock instead of calling the project's.

    Reports a call to ``date.today`` or ``datetime.today`` anywhere, and a call
    to ``datetime.now`` taking no argument, which is the zoneless form. A
    ``datetime.now`` given a zone is reported by nothing, being an explicit
    choice rather than an accident of where a process runs.

    **Parsed, not matched.** A module naming one of these calls in a docstring
    or in a string it checks for is not making the call, and this project
    already holds one such module.

    Design: ``code-style.md`` section 8.3.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per call, naming the file, the line and the call.
    """
    found: list[str] = []
    for directory in _DIRECTORIES:
        for source in sorted((root / directory).rglob("*.py")):
            if source.name == _CLOCK_MODULE:
                continue
            found.extend(_clock_calls(source, root))
    return found


def _clock_calls(source: Path, root: Path) -> list[str]:
    """Return every local clock read one module makes.

    Args:
        source (Path): The module to read.
        root (Path): The repository root, for naming the file relatively.

    Returns:
        list[str]: One entry per call, naming the line and the call.
    """
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"))
    except SyntaxError as error:
        return [f"{source.name}: will not parse, {error}"]
    name = source.relative_to(root).as_posix()
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called = _dotted(node.func)
        if called in _LOCAL_CALLS:
            found.append(
                f"{name}:{node.lineno} calls {called}, which returns wherever "
                f"the process sits; call cmn.project_clock.project_today "
                f"instead (code-style.md section 8.3)"
            )
        elif called == _ZONELESS_NOW and not node.args and not node.keywords:
            found.append(
                f"{name}:{node.lineno} calls {called} with no zone, which "
                f"returns wherever the process sits; call "
                f"cmn.project_clock.project_today, or pass a zone where a "
                f"timestamp is wanted (code-style.md section 8.3)"
            )
    return found


def _dotted(node: ast.expr) -> str:
    """Return a called name as written, for the one and two part forms.

    Args:
        node (ast.expr): The ``func`` of a call node.

    Returns:
        str: The dotted name, or empty where it is neither form.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}"
    return ""
