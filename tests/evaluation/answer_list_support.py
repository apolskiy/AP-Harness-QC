# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Builders and readers the answer-list case modules share.

Created: 2026-11-04
Last updated: 2026-11-05

This file contains :func:`list_declaration`, an answer-list declaration
carrying only what the list check reads; :func:`declared_list_payload`, a rule
payload carrying a declaration; :func:`numbered_answer`, an answer whose items
carry given numbers in a given order; :func:`criteria_asked`, the criteria
each request a recording judge received asked to score; and
:func:`assertions_ran`, the identifiers of the assertions an evaluation ran.

``mqc_uni_answer_list.py``, ``mqc_uni_answer_route.py`` and
``tests/ingestion/mqc_uni_answer_list_schema.py`` build their inputs from these.
A case module holds only cases (``harness_test_taxonomy.md`` section 13), so
they live in this sibling module, which collection does not reach.
"""

from types import SimpleNamespace
from typing import Any, Optional


def list_declaration(style: str, count: Optional[int] = None,
                     max_count: Optional[int] = None) -> Any:
    """Return an answer-list declaration carrying only what the check reads.

    Args:
        style (str): ``numbered`` or ``bulleted``.
        count (Optional[int]): The exact number of items.
        max_count (Optional[int]): The ceiling.

    Returns:
        Any: The declaration.
    """
    return SimpleNamespace(style=style, count=count, max_count=max_count)


def declared_list_payload(payload: dict[str, Any], **answer_list: Any) -> dict[str, Any]:
    """Return the rule payload carrying an answer list, its rubric the sample one.

    Args:
        payload (dict): Minimal rule payload, carrying a rubric.
        **answer_list (Any): The declaration's fields, ``clarification_rubric``
            defaulting to the payload's own rubric.

    Returns:
        dict: The payload with ``answer_list`` set.
    """
    answer_list.setdefault("clarification_rubric", payload["rubric"])
    return {**payload, "answer_list": answer_list}


def numbered_answer(*numbers: int) -> str:
    """Return an answer whose top-level items carry these numbers, in this order.

    Args:
        *numbers (int): The item numbers, as written.

    Returns:
        str: One line per item.
    """
    return "".join(f"{number}. The answer for item {number}.\n" for number in numbers)


def criteria_asked(judge: Any) -> list[list[str]]:
    """Return the criteria each request a recording judge received asked to score.

    Args:
        judge (Any): A ``RecordingJudge``.

    Returns:
        list: One list of criterion identifiers per request.
    """
    return [
        list(request.reply_schema["properties"]["scores"]["required"])
        for request in judge.requests
    ]


def assertions_ran(result: Any) -> list[str]:
    """Return the identifiers of the assertions an evaluation ran.

    Args:
        result (Any): The evaluation result.

    Returns:
        list: The assertion identifiers, in the order they ran.
    """
    return [entry.assertion_id for entry in result.assertion_results]
