# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Running one module's mutation audit, for the cases that assert its result.

**A sibling module collection does not reach**, per `MQC_CMN_UNI_112328`.

Specified in ``docs/design/harness_test_taxonomy.md`` section 15.
"""

from pathlib import Path

from tools.mutation_audit import (
    declared_survivors,
    survivor_problems,
    survivors,
)

_ROOT = Path(__file__).resolve().parents[2]

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
    found = survivors(_ROOT, _ROOT / module, TARGETS)
    declaration = declared_survivors(
        _ROOT / "config/mutation_survivors.yaml"
    ).get(module, {})
    return survivor_problems(module, found, declaration)
