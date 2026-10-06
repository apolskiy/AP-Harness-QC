# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Reading prose a model formatted, without reading the formatting.

Specified by ``docs/design/tier3_evaluation.md`` section 5.1.

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
        str: The same text without code fences, backticks or bold markers.
        **Lengths change**, so a check that counts anything should read the raw
        text instead.
    """
    for marker in MARKUP_MARKERS:
        text = text.replace(marker, "")
    return text
