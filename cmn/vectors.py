# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The injection vector registry, shared by every screen.

Specified by ``docs/design/tier1_ingestion.md`` section 7.2.

**One registry, two screens.** ``MQC_EVL_UNI_10349`` asserts that content the
ingest screen warned about is matched again by the Tier 3 screen. Two copies of
a pattern set cannot be asserted to agree; they can only be compared, and a
comparison passes on the day it is written and drifts afterwards. Sharing the
registry makes the agreement structural rather than tested.

Without that, A19's argument collapses. Warning rather than aborting at ingest
buys a measurement of the two screens meeting real accidental input, and that
measurement is worthless if the screens look for different things.

**This module owns what a hit is. It does not own what a hit means.** Each
screen decides which fields to examine, whether a hit warns or aborts, and which
taxonomy code it emits.

**Detection is programmatic and never a model call.** A model asked to detect
injection is itself injectable, which relocates the problem rather than solving
it. Being deterministic also makes every screen unit-testable.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Final, Pattern

logger = logging.getLogger(__name__)

# Characters that carry no visible glyph and can hide or reorder text. An
# interior byte order mark is included: utf-8-sig strips a leading one, so any
# that survives into a value arrived somewhere it has no business being.
_INVISIBLE_CODE_POINTS: Final[frozenset[int]] = frozenset(
    {0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF}       # zero width space, joiners, BOM
    | set(range(0x202A, 0x202F))                   # bidirectional embedding and override
    | set(range(0x2066, 0x206A))                   # bidirectional isolates
)

# Built from code points rather than written as literals. A source file holding
# a bidirectional override can display differently than it executes, which is
# the attack this module exists to detect, and pylint refuses it as E2502. The
# prose rule in code-style.md section 7 says the same thing about naming a
# prohibited character rather than reproducing it.
_INVISIBLE_CHARS: Final[frozenset[str]] = frozenset(
    chr(code_point) for code_point in _INVISIBLE_CODE_POINTS
)

# The name a hit on an invisible character reports. Kept beside the registry
# because a caller grouping findings by vector needs every vector name from one
# place, and this one is matched by membership rather than by a pattern.
INVISIBLE_VECTOR: Final[str] = "invisible_characters"

# A CHARACTER-LEVEL VECTOR, like the invisible one and for the same reason: a
# confusable letter is a fact about code points, and the visible text looks
# exactly like what it imitates, so no pattern over it can find anything.
HOMOGLYPH_VECTOR: Final[str] = "homoglyph_substitution"

# The scripts whose letters are routinely confused with Latin ones. A word
# mixing one of these with Latin is almost always an imitation, because no
# natural orthography mixes them inside a word.
_CONFUSABLE_SCRIPTS: Final[tuple[str, ...]] = ("CYRILLIC", "GREEK")

# A run of letters, which is the unit the mixed-script test applies to. Testing
# whole text instead would report any document containing both scripts, and a
# bilingual glossary is not an attack.
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

# One entry per vector named in the tier designs. A pattern is data, so adding a
# vector is a registry entry rather than a code change, per A12, and it now
# reaches both screens at once.
_VECTOR_PATTERNS: Final[dict[str, Pattern[str]]] = {
    "instruction_override": re.compile(
        r"\b(ignore|disregard|forget|override)\b[^.]{0,40}?"
        r"\b(previous|prior|above|earlier|all)\b[^.]{0,20}?"
        r"\b(instruction|instructions|prompt|rule|rules|context)\b",
        re.IGNORECASE,
    ),
    # SECOND PERSON AND FIRST. The original covered an attacker telling the
    # model what it is; an attacker claiming what THEY are asserts the same
    # authority from the other direction and was unscreened
    # (tier1_ingestion.md section 7.3.2).
    "role_assertion": re.compile(
        r"(^|\n)\s*(system|assistant|user)\s*:|"
        r"\byou\s+are\s+now\b|\bact\s+as\s+(the\s+)?(system|administrator|developer)\b|"
        r"\b(i\s+am|this\s+is)\s+(the\s+)?(platform\s+|system\s+)?"
        r"(administrator|admin|developer|operator|owner)\b|"
        r"\b(system|admin|administrator|operator)\s+override\b",
        re.IGNORECASE,
    ),
    "delimiter_escape": re.compile(
        r"<\|[a-z_]+\|>|\[/?INST\]|<\|?(im_start|im_end)\|?>|```\s*(system|assistant)\b",
        re.IGNORECASE,
    ),
    "score_manipulation": re.compile(
        r"\b(give|award|assign|rate|score)\b[^.]{0,30}?"
        r"\b(5|five|10|ten|full|maximum|top|perfect|highest)\b|"
        r"\bthis\s+(response|answer)\s+(is|deserves)\b[^.]{0,20}\bperfect\b",
        re.IGNORECASE,
    ),
    "prompt_extraction": re.compile(
        # INFLECTIONS INCLUDED. "recites" failed the word boundary after
        # "recite", which is the narrowness this widening was for.
        r"\b(repeat|reveal|print|show|output|disclos|recit|restat|quot)\w*\b"
        r"[^.]{0,30}?\b(your|the|its)\b[^.]{0,20}?"
        r"\b(instruction|instructions|system\s+prompt|prompt|configuration)\b",
        re.IGNORECASE,
    ),
    "encoding_obfuscation": re.compile(
        r"\b(base64|rot13|hex\s*decode|atob)\b|[A-Za-z0-9+/]{60,}={0,2}",
        re.IGNORECASE,
    ),
    # A DIFFERENT TASK, WITH NO OVERRIDE LANGUAGE. Screening for the words one
    # attack happened to use is not screening for the attack: `50004` passed
    # the cross-check on phrasing it did not need, and a payload that merely
    # names a replacement task matched nothing (section 7.3.1).
    "task_substitution": re.compile(
        r"\b(instead\s+of|rather\s+than)\b[^.]{0,40}?"
        r"\b(summaris|summariz|answer|respond|reply|translat)\w*\b|"
        r"\bthe\s+(actual|real|correct|true)\s+task\s+is\b|"
        r"\b(task|instruction)\s+has\s+been\s+(retired|replaced|superseded|updated)\b|"
        r"\bcorrection\s+to\s+your\s+(configuration|instruction|prompt)\b",
        re.IGNORECASE,
    ),
    # NAMING A TOOL AND AN IMPERATIVE, or an authority claim about one. `50008`
    # also passed on override phrasing rather than on this (section 7.3.1).
    "tool_coercion": re.compile(
        # AN IMPERATIVE ALONE IS NOT COERCION. "You may use lookup_order" is
        # what a legitimate system instruction says, and the first version of
        # this pattern fired on it: MQC_EVL_UNI_10399 caught that before it
        # reached the corpus. The imperative counts only alongside urgency,
        # and the other clauses carry the cases that need no tool name.
        r"\b(call|invoke|run|trigger|execute)\s+(the\s+)?[a-z]+_[a-z_]+\b"
        # A DECIMAL POINT IS NOT A SENTENCE END. The `[^.]` idiom this file
        # uses to stay inside one sentence breaks on "149.00", and an amount is
        # exactly what a refund directive carries. A period counts as a
        # boundary only when a digit does not follow it.
        r"(?:[^.]|\.(?=\d)){0,60}?"
        r"\b(immediately|right\s+now|before\s+replying|regardless|"
        r"without\s+asking|first)\b|"
        r"\b(must|should|shall|has\s+to)\s+be\s+(called|invoked|used)\b|"
        r"\bassistant\s+directive\b|"
        r"\boverrides?\s+any\s+(prohibition|restriction|rule|instruction)\b",
        re.IGNORECASE,
    ),
    "payload_splitting": re.compile(
        r"\b(concatenate|join|combine|append)\b[^.]{0,40}?\b(part|parts|piece|pieces|fragment)\b|"
        # DIGITS OR WORDS. "part one of two" is the same instruction and was
        # unscreened (section 7.3.2).
        r"\bpart\s+([0-9]|one|two|three|first|second)\s+of\s+([0-9]|one|two|three)\b",
        re.IGNORECASE,
    ),
}


@dataclass(frozen=True)
class VectorMatch:
    """One vector matching one piece of text.

    The shape a screen builds its own finding from. It deliberately carries no
    owner: this module does not know whether the text came from a task field or
    from a model response, and a match means the same thing either way.

    Attributes:
        vector (str): The registered vector name that matched.
        excerpt (str): A short excerpt around the match, whitespace collapsed.
        start (int): Where the match began, so a caller can redact the span.
        end (int): Where the match ended.
    """

    vector: str
    excerpt: str
    start: int
    end: int


def registered_vectors() -> list[str]:
    """Return every registered vector name.

    Returns:
        list[str]: Pattern vector names plus the invisible-character vector, in
        sorted order so a run's output does not depend on mapping order.
    """
    return sorted(
        set(_VECTOR_PATTERNS) | {INVISIBLE_VECTOR, HOMOGLYPH_VECTOR}
    )


def is_registered_vector(vector: str) -> bool:
    """Report whether a name is a registered vector.

    Args:
        vector (str): The name to check.

    Returns:
        bool: True when registered.
    """
    return vector in _VECTOR_PATTERNS or vector in {
        INVISIBLE_VECTOR,
        HOMOGLYPH_VECTOR,
    }



def _script_of(character: str) -> str:
    """Return the script a letter belongs to.

    Args:
        character (str): One character.

    Returns:
        str: ``LATIN``, ``CYRILLIC``, ``GREEK`` or ``OTHER``. Derived from the
        Unicode name rather than from a table, so a letter this project has
        never seen is classified correctly without being listed.
    """
    name = unicodedata.name(character, "")
    for script in ("LATIN",) + _CONFUSABLE_SCRIPTS:
        if name.startswith(script + " "):
            return script
    return "OTHER"


def homoglyph_words(text: str) -> list[str]:
    """Return every word mixing Latin with a confusable script.

    **Mixed script inside one word is the test.** A word written wholly in
    Cyrillic is Russian and reported by nothing here; a word mixing Cyrillic
    and Latin imitates the Latin one. Reporting the first would call every
    Russian document an attack, which is the failure that gets a check
    disabled within a week.

    Args:
        text (str): The text to scan.

    Returns:
        list[str]: The offending words, in order of appearance and without
        duplicates.
    """
    found: list[str] = []
    for word in _WORD.findall(text):
        scripts = {_script_of(character) for character in word}
        confusable = scripts & set(_CONFUSABLE_SCRIPTS)
        if confusable and "LATIN" in scripts and word not in found:
            found.append(word)
    return found


def match_vectors(text: str) -> list[VectorMatch]:
    """Apply every registered vector to one piece of text.

    Args:
        text (str): The text to screen.

    Returns:
        list[VectorMatch]: One match per vector that fired. **A text matching
        several vectors yields several matches**, because the vectors describe
        different attacks and collapsing them to a count would lose exactly the
        distinction the registry exists to make. Ordered with the
        invisible-character match first and the pattern matches in sorted
        vector order, so the result is reproducible.
    """
    matches: list[VectorMatch] = []
    invisible = sorted({character for character in text if character in _INVISIBLE_CHARS})
    if invisible:
        position = min(text.index(character) for character in invisible)
        matches.append(
            VectorMatch(
                vector=INVISIBLE_VECTOR,
                excerpt=", ".join(describe_character(entry) for entry in invisible),
                start=position,
                end=position + 1,
            )
        )

    confusable = homoglyph_words(text)
    if confusable:
        position = text.index(confusable[0])
        matches.append(
            VectorMatch(
                vector=HOMOGLYPH_VECTOR,
                excerpt=", ".join(confusable[:5]),
                start=position,
                end=position + len(confusable[0]),
            )
        )

    for vector in sorted(_VECTOR_PATTERNS):
        found = _VECTOR_PATTERNS[vector].search(text)
        if found is not None:
            matches.append(
                VectorMatch(
                    vector=vector,
                    excerpt=excerpt_around(text, found.start()),
                    start=found.start(),
                    end=found.end(),
                )
            )
    return matches


def describe_character(character: str) -> str:
    """Name an invisible character so a message is readable.

    Reproducing the character in a message would be useless, since it has no
    glyph, and would carry the hidden character into the record.

    Args:
        character (str): The character to describe.

    Returns:
        str: Its Unicode name and code point.
    """
    # Every code point in the current set is named, so this fallback is not
    # reachable today. It is kept because the set is data and will grow, and
    # unicodedata.name raises for an unassigned code point rather than
    # returning a placeholder. A screen that crashed while describing what it
    # found would lose the finding it had already made.
    try:
        name = unicodedata.name(character)
    except ValueError:
        name = "UNNAMED"
    return f"{name} (U+{ord(character):04X})"


def excerpt_around(text: str, position: int, window: int = 40) -> str:
    """Return a short excerpt around a match position.

    **Bounded, and the full text is never carried.** A context document can be
    thousands of characters, and a finding reproducing one is unreadable where a
    reader meets it. The window is enough to judge a match and not enough to
    relocate a payload wholesale.

    Args:
        text (str): The full text.
        position (int): Where the match began.
        window (int): Characters to include either side.

    Returns:
        str: The excerpt, with surrounding whitespace collapsed so a multi-line
        payload stays readable on one line of a log.
    """
    start = max(0, position - window)
    end = min(len(text), position + window)
    return " ".join(text[start:end].split())
