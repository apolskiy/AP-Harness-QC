# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The runner image every workflow names, checked against the pin before a push.

Created: 2026-10-28
Last updated: 2026-10-28

This file contains ``unpinned_runner_images``, which reports a runner label
disagreeing with the image the project pins, and the readers it needs:
``_runner_labels``, which collects the labels a job names directly and through
its matrix, ``_declared_runner_labels``, which reads what the linter was told,
and ``_pin_disagreements``, which compares the two.

A precondition case in each repository calls it with that repository's root, so
a workflow naming a label that moves, a second operating system version, or a
version the linter does not know fails the unit layer locally rather than
turning a lint job red and skipping every job behind it.

Four things are reported and the last two are a pair: the declaration exists
only to make the pin lintable, so the pin and the declaration are compared with
each other rather than each with a constant. Moving the pin is then a sweep and
one line, and omitting either half fails here.

Specified by ``docs/design/harness_ci_pipeline.md`` section 8.7.

**Its own module rather than a subject in ``workflow_standards.py``**, which
reached its nine-hundred-line runway as this was written (``code-style.md``
section 5.1). That is the same reason ``ci_gating.py`` was split off, and the
subjects divide: that module reads what a step names, and this one reads where
a job runs.
"""

import re
from pathlib import Path
from typing import Any, Final

import yaml

# THE RUNNER IMAGE THE PROJECT PINS, by its family rather than by its version:
# the version is whatever the workflows agree on, so moving the pin is a sweep
# and a declaration rather than an edit here. `DESIGN.md` section 5.0 pins
# Ubuntu and leaves the Windows label moving, which is why only one family is
# the subject.
_PINNED_FAMILY: Final[str] = "ubuntu-"

# A LABEL CARRYING A VERSION, against one that moves under the project.
# `ubuntu-latest` and `ubuntu-slim` match the family and not this.
_VERSIONED_IMAGE: Final[re.Pattern] = re.compile(
    r"^ubuntu-(?P<version>\d{2}\.\d{2})(?:-[a-z0-9]+)?$"
)

# WHERE THE LINTER IS TOLD ABOUT A LABEL IT DOES NOT SHIP WITH. `actionlint`
# validates `runs-on` against a list compiled into the binary, so an image
# newer than the release is an unknown label and the lint job refuses the file
# (`harness_ci_pipeline.md` section 3.1.2.2). Both spellings, because the tool
# accepts either and a repository picking the other would read as undeclared.
_LINT_CONFIGS: Final[tuple[str, ...]] = ("actionlint.yaml", "actionlint.yml")
_SELF_HOSTED: Final[str] = "self-hosted-runner"


def unpinned_runner_images(root: Path) -> list[str]:
    """Report every workflow runner label that disagrees with the pin.

    Reads each job's ``runs-on``, as a scalar or a list, and the ``os`` values
    of a matrix, including those an ``include:`` entry carries. Four things are
    reported: a label in the pinned family carrying no version, a second
    version anywhere in the repository, a version no ``actionlint``
    configuration declares, and a declaration no workflow names. An expression
    is not a label and is skipped, the matrix it reads being collected already.

    Design: ``harness_ci_pipeline.md`` section 8.7.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per problem, naming the label and where it is.
    """
    named: dict[str, list[str]] = {}
    for workflow in sorted((root / ".github" / "workflows").glob("*.yml")):
        definition = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        if not isinstance(definition, dict):
            continue
        jobs = definition.get("jobs")
        for job_name, job in (jobs if isinstance(jobs, dict) else {}).items():
            for label in _runner_labels(job):
                if label.startswith(_PINNED_FAMILY):
                    named.setdefault(label, []).append(
                        f"{workflow.name}: job {job_name}"
                    )
    return _pin_disagreements(named, _declared_runner_labels(root))


def _pin_disagreements(
    named: dict[str, list[str]], declared: set[str]
) -> list[str]:
    """Compare the labels the workflows name with the ones declared.

    Args:
        named (dict[str, list[str]]): Each label, and where it is named.
        declared (set[str]): The labels an ``actionlint`` configuration holds.

    Returns:
        list[str]: One entry per problem, in the order the classes are checked.
    """
    problems: list[str] = []
    versions: dict[str, str] = {}
    for label, sites in sorted(named.items()):
        matched = _VERSIONED_IMAGE.match(label)
        if matched is None:
            problems.append(
                f"{sites[0]}: runs on {label}, which names no version and so "
                f"moves under the project; DESIGN.md section 5.0.2 pins the "
                f"image deliberately, and a label that migrates can land two "
                f"runs of one commit on different operating system majors"
            )
            continue
        versions[label] = matched.group("version")
    distinct = sorted(set(versions.values()))
    if len(distinct) > 1:
        problems.append(
            f"the workflows name {len(distinct)} Ubuntu versions at once, "
            f"{', '.join(distinct)}; one gate running two majors compares "
            f"platforms rather than code, so a sweep that moved the pin "
            f"missed a line"
        )
    for label in sorted(set(versions) - declared):
        problems.append(
            f"{named[label][0]}: runs on {label}, which no .github/"
            f"actionlint.yaml declares; actionlint validates runs-on against "
            f"the labels of its own release, so it reports an image newer "
            f"than the binary as unknown and the lint job refuses the file"
        )
    for label in sorted(declared - set(named)):
        problems.append(
            f".github/actionlint.yaml declares {label}, which no workflow "
            f"names; a declaration left behind by a pin that moved accepts a "
            f"label nothing runs on"
        )
    return problems


def _runner_labels(job: Any) -> list[str]:
    """Return every runner label a job names, directly or through its matrix.

    Args:
        job (Any): One job of a parsed workflow definition.

    Returns:
        list[str]: The labels found, without expressions and without duplicates.
    """
    if not isinstance(job, dict):
        return []
    found: list[str] = []
    runner = job.get("runs-on")
    candidates = runner if isinstance(runner, list) else [runner]
    strategy = job.get("strategy")
    matrix = strategy.get("matrix") if isinstance(strategy, dict) else None
    if isinstance(matrix, dict):
        platforms = matrix.get("os")
        candidates += platforms if isinstance(platforms, list) else [platforms]
        included = matrix.get("include")
        for entry in included if isinstance(included, list) else []:
            if isinstance(entry, dict):
                candidates.append(entry.get("os"))
    for candidate in candidates:
        if isinstance(candidate, str) and "${{" not in candidate:
            if candidate not in found:
                found.append(candidate)
    return found


def _declared_runner_labels(root: Path) -> set[str]:
    """Return the labels an ``actionlint`` configuration declares.

    Args:
        root (Path): The repository root.

    Returns:
        set[str]: The declared labels, empty where no configuration exists.
    """
    declared: set[str] = set()
    for name in _LINT_CONFIGS:
        source = root / ".github" / name
        if not source.is_file():
            continue
        parsed = yaml.safe_load(source.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            continue
        section = parsed.get(_SELF_HOSTED)
        labels = section.get("labels") if isinstance(section, dict) else None
        declared.update(
            entry for entry in (labels or []) if isinstance(entry, str)
        )
    return declared
