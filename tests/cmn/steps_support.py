# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Test doubles of dispatch outcomes and evaluation results, for the step ledger cases.

Created: 2026-10-07
Last updated: 2026-10-21

This file provides ``dispatched`` and ``evaluated``, a successful dispatch and a
passing evaluation with fields overridden, ``failed_check`` and ``unmeasured``
for an evaluation whose assertion failed or whose judgement was never recorded,
``mixed_observations`` for five observations with the second failing, and
``Announced``, an item carrying only a node identifier.

They serve ``mqc_uni_steps.py``. A case module holds only cases
(``harness_test_taxonomy.md`` section 13), so the builders live in this sibling
module, which collection does not reach.

**Both start from a success and take overrides.** A ledger case is about one
step going wrong, and spelling out thirteen healthy fields to say so buries the
one that matters.
"""

from types import SimpleNamespace
from typing import Any


def dispatched(**overrides: Any) -> SimpleNamespace:
    """Return a dispatch outcome that succeeded, with fields overridden.

    Args:
        **overrides (Any): Fields to replace.

    Returns:
        SimpleNamespace: The outcome.
    """
    fields: dict[str, Any] = {
        "taxonomy_code": "",
        "request": {"model": "x", "messages": []},
        "mode": "replay",
        "attempts": 1,
        "response": SimpleNamespace(finish_reason="stop", text="an answer"),
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def evaluated(**overrides: Any) -> SimpleNamespace:
    """Return an evaluation result that passed, with fields overridden.

    Args:
        **overrides (Any): Fields to replace.

    Returns:
        SimpleNamespace: The result.
    """
    fields: dict[str, Any] = {
        "screen": SimpleNamespace(taxonomy_code=None),
        "rubric_authored": True,
        "assertion_results": [
            SimpleNamespace(
                passed=True, assertion_id="A_ALPHA", detail="", taxonomy_code=""
            )
        ],
        "score": SimpleNamespace(value=4.0, passed=True),
        "judge_skipped_reason": "",
        "taxonomy_codes": [],
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def failed_check() -> SimpleNamespace:
    """Return an evaluation result whose one assertion did not hold.

    Returns:
        SimpleNamespace: The result, unjudged because the assertion failed.
    """
    return evaluated(
        assertion_results=[
            SimpleNamespace(
                passed=False, assertion_id="A_ALPHA",
                detail="required substring absent",
                taxonomy_code="QC_LLM_SOURCE_ALTERATION",
            )
        ],
        score=None,
        judge_skipped_reason="assertions failed",
    )


def unmeasured() -> SimpleNamespace:
    """Return an evaluation result whose judgement was never recorded.

    Returns:
        SimpleNamespace: The result, carrying the fixture code.
    """
    return evaluated(
        score=None,
        judge_skipped_reason="judgement_unavailable",
        taxonomy_codes=["QC_HARNESS_FIXTURE_MISSING"],
    )


def mixed_observations() -> list[tuple[SimpleNamespace, SimpleNamespace]]:
    """Return five observations, the second failing.

    Returns:
        list: Dispatch outcome and evaluation result pairs.
    """
    return (
        [(dispatched(), evaluated()), (dispatched(), failed_check())]
        + [(dispatched(), evaluated())] * 3
    )


class Announced:
    """An item carrying only the identifier the announcement reads."""

    def __init__(self, nodeid: object) -> None:
        """Hold the identifier, or its absence.

        Args:
            nodeid (object): What pytest would carry, or None.

        Returns:
            None
        """
        if nodeid is not None:
            self.nodeid = nodeid
