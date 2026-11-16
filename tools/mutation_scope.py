# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""What a mutation audit is asked for: its targets, its exclusions, its scope.

Created: 2026-10-24
Last updated: 2026-11-15

This file contains ``AUDIT_TARGETS``, the pytest arguments an audit runs and
the cases it deselects; ``audit_targets``, which takes a caller's arguments or
those; ``quarantined_cases`` and ``quarantine_report``, which name what the run
set aside; ``undefined_deselects``, which reports a deselected node naming no
defined case; and ``changed_lines``, the lines a module gained since a git ref,
which is how an audit is narrowed to the work that prompted it.

**Asked for, as against measured.** ``tools/mutation_audit.py`` mutates a
module, runs a suite and refuses when it cannot measure; none of that is here.
This module answers what the audit was pointed at, which is read by the
command line, by Gate 8's job summary and by the mutation suite's own closing
line.

**Split out on 2026-10-24**, when the scoping and the quarantine report took
that module to 956 lines against the nine-hundred-line runway
(``code-style.md`` section 5.1). It is re-exported there, so no caller moved.

Design: ``docs/design/harness_test_taxonomy.md`` sections 15.6A and 15.7.1.2.
"""

import ast
import logging
import re
import subprocess
from pathlib import Path
from typing import Final, Optional

logger = logging.getLogger(__name__)


# THE IDENTIFIER INSIDE A DESELECTED NODE ID, for the line that reports what
# the audit set aside. Five or six digits, as the resolver elsewhere reads.
_CASE_IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"MQC_[A-Z]+_[A-Z]{3,5}_(\d{5,6})_")
# THE DESTINATION SIDE OF A DIFF HUNK, which is where a line stands now:
# `@@ -12,3 +14,5 @@` means five lines from line 14 in the file on disk.
_HUNK: Final[re.Pattern[str]] = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
# THE FOUR CASES THAT READ SOURCE AS TEXT RATHER THAN IMPORTING IT, so they
# fail on the reformatting the mutator performs and would kill every mutant for
# the wrong reason. Measured rather than guessed: the suite was run against an
# unparsed module and these are what failed. Declared once, for the audit cases
# and the command line alike (sections 15.4 and 15.4.2).
#
# THE DIGEST PRECONDITION IS THE THIRD, added 2026-10-23 on the first run after
# it was written: the control writes a module as its own unparse, which by
# construction does not hash to the declared digest, so every audit refused
# with its own control as the reason (section 15.4.4).
#
# AND THE COPY COMPARISON IS THE FOURTH, added 2026-10-24 for the same reason
# one case along: it copies the audited modules and the manifest and asserts
# the copy is accepted, which is true of every ordinary run and false of every
# audit, the module on disk being its own unparse while it is held.
#
# THE FILE-DATE READER IS THE FIFTH, and the list was **re-measured** on
# 2026-10-24 rather than extended one refusal at a time: the targets were run
# against an unparsed module and this is the only other case that failed.
# `ast.unparse` re-emits a docstring as one string literal, so the `Created:`
# and `Last updated:` lines stop being line-shaped text and the reader finds
# none (section 15.7.1.1).
#
# A NODE IS A PATH, AND A PATH GOES STALE WHEN A CASE MOVES. pytest deselects
# nothing for a node it cannot find, so `undefined_deselects` reports one and
# MQC_CMN_UNI_410009 asserts there is none (section 15.7.1.2).
AUDIT_TARGETS: Final[tuple[str, ...]] = (
    "-m", "unit",
    "--deselect",
    "tests/cmn/mqc_uni_file_standards.py::TestMQCAuthorshipHeader"
    "::MQC_CMN_UNI_112502_every_python_file_carries_its_spdx_header",
    "--deselect",
    "tests/cmn/mqc_uni_module_layout.py::TestMQCModuleRunway"
    "::MQC_CMN_UNI_112331_a_module_at_the_runway_ceiling_is_reported",
    "--deselect",
    "tests/cmn/mqc_uni_mutation_declarations.py::TestMQCMutationDeclarations"
    "::MQC_CMN_UNI_410000_every_audited_module_hashes_to_its_declared_digest",
    "--deselect",
    "tests/cmn/mqc_uni_mutation_declarations.py::TestMQCMutationDeclarations"
    "::MQC_CMN_UNI_410003_a_stale_declaration_from_the_command_line_exits_four",
    "--deselect",
    "tests/cmn/mqc_uni_file_dates.py::TestMQCFileDates"
    "::MQC_CMN_UNI_112526_a_file_date_line_missing_or_stale_is_reported",
)
def changed_lines(root: Path, module: Path, since: str) -> frozenset[int]:
    """Return the lines a module gained or changed since a git ref.

    **A survivor appears where code was written without a case to notice it**,
    so the points worth measuring are the ones on lines the work being audited
    touched (section 15.6A.4).

    Args:
        root (Path): The repository root.
        module (Path): The module, absolute or relative to the root.
        since (str): Any ref ``git diff`` accepts.

    Returns:
        frozenset[int]: The line numbers, empty where git reports nothing or
        cannot answer. **An empty set audits every point**, because a scope
        nobody could compute is not a scope of none.
    """
    relative = module.relative_to(root).as_posix() if module.is_absolute() else str(module)
    try:
        finished = subprocess.run(
            ["git", "diff", "--unified=0", since, "--", relative],
            cwd=root, capture_output=True, text=True, check=False,
            stdin=subprocess.DEVNULL, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return frozenset()
    if finished.returncode != 0:
        return frozenset()
    found: set[int] = set()
    for line in finished.stdout.splitlines():
        match = _HUNK.match(line)
        if match is None:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        found.update(range(start, start + max(count, 1)))
    return frozenset(found)
def quarantined_cases(targets: Optional[list[str]] = None) -> list[str]:
    """Return every case the audit sets aside, by identifier.

    A case that reads source or the manifest as text fails on the
    reformatting the mutator performs rather than on a mutant, so the control
    deselects it and this names which. **Read from the targets rather than
    restated**, so a list extended in one place is reported from the same
    place (``harness_test_taxonomy.md`` section 15.7.1.2).

    Args:
        targets (Optional[list]): The pytest arguments to read, defaulting to
            the audit's own.

    Returns:
        list[str]: The six-digit identifier of each deselected case, in the
        order the list declares them, empty where none is deselected.
    """
    reading = list(AUDIT_TARGETS) if targets is None else list(targets)
    found: list[str] = []
    for index, argument in enumerate(reading[:-1]):
        if argument != "--deselect":
            continue
        match = _CASE_IDENTIFIER.search(reading[index + 1])
        if match is not None:
            found.append(match.group(1))
    return found
def quarantine_report(targets: Optional[list[str]] = None) -> str:
    """Return the line a run closes with, naming what it set aside.

    Args:
        targets (Optional[list]): The pytest arguments to read, defaulting to
            the audit's own.

    Returns:
        str: One sentence, with the count and the identifiers, reading
        ``none`` where the list is empty.
    """
    quarantined = quarantined_cases(targets)
    return (
        f"{len(quarantined)} case(s) quarantined from this audit: "
        f"{', '.join(quarantined) or 'none'}"
    )
def undefined_deselects(root: Path, targets: list[str]) -> list[str]:
    """Return every deselected node that names no defined case.

    Args:
        root (Path): The repository root the node paths are relative to.
        targets (list[str]): The pytest arguments to read.

    Returns:
        list[str]: The nodes, in the order the targets declare them.
    """
    nodes = [
        targets[index + 1]
        for index, argument in enumerate(targets[:-1])
        if argument == "--deselect"
    ]
    return [node for node in nodes if not _node_defined(root, node)]
def _node_defined(root: Path, node: str) -> bool:
    """Return whether a ``module::Class::case`` node names a defined case.

    Args:
        root (Path): The repository root the module path is relative to.
        node (str): The node identifier.

    Returns:
        bool: True when the module exists, defines the class, and the class
        defines the case.
    """
    module, _, rest = node.partition("::")
    class_name, _, case_name = rest.partition("::")
    source = root / module
    if not source.is_file():
        return False
    tree = ast.parse(source.read_text(encoding="utf-8"))
    return any(
        isinstance(member, ast.FunctionDef) and member.name == case_name
        for definition in tree.body
        if isinstance(definition, ast.ClassDef) and definition.name == class_name
        for member in definition.body
    )
def audit_targets(named: list[str]) -> list[str]:
    """Return the pytest arguments an audit runs, the declared ones when none are named.

    Args:
        named (list[str]): The ``--target`` arguments, empty when none were given.

    Returns:
        list[str]: The arguments.
    """
    return list(named) if named else list(AUDIT_TARGETS)
