# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Runs one module's mutation audit and compares its survivors with their declaration.

Created: 2026-10-13
Last updated: 2026-10-23

This file contains :func:`audit`, which mutates a module in four parallel copies
of the repository (section 15.15), runs the unit suite in each and returns every
undeclared survivor and every declaration that no longer survives, skipping when
the audit refuses. ``MANIFEST`` points at ``config/mutation_survivors.yaml`` and
``ROOT`` at the repository.

``mqc_mut_verdict.py`` and ``mqc_mut_registries.py`` assert on what
:func:`audit` returns. **A sibling module collection does not reach**, per
`MQC_CMN_UNI_112328`.

**The list of audited modules is ``tools.mutation_declarations.AUDITED``**,
in the harness rather than here, because a precondition in ``tests/cmn/`` reads
it and the manifest's API belongs to the harness (taxonomy section 15.2.2).

Specified in ``docs/design/harness_test_taxonomy.md`` section 15.
"""

from pathlib import Path
from typing import Final

import pytest

from tools.mutation_audit import (
    AUDIT_TARGETS,
    MutationRefusal,
    survivor_problems,
)
from tools.mutation_declarations import declared_survivors
from tools.mutation_parallel import parallel_survivors

ROOT: Final[Path] = Path(__file__).resolve().parents[2]
MANIFEST: Final[Path] = ROOT / "config/mutation_survivors.yaml"

# DECLARED ONCE IN THE TOOL, so the cases and the command line audit against
# the same targets (taxonomy section 15.4.2).
TARGETS = list(AUDIT_TARGETS)


def audit(module: str) -> list[str]:
    """Audit one module and return what disagrees with its declaration.

    Args:
        module (str): The module path, relative to the repository root and as
            ``config/mutation_survivors.yaml`` keys it.

    Returns:
        list[str]: One entry per undeclared survivor and per declaration that
        no longer survives. Empty when the two agree.
    """
    try:
        found = parallel_survivors(ROOT, ROOT / module, TARGETS)
    except MutationRefusal as refusal:
        # THE CONTROL'S REFUSAL, discovered here because it costs a full suite
        # run and the setup gate would pay for it twice. A refusal is a skip
        # wherever it is raised: it says nothing about the survivor set, which
        # is the only thing this case measures (section 15.2.1).
        pytest.skip(str(refusal))
    declaration = declared_survivors(MANIFEST).get(module, {})
    return survivor_problems(module, found, declaration)
