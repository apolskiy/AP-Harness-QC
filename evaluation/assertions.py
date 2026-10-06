# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Programmatic assertions: the deterministic half of the dual pass.

Specified by ``docs/design/tier3_evaluation.md`` sections 4.1 and 5.

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
case is graded here and never sent to a judge.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Final, Optional

from cmn.markup import normalise_markup

logger = logging.getLogger(__name__)

# A fatal failure is never judged, flag or not: there is nothing coherent to
# score. A violation is judged only under the flag. The two severities exist
# solely to make that distinction, so they are a closed set.
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
    """

    assertion_id: str
    kind: str
    passed: bool
    severity: str
    detail: str
    taxonomy_code: Optional[str] = None

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


def _check_contains(text: str, parameters: dict[str, Any]) -> tuple[bool, str]:
    """Check that a required substring is present.

    Args:
        text (str): The candidate output.
        parameters (dict): ``value``, and optional ``case_sensitive``.

    Returns:
        tuple: Whether the check held, and what was found.
    """
    needle = str(parameters["value"])
    haystack = text if parameters.get("case_sensitive", False) else text.lower()
    target = needle if parameters.get("case_sensitive", False) else needle.lower()
    found = target in haystack
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


# One entry per kind named in design section 5. A kind is a registry entry, so
# adding one is data plus a function rather than a change to the runner.
_ASSERTION_KINDS: Final[dict[str, Callable[[str, dict[str, Any]], tuple[bool, str]]]] = {
    "regex": _check_regex,
    "json_schema": _check_json_schema,
    "length": _check_length,
    "contains": _check_contains,
    "not_contains": _check_not_contains,
}

# WHICH KINDS READ NORMALISED TEXT, per design section 5.1. The two excluded
# kinds are excluded for a reason each, not by omission: `length` counts the
# text as written, and removing markup shortens it, so a bound stated against
# a model's output would be measured against something shorter; `json_schema`
# parses the body, so altering the text before parsing changes what is
# validated.
_MARKUP_SENSITIVE: Final[frozenset[str]] = frozenset(
    {"regex", "contains", "not_contains"}
)


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

    # NORMALISED FOR THE KINDS THAT READ PROSE, unless this assertion declares
    # that markup is part of what it checks. Per design section 5.1.
    parameters = dict(assertion.parameters)
    literal = bool(parameters.pop("literal_markup", False))
    normalise = assertion.kind in _MARKUP_SENSITIVE and not literal
    passed, detail = checker(
        normalise_markup(text) if normalise else text, parameters
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
