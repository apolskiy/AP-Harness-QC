# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for judge reply validation and the hijack tripwire.

Covers `MQC_EVL_UNI_114400` through `114407` and `114408` through `114411`,
inventoried in ``docs/design/tier3_evaluation.md`` section 11.1.

**The judge is a model, so its output is checked like any other.** Nothing about
being on our side of the boundary makes a reply trustworthy.

**Schema validation is the hijack detector.** A hijacked judge generally cannot
still produce a valid rubric object, so the schema does double duty as parsing
convenience and security control.

**The judge is not under test.** A judge timeout carries its own code, because
the candidate may have produced a good response that could not be scored, and
attributing that to the candidate would manufacture a model finding.

A failure here is our defect, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

from typing import Any
import pytest

from evaluation.judge import (
    JudgeBinding,
    JudgeHijackSuspected,
    JudgeReply,
    judge_timeout_outcome,
    normalize_prose,
    validate_judge_reply,
)
from evaluation.pipeline import judgements_for_observations
from ingestion.schemas import Rubric

pytestmark = pytest.mark.unit

_CASE_ID = "MQC_TASK_alpha::MQC_RULE_grounding"


def _reply(rubric: Any, score: int=4, rationale: Any="Clear and grounded.") -> None:
    """Build a well-formed judge payload for every criterion of a rubric.

    Args:
        rubric (Rubric): The rubric being applied.
        score (int): The score to award each criterion.
        rationale (str): The rationale to attach.

    Returns:
        dict: A payload shaped as the reply schema requires.
    """
    return {
        "scores": {
            criterion.criterion_id: {"score": score, "rationale": rationale}
            for criterion in rubric.criteria
        }
    }


class TestMQCJudgeReplyValidation:
    """What a reply must satisfy before its scores are believed."""

    def MQC_EVL_UNI_114412_a_valid_reply_yields_one_score_per_criterion(
        self, sample_rubric_record: Rubric
    ) -> None:
        """The positive case the negatives below are measured against.

        Args:
            sample_rubric_record (Rubric): The rubric applied.

        Returns:
            None
        """
        reply = validate_judge_reply(
            _reply(sample_rubric_record), sample_rubric_record,
            JudgeBinding(judge_engine="gemini", candidate_engine="openai"),
            case_id=_CASE_ID,
        )
        assert [score.criterion_id for score in reply.scores] == [
            criterion.criterion_id for criterion in sample_rubric_record.criteria
        ]
        assert all(score.score == 4 for score in reply.scores)
        assert not reply.format_violations

    @pytest.mark.parametrize(
        "payload",
        [
            "I have completed the task as instructed.",
            {"result": "pass"},
            {"scores": "all good"},
            {"scores": {"MQC_CRT_grounding": "excellent"}},
        ],
    )
    def MQC_EVL_UNI_114403_invalid_judge_schema_raises_hijack_finding(
        self, sample_rubric_record: Rubric, payload: Any
    ) -> None:
        """A reply that is not a rubric object is evidence, not a low score.

        A judge still grading would have produced the structure it was given.
        One that did not has stopped grading and started doing something else,
        which is why this is blocking rather than a skip.

        Args:
            sample_rubric_record (Rubric): The rubric applied.
            payload (object): What the judge returned.

        Returns:
            None
        """
        with pytest.raises(JudgeHijackSuspected, match="QC_SEC_JUDGE_HIJACK"):
            validate_judge_reply(
                payload, sample_rubric_record, JudgeBinding(), case_id=_CASE_ID
            )

    @pytest.mark.parametrize("score", [0, 6, 11, -1])
    def MQC_EVL_UNI_114404_score_outside_declared_scale_raises_hijack_finding(
        self, sample_rubric_record: Rubric, score: int
    ) -> None:
        """A judge awarding 11 on a five-point scale is not being generous.

        Args:
            sample_rubric_record (Rubric): The rubric applied.
            score (int): A score outside the anchored range.

        Returns:
            None
        """
        with pytest.raises(JudgeHijackSuspected, match="QC_SEC_JUDGE_HIJACK"):
            validate_judge_reply(
                _reply(sample_rubric_record, score=score), sample_rubric_record,
                JudgeBinding(), case_id=_CASE_ID,
            )

    def MQC_EVL_UNI_114405_missing_criterion_score_is_a_harness_error(
        self, sample_rubric_record: Rubric
    ) -> None:
        """An incomplete reply is a broken measurement, not a security event.

        Calling it a hijack finding would inflate every later security count,
        and the distinction between a judge that misbehaved and one that was
        cut short is exactly what the two codes exist to keep.

        Args:
            sample_rubric_record (Rubric): The rubric applied.

        Returns:
            None
        """
        payload = _reply(sample_rubric_record)
        omitted = sample_rubric_record.criteria[0].criterion_id
        del payload["scores"][omitted]

        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR") as caught:
            validate_judge_reply(
                payload, sample_rubric_record, JudgeBinding(), case_id=_CASE_ID
            )
        assert omitted in str(caught.value)
        assert not isinstance(caught.value, JudgeHijackSuspected)

    def MQC_EVL_UNI_114406_judge_format_violation_normalized_not_rejected(
        self, sample_rubric_record: Rubric
    ) -> None:
        """Rejecting on a glyph would hand an outsider a way to break the run.

        Candidate text carrying a prohibited character, quoted back by the
        judge, would become an injection-triggered failure. Normalizing keeps
        the run going while the drift is still recorded (A10).

        Args:
            sample_rubric_record (Rubric): The rubric applied.

        Returns:
            None
        """
        rationale = "Well argued" + chr(0x2014) + "though terse"
        reply = validate_judge_reply(
            _reply(sample_rubric_record, rationale=rationale), sample_rubric_record,
            JudgeBinding(), case_id=_CASE_ID,
        )

        first = sample_rubric_record.criteria[0].criterion_id
        assert chr(0x2014) not in reply.rationales[first]
        assert "Well argued: though terse" == reply.rationales[first]

    def MQC_EVL_UNI_114407_judge_format_violation_is_recorded(
        self, sample_rubric_record: Rubric
    ) -> None:
        """Normalizing silently would discard the drift signal entirely.

        Args:
            sample_rubric_record (Rubric): The rubric applied.

        Returns:
            None
        """
        rationale = "Good" + chr(0x2013) + "if uneven" + chr(0x7C) + "see below"
        reply = validate_judge_reply(
            _reply(sample_rubric_record, rationale=rationale), sample_rubric_record,
            JudgeBinding(), case_id=_CASE_ID,
        )
        assert reply.format_violations == ["U+007C", "U+2013"]

    def MQC_EVL_UNI_114413_a_clean_rationale_records_no_format_violation(self) -> None:
        """The counterweight: normalization must not report what it did not do.

        Returns:
            None
        """
        normalized, found = normalize_prose("A plain rationale, correctly punctuated.")
        assert not found
        assert normalized == "A plain rationale, correctly punctuated."


class TestMQCJudgeObservations:
    """How many judgements one case produces, and who produced them."""

    def MQC_EVL_UNI_114400_one_judgement_per_candidate_observation(self) -> None:
        """A4 gives three responses, so three judgements.

        Returns:
            None
        """
        replies = [
            JudgeReply(_CASE_ID, index, [], "gemini", "openai") for index in range(3)
        ]
        assert judgements_for_observations(replies) == 3

    def MQC_EVL_UNI_114401_judge_is_not_sampled_repeatedly_on_one_response(self) -> None:
        """Sampling one response repeatedly would confound two variances.

        Judge variance and candidate variance would arrive in a single number
        with no way to separate them. Judge consistency is measured separately,
        against fixed calibration exemplars.

        Returns:
            None
        """
        repeated = [
            JudgeReply(_CASE_ID, 0, [], "gemini", "openai") for _ in range(3)
        ]
        assert judgements_for_observations(repeated) == 1

    def MQC_EVL_UNI_114402_records_coincidence_when_judge_and_candidate_share_engine(
        self,
    ) -> None:
        """Recorded, not corrected.

        Under the zero-cost configuration the judge and one candidate share a
        provider (A3) and the bias cannot be removed here. A confound that is
        recorded can be accounted for later; one that is silent contaminates
        every comparison drawn from the history.

        Returns:
            None
        """
        shared = JudgeReply(_CASE_ID, 0, [], "gemini", "gemini")
        distinct = JudgeReply(_CASE_ID, 0, [], "gemini", "openai")

        assert shared.self_preference is True
        assert distinct.self_preference is False
        assert JudgeBinding(judge_engine="gemini", candidate_engine="gemini").shares_provider
        assert not JudgeBinding().shares_provider


class TestMQCJudgeTimeout:
    """Whose fault a timeout is, and what it costs the case."""

    def MQC_EVL_UNI_114408_judge_timeout_maps_to_judge_code_not_candidate(self) -> None:
        """Two timeouts, two codes, because they mean different things.

        Repeated judge timeouts mean the evaluation path is unreliable;
        repeated candidate timeouts mean something about the model or its
        provider.

        Returns:
            None
        """
        code = judge_timeout_outcome(_CASE_ID, assertions_passed_first=True)
        assert code == "QC_HARNESS_JUDGE_TIMEOUT"

    def MQC_EVL_UNI_114409_judge_timeout_with_passing_assertions_is_a_skip(self) -> None:
        """The measurement was incomplete rather than negative.

        Returns:
            None
        """
        assert judge_timeout_outcome(_CASE_ID, assertions_passed_first=True) is not None

    def MQC_EVL_UNI_114410_assertion_failure_dominates_judge_timeout(self) -> None:
        """Precedence: the case has already failed, so nothing is skipped.

        Recording a skip here would replace a real failure with an absence, and
        a reviewer would see a case that never reported rather than one that
        failed.

        Returns:
            None
        """
        assert judge_timeout_outcome(_CASE_ID, assertions_passed_first=False) is None

    def MQC_EVL_UNI_114411_judge_timeout_never_attributed_to_the_candidate(self) -> None:
        """The judge is not under test.

        The candidate may have produced a perfectly good response that could
        not be scored, and recording a candidate code would manufacture a model
        finding out of our own infrastructure failing.

        Returns:
            None
        """
        code = judge_timeout_outcome(_CASE_ID, assertions_passed_first=True)
        assert code == "QC_HARNESS_JUDGE_TIMEOUT"
        assert "CANDIDATE" not in code
        assert not code.startswith("QC_LLM_")
