# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The layer registry, and the outcome registry the verdict reads denominators from.

Specified by ``docs/design/cmn_verdict_and_cli.md`` section 9 and
``docs/design/test_taxonomy.md`` sections 2 and 9.

**Layer semantics are read, never hardcoded.** The verdict function asks a layer
whether it is graded and whether it is exempt from the distribution ceilings
rather than naming ``UNI``, ``SYS`` or ``SEC``. Registering a layer must not
require editing the function deciding every run's outcome, because a regression
there would misreport every existing test rather than only the new one.

**An outcome declares its denominator treatment before it can be registered.**
All three answers are required: pass rate, skip rate, distribution. An outcome
that cannot answer all three would have the verdict function silently choose a
default, and that default would be wrong somewhere.

**Preconditions carry no priority because they sit above the scale**, not below
it. Every one is unconditionally blocking: a failure stops the graded layers
executing, the run exits 3, and nothing is measured. That is a stronger
consequence than any level inside the scale can express.
"""

import logging
from dataclasses import dataclass
from typing import Final, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LayerProperties:
    """What the verdict function needs to know about a layer.

    Attributes:
        layer (str): The uppercase token, such as ``UNI``.
        marker (str): The pytest marker selecting it.
        graded (bool): Whether the layer measures the model. A precondition
            tests our harness, so a failure is our defect.
        distribution_exempt (bool): Whether its cases are excluded from the
            priority distribution ceilings. **Security coverage does not compete
            with functional coverage for a budget**: a ceiling exists to prevent
            priority inflation, and a security test going unwritten because the
            P0 quota was full is the ceiling doing harm.
        blocking (bool): Whether a failure stops the graded layers executing.
        id_block (tuple): The inclusive identifier range reserved for it.
    """

    layer: str
    marker: str
    graded: bool
    distribution_exempt: bool
    blocking: bool
    id_block: tuple[int, int]

    @property
    def carries_priority(self) -> bool:
        """Report whether a case in this layer must declare a priority.

        Returns:
            bool: True for graded layers only. A precondition carries none
            because the marker is a **budget** device and a budget only exists
            where claims compete. Preconditions do not compete: all are
            mandatory.
        """
        return self.graded


_LAYERS: Final[dict[str, LayerProperties]] = {
    "UNI": LayerProperties("UNI", "unit", False, True, True, (110000, 119999)),
    "SYS": LayerProperties("SYS", "system", False, True, True, (120000, 129999)),
    "EVAL": LayerProperties("EVAL", "evaluator", True, False, False, (130000, 139999)),
    "TOOL": LayerProperties("TOOL", "tool", True, False, False, (140000, 149999)),
    "SEC": LayerProperties("SEC", "sec", True, True, False, (150000, 159999)),
}


@dataclass(frozen=True)
class OutcomeProperties:
    """How one outcome is counted in each denominator.

    **All three are required.** An outcome registered without them would have
    the verdict function choose a default, and a default that is right for the
    pass rate is wrong for the skip rate.

    Attributes:
        outcome (str): ``pass``, ``fail``, ``broken`` or ``skip``.
        counts_in_pass_rate (bool): Whether it enters the V2 denominator.
        is_pass (bool): Whether it counts as a passing execution.
        counts_in_skip_rate (bool): Whether it enters the V3 and V4 numerator.
        counts_in_distribution (bool): Whether it enters the distribution
            denominator, which counts case definitions rather than executions.
    """

    outcome: str
    counts_in_pass_rate: bool
    is_pass: bool
    counts_in_skip_rate: bool
    counts_in_distribution: bool


_OUTCOMES: Final[dict[str, OutcomeProperties]] = {
    "pass": OutcomeProperties("pass", True, True, False, True),
    "fail": OutcomeProperties("fail", True, False, False, True),
    # BROKEN MEANS OUR INFRASTRUCTURE FAILED, so it is not a model finding and
    # it is OUT of the pass-rate denominator. Leaving it in made harness
    # flakiness read as model degradation in the headline number, and enough of
    # it pulled the rate under the V2 floor as though the model had got worse.
    #
    # It is not tolerated instead of counted: broken means something needs a
    # fix, so any broken observation blocks the run through the soundness check
    # in verdict.py, which exits 3 rather than 1.
    "broken": OutcomeProperties("broken", False, False, False, True),
    # A skip produced no measurement, so it cannot count toward a pass rate
    # computed over executions. Which skips reach the skip numerator at all is
    # decided by the skip reason, not by this flag.
    "skip": OutcomeProperties("skip", False, False, True, True),
}

# Skip reasons excluded from the skip denominator entirely, with why.
#
# A foundational failure cascades into many dependency skips. Counting them
# would breach V3 as well, adding a derived failure on top of the real one and
# misdirecting diagnosis toward the environment, when the run is already red
# from V1.
#
# A declared capability gap is not an environmental failure, and leaving it in
# the denominator would trip V3 for a reason that is not a defect (A13).
_EXCLUDED_SKIP_REASONS: Final[frozenset[str]] = frozenset({"dependency", "unsupported"})

_SKIP_REASONS: Final[frozenset[str]] = frozenset(
    {"environmental", "dependency", "unsupported", "incomplete"}
)

# A SKIP IS NOT ONE THING, AND THE REASON SAYS WHICH. A provider outage and an
# unwritten case are both skips and they are not the same event.
#
# `incomplete` was added 2026-09-24 because an unwritten case had no reason of
# its own and took `unsupported`, which is EXCLUDED from the denominator
# entirely. Unfinished work was therefore the most tolerated skip in the
# system, and the one thing that must never merge was the one thing no ceiling
# could see.
_BLOCKING_SKIP_REASONS: Final[frozenset[str]] = frozenset({"incomplete"})


def layer_properties(layer: str) -> LayerProperties:
    """Return one layer's declared properties.

    Args:
        layer (str): The layer token.

    Returns:
        LayerProperties: Its registration.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the layer is not
            registered. Defaulting to graded or to ungraded would both be wrong
            somewhere, and a silent default here changes a run's verdict.
    """
    properties = _LAYERS.get(layer)
    if properties is None:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: layer {layer!r} is not registered; "
            f"registered layers are {registered_layers()}"
        )
    return properties


def registered_layers() -> list[str]:
    """Return every registered layer token.

    Returns:
        list[str]: The tokens, sorted so output does not depend on mapping
        order.
    """
    return sorted(_LAYERS)


def register_layer(properties: LayerProperties) -> LayerProperties:
    """Register a new layer.

    Adding a layer must not require editing verdict computation, which is what
    the declared properties on this record exist to make true.

    Args:
        properties (LayerProperties): The layer to register.

    Returns:
        LayerProperties: The same record.

    Raises:
        ValueError: When the token is taken, or the identifier block overlaps
            one already registered. **Overlapping blocks would let two layers
            claim one identifier**, and identifiers are assigned once and never
            reused precisely so history cannot silently rebind.
    """
    if properties.layer in _LAYERS:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: layer {properties.layer!r} is already registered"
        )
    low, high = properties.id_block
    for existing in _LAYERS.values():
        if low <= existing.id_block[1] and existing.id_block[0] <= high:
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: the block {properties.id_block} for "
                f"{properties.layer!r} overlaps {existing.layer!r} at {existing.id_block}"
            )
    _LAYERS[properties.layer] = properties
    return properties


def unregister_layer(layer: str) -> None:
    """Remove a registered layer.

    Exists for the extension cases, which register a layer and must leave the
    registry as they found it. A test that registered a layer permanently would
    change the distribution denominator for every case that ran after it.

    Args:
        layer (str): The token to remove.

    Returns:
        None
    """
    _LAYERS.pop(layer, None)


def outcome_properties(outcome: str) -> OutcomeProperties:
    """Return one outcome's declared denominator treatment.

    Args:
        outcome (str): The outcome name.

    Returns:
        OutcomeProperties: Its registration.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the outcome is not
            registered, or is registered without declaring all three
            treatments.
    """
    properties = _OUTCOMES.get(outcome)
    if properties is None:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: outcome {outcome!r} is not registered; "
            f"registered outcomes are {registered_outcomes()}"
        )
    return properties


def registered_outcomes() -> list[str]:
    """Return every registered outcome name.

    Returns:
        list[str]: The names, sorted.
    """
    return sorted(_OUTCOMES)


def register_outcome(properties: OutcomeProperties) -> OutcomeProperties:
    """Register a new outcome, which must declare every denominator treatment.

    Args:
        properties (OutcomeProperties): The outcome to register.

    Returns:
        OutcomeProperties: The same record.

    Raises:
        ValueError: When the name is taken, or any treatment is undeclared.
    """
    if properties.outcome in _OUTCOMES:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: outcome {properties.outcome!r} is already registered"
        )
    _OUTCOMES[properties.outcome] = properties
    return properties


def unregister_outcome(outcome: str) -> None:
    """Remove a registered outcome.

    Args:
        outcome (str): The name to remove.

    Returns:
        None
    """
    _OUTCOMES.pop(outcome, None)


def require_denominator_declaration(declaration: dict[str, object]) -> OutcomeProperties:
    """Build an outcome registration, refusing an incomplete declaration.

    Args:
        declaration (dict): The proposed registration, which must name the
            outcome and all three denominator treatments.

    Returns:
        OutcomeProperties: The validated registration.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` naming every treatment
            that was not declared. **Silence is not a declaration**: an outcome
            that does not say how it is counted would be counted by a default
            nobody chose.
    """
    required = (
        "outcome", "counts_in_pass_rate", "is_pass",
        "counts_in_skip_rate", "counts_in_distribution",
    )
    missing = [name for name in required if name not in declaration]
    if missing:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: an outcome registration must declare its "
            f"treatment in every denominator; {', '.join(missing)} not declared"
        )
    return OutcomeProperties(
        outcome=str(declaration["outcome"]),
        counts_in_pass_rate=bool(declaration["counts_in_pass_rate"]),
        is_pass=bool(declaration["is_pass"]),
        counts_in_skip_rate=bool(declaration["counts_in_skip_rate"]),
        counts_in_distribution=bool(declaration["counts_in_distribution"]),
    )


def skip_counts_toward_rate(skip_reason: Optional[str]) -> bool:
    """Report whether one skip enters the skip-rate numerator.

    Args:
        skip_reason (Optional[str]): Why the case skipped.

    Returns:
        bool: False for a dependency skip or an unsupported pair. Neither is an
        environmental failure, and counting them would add a derived breach on
        top of a real one.
    """
    return skip_reason not in _EXCLUDED_SKIP_REASONS


def registered_skip_reasons() -> frozenset[str]:
    """Return every registered skip reason.

    Returns:
        frozenset[str]: The three reasons, which are counted differently (A13).
    """
    return _SKIP_REASONS


def is_registered_skip_reason(skip_reason: str) -> bool:
    """Report whether a skip reason is registered.

    Args:
        skip_reason (str): The reason to check.

    Returns:
        bool: True when registered.
    """
    return skip_reason in _SKIP_REASONS


def skip_blocks(skip_reason: Optional[str]) -> bool:
    """Report whether a skip fails the run outright.

    Args:
        skip_reason (Optional[str]): Why the case skipped.

    Returns:
        bool: True for a reason meaning the work is unfinished. **No ceiling
        applies to these**, because tolerating a proportion of unfinished work
        is tolerating unfinished work.
    """
    return skip_reason in _BLOCKING_SKIP_REASONS
