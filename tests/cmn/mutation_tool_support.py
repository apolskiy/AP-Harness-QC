# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""A manifest and a module to hash, for the baseline cases.

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
from pathlib import Path

from cmn.mutation_guard import BACKUP_SUFFIX, LOCK_SUFFIX

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
