# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for what a run may leave out, and what it may not skip.

Covers `MQC_CMN_UNI_112344` and `112345`, inventoried in
``docs/design/cmn_verdict_and_cli.md`` section 10.

**One subject: whether a case was this run's to measure.** A case needing
something the environment lacks is deselected, which takes it out of the total.
Anything that reaches execution and skips is a precondition that measured
nothing, and the run exits 3 for it (`test_taxonomy.md` section 7.5.1).

A failure here is **not a model finding**, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

from pathlib import Path

import pytest

from cmn.environments import (
    deselect_unavailable_environments,
    is_precondition,
    mark_environment,
    refuse_precondition_skips,
    registered_environment_scopes,
    scope_available,
    unavailable_here,
)

from tests.cmn.environment_doubles import (
    Config,
    Item,
    Marker,
    Reporter,
    Session,
)

pytestmark = pytest.mark.unit


class TestMQCPreconditionSkips:
    """Zero skips, enforced rather than stated."""

    def MQC_CMN_UNI_112344_a_precondition_that_skipped_fails_the_run(self) -> None:
        """An ungraded skip exits 3, and a graded one leaves the status alone.

        **A harness unit job reported green at 99.44%** with 704 total, 700
        executed and 4 skipped. Gate 2 has required 100% pass and zero skips
        since it was written, and pytest exits 0 when a test skips, so nothing
        enforced the second half.

        **No reason excuses one.** A precondition measures our harness and every
        one is unconditionally blocking, so a skipped one measured nothing.

        Design: ``test_taxonomy.md`` section 7.5.1.

        Returns:
            None
        """
        # THE LAYER PARTITION, read from the identifier because a skip from
        # collection or setup carries no marker a hook can read.
        assert is_precondition("tests/cmn/m.py::T::MQC_CMN_UNI_112000_x")
        assert is_precondition("tests/x/m.py::T::MQC_EXE_SYS_122000_x")
        assert not is_precondition("tests/cases/m.py::T::MQC_EVL_EVAL_134200_x")
        assert not is_precondition("tests/cases/m.py::T::MQC_EVL_SEC_154100_x")
        assert not is_precondition("tests/cases/m.py::T::MQC_EVL_TOOL_144700_x")

        skipped = Session(Reporter("tests/cmn/m.py::T::MQC_CMN_UNI_112000_x"))
        assert refuse_precondition_skips(skipped) == 1
        assert skipped.exitstatus == 3, (
            "a skipped precondition left the run green, so Gate 2's zero is "
            "stated and not enforced"
        )

        # A GRADED SKIP IS NOT THIS GATE'S BUSINESS. It is counted by its cause
        # in the pass rate, which is a different question from whether the
        # harness itself was measured (section 7.4.1).
        graded = Session(Reporter("tests/cases/m.py::T::MQC_EVL_EVAL_134200_x"))
        assert refuse_precondition_skips(graded) == 0
        assert graded.exitstatus == 0

        # AND IT ADDS A FAILURE, NEVER REMOVES ONE. A run already red stays red
        # at the code it earned.
        already = Session(Reporter(), exitstatus=1)
        assert refuse_precondition_skips(already) == 0
        assert already.exitstatus == 1

        # NO REPORTER MEANS NOTHING TO READ, which must not raise: the hook runs
        # in every invocation, including ones that collected nothing.
        assert refuse_precondition_skips(Session(None)) == 0


class TestMQCEnvironmentScope:
    """A case the environment cannot run is not this run's to measure."""

    def MQC_CMN_UNI_112345_a_case_whose_environment_scope_is_absent_is_deselected(
        self, tmp_path: Path
    ) -> None:
        """Deselected before it runs, so it leaves the total rather than it.

        **A skip is an outcome and this is not one.** "This case could not have
        run here" is a statement about the selection, and recording it as a skip
        put a non-outcome in the result where a reader had to interpret it: the
        line read "4 skipped for a reason of ours" and the job was green.

        Design: ``test_taxonomy.md`` section 7.5.1.

        Returns:
            None
        """
        # THE REGISTRY IS PINNED, so a new scope is deliberate: each one is a
        # new way for a precondition to leave a run silently.
        assert registered_environment_scopes() == frozenset({"local", "paired"})

        # A SIBLING THAT EXISTS SATISFIES `paired`, and one that does not, does
        # not. The directory name comes from the case, so this repository names
        # no consumer.
        (tmp_path / "beside" / "Present-Repo").mkdir(parents=True)
        root = tmp_path / "beside" / "This-Repo"
        root.mkdir()
        assert scope_available("paired", "Present-Repo", root)
        assert not scope_available("paired", "Absent-Repo", root)
        assert not scope_available("paired", "", root), (
            "a paired scope naming no sibling was treated as satisfied"
        )

        # AN UNREGISTERED SCOPE IS REFUSED RATHER THAN GUESSED. Treating it as
        # available runs a case where it declared it could not, and treating it
        # as absent drops a case on a typo; both are silent.
        with pytest.raises(ValueError):
            scope_available("invented", "", root)
        with pytest.raises(ValueError):
            mark_environment("invented")

        # A CASE DECLARING NOTHING IS ALWAYS AVAILABLE, which keeps the
        # mechanism opt-in.
        plain = Item("tests/cmn/m.py::T::MQC_CMN_UNI_112000_x")
        assert unavailable_here(plain, root) == ""

        absent = Item(
            "tests/cmn/m.py::T::MQC_CMN_UNI_112001_x",
            Marker("paired", sibling="Absent-Repo"),
        )
        present = Item(
            "tests/cmn/m.py::T::MQC_CMN_UNI_112002_x",
            Marker("paired", sibling="Present-Repo"),
        )
        assert unavailable_here(absent, root) == "paired"
        assert unavailable_here(present, root) == ""

        config = Config()
        items = [plain, absent, present]
        dropped = deselect_unavailable_environments(config, items, root)

        assert dropped == 1
        assert config.hook.deselected == [absent], (
            "the wrong case was deselected, so a run either measured something "
            "it could not or dropped something it could"
        )
        assert items == [plain, present], (
            "the kept items are not the ones that remain selected"
        )

        # AND A SELECTION WITH NOTHING ABSENT IS UNTOUCHED, so the hook is not
        # called with an empty list and no line is printed about nothing.
        quiet = Config()
        kept = [plain, present]
        assert deselect_unavailable_environments(quiet, kept, root) == 0
        assert not quiet.hook.deselected
        assert kept == [plain, present]
