# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Test helpers for planted CI definitions: a workflow body, and a root to put it in.

Created: 2026-10-28
Last updated: 2026-10-28

This file provides ``pinned_workflow``, which returns a one-job workflow naming
a given runner; ``gated_workflow``, which returns a fan-out workflow whose
summary job carries a given condition behind a job gated on the triggering
run's conclusion; and ``plant_root``, which writes a workflow and an optional
``actionlint`` declaration into a repository root a case hands it.

It serves the cases in ``mqc_uni_runner_images.py`` and
``mqc_uni_graded_selection.py``. They are here rather than in those modules
because a collected module holds cases and nothing else
(``harness_test_taxonomy.md`` section 13).

**A planted root rather than this repository**, because each case asks for a
definition this repository does not contain and must not: a label that moves, a
second operating system version, a summary job reporting a run nothing earned.

Specified by ``docs/design/harness_ci_pipeline.md`` sections 8.7 and 8.8.
"""

from pathlib import Path

# THE DECLARATION THAT MAKES A PIN LINTABLE, as `.github/actionlint.yaml`
# carries it. A case appends a second label to plant a stale declaration.
DECLARED_PIN: str = "self-hosted-runner:\n  labels:\n    - ubuntu-26.04\n"


def pinned_workflow(runner: str) -> str:
    """Return a one-job workflow naming the given runner.

    Args:
        runner (str): The ``runs-on`` value to write.

    Returns:
        str: A complete workflow definition.
    """
    return "\n".join([
        "name: gate",
        "on:",
        "  workflow_dispatch:",
        "jobs:",
        "  build:",
        f"    runs-on: {runner}",
        "    steps:",
        "      - run: echo built",
    ]) + "\n"


def matrix_workflow(runners: str) -> str:
    """Return a workflow naming its runners through a matrix.

    Args:
        runners (str): The ``os`` list, written as a YAML flow sequence.

    Returns:
        str: A complete workflow definition whose ``runs-on`` is an expression.
    """
    return "\n".join([
        "name: gate",
        "on:",
        "  workflow_dispatch:",
        "jobs:",
        "  build:",
        "    strategy:",
        "      matrix:",
        f"        os: {runners}",
        "    runs-on: ${{ matrix.os }}",
        "    steps:",
        "      - run: echo built",
    ]) + "\n"


def gated_workflow(condition: str) -> str:
    """Return a fan-out workflow whose summary job carries the given condition.

    The ``enumerate`` job is gated on the triggering run's conclusion, which is
    the shape section 8.8 reads: the summary job's condition is what decides
    whether a run that fanned out to nothing reports success.

    Args:
        condition (str): The ``if`` value written on the summary job.

    Returns:
        str: A complete workflow definition, triggered by ``workflow_run``.
    """
    return "\n".join([
        "name: fan-out",
        "on:",
        "  workflow_run:",
        "    workflows: [gate-on-change]",
        "    types: [completed]",
        "jobs:",
        "  enumerate:",
        "    if: >-",
        "      github.event_name != 'workflow_run' ||",
        "      github.event.workflow_run.conclusion == 'success'",
        "    runs-on: ubuntu-26.04",
        "    steps:",
        "      - run: echo enumerated",
        "  verify:",
        "    needs: enumerate",
        "    runs-on: ubuntu-26.04",
        "    steps:",
        "      - run: echo verified",
        "  report:",
        "    needs: [enumerate, verify]",
        f"    if: {condition}",
        "    runs-on: ubuntu-26.04",
        "    steps:",
        "      - run: echo reported",
    ]) + "\n"


def plant_root(
    root: Path, workflow: str, *, declaration: str = "", name: str = "gate.yml"
) -> Path:
    """Write a workflow, and optionally a lint declaration, into a root.

    Args:
        root (Path): Where to build the planted repository.
        workflow (str): The workflow body.
        declaration (str): The ``actionlint`` configuration body, empty for none.
        name (str): The workflow's file name.

    Returns:
        Path: The planted root, for handing straight to a check.
    """
    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (root / ".github" / "workflows" / name).write_text(
        workflow, encoding="utf-8"
    )
    if declaration:
        (root / ".github" / "actionlint.yaml").write_text(
            declaration, encoding="utf-8"
        )
    return root
