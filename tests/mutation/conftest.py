# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""A setup check that skips the mutation cases when the repository cannot be audited.

Created: 2026-10-14
Last updated: 2026-10-24

This file contains :func:`baselines_ready`, an autouse class fixture run before
every case in ``tests/mutation/``, and :func:`pytest_terminal_summary`, which
closes the run by naming the cases the audit set aside. For each audited module
the fixture restores a backup left by a killed run, skipping the class with
``QC_HARNESS_AUDIT_REFUSED`` when it finds one.

**The closing line is here because this is where the run ends.** The command
line reports it from ``tools.mutation_audit.main``, and Gate 8 never calls
that: it runs this suite, whose cases measure directly. A line printed only on
the path nobody uses in CI is a line nobody reads
(``harness_test_taxonomy.md`` section 15.7.1.2).

**A refusal is not a measurement, so it skips**, per
``docs/design/harness_test_taxonomy.md`` section 15.2.1.
``framework-rules.md`` section 4 gives every ``QC_HARNESS_*`` code the outcome
"skip or broken, never fail", and both cases here reported `failed` for a
baseline they never got past.

**A backup is the one refusal that is about the repository**, which is why it
is the only one checked here. A module that does not hash to its declared
digest is a statement about that module alone, and checking it here skipped
every case in the layer for one stale declaration: it belongs to the
measurement, which makes the same check per module and refuses there
(section 15.2.1.1).

**Here rather than beside the helpers**, because a fixture is discovered from
a ``conftest.py`` and not from an imported module. Defining it next to the
helpers would have left it never running, which is the shape this project has
corrected often enough to stop writing new instances of.
"""

from typing import Any

import pytest

from tests.mutation.mutation_support import ROOT, TARGETS
from tools.mutation_audit import quarantine_report, recover
from tools.mutation_declarations import AUDITED


@pytest.fixture(scope="class", autouse=True)
def baselines_ready() -> None:
    """Skip the class when a killed run left a mutant on disk.

    **Executing a case that cannot measure anything is superfluous**, and
    reporting its non-execution as a failure sends a reader looking for a
    survivor nothing computed.

    The baseline and the control are not checked here. The baseline is about
    one module and the control costs a full suite run, so each is raised where
    it is discovered and skipped there rather than being paid for twice
    (sections 15.2.1 and 15.2.1.1).

    Returns:
        None
    """
    for module in AUDITED:
        recovered = recover(ROOT / module)
        if recovered is not None:
            pytest.skip(f"QC_HARNESS_AUDIT_REFUSED: {recovered}")


def pytest_terminal_summary(terminalreporter: Any) -> None:
    """Close the run by naming the cases the audit set aside.

    **Nothing can decide the list for the audit**, so the run says what is on
    it: a reader of a refusal sees which cases did not run against the
    mutants, and a case that should have been on the list and is not is
    visible by its absence (section 15.7.1.2).

    Args:
        terminalreporter (Any): pytest's reporter, written to so the line
            lands with the run's own summary rather than in a log a reader
            has to go looking for.

    Returns:
        None
    """
    terminalreporter.write_line(quarantine_report(TARGETS))
