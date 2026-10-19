# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""A nested suite for the precondition step recorder, in a sibling module collection does not reach.

The recorder lives in pytest's hooks, so it is exercised by running a small
suite of its own and reading what it logged. Design
``harness_test_taxonomy.md`` section 8.2.4.
"""

import os
import sys
from pathlib import Path
from typing import Final

from tests.cmn.subprocess_support import run_bounded

_HARNESS_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

_INI: Final[str] = """[pytest]
python_files = mqc_*.py
python_classes = TestMQC*
python_functions = MQC_*
enable_assertion_pass_hook = true
markers =
    unit: a precondition
    evaluator: a graded case
"""

_CONFTEST: Final[str] = """import pytest

pytest.register_assert_rewrite("inner_support")

from cmn.case_steps import begin_case_steps, record_assertion, record_call


def pytest_runtest_setup(item):
    begin_case_steps(item)


def pytest_assertion_pass(item, lineno, orig, expl):
    record_assertion(item, lineno, orig)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    outcome = yield
    record_call(item, outcome)
"""

_SUPPORT: Final[str] = """def check_positive(value):
    assert value > 0, "not positive"
"""

_CASES: Final[str] = """import pytest

from cmn.case_steps import step
from inner_support import check_positive

pytestmark = pytest.mark.unit


class TestMQCInner:
    def MQC_CMN_UNI_119001_passes(self):
        total = 2 + 2
        assert total == 4
        doubled = total * 2
        assert doubled == 8

    def MQC_CMN_UNI_119002_fails(self):
        value = 3
        assert value == 4, "three is not four"

    def MQC_CMN_UNI_119003_named(self):
        step(1, "add two and two")
        assert 2 + 2 == 4

    def MQC_CMN_UNI_119004_raises(self):
        with pytest.raises(ZeroDivisionError):
            print(1 / 0)

    def MQC_CMN_UNI_119005_support(self):
        check_positive(5)

    def MQC_CMN_UNI_119006_checks_nothing(self):
        total = 1 + 1
        print(total)

    def MQC_CMN_UNI_119007_names_a_step_it_never_verifies(self):
        step(1, "compute a total nobody checks")
        total = 1 + 1
        step(2, "check the total")
        assert total == 2

    def MQC_CMN_UNI_119008_declares_a_step_out_of_place(self):
        step(1, "check one")
        assert 1 == 1
        step(3, "check two, declared as the third step")
        assert 2 == 2
"""

_GRADED: Final[str] = """import pytest

pytestmark = pytest.mark.evaluator


class TestMQCGraded:
    def MQC_EVL_EVAL_139001_graded(self):
        assert 1 == 1
"""


def run_nested_steps_suite(directory: Path) -> str:
    """Write the nested suite under a directory, run it, and return everything it printed.

    Args:
        directory (Path): An empty scratch directory.

    Returns:
        str: The child's standard output and error, joined.
    """
    files = {
        "pytest.ini": _INI, "conftest.py": _CONFTEST, "inner_support.py": _SUPPORT,
        "mqc_inner.py": _CASES, "mqc_graded.py": _GRADED,
    }
    for name, body in files.items():
        (directory / name).write_text(body, encoding="utf-8")
    environment = {**os.environ, "PYTHONPATH": f"{_HARNESS_ROOT}{os.pathsep}{directory}"}
    finished = run_bounded(
        [
            sys.executable, "-m", "pytest", str(directory), "-c", str(directory / "pytest.ini"),
            "--rootdir", str(directory), "-p", "no:cacheprovider", "-p", "no:randomly",
            "-o", "log_cli=true", "--log-cli-level=INFO", "-rA",
        ],
        cwd=directory, env=environment,
    )
    return finished.stdout + finished.stderr


def lines_for(output: str, case: str) -> list[str]:
    """Return the step lines the nested run logged for one case.

    Args:
        output (str): Everything the nested run printed.
        case (str): The case's six-digit identifier.

    Returns:
        list[str]: Lines naming the case and a step, in order.
    """
    return [
        line.strip() for line in output.splitlines()
        if case in line and "STEP_" in line
    ]
