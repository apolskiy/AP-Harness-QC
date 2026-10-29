# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Test helpers for the grouping tree: a planted repository, and a real reporter's labels.

Created: 2026-10-24
Last updated: 2026-10-28

This file provides ``plant_root``, which writes a repository whose declaration
and test tree are exactly what a case asks for; ``published_results``, which
runs one of this repository's modules under a real Allure reporter and returns
what it wrote; ``run_without_reporter``, which runs a module in a process where
every Allure import is refused; and ``BandItem``, a collected item carrying
only a node identifier and a priority, for the suite root a graded case takes.

**The label readers are in ``cmn.grouping`` rather than here**, because the
case repository asserts what a reporter wrote as well and the installed wheel
ships no tests, so a reader here would have to be copied there.

It serves the cases in ``mqc_uni_grouping.py``. They are here rather than in
that module because a collected module holds cases and nothing else
(``harness_test_taxonomy.md`` section 13).

**A planted root rather than this repository**, for the three checks about a
declaration going wrong: moving this repository's own declaration would leave
it wrong for every later case in the run.

**A real reporter rather than a double**, for the two checks about what
arrives. The labels are written by ``allure-pytest`` from markers a collection
hook adds, so a double would be asserting that this file's own idea of the
format is self-consistent (``cmn_verdict_and_cli.md`` section 5.1).

Specified by ``harness_test_taxonomy.md`` section 16.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Final, Optional

import pytest
import yaml

from cmn.mutation_guard import AUDIT_ENV

from tests.cmn.subprocess_support import run_bounded

# A MODULE HOLDING ONE CASE, which is what makes a planted file a module the
# capability check reads: a file defining no case needs no capability.
PLANTED_MODULE: Final[str] = '\n'.join([
    '"""A planted module holding one case."""',
    "",
    "",
    "class TestMQCPlanted:",
    '    """One case, so the module counts as holding cases."""',
    "",
    "    def MQC_CMN_UNI_112000_a_planted_case(self) -> None:",
    '        """Assert nothing.',
    "",
    "        Returns:",
    "            None",
    '        """',
    "",
]) + "\n"


def plant_root(
    base: Path,
    *,
    epic: str,
    features: list[str],
    declared: dict[str, str],
    modules: list[str],
) -> Path:
    """Write a repository with the declaration and the test tree given.

    Args:
        base (Path): The directory to build in, usually ``tmp_path``.
        epic (str): The epic to declare, empty to declare none.
        features (list): The vocabulary to declare.
        declared (dict): The module-to-capability map to declare, whose keys
            need not be modules that exist: an entry naming nothing is one of
            the things the check reports.
        modules (list): The test modules to write, by path relative to the
            root, each holding one case.

    Returns:
        Path: The planted root.
    """
    root = base / "planted"
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "ap-harness-qc"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    declaration: dict[str, Any] = {"features": list(features), "modules": dict(declared)}
    if epic:
        declaration["epic"] = epic
    (root / "config" / "allure_features.yaml").write_text(
        yaml.safe_dump(declaration, sort_keys=False), encoding="utf-8"
    )
    for relative in modules:
        module = root / relative
        module.parent.mkdir(parents=True, exist_ok=True)
        module.write_text(PLANTED_MODULE, encoding="utf-8")
    return root


def published_results(root: Path, module: str, results: Path) -> list[dict[str, Any]]:
    """Run one module under a real reporter and return the results it wrote.

    Args:
        root (Path): The repository root, which the run is made from so that
            its ``conftest.py`` and its declaration are the ones in force.
        module (str): The module to run, relative to the root.
        results (Path): Where the reporter writes, usually under ``tmp_path``.

    Returns:
        list[dict]: One parsed result per case that ran, in file order.
    """
    completed = run_bounded(
        [
            sys.executable, "-m", "pytest", str(root / module),
            "-q", "--no-header", "-p", "no:randomly",
            "--alluredir", str(results),
        ],
        cwd=root,
    )
    if completed.returncode != 0:
        printed = (completed.stdout + completed.stderr)[-700:]
        raise AssertionError(
            f"the probe run of {module} exited {completed.returncode}, so there is "
            f"nothing to read labels from:\n{printed}"
        )
    return [
        json.loads(written.read_text(encoding="utf-8"))
        for written in sorted(results.glob("*-result.json"))
    ]


# A PROCESS THAT REFUSES EVERY ALLURE IMPORT, which is what a machine without
# the reporting extra is. Written as a ``sitecustomize`` module, which Python
# imports before anything else on the path, so the refusal is in place before
# pytest loads a plugin or a conftest.
_BLOCKER: Final[str] = '''"""Refuse every Allure import, so a run can be measured without one."""

import sys
from importlib.abc import MetaPathFinder

BLOCKED = ("allure", "allure_commons", "allure_pytest")


class Refuse(MetaPathFinder):
    """Raise ImportError for the reporting packages."""

    def find_spec(self, fullname, path=None, target=None):
        """Refuse a blocked name and decline every other.

        Args:
            fullname (str): The module being imported.
            path: Unused.
            target: Unused.

        Returns:
            None: For a name this finder does not handle.
        """
        del path, target
        if fullname.split(".")[0] in BLOCKED:
            raise ImportError(f"no reporting extra installed: {fullname}")
        return None


sys.meta_path.insert(0, Refuse())
'''


def run_without_reporter(
    root: Path, module: str, base: Path
) -> subprocess.CompletedProcess[str]:
    """Run one module in a process where no Allure import can succeed.

    **The plugin is disabled as well as the imports refused.** On a machine
    with no reporting extra there is no plugin to auto-load, and leaving the
    installed one enabled would fail at plugin load rather than measuring what
    a run does without it.

    Args:
        root (Path): The repository root, run from so its conftest is in force.
        module (str): The module to run, relative to the root.
        base (Path): A directory to write the blocker into, usually
            ``tmp_path``.

    Returns:
        subprocess.CompletedProcess[str]: The finished run, whatever its exit
        code: its output is the evidence either way.
    """
    (base / "sitecustomize.py").write_text(_BLOCKER, encoding="utf-8", newline="\n")
    return run_bounded(
        [
            sys.executable, "-m", "pytest", str(root / module),
            "-q", "--no-header", "-p", "no:randomly", "-p", "no:allure_pytest",
        ],
        cwd=root,
        env={
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": os.pathsep.join([str(base), str(root)]),
            # THIS AUDIT'S OWN MARKER, FORWARDED. A mutation audit holds a lock
            # beside the module it is measuring, and a run that cannot show the
            # audit's process id refuses rather than importing a held module
            # (harness_test_taxonomy.md section 15.12). The environment here is
            # minimal on purpose, and stripping this turned a case into one
            # that cannot pass inside an audit.
            **({AUDIT_ENV: os.environ[AUDIT_ENV]} if AUDIT_ENV in os.environ else {}),
        },
    )


class BandItem:
    """A collected item as the band hook reads one, carrying what it reads.

    **A stub rather than a real reporter, for the graded path only.** The suite
    root a precondition takes is asserted against a real reporter, this
    repository having preconditions; the root a graded case takes cannot be,
    because the harness owns no corpus and therefore no graded case. The case
    repository asserts the graded root against a reporter of its own.

    Attributes:
        nodeid (str): The node identifier, which decides whether an item
            carrying no priority is a precondition.
        added (list): Every marker the hook added, in the order it added them.
    """

    def __init__(self, nodeid: str, priority: Optional[int] = None) -> None:
        """Store the identifier and the priority the item carries.

        Args:
            nodeid (str): The node identifier.
            priority (Optional[int]): The level, or ``None`` for an item
                carrying no priority marker at all.

        Returns:
            None
        """
        self.nodeid = nodeid
        self.added: list[Any] = []
        self._priority = priority

    def get_closest_marker(self, name: str) -> Optional[Any]:
        """Return the priority marker where one was declared.

        Args:
            name (str): The marker name the hook asks for.

        Returns:
            Optional[Any]: The mark, or ``None``.
        """
        if name == "priority" and self._priority is not None:
            return pytest.mark.priority(self._priority).mark
        return None

    def iter_markers(self, name: str = "") -> list[Any]:
        """Return the marks already on the item, filtered by name.

        Args:
            name (str): The marker name, empty for all of them.

        Returns:
            list[Any]: The matching marks.
        """
        marks = [decorator.mark for decorator in self.added]
        return [mark for mark in marks if not name or mark.name == name]

    def add_marker(self, marker: Any) -> None:
        """Record a marker the hook added.

        Args:
            marker (Any): The marker decorator.

        Returns:
            None
        """
        self.added.append(marker)

    def labels(self, label_type: str) -> list[str]:
        """Return every value the item was labelled with, for one label type.

        Args:
            label_type (str): The Allure label type, such as ``parentSuite``.

        Returns:
            list[str]: The values, in the order they were added.
        """
        return [
            str(mark.args[0])
            for mark in self.iter_markers(name="allure_label")
            if mark.kwargs.get("label_type") == label_type
        ]
