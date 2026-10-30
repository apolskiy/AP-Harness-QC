# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Flag checks: whether a flag a document tells a reader to type is declared.

Created: 2026-10-22
Last updated: 2026-10-29

This file contains ``declared_flags``, every flag a repository's own scripts
declare to argparse or to pytest, read from their syntax trees;
``FOREIGN_FLAGS`` and ``RETIRED_FLAGS``, the two registries naming what owns a
flag from outside the repository and which flag of ours was retired when; and
``undeclared_flags``, which reports a flag a live document names and none of
those declares.

It runs in the unit layer of both repositories, before anything a document
says is relied on, and a failure means a reader following that document would
type something the tool refuses. Nothing downstream depends on it, so a
failure costs a document edit rather than a run.

**A document names three kinds of flag and only one of them is ours.** The
pytest option registry is shared by both repositories, a script of the
repository declares its own, and everything else belongs to another program or
to the other repository's scripts, which is what the foreign registry records.
A retired flag of ours stays resolvable through its own registry rather than
being erased, for the reason ``testing-standards.md`` gives about a retired
identifier.

Specified by ``docs/design/cmn_verdict_and_cli.md`` section 7.1.0.4.
"""

import ast
import logging
import re
from pathlib import Path
from typing import Final

from cmn.code_standards import python_sources, walked_nodes
from cmn.document_citations import live_documents
from cmn.options import registered_options

logger = logging.getLogger(__name__)

# A LONG FLAG, WHICH IS THE ONLY FORM A DOCUMENT CAN BE CHECKED ON. A short
# flag is one letter, so `-m` in prose is as likely to be a minus sign or a
# list marker as an option, and the documents use `-m` constantly for pytest's
# marker selector.
_FLAG: Final[re.Pattern] = re.compile(r"--[a-z][a-z0-9-]{2,}")

# WHAT A SCRIPT DECLARES, by the two calls that declare one. `add_argument` is
# argparse and `addoption` is pytest's parser; the harness registers through
# `cmn.pytest_support` and the tools through argparse.
_DECLARING_CALLS: Final[frozenset[str]] = frozenset({"add_argument", "addoption"})

# FLAGS OWNED OUTSIDE THIS REPOSITORY, each naming its owner. This is NOT a
# declared-gap registry and carries no expiry: `--junitxml` belonging to
# pytest is a permanent fact rather than an absence somebody will close, and an
# entry that lapsed would report pytest as a defect on a Tuesday
# (`cmn_verdict_and_cli.md` section 7.1.0.4).
#
# THE LAST TWO ARE THE OTHER REPOSITORY'S SCRIPTS. Neither root can resolve
# the other's `tools/`, because the wheel ships `cmn` and not `tools`, so each
# is declared by name with its owner.
FOREIGN_FLAGS: Final[dict[str, str]] = {
    "--alluredir": "pytest, through the allure-pytest plugin",
    "--collect-only": "pytest",
    "--deselect": "pytest",
    "--help": "pytest, and every other program",
    "--junitxml": "pytest",
    "--last-failed": "pytest",
    "--log-level": "pytest",
    "--rootdir": "pytest",
    "--stepwise": "pytest",
    "--strict-markers": "pytest",
    "--rcfile": "pylint",
    "--name-only": "git",
    "--untracked-files": "git",
    "--editable": "pip",
    "--no-deps": "pip",
    "--clean": "allure generate",
    "--dir": "the GitHub CLI, gh run download",
    "--field": "the GitHub CLI, gh workflow run",
    "--limit": "the GitHub CLI, gh run list",
    "--name": "the GitHub CLI, gh run download",
    "--ref": "the GitHub CLI, gh workflow run",
    "--workflow": "the GitHub CLI, gh run list",
    "--case-branch": "AP-Model-QC, tools/harness_pin.py",
    "--hold-unreproduced": "AP-Model-QC, tools/findings.py",
    "--root": "AP-Harness-QC, tools/refresh_file_dates.py",
    # SHIPPED IN THE WHEEL AND STILL FOREIGN FROM THE OTHER ROOT.
    # `declared_flags` reads a repository's own sources, not its installed
    # packages, so a flag on a harness module a consumer's runbook documents
    # resolves here and nowhere else without this entry.
    "--role": "AP-Harness-QC, execution/adapters/registry.py",
}

# FLAGS OF OURS THAT WERE RETIRED. A retired flag stays resolvable rather than
# being erased, so the twelve live lines naming `--case` are correct: each
# describes the retirement. The registry is one entry rather than a rule about
# how such a line is worded.
RETIRED_FLAGS: Final[dict[str, str]] = {
    "--case": "retired 2026-10-03, replaced by --tests "
              "(cmn_verdict_and_cli.md section 7.8.4)",
}


def declared_flags(root: Path) -> set[str]:
    """Return every flag this repository's own code declares.

    The pytest option registry is included, being shared by both
    repositories, and every script's ``add_argument`` and ``addoption`` call
    is read from its syntax tree.

    **Parsed rather than matched**, for the reason ``112202`` and ``112226``
    parse: a file describing this rule names these strings, and a substring
    check reports itself.

    Args:
        root (Path): The repository root.

    Returns:
        set[str]: The flags, each with its leading double hyphen.
    """
    found = {entry.cli_flag for entry in registered_options()}
    for source in python_sources(root):
        for node in walked_nodes(source):
            if not isinstance(node, ast.Call):
                continue
            if getattr(node.func, "attr", "") not in _DECLARING_CALLS:
                continue
            for argument in node.args:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    found.add(argument.value)
    return found


def undeclared_flags(root: Path) -> list[str]:
    """Report every flag a live document names that nothing declares.

    A document's reader is being told to type the flag, so a flag that never
    existed or that was renamed sends them to a tool that refuses it. The
    rename is the costlier of the two, because the document describing the
    behaviour is the thing that is wrong.

    **The changelog and the progress log are not read.** They record what was
    true when they were written, so a flag retired since is correctly named in
    them, and ``cmn.document_citations.live_documents`` already draws that
    line for the same reason.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: ``<path>:<line> <flag>`` per occurrence, the path relative
        to the root, sorted by path and line. Design:
        ``cmn_verdict_and_cli.md`` section 7.1.0.4.
    """
    declared = declared_flags(root) | set(FOREIGN_FLAGS) | set(RETIRED_FLAGS)
    problems: list[str] = []
    for document in live_documents(root):
        where = document.relative_to(root).as_posix()
        for lineno, line in enumerate(
            document.read_text(encoding="utf-8").splitlines(), start=1
        ):
            for flag in _FLAG.findall(line):
                if flag not in declared:
                    problems.append(f"{where}:{lineno} {flag}")
    return problems
