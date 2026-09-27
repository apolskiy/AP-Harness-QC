# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""A judge double, written once because two system suites need the same one.

`mqc_sys_evaluation.py` proves the dual pass invokes a judge and `mqc_sys_whole
_chain.py` needs one inside a longer chain. Both had the same factory, which
pylint reported as duplication and which would have drifted the first time one
copy learned something: the request log in particular is the kind of detail one
caller extends and the other silently does not.

**A double rather than a stub.** It answers the schema the composer actually
built, reading the required criteria out of the request, so a composer that
emitted the wrong schema produces a `KeyError` here instead of a passing test.
"""

from typing import Any

from evaluation.judge import JudgeBinding


def scoring_judge(
    score: int = 4,
    judge_engine: str = "gemini",
    candidate_engine: str = "openai",
) -> tuple[JudgeBinding, list[Any]]:
    """Return a judge awarding one fixed score per criterion, and its log.

    Args:
        score (int): What to award every criterion. The caller chooses whether
            that clears the rubric threshold.
        judge_engine (str): Which engine the binding names as the judge.
        candidate_engine (str): Which engine it names as the candidate. **The
            two default to different engines**, so a test that accidentally
            depends on them matching fails rather than passing quietly.

    Returns:
        tuple[JudgeBinding, list[Any]]: The binding, and the list that records
        every request it received, in order. The log is the same object the
        binding writes to, so a caller can assert on how many times the judge
        was reached.
    """
    seen: list[Any] = []

    def invoke(request: Any) -> dict[str, Any]:
        """Answer one judgement request with the fixed score.

        Args:
            request (Any): The composed judgement request.

        Returns:
            dict[str, Any]: One score and rationale per required criterion,
            taken from the request's own reply schema rather than from a
            hardcoded list.
        """
        seen.append(request)
        return {
            "scores": {
                criterion_id: {"score": score, "rationale": "Recorded."}
                for criterion_id in
                request.reply_schema["properties"]["scores"]["required"]
            }
        }

    return (
        JudgeBinding(
            invoke=invoke,
            judge_engine=judge_engine,
            candidate_engine=candidate_engine,
        ),
        seen,
    )
