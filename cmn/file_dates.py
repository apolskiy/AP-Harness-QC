# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Reads, checks and writes the creation and update dates in every module docstring.

Created: 2026-10-21
Last updated: 2026-10-21

This file contains ``date_lines``, which reads the ``Created:`` and
``Last updated:`` lines a module docstring carries as its third and fourth
lines; ``file_date_problems``, which reports every file whose lines are missing,
malformed, misordered, in the future or stale; and ``stamped_source``, which
writes both lines into a source text. ``changed_files``, ``first_added`` and
``last_committed`` answer the three questions about git history the other
functions need.

**One implementation, called with each root.** ``MQC_CMN_UNI_112526`` and
``MQC_CAS_UNI_115773`` assert ``file_date_problems`` against their own
repository, and ``tools/refresh_file_dates.py`` uses ``stamped_source`` to keep
the dates current, so the check and the remedy cannot disagree about where the
lines sit.

**Staleness needs local edits to compare.** A file is stale when it differs from
its last commit and its ``Last updated`` is neither today nor after that commit.
Where git is absent or the root is no repository, that half reports nothing,
which is what a CI checkout with no local edits would report anyway.

**Today is a parameter**, never read from a clock here, so a case can put
today wherever it needs to.

Specified by ``.claude/rules/code-style.md`` section 3.1.2 and
``docs/design/cmn_verdict_and_cli.md`` section 10.39.
"""

import ast
import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Final, Optional

from cmn.code_standards import python_sources

CREATED: Final[str] = "Created: "
UPDATED: Final[str] = "Last updated: "

# THE LINES' PLACE IN THE DOCSTRING, counted from its first line: the purpose
# line, a blank line, then the two dates.
_CREATED_LINE: Final[int] = 2
_UPDATED_LINE: Final[int] = 3

_ISO_DATE: Final[re.Pattern] = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# BOUNDED, per `harness_test_taxonomy.md` section 14. A local history read in a
# minute is already pathological.
_GIT_TIMEOUT_SEC: Final[float] = 60.0


def _git(root: Path, arguments: list[str]) -> Optional[str]:
    """Return git's output for one command, or None where git cannot answer.

    Args:
        root (Path): The repository root to run in.
        arguments (list): The git arguments.

    Returns:
        Optional[str]: The standard output, or None when git is absent, the
        root is no repository, or the command failed.
    """
    try:
        completed = subprocess.run(
            ["git", *arguments],
            capture_output=True, text=True, encoding="utf-8", check=False,
            shell=False, cwd=str(root), stdin=subprocess.DEVNULL,
            timeout=_GIT_TIMEOUT_SEC,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout if completed.returncode == 0 else None


def changed_files(root: Path) -> Optional[set[str]]:
    """Return the tracked files that differ from the last commit.

    Args:
        root (Path): The repository root.

    Returns:
        Optional[set]: Paths relative to the root, with forward slashes, or None
        where there is no history to compare against.
    """
    listed = _git(root, ["diff", "--name-only", "HEAD", "--", "."])
    if listed is None:
        return None
    prefix = _git(root, ["rev-parse", "--show-prefix"]) or ""
    return {
        line.strip()[len(prefix.strip()):]
        for line in listed.splitlines()
        if line.strip().startswith(prefix.strip())
    }


def last_committed(root: Path, relative: str) -> str:
    """Return the date of the last commit that touched a file.

    Args:
        root (Path): The repository root.
        relative (str): The file, relative to the root.

    Returns:
        str: An ISO date, or empty where git records none.
    """
    found = _git(root, ["log", "-1", "--format=%cs", "--", relative])
    return (found or "").strip()


def first_added(root: Path, relative: str) -> str:
    """Return the date git first recorded a file, following renames.

    Args:
        root (Path): The repository root.
        relative (str): The file, relative to the root.

    Returns:
        str: An ISO date, or empty where git records none.
    """
    found = _git(root, ["log", "--follow", "--diff-filter=A", "--format=%cs", "--", relative])
    dates = (found or "").split()
    return dates[-1] if dates else ""


def date_lines(source: str) -> tuple[Optional[str], Optional[str]]:
    """Return the dates a module docstring's third and fourth lines carry.

    Args:
        source (str): The module's source text.

    Returns:
        tuple: The ``Created`` and ``Last updated`` values, each None where its
        line is absent from its place.
    """
    docstring = ast.get_docstring(ast.parse(source), clean=False) or ""
    lines = docstring.split("\n")

    def value(index: int, label: str) -> Optional[str]:
        if len(lines) <= index or not lines[index].startswith(label):
            return None
        return lines[index][len(label):].strip()

    return value(_CREATED_LINE, CREATED), value(_UPDATED_LINE, UPDATED)


def _parsed(text: Optional[str]) -> Optional[date]:
    """Return a date from an ISO string, or None where it is not one."""
    if text is None or not _ISO_DATE.match(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _shape_problems(name: str, created: Optional[str], updated: Optional[str],
                    today: date) -> list[str]:
    """Return what is wrong with one file's two date lines, history aside.

    Args:
        name (str): The file, as the message names it.
        created (Optional[str]): Its ``Created`` value.
        updated (Optional[str]): Its ``Last updated`` value.
        today (date): The date a line may not pass.

    Returns:
        list[str]: One message per problem.
    """
    problems: list[str] = []
    for label, text in ((CREATED, created), (UPDATED, updated)):
        if text is None:
            problems.append(
                f"{name}: the module docstring carries no '{label.strip()}' line in its place, "
                f"the purpose line, a blank line, then Created and Last updated"
            )
        elif _parsed(text) is None:
            problems.append(f"{name}: '{label}{text}' is not a date in YYYY-MM-DD form")
    born, touched = _parsed(created), _parsed(updated)
    if born and touched and born > touched:
        problems.append(f"{name}: created {born} is later than last updated {touched}")
    for stamp in (born, touched):
        if stamp and stamp > today:
            problems.append(f"{name}: {stamp} is later than today, {today}")
    return problems


def file_date_problems(root: Path, today: date) -> list[str]:
    """Return every Python file whose creation or update date is missing or wrong.

    Args:
        root (Path): The repository root.
        today (date): The date the run treats as today.

    Returns:
        list[str]: One message per problem, naming the file. A changed file is
        stale when its ``Last updated`` is before its last commit, and the
        message names ``tools/refresh_file_dates.py``.
    """
    changed = changed_files(root)
    problems: list[str] = []
    for path in python_sources(root):
        name = path.relative_to(root).as_posix()
        created, updated = date_lines(path.read_text(encoding="utf-8"))
        problems.extend(_shape_problems(name, created, updated, today))
        touched = _parsed(updated)
        if changed is None or name not in changed or touched is None:
            continue
        # TWO VALUES FROM ONE CLOCK. The stamp and `%cs` are both written in the
        # author's timezone; `today` comes from the runner's, and comparing
        # across them called every same-day commit stale for the seven hours
        # after local midnight. The mutation audit found it, being the one CI
        # caller whose tree differs from its last commit because it wrote it.
        # Section 10.39.1.
        committed = _parsed(last_committed(root, name))
        if committed is not None and touched < committed:
            problems.append(
                f"{name}: changed since its last commit on {committed} and still says "
                f"last updated {touched}; run tools/refresh_file_dates.py"
            )
    return problems


def stamped_source(source: str, created: str, updated: str) -> str:
    """Return the source with both date lines written into its module docstring.

    Existing lines are replaced in place. A docstring without them gains them
    after its purpose line and the blank line, and a one-line docstring is
    opened out to make room.

    Args:
        source (str): The module's source text, carrying a docstring.
        created (str): The ``Created`` date.
        updated (str): The ``Last updated`` date.

    Returns:
        str: The new source text.

    Raises:
        ValueError: When the module carries no docstring to write into.
    """
    tree = ast.parse(source)
    if not tree.body or ast.get_docstring(tree, clean=False) is None:
        raise ValueError("QC_HARNESS_PARSER_ERROR: the module carries no docstring to date")
    lines = source.split("\n")
    start = tree.body[0].lineno - 1
    end = tree.body[0].end_lineno - 1
    stamps = [f"{CREATED}{created}", f"{UPDATED}{updated}"]
    if start == end:
        opener = lines[start]
        quote = opener[:3]
        purpose = opener[3:opener.rindex(quote)]
        lines[start:start + 1] = [quote + purpose, "", *stamps, quote]
        return "\n".join(lines)
    created_at, updated_at = start + _CREATED_LINE, start + _UPDATED_LINE
    if lines[created_at].startswith(CREATED) and lines[updated_at].startswith(UPDATED):
        lines[created_at:updated_at + 1] = stamps
    else:
        lines[created_at:created_at] = [*stamps, ""]
    return "\n".join(lines)
