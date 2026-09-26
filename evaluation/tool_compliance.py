# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Whether the model invoked what it was told to, and nothing it was not.

Specified by ``docs/design/tier3_evaluation.md`` section 5B.

**Gate 5 was specified without this.** Ingestion validated the tool
expectation, execution captured the calls, and nothing compared them. Eight
graded cases were collected against a capability no module implemented, and a
corpus carrying `tool_expectation` blocks would have loaded cleanly and
measured nothing.

**Every check here is programmatic and never a model call**, for the same
reason the injection screen is not: a tool name is attacker-influenced text,
and a model asked to detect an attack is itself injectable.

**The results are ordinary assertion results.** A tool violation then fails the
case through the same conjunctive gate as every other assertion, and the
verdict, the artifact and the taxonomy counting need no second path.
"""

import logging
from typing import Any, Final, Optional

from evaluation.assertions import AssertionResult

logger = logging.getLogger(__name__)

_TOOL_CODE = "QC_LLM_TOOL_VIOLATION"
_SCHEMA_CODE = "QC_LLM_SCHEMA_VIOLATION"

# Reported as an assertion of this kind, so a reader can tell a tool result
# from a regex result without consulting the rule set.
_KIND = "tool_expectation"

_VIOLATION = "violation"

# The JSON Schema primitives this subset models. A declaration outside it
# constrains nothing here rather than reporting a violation nobody can act on.
_JSON_TYPES: Final[dict[str, tuple[type, ...]]] = {
    "boolean": (bool,),
    "integer": (int,),
    "number": (int, float),
    "string": (str,),
    "array": (list,),
    "object": (dict,),
}


def evaluate_tool_compliance(
    tool_calls: tuple[Any, ...],
    expectation: Optional[Any],
    offered: tuple[Any, ...] = (),
) -> list[AssertionResult]:
    """Check captured tool calls against what the rule set expects.

    Args:
        tool_calls (tuple): What the model invoked, as captured. Never
            executed.
        expectation (Optional[Any]): The rule set's tool expectation, absent
            for a case that makes no tool claim.
        offered (tuple): The tools the task offered, used to report a name the
            model invented.

    Returns:
        list[AssertionResult]: One result per violation, empty when the
        response complies. **An empty list is not a recorded pass**: a blank
        taking its default is normal operation, and recording one would corrupt
        every later count of tool behaviour.
    """
    if expectation is None:
        return []

    invoked = tuple(str(call.tool_name) for call in tool_calls)
    results: list[AssertionResult] = []

    results.extend(_missing_required(invoked, expectation))
    results.extend(_forbidden_invoked(invoked, expectation))
    results.extend(_not_offered(invoked, offered))
    results.extend(_argument_problems(tool_calls, offered))
    return results


def _missing_required(
    invoked: tuple[str, ...], expectation: Any
) -> list[AssertionResult]:
    """Report a required tool the model never called.

    Args:
        invoked (tuple): Tool names the model invoked.
        expectation (Any): The rule set's tool expectation.

    Returns:
        list[AssertionResult]: One result when any required tool is absent.
    """
    required = frozenset(getattr(expectation, "required_tools", frozenset()))
    missing = sorted(required - set(invoked))
    if not missing:
        return []
    logger.warning("%s required tools not invoked: %s", _TOOL_CODE, missing)
    return [
        AssertionResult(
            assertion_id="A_TOOL_REQUIRED_INVOKED",
            kind=_KIND,
            passed=False,
            severity=_VIOLATION,
            detail=(
                f"required tools were not invoked: {missing}; "
                f"invoked {sorted(set(invoked))}"
            ),
            taxonomy_code=_TOOL_CODE,
        )
    ]


def _forbidden_invoked(
    invoked: tuple[str, ...], expectation: Any
) -> list[AssertionResult]:
    """Report a forbidden tool the model called.

    Args:
        invoked (tuple): Tool names the model invoked.
        expectation (Any): The rule set's tool expectation.

    Returns:
        list[AssertionResult]: One result when any forbidden tool was called.
    """
    forbidden = frozenset(getattr(expectation, "forbidden_tools", frozenset()))
    called = sorted(forbidden & set(invoked))
    if not called:
        return []
    logger.warning("%s forbidden tools invoked: %s", _TOOL_CODE, called)
    return [
        AssertionResult(
            assertion_id="A_TOOL_FORBIDDEN_AVOIDED",
            kind=_KIND,
            passed=False,
            severity=_VIOLATION,
            detail=f"forbidden tools were invoked: {called}",
            taxonomy_code=_TOOL_CODE,
        )
    ]


def _not_offered(
    invoked: tuple[str, ...], offered: tuple[Any, ...]
) -> list[AssertionResult]:
    """Report a tool the model invented.

    **This is not implied by the forbidden set.** A forbidden list names the
    tools an author thought of; the offered set is everything that exists. A
    model naming a tool nobody supplied has done something no list would have
    caught.

    Args:
        invoked (tuple): Tool names the model invoked.
        offered (tuple): The tools the task offered.

    Returns:
        list[AssertionResult]: One result when a name was invented. **An empty
        offered set reports nothing**, because a task that offered no tools
        gives no basis for saying which names exist, and reporting every call
        there would fire on every case that declares no tools.
    """
    if not offered:
        return []
    known = {str(tool.tool_name) for tool in offered}
    invented = sorted(set(invoked) - known)
    if not invented:
        return []
    logger.warning("%s tools invoked that were never offered: %s", _TOOL_CODE, invented)
    return [
        AssertionResult(
            assertion_id="A_TOOL_WAS_OFFERED",
            kind=_KIND,
            passed=False,
            severity=_VIOLATION,
            detail=(
                f"tools were invoked that the task never offered: {invented}; "
                f"offered {sorted(known)}"
            ),
            taxonomy_code=_TOOL_CODE,
        )
    ]


def _argument_problems(
    tool_calls: tuple[Any, ...], offered: tuple[Any, ...]
) -> list[AssertionResult]:
    """Report arguments that violate a tool's declared parameter schema.

    **A different code from the other three.** Calling the wrong tool and
    calling the right tool wrongly are different defects with different fixes,
    and one code covering both would make them indistinguishable in the record.

    Args:
        tool_calls (tuple): What the model invoked.
        offered (tuple): The tools the task offered, carrying their schemas.

    Returns:
        list[AssertionResult]: One result per non-conforming call.
    """
    schemas = {
        str(tool.tool_name): getattr(tool, "parameters_schema", {}) or {}
        for tool in offered
    }
    results: list[AssertionResult] = []
    for call in tool_calls:
        schema = schemas.get(str(call.tool_name))
        if schema is None:
            # Reported by _not_offered, and reporting it twice would count one
            # defect as two in every later aggregate.
            continue
        problems = _schema_problems(dict(call.arguments or {}), schema)
        if not problems:
            continue
        logger.warning(
            "%s %s arguments do not conform: %s",
            _SCHEMA_CODE, call.tool_name, problems,
        )
        results.append(
            AssertionResult(
                assertion_id=f"A_TOOL_ARGUMENTS_{str(call.tool_name).upper()}",
                kind=_KIND,
                passed=False,
                severity=_VIOLATION,
                detail=(
                    f"{call.tool_name} was invoked with arguments that violate "
                    f"its declared schema: {'; '.join(problems)}"
                ),
                taxonomy_code=_SCHEMA_CODE,
            )
        )
    return results


def _schema_problems(arguments: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Return every way the arguments depart from the declared schema.

    **Deliberately a subset of JSON Schema**, covering required keys, declared
    properties and primitive types. A full implementation belongs in a library,
    and the three rules here are the ones a model actually breaks: omitting a
    required argument, inventing one, and sending a string where a number was
    declared.

    Args:
        arguments (dict): What the model sent.
        schema (dict): The declared parameter schema.

    Returns:
        list[str]: One entry per departure, empty when the arguments conform.
    """
    properties = schema.get("properties") or {}
    problems: list[str] = []

    for name in sorted(schema.get("required") or ()):
        if name not in arguments:
            problems.append(f"required argument {name!r} is missing")

    if properties and not schema.get("additionalProperties", False):
        for name in sorted(set(arguments) - set(properties)):
            problems.append(f"argument {name!r} is not declared")

    for name, value in sorted(arguments.items()):
        declared = (properties.get(name) or {}).get("type")
        if declared is None:
            continue
        if not _matches_type(value, str(declared)):
            problems.append(
                f"argument {name!r} is {type(value).__name__}, "
                f"and the schema declares {declared}"
            )
    return problems


def _matches_type(value: Any, declared: str) -> bool:
    """Report whether a value matches a declared JSON Schema type.

    Args:
        value (Any): The supplied value.
        declared (str): The declared type name.

    Returns:
        bool: True when it matches, and True for a type name this subset does
        not model, so an unmodelled declaration never reports a false
        violation.
    """
    expected = _JSON_TYPES.get(declared)
    if expected is None:
        return True
    # BOOL IS A SUBCLASS OF INT IN PYTHON, so a flag sent where a count was
    # declared would otherwise pass as an integer.
    if declared in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, expected)
