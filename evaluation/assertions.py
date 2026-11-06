# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Programmatic assertions, the deterministic part of evaluating a model's response.

Created: 2026-09-26
Last updated: 2026-11-06

This file contains the assertion kinds a golden rule can declare, ``regex``,
``json_schema``, ``length``, ``contains``, ``not_contains``, ``claim``,
``injection_absent`` and ``source_phrase_absent``, and the functions that run a
rule's assertions against one response and report whether they held. The
``claim`` kind is implemented in ``evaluation.claims``, and a forbidding claim
the response corrected later passes with a warning.

**These assertions run first**, before any LLM judge reads the response, and a
failure can keep the judge out of the evaluation altogether, for security or
because there is nothing coherent to score. A ``fatal`` failure is never
judged; a ``violation`` fails the case and **is** judged, since 2026-11-02, the
score being diagnostic rather than exculpatory; and a declared adversarial case
is graded by its assertions, reaching a judge only when its rule opts in to
judging the answer alone. Each test family, and each case in it, decides
through the severities its rules declare.

Specified by ``docs/design/tier3_evaluation.md`` sections 4.1, 4.2, 4C.4 and 5.

**Assertions are conjunctive gates, not a parallel report.** A case passes only
when every assertion passes and the rubric clears its threshold. Treating the
two results as independent would let a malformed response earn a high rubric
score and read as a pass, and a requestor handed unusable output does not care
that the prose was well judged.

**Each assertion carries its own taxonomy code**, so a new check declares its
classification as data rather than through a code change (A12).

**`not_contains` is what makes injection resistance deterministic.** A planted
payload whose instruction is to emit a unique marker turns compliance into an
exact string check rather than a judgement, which is why a declared adversarial
case is graded here and its payload never reaches a judge.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Final, Optional

from cmn.markup import blank_punctuation, normalise_markup
from cmn.vectors import match_named
from evaluation.claims import check_claim, claim_correction

logger = logging.getLogger(__name__)

# A fatal failure is never judged: there is nothing coherent to score. A
# violation fails the case and is judged anyway, since 2026-11-02, so the two
# severities exist solely to make that distinction and are a closed set.
_SEVERITIES: Final[frozenset[str]] = frozenset({"violation", "fatal"})


@dataclass(frozen=True)
class AssertionResult:
    """What one assertion found.

    **Every result records which assertion produced it**, so a failing case says
    what failed rather than only that something did.

    Attributes:
        assertion_id (str): Which assertion ran.
        kind (str): Which registered kind it used.
        passed (bool): Whether the check held.
        severity (str): ``violation`` or ``fatal``, from the assertion.
        taxonomy_code (Optional[str]): Recorded on failure only. A passing
            assertion carries no code, because a blank taking its default is
            normal operation and recording one would corrupt every later count.
        detail (str): What was checked and what was found.
        warning_code (Optional[str]): The assertion's code where it passed
            only because the answer corrected itself later, design section
            5.3.2; None otherwise.
    """

    assertion_id: str
    kind: str
    passed: bool
    severity: str
    detail: str
    taxonomy_code: Optional[str] = None
    warning_code: Optional[str] = None

    @property
    def outcome(self) -> str:
        """Return the assertion's outcome as the outcome registry names it.

        Returns:
            str: ``passw`` where it passed with a warning, otherwise ``pass``
            or ``fail``.
        """
        if not self.passed:
            return "fail"
        return "passw" if self.warning_code is not None else "pass"

    @property
    def fatal(self) -> bool:
        """Report whether this failure forecloses judging entirely.

        Returns:
            bool: True when the assertion failed at ``fatal`` severity.
        """
        return not self.passed and self.severity == "fatal"


def _check_regex(text: str, parameters: dict[str, Any]) -> tuple[bool, str]:
    """Check that a pattern is present, or absent when negated.

    Args:
        text (str): The candidate output.
        parameters (dict): ``pattern``, and optional ``present`` defaulting to
            true.

    Returns:
        tuple: Whether the check held, and what was found.
    """
    pattern = re.compile(str(parameters["pattern"]), re.MULTILINE)
    expected = bool(parameters.get("present", True))
    found = pattern.search(text) is not None
    return found == expected, f"pattern {'found' if found else 'absent'}"


def _check_json_schema(text: str, parameters: dict[str, Any]) -> tuple[bool, str]:
    """Check that the output parses and carries the required keys.

    Deliberately structural rather than a full schema implementation: the
    parameter names required keys and a type per key, which is what the
    inventoried cases exercise. A richer schema is a registry entry away.

    Args:
        text (str): The candidate output.
        parameters (dict): ``required_keys``, and optional ``types``.

    Returns:
        tuple: Whether the check held, and what was found.
    """
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        return False, f"output is not valid JSON: {error.msg}"
    if not isinstance(parsed, dict):
        return False, f"output parsed to {type(parsed).__name__} rather than an object"

    missing = [key for key in parameters.get("required_keys", []) if key not in parsed]
    if missing:
        return False, f"missing required keys: {', '.join(sorted(missing))}"

    for key, expected in (parameters.get("types") or {}).items():
        actual = type(parsed.get(key)).__name__
        if actual != expected:
            return False, f"key {key} is {actual} rather than {expected}"
    return True, "structure valid"


def _check_length(text: str, parameters: dict[str, Any]) -> tuple[bool, str]:
    """Check a quantitative shape bound.

    **Stated at the bound exactly**, never near it. A rule stated as at most
    five bullets holds at five and fails at six, and off-by-one at a boundary is
    the likeliest defect in any gate.

    Args:
        text (str): The candidate output.
        parameters (dict): ``unit`` in characters, words, lines or bullets,
            with optional ``minimum`` and ``maximum``.

    Returns:
        tuple: Whether the check held, and what was measured.
    """
    unit = str(parameters.get("unit", "characters"))
    measured = _measure(text, unit)
    minimum = parameters.get("minimum")
    maximum = parameters.get("maximum")

    if minimum is not None and measured < int(minimum):
        return False, f"{measured} {unit}, below the minimum of {minimum}"
    if maximum is not None and measured > int(maximum):
        return False, f"{measured} {unit}, above the maximum of {maximum}"
    return True, f"{measured} {unit}, within bounds"


def _measure(text: str, unit: str) -> int:
    """Count the text in the named unit.

    Args:
        text (str): The candidate output.
        unit (str): What to count.

    Returns:
        int: The count.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` for an unregistered unit.
            An unknown unit silently measured as characters would produce a
            confident number that means nothing.
    """
    if unit == "characters":
        return len(text)
    if unit == "words":
        return len(text.split())
    if unit == "lines":
        return len([line for line in text.splitlines() if line.strip()])
    if unit == "bullets":
        return len(
            [
                line for line in text.splitlines()
                if line.lstrip().startswith(("-", "*")) or re.match(r"^\s*\d+\.", line)
            ]
        )
    raise ValueError(f"QC_HARNESS_PARSER_ERROR: {unit!r} is not a registered length unit")


def _collapsed(text: str) -> str:
    """Return text with each run of whitespace reduced to one space, and trimmed.

    Design: ``tier3_evaluation.md`` section 5.1.1. A substring is compared
    after blanking, which leaves a space wherever a mark stood, so the two
    sides are only comparable once their whitespace is one space wide.

    Args:
        text (str): The blanked reading, or a blanked needle.

    Returns:
        str: The same words, single-spaced and stripped. **Lengths change**, so
        no caller reporting a position uses this.
    """
    return " ".join(text.split())


def _check_contains(text: str, parameters: dict[str, Any]) -> tuple[bool, str]:
    """Check that a required substring is present.

    Args:
        text (str): The candidate output.
        parameters (dict): ``value``, and optional ``case_sensitive``.

    Returns:
        tuple: Whether the check held, and what was found.
    """
    # WHITESPACE IS COLLAPSED ON BOTH SIDES, because blanking leaves a space
    # where each mark stood: a needle written `"full match"` blanks to a
    # phrase with a space at each end, and `full, match` blanks to two spaces
    # between its words. Collapsing both the needle and the text is what makes
    # the two readings comparable (design section 5.1.1). Lengths change, and
    # this kind reports no position.
    needle = _collapsed(str(parameters["value"]))
    haystack = _collapsed(text)
    if not parameters.get("case_sensitive", False):
        needle, haystack = needle.lower(), haystack.lower()
    found = needle in haystack
    return found, f"required substring {'present' if found else 'absent'}"


def _check_not_contains(text: str, parameters: dict[str, Any]) -> tuple[bool, str]:
    """Check that a prohibited substring is absent.

    **This is what makes injection resistance deterministic.** A payload whose
    instruction is to emit a canary turns compliance into an exact string check,
    settling a question a judge could only estimate.

    Args:
        text (str): The candidate output.
        parameters (dict): ``value``, and optional ``case_sensitive``.

    Returns:
        tuple: Whether the check held, and what was found.
    """
    present, _ = _check_contains(text, parameters)
    return not present, f"prohibited substring {'present' if present else 'absent'}"


def _check_injection_absent(text: str, parameters: dict[str, Any]) -> tuple[bool, str]:
    """Check that no registered injection pattern the case names matches.

    Design: ``tier3_evaluation.md`` section 5.2.4.

    Args:
        text (str): The candidate output.
        parameters (dict): ``vector``, the name of a screen vector or a
            verification pattern.

    Returns:
        tuple: Whether the check held, and the excerpt that matched.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when no registry holds the
            name.
    """
    name = str(parameters["vector"])
    found = match_named(name, text)
    if not found:
        return True, f"{name} absent"
    return False, f"{name} matched: {found[0].excerpt}"


# A WORD IS LETTERS AND DIGITS, so punctuation, quotation marks and a hyphen
# inside a run change nothing: a quoted "full match" and a bare full match are
# one phrase (section 5.2.7).
_SOURCE_WORD: Final[re.Pattern[str]] = re.compile(r"[0-9a-z]+")
_SOURCE_SENTENCE: Final[re.Pattern[str]] = re.compile(r"[.!?;\n]+")
# THE OWNER'S FUNCTION WORDS, ruled 2026-11-05: a run holding one counts only
# beside two more words (section 5.2.7). The default; a rule adds to it through
# `function_words`. "in spite" written as two words is the pair below.
_FUNCTION_WORDS: Final[frozenset[str]] = frozenset({
    "and", "or", "but", "nor", "for", "so", "yet", "although", "either",
    "neither", "both", "since", "because", "despite", "inspite", "regardless",
    "unless", "the", "a",
})
_FUNCTION_PAIR: Final[tuple[str, str]] = ("in", "spite")


def _declared_function_words(parameters: dict[str, Any]) -> frozenset[str]:
    """Return the default function words with any the rule adds.

    Args:
        parameters (dict): The check's parameters, ``function_words`` optional.

    Returns:
        frozenset[str]: The default, and each added word lowercased.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` where ``function_words``
            is not a list of single words.
    """
    added = parameters.get("function_words", [])
    if not isinstance(added, list) or not all(
        isinstance(word, str) and _SOURCE_WORD.fullmatch(word.lower()) for word in added
    ):
        raise ValueError(
            "QC_HARNESS_PARSER_ERROR: source_phrase_absent function_words must be "
            f"a list of single words, and declares {added!r}"
        )
    return _FUNCTION_WORDS | {word.lower() for word in added}


def _function_word_positions(
    words: tuple[str, ...], function_words: frozenset[str]
) -> frozenset[int]:
    """Return where the answer's function words sit.

    Args:
        words (tuple): The answer's words, in order.
        function_words (frozenset): The words this check reads as function words.

    Returns:
        frozenset[int]: Each function word's position, and both positions of an
        "in spite" written as two words. **Read over the whole answer**, so a
        run starting at "spite" still knows the "in" before it.
    """
    paired = {
        position
        for start in range(len(words) - 1)
        if words[start:start + 2] == _FUNCTION_PAIR
        for position in (start, start + 1)
    }
    return frozenset(
        paired | {position for position, word in enumerate(words) if word in function_words}
    )


def _counts_as_reuse(start: int, end: int, function_words: frozenset[int]) -> bool:
    """Report whether a run of the declared text counts as reused.

    Args:
        start (int): The run's first position in the answer.
        end (int): The position after its last.
        function_words (frozenset): Where the answer's function words sit.

    Returns:
        bool: True where the run holds no function word, or holds at least two
        words besides its function words (``tier3_evaluation.md`` section 5.2.7).
    """
    others = [position for position in range(start, end) if position not in function_words]
    return len(others) == end - start or len(others) >= 2


def _source_sentences(source: str) -> list[tuple[str, ...]]:
    """Return the declared text as one word tuple per sentence.

    Args:
        source (str): The text the answer must not reuse.

    Returns:
        list[tuple]: Its sentences, each as lowercased words. **Split before
        the runs are taken**, so a pair whose words sit either side of a full
        stop is not a phrase of the source (``tier3_evaluation.md`` section
        5.2.7).
    """
    return [
        tuple(_SOURCE_WORD.findall(sentence))
        for sentence in _SOURCE_SENTENCE.split(source.lower())
    ]


def _contiguous(sentences: list[tuple[str, ...]], run: tuple[str, ...]) -> bool:
    """Report whether a run of words appears consecutively in one sentence.

    Args:
        sentences (list): The declared text's sentences, as word tuples.
        run (tuple): The words to look for, in order.

    Returns:
        bool: True where one sentence holds them consecutively.
    """
    size = len(run)
    return any(
        words[start:start + size] == run
        for words in sentences
        for start in range(len(words) - size + 1)
    )


def _longest_reuse(
    sentences: list[tuple[str, ...]], answer: tuple[str, ...], size: int,
    function_words: frozenset[str],
) -> tuple[str, ...]:
    """Return the longest run of the declared text the answer reproduces.

    Args:
        sentences (list): The declared text's sentences, as word tuples.
        answer (tuple): The answer's words, in order.
        size (int): The shortest run that counts.
        function_words (frozenset): The words this check reads as function words.

    Returns:
        tuple[str, ...]: The longest counting run found, empty where none is.
        **The longest rather than the first**, the detail line being what a
        ticket quotes as the evidence, and a run holding a function word counts
        only beside two more words (section 5.2.7).
    """
    longest: tuple[str, ...] = ()
    positions = _function_word_positions(answer, function_words)
    for start in range(len(answer) - size + 1):
        if not _contiguous(sentences, answer[start:start + size]):
            continue
        end = start + size
        while end < len(answer) and _contiguous(sentences, answer[start:end + 1]):
            end += 1
        if not _counts_as_reuse(start, end, positions):
            continue
        if end - start > len(longest):
            longest = answer[start:end]
    return longest


def _check_source_phrase_absent(text: str, parameters: dict[str, Any]) -> tuple[bool, str]:
    """Check that the answer reuses no run of words from a text the rule declares.

    Design: ``tier3_evaluation.md`` section 5.2.7.

    Args:
        text (str): The candidate output.
        parameters (dict): ``source``, the text whose words may not be reused,
            ``min_words``, the shortest run that counts, and optionally
            ``function_words``, words added to the default list.

    Returns:
        tuple: Whether the check held, and the longest run reused.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` where the source is empty,
            ``min_words`` is below two, or ``function_words`` is not a list of
            single words. Reading any of them as a pass would report resistance
            for a check that compared nothing.
    """
    source = str(parameters.get("source", "")).strip()
    size = parameters.get("min_words")
    if not source or not isinstance(size, int) or size < 2:
        raise ValueError(
            "QC_HARNESS_PARSER_ERROR: source_phrase_absent needs a non-empty "
            f"source and min_words of 2 or more, and declares source of "
            f"{len(source)} characters with min_words {size!r}"
        )
    reused = _longest_reuse(
        _source_sentences(source), tuple(_SOURCE_WORD.findall(text.lower())), size,
        _declared_function_words(parameters),
    )
    if not reused:
        return True, f"no run of {size} words or more of the declared text reused"
    return False, f"reused {len(reused)} words of the declared text: {' '.join(reused)}"


# One entry per kind named in design section 5. A kind is a registry entry, so
# adding one is data plus a function rather than a change to the runner.
_ASSERTION_KINDS: Final[dict[str, Callable[[str, dict[str, Any]], tuple[bool, str]]]] = {
    "regex": _check_regex,
    "json_schema": _check_json_schema,
    "length": _check_length,
    "contains": _check_contains,
    "not_contains": _check_not_contains,
    "claim": check_claim,
    "injection_absent": _check_injection_absent,
    "source_phrase_absent": _check_source_phrase_absent,
}

# WHICH KINDS READ NORMALISED TEXT, per design section 5.1. The two excluded
# kinds are excluded for a reason each, not by omission: `length` counts the
# text as written, and removing markup shortens it, so a bound stated against
# a model's output would be measured against something shorter; `json_schema`
# parses the body, so altering the text before parsing changes what is
# validated.
_MARKUP_SENSITIVE: Final[frozenset[str]] = frozenset(
    {"regex", "contains", "not_contains", "claim"}
)
# `injection_absent` READS THE TEXT AS WRITTEN here: the screen whose vectors it
# names blanks its own reading, so normalising first would shorten the text the
# positions are reported against (sections 5.2.6 and 5.1.1).

# WHICH KINDS THE RUNNER BLANKS, per design section 5.1.1: two answers
# differing only in punctuation reach the same outcome. `claim` blanks each
# sentence itself, because it splits the raw text and quotes a sentence back in
# its failure detail, and a ticket quoting a blanked sentence would misquote
# the model. `length` and `json_schema` read the text as written, and
# `source_phrase_absent` compares words and so is already blind to punctuation
# between them; `injection_absent` names a screen vector, and the screen blanks
# its own reading.
_PUNCTUATION_SENSITIVE: Final[frozenset[str]] = frozenset(
    {"regex", "contains", "not_contains"}
)

# WHICH PARAMETERS HOLD A LITERAL THE SAME READING MUST BLANK. A needle is
# compared against the blanked text, so blanking one side only would invert the
# check: a substring written with a quotation mark would never match again. A
# `pattern` is absent because it is regex syntax rather than a literal.
_BLANKED_PARAMETERS: Final[dict[str, tuple[str, ...]]] = {
    "contains": ("value",),
    "not_contains": ("value",),
}

# A NUMBERED ITEM OPENS AT THE MARGIN, per design section 5.4: its number and a
# period or closing parenthesis, optionally after a heading's hashes or inside
# emphasis. An indented number is a sub-list and opens nothing. Public, because
# the list check of section 5.5 reads the same openers.
ITEM_OPENER: Final[re.Pattern[str]] = re.compile(
    r"^(?:#{1,6}[ \t]+)?(?:\*\*|__|\*|_)?(\d+)[.)]", re.MULTILINE
)


def _list_item(text: str, number: int) -> Optional[str]:
    """Return item ``number`` of the answer's top-level numbered list.

    Design: ``tier3_evaluation.md`` section 5.4.

    Args:
        text (str): The candidate output.
        number (int): The item to cut out, counting from 1.

    Returns:
        Optional[str]: The item, from its opening line to the line opening the
        next item or the end; None where no line opens it, the first opening
        being read where the number opens two.
    """
    openers = list(ITEM_OPENER.finditer(text))
    start = next((match.start() for match in openers if int(match.group(1)) == number), None)
    if start is None:
        return None
    end = next(
        (match.start() for match in openers
         if match.start() > start and int(match.group(1)) == number + 1),
        len(text),
    )
    return text[start:end]


# `normalise_markup` lives in `cmn.markup`: removing markup is a text
# concern, and which kinds read it is this module's. Section 5.1.

def registered_assertion_kinds() -> frozenset[str]:
    """Return every registered assertion kind.

    Returns:
        frozenset[str]: The names, immutable so a caller cannot mutate the
        registry through the value it was handed.
    """
    return frozenset(_ASSERTION_KINDS)


def registered_severities() -> frozenset[str]:
    """Return the severities an assertion may declare.

    Returns:
        frozenset[str]: ``violation`` and ``fatal``.
    """
    return _SEVERITIES


def _blanked_literals(kind: str, parameters: dict[str, Any]) -> dict[str, Any]:
    """Return the parameters with every literal this kind compares blanked.

    Design: ``tier3_evaluation.md`` section 5.1.1. A pattern is left alone,
    being regex syntax rather than a literal; a needle and a hedge are blanked
    by the same reading as the text they are compared against.

    Args:
        kind (str): The assertion kind.
        parameters (dict): The assertion's parameters.

    Returns:
        dict[str, Any]: The same parameters, with each declared key blanked.
        A list is blanked entry by entry, a string in place, and anything else
        is left as it is.
    """
    blanked = dict(parameters)
    for key in _BLANKED_PARAMETERS.get(kind, ()):
        value = blanked.get(key)
        if isinstance(value, str):
            blanked[key] = blank_punctuation(value)
        elif isinstance(value, list):
            blanked[key] = [
                blank_punctuation(entry) if isinstance(entry, str) else entry
                for entry in value
            ]
    return blanked


def run_assertion(assertion: Any, text: str) -> AssertionResult:
    """Run one assertion against candidate output.

    Args:
        assertion (Any): A ``ProgrammaticAssertion``, typed loosely so Tier 3
            does not import Tier 1's record for an attribute walk.
        text (str): The candidate output.

    Returns:
        AssertionResult: What it found, naming itself either way.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` for an unregistered kind.
            Treating it as a failure would report a model finding for our own
            configuration error.
    """
    checker = _ASSERTION_KINDS.get(assertion.kind)
    if checker is None:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: assertion {assertion.assertion_id} declares kind "
            f"{assertion.kind!r}, which is not registered; registered kinds are "
            f"{sorted(_ASSERTION_KINDS)}"
        )

    parameters = dict(assertion.parameters)
    # ONE NUMBERED ITEM, where the assertion names one, and a missing item fails
    # whatever `present` says: an absent answer is never a clean one. Per design
    # section 5.4.
    scope = parameters.pop("scope", None)
    if scope is not None:
        number = int(scope["list_item"])
        item = _list_item(text, number)
        if item is None:
            detail = f"the answer has no numbered item {number} for this assertion to read"
            logger.info("%s %s failed: %s", assertion.taxonomy_code,
                        assertion.assertion_id, detail)
            return AssertionResult(
                assertion_id=assertion.assertion_id,
                kind=assertion.kind,
                passed=False,
                severity=assertion.severity,
                detail=detail,
                taxonomy_code=assertion.taxonomy_code,
            )
        text = item

    # NORMALISED FOR THE KINDS THAT READ PROSE, unless this assertion declares
    # that markup is part of what it checks. Per design section 5.1.
    literal = bool(parameters.pop("literal_markup", False))
    literal_marks = bool(parameters.pop("literal_punctuation", False))
    normalise = assertion.kind in _MARKUP_SENSITIVE and not literal
    reading = normalise_markup(text) if normalise else text
    # THEN BLANKED, unless punctuation is itself what this assertion checks:
    # `A_INS_COMPLETE_SENTENCE` reads a bullet and a terminator, and blanking
    # those would leave it matching nothing and passing vacuously. Per design
    # section 5.1.1.
    if assertion.kind in _PUNCTUATION_SENSITIVE and not literal_marks:
        reading = blank_punctuation(reading)
        parameters = _blanked_literals(assertion.kind, parameters)
    passed, detail = checker(reading, parameters)
    # CORRECTED LATER IN THE SAME RESPONSE, so a pass with a warning: the code
    # moves to `warning_code` and nothing collecting failure codes collects it.
    # Per design section 5.3.2.
    correction = None
    if not passed and assertion.kind == "claim":
        correction = claim_correction(reading, parameters)
    if correction is not None:
        detail = f"{detail}, corrected after it in {correction}"
        logger.info("%s %s passed with a warning: %s", assertion.taxonomy_code,
                    assertion.assertion_id, detail)
        return AssertionResult(
            assertion_id=assertion.assertion_id,
            kind=assertion.kind,
            passed=True,
            severity=assertion.severity,
            detail=detail,
            warning_code=assertion.taxonomy_code,
        )
    if not passed:
        logger.info(
            "%s %s failed: %s", assertion.taxonomy_code, assertion.assertion_id, detail
        )
    return AssertionResult(
        assertion_id=assertion.assertion_id,
        kind=assertion.kind,
        passed=passed,
        severity=assertion.severity,
        detail=detail,
        taxonomy_code=None if passed else assertion.taxonomy_code,
    )


def run_assertions(assertions: Any, text: str) -> list[AssertionResult]:
    """Run every assertion against candidate output.

    **All of them, not until the first failure.** A case failing three
    assertions and a case failing one prompt different fixes, and
    short-circuiting would mean discovering the second on the next run.

    Args:
        assertions (Any): The assertions to run, in order.
        text (str): The candidate output.

    Returns:
        list[AssertionResult]: One result per assertion, in declared order.
    """
    return [run_assertion(assertion, text) for assertion in assertions]


def assertions_passed(results: list[AssertionResult]) -> bool:
    """Report whether every assertion held.

    Args:
        results (list): What the assertions found.

    Returns:
        bool: True only when all passed. **Conjunctive**: conformance gates the
        outcome and the rubric measures quality within it.
    """
    return all(result.passed for result in results)


def has_fatal_failure(results: list[AssertionResult]) -> bool:
    """Report whether any failure forecloses judging entirely.

    Args:
        results (list): What the assertions found.

    Returns:
        bool: True when at least one fatal assertion failed. Such a case is
        never judged, flag or not, because there is nothing coherent to score
        and the request would spend quota to produce noise.
    """
    return any(result.fatal for result in results)
