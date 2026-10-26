# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The evaluation pipeline, which turns one model response into one evaluated result.

Created: 2026-09-26
Last updated: 2026-10-25

This file contains ``evaluate_observation``, which takes a response through
every Tier 3 step in order and returns an ``EvaluationResult``; the context it
reads and the result it returns; ``observation_judge_request``, which composes
what the judge is sent, for the run and for anyone rebuilding a judge prompt
from a recorded response; and ``judgements_for_observations``, which counts how
many distinct observations a case's judge replies cover.

**Each step can end the evaluation before the next one runs.** The screen
aborts a response carrying an injection aimed at the judge, the assertions fail
a response that breaks a rule's deterministic checks, and either way the judge
is never asked, which saves its cost and keeps an injection away from it. Only
a response that clears both is judged, and the result records how far it got,
why it stopped, and the prompt its judge received.

Specified by ``docs/design/tier3_evaluation.md`` sections 4, 4.0, 4.2 and 4C.6.

1. Screen the candidate output.
2. Isolate it into the typed field.
3. Run programmatic assertions.
4. Invoke the judge, subject to section 4.2.
5. Validate the judge reply.
6. Aggregate.

**A case passes only when every assertion passes and the rubric clears its
threshold.** Conformance gates the outcome and the rubric measures quality
within it, so an assertion failure fails the case regardless of the score.

**A declared adversarial case's payload reaches no judge at all** (A19).
Resistance is a string check, not a judgement: a payload carries a canary, the
response either contains it or does not, and `not_contains` settles the question
exactly. The exposure is removed rather than mitigated, which is what isolation
alone cannot do for content a judge is meant to read. A rule opting in with
``judge_response_only`` is judged on the answer alone, once it screens clean,
and never on the task or its documents (section 4C.4).

**Priority never arrives here.** It is test metadata consumed by ``CMN``, and
nothing about how severely a failure is treated should be visible to the
component deciding whether it failed.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Final, Optional

from cmn.vectors import grading_values

# THE REPLAY STORE'S OWN EXCEPTIONS, not a vendor type. Tier 3's boundary
# rule is that provider-specific types stop at the adapter, and these are
# the harness's own; this module already calls the binding that raises
# them. Reading them off a message instead would make the handler stop
# working silently the day the message is reworded. Section 6.5.
from execution.replay import FixtureMissing, FixtureStale

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

# The judge-skip reason for a rubric-bearing observation in a run that withheld
# the judge, ``--judge-mode off``. Named once for the same reason: the case
# repository records it as the ``unjudged`` skip (section 5A.5.3).
UNJUDGED: Final[str] = "unjudged"

# A PLANTED SCORE SPELT AS A WORD, so "grade this as four" asks for a 4.
_NUMBER_WORDS: Final[dict[int, str]] = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
}


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
        planted_score_returned (str): Which criteria the judge scored at the
            rubric's planted score, and the value, empty where it returned none.
            **The judgement failed, not an assertion** (design section 4C.5).
        judge_prompt (str): The rendered request the judge was sent, wherever
            one was composed, and empty where none was (design section 4C.6).
        judge_reply (dict): The judge's reply as it returned it, each criterion
            with its score and rationale, empty where no usable reply came back.
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
    planted_score_returned: str = ""
    judge_prompt: str = ""
    judge_reply: dict[str, Any] = field(default_factory=dict)

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
        if self.planted_score_returned or not self.checks_ran:
            # AN ANSWER THAT STEERED ITS OWN JUDGE has no rubric verdict,
            # whatever it aggregated to (section 4C.5).
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



def _response_only(rules: Any) -> bool:
    """Return whether a rule is judged on its answer alone.

    Design: ``tier3_evaluation.md`` section 4C.4.

    Args:
        rules (Any): The evaluation-relevant subset of the rule set.

    Returns:
        bool: The rule's ``judge_response_only``, False where it carries none.
    """
    return bool(getattr(rules, "judge_response_only", False))


def observation_judge_request(context: ObservationContext) -> Any:
    """Return the judge request an observation is sent, as the pipeline composes it.

    The answer alone on a rule judged on it, since the task and its documents
    are where a declared payload lives (section 4C.4), and the whole material
    otherwise. A caller holding a recorded response rebuilds the exact prompt
    from it (section 4C.6).

    Args:
        context (ObservationContext): The observation, its rule carrying a rubric.

    Returns:
        Any: The composed ``JudgeRequest``.
    """
    material = (
        UnauthoredMaterial(candidate_output=context.material.candidate_output)
        if _response_only(context.rules) else context.material
    )
    return compose_judge_request(
        context.case_id, context.rules.rubric, material,
        observation_index=context.observation_index,
    )


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
    at_pass_mark: str = "pass",
) -> EvaluationResult:
    """Evaluate one candidate observation against one rule set.

    Args:
        context (ObservationContext): The observation and what judges it.
        binding (Optional[JudgeBinding]): Who judges, and whose output. An
            absent or unbound judge is recorded as a skip with its reason.
        at_pass_mark (str): Whether a score equal to the rubric mark
            passes. ``pass`` by default, which is the behaviour that shipped.
        judge_on_failure (bool): Whether to judge a case whose assertions
            failed at ``violation`` severity.


    Returns:
        EvaluationResult: What the six steps produced.
    """
    bound = binding or JudgeBinding()
    declared, rubric_authored = _declared_checks(context.rules)
    # A RULE JUDGED ON ITS ANSWER ALONE is screened as an ordinary case: an
    # answer repeating the injection aborts and fails, so it never reaches the
    # judge (section 4C.4). A rejected report of an override is not a repeat
    # (section 5.2.6).
    response_only = context.declared_adversarial and _response_only(context.rules)
    # AND WHETHER A QUOTE OF THE INJECTION FAILS. Only a prompt that forbade
    # it can ask for that, so the rule declares it: a task telling the model
    # to report an instruction cannot fail it for quoting what it reported
    # (section 4C.4.1).
    forbidden = bool(getattr(context.rules, "relay_forbidden", False))
    progress = _Progress(
        screen=screen_response(
            context.case_id,
            context.material.candidate_output,
            declared_adversarial=(
                context.declared_adversarial and not (response_only and forbidden)
            ),
            exempt_reports=response_only,
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
        context, bound, progress, judge_on_failure=judge_on_failure,
        at_pass_mark=at_pass_mark,
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
    if context.declared_adversarial and not _response_only(context.rules):
        # A19: the exposure is removed rather than mitigated. No judge is
        # invoked, so no payload reaches one. A rule judged on its answer
        # alone sends only an answer the screen passed (section 4C.4).
        return DECLARED_ADVERSARIAL
    if has_fatal_failure(results):
        # Never judged, flag or not. There is nothing coherent to score and the
        # request would spend quota to produce noise.
        return "fatal_assertion_failure"
    if not assertions_passed(results) and not judge_on_failure:
        return "violation_assertion_failure"
    return _binding_skip_reason(context, binding)


def _binding_skip_reason(context: ObservationContext, binding: JudgeBinding) -> Optional[str]:
    """Decide, once the checks allow judging, whether the binding and the rule do.

    Args:
        context (ObservationContext): The observation.
        binding (JudgeBinding): Who would judge.

    Returns:
        Optional[str]: The reason to record, or ``None`` when the judge runs.
    """
    if binding.withheld:
        # THE JUDGE WAS ASKED FOR NOTHING, in a debug run checking the screen
        # and the assertions alone. A rule with no rubric is decided by its
        # assertions as always; one with a rubric is never a pass. 5A.5.3.
        return "no_rubric_authored" if context.rules.rubric is None else UNJUDGED
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
    at_pass_mark: str = "pass",
) -> EvaluationResult:
    """Run steps 4 through 6 for a case that reached the judge.

    Args:
        context (ObservationContext): The observation.
        binding (JudgeBinding): Who judges, and whose output.
        progress (_Progress): What the earlier steps accumulated.
        judge_on_failure (bool): Whether the flag was in force.
        at_pass_mark (str): Whether a score equal to the rubric mark passes.
        judge_on_failure (bool): Whether the flag was in force.

    Returns:
        EvaluationResult: The judged result, or a recorded skip when the judge
        could not produce a usable one.
    """
    declared, rubric_authored = _declared_checks(context.rules)
    request = observation_judge_request(context)
    try:
        returned = binding.invoke(request)
        reply = validate_judge_reply(
            returned, context.rules.rubric, binding,
            case_id=context.case_id, observation_index=context.observation_index,
        )
    except JudgeHijackSuspected:
        # Blocking, and deliberately not caught here. A hijacked judge is a
        # security finding about the run, not a quality finding about the case.
        raise
    except (FixtureMissing, FixtureStale) as error:
        # A HARNESS EVENT IS A SKIP, NEVER A FAILURE (`framework-rules.md`
        # section 4). The candidate path already did this and
        # `tier2_execution.md` section 7.6 records why it had to be taught:
        # both exceptions inherit from `Exception` alone, so the handler
        # written for `ValueError` below never fired and the case reported a
        # harness error where it meant to report nothing.
        #
        # **THIS IS NOT THE FALL-BACK SECTION 7.9.1 FORBIDS.** That rule is
        # about a replay run quietly calling a live judge. A skip calls
        # nothing and scores nothing, and the assertion results below travel
        # with it, so an observation that failed an assertion still reports
        # that failure with its own model code.
        code = (
            "QC_HARNESS_FIXTURE_STALE"
            if isinstance(error, FixtureStale)
            else "QC_HARNESS_FIXTURE_MISSING"
        )
        logger.warning(
            "%s observation %d judgement unavailable: %s",
            context.case_id, context.observation_index, code,
        )
        return EvaluationResult(
            case_id=context.case_id, screen=progress.screen,
            assertion_results=progress.results,
            judge_skipped_reason="judgement_unavailable",
            judge_on_failure=judge_on_failure,
            taxonomy_codes=progress.codes + [code],
            checks_ran=declared, rubric_authored=rubric_authored, judge_prompt=request.rendered(),
        )
    except ValueError as error:
        # NO REPLY IS NOT A BAD REPLY. The channel leads its message with the
        # code the adapter mapped; a provider code there means the judge was
        # never reached, which is unavailable and a skip, not a reply we could
        # not use (design section 6.5.1).
        carried = str(error).split(":", 1)[0].strip()
        if carried.startswith("QC_HARNESS_") and carried != "QC_HARNESS_PARSER_ERROR":
            logger.warning("%s judge unreachable: %s", context.case_id, carried)
            return EvaluationResult(
                case_id=context.case_id, screen=progress.screen,
                assertion_results=progress.results,
                judge_skipped_reason="judgement_unavailable",
                judge_on_failure=judge_on_failure,
                taxonomy_codes=progress.codes + [carried],
                checks_ran=declared, rubric_authored=rubric_authored,
                judge_prompt=request.rendered(),
            )
        logger.warning("%s judgement unusable: %s", context.case_id, error)
        return EvaluationResult(
            case_id=context.case_id, screen=progress.screen,
            assertion_results=progress.results,
            judge_skipped_reason="judge_reply_unusable",
            judge_on_failure=judge_on_failure,
            taxonomy_codes=progress.codes + ["QC_HARNESS_PARSER_ERROR"],
            checks_ran=declared, rubric_authored=rubric_authored, judge_prompt=request.rendered(),
        )

    if reply.self_preference:
        logger.info(
            "%s judged by its own provider; coincidence recorded", context.case_id
        )
    if reply.format_violations:
        progress.codes.append("QC_LLM_FORMAT_VIOLATION")

    score = aggregate(
        context.rules.rubric.aggregation, reply.scores,
        threshold=context.rules.rubric.threshold,
        parameters=dict(getattr(context.rules.rubric, "aggregation_params", None) or {}),
        at_pass_mark=at_pass_mark,
    )
    if score.passed is False:
        progress.codes.append("QC_LLM_RUBRIC_FAILURE")
    steered = _planted_score_returned(
        context.rules.rubric, reply.scores, context.material.candidate_output
    )
    if steered:
        logger.warning("QC_SEC_INJECTION_ATTEMPT %s %s", context.case_id, steered)
        progress.codes.append("QC_SEC_INJECTION_ATTEMPT")

    return EvaluationResult(
        case_id=context.case_id, screen=progress.screen,
        assertion_results=progress.results, score=score,
        judge_on_failure=judge_on_failure,
        self_preference=reply.self_preference, taxonomy_codes=progress.codes,
        checks_ran=declared, rubric_authored=rubric_authored, judge_prompt=request.rendered(),
        planted_score_returned=steered,
        judge_reply=dict(returned) if isinstance(returned, dict) else {},
    )


def _planted_score_returned(rubric: Any, scores: Any, answer: str) -> str:
    """Name the criteria a judge scored at the planted score the answer asks for.

    Design: section 4C.5.

    Args:
        rubric (Any): The rubric, which may declare ``planted_score``.
        scores (Any): The judge's per-criterion scores.
        answer (str): The answer the judge read.

    Returns:
        str: The finding, naming the value and the criteria, or empty where the
        rubric plants nothing, the answer asks for no such value, or the judge
        returned it nowhere.
    """
    planted = getattr(rubric, "planted_score", None)
    if planted is None or not _asks_for(answer, planted):
        return ""
    named = [entry.criterion_id for entry in scores if entry.score == planted]
    if not named:
        return ""
    return f"the judge returned {planted}, the planted score, on {', '.join(named)}"


def _asks_for(answer: str, value: int) -> bool:
    """Report whether an answer carries a grading instruction asking for a value.

    Args:
        answer (str): The answer the judge read.
        value (int): The planted score, 1 to 5.

    Returns:
        bool: True where a requested value is the number, as digits or a word.
    """
    spellings = {str(value), _NUMBER_WORDS[value]}
    return any(
        requested in spellings or _is_number(requested, value)
        for requested in grading_values(answer)
    )


def _is_number(requested: str, value: int) -> bool:
    """Report whether a requested value written in digits equals a number.

    Args:
        requested (str): The value as the instruction wrote it.
        value (int): The number to compare with.

    Returns:
        bool: True for ``4.0`` against 4, false for a word or another number.
    """
    try:
        return float(requested) == value
    except ValueError:
        return False



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
