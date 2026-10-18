# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""A graded case's steps, the pipeline phases beneath each, and where it stopped.

Specified by ``docs/design/harness_test_taxonomy.md`` section 8: a step is a
verifiable action and one verification, logged apart, because a step can fail
in either and the two are different diagnoses.

**A step is a dispatch** (section 8.2.2). Steps 1 to *k* are the configured
observations, the next two the escalation, taken only when one of the first
*k* failed and otherwise recorded as not run, and the last compares them. The
seven pipeline phases one observation passes through are recorded beneath its
step as ``PHASE_<NN>_<ACTION|VERIFY>``.

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
from typing import Any, Final, Iterator, Optional, Sequence

from cmn.observations import escalation_size, further_observations

logger = logging.getLogger(__name__)

# WHAT EACH PHASE DOES AND WHAT IT ASSERTS. The pair is the unit: section 8.2
# requires both names, and a phase declaring only an action is one nobody
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

# WHAT A LABEL NAMES. A step is a dispatch or the comparison; a phase is one
# stage of the pipeline inside an observation's step (section 8.2.2).
_STEP: Final[str] = "STEP"
_PHASE: Final[str] = "PHASE"

# THE LAST DISPATCH PHASE. Phases 1 to 3 form, send and ingest, and sit under
# an observation step's action; 4 to 7 sit under its verification.
_LAST_DISPATCH_PHASE: Final[int] = 3

_INCONSISTENT: Final[str] = "QC_LLM_INCONSISTENT"


@dataclass(frozen=True)
class StepOutcome:
    """One phase, ACTION or VERIFY, of a step or of a pipeline phase.

    Attributes:
        number (int): The position, from 1 within the case or the observation.
        phase (str): ``ACTION`` or ``VERIFY``.
        name (str): What is performed, or what is asserted.
        outcome (str): ``ok``, ``failed``, ``not run`` or ``not applicable``.
        detail (str): What was found, empty where there is nothing to add.
        taxonomy_code (str): The code this phase emitted, empty where none.
        prefix (str): ``PHASE`` for a pipeline phase, ``STEP`` for a step.
    """

    number: int
    phase: str
    name: str
    outcome: str
    detail: str = ""
    taxonomy_code: str = ""
    prefix: str = _PHASE

    @property
    def label(self) -> str:
        """Return the name section 8.2 requires, parseable mechanically.

        Returns:
            str: ``<PREFIX>_<NN>_<PHASE>: <name>``.
        """
        return f"{self.prefix}_{self.number:02d}_{self.phase}: {self.name}"

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
    reader to the whole pipeline; "it was inside PHASE_02_ACTION: send the
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
    label = f"{_PHASE}_{number:02d}_{phase}"
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
        f"stopped at {halt.prefix}_{halt.number:02d}_{halt.phase} "
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


@dataclass(frozen=True)
class CaseStep:
    """One step of a graded case: an action, one verification, its phases.

    Attributes:
        number (int): The step's position, from 1 within the case.
        action (StepOutcome): What was performed.
        verification (StepOutcome): The one thing verified.
        phases (tuple): The pipeline phases beneath an observation step, empty
            for a step that dispatched nothing.
    """

    number: int
    action: StepOutcome
    verification: StepOutcome
    phases: tuple[StepOutcome, ...] = ()

    @property
    def action_phases(self) -> tuple[StepOutcome, ...]:
        """Return the phases beneath the action: form, send and ingest.

        Returns:
            tuple: Phases 1 to 3, both halves of each.
        """
        return tuple(
            entry for entry in self.phases if entry.number <= _LAST_DISPATCH_PHASE
        )

    @property
    def verification_phases(self) -> tuple[StepOutcome, ...]:
        """Return the phases beneath the verification: screen, check and judge.

        Returns:
            tuple: Phases 4 to 7, both halves of each.
        """
        return tuple(
            entry for entry in self.phases if entry.number > _LAST_DISPATCH_PHASE
        )


def observation_step(number: int, outcome: Any, result: Any) -> CaseStep:
    """Return the step one dispatch is, verifying that request alone.

    Args:
        number (int): The step number, which is the observation's, from 1.
        outcome (Any): The ``DispatchOutcome``, or None.
        result (Any): The ``EvaluationResult``, or None.

    Returns:
        CaseStep: The ACTION reads phases 1 to 3 and the VERIFY phases 4 to 7.
        **A failed action leaves the verification not run**, a dispatch that
        measured nothing having nothing to verify (section 8.1). A step's
        detail names the phase it stopped at and never a phase's detail, which
        for an assertion quotes the model.
    """
    phases = tuple(ledger(outcome, result))
    action = StepOutcome(
        number, _ACTION, f"dispatch observation {number}: form, send and ingest",
        *_halted([entry for entry in phases if entry.number <= _LAST_DISPATCH_PHASE]),
        prefix=_STEP,
    )
    verify_name = f"observation {number} met the rule: screen, assertions and judgement"
    if action.outcome != _REACHED:
        verification = StepOutcome(
            number, _VERIFY, verify_name, _NOT_RUN,
            "the dispatch produced no measurement", "", _STEP,
        )
    else:
        verification = StepOutcome(
            number, _VERIFY, verify_name,
            *_halted([entry for entry in phases if entry.number > _LAST_DISPATCH_PHASE]),
            prefix=_STEP,
        )
    return CaseStep(number, action, verification, phases)


def consistency_step(number: int, outcomes: Sequence[Optional[bool]]) -> CaseStep:
    """Return the last step, verifying only that the observations agree.

    Args:
        number (int): The step number, the last in the case.
        outcomes (Sequence): Each observation's result in order: True passed,
            False failed, None measured nothing.

    Returns:
        CaseStep: A VERIFY that fails with ``QC_LLM_INCONSISTENT`` when the
        measured observations differ, and passes when they concur, **failing
        every time included**: the observation steps carry that failure.
        Unmeasured observations are left out; with none measured the
        verification is not run.
    """
    measured = [value for value in outcomes if value is not None]
    action = StepOutcome(
        number, _ACTION, "compare every observation taken", _REACHED,
        f"{len(outcomes)} observation(s), {len(measured)} measured", "", _STEP,
    )
    name = "the observations agree"
    if not measured:
        state, detail, code = _NOT_RUN, "no observation produced a measurement", ""
    elif len(set(measured)) == 1:
        state, detail, code = _REACHED, f"{len(measured)} measured observation(s) agree", ""
    else:
        state, detail, code = (
            _FAILED,
            f"{sum(measured)} of {len(measured)} measured observations passed",
            _INCONSISTENT,
        )
    return CaseStep(
        number, action, StepOutcome(number, _VERIFY, name, state, detail, code, _STEP)
    )


def case_steps(
    observations: Sequence[tuple[Any, Any]], *, configured: int
) -> list[CaseStep]:
    """Return every step of a graded case, in order.

    Args:
        observations (Sequence): Each observation's dispatch outcome and
            evaluation result, in the order taken.
        configured (int): How many observations the run takes before any
            escalation, *k* in section 8.2.2.

    Returns:
        list[CaseStep]: Steps 1 to *k*, the escalation steps, then the
        comparison. **An escalation step not taken is recorded as not run**,
        saying whether it was not earned or earned and not dispatched; the
        rule deciding which is :func:`cmn.observations.further_observations`.
    """
    steps = [
        observation_step(number, outcome, result)
        for number, (outcome, result) in enumerate(observations, start=1)
    ]
    earned = further_observations(
        [step.verification.outcome == _REACHED for step in steps[:configured]]
    )
    reason = (
        f"{earned} further observation(s) earned and not dispatched"
        if earned
        else f"not earned, the first {configured} observation(s) having agreed"
    )
    missing = escalation_size() - max(0, len(steps) - configured)
    for _ in range(max(0, missing)):
        number = len(steps) + 1
        steps.append(CaseStep(
            number,
            StepOutcome(
                number, _ACTION, "dispatch the escalation observation", _NOT_RUN,
                reason, "", _STEP,
            ),
            StepOutcome(number, _VERIFY, "it met the rule", _NOT_RUN, reason, "", _STEP),
        ))
    outcomes = [
        _measured_outcome(step.verification.outcome)
        for step in steps if step.phases
    ]
    steps.append(consistency_step(len(steps) + 1, outcomes))
    return steps


def step_lines(case_id: str, steps: Sequence[CaseStep]) -> list[str]:
    """Return the log lines for a case's steps, each phase beneath its half.

    Args:
        case_id (str): Which case, carried on every line per section 8.2.
        steps (Sequence): The steps.

    Returns:
        list[str]: Per step, its ACTION line, the dispatch phases, its VERIFY
        line, then the evaluation phases.
    """
    lines: list[str] = []
    for step in steps:
        lines.append(f"{case_id} | {step.action.line}")
        lines += [f"{case_id} |   {entry.line}" for entry in step.action_phases]
        lines.append(f"{case_id} | {step.verification.line}")
        lines += [f"{case_id} |   {entry.line}" for entry in step.verification_phases]
    return lines


def _halted(entries: list[StepOutcome]) -> tuple[str, str, str]:
    """Return a step half's state from the phases beneath it.

    Args:
        entries (list): The phases, in order.

    Returns:
        tuple: The first failed or unrun phase's state, a detail naming that
        phase, and its code; ``ok`` where every phase ran or did not apply.
    """
    halt = stopped_at(entries)
    if halt is None:
        return _REACHED, "", ""
    return (
        halt.outcome,
        f"stopped at {halt.prefix}_{halt.number:02d}_{halt.phase}",
        halt.taxonomy_code,
    )


def _measured_outcome(state: str) -> Optional[bool]:
    """Return an observation's result as the comparison reads it.

    Args:
        state (str): The observation step's verification outcome.

    Returns:
        Optional[bool]: True verified, False failed, None measured nothing.
    """
    if state == _REACHED:
        return True
    if state == _FAILED:
        return False
    return None


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
