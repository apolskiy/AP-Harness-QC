# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Whether a CI definition gates what it runs, read before a push.

Created: 2026-10-25
Last updated: 2026-10-25

This file contains ``ungated_graded_jobs``, which reports a job that runs
graded cases out of this repository's checkout and reaches no precondition
invocation, and the readers it needs: ``_job_scripts``, which follows a local
``uses:`` into a composite action, ``_selected_layers``, which reads a marker
expression, and ``_reaches_a_precondition``, which walks a job's ``needs:``.

A precondition case in each repository calls it with that repository's root, so
a workflow that would measure a model with an unchecked instrument fails the
unit layer locally rather than spending quota in CI to find out.

**Its own module rather than a subject in ``workflow_standards.py``**, which
reached its nine-hundred-line runway as this was written. The subjects divide
cleanly: that module reads what a definition says, a pylint path list or a
spending ceiling, and this one reads what stands in front of a job.

Specified by ``docs/design/harness_ci_pipeline.md`` section 8.6.
"""

import re
from pathlib import Path
from typing import Any, Final

import yaml

# A DEBUG WORKFLOW IS EXEMPT, by the cadence suffix its file name carries: its
# rows are `ci_debug` and yield no verdict whatever they selected, which is
# what a debug run is for (section 8.2.2).
_ON_DEMAND_SUFFIX: Final[str] = "-on-demand.yml"

# THE PRECONDITION LAYERS, which carry no priority and gate everything graded.
# `framework-rules.md` section 1 makes Gate 2 blocking and
# `testing-standards.md` says the graded layers do not execute if one fails,
# because running them spends provider quota to generate noise.
_PRECONDITION_LAYERS: Final[tuple[str, ...]] = ("unit", "system")

# THE GRADED LAYERS, which together are every case that measures a model.
_GRADED_LAYERS: Final[tuple[str, ...]] = ("evaluator", "tool", "sec")

# THE `-m` EXPRESSION, quoted either way or bare, as `code_standards` reads it.
_LAYER_EXPRESSION: Final[re.Pattern] = re.compile(
    r"-m\s+(?:\"([^\"]*)\"|'([^']*)'|(\S+))"
)

# A REFERENCE THIS REPOSITORY OWNS, which section 8.4 requires following.
_LOCAL_REFERENCE: Final[str] = "./"
_ACTION_DEFINITION: Final[str] = "action.yml"


def ungated_graded_jobs(root: Path) -> list[str]:
    """Report every job running graded cases that reaches no precondition.

    A graded job is gated by a job it needs, directly or transitively, that
    runs a precondition invocation, or by an earlier step of its own job that a
    failure stops. Neither holding means the job can measure a model with an
    instrument nothing checked, and the ones that spend are reached the same
    way.

    **A step running in a checkout the job fetched is not read as ours.** The
    cases, the corpus and therefore the preconditions belong to that checkout.

    **A debug workflow is exempt** by its cadence suffix, and a local ``uses:``
    is followed, because a graded invocation factored into a composite action
    would otherwise leave its job looking ungraded.

    Design: ``harness_ci_pipeline.md`` section 8.6.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per job, naming the file, the job and what it
        needs. Empty where every graded job reaches a precondition.
    """
    gaps: list[str] = []
    for path in sorted((root / ".github" / "workflows").glob("*.yml")):
        if path.name.endswith(_ON_DEMAND_SUFFIX):
            continue
        parsed = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        jobs: dict[str, Any] = parsed.get("jobs") or {}
        scripts = {name: _job_scripts(root, body or {}) for name, body in jobs.items()}
        for name in jobs:
            if not _grades_our_cases(scripts[name]):
                continue
            if _reaches_a_precondition(name, jobs, scripts):
                continue
            needed = ", ".join(_needed(jobs[name] or {})) or "nothing"
            gaps.append(
                f"{path.name} job {name!r} runs graded cases and reaches no "
                f"precondition invocation: it needs {needed}, and no earlier "
                f"step of its own runs one, so it would measure a model with "
                f"an instrument nothing checked"
            )
    return gaps


def _job_scripts(root: Path, job: dict[str, Any]) -> list[tuple[str, bool]]:
    """Return each shell command a job runs, and whether it runs elsewhere.

    A local ``uses:`` contributes the referenced definition's own commands, per
    section 8.4, and inherits the referring step's working directory.

    Args:
        root (Path): The repository root, which a local reference resolves
            against.
        job (dict[str, Any]): The job definition.

    Returns:
        list[tuple[str, bool]]: Each command in step order, with whether it
        runs in a checkout the job fetched.
    """
    scripts: list[tuple[str, bool]] = []
    for step in job.get("steps") or []:
        declared = step or {}
        elsewhere = bool(str(declared.get("working-directory") or ""))
        command = str(declared.get("run") or "")
        if command:
            scripts.append((command, elsewhere))
        reference = str(declared.get("uses") or "")
        if not reference.startswith(_LOCAL_REFERENCE):
            continue
        for referenced in _referenced_steps(root, reference):
            carried = referenced or {}
            scripts.append(
                (
                    str(carried.get("run") or ""),
                    elsewhere or bool(str(carried.get("working-directory") or "")),
                )
            )
    return scripts


def _referenced_steps(root: Path, reference: str) -> list[Any]:
    """Return the steps a local composite action or workflow defines.

    Args:
        root (Path): The repository root.
        reference (str): The ``uses:`` value, beginning with a local prefix.

    Returns:
        list[Any]: The referenced steps, empty where the reference resolves to
        no file. An unresolvable reference is reported by the reader that
        walks a job's lines, not here.
    """
    target = root / reference.removeprefix(_LOCAL_REFERENCE)
    if target.is_dir():
        target = target / _ACTION_DEFINITION
    if not target.is_file():
        return []
    parsed = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    steps: list[Any] = list((parsed.get("runs") or {}).get("steps") or [])
    for body in (parsed.get("jobs") or {}).values():
        steps += list((body or {}).get("steps") or [])
    return steps


def _selected_layers(command: str) -> set[str]:
    """Return the layer markers a command's marker expressions name.

    Args:
        command (str): A shell command.

    Returns:
        set[str]: The layer names present, of the graded and precondition
        layers. Empty where the command names no marker expression.
    """
    named: set[str] = set()
    for quoted, single, bare in _LAYER_EXPRESSION.findall(command):
        expression = quoted or single or bare
        named.update(
            layer
            for layer in _GRADED_LAYERS + _PRECONDITION_LAYERS
            if re.search(rf"\b{layer}\b", expression)
        )
    return named


def _grades_our_cases(scripts: list[tuple[str, bool]]) -> bool:
    """Say whether a job runs graded cases out of this repository's checkout.

    Args:
        scripts (list[tuple[str, bool]]): The job's commands, each with
            whether it runs in a checkout the job fetched.

    Returns:
        bool: True where a command in our own checkout names a graded layer.
    """
    return any(
        not elsewhere and _selected_layers(command) & set(_GRADED_LAYERS)
        for command, elsewhere in scripts
    )


def _runs_a_precondition(scripts: list[tuple[str, bool]], *, before: int) -> bool:
    """Say whether a precondition invocation appears among a job's commands.

    Args:
        scripts (list[tuple[str, bool]]): The job's commands in step order.
        before (int): How many commands to read, which is the whole job for a
            job another one needs and the commands ahead of the graded one
            within a job.

    Returns:
        bool: True where one of those commands names a precondition layer.
    """
    return any(
        _selected_layers(command) & set(_PRECONDITION_LAYERS)
        for command, _ in scripts[:before]
    )


def _needed(job: dict[str, Any]) -> list[str]:
    """Return the jobs a job declares it needs.

    Args:
        job (dict[str, Any]): The job definition.

    Returns:
        list[str]: The named jobs, one entry for the string form.
    """
    declared = job.get("needs")
    if isinstance(declared, str):
        return [declared]
    return [str(name) for name in declared or []]


def _reaches_a_precondition(
    name: str, jobs: dict[str, Any], scripts: dict[str, list[tuple[str, bool]]]
) -> bool:
    """Say whether a graded job is gated by a precondition it cannot outrun.

    Args:
        name (str): The graded job's name.
        jobs (dict[str, Any]): Every job in the workflow.
        scripts (dict[str, list[tuple[str, bool]]]): Each job's commands.

    Returns:
        bool: True where an earlier step of the job itself runs a precondition,
        or where the jobs it needs reach one.
    """
    graded = next(
        (
            index
            for index, (command, elsewhere) in enumerate(scripts[name])
            if not elsewhere and _selected_layers(command) & set(_GRADED_LAYERS)
        ),
        0,
    )
    if _runs_a_precondition(scripts[name], before=graded):
        return True
    seen: set[str] = set()
    pending = _needed(jobs[name] or {})
    while pending:
        reached = pending.pop()
        if reached in seen or reached not in jobs:
            continue
        seen.add(reached)
        if _runs_a_precondition(scripts[reached], before=len(scripts[reached])):
            return True
        pending += _needed(jobs[reached] or {})
    return False
