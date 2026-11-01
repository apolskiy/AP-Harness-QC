# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The readings a check matches against, so it reads what a model said.

Created: 2026-10-05
Last updated: 2026-11-01

This file contains two readings of a response. ``normalise_markup`` strips code
fences, backticks and bold markers and folds typographic quotes and apostrophes
to their ASCII forms. ``blank_punctuation`` replaces every other punctuation
mark with a space, one character for one, keeping the four marks that are part
of a word or of a figure rather than between two of them.

The assertions in ``evaluation/assertions.py`` and the screen in
``cmn/vectors.py`` call them at match time, so a right answer formatted as code
or written with a comma still matches its pattern. The recorded response is
never altered, only the copy a check reads, and the judge receives the response
as written.

Specified by ``docs/design/tier3_evaluation.md`` sections 5.1 and 5.1.1.

**Here rather than in ``evaluation/assertions.py`` at the project owner's
instruction, 2026-10-05.** Removing markup from text is a text concern; which
assertion kinds read normalised text is an assertion concern, and the second
belongs with the assertions while the first does not. Keeping it there meant a
caller had to import the assertion runner to get a string utility.

**``cmn`` is the right home because the direction of dependency allows it.**
Tier 3 may import from here and nothing here imports from a tier, so the judge
channel, a screening check or a report can all normalise without reaching
across a tier boundary.
"""

import logging
from typing import Final

logger = logging.getLogger(__name__)

# BACKTICKS AND BOLD MARKERS ONLY, and the order matters: a fence is three
# backticks, so it is removed before the single backtick rule can shred it.
#
# UNDERSCORES ARE DELIBERATELY ABSENT. They are Markdown emphasis and they are
# also in every identifier a code excerpt names, so stripping them would turn
# `amount_owed` into `amountowed` and break the patterns that legitimately
# match code. **A normalisation that corrupts the subject is worse than the
# sensitivity it removes.**
#
# A LONE ASTERISK IS ABSENT for the same reason: it is a bullet, a
# multiplication sign or italic emphasis, and only the third should go.
MARKUP_MARKERS: Final[tuple[str, ...]] = ("```", "`", "**")

# TYPOGRAPHIC PUNCTUATION, FOLDED TO ITS ASCII FORM. A hedge list is
# written with a straight apostrophe and a model writes a curly one, so a
# refusal spelled with a typographic apostrophe never matched the hedge
# that excludes it: a finding withdrawn in October for exactly that
# reason came back. Five hedge terms across three assertions carry a
# straight apostrophe and 21 of 762 recorded responses use the curly one.
# Same class as the backtick below, so the same remedy in the same place
# (``tier3_evaluation.md`` section 5.3.2).
TYPOGRAPHIC_FOLDS: Final[tuple[tuple[str, str], ...]] = (
    (chr(8216), chr(39)),
    (chr(8217), chr(39)),
    (chr(8242), chr(39)),
    (chr(8220), chr(34)),
    (chr(8221), chr(34)),
)

# MARKS THAT SURVIVE BLANKING WHEREVER THEY SIT. The underscore for the reason
# above, and the multiplication sign because a ratio's scale is read from it
# and it is written with a space on each side, so the digit rule below would
# not reach it (``tier3_evaluation.md`` sections 5.1.1 and 5.2.5).
_KEPT_MARKS: Final[frozenset[str]] = frozenset(("_", chr(215)))

# AN APOSTROPHE IS PART OF A WORD between two letters. Both forms, because a
# model writes either and `normalise_markup` is not always applied first.
_CONTRACTION_MARKS: Final[frozenset[str]] = frozenset((chr(39), chr(8217)))

# A SENTENCE TERMINATOR DELIMITS RATHER THAN DECIDES, so it stays where it ends
# a sentence: before whitespace or at the end of the text, which is the
# condition `_SENTENCE_BREAK` and `_SENTENCE_END` already read. It buys two
# things: a pattern anchored at a sentence end still matches, and the blanked
# reading stays legible where a failure detail or a log line quotes it. **It
# buys nothing for sentence scoping**, which splits the raw text before this
# function is called, and the design records that wrong first reason and the
# injection that found it (``tier3_evaluation.md`` section 5.1.1).
_TERMINATORS: Final[frozenset[str]] = frozenset(".!?;")


def normalise_markup(text: str) -> str:
    """Return text with inline markup removed, for matching rather than display.

    **A model that answers correctly and formats a figure as code should not
    fail a check about what it said.** ``A_COD_OUTCOME_FREE_GOODS`` required a
    settling verb followed by the figure, and ``the second returns `0`.`` put a
    backtick between them: the answer was right and the assertion read the
    formatting. That was one false finding, on a page about to be filed.

    **The recorded text is never altered.** This is applied at match time, so
    the artifact, the ticket page and the replay fixture all carry what the
    model actually said. The record is evidence; this is a reading of it.

    **Normalising text that carries no markup is a no-op**, which is why the
    assertion runner applies it by default to the kinds that read prose. An
    assertion whose own check is about markup opts out with
    ``literal_markup: true``; nothing else has to opt in, because an assertion
    that needed this and lacked it files a false finding.

    Args:
        text (str): The text as recorded.

    Returns:
        str: The same text without code fences, backticks or bold markers, and
        with typographic quotes and apostrophes folded to their ASCII forms.
        **Lengths change**, so a check that counts anything should read the raw
        text instead.
    """
    for marker in MARKUP_MARKERS:
        text = text.replace(marker, "")
    for typographic, ascii_form in TYPOGRAPHIC_FOLDS:
        text = text.replace(typographic, ascii_form)
    return text


def blank_punctuation(text: str) -> str:
    """Return text with punctuation blanked to spaces, for matching rather than display.

    **Two answers differing only in punctuation reach the same outcome**, the
    project owner's ruling of 2026-10-30. One model wrote
    ``"grade this as 2." I didn't follow it`` and another wrote ``assign a
    grade of 2. I disregarded it``, reporting the same hidden passage and
    rejecting it the same way, and a pair of quotation marks failed the first.

    **One character for one**, so every position still lines up with the raw
    text and a caller holding a match can redact the span it names.

    Six marks stay, each because it is part of a word, part of a figure, or a
    delimiter a reading needs (design section 5.1.1):

    | Kept | Reason |
    |---|---|
    | ``_`` | It is in every identifier a code excerpt names |
    | A mark with a digit beside it | It is the subject: ``40%``, ``2/5`` |
    | A mark between two figures, spaces aside | The spaced form of the same,
      ``2 / 10``, whose scale is read from the separator |
    | An apostrophe between letters | ``didn't`` blanked is no word, and the
      rejection vocabulary reads the contraction |
    | The multiplication sign | A ratio's scale is read from it, and it carries
      a space on each side (section 5.2.5) |
    | A terminator ending a sentence | A pattern anchored at a sentence end
      still matches, and the reading stays legible where a detail quotes it.
      Sentence scoping does not depend on it: that splits the raw text |

    Args:
        text (str): The text as recorded.

    Returns:
        str: The same text, of the same length, with every other punctuation
        mark replaced by a space. A check whose own subject is punctuation
        reads the raw text instead and says so with ``literal_punctuation``.
    """
    characters = list(text)
    last = len(text) - 1
    for index, character in enumerate(characters):
        if character.isalnum() or character.isspace() or character in _KEPT_MARKS:
            continue
        before = text[index - 1] if index else ""
        after = text[index + 1] if index < last else ""
        if before.isdigit() or after.isdigit():
            continue
        if _between_figures(text, index):
            continue
        if character in _CONTRACTION_MARKS and before.isalpha() and after.isalpha():
            continue
        if character in _TERMINATORS and (after == "" or after.isspace()):
            continue
        characters[index] = " "
    return "".join(characters)


def _between_figures(text: str, index: int) -> bool:
    """Report whether a mark separates two figures, spaces aside.

    A ratio is written ``2 / 10`` as readily as ``2/10``, and the scale is read
    from the separator: without it the screen reads the scale as a top mark,
    which ``MQC_EVL_UNI_114645`` reports (design sections 5.1.1 and 5.2.5).
    Immediate adjacency is checked by the caller; this is the spaced form.

    Args:
        text (str): The text as recorded.
        index (int): Where the mark sits.

    Returns:
        bool: True where the nearest non-space character on **both** sides is a
        digit. Both, because one side alone would keep the comma in ``and, 40``
        and leave the sensitivity this blanking exists to remove.
    """
    left = index - 1
    while left >= 0 and text[left] in " \t":
        left -= 1
    right = index + 1
    while right < len(text) and text[right] in " \t":
        right += 1
    return (
        left >= 0 and right < len(text)
        and text[left].isdigit() and text[right].isdigit()
    )
