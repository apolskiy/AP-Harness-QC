# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Writes ``requirements.txt`` and ``requirements-dev.txt`` from ``pyproject.toml``.

Created: 2026-09-26
Last updated: 2026-10-28

This file contains ``main``, which resolves a repository root from ``--root``
and writes the two derived files for it. The reading, rendering and comparison
all live in ``cmn.dependency_declaration``, so the generator and the cases that
check it run one implementation.

**A contributor runs it after changing a dependency**, and
``MQC_CMN_UNI_112222`` regenerates the contents and fails the run when the
committed files no longer match the declaration. The case repository has the
same pair of files and the same check, ``MQC_CAS_UNI_115785``, which is why the
root is an argument rather than this file's own location.

Specified by ``DESIGN.md`` section 5.0.1.

**`pyproject.toml` is the declaration; these files are derived.** Tooling
expects a requirements file, and PyCharm in particular offers to install from
one and does not read an optional-dependency extra. A contributor opening the
project should not have to know which of two conventions this repository chose.

**They are never hand-edited.** The check fails the run when they disagree with
the declaration, which is the same rule applied everywhere else here: two
statements of one fact drift, so either there is one statement or there is a
check. A generated file plus a check is the second form rather than an
exception to the rule.

Run it with ``python tools/generate_requirements.py``, or with
``--root ../AP-Model-QC`` to write the case repository's pair. The check tells
you when you have forgotten.
"""

import argparse
import sys
from pathlib import Path
from typing import Final

from cmn.dependency_declaration import generated_files

_ENCODING: Final[str] = "utf-8"


def main() -> int:
    """Write the generated files for the root given.

    Returns:
        int: Zero on success.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="the repository root to write the requirements files for",
    )
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    for path, contents in generated_files(root).items():
        path.write_text(contents, encoding=_ENCODING, newline="\n")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
