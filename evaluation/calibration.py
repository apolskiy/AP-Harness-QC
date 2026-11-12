# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Checks whether the LLM judge catches the mistakes in authored calibration samples.

Created: 2026-09-26
Last updated: 2026-11-12

This file contains :class:`CalibrationSample`, one authored response to one
case, clean or carrying one or two named mistakes; ``calibration_context``,
which builds the graded path's observation from a case and a sample;
``calibrate_sample``, which evaluates a sample through that path and returns a
:class:`CalibrationOutcome`; ``deterministic_disagreement`` and
``judge_disagreement``, which compare the result with what the sample
declares; ``uncalibrated_message``, the report for a family that disagreed;
and ``observation_variance``, the spread across a case's repeat observations.

**A sample states its mistake and the judge either catches it or does not.**
Nothing here compares a score with a level, because a level is an opinion about
prose and four of four misses in the first live run of exemplar placement were
the labels' fault. Specified by ``docs/design/tier3_evaluation.md`` section 9.

**Calibration reuses the graded path unchanged.** A sample is evaluated by
``evaluate_observation`` as a recorded response would be; this file decides
only what the result has to show.

**Calibration runs on the schedule, not on pull requests**, because it requires
live judge invocation. Its deterministic half needs no judge (section 9.1.2).
"""

from dataclasses import dataclass
from typing import Any, Final, Optional

from evaluation.aggregation import aggregate
from evaluation.answer_list import CLARIFICATION_ROUTE
from evaluation.isolation import UnauthoredMaterial
from evaluation.judge import JudgeBinding, validate_judge_reply
from evaluation.pipeline import (
    DECLARED_ADVERSARIAL,
    ObservationContext,
    evaluate_observation,
)

# The prefix on a calibration observation's task, which no graded judgement's
# task carries, so a recording judge stores the two apart (section 9.1.1).
_CALIBRATION_PREFIX: Final[str] = "calibration."

# THE MOST MISTAKES ONE SAMPLE CARRIES, so a judge missing it is reported
# against no more than two (section 9.1).
_MOST_VIOLATED: Final[int] = 2

_FIELDS: Final[frozenset[str]] = frozenset(
    {"sample_id", "task_id", "rule_id", "response", "violates", "mistake"}
)
_REQUIRED: Final[tuple[str, ...]] = ("sample_id", "task_id", "rule_id", "response")

# WHY THE GRADED PATH WOULD NOT ASK THE JUDGE, for reasons belonging to the
# sample or its case rather than to the binding. A sample meeting one measures
# no judge (section 9.1.2).
_NEVER_JUDGED: Final[frozenset[str]] = frozenset({
    "screen_abort",
    "provider_refused",
    "no_output_produced",
    "fatal_assertion_failure",
    DECLARED_ADVERSARIAL,
    "no_rubric_authored",
})

# THE GRADED PATH'S REASON WHEN THE JUDGE WAS ASKED AND NOTHING CAME BACK.
_UNAVAILABLE: Final[str] = "judgement_unavailable"

# CRITERIA ARE READ ONE BY ONE through the registered minimum, so a mistake the
# judge caught on one criterion counts though the mean clears the threshold.
_LOWEST: Final[str] = "min"


@dataclass(frozen=True)
class CalibrationSample:
    """One authored response to one case, clean or carrying one or two named mistakes.

    Attributes:
        sample_id (str): Its identifier, unique within the consumer's samples.
        task_id (str): The task it answers.
        rule_id (str): The rule set judging it.
        response (str): The text the judge is shown as the candidate output.
        violates (tuple): What its mistake breaks that a deterministic check
            reads: a constraint identifier, or a check's own identifier where
            the check names no constraint. Empty for a clean sample and for a
            mistake only the judge can see.
        mistake (str): What is wrong, in one plain statement. Empty for a clean
            sample.
    """

    sample_id: str
    task_id: str
    rule_id: str
    response: str
    violates: tuple[str, ...] = ()
    mistake: str = ""

    @property
    def flawed(self) -> bool:
        """Report whether the sample carries a mistake.

        Returns:
            bool: True where a mistake is stated.
        """
        return bool(self.mistake)

    @property
    def case_id(self) -> str:
        """Return the case the sample answers.

        Returns:
            str: ``<task_id>::<rule_id>``.
        """
        return f"{self.task_id}::{self.rule_id}"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CalibrationSample":
        """Build a sample from an authored mapping, refusing one that cannot be reported on.

        Design: ``tier3_evaluation.md`` section 9.1.

        Args:
            payload (dict): The authored sample.

        Returns:
            CalibrationSample: The frozen record.

        Raises:
            KeyError: ``QC_DATA_MALFORMED_SOURCE``, on an unknown field or a
                required one absent or empty.
            ValueError: ``QC_DATA_INVARIANT_VIOLATION``, where ``violates``
                names more than two entries, repeats one, or is not stated
                beside its ``mistake``.
        """
        owner = str(payload.get("sample_id", "<unidentified>"))
        unknown = sorted(set(payload) - _FIELDS)
        if unknown:
            raise KeyError(
                f"QC_DATA_MALFORMED_SOURCE: calibration sample {owner} carries unknown "
                f"field(s) {unknown}"
            )
        missing = [name for name in _REQUIRED if not str(payload.get(name) or "").strip()]
        if missing:
            raise KeyError(
                f"QC_DATA_MALFORMED_SOURCE: calibration sample {owner} is missing {missing}"
            )
        violates = tuple(str(entry).strip() for entry in payload.get("violates") or ())
        mistake = str(payload.get("mistake") or "").strip()
        _refuse_unreportable(owner, violates, mistake)
        return cls(
            sample_id=str(payload["sample_id"]).strip(),
            task_id=str(payload["task_id"]).strip(),
            rule_id=str(payload["rule_id"]).strip(),
            response=str(payload["response"]),
            violates=violates,
            mistake=mistake,
        )


@dataclass(frozen=True)
class CalibrationOutcome:
    """One sample, evaluated through the graded path and compared with what it declares.

    Attributes:
        sample (CalibrationSample): The sample.
        result (Any): The graded path's ``EvaluationResult``, carrying the
            judge prompt and reply for review.
        disagreement (str): What disagreed with the sample, empty where our
            checks and the judge both agreed.
    """

    sample: CalibrationSample
    result: Any
    disagreement: str

    @property
    def agreed(self) -> bool:
        """Report whether our checks and the judge both agreed with the sample.

        Returns:
            bool: True where nothing disagreed.
        """
        return not self.disagreement


def calibration_case_id(case_id: str, sample_id: str) -> str:
    """Return the identifier a calibration observation is judged and stored under.

    Design: ``tier3_evaluation.md`` section 9.1.1.

    Args:
        case_id (str): The case the sample answers, ``<task>::<rule>``.
        sample_id (str): The sample.

    Returns:
        str: ``calibration.<task>::<rule>.<sample>``, whose task part no graded
        judgement shares.
    """
    task_id, _, rule_id = case_id.partition("::")
    return f"{_CALIBRATION_PREFIX}{task_id}::{rule_id or '_'}.{sample_id}"


def calibration_context(case: Any, sample: CalibrationSample) -> ObservationContext:
    """Build the graded path's observation for a sample: its response and the case's material.

    Design: ``tier3_evaluation.md`` section 9.1.

    Args:
        case (Any): The case, carrying ``case_id``, ``task`` and ``golden_rules``.
        sample (CalibrationSample): The sample answering it.

    Returns:
        ObservationContext: The sample as the candidate output, with the
        task's system instruction, prompt and documents, the case's rule set,
        and the task's declared payload and offered tools.
    """
    task = case.task
    return ObservationContext(
        case_id=calibration_case_id(case.case_id, sample.sample_id),
        rules=case.golden_rules,
        material=UnauthoredMaterial(
            candidate_output=sample.response,
            system_instruction=task.system_instruction,
            task_instruction=task.user_prompt,
            context_documents={
                document.document_id: document.content for document in task.context_documents
            },
        ),
        declared_adversarial=bool(task.contains_adversarial_content),
        offered_tools=tuple(task.available_tools),
    )


def calibrate_sample(
    case: Any, sample: CalibrationSample, binding: JudgeBinding
) -> CalibrationOutcome:
    """Evaluate a sample through the graded path, then compare our checks and the judge with it.

    Design: ``tier3_evaluation.md`` section 9.1.

    Args:
        case (Any): The case the sample answers.
        sample (CalibrationSample): The sample.
        binding (JudgeBinding): The judge being calibrated.

    Returns:
        CalibrationOutcome: The result and what disagreed, our checks first.

    Raises:
        ValueError: Led by the harness code the channel carried, where the
            judge was asked and could not be reached: nothing was measured.
    """
    result = evaluate_observation(
        calibration_context(case, sample), binding, judge_on_failure=True
    )
    if result.judge_skipped_reason == _UNAVAILABLE:
        # THE PIPELINE APPENDS THE HARNESS CODE LAST on every unavailable path.
        raise ValueError(
            f"{result.taxonomy_codes[-1]}: calibration sample {sample.sample_id} "
            f"received no judgement"
        )
    disagreement = deterministic_disagreement(sample, case, result) or judge_disagreement(
        sample, case, result, binding
    )
    return CalibrationOutcome(sample=sample, result=result, disagreement=disagreement)


def deterministic_disagreement(sample: CalibrationSample, case: Any, result: Any) -> str:
    """Compare what our checks found with what the sample declares, reading nothing the judge made.

    Design: ``tier3_evaluation.md`` section 9.1.2.

    Args:
        sample (CalibrationSample): The sample.
        case (Any): The case it answers, whose assertions name their constraints.
        result (Any): The graded path's result for the sample.

    Returns:
        str: Empty where the failed checks are exactly ``violates``;
        otherwise the sample, what disagreed, and why. A sample the graded
        path would never judge is reported, since it calibrates nothing.
    """
    if result.judge_skipped_reason in _NEVER_JUDGED:
        return (
            f"{sample.sample_id} cannot calibrate: the judge is never asked "
            f"({result.judge_skipped_reason})"
        )
    constraints = {
        entry.assertion_id: entry.constraint_ref
        for entry in getattr(case.golden_rules, "assertions", None) or []
    }
    failed = sorted({
        constraints.get(check.assertion_id) or check.assertion_id
        for check in result.assertion_results if not check.passed
    })
    unnamed = [entry for entry in failed if entry not in sample.violates]
    held = [entry for entry in sample.violates if entry not in failed]
    if not unnamed and not held:
        return ""
    parts = []
    if unnamed:
        parts.append(f"our checks failed {unnamed}, which it does not name")
    if held:
        parts.append(f"our checks held on {held}, which it names")
    return f"{sample.sample_id} ({_declared(sample)}): " + "; ".join(parts)


def judge_disagreement(
    sample: CalibrationSample, case: Any, result: Any, binding: JudgeBinding
) -> str:
    """Compare the judge's lowest criterion with what the sample declares.

    Design: ``tier3_evaluation.md`` section 9.1.

    Args:
        sample (CalibrationSample): The sample.
        case (Any): The case it answers.
        result (Any): The graded path's judged result.
        binding (JudgeBinding): The judge, for validating its reply again.

    Returns:
        str: Empty where a clean sample has every criterion at or above the
        threshold and a flawed one has at least one below it; otherwise the
        sample, what it declares and every criterion's score.
    """
    if not result.judged:
        return f"{sample.sample_id} was not judged ({result.judge_skipped_reason})"
    rubric = _rubric_read(case.golden_rules, result)
    reply = validate_judge_reply(
        result.judge_reply, rubric, binding,
        case_id=result.case_id, observation_index=0,
    )
    lowest = aggregate(_LOWEST, reply.scores, threshold=rubric.threshold)
    caught = lowest.passed is False
    if caught == sample.flawed:
        return ""
    scores = ", ".join(f"{entry.criterion_id} {entry.score:g}" for entry in reply.scores)
    verdict = (
        f"the judge scored every criterion at or above {rubric.threshold:g}"
        if sample.flawed
        else f"the judge scored a criterion below {rubric.threshold:g}"
    )
    return f"{sample.sample_id} ({_declared(sample)}): {verdict}: {scores}"


def uncalibrated_message(family: str, failures: list[str]) -> str:
    """Return the report for a family whose samples the judge or our checks disagreed with.

    Design: ``tier3_evaluation.md`` section 9.3.

    Args:
        family (str): The evaluation family calibrated.
        failures (list[str]): One disagreement per sample.

    Returns:
        str: The message, led by ``QC_HARNESS_JUDGE_UNCALIBRATED``.
    """
    return (
        f"QC_HARNESS_JUDGE_UNCALIBRATED: {len(failures)} {family} calibration "
        f"sample(s) disagreed: " + "; ".join(failures)
    )


def observation_variance(scores: list[float]) -> Optional[float]:
    """Return the spread across A4's repeat observations.

    **High variance on identical input means the anchors are not
    discriminating**, which is a drift signal needing no new machinery: the
    three observations already exist.

    Args:
        scores (list): One score per observation.

    Returns:
        Optional[float]: The range between the highest and lowest, or ``None``
        with fewer than two observations, where spread is undefined rather than
        zero. Reporting zero would make a single observation look maximally
        consistent.
    """
    if len(scores) < 2:
        return None
    return max(scores) - min(scores)


def _refuse_unreportable(owner: str, violates: tuple[str, ...], mistake: str) -> None:
    """Refuse a sample whose mistake a report could not state.

    Args:
        owner (str): The sample, for the message.
        violates (tuple): What it declares broken.
        mistake (str): What it says is wrong.

    Returns:
        None

    Raises:
        ValueError: ``QC_DATA_INVARIANT_VIOLATION``, for more than two
            entries, a repeated or empty one, or entries without a mistake.
    """
    if len(violates) > _MOST_VIOLATED:
        problem = f"names {len(violates)} violations; a sample carries one or two"
    elif len(set(violates)) != len(violates) or "" in violates:
        problem = f"names a violation twice or empty: {list(violates)}"
    elif violates and not mistake:
        problem = "names a violation without stating its mistake"
    else:
        return
    raise ValueError(f"QC_DATA_INVARIANT_VIOLATION: calibration sample {owner} {problem}")


def _rubric_read(rules: Any, result: Any) -> Any:
    """Return the rubric the judge scored: the clarification one where the answer took that route.

    Args:
        rules (Any): The case's rule set.
        result (Any): The judged result, recording the route.

    Returns:
        Any: The rubric.
    """
    if result.answer_route == CLARIFICATION_ROUTE:
        return rules.answer_list.clarification_rubric
    return rules.rubric


def _declared(sample: CalibrationSample) -> str:
    """Return what a sample declares, as a report states it.

    Args:
        sample (CalibrationSample): The sample.

    Returns:
        str: ``clean``, or its mistake and what it breaks.
    """
    if not sample.flawed:
        return "clean"
    broken = ", ".join(sample.violates) if sample.violates else "no checked constraint"
    return f"{sample.mistake}; breaks {broken}"
