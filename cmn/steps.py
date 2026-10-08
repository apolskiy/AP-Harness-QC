# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The numbered steps a graded observation passes through, and where it stopped.

Specified by ``docs/design/test_taxonomy.md`` section 8, which has carried this
since the project began and which nothing implemented: a step is a verifiable
action and a verification, logged apart, because a step can fail in either
phase and the two are different diagnoses.

| Phase | Failure means | Family | Outcome |
|---|---|---|---|
| Action | The step could not be performed | ``QC_HARNESS_*`` | Skip |
| Verification | It was performed and the result was wrong | ``QC_LLM_*`` | Fail |

**The phase reached is recorded, not merely the step.** Failure can occur
between an action and its verification, and "step 5 failed" cannot tell a
provider timeout from a model answering wrongly.

**Nothing new is stored to answer this.** Every fact the ledger reports is
already on the dispatch outcome and the evaluation result; what was missing was
a reading of them in order. So this module computes and never records, which is
also why it can be applied to a result that was produced before it existed.
"""

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Final, Iterator, Optional

logger = logging.getLogger(__name__)

# WHAT EACH STEP DOES AND WHAT IT ASSERTS. The pair is the unit: section 8.2
# requires both names, and a step declaring only an action is a step nobody
# verified.
_STEPS: Final[tuple[tuple[str, str], ...]] = (
    ("form the request",
     "the request carries the task's prompt, documents and offered tools"),
    ("send the request",
     "a response was returned for this observation"),
    ("ingest the response",
     "the response normalised, carrying a finish reason"),
    ("screen the response",
     "no planted instruction pattern on a case that declared none"),
    ("check the response",
     "every assertion the rule declares held"),
    ("send the response to the judge",
     "the judge was reached for this observation"),
    ("receive the judgement",
     "the rubric cleared the threshold it declares"),
)

_ACTION: Final[str] = "ACTION"
_VERIFY: Final[str] = "VERIFY"

_REACHED: Final[str] = "ok"
_FAILED: Final[str] = "failed"
_NOT_RUN: Final[str] = "not run"
# A RULE AUTHORING NO RUBRIC DECLARES ITSELF DECIDED BY ITS ASSERTIONS,
# which is what the whole security suite does. Its judge steps did not
# fail to run; they do not apply, and reading them as a stop would report
# twenty-one rules as having halted early.
_NOT_APPLICABLE: Final[str] = "not applicable"


@dataclass(frozen=True)
class StepOutcome:
    """One phase of one numbered step.

    Attributes:
        number (int): The step's position, from 1 within the case.
        phase (str): ``ACTION`` or ``VERIFY``.
        name (str): What is performed, or what is asserted.
        outcome (str): ``ok``, ``failed`` or ``not run``.
        detail (str): What was found, empty where there is nothing to add.
        taxonomy_code (str): The code this phase emitted, empty where none.
    """

    number: int
    phase: str
    name: str
    outcome: str
    detail: str = ""
    taxonomy_code: str = ""

    @property
    def label(self) -> str:
        """Return the name section 8.2 requires, parseable mechanically.

        Returns:
            str: ``STEP_<NN>_<PHASE>: <name>``.
        """
        return f"STEP_{self.number:02d}_{self.phase}: {self.name}"

    @property
    def line(self) -> str:
        """Return the log line for this phase.

        **Carries the step number, the phase, the outcome and the code**, which
        is what section 8.2 requires of every line; the case identifier is
        added by the caller, which knows it.

        Returns:
            str: The line, without a trailing newline.
        """
        parts = [self.label, self.outcome]
        if self.taxonomy_code:
            parts.append(self.taxonomy_code)
        if self.detail:
            parts.append(self.detail)
        return " | ".join(parts)


@contextmanager
def entering(case_id: str, number: int, phase: str, detail: str = "") -> Iterator[None]:
    """Log a phase on entry, and on the way out however it leaves.

    **The ledger is computed after the fact and cannot survive a crash.** A
    request that times out, an adapter that raises, a provider connection that
    drops: each leaves no result to read, so a record written only at the end
    records nothing about where the run was. This writes the location first.

    **What it buys is time to repair.** "Something failed in this case" sends a
    reader to the whole pipeline; "it was inside STEP_02_ACTION: send the
    request" sends them to one call.

    Args:
        case_id (str): Which case, carried on every line.
        number (int): The step number, from 1.
        phase (str): ``ACTION`` or ``VERIFY``.
        detail (str): What is about to be attempted, where that is known.

    Yields:
        None: The body runs inside the record.

    Raises:
        BaseException: Whatever the body raised, re-raised unchanged after the
            location is logged. **Nothing is swallowed**: this records where a
            failure happened and never decides what it means.
    """
    label = f"STEP_{number:02d}_{phase}"
    opening = f"{case_id} | {label} | entering"
    logger.info("%s", f"{opening} | {detail}" if detail else opening)
    try:
        yield
    except BaseException as error:
        # THE TYPE AND THE MESSAGE, because a crash between a request and a
        # response is diagnosed from what was raised and where, and the where
        # is the half nothing recorded before this.
        logger.error(
            "%s | %s | crashed inside this phase | %s: %s",
            case_id, label, type(error).__name__, error,
        )
        raise
    logger.info("%s | %s | left", case_id, label)


def ledger(outcome: Any, result: Any) -> list[StepOutcome]:
    """Return every step's two phases, in order, for one observation.

    Args:
        outcome (Any): The ``DispatchOutcome``, or ``None`` where dispatch did
            not return one.
        result (Any): The ``EvaluationResult``, or ``None`` where evaluation
            never ran.

    Returns:
        list[StepOutcome]: Two entries per step, fourteen in all, each carrying
        what it found. **Every step appears**, including those that did not
        run, because the steps nobody reached are what an early stop hides.
    """
    entries: list[StepOutcome] = []
    stopped = False
    for index, (action, verification) in enumerate(_STEPS, start=1):
        for phase, name in ((_ACTION, action), (_VERIFY, verification)):
            if stopped:
                entries.append(
                    StepOutcome(index, phase, name, _NOT_RUN)
                )
                continue
            state, detail, code = _assess(index, phase, outcome, result)
            entries.append(StepOutcome(index, phase, name, state, detail, code))
            if state in (_FAILED, _NOT_RUN):
                stopped = True
    return entries


def stopped_at(entries: list[StepOutcome]) -> Optional[StepOutcome]:
    """Return the phase execution stopped at, or None where it completed.

    Args:
        entries (list): The ledger.

    Returns:
        Optional[StepOutcome]: The first phase that failed or did not run.
    """
    for entry in entries:
        if entry.outcome in (_FAILED, _NOT_RUN):
            return entry
    return None


def stopped_line(entries: list[StepOutcome]) -> str:
    """Return one line naming where execution stopped, carrying no output.

    **Payload free by construction**, so a security case can print it: the line
    names the step, the phase, the outcome and the code, and never the detail,
    which for a claim assertion quotes the model's own sentence.

    Args:
        entries (list): The ledger.

    Returns:
        str: The line, or an empty string where every applicable phase ran.
    """
    halt = stopped_at(entries)
    if halt is None:
        return ""
    unrun = sum(1 for entry in entries if entry.outcome == _NOT_RUN)
    code = f", {halt.taxonomy_code}" if halt.taxonomy_code else ""
    tail = (
        f"; {unrun} later phase(s) did not run, so what they would have found "
        f"is unknown"
        if unrun else ""
    )
    return (
        f"stopped at STEP_{halt.number:02d}_{halt.phase} "
        f"({halt.outcome}{code}){tail}"
    )


def summary(case_id: str, entries: list[StepOutcome]) -> list[str]:
    """Return the lines a reader needs when a case failed.

    **Names the steps that did not run.** A failure at step five leaves six and
    seven unmeasured, and anything they would have found is unknown rather than
    absent: more failures in the harness and in the model both hide there.

    Args:
        case_id (str): Which case, carried on every line per section 8.2.
        entries (list): The ledger.

    Returns:
        list[str]: One line per phase, then where it stopped.
    """
    lines = [f"{case_id} | {entry.line}" for entry in entries]
    halt = stopped_at(entries)
    if halt is None:
        applicable = sum(1 for entry in entries if entry.outcome == _REACHED)
        return lines + [
            f"{case_id} | {applicable} of {len(entries)} phase(s) ran and "
            f"verified, the rest not applicable"
            if applicable != len(entries)
            else f"{case_id} | every step ran and verified"
        ]

    unrun = sum(1 for entry in entries if entry.outcome == _NOT_RUN)
    lines.append(
        f"{case_id} | stopped at {halt.label} ({halt.outcome})"
        + (
            f"; {unrun} later phase(s) did not run, so what they would have "
            f"found is unknown"
            if unrun else ""
        )
    )
    return lines


# ONE HANDLER PER STEP, keyed by number. A single function reading all seven
# carried the whole pipeline's branches, which pylint reported and which is
# also how a reader loses the thread: each step's rule now sits alone.
def _assess(
    number: int, phase: str, outcome: Any, result: Any
) -> tuple[str, str, str]:
    """Return one phase's state, detail and code.

    Args:
        number (int): The step number, from 1.
        phase (str): ``ACTION`` or ``VERIFY``.
        outcome (Any): The dispatch outcome, possibly None.
        result (Any): The evaluation result, possibly None.

    Returns:
        tuple: The state, what was found, and the taxonomy code.
    """
    if number <= 3:
        if outcome is None:
            # AN EVALUATION RESULT PROVES DISPATCH SUCCEEDED, because nothing
            # evaluates a response that never arrived. So a caller holding the
            # result and not the outcome reports these three as reached rather
            # than unknown, which is what a failure message has to hand.
            if result is not None:
                return _REACHED, "", ""
            return _NOT_RUN, "dispatch returned nothing", ""
        return _DISPATCH_STEPS[number](phase, outcome)
    if result is None:
        return _NOT_RUN, "evaluation did not run", ""
    if number >= 6 and not getattr(result, "rubric_authored", True):
        return (
            _NOT_APPLICABLE,
            "the rule authors no rubric and is decided by its assertions",
            "",
        )
    return _EVALUATION_STEPS[number](phase, result)


def _step_form(phase: str, outcome: Any) -> tuple[str, str, str]:
    """Return whether the adapter composed a request.

    Args:
        phase (str): ``ACTION`` or ``VERIFY``.
        outcome (Any): The dispatch outcome.

    Returns:
        tuple: The state, what was found, and the taxonomy code.
    """
    if phase == _ACTION:
        return _REACHED, "", ""
    request = getattr(outcome, "request", None)
    if not request:
        return _FAILED, "the adapter composed no request", "QC_HARNESS_PARSER_ERROR"
    return _REACHED, f"{len(request)} field(s)", ""


def _step_send(phase: str, outcome: Any) -> tuple[str, str, str]:
    """Return whether a response came back for this observation.

    Args:
        phase (str): ``ACTION`` or ``VERIFY``.
        outcome (Any): The dispatch outcome.

    Returns:
        tuple: The state, what was found, and the taxonomy code.
    """
    code = str(getattr(outcome, "taxonomy_code", "") or "")
    if phase == _ACTION:
        mode = str(getattr(outcome, "mode", "") or "")
        attempts = getattr(outcome, "attempts", 0)
        return _REACHED, f"{mode}, {attempts} attempt(s)", ""
    if code:
        # A STEP THAT COULD NOT BE PERFORMED IS A SKIP, per section 8.1, and
        # the code says whose defect it was.
        return _FAILED, "no response for this observation", code
    return _REACHED, "", ""


def _step_ingest(phase: str, outcome: Any) -> tuple[str, str, str]:
    """Return whether the response normalised.

    Args:
        phase (str): ``ACTION`` or ``VERIFY``.
        outcome (Any): The dispatch outcome.

    Returns:
        tuple: The state, what was found, and the taxonomy code.
    """
    if phase == _ACTION:
        return _REACHED, "", ""
    response = getattr(outcome, "response", None)
    if response is None:
        code = str(getattr(outcome, "taxonomy_code", "") or "")
        return _FAILED, "nothing to normalise", code or "QC_HARNESS_PARSER_ERROR"
    finish = str(getattr(response, "finish_reason", "") or "unstated")
    text = str(getattr(response, "text", "") or "")
    return _REACHED, f"finish_reason {finish}, {len(text)} character(s)", ""


def _step_screen(phase: str, result: Any) -> tuple[str, str, str]:
    """Return what the injection screen found.

    Args:
        phase (str): ``ACTION`` or ``VERIFY``.
        result (Any): The evaluation result.

    Returns:
        tuple: The state, what was found, and the taxonomy code.
    """
    if phase == _ACTION:
        return _REACHED, "", ""
    screen = getattr(result, "screen", None)
    code = str(getattr(screen, "taxonomy_code", "") or "")
    if code:
        return _FAILED, "a planted pattern matched the response", code
    return _REACHED, "", ""


def _step_check(phase: str, result: Any) -> tuple[str, str, str]:
    """Return what the declared assertions found.

    Args:
        phase (str): ``ACTION`` or ``VERIFY``.
        result (Any): The evaluation result.

    Returns:
        tuple: The state, what was found, and the taxonomy code.
    """
    results = list(getattr(result, "assertion_results", ()) or ())
    if phase == _ACTION:
        if not results:
            return _NOT_RUN, "no assertion ran", ""
        return _REACHED, f"{len(results)} assertion(s)", ""
    failing = [entry for entry in results if not entry.passed]
    if not failing:
        return _REACHED, "", ""
    detail = "; ".join(
        f"{entry.assertion_id}: {entry.detail}" for entry in failing
    )
    return _FAILED, detail, str(failing[0].taxonomy_code or "")


def _step_judge_send(phase: str, result: Any) -> tuple[str, str, str]:
    """Return whether the judge was reached.

    Args:
        phase (str): ``ACTION`` or ``VERIFY``, read alike here.
        result (Any): The evaluation result.

    Returns:
        tuple: The state, what was found, and the taxonomy code.
    """
    del phase
    skipped = str(getattr(result, "judge_skipped_reason", "") or "")
    if skipped:
        return _NOT_RUN, skipped, _skip_code(result)
    return _REACHED, "", ""


def _step_judge_receive(phase: str, result: Any) -> tuple[str, str, str]:
    """Return what the rubric scored.

    Args:
        phase (str): ``ACTION`` or ``VERIFY``, read alike here.
        result (Any): The evaluation result.

    Returns:
        tuple: The state, what was found, and the taxonomy code.
    """
    del phase
    score = getattr(result, "score", None)
    if score is None:
        skipped = str(getattr(result, "judge_skipped_reason", "") or "")
        return _NOT_RUN, skipped or "no judgement returned", _skip_code(result)
    value = getattr(score, "value", "?")
    if not getattr(score, "passed", True):
        return (
            _FAILED,
            f"scored {value} against its threshold",
            "QC_LLM_RUBRIC_FAILURE",
        )
    return _REACHED, f"scored {value}", ""


_DISPATCH_STEPS: Final[dict[int, Any]] = {
    1: _step_form,
    2: _step_send,
    3: _step_ingest,
}

_EVALUATION_STEPS: Final[dict[int, Any]] = {
    4: _step_screen,
    5: _step_check,
    6: _step_judge_send,
    7: _step_judge_receive,
}


def _skip_code(result: Any) -> str:
    """Return the harness code a skipped judgement carried.

    Args:
        result (Any): The evaluation result.

    Returns:
        str: The first ``QC_HARNESS_*`` code recorded, empty where none is.
    """
    for code in getattr(result, "taxonomy_codes", ()) or ():
        if str(code).startswith("QC_HARNESS_"):
            return str(code)
    return ""
