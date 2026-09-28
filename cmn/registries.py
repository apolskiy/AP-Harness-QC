# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Registries that the rest of the harness reads rather than hardcodes.

A registry here is the executable form of a table in a design document. The
document remains the single normative source; this module exists so that a
check can be run rather than remembered, and so that adding an entry is a data
change in one place.

Registered here:

* Priority conditions, per ``docs/design/test_taxonomy.md`` section 4.1.0.
  Invariant G6 in :mod:`ingestion.schemas` reads them to validate that a
  declared priority names a registered condition and respects its ceiling.
* Failure taxonomy codes, per ``docs/design/test_taxonomy.md`` section 6.

Nothing here decides anything. Callers ask whether an identifier is registered
and at what level; the rules that use those answers live with the component
they constrain.
"""

import logging
from dataclasses import dataclass
from typing import Any, Final, Optional

logger = logging.getLogger(__name__)

# Priority conditions, keyed by identifier, valued by the priority level the
# condition justifies. The level is a ceiling rather than an assignment: a case
# matching only a P2 condition cannot be assigned P0, but may be demoted to P3.
#
# Mirrors test_taxonomy.md section 4.1.0. An identifier absent there is a defect
# here, and MQC_CMN_UNI_10143 through 10145 verify the correspondence.
_PRIORITY_CONDITIONS: Final[dict[str, int]] = {
    "P0_SAFETY_CONTROL": 0,
    "P0_RUN_INTEGRITY": 0,
    "P0_CREDENTIAL_EXPOSURE": 0,
    "P0_EVALUATOR_TRUST": 0,
    "P0_SAFETY_CRITICAL_MODEL": 0,
    "P0_FOUNDATIONAL": 0,
    "P1_TIER_GUARANTEE": 1,
    "P1_ATTRIBUTION": 1,
    "P1_UNINTERPRETABLE_MEASUREMENT": 1,
    "P1_TOOL_COMPLIANCE": 1,
    "P1_REFERENTIAL_INTEGRITY": 1,
    "P2_DOCUMENTED_BEHAVIOUR": 2,
    "P2_RUBRIC_THRESHOLD": 2,
    "P2_SPECIFIED_ERROR_PATH": 2,
    "P3_BOUNDARY": 3,
    "P3_UNUSUAL_VALID_INPUT": 3,
    "P3_EDGE_PATH": 3,
    "P4_WORDING": 4,
    "P4_INFORMATIONAL": 4,
}

# Ingestion diagnostics, per test_taxonomy.md section 6.3. Severity is carried
# because the same family spans INFO, WARNING and ERROR: a blank cell taking its
# declared default is normal operation, and recording it as a defect would
# corrupt every later count of harness reliability.
_DATA_CODES: Final[dict[str, str]] = {
    "QC_DATA_BLANK_CELL_DEFAULTED": "INFO",
    "QC_DATA_COLUMN_ABSENT": "INFO",
    "QC_DATA_WHITESPACE_STRIPPED": "INFO",
    "QC_DATA_EMPTY_STRING": "WARNING",
    "QC_DATA_EXTRA_COLUMN_DROPPED": "WARNING",
    "QC_DATA_ADVERSARIAL_DECLARED": "WARNING",
    "QC_DATA_UNDECLARED_ADVERSARIAL": "WARNING",
    "QC_DATA_DUPLICATE_COLUMN": "ERROR",
    "QC_DATA_UNKNOWN_FIELD": "ERROR",
    "QC_DATA_REQUIRED_FIELD_MISSING": "ERROR",
    "QC_DATA_REQUIRED_FIELD_EMPTY": "ERROR",
    "QC_DATA_LOADER_DIVERGENCE": "ERROR",
    "QC_DATA_INVARIANT_VIOLATION": "ERROR",
    "QC_DATA_MALFORMED_SOURCE": "ERROR",
    "QC_DATA_IDENTIFIER_UNSAFE": "ERROR",
}

# Harness and infrastructure failures, per test_taxonomy.md section 6.2. Every
# adapter maps its provider's errors into this closed set, so a rate limit from
# one vendor and a rate limit from another become the same row in the durable
# record. Without translation, cross-engine comparison of harness reliability
# is not possible at all.
_HARNESS_CODES: Final[frozenset[str]] = frozenset({
    "QC_HARNESS_CANDIDATE_TIMEOUT",
    "QC_HARNESS_JUDGE_TIMEOUT",
    "QC_HARNESS_RATE_LIMIT",
    "QC_HARNESS_PROVIDER_UNAVAILABLE",
    "QC_HARNESS_GATEWAY_FAILURE",
    "QC_HARNESS_ENGINE_UNREACHABLE",
    "QC_HARNESS_REQUEST_REJECTED",
    "QC_HARNESS_PARSER_ERROR",
    "QC_HARNESS_AUTH_ERROR",
    "QC_HARNESS_PREFLIGHT_FAILURE",
    "QC_HARNESS_VERSION_UNAVAILABLE",
    "QC_HARNESS_FIXTURE_MISSING",
    "QC_HARNESS_FIXTURE_STALE",
    "QC_HARNESS_DEPENDENCY_UNMET",
    "QC_HARNESS_UPSTREAM_UNVERIFIED",
    "QC_HARNESS_BRANCH_NAME",
    "QC_HARNESS_BRANCH_STALE",
    "QC_HARNESS_BRANCH_ROUTE",
    # A RUN THAT STOPPED ITSELF RATHER THAN A PROVIDER STOPPING IT.
    # Distinct from a rate limit on purpose: a rate limit is the
    # provider declining, and this is us declining, which is a
    # different remedy (raise the ceiling, or accept that the run is
    # bigger than the budget) and a different conversation.
    "QC_HARNESS_BUDGET_EXHAUSTED",
    # THE ACCOUNT HAS NO MONEY LEFT, which is not the same as having no
    # valid credential. Reachable from 2026-09-28, when the project first
    # held prepaid credit that could run out.
    "QC_HARNESS_CREDIT_EXHAUSTED",
})

# The subset an adapter's map_error may return. Narrower than the family: a
# fixture code is produced by the replay store and a dependency code by the
# runner, and an adapter returning one would be reporting on something it
# cannot observe.
_ADAPTER_ERROR_CODES: Final[frozenset[str]] = frozenset({
    "QC_HARNESS_CREDIT_EXHAUSTED",
    "QC_HARNESS_CANDIDATE_TIMEOUT",
    "QC_HARNESS_RATE_LIMIT",
    "QC_HARNESS_PROVIDER_UNAVAILABLE",
    "QC_HARNESS_GATEWAY_FAILURE",
    "QC_HARNESS_ENGINE_UNREACHABLE",
    "QC_HARNESS_REQUEST_REJECTED",
    "QC_HARNESS_AUTH_ERROR",
    "QC_HARNESS_PARSER_ERROR",
    "QC_HARNESS_VERSION_UNAVAILABLE",
})

# Constraint kinds, per tier1_ingestion.md section 8. The vocabulary is open by
# design: an unregistered kind is permitted and warns rather than failing, so a
# typo surfaces instead of silently fragmenting the analysis the codes support.
# A kind used repeatedly is promoted into this table.
# Promoted 2026-09-23: the instruction-following corpus authored seven
# constraints across `count` and `ordering`, which is the repetition this
# registry says triggers promotion. Neither fits a registered kind: a bullet
# ceiling is a bound on how much rather than output shape, and a response can
# satisfy every shape constraint while ordering its content wrongly.
_CONSTRAINT_KINDS: Final[frozenset[str]] = frozenset(
    {"format", "prohibition", "requirement", "citation", "count", "ordering"}
)

# Aggregation strategies, per tier1_ingestion.md section 10. Each declares the
# scale its scores live on, because scores across different scales are not
# comparable and a declared scale makes that a machine-checkable fact rather
# than a convention someone has to remember.
#
# Adding a strategy is an entry here plus an implementation registered by name,
# never a schema change (A12).
_AGGREGATION_SCALES: Final[dict[str, str]] = {
    "weighted_mean": "continuous_1_5",
    "unweighted_mean": "continuous_1_5",
    "min": "continuous_1_5",
    "all_must_pass": "verdict_only",
    "threshold_count": "count_of_n",
}

# Windows reserves these as device names. A directory cannot take one, whatever
# its extension, so an identifier that becomes a path segment must not either.
# Screened at ingest because the failure otherwise arrives far from its cause,
# on one platform only. See DESIGN.md section 5.0 and A18.
_WINDOWS_RESERVED_NAMES: Final[frozenset[str]] = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{digit}" for digit in range(1, 10)}
    | {f"lpt{digit}" for digit in range(1, 10)}
)


def priority_condition_level(condition_id: str) -> Optional[int]:
    """Return the priority level a registered condition justifies.

    Args:
        condition_id (str): A condition identifier such as ``P1_ATTRIBUTION``.

    Returns:
        Optional[int]: The level in 0 to 4, or ``None`` when the identifier is
        not registered. ``None`` is a defect in the caller's data rather than an
        ordinary outcome, and callers are expected to reject it.
    """
    return _PRIORITY_CONDITIONS.get(condition_id)


def registered_priority_conditions() -> frozenset[str]:
    """Return every registered priority condition identifier.

    Returns:
        frozenset[str]: The identifiers, as an immutable set so that a caller
        cannot mutate the registry through the value it was handed.
    """
    return frozenset(_PRIORITY_CONDITIONS)


def is_registered_data_code(taxonomy_code: str) -> bool:
    """Report whether an ingestion diagnostic code is registered.

    Args:
        taxonomy_code (str): A code such as ``QC_DATA_UNKNOWN_FIELD``.

    Returns:
        bool: True when the code appears in the registry.
    """
    return taxonomy_code in _DATA_CODES


def data_code_severity(taxonomy_code: str) -> Optional[str]:
    """Return the severity declared for an ingestion diagnostic code.

    Args:
        taxonomy_code (str): A code such as ``QC_DATA_WHITESPACE_STRIPPED``.

    Returns:
        Optional[str]: ``INFO``, ``WARNING`` or ``ERROR``, or ``None`` when the
        code is not registered.
    """
    return _DATA_CODES.get(taxonomy_code)


def aggregation_scale(strategy: str) -> Optional[str]:
    """Return the scale identifier a registered aggregation strategy declares.

    Args:
        strategy (str): A strategy name such as ``weighted_mean``.

    Returns:
        Optional[str]: The ``scale_id``, or ``None`` when the strategy is not
        registered. Unlike a constraint kind, an unregistered strategy is an
        error rather than an open-vocabulary entry: nothing could aggregate
        against it, and a score with no declared scale cannot be compared with
        anything.
    """
    return _AGGREGATION_SCALES.get(strategy)


def registered_aggregation_strategies() -> frozenset[str]:
    """Return every registered aggregation strategy name.

    Returns:
        frozenset[str]: The names, immutable so a caller cannot mutate the
        registry through the value it was handed.
    """
    return frozenset(_AGGREGATION_SCALES)


def scores_are_comparable(first_strategy: str, second_strategy: str) -> bool:
    """Report whether two strategies produce scores that may be compared.

    Two rubrics aggregating on different scales produce numbers that look
    comparable and are not. Reporting compares **verdicts** across rubrics and
    **scores** only within a matching scale.

    Args:
        first_strategy (str): One strategy name.
        second_strategy (str): The other strategy name.

    Returns:
        bool: True when both are registered and declare the same scale. An
        unregistered strategy yields False rather than raising, because the
        caller asking this question wants an answer rather than an exception.
    """
    first_scale = aggregation_scale(first_strategy)
    second_scale = aggregation_scale(second_strategy)
    return first_scale is not None and first_scale == second_scale


def is_registered_harness_code(taxonomy_code: str) -> bool:
    """Report whether a harness failure code is registered.

    Args:
        taxonomy_code (str): A code such as ``QC_HARNESS_RATE_LIMIT``.

    Returns:
        bool: True when the code appears in the registry.
    """
    return taxonomy_code in _HARNESS_CODES


# The model-quality family, from test_taxonomy.md section 6.1. Registered here
# so a code emitted by Tier 3 can be checked rather than trusted. The family is
# deliberately wide: a code's presence, a set of codes and their severity
# together drive fix prioritization, so merging two signals to shorten the list
# would discard the distinction that makes either useful.
_LLM_CODES: Final[frozenset[str]] = frozenset({
    "QC_LLM_NO_OUTPUT",
    "QC_LLM_SCHEMA_VIOLATION",
    "QC_LLM_INSTRUCTION_DRIFT",
    "QC_LLM_FORMAT_VIOLATION",
    "QC_LLM_LENGTH_VIOLATION",
    "QC_LLM_CONTEXT_OMISSION",
    "QC_LLM_RUBRIC_FAILURE",
    "QC_LLM_HALLUCINATION",
    "QC_LLM_OVER_DISCLOSURE",
    "QC_LLM_SOURCE_ALTERATION",
    "QC_LLM_UNSOURCED_CLAIM",
    "QC_LLM_TOOL_VIOLATION",
    "QC_LLM_INJECTION_SUSCEPTIBLE",
    "QC_LLM_PROMPT_LEAKAGE",
    "QC_LLM_GOAL_HIJACK",
    "QC_LLM_AMBIGUITY_UNHANDLED",
    "QC_LLM_OVER_CLARIFICATION",
    # Added 2026-09-23. The requirement_match family reads its inputs correctly
    # and applies the wrong rule to them, which no registered code described.
    "QC_LLM_MATCH_MISCOMPUTED",
    # The mirror of a hallucinated defect: one invents what is not there, this
    # omits what is. A recall figure needs both directions to mean anything.
    "QC_LLM_DEFECT_MISSED",
    # REGISTERED 2026-09-26, AFTER BEING EMITTED FOR DAYS. `consistent()` in the
    # consumer's `graded_support.py` has raised this code since A4.1 introduced
    # repeat observations, and it was never registered here: the emit-site check
    # runs inside this repository and the emit site is in the other one.
    #
    # IT IS `QC_LLM_*` RATHER THAN `QC_HARNESS_*` because nothing about our
    # infrastructure varied. Same request, same engine, same commit, different
    # answer: that is a property of the model (design section 4.9.1).
    "QC_LLM_INCONSISTENT",
})

# The security family, from test_taxonomy.md section 6.4. A security finding is
# neither a measure of task quality nor a harness defect; it is a third thing
# with different escalation, and it stays visible independently of quality
# scores (A5a).
_SEC_CODES: Final[frozenset[str]] = frozenset({
    "QC_SEC_INJECTION_ATTEMPT",
    "QC_SEC_JUDGE_HIJACK",
    "QC_SEC_CREDENTIAL_LEAK",
})


def is_registered_llm_code(taxonomy_code: str) -> bool:
    """Report whether a code is a registered model-quality finding.

    Args:
        taxonomy_code (str): A code such as ``QC_LLM_RUBRIC_FAILURE``.

    Returns:
        bool: True when registered.
    """
    return taxonomy_code in _LLM_CODES


def is_registered_sec_code(taxonomy_code: str) -> bool:
    """Report whether a code is a registered security finding.

    Args:
        taxonomy_code (str): A code such as ``QC_SEC_JUDGE_HIJACK``.

    Returns:
        bool: True when registered.
    """
    return taxonomy_code in _SEC_CODES


def registered_codes() -> frozenset[str]:
    """Return every registered code across all four families.

    **The four families split by what the code asserts about**, never by
    severity, so one function returning all of them is a lookup rather than a
    flattening of a meaningful distinction.

    Returns:
        frozenset[str]: Every registered code.
    """
    return frozenset(_LLM_CODES | _SEC_CODES | _HARNESS_CODES | frozenset(_DATA_CODES))


@dataclass(frozen=True)
class EvaluationFamily:
    """One registered evaluation family, with its admission criterion.

    Families apply to **graded cases only**. A precondition tests the harness,
    which performs no task, so a precondition carries no family.

    Attributes:
        identifier (str): Lowercase snake case, naming the **task** rather than
            the subject matter: ``code_comprehension``, not ``python_bugs``.
        input_shape (str): What the model is given.
        ground_truth (str): **The admission criterion, not a description.** A
            family gradable only by rubric is refused: it adds cases without
            adding confidence, because it measures the judge as much as the
            candidate.
    """

    identifier: str
    input_shape: str
    ground_truth: str


_EVALUATION_FAMILIES: Final[dict[str, EvaluationFamily]] = {
    "requirement_match": EvaluationFamily(
        identifier="requirement_match",
        input_shape="Resume material and a job posting's requirements",
        ground_truth="Provided source material, making invention a set operation",
    ),
    "output_shape": EvaluationFamily(
        identifier="output_shape",
        input_shape="Any content plus declared shape constraints",
        ground_truth="Parsers and counters applied to the response",
    ),
    "code_comprehension": EvaluationFamily(
        identifier="code_comprehension",
        input_shape="A code excerpt carrying a known defect",
        ground_truth="A parser for syntactic defects, execution for logical ones",
    ),
}


def registered_evaluation_families() -> frozenset[str]:
    """Return every registered family identifier.

    Returns:
        frozenset[str]: The identifiers, immutable so a caller cannot mutate
        the registry through the value it was handed.
    """
    return frozenset(_EVALUATION_FAMILIES)


def evaluation_family(identifier: str) -> Optional[EvaluationFamily]:
    """Return one family's registration.

    Args:
        identifier (str): The family identifier.

    Returns:
        Optional[EvaluationFamily]: Its registration, or ``None`` when
        unregistered.
    """
    return _EVALUATION_FAMILIES.get(identifier)


def register_evaluation_family(family: EvaluationFamily) -> EvaluationFamily:
    """Register a family, refusing one with no ground-truth mechanism.

    Args:
        family (EvaluationFamily): The family to register.

    Returns:
        EvaluationFamily: The same record.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the identifier is
            taken, or when no ground-truth mechanism is stated. **The second is
            the admission criterion**: a family gradable only by rubric adds
            cases without adding confidence, and refusing it at registration is
            what keeps that a rule rather than an intention.
    """
    if family.identifier in _EVALUATION_FAMILIES:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: family {family.identifier!r} is already registered"
        )
    if not family.ground_truth.strip():
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: family {family.identifier!r} states no ground-truth "
            f"mechanism, so it could only be graded by rubric and would measure the judge "
            f"as much as the candidate"
        )
    _EVALUATION_FAMILIES[family.identifier] = family
    return family


def unregister_evaluation_family(identifier: str) -> None:
    """Remove a registered family.

    Exists for the extension cases, which register a family and must leave the
    registry as they found it.

    Args:
        identifier (str): The identifier to remove.

    Returns:
        None
    """
    _EVALUATION_FAMILIES.pop(identifier, None)


def is_adapter_error_code(taxonomy_code: str) -> bool:
    """Report whether an adapter may return this code from ``map_error``.

    The adapter set is narrower than the harness family. A fixture code comes
    from the replay store and a dependency code from the runner, and an adapter
    returning either would be reporting on something outside its view.

    Args:
        taxonomy_code (str): A code such as ``QC_HARNESS_AUTH_ERROR``.

    Returns:
        bool: True when an adapter is permitted to return it.
    """
    return taxonomy_code in _ADAPTER_ERROR_CODES


def is_registered_constraint_kind(kind: str) -> bool:
    """Report whether a constraint kind belongs to the registered core.

    Args:
        kind (str): A kind such as ``prohibition``.

    Returns:
        bool: True when registered. False is **not** an error: the vocabulary is
        open, and the caller warns rather than rejecting.
    """
    return kind in _CONSTRAINT_KINDS


def is_windows_reserved_name(candidate: str) -> bool:
    """Report whether a name collides with a Windows reserved device name.

    The comparison ignores letter case and any extension, matching the operating
    system's own rule: ``nul``, ``NUL`` and ``nul.json`` are all refused.

    Args:
        candidate (str): A name that will become a path segment.

    Returns:
        bool: True when the name cannot be used as a directory or file on
        Windows, and therefore must not be used on any supported platform.
    """
    stem = candidate.split(".", maxsplit=1)[0].strip().lower()
    return stem in _WINDOWS_RESERVED_NAMES


# WHAT AN HTTP STATUS MEANS, which is not a property of any vendor. A 302 says
# the same thing whoever returned it, so this is one table rather than one per
# adapter, and every interface that needs it calls the same function: candidate
# dispatch, judge dispatch and anything added later.
#
# AN ADAPTER STILL OWNS WHAT IS GENUINELY ITS OWN: which exception class its
# SDK raises for a timeout, and how it exposes the status. It does not own what
# the number means.
_STATUS_CODES: Final[dict[int, str]] = {
    # A REDIRECT THE CLIENT DID NOT FOLLOW says the engine was not where we
    # addressed it. A corporate proxy or captive portal answering with a login
    # page is the ordinary cause, and following such a hop blindly is how a
    # login page gets scored as a model response.
    300: "QC_HARNESS_ENGINE_UNREACHABLE",
    301: "QC_HARNESS_ENGINE_UNREACHABLE",
    302: "QC_HARNESS_ENGINE_UNREACHABLE",
    303: "QC_HARNESS_ENGINE_UNREACHABLE",
    305: "QC_HARNESS_ENGINE_UNREACHABLE",
    306: "QC_HARNESS_ENGINE_UNREACHABLE",
    307: "QC_HARNESS_ENGINE_UNREACHABLE",
    308: "QC_HARNESS_ENGINE_UNREACHABLE",
    # OURS, AND ANTICIPATED.
    400: "QC_HARNESS_REQUEST_REJECTED",
    401: "QC_HARNESS_AUTH_ERROR",
    403: "QC_HARNESS_AUTH_ERROR",
    404: "QC_HARNESS_VERSION_UNAVAILABLE",
    # THE BALANCE IS EMPTY, and that is not an authentication failure. Gemini
    # returns this when prepay credits reach zero, at which point every key on
    # the billing account stops at once. Mapping it to the auth code would send
    # a reader to rotate a credential that is working perfectly;
    # `.env.example` already makes the same distinction in prose.
    #
    # ENVIRONMENTAL, LIKE THE NO-CREDIT VARIANT OF 429 (section 8.6), so no
    # retry reaches it: the remedy is money, which no run can supply.
    402: "QC_HARNESS_CREDIT_EXHAUSTED",
    # NOBODY'S DEFECT: the request was well formed and we asked too often.
    429: "QC_HARNESS_RATE_LIMIT",
    # THE SERVICE ITSELF, saying it cannot serve.
    500: "QC_HARNESS_PROVIDER_UNAVAILABLE",
    503: "QC_HARNESS_PROVIDER_UNAVAILABLE",
    # A GATEWAY, which may be a proxy, a CDN or an egress rule and need not be
    # the provider at all. The body of a 502 is the intermediary's.
    502: "QC_HARNESS_GATEWAY_FAILURE",
    504: "QC_HARNESS_GATEWAY_FAILURE",
}


def taxonomy_for_status(status: Any) -> Optional[str]:
    """Return the harness code an HTTP status maps to.

    **One implementation, several callers**, which is the arrangement
    `consumer_ci.md` section 5 gives for every shared rule: a rule enforced
    differently in two places is a defect that ships. Candidate dispatch and
    judge dispatch reach the same answer because they ask the same function.

    Args:
        status (Any): The status an exception carried, of any type. **Not
            required to be an integer**, because SDKs differ in what they put
            in that attribute and a caller should not have to check first.

    Returns:
        Optional[str]: The code, or ``None`` when the status is unmapped or is
        not a status at all. **None rather than a default**, so an unmapped
        number falls through to the caller's own unanticipated-failure path
        and stays visible.
    """
    if isinstance(status, bool) or not isinstance(status, int):
        return None
    return _STATUS_CODES.get(status)


def registered_statuses() -> frozenset[int]:
    """Return every HTTP status the harness maps.

    Returns:
        frozenset[int]: The statuses, so a case can assert coverage without a
        second copy of the list.
    """
    return frozenset(_STATUS_CODES)
