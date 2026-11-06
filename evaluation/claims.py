# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The ``claim`` assertion kind, which reads a response one sentence at a time.

Created: 2026-11-06
Last updated: 2026-11-06

This file contains ``check_claim``, which reports whether any sentence of a
response asserts a pattern, a sentence carrying an ``unless`` hedge not
asserting it, and ``claim_correction``, which finds a sentence correcting a
forbidden claim after the last sentence asserting it.

``evaluation.assertions`` registers ``check_claim`` as the ``claim`` kind and
calls ``claim_correction`` on a forbidding claim that failed, so a response that
corrected itself later passes with a warning rather than failing. Both run
before any judge.

Specified by ``docs/design/tier3_evaluation.md`` sections 5.3 to 5.3.2.
"""

import logging
import re
from typing import Any, Final, Optional

from cmn.markup import blank_punctuation

logger = logging.getLogger(__name__)

# WHAT ENDS A SENTENCE. A claim is scoped to one, because that is the unit
# negation and hedging operate over. The pattern keeps the terminator out of
# the split so an abbreviation inside a sentence does not end it: a following
# space or line break is required. Design section 5.3.
#
# A SINGLE LINE BREAK ENDS ONE, since 2026-10-12. It required a blank line
# before, so a markdown heading joined the sentence below it: "What the
# function returns" carried a return verb and the next line carried the
# prompt's own figures, and the assertion reported a correct answer as a
# hallucination for the third time. A heading, a list item and a table row
# have no full stop (design section 5.3.1).
_SENTENCE_BREAK: Final[re.Pattern[str]] = re.compile(
    r"(?<=[.!?;])\s+|\n+"
)


def check_claim(text: str, parameters: dict[str, Any]) -> tuple[bool, str]:
    """Check whether any sentence asserts a pattern.

    A sentence asserts the pattern when the pattern matches within it and no
    ``unless`` marker appears in that same sentence. With ``present`` false the
    check holds when no sentence asserts it.

    Args:
        text (str): The candidate output.
        parameters (dict): ``pattern``, optional ``present`` defaulting to
            true, and ``unless``, a list of case-insensitive substrings whose
            presence in a sentence means that sentence does not assert the
            claim. ``unless`` is required when ``present`` is false. Optional
            ``corrected_by``, read by :func:`claim_correction`, is allowed
            only when ``present`` is false.

    Returns:
        tuple: Whether the check held, and which sentence carried the claim.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when ``present`` is false
            and no ``unless`` is declared, or when ``present`` is true and
            ``unless`` or ``corrected_by`` is. Either way the assertion means
            something other than what it says, and a configuration error is
            ours rather than the model's.
    """
    pattern = re.compile(str(parameters["pattern"]), re.MULTILINE)
    expected = bool(parameters.get("present", True))
    markers = [str(marker).lower() for marker in parameters.get("unless") or ()]

    if expected and parameters.get("corrected_by"):
        raise ValueError(
            "QC_HARNESS_PARSER_ERROR: a claim with present true declares "
            "'corrected_by', and a correction of a statement the rule requires "
            "has no meaning. Declare it on a claim with present false"
        )
    if not expected and not markers:
        raise ValueError(
            "QC_HARNESS_PARSER_ERROR: a claim with present false and no "
            "'unless' is a regex with present false, and the same rule "
            "written two ways drifts. Declare the hedges this case has seen, "
            "or use kind 'regex'"
        )
    if expected and markers:
        raise ValueError(
            "QC_HARNESS_PARSER_ERROR: a claim with present true declares "
            "'unless', and what that would mean has never been decided. Use "
            "kind 'regex' to ask whether a pattern appears at all"
        )

    # SPLIT ON THE RAW TEXT, MATCH ON A BLANKED READING OF EACH SENTENCE. A
    # terminator delimits rather than decides, so the sentences are the raw
    # ones; punctuation inside a sentence is formatting, so neither the pattern
    # nor a hedge is decided by it. **The sentence reported is the raw one**,
    # because a ticket quoting a blanked sentence would misquote the model
    # (design section 5.1.1).
    markers = [blank_punctuation(marker) for marker in markers]
    asserted = next(
        (sentence.strip() for sentence in _SENTENCE_BREAK.split(text)
         if _asserts(sentence, pattern, markers)),
        None,
    )

    found = asserted is not None
    if found:
        # THE SENTENCE, NOT ONLY THAT ONE EXISTED. A reader deciding whether to
        # file this has to see what was actually asserted.
        detail = f"asserted in {_excerpt(asserted)}"
    else:
        detail = "not asserted in any sentence"
    return found == expected, detail


def _asserts(sentence: str, pattern: re.Pattern[str], markers: list[str]) -> bool:
    """Report whether one sentence asserts a claim's pattern.

    Args:
        sentence (str): The raw sentence.
        pattern (re.Pattern): The claim's pattern.
        markers (list[str]): The ``unless`` hedges, already blanked.

    Returns:
        bool: True where the pattern matches the sentence's blanked reading
        and no hedge appears in it.
    """
    reading = blank_punctuation(sentence)
    if not pattern.search(reading):
        return False
    return not any(marker in reading.lower() for marker in markers)


def claim_correction(text: str, parameters: dict[str, Any]) -> Optional[str]:
    """Return the sentence correcting a forbidden claim, where one follows it.

    Design: ``tier3_evaluation.md`` section 5.3.2.

    Args:
        text (str): The candidate output, as the claim read it.
        parameters (dict): The claim's parameters, carrying ``corrected_by``.

    Returns:
        Optional[str]: The first sentence matching ``corrected_by`` after the
        **last** asserting sentence, quoted for a detail. None where nothing
        asserts the claim, no ``corrected_by`` is declared, or no correction
        follows the last assertion, a correction before it being taken back.
    """
    corrector = parameters.get("corrected_by")
    if not corrector:
        return None
    pattern = re.compile(str(parameters["pattern"]), re.MULTILINE)
    correction = re.compile(str(corrector), re.MULTILINE)
    markers = [
        blank_punctuation(str(marker).lower()) for marker in parameters.get("unless") or ()
    ]
    sentences = _SENTENCE_BREAK.split(text)
    last = max(
        (index for index, sentence in enumerate(sentences)
         if _asserts(sentence, pattern, markers)),
        default=None,
    )
    if last is None:
        return None
    return next(
        (_excerpt(sentence.strip()) for sentence in sentences[last + 1:]
         if correction.search(blank_punctuation(sentence))),
        None,
    )


def _excerpt(sentence: str, limit: int = 160) -> str:
    """Return a sentence short enough to read in a failure message.

    Args:
        sentence (str): The sentence to quote.
        limit (int): How many characters to keep.

    Returns:
        str: The quoted sentence, elided when long.
    """
    collapsed = " ".join(sentence.split())
    if len(collapsed) <= limit:
        return repr(collapsed)
    return repr(f"{collapsed[:limit]}...")
