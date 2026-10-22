# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Test helpers that build a synthetic module and manifest for the mutation audit cases.

Created: 2026-10-14
Last updated: 2026-10-21

This file provides ``write_manifest``, ``harness_tree`` and ``pointed_tree``, which
lay out a small harness with a declared digest, ``hold_module``, ``exited_pid`` and
``write_stop_request``, which stage a live or abandoned audit and a stop request,
pytest stand-ins in ``AuditItem``, ``AuditConfig`` and ``launcher``, and
``restored_baseline``, which checks a module was put back.

They serve ``mqc_uni_mutation_tool.py``, ``mqc_uni_mutation_guard.py`` and
``mqc_uni_mutation_stop.py``, so those cases audit a throwaway module rather than
a production one.

**A sibling module collection does not reach**, per `MQC_CMN_UNI_112328`: a
collected module holds cases and nothing else.

This exists so `MQC_CMN_UNI_112363` and `112364` can work against a synthetic
module rather than a production one. Auditing a real module from a case would
run the suite inside the suite, which is what the `MUT` layer is for and what
section 15.7 keeps in a job of its own.
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from cmn.mutation_guard import BACKUP_SUFFIX, LOCK_SUFFIX, STOP_REQUEST, module_digest
from tests.cmn.environment_doubles import Hook
from tests.cmn.file_dates_support import git_in

# A MODULE CARRYING SOMETHING THE UNPARSE STRIPS. A comment and the blank
# lines are the point: a fixture that round-trips identically would make
# `112363` vacuous, so the case asserts the difference before relying on it.
MODULE = "cmn/sample.py"
SOURCE = '''# a comment the unparse strips
"""A module with something to hash."""


def doubled(value: int) -> int:
    """Return twice the value."""
    return value * 2
'''


def write_manifest(root: Path, digest: str) -> Path:
    """Write a manifest declaring one module's baseline.

    Args:
        root (Path): The directory to write into.
        digest (str): The digest to declare for :data:`MODULE`.

    Returns:
        Path: The manifest that was written.
    """
    path = root / "mutation_survivors.yaml"
    path.write_text(
        f"survivors:\n  {MODULE}:\n    digest: {digest}\n",
        encoding="utf-8", newline="\n",
    )
    return path


def harness_tree(root: Path, digest: str) -> Path:
    """Lay out a harness root holding :data:`MODULE` and a manifest declaring a digest.

    Args:
        root (Path): The directory to treat as the harness root.
        digest (str): The digest the manifest declares for :data:`MODULE`.

    Returns:
        Path: The module, holding :data:`SOURCE`.
    """
    module = root / MODULE
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text(SOURCE, encoding="utf-8", newline="\n")
    (root / "config").mkdir(exist_ok=True)
    write_manifest(root / "config", digest)
    return module


def hold_module(module: Path, pid: int) -> tuple[Path, Path]:
    """Leave a backup of :data:`SOURCE` and a lock naming a process beside a module.

    Args:
        module (Path): The module to hold.
        pid (int): The process the lock names.

    Returns:
        tuple[Path, Path]: The backup and the lock.
    """
    backup = module.with_name(module.name + BACKUP_SUFFIX)
    backup.write_text(SOURCE, encoding="utf-8", newline="\n")
    lock = module.with_name(module.name + LOCK_SUFFIX)
    lock.write_text(json.dumps({"pid": pid, "started": "2026-10-18T14:23:01+00:00"}),
                    encoding="utf-8")
    return backup, lock


def exited_pid() -> int:
    """Return the id of a process that has already exited.

    Returns:
        int: The pid of a child that ran and finished.
    """
    finished = subprocess.run(
        [sys.executable, "-c", "import os; print(os.getpid())"],
        capture_output=True, text=True, check=True, timeout=60,
        stdin=subprocess.DEVNULL,
    )
    return int(finished.stdout.strip())


# A MODULE WITH SEVERAL POINTS, so a stop can land between two of them.
POINTED = '''"""A module with several mutation points."""


def clipped(value: int) -> int:
    """Return the value doubled, or zero when it is not positive."""
    return value * 2 if value > 0 else 0
'''


def pointed_tree(root: Path) -> Path:
    """Lay out a harness root holding :data:`POINTED` and a manifest declaring its digest.

    Args:
        root (Path): The directory to treat as the harness root.

    Returns:
        Path: The module, holding :data:`POINTED`.
    """
    module = root / MODULE
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text(POINTED, encoding="utf-8", newline="\n")
    (root / "config").mkdir(exist_ok=True)
    write_manifest(root / "config", module_digest(POINTED))
    return module


# THE ONE POINT `committed_survivor_tree` DECLARES AS A SURVIVOR: the doubling
# constant on line 6 of `POINTED`.
POINTED_SURVIVOR = "line 6: 2 to 3"


def committed_survivor_tree(root: Path) -> Path:
    """Lay out :data:`POINTED` with one survivor declared, in a committed git repository.

    Args:
        root (Path): The directory to treat as the harness root.

    Returns:
        Path: The module, holding :data:`POINTED`.
    """
    module = pointed_tree(root)
    manifest = root / "config" / "mutation_survivors.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        + f'    accepted:\n      - mutation: "{POINTED_SURVIVOR}"\n        kind: equivalent\n'
        "        reason: planted\n        expires_on: 2999-12-31\n",
        encoding="utf-8", newline="\n",
    )
    for arguments in (["init", "--quiet"], ["add", "."], ["commit", "--quiet", "-m", "measured"]):
        git_in(root, *arguments)
    return module


# THE SIBLING A PAIRED CASE NEEDS, planted beside the harness root so a copy can
# be checked for seeing it.
SIBLING = "AP-Model-QC"
SIBLING_MARKER = "marker.txt"


def isolated_launcher(
    module: Path, seen: dict[str, list[Any]]
) -> Callable[..., subprocess.CompletedProcess]:
    """Return a process launcher recording where each run happened and what it could see.

    The control passes. A point survives only where its copy's module doubles
    by three, which is the one mutant of :data:`POINTED` no case is meant to
    kill. Every run sleeps briefly, so two workers both take points.

    Args:
        module (Path): The repository's own module, checked untouched and held
            by an isolated lock at every run.
        seen (dict): Lists under ``cwd``, ``untouched`` and ``sibling``, appended per run.

    Returns:
        Callable: The launcher, standing in for :func:`subprocess.run`.
    """

    def launched(command: list[str], **options: Any) -> subprocess.CompletedProcess:
        here = Path(options["cwd"])
        seen["cwd"].append(here)
        seen["untouched"].append(
            module_digest(module.read_text(encoding="utf-8")) == module_digest(POINTED)
            and not module.with_name(module.name + BACKUP_SUFFIX).exists()
            and json.loads(module.with_name(module.name + LOCK_SUFFIX).read_text(
                encoding="utf-8")).get("isolated") is True
        )
        seen["sibling"].append((here.parent / SIBLING / SIBLING_MARKER).is_file())
        time.sleep(0.05)
        if "-x" not in command:
            return subprocess.CompletedProcess(command, 0, "1 passed", "")
        survived = "value * 3" in (here / MODULE).read_text(encoding="utf-8")
        return subprocess.CompletedProcess(command, 0 if survived else 1, "", "")

    return launched


def seeing_tree(root: Path) -> dict[str, Path]:
    """Lay out a module, a helper importing it, and three test modules that see it or not.

    Args:
        root (Path): The directory to treat as the harness root.

    Returns:
        dict: ``module``, ``direct``, ``indirect`` and ``blind``, each a path.
    """
    module = pointed_tree(root)
    (root / "cmn" / "__init__.py").write_text("", encoding="utf-8")
    (root / "cmn" / "helper.py").write_text(
        "from cmn.sample import clipped\n\n\ndef twice(value):\n    return clipped(value)\n",
        encoding="utf-8",
    )
    tests = root / "tests"
    tests.mkdir()
    files = {
        "direct": "import cmn.sample\n",
        "indirect": "from cmn import helper\n",
        "blind": "import json\n",
    }
    paths = {"module": module}
    for name, body in files.items():
        paths[name] = tests / f"mqc_uni_{name}.py"
        paths[name].write_text(body, encoding="utf-8")
    return paths


def subset_launcher(
    calls: list[list[str]], survive_subset: str
) -> Callable[..., subprocess.CompletedProcess]:
    """Return a launcher where one mutant survives the seeing cases and the full suite kills it.

    Args:
        calls (list): Each command launched, appended in order.
        survive_subset (str): Text in the mutant that the seeing cases miss.

    Returns:
        Callable: The launcher, standing in for :func:`subprocess.run`.
    """

    def launched(command: list[str], **options: Any) -> subprocess.CompletedProcess:
        calls.append(command)
        if "-x" not in command:
            return subprocess.CompletedProcess(command, 0, "1 passed", "")
        subset = any(argument.endswith(".py") for argument in command)
        mutant = (Path(options["cwd"]) / MODULE).read_text(encoding="utf-8")
        missed = subset and survive_subset in mutant
        return subprocess.CompletedProcess(command, 0 if missed else 1, "", "")

    return launched


class AuditMarker:
    """The `mutation` marker, which carries nothing the selector reads."""


class AuditItem:
    """A collected case, carrying its name and whether it is an audit."""

    def __init__(self, name: str, *, audit: bool) -> None:
        """Hold the case.

        Args:
            name (str): The callable's name, carrying its identifier.
            audit (bool): Whether it carries the `mutation` marker.

        Returns:
            None
        """
        self.name = name
        self.nodeid = f"tests/x.py::T::{name}"
        self._audit = audit

    def get_closest_marker(self, name: str) -> Any:
        """Return the marker asked for, where the case carries it.

        Args:
            name (str): The marker name.

        Returns:
            Any: The marker, or None.
        """
        return AuditMarker() if self._audit and name == "mutation" else None


class AuditConfig:
    """The surface of pytest's configuration the audit selector reads."""

    def __init__(self, root: Path, args: list[str], options: dict[str, str]) -> None:
        """Hold the invocation.

        Args:
            root (Path): The repository root, also the invocation directory.
            args (list[str]): The positional arguments.
            options (dict): Option values by name, ``markexpr`` and ``--tests`` among them.

        Returns:
            None
        """
        self.rootpath = root
        self.args = args
        self.invocation_params = SimpleNamespace(dir=root)
        self._options = options
        self.hook = Hook()

    def getoption(self, name: str, default: Any = None) -> Any:
        """Return an option's value.

        Args:
            name (str): The option.
            default (Any): Returned where the option is unset.

        Returns:
            Any: The value.
        """
        return self._options.get(name, default)


def broken_subset_launcher() -> Callable[..., subprocess.CompletedProcess]:
    """Return a launcher where every run naming test files breaks, mutated or not.

    Returns:
        Callable: The launcher, standing in for :func:`subprocess.run`.
    """

    def launched(command: list[str], **options: Any) -> subprocess.CompletedProcess:
        del options
        named = [argument for argument in command if argument.endswith(".py")]
        if not named:
            return subprocess.CompletedProcess(command, 0, "3 passed", "")
        return subprocess.CompletedProcess(
            command, 3, f"FAILED {named[0]}::TestMQCDirect::MQC_CMN_UNI_119991_direct\n", ""
        )

    return launched


def launcher(
    calls: list[list[str]], on_point: Callable[[int], None]
) -> Callable[..., subprocess.CompletedProcess]:
    """Return a process launcher passing the control and killing every point.

    Args:
        calls (list): Each command launched, appended in order.
        on_point (Callable): Called with the point's number as it runs.

    Returns:
        Callable: The launcher, standing in for :func:`subprocess.run`.
    """

    def launched(command: list[str], **_: Any) -> subprocess.CompletedProcess:
        calls.append(command)
        if "-x" not in command:
            return subprocess.CompletedProcess(command, 0, "1 passed", "")
        on_point(len(calls) - 1)
        return subprocess.CompletedProcess(command, 1, "1 failed", "")

    return launched


def write_stop_request(root: Path, pids: list[int]) -> Path:
    """Write a stop request naming processes, as the stop command does.

    Args:
        root (Path): The harness root.
        pids (list[int]): The processes named.

    Returns:
        Path: The request.
    """
    request = root / STOP_REQUEST
    request.parent.mkdir(parents=True, exist_ok=True)
    request.write_text(json.dumps({"pids": pids, "requested": "2026-10-20T21:14:00Z"}),
                       encoding="utf-8", newline="\n")
    return request


def restored_baseline(module: Path) -> bool:
    """Report whether a module is its baseline, with no backup and no lock beside it.

    Args:
        module (Path): The module.

    Returns:
        bool: True when nothing an audit leaves is left.
    """
    return (
        module_digest(module.read_text(encoding="utf-8")) == module_digest(POINTED)
        and not module.with_name(module.name + BACKUP_SUFFIX).exists()
        and not module.with_name(module.name + LOCK_SUFFIX).exists()
    )
