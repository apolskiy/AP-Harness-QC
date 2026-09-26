# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Judge reply validation, and the tripwire the schema doubles as.

Specified by ``docs/design/tier3_evaluation.md`` sections 6 and 7.

**The judge is a model, so its output is checked like any other.** Nothing about
being on our side of the boundary makes a reply trustworthy.

**Schema validation is the hijack detector.** A hijacked judge generally cannot
still produce a valid rubric object, so the schema does double duty as parsing
convenience and security control. That is why structured output is mandatory for
the judge (C2) and deliberately not for the candidate, where schema-following
stays measurable as a model quality.

**Format violations are normalized, never rejected.** Rejecting a reply for
containing a prohibited glyph would hand an external party a way to break the
harness: candidate text carrying the character, quoted back by the judge,
becomes an injection-triggered failure. A judge ignoring its formatting
instruction is recorded as drift while the run continues (A10).

**The judge is not under test.** A judge timeout carries its own code, because
the candidate may have produced a good response that could not be scored.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Final, Optional

from evaluation.aggregation import CriterionScore

logger = logging.getLogger(__name__)

_HIJACK_CODE: Final[str] = "QC_SEC_JUDGE_HIJACK"
_PARSER_CODE: Final[str] = "QC_HARNESS_PARSER_ERROR"
_FORMAT_CODE: Final[str] = "QC_LLM_FORMAT_VIOLATION"

# Glyphs the prose rules prohibit, with what each is replaced by. Normalizing
# rather than rejecting is the whole point, so every entry names a replacement.
_PROHIBITED_GLYPHS: Final[dict[str, str]] = {
    chr(0x2014): ": ",   # em dash
    chr(0x2013): "-",    # en dash
    chr(0x7C): ";",      # pipe, ambiguous with table syntax
}


class JudgeHijackSuspected(ValueError):
    """A judge reply failed validation in a manner consistent with hijack.

    **Blocking.** A reply that does not parse as a rubric object, or scores
    outside the declared scale, is not a low score; it is evidence that the
    judge stopped grading and started doing something else.
    """


@dataclass(frozen=True)
class JudgeBinding:
    """Who judges, and whose output they are judging.

    Fixed for a run rather than per observation. Holding both engine names
    adjacent is what makes the self-preference check in design section 6.4 a
    comparison rather than a lookup somewhere else.

    Attributes:
        invoke (Optional[Callable]): Called with the composed request. Absent
            means no judgement is available, which is recorded as such rather
            than treated as a zero score.
        judge_engine (str): Which engine grades.
        candidate_engine (str): Which engine produced the response.
    """

    invoke: Optional[Callable[[Any], Any]] = None
    judge_engine: str = ""
    candidate_engine: str = ""

    @property
    def available(self) -> bool:
        """Report whether a judgement can be obtained at all.

        Returns:
            bool: True when a judge is bound.
        """
        return self.invoke is not None

    @property
    def shares_provider(self) -> bool:
        """Report whether judge and candidate come from one provider.

        Returns:
            bool: True when the two engines match. Under the zero-cost
            configuration they often do (A3), and the coincidence is recorded
            rather than corrected.
        """
        return bool(self.judge_engine) and self.judge_engine == self.candidate_engine


@dataclass(frozen=True)
class JudgeReply:
    """One validated judge reply.

    Attributes:
        case_id (str): Which case was judged.
        observation_index (int): Which of the repeat observations (A4).
        scores (list): One score per criterion, in rubric order.
        judge_engine (str): Which engine graded it.
        candidate_engine (str): Which engine produced the response.
        format_violations (list): Glyphs normalized out of the prose fields,
            recorded as a drift signal rather than acted on.
        rationales (dict): Criterion identifier to the judge's reasoning,
            already normalized.
    """

    case_id: str
    observation_index: int
    scores: list[CriterionScore]
    judge_engine: str
    candidate_engine: str
    format_violations: list[str] = field(default_factory=list)
    rationales: dict[str, str] = field(default_factory=dict)

    @property
    def self_preference(self) -> bool:
        """Report whether the judge graded a response from its own provider.

        Returns:
            bool: True when judge and candidate share an engine. **Recorded,
            not corrected.** Under the zero-cost configuration the judge and one
            candidate share a provider (A3), and the bias cannot be removed
            here. A confound that is recorded can be accounted for later; one
            that is silent contaminates every comparison drawn from the history.
        """
        return self.judge_engine == self.candidate_engine


def normalize_prose(text: str) -> tuple[str, list[str]]:
    """Replace prohibited glyphs and report which were found.

    Args:
        text (str): A prose field from the judge reply.

    Returns:
        tuple: The normalized text, and the names of the glyphs replaced.
    """
    normalized = text
    found: list[str] = []
    for glyph, replacement in _PROHIBITED_GLYPHS.items():
        if glyph in normalized:
            found.append(f"U+{ord(glyph):04X}")
            normalized = normalized.replace(glyph, replacement)
    return normalized, found


def validate_judge_reply(
    payload: Any,
    rubric: Any,
    binding: JudgeBinding,
    *,
    case_id: str,
    observation_index: int = 0,
) -> JudgeReply:
    """Validate a judge reply and turn it into scores.

    Args:
        payload (Any): What the judge returned, expected to be a mapping.
        rubric (Any): The rubric applied, naming the criteria and the scale.
        binding (JudgeBinding): Who judged, and whose output.
        case_id (str): Which case was judged.
        observation_index (int): Which of the repeat observations (A4).

    Returns:
        JudgeReply: The validated reply.

    Raises:
        JudgeHijackSuspected: When the reply is not schema-valid, or a score
            lies outside the declared scale. Both are blocking.
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the reply is
            well-formed but omits a criterion. That is a skip rather than a
            hijack finding: an incomplete reply is a broken measurement, and
            calling it a security event would inflate every later count.
    """
    scores_by_id = _require_schema_valid(payload, case_id)
    _require_every_criterion(scores_by_id, rubric, case_id)
    scores, rationales, violations = _read_scores(scores_by_id, rubric, case_id)

    if violations:
        logger.warning(
            "%s %s judge prose carried %s, normalized and recorded",
            _FORMAT_CODE, case_id, ", ".join(sorted(set(violations))),
        )

    return JudgeReply(
        case_id=case_id,
        observation_index=observation_index,
        scores=scores,
        judge_engine=binding.judge_engine,
        candidate_engine=binding.candidate_engine,
        format_violations=sorted(set(violations)),
        rationales=rationales,
    )


def _require_every_criterion(scores_by_id: dict, rubric: Any, case_id: str) -> None:
    """Refuse a reply that scored fewer criteria than the rubric declares.

    Args:
        scores_by_id (dict): What the judge returned.
        rubric (Any): The rubric applied.
        case_id (str): Which case, for the message.

    Returns:
        None

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR``. A skip, not a hijack
            finding: an incomplete reply is a broken measurement, and recording
            it as a security event would inflate every later count.
    """
    missing = [
        criterion.criterion_id for criterion in rubric.criteria
        if criterion.criterion_id not in scores_by_id
    ]
    if missing:
        logger.error("%s %s judge omitted %s", _PARSER_CODE, case_id, ", ".join(missing))
        raise ValueError(
            f"{_PARSER_CODE}: the judge reply for {case_id} scored no value for "
            f"{', '.join(missing)}, so the measurement is incomplete"
        )


def _read_scores(
    scores_by_id: dict, rubric: Any, case_id: str
) -> tuple[list[CriterionScore], dict[str, str], list[str]]:
    """Turn a validated reply into scores, rationales and format findings.

    Args:
        scores_by_id (dict): What the judge returned.
        rubric (Any): The rubric applied.
        case_id (str): Which case, for the message.

    Returns:
        tuple: The scores in rubric order, the normalized rationales, and every
        prohibited glyph found.
    """
    scores: list[CriterionScore] = []
    rationales: dict[str, str] = {}
    violations: list[str] = []
    for criterion in rubric.criteria:
        entry = scores_by_id[criterion.criterion_id]
        scores.append(
            CriterionScore(
                criterion_id=criterion.criterion_id,
                score=_require_in_scale(entry, criterion, case_id),
                weight=float(criterion.weight),
            )
        )
        rationale, found = normalize_prose(str(entry.get("rationale", "")))
        rationales[criterion.criterion_id] = rationale
        violations.extend(found)
    return scores, rationales, violations


def _require_schema_valid(payload: Any, case_id: str) -> dict[str, Any]:
    """Return the scores mapping, refusing a reply that is not one.

    Args:
        payload (Any): What the judge returned.
        case_id (str): Which case, for the message.

    Returns:
        dict: Criterion identifier to its score entry.

    Raises:
        JudgeHijackSuspected: When the reply is not a rubric object at all.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("scores"), dict):
        logger.error("%s %s judge reply is not a rubric object", _HIJACK_CODE, case_id)
        raise JudgeHijackSuspected(
            f"{_HIJACK_CODE}: the judge reply for {case_id} is not a valid rubric "
            f"object, which a judge still grading would have produced"
        )

    entries = payload["scores"]
    for criterion_id, entry in entries.items():
        if not isinstance(entry, dict) or "score" not in entry:
            raise JudgeHijackSuspected(
                f"{_HIJACK_CODE}: the judge reply for {case_id} carried no score for "
                f"{criterion_id}, in a reply that is otherwise structured"
            )
    return entries


def _require_in_scale(entry: dict[str, Any], criterion: Any, case_id: str) -> float:
    """Return one score, refusing a value outside the declared scale.

    Args:
        entry (dict): The judge's entry for this criterion.
        criterion (Any): The criterion, whose anchors declare the scale.
        case_id (str): Which case, for the message.

    Returns:
        float: The score.

    Raises:
        JudgeHijackSuspected: When the score is not a number, or lies outside
            the anchored range. A judge awarding 11 on a five-point scale is not
            being generous; it has stopped applying the rubric.
    """
    lowest, highest = min(criterion.anchors), max(criterion.anchors)
    try:
        score = float(entry["score"])
    except (TypeError, ValueError) as error:
        raise JudgeHijackSuspected(
            f"{_HIJACK_CODE}: the judge scored {criterion.criterion_id} on {case_id} "
            f"as {entry.get('score')!r}, which is not a number"
        ) from error

    if not lowest <= score <= highest:
        logger.error(
            "%s %s scored %s outside the scale %d to %d",
            _HIJACK_CODE, case_id, score, lowest, highest,
        )
        raise JudgeHijackSuspected(
            f"{_HIJACK_CODE}: the judge scored {criterion.criterion_id} on {case_id} "
            f"as {score}, outside the declared scale of {lowest} to {highest}"
        )
    return score


def judge_timeout_outcome(case_id: str, *, assertions_passed_first: bool) -> Optional[str]:
    """Return the code a judge timeout records, given the assertion result.

    **Precedence: an assertion failure dominates a judge timeout.** If the
    assertions failed the case has already failed, and a timeout only produces a
    skip when the assertions passed and the measurement was therefore incomplete
    rather than negative.

    Args:
        case_id (str): Which case timed out.
        assertions_passed_first (bool): Whether the assertions had passed.

    Returns:
        Optional[str]: ``QC_HARNESS_JUDGE_TIMEOUT`` when the case is a skip, or
        ``None`` when the case has already failed on its assertions. **Never a
        candidate code**: the judge is not under test, and the candidate may
        have produced a good response that could not be scored.
    """
    if not assertions_passed_first:
        logger.info("%s judge timed out after assertions had already failed", case_id)
        return None
    logger.warning("QC_HARNESS_JUDGE_TIMEOUT %s judged nothing; recording a skip", case_id)
    return "QC_HARNESS_JUDGE_TIMEOUT"
