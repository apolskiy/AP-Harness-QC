# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Document standards checks, the rules tracked documents must satisfy.

Created: 2026-10-08
Last updated: 2026-10-25

This file contains ``runbook_problems``, which reports a documented workflow
dispatch GitHub would reject; ``duplicate_inventory_bindings`` and
``duplicate_case_bindings``, an identifier bound to two behaviours in a design
inventory or in the suite; ``inventory_count_problems``, a design whose stated
case count disagrees with its rows; ``changelog_problems``, a README with no
changelog; and ``document_register_problems``, a register disagreeing with the
documents present, read through ``registered_documents`` and
``tracked_documents``.

Precondition cases in both repositories call these with their own root, so a
document that has drifted from the repository fails the unit layer.

**Extracted 2026-10-08**, when `cmn/code_standards.py` reached exactly nine
hundred lines and the next subject to add was document naming. `code-style.md`
section 5.1: at the runway ceiling the next subject belongs in a module of its
own, named for that subject.

**The subject is a document rather than a module.** The register against the
repository both ways, a runbook whose documented dispatches must be accepted, a
heading a check reads prose out of, and a filename that has to say which
repository it belongs to. Everything left behind is about Python files.
"""

import ast
import logging
import re
import subprocess
from pathlib import Path
from typing import Final

import yaml

logger = logging.getLogger(__name__)



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


# A STATED INVENTORY, IN THE ONE PHRASING EVERY DESIGN USES. Four documents
# once used three different wordings for this sentence, which would have forced
# the reader to parse prose variants: a check that parses prose fails the first
# time somebody rewords rather than changes a number.
_INVENTORY: Final[re.Pattern] = re.compile(
    r"\*\*Inventory: (\d+) cases, (\d+) negative, (\d+) positive, (\d+) boundary"
)

# A ROW IN AN INVENTORY TABLE, bare six digits with its category. A struck
# through row is a retirement and is deliberately not matched: the identifier
# stays resolvable and the case no longer exists to be counted.
_INVENTORY_ROW: Final[re.Pattern] = re.compile(
    r"^\| `(\d{6})` \| ([PNB]) \|", re.M
)


# AN INVENTORY ROW, CAPTURED FOR ITS IDENTITY AND ITS BEHAVIOUR. A struck
# through row is a retirement and is deliberately unmatched: the identifier
# stays resolvable and the case no longer exists to collide with anything.
_BINDING_ROW: Final[re.Pattern] = re.compile(
    r"^\|\s*`(?P<identifier>\d{6})`\s*\|\s*[PNB]\s*\|\s*`?(?P<behaviour>[a-z_0-9]+)"
)

# A CASE CALLABLE, PARSED RATHER THAN MATCHED where it matters. Here a regex is
# safe because the subject is a definition line and the project's own scanner
# defect came from matching definitions inside string literals; the suite
# reader below parses.
_CASE_DEFINITION: Final[re.Pattern] = re.compile(
    r"def MQC_[A-Z]{3}_[A-Z]{3,5}_(?P<identifier>\d{6})_(?P<behaviour>[a-z_0-9]+)"
)


def duplicate_inventory_bindings(
    design_dir: Path, historical: frozenset[str] = frozenset()
) -> list[str]:
    """Report every identifier a design inventory binds to two behaviours.

    **Every per-row check passes while an identifier is bound twice**, because
    each is keyed on a row and the defect is a relationship between two rows.
    That is the shape a per-row check cannot see, whatever its strictness.

    Args:
        design_dir (Path): The directory holding the design documents.
        historical (frozenset[str]): Document names whose rows record what was
            rather than what is, excluded so a retired binding does not read as
            a live collision.

    Returns:
        list[str]: One entry per collision, naming the document, the identifier
        and both behaviours.
    """
    seen: dict[str, list[str]] = {}
    for document in sorted(design_dir.glob("*.md")):
        if document.name in historical:
            continue
        for line in document.read_text(encoding="utf-8").splitlines():
            match = _BINDING_ROW.match(line.strip())
            if match is None:
                continue
            key = f"{document.name}:{match.group('identifier')}"
            seen.setdefault(key, []).append(match.group("behaviour"))
    return _collisions(seen)


def duplicate_case_bindings(root: Path) -> list[str]:
    """Report every identifier the collected suite binds to two behaviours.

    **The inventory and the suite can disagree separately**, and in this
    project they agreed: five identifiers were bound twice in both, so a check
    on one half would have found the same five and a check on neither found
    nothing for a week.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per collision, naming the identifier and both
        behaviours with the modules that define them.
    """
    base = root / "tests"
    if not base.is_dir():
        return []
    seen: dict[str, list[str]] = {}
    for source in sorted(base.rglob("mqc_*.py")):
        if "__pycache__" in source.parts:
            continue
        body = source.read_text(encoding="utf-8")
        for match in _CASE_DEFINITION.finditer(body):
            # DEFINED, NOT MENTIONED. A `def` inside a triple-quoted fixture is
            # a double rather than a case, which is the scanner defect
            # `code-style.md` section 8.1 records; the line's own indentation
            # distinguishes a module-level class body from a string.
            if not _defines_here(body, match.start()):
                continue
            seen.setdefault(match.group("identifier"), []).append(
                f"{match.group('behaviour')} in {source.name}"
            )
    return _collisions(seen)


def _defines_here(body: str, position: int) -> bool:
    """Report whether a match is a real definition rather than fixture text.

    Args:
        body (str): The module source.
        position (int): Where the match begins.

    Returns:
        bool: True when the enclosing line is a definition at class-body
        indentation, which a line inside a quoted fixture is not.
    """
    start = body.rfind("\n", 0, position) + 1
    prefix = body[start:position]
    return prefix.strip() == "" and len(prefix) == 4


def _collisions(seen: dict[str, list[str]]) -> list[str]:
    """Return one entry per identifier bound more than once.

    Args:
        seen (dict): Identifier or scoped key to the behaviours bound to it.

    Returns:
        list[str]: Sorted, so two runs report in the same order.
    """
    return [
        f"{where} is bound to {' and '.join(sorted(names))}"
        for where, names in sorted(seen.items())
        if len(set(names)) > 1
    ]


def inventory_count_problems(design_dir: Path) -> list[str]:
    """Report every design whose stated inventory disagrees with its own rows.

    **A stated total is derived data, and derived data gets restated wrongly.**
    The harness checked this inline from 2026-09-26; the case repository had no
    equivalent and its own figure drifted to 52 against 48 rows, because five
    cases were added with the count incremented and no row written.

    Design: ``AP-Model-QC`` ``consumer_ci.md`` section 4, which recorded the
    asymmetry as an open question.

    Args:
        design_dir (Path): The directory holding the design documents.

    Returns:
        list[str]: One entry per disagreement, naming the document, what it
        states and what its rows give. **A document stating no inventory is not
        a problem here**, because whether a design carries one is a separate
        question from whether the one it carries is right.
    """
    problems: list[str] = []
    for document in sorted(design_dir.glob("*.md")):
        body = document.read_text(encoding="utf-8")
        stated = _INVENTORY.search(body)
        if stated is None:
            continue
        rows = [category for _, category in _INVENTORY_ROW.findall(body)]
        actual = (
            len(rows), rows.count("N"), rows.count("P"), rows.count("B")
        )
        claimed = tuple(int(group) for group in stated.groups())
        if claimed != actual:
            problems.append(
                f"{document.name} states {claimed[0]} cases "
                f"({claimed[1]} negative, {claimed[2]} positive, "
                f"{claimed[3]} boundary) and its rows give {actual[0]} "
                f"({actual[1]} negative, {actual[2]} positive, "
                f"{actual[3]} boundary)"
            )
    if problems:
        logger.warning(
            "%d design(s) state an inventory their own rows contradict",
            len(problems),
        )
    return problems


def documents_stating_an_inventory(design_dir: Path) -> list[str]:
    """Return every design that states an inventory at all.

    **So a caller can assert it compared something.** A check that silently
    finds no inventory to compare reports agreement having read nothing, which
    is the vacuity the instrument audit exists to prevent.

    Args:
        design_dir (Path): The directory holding the design documents.

    Returns:
        list[str]: The document names, sorted.
    """
    return sorted(
        document.name for document in sorted(design_dir.glob("*.md"))
        if _INVENTORY.search(document.read_text(encoding="utf-8"))
    )


def changelog_problems(root: Path) -> list[str]:
    """Report a repository holding a README and no changelog.

    **The README describes the current state and nothing else**, which is what
    makes it readable and also what makes it historyless: a figure that moves
    there leaves no record of when it moved or why, and the why is the part a
    later reader needs. So the two documents are edited together, and a
    repository holding one holds the other
    (``code-style.md`` section 7.4).

    **Whether they were edited in the same change cannot be checked here**,
    because that is a property of a commit and this reads a working tree. What
    is checked is the state that results from skipping the step, which is the
    answer the authoring-order rule already gives.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry where a README is present without a changelog, and
        empty otherwise. **Empty where neither is present**, because a
        directory that is not a repository root is not missing anything.
    """
    readme = root / "README.md"
    changelog = root / "CHANGELOG.md"
    if readme.is_file() and not changelog.is_file():
        return [
            f"{root.name} has a README and no CHANGELOG.md, so a figure that "
            f"moves in the README leaves no record of when it moved or why"
        ]
    return []


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


# WHAT THE README CALLS THE AUDIT, counted apart from the suite because it is
# an internal tool rather than a test of the harness
# (``harness_test_taxonomy.md`` section 15.6A.5).
_AUDIT_FIGURE: Final[re.Pattern[str]] = re.compile(r"\*\*(\d+) audits\*\*")
# PARSED, NOT MATCHED. An audit named inside a string literal is data, and
# this module plants exactly that in a case: the first version of this reader
# counted five audits where the suite holds four.
_AUDIT_NAME: Final[re.Pattern[str]] = re.compile(r"^MQC_[A-Z]+_MUT_\d{5,6}_[a-z_]+$")


def audit_figure_problems(root: Path) -> list[str]:
    """Report a README whose audit count disagrees with the audits that exist.

    **Counted apart from the suite figure**, which section 15.6A.5 requires:
    an audit measures the suite's own coverage rather than the harness, runs
    in a job of its own, and belongs in neither total.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry where the README states no audit count or states
        one the repository contradicts. Empty where they agree, and empty for
        a repository that holds no audit at all.
    """
    audits: set[str] = set()
    if (root / "tests").is_dir():
        for module in sorted((root / "tests").rglob("mqc_*.py")):
            try:
                tree = ast.parse(module.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):
                continue
            audits.update(
                node.name for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and _AUDIT_NAME.match(node.name)
            )
    readme = root / "README.md"
    if not audits or not readme.is_file():
        return []
    stated = _AUDIT_FIGURE.search(readme.read_text(encoding="utf-8"))
    if stated is None:
        return [
            f"{readme.name} states no audit count, so {len(audits)} audit(s) are "
            f"either uncounted or folded into the suite figure"
        ]
    if int(stated.group(1)) != len(audits):
        return [
            f"{readme.name} says {stated.group(1)} audits, the suite holds "
            f"{len(audits)}"
        ]
    return []
