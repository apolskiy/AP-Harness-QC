# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""What the tracked documents must satisfy, as against what the code must.

**Extracted 2026-10-08**, when `cmn/code_standards.py` reached exactly nine
hundred lines and the next subject to add was document naming. `code-style.md`
section 5.1: at the runway ceiling the next subject belongs in a module of its
own, named for that subject.

**The subject is a document rather than a module.** The register against the
repository both ways, a runbook whose documented dispatches must be accepted, a
heading a check reads prose out of, and a filename that has to say which
repository it belongs to. Everything left behind is about Python files.
"""

import re
import subprocess
from pathlib import Path
from typing import Final

import yaml



# This repository's runbook. **One per repository and now differently named**
# (`code-style.md` section 7.2), so the path is an argument rather than a
# constant: a function reading one repository's filename under another
# repository's root finds nothing and reports no problem, which is a silent
# pass and the class of defect this project treats as worst.
HARNESS_RUNBOOK: Final[str] = "docs/harness_running_jobs.md"

# A documented dispatch, as the runbook spells it.
_DISPATCH = re.compile(r"gh workflow run\s+(\S+\.yml)")

# An input named on that command line. GitHub rejects an undeclared one, and
# the reader concludes the procedure is broken rather than the page.
_FIELD = re.compile(r"--field\s+([A-Za-z_][A-Za-z0-9_-]*)=")


def runbook_problems(root: Path, runbook: str) -> list[str]:
    """Report every documented dispatch that would be rejected.

    **Prose is checked because a reader who believes a page stops looking.**
    The failure is silent at authoring time and lands on whoever follows the
    procedure, which is the person least able to tell a wrong page from a
    broken workflow.

    Args:
        root (Path): The repository root.
        runbook (str): The runbook's path relative to that root, supplied by the
            caller because the two repositories name theirs differently
            (`code-style.md` section 7.2). **No default**, so a caller cannot
            read one repository's filename under another repository's root and
            be told there is no problem.

    Returns:
        list[str]: One entry per problem, naming the command and what is wrong
        with it. An empty list means every documented dispatch would be
        accepted. **A missing runbook is not a problem here**, because whether
        a repository carries one is a separate question from whether the one it
        carries is correct.
    """
    page = root / runbook
    if not page.is_file():
        return []

    problems: list[str] = []
    for command in _dispatch_commands(page.read_text(encoding="utf-8")):
        workflow = _DISPATCH.search(command)
        if workflow is None:
            continue
        definition = root / ".github" / "workflows" / workflow.group(1)
        if not definition.is_file():
            problems.append(
                f"{runbook} dispatches {workflow.group(1)}, which does not exist"
            )
            continue
        declared = _declared_inputs(definition)
        for field in _FIELD.findall(command):
            if field not in declared:
                problems.append(
                    f"{runbook} passes --field {field} to {workflow.group(1)}, "
                    f"which declares {sorted(declared)}"
                )
    return problems


# THE TWO MANDATED ARTIFACTS, as the flags that write them.
# `testing-standards.md` section 5 requires both, so these are a pair and not
# a menu. Design `cmn_verdict_and_cli.md` section 7.1.0.3.


_REGISTER_ROW: Final[re.Pattern] = re.compile(
    r"^\|\s*`([A-Za-z0-9_./-]+\.(?:md|csv))`\s*\|"
)


def registered_documents(register: Path) -> set[str]:
    """Return every document path a register names.

    Args:
        register (Path): The register to read.

    Returns:
        set[str]: The paths, as the register spells them, with forward slashes.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the register names
            nothing, because a reader finding no rows would report no problems
            and pass for having read nothing.
    """
    named: set[str] = set()
    for line in register.read_text(encoding="utf-8").splitlines():
        matched = _REGISTER_ROW.match(line.strip())
        if matched is not None:
            named.add(matched.group(1))

    if not named:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: {register.name} names no document, so "
            f"this reader would report no problems by having read nothing"
        )
    return named


def document_register_problems(root: Path, register: Path) -> list[str]:
    """Return every disagreement between a register and the documents present.

    **Both directions, because each one hides a different failure.** A tracked
    document the register does not name is a document a review never reaches,
    which is how a design came to sit behind the changes made around it. A path
    the register names and nothing provides is a citation that will not resolve.

    **A path outside this root is not checked for existence.** A register
    legitimately names documents in the paired repository so a reader following
    a citation knows where it points, and this repository does not hold them.

    Design: ``harness_test_taxonomy.md`` section 12.

    Args:
        root (Path): The repository root.
        register (Path): The register within it.

    Returns:
        list[str]: One description per disagreement, empty when they agree.
    """
    named = registered_documents(register)
    problems: list[str] = []

    for path in sorted(tracked_documents(root) - named):
        problems.append(
            f"{path} is tracked and this register does not name it, so a "
            f"documentation review would not reach it"
        )

    # TRACKEDNESS, NOT EXISTENCE, in this direction too. **Corrected
    # 2026-10-05 after this check failed in CI and passed on one machine.** It
    # required every named path to be present on disk, and the register named
    # one deliberately untracked file: present where it was written and absent
    # in every clone. A check that reads the working tree for a file no clone
    # has can only pass where it was authored, which is the second instance of
    # that shape in this project.
    #
    # **A named path must now be tracked**, and the register names no untracked
    # file at all: working material is not a project document. A bare filename
    # is a paired-repository citation that resolves elsewhere.
    tracked = tracked_documents(root)
    for path in sorted(named):
        if "/" not in path or path in tracked:
            continue
        problems.append(
            f"{path} is named by this register and is not tracked, so a "
            f"citation to it will not resolve in a fresh checkout"
        )
    return problems


def tracked_documents(root: Path) -> set[str]:
    """Return every document git tracks in a repository.

    **Asked of git rather than walked.** A filesystem walk finds a generated
    `.pytest_cache/README.md` and whatever the next tool leaves behind, so it
    needs a denylist that grows every time one is added. What the register is
    about is the **tracked** documents, and git is the authority on which those
    are.

    Args:
        root (Path): The repository root.

    Returns:
        set[str]: Tracked ``.md`` and ``.csv`` paths, with forward slashes.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when git cannot answer.
            **Not treated as nothing tracked**, which would make the register
            check pass by finding no documents to compare.
    """
    try:
        listed = subprocess.run(
            ["git", "ls-files", "*.md", "*.csv"],
            capture_output=True, text=True, check=True, shell=False,
            cwd=str(root), stdin=subprocess.DEVNULL,
            # BOUNDED, per `harness_test_taxonomy.md` section 14. A local index read in
            # a minute is already pathological, and an unbounded one turns a
            # stalled git into a cancelled job rather than a failed check.
            timeout=60.0,
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: git could not list the tracked "
            f"documents in {root}, so the register cannot be checked against "
            f"them and an empty answer would pass for having compared nothing"
        ) from error

    return {line.strip() for line in listed.splitlines() if line.strip()}


def _dispatch_commands(text: str) -> list[str]:
    """Return every fenced line that dispatches a workflow.

    Args:
        text (str): The runbook source.

    Returns:
        list[str]: The command lines. **Fenced blocks only**, so prose naming a
        workflow in passing is not read as a command somebody could run.
    """
    commands: list[str] = []
    fenced = False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced and "gh workflow run" in line:
            commands.append(line)
    return commands


def _declared_inputs(definition: Path) -> set[str]:
    """Return the dispatch inputs a workflow declares.

    Args:
        definition (Path): The workflow file.

    Returns:
        set[str]: Every declared input name, empty when the workflow takes
        none.
    """
    parsed = yaml.safe_load(definition.read_text(encoding="utf-8"))
    # PyYAML reads the bare key `on` as the boolean True, so both spellings
    # have to be tried. This is the one place the quirk is load-bearing.
    triggers = parsed.get(True) or parsed.get("on") or {}
    dispatch = triggers.get("workflow_dispatch") or {}
    return set((dispatch.get("inputs") or {}).keys())


# The calls that read or write a file and must say in which encoding. `open`
# is the builtin; the other two are Path methods, matched by attribute name
# because Tier-crossing would be the only way to know the receiver is a Path.
