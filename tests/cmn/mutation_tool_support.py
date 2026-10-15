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

from pathlib import Path

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
