# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Whether a CI definition gates what it runs, read before a push.

Created: 2026-10-25
Last updated: 2026-10-29

This file contains ``ungated_graded_jobs``, which reports a job that runs
graded cases out of this repository's checkout and reaches no precondition
invocation, and the readers it needs: ``_job_scripts``, which follows a local
``uses:`` into a composite action, ``_selected_layers``, which reads a marker
expression, and ``_reaches_a_precondition``, which walks a job's ``needs:``.
It also contains ``unearned_run_conclusions``, which reports a job that would
give a run a conclusion its workflow did not earn, having run alone while the
job gated on the triggering run's conclusion was skipped, and
``ungated_dispatches``, which reports a job that starts a workflow that spends
without reading a green pairing from a job it needs.

**The two gating checks ask different questions of different jobs.**
``ungated_graded_jobs`` asks whether a job that measures a model reaches a
verified instrument; ``ungated_dispatches`` asks whether a job that makes
another workflow measure one does. A job of the second kind runs no case, so
the first check passes it in silence.

A precondition case in each repository calls it with that repository's root, so
a workflow that would measure a model with an unchecked instrument fails the
unit layer locally rather than spending quota in CI to find out.

**Its own module rather than a subject in ``workflow_standards.py``**, which
reached its nine-hundred-line runway as this was written. The subjects divide
cleanly: that module reads what a definition says, a pylint path list or a
spending ceiling, and this one reads what stands in front of a job.

Specified by ``docs/design/harness_ci_pipeline.md`` sections 8.6 and 8.9.
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

# THE TRIGGER THAT CARRIES ANOTHER RUN'S OUTCOME, and the expression a job
# reads it with. A workflow fired any other way has no conclusion to gate on,
# so section 8.8 has nothing to say about it.
_TRIGGER: Final[str] = "workflow_run"
_TRIGGER_CONCLUSION: Final[re.Pattern] = re.compile(
    r"github\.event\.workflow_run\.conclusion"
)

# THE CONDITION THAT SURVIVES A SKIPPED PREREQUISITE, which is what a summary
# job wants and what makes it report a run nothing earned (section 8.8.2).
_ALWAYS: Final[str] = "always()"

# THE TWO WAYS A JOB STARTS ANOTHER WORKFLOW, the command line and the API.
# Both are read because a job using the second would otherwise look like a job
# that dispatches nothing (design section 8.9).
_DISPATCH: Final[re.Pattern] = re.compile(
    r"gh\s+workflow\s+run|/actions/workflows/[^\s]+/dispatches"
)

# A DISPATCH NAMING A REPOSITORY THAT IS NOT THIS ONE. The expression for this
# repository is permitted, because a job dispatching into its own repository is
# spending its own quota and is this check's subject; anything else belongs to
# the repository that owns the pairing.
_FOREIGN_REPOSITORY: Final[re.Pattern] = re.compile(
    r"--repo[=\s]+(?!\"?\$\{\{\s*github\.repository\s*\}\})"
)

# WHAT A GATED CONDITION READS, with the spaces already removed from both
# sides so `needs.resolve.outputs.green=='true'` and the spaced form are one
# comparison.
_GREEN_PAIRING: Final[str] = "needs.{job}.outputs.green"


def unearned_run_conclusions(root: Path) -> list[str]:
    """Report every job that would conclude a run its workflow did not earn.

    A workflow triggered by ``workflow_run`` whose work is gated on the
    triggering run's conclusion has a job deciding whether there is anything to
    do. A job that calls ``always()``, depends on that gated job and names
    nothing about its result runs anyway, and a run whose only completed job
    succeeded concludes success although nothing ran.

    **``always()`` is not itself the defect**, being what lets a summary job
    report a fan-out that failed. What is reported is ``always()`` paired with
    no mention of the gated job's ``result``; a job taking ``needs:`` without
    ``always()`` is skipped by ``needs`` and satisfies this already.

    **The comparison is not prescribed.** The condition has to mention the
    gated job's ``result`` and may test it however it likes, because the shapes
    that are correct here are not enumerable in advance.

    Design: ``harness_ci_pipeline.md`` section 8.8.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per job, naming the workflow, the job, the gated
        job it depends on and its condition.
    """
    gaps: list[str] = []
    for path in sorted((root / ".github" / "workflows").glob("*.yml")):
        parsed = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        triggers = parsed.get("on", parsed.get(True)) or {}
        if not isinstance(triggers, dict) or _TRIGGER not in triggers:
            continue
        jobs: dict[str, Any] = parsed.get("jobs") or {}
        gated = [
            name
            for name, body in jobs.items()
            if _TRIGGER_CONCLUSION.search(_condition(body))
        ]
        for name, body in jobs.items():
            condition = _condition(body)
            if name in gated or _ALWAYS not in condition:
                continue
            for decider in gated:
                if decider not in _reached(name, jobs):
                    continue
                if f"needs.{decider}.result" in condition:
                    continue
                gaps.append(
                    f"{path.name} job {name!r} runs on {_ALWAYS} and depends "
                    f"on {decider!r}, which is gated on the triggering run's "
                    f"conclusion, without naming its result: a gate that did "
                    f"not conclude success skips {decider!r} and this job "
                    f"runs alone, so the run concludes success having "
                    f"established nothing"
                )
    return gaps


def _condition(job: Any) -> str:
    """Return a job's condition as text.

    Args:
        job (Any): One job of a parsed workflow definition.

    Returns:
        str: The ``if`` value, or empty where the job declares none.
    """
    if not isinstance(job, dict):
        return ""
    return str(job.get("if") or "")


def _reached(name: str, jobs: dict[str, Any]) -> set[str]:
    """Return every job a job depends on, directly or through another.

    Args:
        name (str): The job to walk from.
        jobs (dict[str, Any]): Every job in the workflow.

    Returns:
        set[str]: The jobs reached, not including the one walked from.
    """
    seen: set[str] = set()
    pending = _needed(jobs.get(name) or {})
    while pending:
        reached = pending.pop()
        if reached in seen or reached not in jobs:
            continue
        seen.add(reached)
        pending += _needed(jobs[reached] or {})
    return seen


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


def ungated_dispatches(root: Path) -> list[str]:
    """Report every job dispatching a spending workflow with no green pairing.

    Section 8.6 gates a job that **runs** graded cases on the preconditions.
    This gates a job that **causes** graded cases to run elsewhere on the
    instrument having been verified, which neither covers nor is covered by
    the other: a red there means nothing was measured, and a red here means
    nothing was dispatched and nothing was spent.

    **A dispatch into another repository is out of scope**, and belongs to the
    repository that owns the pairing. That is the boundary section 8.6.3 draws:
    a job reaching another repository is measuring that repository's subject,
    and only the repository holding the pin can say whether a harness is green.

    Design: ``harness_ci_pipeline.md`` section 8.9.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per job, naming the file, the job and what it
        needs. Empty where every dispatching job reads a green pairing, and
        empty against a root with no pin of its own, which is why this reports
        nothing here and is called from both repositories.
    """
    gaps: list[str] = []
    for path in sorted((root / ".github" / "workflows").glob("*.yml")):
        if path.name.endswith(_ON_DEMAND_SUFFIX):
            continue
        parsed = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        jobs: dict[str, Any] = parsed.get("jobs") or {}
        for name, body in jobs.items():
            scripts = _job_scripts(root, body or {})
            if not _dispatches_a_workflow(scripts):
                continue
            if _reads_a_green_pairing(name, jobs):
                continue
            needed = ", ".join(_needed(jobs[name] or {})) or "nothing"
            gaps.append(
                f"{path.name} job {name!r} dispatches a workflow that spends "
                f"and reads no green pairing: it needs {needed}, so it would "
                f"spend against a harness nothing verified"
            )
    return gaps


def _dispatches_a_workflow(scripts: list[tuple[str, bool]]) -> bool:
    """Say whether a job dispatches a workflow in its own repository.

    Args:
        scripts (list[tuple[str, bool]]): Each command, and whether it runs in
            a checkout the job fetched.

    Returns:
        bool: True where a command of this job's own dispatches a workflow and
        does not name another repository to dispatch into.
    """
    return any(
        not elsewhere
        and _DISPATCH.search(command)
        and not _FOREIGN_REPOSITORY.search(command)
        for command, elsewhere in scripts
    )


def _reads_a_green_pairing(name: str, jobs: dict[str, Any]) -> bool:
    """Say whether a job's condition reads a green pairing from a job it needs.

    Args:
        name (str): The dispatching job's name.
        jobs (dict[str, Any]): Every job in the workflow.

    Returns:
        bool: True where the condition names the ``green`` output of a job this
        one reaches. **The job it needs, not any job**: a condition reading an
        output of something that does not gate it would not stop the dispatch.
    """
    condition = _condition(jobs.get(name))
    if not condition:
        return False
    return any(
        _GREEN_PAIRING.format(job=reached) in condition.replace(" ", "")
        for reached in _reached(name, jobs)
    )


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
