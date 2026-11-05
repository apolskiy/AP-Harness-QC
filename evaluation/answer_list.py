# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The list check, which decides whether an answer gave the list its prompt asked for.

Created: 2026-11-04
Last updated: 2026-11-05

This file contains :func:`check_answer_list`, which reports whether an answer
holds the numbered or bulleted list a rule declares, as an assertion result
named ``ANSWER_LIST``; :func:`asks_for_clarification`, which reports whether an
answer asks a question outside that list; and :func:`answer_route`, which
combines the two into the route the answer takes: ``list``, ``clarification``
or ``neither``, or nothing where the rule declares no list.

**The route is settled before the judge runs.** The pipeline calls
:func:`answer_route` after the screen and before the assertions: on the list
route every assertion runs and the rule's rubric judges, on the clarification
route only the fatal assertions run and the declared clarification rubric
judges, and on neither the list check fails the answer whatever the judge
returns.

**A numbered list holds where its top-level numbers run 1 to N once each, in
ascending order**; a missing, repeated or extra item is a length violation and
every number present out of order a format violation. A bulleted list holds at
its declared count or within its ceiling. Top level means at the margin, the
opener ``assertions.ITEM_OPENER`` reads for a number, so a sub-list is never
counted. **A request for clarification is a line outside the list ending a
sentence with a question mark**, never a line opening an item, a heading, a
line wholly in emphasis or a line inside a fenced block.

Specified by ``docs/design/tier3_evaluation.md`` section 5.5.
"""

import logging
import re
from typing import Any, Final, Optional

from cmn.markup import normalise_markup
from evaluation.assertions import ITEM_OPENER, AssertionResult

logger = logging.getLogger(__name__)

LIST_ROUTE: Final[str] = "list"
CLARIFICATION_ROUTE: Final[str] = "clarification"
NEITHER_ROUTE: Final[str] = "neither"

_LENGTH: Final[str] = "QC_LLM_LENGTH_VIOLATION"
_FORMAT: Final[str] = "QC_LLM_FORMAT_VIOLATION"

# A BULLET OPENS AT THE MARGIN: a hyphen, an asterisk, a plus sign or a bullet
# character, then a space. Bold text opens with two asterisks and no space, so
# it is not a bullet; an indented bullet is a sub-list.
_BULLET: Final[re.Pattern[str]] = re.compile(r"^[-*+•][ \t]+", re.MULTILINE)

# A FENCED BLOCK OPENS AND CLOSES ON A LINE STARTING WITH THREE BACKTICKS OR
# TILDES, indented or not, since a fence inside an item is indented with it.
_FENCE: Final[re.Pattern[str]] = re.compile(r"^\s*(```|~~~)")

# A LINE WHOLLY IN EMPHASIS, which is a heading in all but its marks: the model
# asking itself a question it then answers.
_EMPHASIS_LINE: Final[re.Pattern[str]] = re.compile(r"(\*\*|__|\*|_)(.+?)\1[:.]?")

# A QUESTION MARK ENDING A SENTENCE, so a question mark inside a word or a
# pattern is not one.
_QUESTION: Final[re.Pattern[str]] = re.compile(r"\?(?=\s|$)")


def _opener(declaration: Any) -> re.Pattern[str]:
    """Return the pattern opening a top-level item of the declared style.

    Args:
        declaration (Any): The rule's ``answer_list``.

    Returns:
        re.Pattern: ``ITEM_OPENER`` for a numbered list, the bullet otherwise.
    """
    return ITEM_OPENER if declaration.style == "numbered" else _BULLET


def _result(passed: bool, detail: str, code: Optional[str]) -> AssertionResult:
    """Return the list check's result, logging a failure.

    Args:
        passed (bool): Whether the list held.
        detail (str): What was found.
        code (Optional[str]): The taxonomy code on failure.

    Returns:
        AssertionResult: Named ``ANSWER_LIST``, of kind ``answer_list``.
    """
    if not passed:
        logger.info("%s ANSWER_LIST failed: %s", code, detail)
    return AssertionResult(
        assertion_id="ANSWER_LIST", kind="answer_list", passed=passed,
        severity="violation", detail=detail, taxonomy_code=None if passed else code,
    )


def _numbered(text: str, count: int) -> AssertionResult:
    """Check that the top-level numbers run 1 to ``count`` once each, in order.

    Args:
        text (str): The candidate output.
        count (int): The number of items asked for.

    Returns:
        AssertionResult: The list check's result.
    """
    numbers = [int(match.group(1)) for match in ITEM_OPENER.finditer(text)]
    if not numbers:
        return _result(
            False, f"the answer holds no numbered list; {count} items were asked for", _LENGTH
        )
    expected = range(1, count + 1)
    found = {
        "missing": [number for number in expected if number not in numbers],
        "repeated": sorted({number for number in numbers if numbers.count(number) > 1}),
        "extra": sorted({number for number in numbers if number not in expected}),
    }
    wrong = "; ".join(f"{name} {values}" for name, values in found.items() if values)
    if wrong:
        return _result(
            False, f"numbered items {numbers} against 1 to {count}: {wrong}", _LENGTH
        )
    if numbers != sorted(numbers):
        return _result(
            False,
            f"numbered items 1 to {count} present once each, in the order {numbers}",
            _FORMAT,
        )
    return _result(True, f"numbered items 1 to {count} present once each, in order", None)


def _bulleted(text: str, declaration: Any) -> AssertionResult:
    """Check the top-level bullet count against the declared count or ceiling.

    Args:
        text (str): The candidate output.
        declaration (Any): The rule's ``answer_list``.

    Returns:
        AssertionResult: The list check's result.
    """
    found = len(_BULLET.findall(text))
    if declaration.count is not None:
        bound, held = f"exactly {declaration.count}", found == declaration.count
    else:
        bound, held = f"at most {declaration.max_count}", found <= declaration.max_count
    if not found:
        return _result(False, f"the answer holds no bulleted list; {bound} were asked for", _LENGTH)
    return _result(
        held, f"{found} top-level bullets against {bound}", None if held else _LENGTH
    )


def check_answer_list(text: str, declaration: Any) -> AssertionResult:
    """Report whether an answer holds the list its rule declares.

    Design: ``tier3_evaluation.md`` section 5.5.

    Args:
        text (str): The candidate output.
        declaration (Any): The rule's ``answer_list``, carrying ``style``,
            ``count`` and ``max_count``.

    Returns:
        AssertionResult: Named ``ANSWER_LIST``. On failure it carries
        ``QC_LLM_LENGTH_VIOLATION`` for a missing, repeated or extra item or a
        bullet count outside the bound, and ``QC_LLM_FORMAT_VIOLATION`` for
        every number present out of order, its detail naming what was found.
    """
    if declaration.style == "numbered":
        return _numbered(text, int(declaration.count))
    return _bulleted(text, declaration)


def _outside_the_list(lines: list[str], fenced: list[bool], opener: re.Pattern[str]) -> list[int]:
    """Return the indices of the lines before the list's first item or after its last.

    The last item ends at the first blank line followed by a margin line that
    opens nothing. That end decides this question only; section 5.4's item
    still runs to the end of the answer.

    Args:
        lines (list): The answer's lines.
        fenced (list): Whether each line is inside, or opens or closes, a fence.
        opener (re.Pattern): What opens a top-level item.

    Returns:
        list: The line indices outside the list, every index where there is none.
    """
    openers = [
        index for index, line in enumerate(lines)
        if not fenced[index] and opener.match(line)
    ]
    if not openers:
        return list(range(len(lines)))
    end = next(
        (
            index for index in range(openers[-1] + 1, len(lines))
            if not lines[index - 1].strip() and lines[index].strip()
            and not lines[index][0].isspace() and not opener.match(lines[index])
        ),
        len(lines),
    )
    return list(range(openers[0])) + list(range(end, len(lines)))


def _fences(lines: list[str]) -> list[bool]:
    """Return whether each line is inside a fenced block or is one of its marks.

    Args:
        lines (list): The answer's lines.

    Returns:
        list: One flag per line.
    """
    inside = False
    flags: list[bool] = []
    for line in lines:
        mark = bool(_FENCE.match(line))
        flags.append(inside or mark)
        if mark:
            inside = not inside
    return flags


def _asks(line: str) -> bool:
    """Report whether one line outside the list asks the reader a question.

    Args:
        line (str): The line.

    Returns:
        bool: True for a sentence ending in a question mark, False for a
        heading or a line wholly in emphasis, which is the model's own
        structure.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or _EMPHASIS_LINE.fullmatch(stripped):
        return False
    return bool(_QUESTION.search(normalise_markup(stripped)))


def asks_for_clarification(text: str, declaration: Any) -> bool:
    """Report whether an answer asks a question outside its list.

    Design: ``tier3_evaluation.md`` section 5.5.

    Args:
        text (str): The candidate output.
        declaration (Any): The rule's ``answer_list``.

    Returns:
        bool: True where a line outside the list, outside any fence, ends a
        sentence with a question mark and is neither a heading nor wholly in
        emphasis. A question on a line opening an item is part of the list.
    """
    lines = text.splitlines()
    fenced = _fences(lines)
    return any(
        not fenced[index] and _asks(lines[index])
        for index in _outside_the_list(lines, fenced, _opener(declaration))
    )


def answer_route(rules: Any, text: str) -> str:
    """Return the route an answer takes under its rule's list declaration.

    Design: ``tier3_evaluation.md`` section 5.5.

    Args:
        rules (Any): The evaluation-relevant subset of the rule set.
        text (str): The candidate output.

    Returns:
        str: Empty where the rule declares no list; ``list`` where the answer
        holds it; ``clarification`` where it does not and asks a question
        outside it; ``neither`` otherwise.
    """
    declaration = getattr(rules, "answer_list", None)
    if declaration is None:
        return ""
    if check_answer_list(text, declaration).passed:
        return LIST_ROUTE
    if asks_for_clarification(text, declaration):
        return CLARIFICATION_ROUTE
    return NEITHER_ROUTE
