# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""What the record says when a case belongs to more than one family.

Covers ``MQC_CMN_UNI_112241`` and ``112243``, inventoried in
``docs/design/cmn_verdict_and_cli.md`` section 10 and designed in
``test_taxonomy.md`` section 11.7.

**Written 2026-10-03, when the relation was stated to be many to many.** The
matrix column had been a semicolon-separated set since it was introduced and
three rows used it, while the durable record held a single value: a case traced
to two families could publish only one of them, and nothing said which.

A failure here is our defect, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

import pytest

from cmn.metadata import emit_result
from cmn.observations import Observation, RunContext

pytestmark = pytest.mark.unit


def _graded(**overrides: object) -> Observation:
    """Return a graded observation, with fields replaced.

    Args:
        **overrides (object): Fields to set on it.

    Returns:
        Observation: A graded observation carrying a priority and a condition,
        since a graded case without one cannot be gated.
    """
    fields: dict[str, object] = {
        "case_id": "MQC_TASK_a::MQC_RULE_r",
        "layer": "EVAL",
        "outcome": "pass",
        "priority": 2,
        "priority_conditions": ["P2_DOCUMENTED_BEHAVIOUR"],
    }
    fields.update(overrides)
    return Observation(**fields)  # type: ignore[arg-type]


class TestMQCSeveralFamilies:
    """A complex case addresses more than one, and one of them is primary."""

    def MQC_CMN_UNI_112241_a_case_in_two_families_publishes_both(self) -> None:
        """Both families reach the record, in order, with the primary named.

        **The ordering is the claim and the derived field is what guards it.**
        A semicolon-separated cell, a serialization round trip or a maintainer
        alphabetizing a list all keep the set and lose the order, and nothing
        downstream could detect it: every value would still be registered and
        would still match the row's cases. So primacy is published rather than
        left to position, and this compares the two.

        The reversed pair is asserted as well. Publishing the set alone would
        pass a check that only looked for both values present, which is the
        shape of a case that cannot fail for the reason it exists.

        Design: ``test_taxonomy.md`` section 11.7.2.1.

        Returns:
            None
        """
        run = RunContext(
            run_context="ci", selection_mode="full", preconditions_executed=True,
        )
        pair = ("injection_resistance", "output_shape")

        emitted = emit_result(_graded(families=pair), run)

        assert emitted["families"] == list(pair), (
            "the record dropped a family the case belongs to, so an artifact "
            "would disagree with the matrix that traced it"
        )
        assert emitted["primary_family"] == "injection_resistance"

        # REVERSED, so the order is established to carry meaning rather than
        # being whatever the fixture happened to spell.
        reversed_emission = emit_result(_graded(families=pair[::-1]), run)

        assert reversed_emission["families"] == list(pair[::-1])
        assert reversed_emission["primary_family"] == "output_shape", (
            "the primary was read from something other than the first value, "
            "so reordering the set would not change what it reports"
        )

    def MQC_CMN_UNI_112243_a_repeated_family_value_is_reported(self) -> None:
        """A duplicate makes the primary ambiguous and double-counts the case.

        Both consequences are real rather than tidiness. A per-family cost
        total sums a case once per family it names, so a repeat bills it twice
        against one family and overstates what dropping that family would
        save.

        **An unregistered value in second position is refused too**, which the
        per-value check is for: validating the first alone would let the second
        reach the record unresolvable.

        Design: ``test_taxonomy.md`` section 11.7.2.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="repeats a family"):
            _graded(families=("output_shape", "output_shape"))

        with pytest.raises(ValueError, match="are not registered"):
            _graded(families=("output_shape", "invented_family"))

        # AND A PRECONDITION CARRIES NONE, whatever the count. The layer
        # performs no task, so there is no family to be primary.
        with pytest.raises(ValueError, match="performs no task"):
            Observation(
                case_id="MQC_TASK_pre::MQC_RULE_pre", layer="UNI", outcome="pass",
                families=("output_shape",),
            )
