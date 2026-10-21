# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""A setup check that skips the mutation cases when the repository cannot be audited.

Created: 2026-10-14
Last updated: 2026-10-21

This file contains :func:`baselines_ready`, an autouse class fixture run before
every case in ``tests/mutation/``. For each audited module it restores a backup
left by a killed run, and checks that the module still matches the baseline its
survivors were declared against, skipping the class with
``QC_HARNESS_AUDIT_REFUSED`` when either fails.

**A refusal is not a measurement, so it skips**, per
``docs/design/harness_test_taxonomy.md`` section 15.2.1.
``framework-rules.md`` section 4 gives every ``QC_HARNESS_*`` code the outcome
"skip or broken, never fail", and both cases here reported `failed` for a
baseline they never got past.

**Here rather than beside the helpers**, because a fixture is discovered from
a ``conftest.py`` and not from an imported module. Defining it next to the
helpers would have left it never running, which is the shape this project has
corrected often enough to stop writing new instances of.
"""

import pytest

from tests.mutation.mutation_support import AUDITED, MANIFEST, ROOT
from tools.mutation_audit import baseline_problem, recover


@pytest.fixture(scope="class", autouse=True)
def baselines_ready() -> None:
    """Skip the class when the repository is not in a state worth auditing.

    The two cheap refusals, checked before any case body runs: a backup from a
    killed run, and a module that is not the baseline its survivors were
    measured against. **Executing a case that cannot measure anything is
    superfluous**, and reporting its non-execution as a failure sends a reader
    looking for a survivor nothing computed.

    The control's refusal is not checked here. It costs a full suite run, so
    it is raised where it is discovered and skipped there instead of being
    paid for twice (section 15.2.1).

    Returns:
        None
    """
    for module in AUDITED:
        # RECOVER FIRST, because it is what makes the baseline check
        # meaningful: a leftover backup is restored and reported, and the
        # digest below then compares the restored content.
        recovered = recover(ROOT / module)
        if recovered is not None:
            pytest.skip(f"QC_HARNESS_AUDIT_REFUSED: {recovered}")
        stale = baseline_problem(
            MANIFEST, module, (ROOT / module).read_text(encoding="utf-8")
        )
        if stale is not None:
            pytest.skip(f"QC_HARNESS_AUDIT_REFUSED: {stale}")
