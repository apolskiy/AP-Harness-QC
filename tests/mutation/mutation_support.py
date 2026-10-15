# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Running one module's mutation audit, for the cases that assert its result.

**A sibling module collection does not reach**, per `MQC_CMN_UNI_112328`.

Specified in ``docs/design/harness_test_taxonomy.md`` section 15.
"""

from pathlib import Path
from typing import Final

import pytest

from tools.mutation_audit import (
    MutationRefusal,
    declared_survivors,
    survivor_problems,
    survivors,
)

ROOT: Final[Path] = Path(__file__).resolve().parents[2]
MANIFEST: Final[Path] = ROOT / "config/mutation_survivors.yaml"

# EVERY MODULE THIS LAYER AUDITS, read by the setup gate in `conftest.py` so
# it covers the whole class rather than whichever case runs first.
AUDITED: Final[tuple[str, ...]] = (
    "cmn/verdict.py", "cmn/threshold_domain.py", "cmn/layers.py", "cmn/registries.py",
    "cmn/band_summary.py", "cmn/environments.py",
)

# THE TWO CASES THAT READ SOURCE AS TEXT RATHER THAN IMPORTING IT, so they fail
# on the reformatting the mutator performs and would kill every mutant for the
# wrong reason. Measured rather than guessed: the suite was run against an
# unparsed module and these are what failed. Section 15.4.
_DESELECT = (
    "--deselect",
    "tests/cmn/mqc_uni_file_standards.py::TestMQCAuthorshipHeader"
    "::MQC_CMN_UNI_112502_every_python_file_carries_its_spdx_header",
    "--deselect",
    "tests/cmn/mqc_uni_file_standards.py::TestMQCModuleRunway"
    "::MQC_CMN_UNI_112331_a_module_at_the_runway_ceiling_is_reported",
)
TARGETS = ["-m", "unit", *_DESELECT]


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
        found = survivors(ROOT, ROOT / module, TARGETS)
    except MutationRefusal as refusal:
        # THE CONTROL'S REFUSAL, discovered here because it costs a full suite
        # run and the setup gate would pay for it twice. A refusal is a skip
        # wherever it is raised: it says nothing about the survivor set, which
        # is the only thing this case measures (section 15.2.1).
        pytest.skip(str(refusal))
    declaration = declared_survivors(MANIFEST).get(module, {})
    return survivor_problems(module, found, declaration)
