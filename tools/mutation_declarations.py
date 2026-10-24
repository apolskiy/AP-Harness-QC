# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The manifest of accepted survivors: what it declares, and which modules it describes.

Created: 2026-10-23
Last updated: 2026-10-23

This file contains ``AUDITED``, the production modules the mutation layer
audits; ``declared_survivors`` and ``declare_digest``, which read and write
``config/mutation_survivors.yaml``; ``baseline_problem`` and
``baseline_refusal``, which say whether a module may be measured at all; and
:func:`declaration_problems`, which reports each audited module whose content
does not hash to the digest declared for it.

**It is read before an audit and again at the moment one measures.**
``MQC_CMN_UNI_410000`` calls :func:`declaration_problems` in the unit layer, so
a declaration that has gone stale fails Gate 2 rather than waiting for the
mutation job to refuse on a push to main; ``tools/mutation_audit.py`` and
``tools/mutation_parallel.py`` call ``baseline_refusal`` as they start, and
``tools/mutation_redeclare.py`` writes through ``declare_digest``.

The comparison reads a hash and a declaration and nothing else, so what it
reports is a disagreement about which code was measured, never a survivor: a
survivor costs minutes per module and stays with the audit, which section 15.6
allows to be red.

**Here rather than in `tools/mutation_audit.py`**, which reached the 900-line
runway on 2026-10-23 (``code-style.md`` section 5.1). The manifest is the
second subject in that file: the audit measures, and this says what was
measured and what is accepted.

Specified by ``docs/design/harness_test_taxonomy.md`` sections 15.2.2, 15.10
and 15.10.1.
"""

import ast
from pathlib import Path
from typing import Any, Final, Optional

import yaml

from cmn.mutation_guard import module_digest

MANIFEST: Final[str] = "config/mutation_survivors.yaml"

# EVERY MODULE THE MUTATION LAYER AUDITS, held in the harness rather than
# beside the cases, because the manifest's API belongs here and a precondition
# in `tests/cmn/` reads it (taxonomy section 15.2.2).
AUDITED: Final[tuple[str, ...]] = (
    "cmn/verdict.py", "cmn/threshold_domain.py", "cmn/layers.py", "cmn/registries.py",
    "cmn/band_summary.py", "cmn/environments.py",
)


def declaration_problems(root: Path) -> list[str]:
    """Report every audited module that is not the module its survivors describe.

    **One implementation, asked twice.** The comparison is
    :func:`baseline_problem`, which is what an audit refuses with, so a
    precondition failure names the module, both digests and the remedy in the
    words the audit would have used.

    Design: ``harness_test_taxonomy.md`` section 15.10.1.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per module whose content does not hash to its
        declared digest and per module the manifest declares no digest for.
        Empty when every declaration describes the module on disk.
    """
    manifest = root / MANIFEST
    problems: list[str] = []
    for module in AUDITED:
        stale = baseline_problem(
            manifest, module, (root / module).read_text(encoding="utf-8")
        )
        if stale is not None:
            problems.append(stale)
    return problems


def declared_survivors(path: Path) -> dict[str, dict[str, Any]]:
    """Return the accepted survivors, per module.

    Args:
        path (Path): ``config/mutation_survivors.yaml``.

    Returns:
        dict: Module path to its declaration. Empty when the file is absent,
        which is the state a repository with no accepted survivor is in.
    """
    if not path.is_file():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return loaded.get("survivors") or {}


def declare_digest(manifest: Path, module: str, digest: str) -> None:
    """Record the baseline digest a module's survivors were measured against.

    **Edited in place rather than re-serialized.** Dumping the parsed mapping
    back would drop every comment, and the comments are the reasons section
    15.2 requires each accepted survivor to carry.

    Design: ``harness_test_taxonomy.md`` section 15.2.2.

    Args:
        manifest (Path): ``config/mutation_survivors.yaml``.
        module (str): The module path, as the declaration keys it.
        digest (str): The hex digest to declare.

    Returns:
        None
    """
    text = manifest.read_text(encoding="utf-8") if manifest.is_file() else ""
    entry = f"  {module}:\n"
    declared = (declared_survivors(manifest).get(module) or {}).get("digest")
    if declared:
        manifest.write_text(
            text.replace(f"    digest: {declared}\n",
                         f"    digest: {digest}\n", 1),
            encoding="utf-8", newline="\n",
        )
        return
    if entry in text:
        manifest.write_text(
            text.replace(entry, f"{entry}    digest: {digest}\n", 1),
            encoding="utf-8", newline="\n",
        )
        return
    # A MODULE WITH NO ENTRY AT ALL, which is an audited module that has
    # accepted nothing. The digest alone is the correct statement, and
    # `survivor_problems` reads an absent `accepted` as an empty list.
    opener = "" if text.endswith("\n") or not text else "\n"
    manifest.write_text(
        f"{text}{opener}{entry}    digest: {digest}\n",
        encoding="utf-8", newline="\n",
    )


def baseline_problem(manifest: Path, module: str, text: str) -> Optional[str]:
    """Report why this content may not serve as a baseline, or None.

    Design: ``harness_test_taxonomy.md`` section 15.10.

    Args:
        manifest (Path): ``config/mutation_survivors.yaml``.
        module (str): The module path, as the declaration keys it.
        text (str): The content on disk.

    Returns:
        Optional[str]: The reason to refuse, or None when the content hashes
        to the declared digest.
    """
    declared = (declared_survivors(manifest).get(module) or {}).get("digest")
    found = module_digest(text)
    if not declared:
        return (
            f"{module} declares no baseline digest, so nothing establishes "
            f"that this content is the module the survivors were measured "
            f"against. Add `digest: {found}` beside its `accepted` list"
        )
    if declared != found:
        return (
            f"{module} hashes to {found} and {manifest.name} declares "
            f"{declared}. Either an earlier run left the module altered, or "
            f"it was edited and the survivors need re-measuring against it: "
            f"`python -m tools.mutation_audit {module} --remeasure`, or "
            f"`python -m tools.mutation_redeclare {module}` where only its "
            f"docstrings or comments changed"
        )
    return None


def baseline_refusal(
    manifest: Path, module: str, text: str, *, remeasure: bool
) -> Optional[str]:
    """Report why this content may not be measured at all, or None.

    **Re-measuring replaces the declared digest as the anchor; it does not
    remove one.** The damage the full-text digest exists for is a module an
    earlier run left as its own ``ast.unparse``, which no fingerprint can see
    and which a re-measurement would adopt as the baseline, so that refusal
    stays whichever way the run was asked for.

    Design: ``harness_test_taxonomy.md`` sections 15.10 and 15.10.2.

    Args:
        manifest (Path): ``config/mutation_survivors.yaml``.
        module (str): The module path, as the declaration keys it.
        text (str): The content on disk.
        remeasure (bool): True where the run was asked to take this content as
            the new baseline rather than compare it with the declared one.

    Returns:
        Optional[str]: The reason to refuse, or None where the content may be
        measured.
    """
    if not remeasure:
        return baseline_problem(manifest, module, text)
    if text == ast.unparse(ast.parse(text)):
        return (
            f"{module} reads exactly as its own unparse, which is the damage a "
            f"declared digest exists for (section 15.10); restore it from git "
            f"rather than re-measuring it"
        )
    return None
