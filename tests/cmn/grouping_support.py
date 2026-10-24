# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Test helpers for the grouping tree: a planted repository, and a real reporter's labels.

Created: 2026-10-24
Last updated: 2026-10-24

This file provides ``plant_root``, which writes a repository whose declaration
and test tree are exactly what a case asks for; ``published_results``, which
runs one of this repository's modules under a real Allure reporter and returns
what it wrote; ``label_values`` and ``sole_label``, which read one label type
out of a published result; and ``run_without_reporter``, which runs a module in
a process where every Allure import is refused.

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

import yaml

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


def label_values(result: dict[str, Any], name: str) -> list[str]:
    """Return every value a result carries for one label type.

    **A list rather than a value**, because the defect this exists to catch is
    a second label of the same type: Allure unions them and the report grows a
    branch for each (``harness_test_taxonomy.md`` section 16.2.1).

    Args:
        result (dict): A parsed Allure result.
        name (str): The label type, such as ``feature``.

    Returns:
        list[str]: The values, empty where the result carries none.
    """
    return [
        str(label.get("value") or "")
        for label in result.get("labels") or []
        if label.get("name") == name
    ]


def sole_label(result: dict[str, Any], name: str) -> Optional[str]:
    """Return the one value a result carries for a label type.

    Args:
        result (dict): A parsed Allure result.
        name (str): The label type.

    Returns:
        Optional[str]: The value, or ``None`` where the result carries no
        label of that type or carries more than one.
    """
    values = label_values(result, name)
    return values[0] if len(values) == 1 else None


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
        },
    )
