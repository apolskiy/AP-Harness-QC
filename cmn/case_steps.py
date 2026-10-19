# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Every precondition case's steps, recorded by the engine graded cases use.

A verification is each assertion a ``UNI`` or ``SYS`` case reaches and each
``pytest.raises`` block it opens; the action is the step the case names with
:func:`step`, or the code that ran since the previous verification. Each step
is a :class:`cmn.steps.CaseStep`, written to Allure and the log as
``STEP_NN_ACTION`` and ``STEP_NN_VERIFY`` exactly as a graded case's are. A
precondition case recording no verification fails as
``QC_HARNESS_NO_VERIFICATION``.

Design: ``docs/design/harness_test_taxonomy.md`` section 8.2.4.
"""

import ast
import inspect
import logging
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from types import FrameType, TracebackType
from typing import Any, Callable, Final, Optional

import allure
import pytest

from cmn.environments import is_precondition
from cmn.steps import CaseStep, StepOutcome, step_lines

logger = logging.getLogger(__name__)

# WHAT A STEP DOES WHEN NOTHING RAN SINCE THE PREVIOUS VERIFICATION.
_NO_ACTION: Final[str] = "verifies the result of the previous step"

# HOW MUCH CODE AN ACTION QUOTES, so a log line stays one line.
_ACTION_LIMIT: Final[int] = 160

# FRAMES THAT ARE PYTEST'S OR OURS, never the case's own code.
_FOREIGN: Final[tuple[str, ...]] = ("_pytest", "pluggy", str(Path(__file__)))

_ACTIVE: ContextVar[Optional["CaseStepRecorder"]] = ContextVar("case_steps", default=None)
_RECORDER_KEY: Final[pytest.StashKey["CaseStepRecorder"]] = pytest.StashKey()
_ORIGINAL_RAISES: Final[Callable[..., Any]] = pytest.raises


def step(number: int, action: str) -> None:
    """Declare the next step by its number and name its action in words.

    Args:
        number (int): The step's place in the case, from 1, checked against
            the place it actually takes.
        action (str): What the step does.

    Returns:
        None
    """
    recorder = _ACTIVE.get()
    if recorder is not None:
        recorder.name_next(number, action)


def _is_verification(node: ast.AST) -> bool:
    """Report whether a node is an assertion or a ``pytest.raises`` block.

    Args:
        node (ast.AST): A syntax node.

    Returns:
        bool: True for either form of verification.
    """
    if isinstance(node, ast.Assert):
        return True
    if isinstance(node, ast.With):
        return any(
            isinstance(entry.context_expr, ast.Call)
            and getattr(entry.context_expr.func, "attr", "") in ("raises", "warns")
            for entry in node.items
        )
    return False


def _shortened(code: str) -> str:
    """Return code fitted to one log line.

    Args:
        code (str): The statements, joined.

    Returns:
        str: At most ``_ACTION_LIMIT`` characters.
    """
    return code if len(code) <= _ACTION_LIMIT else code[: _ACTION_LIMIT - 3] + "..."


def _joined(lines: list[str]) -> str:
    """Return source lines as one statement list, comments and blanks dropped.

    Args:
        lines (list[str]): Raw source lines.

    Returns:
        str: The statements separated by semicolons.
    """
    return "; ".join(
        stripped for stripped in (line.strip() for line in lines)
        if stripped and not stripped.startswith("#")
    )


@lru_cache(maxsize=512)
def verification_actions(path: str) -> dict[int, str]:
    """Return, for each verification line in a source file, the code that ran before it.

    Args:
        path (str): The source file.

    Returns:
        dict[int, str]: Verification line number to its action. A
        ``pytest.raises`` block's action includes the code inside it, which is
        what is expected to raise.
    """
    source = Path(path).read_text(encoding="utf-8")
    lines = source.splitlines()
    actions: dict[int, str] = {}
    for function in ast.walk(ast.parse(source)):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        first = function.body[0]
        documented = isinstance(first, ast.Expr) and isinstance(
            getattr(first, "value", None), ast.Constant
        ) and isinstance(first.value.value, str)
        previous = first.end_lineno if documented else first.lineno - 1
        checks = sorted(
            {node.lineno: node for node in ast.walk(function) if _is_verification(node)}.items()
        )
        for lineno, node in checks:
            before = lines[previous: lineno - 1]
            inside = lines[lineno: node.end_lineno] if isinstance(node, ast.With) else []
            actions[lineno] = _shortened(_joined(before + inside)) or _NO_ACTION
            previous = node.end_lineno or lineno
    return actions


@lru_cache(maxsize=512)
def _assertion_texts(path: str) -> dict[int, str]:
    """Return each assertion's condition as written, by line.

    Args:
        path (str): The source file.

    Returns:
        dict[int, str]: Assertion line number to its condition's source.
    """
    source = Path(path).read_text(encoding="utf-8")
    return {
        node.lineno: ast.get_source_segment(source, node.test) or ""
        for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Assert)
    }


class CaseStepRecorder:
    """The steps one precondition case records, as it runs."""

    def __init__(self, case_id: str) -> None:
        """Start a case with no steps.

        Args:
            case_id (str): The case, carried on every line.

        Returns:
            None
        """
        self._case_id = case_id
        self._steps: list[CaseStep] = []
        self._named: Optional[str] = None
        self._unverified: list[str] = []
        self._misnumbered: list[str] = []

    @property
    def steps(self) -> list[CaseStep]:
        """Return the steps recorded so far.

        Returns:
            list[CaseStep]: In the order they ran.
        """
        return list(self._steps)

    @property
    def unverified(self) -> list[str]:
        """Return every named step no verification followed.

        Returns:
            list[str]: Their names, the one still pending included.
        """
        return self._unverified + ([self._named] if self._named else [])

    @property
    def misnumbered(self) -> list[str]:
        """Return every step declared with a number other than its place.

        Returns:
            list[str]: One line per step, naming both numbers.
        """
        return list(self._misnumbered)

    def name_next(self, number: int, action: str) -> None:
        """Declare the next step, keeping a previous name no verification followed.

        Args:
            number (int): The number the case declares for the step.
            action (str): What the step does.

        Returns:
            None
        """
        if self._named:
            # NEVER DROPPED. A step is an action and a verification, so a name
            # replaced before its verification is a step that checked nothing.
            self._unverified.append(self._named)
        # ITS PLACE COUNTS EVERY STEP BEFORE IT, an unverified one included,
        # so an insertion that was not renumbered is caught either way.
        place = len(self._steps) + len(self._unverified) + 1
        if number != place:
            self._misnumbered.append(f"{action!r} declares step {number} and is step {place}")
        self._named = action

    def verified(
        self, path: Optional[str], lineno: int, name: str, *, passed: bool, detail: str = ""
    ) -> CaseStep:
        """Record one step: its action and the verification that just ran.

        Args:
            path (Optional[str]): The source file the verification is in.
            lineno (int): Its line.
            name (str): What it verifies.
            passed (bool): Whether it held.
            detail (str): Why it did not, where it did not.

        Returns:
            CaseStep: The step recorded.
        """
        number = len(self._steps) + 1
        action = self._named or (
            verification_actions(path).get(lineno) if path and Path(path).is_file() else None
        ) or _NO_ACTION
        self._named = None
        recorded = CaseStep(
            number,
            StepOutcome(number, "ACTION", action, "ok", prefix="STEP"),
            StepOutcome(
                number, "VERIFY", name, "ok" if passed else "failed", detail, prefix="STEP"
            ),
        )
        self._steps.append(recorded)
        for half in (recorded.action, recorded.verification):
            with allure.step(f"{half.label} [{half.outcome}]"):
                pass
        for line in step_lines(self._case_id, [recorded]):
            logger.info("%s", line)
        return recorded


class _RecordedRaises:
    """A ``pytest.raises`` context recording its outcome as a verification step."""

    def __init__(self, context: Any, name: str, where: tuple[str, int]) -> None:
        """Wrap a pytest raises context.

        Args:
            context (Any): The context ``pytest.raises`` returned.
            name (str): What it verifies.
            where (tuple): Its source file and line.

        Returns:
            None
        """
        self._context = context
        self._name = name
        self._where = where

    def __enter__(self) -> Any:
        """Enter the wrapped context.

        Returns:
            Any: The exception information pytest hands back.
        """
        return self._context.__enter__()

    def __exit__(
        self,
        kind: Optional[type[BaseException]],
        value: Optional[BaseException],
        trace: Optional[TracebackType],
    ) -> bool:
        """Leave the wrapped context, recording whether the exception arrived.

        Args:
            kind (Optional[type]): The exception type, if any.
            value (Optional[BaseException]): The exception, if any.
            trace (Optional[TracebackType]): Its traceback.

        Returns:
            bool: Whatever the wrapped context returned.

        Raises:
            BaseException: Whatever the wrapped context raised, after recording it.
        """
        recorder = _ACTIVE.get()
        try:
            suppressed = bool(self._context.__exit__(kind, value, trace))
        except BaseException as error:
            if recorder is not None:
                recorder.verified(*self._where, self._name, passed=False, detail=str(error))
            raise
        if recorder is not None:
            recorder.verified(*self._where, self._name, passed=True)
        return suppressed


def _expected_names(expected: Any) -> str:
    """Return the exception types a raises block expects, by name.

    Args:
        expected (Any): A type or a tuple of types.

    Returns:
        str: Their names, joined.
    """
    kinds = expected if isinstance(expected, tuple) else (expected,)
    return " or ".join(getattr(kind, "__name__", str(kind)) for kind in kinds)


def _recording_raises(expected: Any, *args: Any, **kwargs: Any) -> Any:
    """Stand in for ``pytest.raises`` during a precondition case, recording each use.

    Args:
        expected (Any): The exception type or types.
        *args (Any): A callable and its arguments, for the call form.
        **kwargs (Any): ``match`` and the rest, passed through.

    Returns:
        Any: A recording context, or the call form's result.
    """
    current = inspect.currentframe()
    caller = current.f_back if current is not None else None
    where = (caller.f_code.co_filename, caller.f_lineno) if caller is not None else ("", 0)
    name = f"raises {_expected_names(expected)}"
    if args:
        recorder = _ACTIVE.get()
        try:
            result = _ORIGINAL_RAISES(expected, *args, **kwargs)
        except BaseException as error:
            if recorder is not None:
                recorder.verified(*where, name, passed=False, detail=str(error))
            raise
        if recorder is not None:
            recorder.verified(*where, name, passed=True)
        return result
    return _RecordedRaises(_ORIGINAL_RAISES(expected, **kwargs), name, where)


def begin_case_steps(item: pytest.Item) -> None:
    """Start recording a precondition case's steps, and record its preconditions.

    Args:
        item (pytest.Item): The test about to run.

    Returns:
        None
    """
    # A GRADED CASE'S STEPS ARE ITS DISPATCHES (section 8.2.2), so only a
    # precondition is recorded here, read from its layer token.
    if not is_precondition(item.nodeid):
        return
    recorder = CaseStepRecorder(item.name)
    item.stash[_RECORDER_KEY] = recorder
    _ACTIVE.set(recorder)
    pytest.raises = _recording_raises  # type: ignore[assignment]
    fixtures = [name for name in getattr(item, "fixturenames", ()) if name != "request"]
    if fixtures:
        logger.info("%s | PRECONDITIONS: %s", item.name, ", ".join(fixtures))


def _caller_of(lineno: int) -> Optional[str]:
    """Return the source file whose frame is executing a line, outside pytest and here.

    Args:
        lineno (int): The line the assertion is on.

    Returns:
        Optional[str]: The file, or None where no frame matches.
    """
    frame: Optional[FrameType] = inspect.currentframe()
    while frame is not None:
        filename = frame.f_code.co_filename
        if frame.f_lineno == lineno and not any(part in filename for part in _FOREIGN):
            return filename
        frame = frame.f_back
    return None


def record_assertion(item: pytest.Item, lineno: int, orig: str) -> None:
    """Record a passing assertion as a verification step.

    Args:
        item (pytest.Item): The test running.
        lineno (int): The assertion's line.
        orig (str): The assertion's condition as written.

    Returns:
        None
    """
    recorder = item.stash.get(_RECORDER_KEY, None)
    if recorder is not None:
        recorder.verified(_caller_of(lineno), lineno, orig, passed=True)


def _failing_assertion(excinfo: Any) -> Optional[tuple[str, int, str]]:
    """Return where a failing assertion is and what it asserted.

    Args:
        excinfo (Any): The call's exception information.

    Returns:
        Optional[tuple]: Its file, line and condition, or None where the
        failure was not an assertion in the case's own code.
    """
    kind, _, trace = excinfo
    if kind is None or not issubclass(kind, AssertionError):
        return None
    found: Optional[tuple[str, int]] = None
    while trace is not None:
        filename = trace.tb_frame.f_code.co_filename
        if not any(part in filename for part in _FOREIGN):
            found = (filename, trace.tb_lineno)
        trace = trace.tb_next
    if found is None:
        return None
    text = _assertion_texts(found[0]).get(found[1], "") if Path(found[0]).is_file() else ""
    return found[0], found[1], text or "an assertion"


def record_call(item: pytest.Item, outcome: Any) -> None:
    """Close a precondition case: record a failing assertion, or fail a case that verified nothing.

    Args:
        item (pytest.Item): The test that ran.
        outcome (Any): pluggy's result for the call phase.

    Returns:
        None
    """
    recorder = item.stash.get(_RECORDER_KEY, None)
    if recorder is None:
        return
    pytest.raises = _ORIGINAL_RAISES  # type: ignore[assignment]
    _ACTIVE.set(None)
    excinfo = outcome.excinfo
    if excinfo is not None:
        failing = _failing_assertion(excinfo)
        last = recorder.steps[-1].verification if recorder.steps else None
        if failing is not None and not (last is not None and last.outcome == "failed"):
            recorder.verified(failing[0], failing[1], failing[2], passed=False,
                              detail=str(excinfo[1]).splitlines()[0] if str(excinfo[1]) else "")
        return
    if recorder.misnumbered:
        outcome.force_exception(pytest.fail.Exception(
            f"QC_HARNESS_STEP_MISNUMBERED: {item.name}: {'; '.join(recorder.misnumbered)}",
            pytrace=False,
        ))
    elif not recorder.steps:
        outcome.force_exception(pytest.fail.Exception(
            f"QC_HARNESS_NO_VERIFICATION: {item.name} finished having recorded no "
            f"verification step, so it checked nothing",
            pytrace=False,
        ))
    elif recorder.unverified:
        outcome.force_exception(pytest.fail.Exception(
            f"QC_HARNESS_NO_VERIFICATION: {item.name} named steps no verification "
            f"followed: {'; '.join(recorder.unverified)}",
            pytrace=False,
        ))
