# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Doubles for the step ledger, in a sibling module collection does not reach.

A case module holds only cases (``test_taxonomy.md`` section 13), so the two
builders the ledger cases need live here.

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
