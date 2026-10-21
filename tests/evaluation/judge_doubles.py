# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Stand-in judges for the cases that need a judge without calling a provider.

Created: 2026-09-26
Last updated: 2026-10-21

This file contains two factories returning a ``JudgeBinding`` from
:mod:`evaluation.judge`. :func:`scoring_judge` awards one fixed score to every
criterion and returns the log of requests it received; :func:`refusing_judge`
raises the exception it was built with instead of judging.

``mqc_sys_evaluation.py`` uses the scoring judge to prove the dual pass invokes
a judge, ``mqc_sys_whole_chain.py`` needs one inside a longer chain, and
``mqc_uni_judgement_gaps.py`` uses the refusing judge to stand in for a missing
or stale recording. One factory serves them all, since copies would drift the
first time one learned something, the request log being the kind of detail one
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


def refusing_judge(error: Exception) -> JudgeBinding:
    """Return a binding whose invoke raises instead of judging.

    **The replay store is not reached in a unit test**, so what it would have
    raised is injected at the boundary the pipeline actually calls. Used by
    `MQC_EVL_UNI_114115` to pin that a judgement gap is a skip.

    Args:
        error (Exception): What ``invoke`` raises, normally
            ``FixtureMissing`` or ``FixtureStale``.

    Returns:
        JudgeBinding: A binding that raises on invocation.
    """

    def _raise(request: Any) -> Any:
        """Raise the held exception.

        Args:
            request (Any): The composed judge request, unused.

        Returns:
            Any: Never returns.

        Raises:
            Exception: Whatever this double was built with.
        """
        raise error

    return JudgeBinding(
        invoke=_raise, judge_engine="gemini", candidate_engine="claude",
    )
