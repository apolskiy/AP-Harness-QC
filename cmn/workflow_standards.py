# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""What the CI definitions must hold, checked before a push rather than by it.

Specified by ``docs/design/ci_pipeline.md`` sections 8.2 and 8.3.

**Split from ``code_standards.py`` on 2026-10-04**, when these took that module
past the thousand-line ceiling. The concerns differ: that module is about the
source a reader writes, this one about the pipeline definitions and the commands
written beside them.

**None of these replaces ``actionlint``**, which validates the workflow schema
and runs in CI. They cover what a local check could have caught before a push:
a command that disagrees with its copies, a step that can spend without a
ceiling, and the one malformed-YAML class a parse accepts.
"""

import logging
import re
from pathlib import Path
from typing import Any, Final

import yaml

logger = logging.getLogger(__name__)


_PYLINT_CALL: Final[re.Pattern] = re.compile(
    r"pylint\s+([^\n]*?--rcfile=\.pylintrc)"
)


_CEILING_FLAG: Final[str] = "--max-spend"


# A STEP THAT CAN REACH A PROVIDER. `--mode live` dispatches to the candidate
# and `--judge-mode live` dispatches to the judge, which is never replayed: a
# bound judge is a live call whatever the candidate mode. Either spends.
# Design `ci_pipeline.md` section 8.2.
_SPENDING_FLAGS: Final[tuple[str, ...]] = ("--mode live", "--judge-mode live")

# AND THE ONE THAT BOUNDS IT. `--max-spend` aborts before a request would take
# the run past a figure, and fails closed on an unpriced model.


def uncapped_spending_steps(root: Path) -> list[str]:
    """Report every workflow step that can spend and names no ceiling.

    **The flag existed and nothing passed it**, which is this project's
    recurring shape: `--max-spend` is implemented and covered, and until
    2026-10-04 no workflow set a value, so a live run had no ceiling at all.
    That mattered the moment a credential reached Actions.

    **Keyed on the mode flags rather than on a job's environment.** A job can
    name ``environment: live`` and run only replay legs, and a step can spend
    from a workflow whose other jobs do not; what decides is whether the
    invocation dispatches live.

    **A matrix-valued mode counts as spending.** A step whose mode comes from
    ``matrix.mode`` may be live on one leg, so it is reported unless it carries
    a ceiling, on the same reasoning that makes the artifact check key on the
    flags rather than on the word pytest.

    Design: ``ci_pipeline.md`` section 8.2.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per step, naming the workflow and the line. Empty
        when every step that can reach a provider carries a ceiling.
    """
    problems: list[str] = []
    for workflow in sorted((root / ".github" / "workflows").glob("*.yml")):
        for number, invocation in _shell_invocations(workflow):
            spends = any(flag in invocation for flag in _SPENDING_FLAGS)
            matrix_mode = "--mode ${{ matrix.mode }}" in invocation
            if not spends and not matrix_mode:
                continue
            if _CEILING_FLAG in invocation:
                continue
            problems.append(
                f"{workflow.name}:{number} can dispatch live and names no "
                f"{_CEILING_FLAG}, so the run has no ceiling"
            )
    return problems


def _shell_invocations(workflow: Path) -> list[tuple[int, str]]:
    """Return each shell command in a workflow as one logical line.

    **Continuations are joined first.** A pytest invocation in CI is written
    across several lines with trailing backslashes, so a line-based reader sees
    ``--mode live`` and ``--max-spend`` as different lines and reports a step
    that carries both. A check that over-reports is one a reader learns to
    skip, which is worse than the gap it was written for.

    Args:
        workflow (Path): The workflow file.

    Returns:
        list[tuple[int, str]]: The line the command starts on, and the command
        with its continuations joined.
    """
    joined: list[tuple[int, str]] = []
    pending: list[str] = []
    start = 0
    for number, line in enumerate(
        workflow.read_text(encoding="utf-8").splitlines(), start=1
    ):
        stripped = line.strip()
        if not pending:
            start = number
        if stripped.endswith("\\"):
            pending.append(stripped[:-1].strip())
            continue
        pending.append(stripped)
        joined.append((start, " ".join(pending)))
        pending = []
    if pending:
        joined.append((start, " ".join(pending)))
    return joined


# EVERY PYLINT INVOCATION IN THE REPOSITORY, wherever it is written. The path
# list is part of the command: a directory omitted from one copy passes that
# gate and fails another, which arrives as a red on a commit already reported
# green. Design `ci_pipeline.md` section 8.3.


def pylint_invocations(root: Path) -> dict[str, list[str]]:
    """Return every pylint invocation written in the repository, by file.

    Reads the workflows and the tracked prose, because a documented command a
    reader copies is as load-bearing as the one CI runs: a contributor who
    lints less than the gate does finds out from the gate.

    Args:
        root (Path): The repository root.

    Returns:
        dict[str, list[str]]: Relative path to each invocation's argument
        string, normalised on whitespace so formatting is not a difference.
    """
    found: dict[str, list[str]] = {}
    sources = sorted((root / ".github" / "workflows").glob("*.yml"))
    sources += [
        root / ".claude" / "rules" / "testing-standards.md",
        root / "docs" / "running_jobs.md",
    ]
    for source in sources:
        if not source.is_file():
            continue
        calls = [
            " ".join(match.split())
            for match in _PYLINT_CALL.findall(source.read_text(encoding="utf-8"))
        ]
        if calls:
            found[source.relative_to(root).as_posix()] = calls
    return found


def disagreeing_pylint_invocations(root: Path) -> list[str]:
    """Report every pylint invocation that differs from the others.

    **The path list is part of the command.** Four copies stood with four
    different lists until 2026-10-04: one omitted ``cmn/``, two omitted
    ``conftest.py``, the gate omitted ``tools/``. A file in an omitted
    directory passes the gate and fails the branch regression, which arrives as
    a red on a commit that was already reported green.

    Design: ``ci_pipeline.md`` section 8.3.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per invocation that is not the majority form,
        empty when every copy agrees.
    """
    found = pylint_invocations(root)
    everything = [call for calls in found.values() for call in calls]
    if not everything:
        return [
            "no pylint invocation was found at all, so this reader would "
            "report agreement by having read nothing"
        ]

    agreed = max(set(everything), key=everything.count)
    return [
        f"{where} runs pylint over {call!r} while the rest run it over "
        f"{agreed!r}"
        for where, calls in sorted(found.items())
        for call in calls
        if call != agreed
    ]


def duplicate_yaml_keys(root: Path) -> list[str]:
    """Report every tracked YAML file carrying a duplicated mapping key.

    **This is the class a parse accepts and a schema rejects.** YAML permits a
    duplicate key and resolves it last-wins, so a stanza given a second
    ``inputs:`` block loses the first silently along with whatever it declared,
    while GitHub rejects the file outright.

    **Composed rather than loaded.** ``yaml.compose`` returns the node tree
    before any mapping is constructed, so the duplicate is still visible; a
    loader that constructs the mapping has already resolved it. It needs no
    loader subclass either, which the ancestor limit in ``.pylintrc`` refuses.

    Design: ``ci_pipeline.md`` section 8.3.2.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per offending file, naming the key and the line.
    """
    problems: list[str] = []
    sources = sorted((root / ".github" / "workflows").glob("*.yml"))
    sources += sorted((root / "config").glob("*.yaml"))
    for source in sources:
        try:
            tree = yaml.compose(source.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            problems.append(f"{source.name}: will not parse at all, {error}")
            continue
        if tree is not None:
            problems.extend(
                f"{source.name}: {detail}" for detail in _repeated_keys(tree)
            )
    return problems


def _repeated_keys(node: Any) -> list[str]:
    """Return a description of every duplicated key in a composed node tree.

    Args:
        node (Any): A composed YAML node.

    Returns:
        list[str]: One entry per duplicate, naming the key and its line.
    """
    found: list[str] = []
    if isinstance(node, yaml.MappingNode):
        seen: set[str] = set()
        for key_node, value_node in node.value:
            name = getattr(key_node, "value", None)
            if isinstance(name, str):
                if name in seen:
                    found.append(
                        f"QC_DATA_MALFORMED_SOURCE: key {name!r} appears twice "
                        f"in the same mapping at line "
                        f"{key_node.start_mark.line + 1}, and YAML would "
                        f"resolve it last-wins, discarding the first silently"
                    )
                seen.add(name)
            found.extend(_repeated_keys(value_node))
    elif isinstance(node, yaml.SequenceNode):
        for entry in node.value:
            found.extend(_repeated_keys(entry))
    return found
