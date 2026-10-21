# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Mutation re-declaration, which re-declares an audited module whose code did not change.

Created: 2026-10-21
Last updated: 2026-10-21

This file contains ``measured_version``, which finds the committed text of a
module that hashes to its declared digest; ``redeclare``, which writes a
module's new digest and moves each declared survivor to the line its mutation
point now sits on, refusing whenever only an audit can answer; and ``main``,
the command line.

**An author runs it after editing only the docstrings or comments of a module
named in ``config/mutation_survivors.yaml``**, in place of that module's
mutation audit, which costs minutes to an hour::

    python -m tools.mutation_redeclare cmn/verdict.py

It exits 0 once re-declared and 4 when it refuses: the code changed, the
module reads as its own unparse, the measured version is not in history, or a
backup or lock sits beside the module. ``MQC_CMN_UNI_112422`` asserts each.

Specified by ``docs/design/harness_test_taxonomy.md`` section 15.14. Moved out
of ``tools/mutation_audit.py`` the day it was written, when that module reached
the 900-line runway (``code-style.md`` section 5.1).
"""

import argparse
import ast
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Final, Optional

from cmn.mutation_guard import BACKUP_SUFFIX, LOCK_SUFFIX, behaviour_fingerprint, module_digest
from tools.mutation_audit import (
    MutationRefusal,
    declare_digest,
    declared_survivors,
    mutation_points,
)

logger = logging.getLogger(__name__)

_MANIFEST: Final[str] = "config/mutation_survivors.yaml"
_BACKUP_SUFFIX: Final[str] = BACKUP_SUFFIX
_LOCK_SUFFIX: Final[str] = LOCK_SUFFIX
_RUN_TIMEOUT_SEC: Final[int] = 600


# HOW FAR BACK A MEASURED VERSION IS LOOKED FOR, in commits touching the module.
_HISTORY_DEPTH: Final[int] = 200


def measured_version(root: Path, module: str, digest: str) -> Optional[str]:
    """Return the committed text of a module that hashes to a digest, or None.

    Args:
        root (Path): The repository root.
        module (str): The module path, relative to the root.
        digest (str): The declared digest.

    Returns:
        Optional[str]: The text, or None where no commit holds it.
    """
    listed = subprocess.run(
        ["git", "log", f"-{_HISTORY_DEPTH}", "--format=%H", "--", module],
        cwd=root, capture_output=True, text=True, encoding="utf-8", check=False,
        stdin=subprocess.DEVNULL, timeout=_RUN_TIMEOUT_SEC,
    )
    for commit in listed.stdout.split():
        shown = subprocess.run(
            ["git", "show", f"{commit}:{module}"], cwd=root, capture_output=True,
            text=True, encoding="utf-8", check=False, stdin=subprocess.DEVNULL,
            timeout=_RUN_TIMEOUT_SEC,
        )
        if shown.returncode == 0 and module_digest(shown.stdout) == digest:
            return shown.stdout
    return None


def _redeclare_refusal(root: Path, module: str, digest: str, text: str) -> Optional[str]:
    """Return why a module cannot be re-declared without an audit, or None.

    Args:
        root (Path): The repository root.
        module (str): The module path, as the declaration keys it.
        digest (str): The declared digest, empty when none is declared.
        text (str): The module's current text.

    Returns:
        Optional[str]: The refusal, or None when only prose changed.
    """
    refusal = "QC_HARNESS_AUDIT_REFUSED: " + module
    path = root / module
    if not digest:
        return f"{refusal} declares no digest, so nothing was measured; run its audit"
    for suffix in (_BACKUP_SUFFIX, _LOCK_SUFFIX):
        if path.with_suffix(path.suffix + suffix).exists():
            return f"{refusal} has a {suffix} beside it; an audit is running or died"
    if text == ast.unparse(ast.parse(text)):
        return (f"{refusal} reads exactly as its own unparse, which is the damage the "
                f"digest exists for (section 15.10); restore it from git")
    measured = measured_version(root, module, digest)
    if measured is None:
        return (f"{refusal}: no committed version hashes to {digest[:12]}, so nothing "
                f"establishes what was measured; commit the measured version or run its audit")
    if behaviour_fingerprint(measured) != behaviour_fingerprint(text):
        return f"{refusal}: its code changed since it was measured; run its audit"
    return None


def redeclare(root: Path, module: str) -> list[str]:
    """Re-declare a module whose code is unchanged since its survivors were measured.

    Writes the module's new digest and moves each declared survivor to the
    line its mutation point now sits on. Runs no mutant.

    Design: ``docs/design/harness_test_taxonomy.md`` section 15.14.

    Args:
        root (Path): The repository root.
        module (str): The module path, as the declaration keys it.

    Returns:
        list[str]: One line per survivor moved, empty when nothing changed.

    Raises:
        MutationRefusal: When the code changed, the module reads as its own
            unparse, the measured version is not in history, or a backup or
            lock sits beside it. Only an audit can answer those.
    """
    manifest = root / _MANIFEST
    declared = declared_survivors(manifest).get(module) or {}
    digest = str(declared.get("digest") or "")
    text = (root / module).read_text(encoding="utf-8")
    if digest and module_digest(text) == digest:
        return []
    refusal = _redeclare_refusal(root, module, digest, text)
    if refusal is not None:
        raise MutationRefusal(refusal)
    measured = measured_version(root, module, digest) or ""
    moved = _move_survivors(manifest, module, [
        (before.describe(), after.describe())
        for before, after in zip(mutation_points(measured), mutation_points(text))
    ])
    declare_digest(manifest, module, module_digest(text))
    return moved


def _move_survivors(manifest: Path, module: str, pairs: list[tuple[str, str]]) -> list[str]:
    """Rewrite each declared survivor of one module to its point's new line.

    Args:
        manifest (Path): ``config/mutation_survivors.yaml``.
        module (str): The module path, as the declaration keys it.
        pairs (list): Each point's description in the measured version and now,
            in the same order, which an unchanged fingerprint guarantees.

    Returns:
        list[str]: One line per survivor moved.

    Raises:
        MutationRefusal: When a declared survivor is no point of the measured
            version.
    """
    now_of = dict(pairs)
    content = manifest.read_text(encoding="utf-8")
    start = content.index(f"  {module}:\n")
    following = re.search(r"^  \S", content[start + 3:], re.M)
    end = start + 3 + following.start() if following else len(content)
    block, moved = content[start:end], []
    for entry in (declared_survivors(manifest).get(module) or {}).get("accepted") or []:
        label = str(entry.get("mutation", ""))
        if label not in now_of:
            raise MutationRefusal(
                f"QC_HARNESS_AUDIT_REFUSED: {module}: '{label}' is no point of the measured version"
            )
        if now_of[label] != label:
            block = block.replace(f'mutation: "{label}"', f'mutation: "{now_of[label]}"', 1)
            moved.append(f"{label} -> {now_of[label]}")
    manifest.write_text(content[:start] + block + content[end:], encoding="utf-8", newline="\n")
    return moved


def main(argv: Optional[list[str]] = None) -> int:
    """Re-declare one module from the command line.

    Args:
        argv (Optional[list[str]]): Arguments, or None for ``sys.argv``.

    Returns:
        int: ``0`` once re-declared, ``4`` when it refused.
    """
    parser = argparse.ArgumentParser(
        prog="mutation-redeclare",
        description="Re-declare an audited module whose code is unchanged, without auditing it",
    )
    parser.add_argument("module", type=Path, help="The production module")
    parsed = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        moved = redeclare(root, parsed.module.as_posix())
    except MutationRefusal as error:
        logger.error("%s", error)
        return 4
    for line in moved:
        logger.info("moved %s", line)
    logger.info("%s re-declared, %d survivor(s) moved", parsed.module, len(moved))
    return 0


if __name__ == "__main__":
    sys.exit(main())
