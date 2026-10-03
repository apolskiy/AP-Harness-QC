# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The order of operations, and the decisions that live between the steps.

Specified by ``docs/design/tier3_evaluation.md`` sections 4, 4.0 and 4.2.

1. Screen the candidate output.
2. Isolate it into the typed field.
3. Run programmatic assertions.
4. Invoke the judge, subject to section 4.2.
5. Validate the judge reply.
6. Aggregate.

**A case passes only when every assertion passes and the rubric clears its
threshold.** Conformance gates the outcome and the rubric measures quality
within it, so an assertion failure fails the case regardless of the score.

**A declared adversarial case reaches no judge at all** (A19). Resistance is a
string check, not a judgement: a payload carries a canary, the response either
contains it or does not, and `not_contains` settles the question exactly. The
exposure is removed rather than mitigated, which is what isolation alone cannot
do for content a judge is meant to read.

**Priority never arrives here.** It is test metadata consumed by ``CMN``, and
nothing about how severely a failure is treated should be visible to the
component deciding whether it failed.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Final, Optional

from evaluation.aggregation import AggregateScore, aggregate
from evaluation.assertions import (
    AssertionResult,
    assertions_passed,
    has_fatal_failure,
    run_assertions,
)
from evaluation.tool_compliance import evaluate_tool_compliance
from evaluation.isolation import UnauthoredMaterial, compose_judge_request
from evaluation.judge import (
    JudgeBinding,
    JudgeHijackSuspected,
    JudgeReply,
    validate_judge_reply,
)
from evaluation.screening import ScreenDecision, screen_response

logger = logging.getLogger(__name__)

# The judge-skip reason recorded for a case that declares a payload. Named once
# because the skip and the verdict must agree on it: they are two halves of one
# decision and a typo in either would separate them silently.
DECLARED_ADVERSARIAL: Final[str] = "declared_adversarial"


@dataclass(frozen=True)
class ObservationContext:
    """One candidate observation, with everything needed to evaluate it.

    Attributes:
        case_id (str): Which case.
        rules (Any): The **evaluation-relevant subset** of the golden rule set:
            its assertions, rubric and tool expectation. Typed loosely so Tier 3
            does not import Tier 1's record for an attribute walk, and carrying
            no priority, which section 2 forbids reaching here at all.
        material (UnauthoredMaterial): Everything the harness did not author.
        declared_adversarial (bool): Whether the case declares a payload. A
            declared case is graded by assertion and never judged.
        observation_index (int): Which of the repeat observations (A4).
        blocked_by (str): The provider's word for refusing, empty where it
            did not refuse. **A refusal is resistance for a declared adversarial
            case**, whichever layer enforced it: nothing here can see whether a
            given vendor filtered at the model, the API or the edge, so crediting
            only a model-level refusal would score an implementation detail.
        blocked_at (str): ``prompt`` or ``response``, kept beside the reason so a
            later change of requirements re-reads the corpus instead of
            re-running it.
        produced_output (bool): Whether the response carried anything to
            evaluate. **Error is error**: a turn the provider reported as
            failed, and one that returned neither text nor a tool call, are
            the same condition here (design section 4.2.1).
        tool_calls (tuple): What the model invoked, captured and never
            executed. **Here and not on** :class:`UnauthoredMaterial`, because
            that record exists to be isolated into a judge request and a tool
            name is attacker-influenced text. The compliance check is
            programmatic, so nothing here reaches the judge (section 5B.3).
        offered_tools (tuple): The tools the task offered, carrying their
            declared parameter schemas. Needed to report a name the model
            invented, which no forbidden list would have caught.
    """

    case_id: str
    rules: Any
    material: UnauthoredMaterial
    declared_adversarial: bool = False
    observation_index: int = 0
    produced_output: bool = True
    blocked_by: str = ""
    blocked_at: str = ""
    tool_calls: tuple[Any, ...] = ()
    offered_tools: tuple[Any, ...] = ()


@dataclass(frozen=True)
class EvaluationResult:
    """What evaluating one candidate observation produced.

    Attributes:
        case_id (str): Which case.
        screen (ScreenDecision): What the screen found.
        assertion_results (list): One result per assertion, empty when the
            screen aborted before they ran.
        score (Optional[AggregateScore]): The aggregated rubric result, absent
            when no judgement was made.
        provider_refusal (str): ``stage:reason`` where the provider declined to
            answer a declared adversarial case, empty otherwise. **Evidence, not
            a verdict**: it is what justifies the pass below, and keeping the
            stage beside the reason means a change of requirements re-reads the
            corpus rather than re-running it.
        judge_skipped_reason (Optional[str]): Why no judgement was made.
        checks_ran (bool): Whether the rule's declared checks executed.
            **Not whether anything was reported.** A tool check that holds
            reports nothing, so results-exist and a-check-ran coincide only
            for a check that announces success, and none of ours does
            (design section 4D).

            **False where the evaluation returned early.** A screen abort or an
            empty response skips the assertions, so the checks were declared
            and did not run, and a case that measured nothing must not pass.
        rubric_authored (bool): Whether a rubric exists to be cleared. Absent
            and unscored are different: a rule authoring none declares itself
            fully decided by its deterministic checks, while one whose rubric
            went unscored was meant to measure something and did not.
            **Recorded rather than left absent**: a missing score and a score of
            zero are different facts, and so are a skipped judgement and a
            failed one.
        judge_on_failure (bool): Whether the flag was in force. Recorded
            because whether a failed case carries a score depends on it, and a
            reviewer comparing two runs must not read a skipped judgement as a
            different outcome.
        self_preference (bool): Whether judge and candidate shared a provider.
        taxonomy_codes (list): Every code this evaluation emitted.
    """

    case_id: str
    screen: ScreenDecision
    assertion_results: list[AssertionResult] = field(default_factory=list)
    score: Optional[AggregateScore] = None
    judge_skipped_reason: Optional[str] = None
    checks_ran: bool = False
    rubric_authored: bool = False
    judge_on_failure: bool = False
    self_preference: bool = False
    taxonomy_codes: list[str] = field(default_factory=list)
    provider_refusal: str = ""

    @property
    def judged(self) -> bool:
        """Report whether a judgement was made.

        Returns:
            bool: True when a rubric score exists.
        """
        return self.score is not None and self.score.evaluated

    @property
    def passed(self) -> bool:
        """Report whether the case passed.

        Returns:
            bool: **Conjunctive.** Every assertion must pass and the rubric must
            clear its threshold. A screen abort fails, and an unjudged case has
            no rubric verdict to clear, so it does not pass on the strength of
            its assertions alone.

            **Unless the judge was skipped because the case declares a
            payload**, which is the one case where the assertions ARE the whole
            measurement. A19 removes the judge from an adversarial case
            deliberately, so requiring a rubric verdict there made a resisting
            model unable to pass at all (design section 4C).

            **A case carrying no assertion results still fails**, and that
            matters most here: a security case whose assertions were never
            written would otherwise pass by having nothing to fail.
        """
        if self.screen.aborts:
            return False
        if self.provider_refusal:
            # THE PROVIDER REFUSED, WHICH IS RESISTANCE. Applies to every
            # declared adversarial case, not to one: whichever layer enforced it,
            # the attack did not land, and no consumer of this harness can see
            # whether a vendor filters at the model, the API or the edge (design
            # section 4.2.2).
            #
            # THIS IS NOT A RELAXATION OF THE RULE BELOW. That rule refuses to
            # pass a case with no assertion results, because a security case
            # whose assertions were never written would pass by having nothing
            # to fail. This passes on evidence the provider supplied, which an
            # unwritten assertion does not produce.
            return True
        if not self.checks_ran:
            return False
        if not assertions_passed(self.assertion_results):
            return False
        if not self.rubric_authored:
            # NO RUBRIC AUTHORED, so the rule declares itself fully decided by
            # its deterministic checks. This is the tool and security case, and
            # it subsumes the adversarial one: those rules author none either.
            #
            # The escape risk moves to the corpus, where it can be seen:
            # MQC_CAS_UNI_115010 reports a graded evaluation rule with no rubric.
            return True
        return bool(self.score is not None and self.score.passed)


@dataclass
class _Progress:
    """What the steps before the judge accumulated.

    Named because three of the six steps produce something the later steps
    carry forward, and passing them separately made the judging helper a list
    of positional arguments rather than a stage in a sequence.

    Attributes:
        screen (ScreenDecision): What step 1 found.
        results (list): What step 3 found.
        codes (list): Every taxonomy code emitted so far.
    """

    screen: ScreenDecision
    results: list[AssertionResult] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)



def _declared_checks(rules: Any) -> tuple[bool, bool]:
    """Return what the rule set declared, for the verdict to read.

    **Declared, not reported.** A tool check that holds reports nothing, so
    asking whether results exist answers a different question from asking
    whether a check ran (design section 4D).

    Args:
        rules (Any): The evaluation-relevant subset of the rule set.

    Returns:
        tuple[bool, bool]: Whether anything is checked at all, and whether a
        rubric was authored. G1 already refuses to load a rule set declaring
        none of the three, so the first is False only for a double built in a
        test.
    """
    rubric = getattr(rules, "rubric", None) is not None
    declared = bool(
        getattr(rules, "assertions", None)
        or getattr(rules, "tool_expectation", None) is not None
        or rubric
    )
    return declared, rubric


def evaluate_observation(
    context: ObservationContext,
    binding: Optional[JudgeBinding] = None,
    *,
    judge_on_failure: bool = False,
) -> EvaluationResult:
    """Evaluate one candidate observation against one rule set.

    Args:
        context (ObservationContext): The observation and what judges it.
        binding (Optional[JudgeBinding]): Who judges, and whose output. An
            absent or unbound judge is recorded as a skip with its reason.
        judge_on_failure (bool): Whether to judge a case whose assertions
            failed at ``violation`` severity.


    Returns:
        EvaluationResult: What the six steps produced.
    """
    bound = binding or JudgeBinding()
    declared, rubric_authored = _declared_checks(context.rules)
    progress = _Progress(
        screen=screen_response(
            context.case_id,
            context.material.candidate_output,
            declared_adversarial=context.declared_adversarial,
        )
    )
    if progress.screen.taxonomy_code is not None:
        progress.codes.append(progress.screen.taxonomy_code)

    if progress.screen.aborts:
        # Step 4.4: nothing after step 2 runs. There is nothing to score, and
        # forwarding the content is the risk the screen exists to prevent.
        logger.warning("%s screen aborted the evaluation", context.case_id)
        return EvaluationResult(
            case_id=context.case_id, screen=progress.screen,
            judge_skipped_reason="screen_abort",
            judge_on_failure=judge_on_failure, taxonomy_codes=progress.codes,
            checks_ran=False, rubric_authored=rubric_authored,
        )

    if not context.produced_output and context.blocked_by and context.declared_adversarial:
        # A REFUSAL THE PROVIDER OWNED UP TO, which is a different fact from an
        # empty response and is why this sits above the check below rather than
        # inside it. Section 4.2.1 refuses to read an absence as resistance
        # because every absence assertion is satisfied by the absence of
        # everything; a named block reason is an affirmative act, not an absence.
        #
        # WHICH LAYER REFUSED IS NOT KNOWABLE AND NOT THE QUESTION. The project
        # owner's decision, 2026-09-28: security is in place whether the model,
        # the API or the provider's filter enforced it, and no consumer of this
        # harness can see which. Design section 4.2.2.
        #
        # THE EVIDENCE IS CARRIED, not just the verdict, so that reclassifying
        # this later is a re-reading rather than another paid run.
        logger.info(
            "%s refused by the provider at the %s stage (%s), recorded as "
            "resistance for a declared adversarial case",
            context.case_id, context.blocked_at or "unreported", context.blocked_by,
        )
        return EvaluationResult(
            case_id=context.case_id, screen=progress.screen,
            judge_skipped_reason="provider_refused",
            judge_on_failure=judge_on_failure, taxonomy_codes=progress.codes,
            checks_ran=False, rubric_authored=rubric_authored,
            provider_refusal=f"{context.blocked_at or 'unreported'}:{context.blocked_by}",
        )

    if not context.produced_output:
        # Section 4.2.1. The assertions are skipped as well as the judge, and
        # that is the part that matters: a not_contains assertion against an
        # empty response PASSES, so a model that never answered would be
        # recorded as having resisted the attack. Every assertion that asserts
        # an absence is satisfied by the absence of everything.
        logger.warning(
            "QC_LLM_NO_OUTPUT %s produced no output; nothing to assert or judge",
            context.case_id,
        )
        progress.codes.append("QC_LLM_NO_OUTPUT")
        return EvaluationResult(
            case_id=context.case_id, screen=progress.screen,
            judge_skipped_reason="no_output_produced",
            judge_on_failure=judge_on_failure, taxonomy_codes=progress.codes,
            checks_ran=False, rubric_authored=rubric_authored,
        )

    progress.results = run_assertions(
        getattr(context.rules, "assertions", None) or [],
        context.material.candidate_output,
    )

    # STEP 3B. Tool compliance is an assertion in everything but where it is
    # declared, so its results join the same list and gate the same way.
    # Gate 5 was specified without this entirely; tier3_evaluation.md 5B.
    progress.results.extend(
        evaluate_tool_compliance(
            context.tool_calls,
            getattr(context.rules, "tool_expectation", None),
            context.offered_tools,
        )
    )

    progress.codes.extend(
        result.taxonomy_code for result in progress.results
        if result.taxonomy_code is not None
    )

    reason = _judge_skip_reason(
        progress.results, context, bound, judge_on_failure=judge_on_failure
    )
    if reason is not None:
        return EvaluationResult(
            case_id=context.case_id, screen=progress.screen,
            assertion_results=progress.results, judge_skipped_reason=reason,
            judge_on_failure=judge_on_failure, taxonomy_codes=progress.codes,
            checks_ran=declared, rubric_authored=rubric_authored,
        )

    return _judge_and_aggregate(
        context, bound, progress, judge_on_failure=judge_on_failure
    )


def _judge_skip_reason(
    results: list[AssertionResult],
    context: ObservationContext,
    binding: JudgeBinding,
    *,
    judge_on_failure: bool,
) -> Optional[str]:
    """Decide whether the judge runs, and say why when it does not.

    Args:
        results (list): What the assertions found.
        context (ObservationContext): The observation.
        binding (JudgeBinding): Who would judge.
        judge_on_failure (bool): Whether the flag is in force.

    Returns:
        Optional[str]: The reason to record, or ``None`` when the judge runs.
    """
    if context.declared_adversarial:
        # A19: the exposure is removed rather than mitigated. No judge is
        # invoked, so no payload reaches one.
        return DECLARED_ADVERSARIAL
    if has_fatal_failure(results):
        # Never judged, flag or not. There is nothing coherent to score and the
        # request would spend quota to produce noise.
        return "fatal_assertion_failure"
    if not assertions_passed(results) and not judge_on_failure:
        return "violation_assertion_failure"
    if not binding.available:
        return "no_judge_configured"
    if context.rules.rubric is None:
        # NOTHING TO GRADE, which is not the same as nobody to grade it.
        # Section 4D permits a rule carrying no rubric: an EVAL rule exists to
        # be judged and a tool or security rule does not. Without this the
        # composer dereferenced None three frames away. Design section 5A.6.
        return "no_rubric_authored"
    return None


def _judge_and_aggregate(
    context: ObservationContext,
    binding: JudgeBinding,
    progress: _Progress,
    *,
    judge_on_failure: bool,
) -> EvaluationResult:
    """Run steps 4 through 6 for a case that reached the judge.

    Args:
        context (ObservationContext): The observation.
        binding (JudgeBinding): Who judges, and whose output.
        progress (_Progress): What the earlier steps accumulated.
        judge_on_failure (bool): Whether the flag was in force.

    Returns:
        EvaluationResult: The judged result, or a recorded skip when the judge
        could not produce a usable one.
    """
    declared, rubric_authored = _declared_checks(context.rules)
    rubric = context.rules.rubric
    request = compose_judge_request(
        context.case_id, rubric, context.material,
        observation_index=context.observation_index,
    )

    try:
        reply = validate_judge_reply(
            binding.invoke(request), rubric, binding,
            case_id=context.case_id, observation_index=context.observation_index,
        )
    except JudgeHijackSuspected:
        # Blocking, and deliberately not caught here. A hijacked judge is a
        # security finding about the run, not a quality finding about the case.
        raise
    except ValueError as error:
        logger.warning("%s judgement unusable: %s", context.case_id, error)
        return EvaluationResult(
            case_id=context.case_id, screen=progress.screen,
            assertion_results=progress.results,
            judge_skipped_reason="judge_reply_unusable",
            judge_on_failure=judge_on_failure,
            taxonomy_codes=progress.codes + ["QC_HARNESS_PARSER_ERROR"],
            checks_ran=declared, rubric_authored=rubric_authored,
        )

    if reply.self_preference:
        logger.info(
            "%s judged by its own provider; coincidence recorded", context.case_id
        )
    if reply.format_violations:
        progress.codes.append("QC_LLM_FORMAT_VIOLATION")

    score = aggregate(
        rubric.aggregation, reply.scores, threshold=rubric.threshold,
        parameters=dict(getattr(rubric, "aggregation_params", None) or {}),
    )
    if score.passed is False:
        progress.codes.append("QC_LLM_RUBRIC_FAILURE")

    return EvaluationResult(
        case_id=context.case_id, screen=progress.screen,
        assertion_results=progress.results, score=score,
        judge_on_failure=judge_on_failure,
        self_preference=reply.self_preference, taxonomy_codes=progress.codes,
        checks_ran=declared, rubric_authored=rubric_authored,
    )



def judgements_for_observations(replies: list[JudgeReply]) -> int:
    """Return how many distinct observations were judged.

    **One judgement per candidate observation** (design section 6.3). A4 gives
    three responses and the judge scores each once. Sampling the judge
    repeatedly against one response would confound judge variance with candidate
    variance in a single number; judge consistency is measured separately,
    against fixed calibration exemplars.

    Args:
        replies (list): The judge replies collected for one case.

    Returns:
        int: The count of distinct observation indices.
    """
    return len({reply.observation_index for reply in replies})
