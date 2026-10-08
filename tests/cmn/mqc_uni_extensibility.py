# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for adding a layer, an outcome or a verdict rule.

Covers `MQC_CMN_UNI_112100`, `112101` and `112106` through `112109`, inventoried in
``docs/design/cmn_verdict_and_cli.md`` section 10.

**Adding a test type must not require editing verdict computation.** A
regression in the function deciding every run's outcome would misreport results
for every existing test, not only the new one, which is why layer semantics are
read from registration and verdict rules are a registry.

Each case here registers something and removes it again. A test that left a
layer registered would change the distribution denominator for every case that
ran after it, and the failure would land on whichever case happened to run last.

A failure here is **not a model finding**, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

from datetime import date
from pathlib import Path
from typing import Any, Iterator

import pytest

from cmn.code_standards import identifier_block_problems
from cmn.config import unrostered_adapters
from cmn.demotion import DemotionCandidate, count_demoted, demotion_order, exceeds_ceiling
from cmn.layers import (
    LayerProperties,
    OutcomeProperties,
    register_layer,
    register_outcome,
    require_denominator_declaration,
    unregister_layer,
    unregister_outcome,
)
from cmn.observations import Observation
from cmn.verdict import (
    Thresholds,
    VerdictConfig,
    evaluate_distribution,
    register_verdict_rule,
    registered_verdict_rules,
    unregister_verdict_rule,
    verdict,
)
from execution.adapters.registry import registered_engines

pytestmark = pytest.mark.unit

# The date the roster's declared absences are judged against. Injected
# rather than read from the clock, so a lapse is testable at its boundary.
_AS_OF = date(2026, 10, 2)

# This repository's root, two levels above a case module.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

_TODAY = date(2026, 9, 23)


@pytest.fixture(name="extra_layer")
def fixture_extra_layer() -> Iterator[LayerProperties]:
    """Register a graded layer and remove it afterwards.

    Yields:
        LayerProperties: The registered layer.
    """
    properties = LayerProperties(
        layer="PERF", marker="perf", graded=True,
        distribution_exempt=False, blocking=False, id_block=(60001, 69999),
    )
    register_layer(properties)
    yield properties
    unregister_layer(properties.layer)


class TestMQCLayerRegistration:
    """What a newly registered layer inherits without a code change."""

    def MQC_CMN_UNI_112106_new_layer_respects_declared_graded_flag(
        self,
        extra_layer: LayerProperties,
    ) -> None:
        """The verdict reads graded status from registration, not from the name.

        A function naming the layers it knows would treat an unfamiliar one as
        whichever branch it fell through to, and that default would be wrong
        for half the layers anyone might add.

        Args:
            extra_layer (LayerProperties): The registered layer.

        Returns:
            None
        """
        observations = [
            Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass"),
            Observation("MQC_TASK_x::MQC_RULE_r", extra_layer.layer, "fail", priority=0),
        ]
        result = verdict(observations, VerdictConfig(), _TODAY)

        assert observations[1].graded is True
        assert "V1" in result.breached_rules
        assert result.exit_code == 1

    def MQC_CMN_UNI_112107_new_layer_respects_declared_distribution_exemption(self) -> None:
        """An exempt layer is excluded by its declaration, not by its name.

        The hand-written security exemption that shipped in the taxonomy is a
        declared property here, so a second exempt layer needs no change to the
        check that reads it.

        Returns:
            None
        """
        exempt = LayerProperties(
            layer="FUZZ", marker="fuzz", graded=True,
            distribution_exempt=True, blocking=False, id_block=(70001, 79999),
        )
        register_layer(exempt)
        try:
            observations = [
                Observation(f"MQC_TASK_{index}::MQC_RULE_r", "EVAL", "pass", priority=3)
                for index in range(40)
            ] + [
                Observation(f"MQC_TASK_f{index}::MQC_RULE_r", "FUZZ", "pass", priority=0)
                for index in range(40)
            ]
            report = evaluate_distribution(observations, Thresholds())
            assert report.case_definitions == 40
            assert report.p0_share == pytest.approx(0.0)
        finally:
            unregister_layer(exempt.layer)

    def MQC_CMN_UNI_112128_an_overlapping_identifier_block_is_rejected(self) -> None:
        """Two layers claiming one identifier would let history rebind it.

        Identifiers are assigned once and never reused, including after a test
        is deleted, precisely so downstream history cannot silently attach an
        identifier to different behaviour.

        Returns:
            None
        """
        # INSIDE UNI'S BLOCK, which the six-digit scheme moved to 110000-119999.
        # The old value sat inside the old UNI block and overlapped nothing
        # afterwards, so the case stopped testing what it names.
        overlapping = LayerProperties(
            layer="DUPE", marker="dupe", graded=True,
            distribution_exempt=False, blocking=False, id_block=(115000, 115100),
        )
        with pytest.raises(ValueError, match="overlaps"):
            register_layer(overlapping)


class TestMQCOutcomeRegistration:
    """An outcome declares its denominator treatment, or it is not registered."""

    def MQC_CMN_UNI_112108_outcome_without_declared_denominator_treatment_is_rejected(
        self,
    ) -> None:
        """All three answers are required, and silence is not a declaration.

        An outcome that does not say how it is counted would be counted by a
        default nobody chose, and a default that is right for the pass rate is
        wrong for the skip rate.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR") as caught:
            require_denominator_declaration(
                {"outcome": "deferred", "counts_in_pass_rate": False}
            )
        message = str(caught.value)
        assert "is_pass" in message
        assert "counts_in_skip_rate" in message
        assert "counts_in_distribution" in message

    def MQC_CMN_UNI_112129_a_complete_declaration_registers_and_is_read(self) -> None:
        """The positive the rejection is measured against.

        Returns:
            None
        """
        declared = require_denominator_declaration({
            "outcome": "deferred", "counts_in_pass_rate": False, "is_pass": False,
            "counts_in_skip_rate": True, "counts_in_distribution": True,
        })
        register_outcome(declared)
        try:
            assert isinstance(declared, OutcomeProperties)
            observation = Observation("MQC_TASK_x::MQC_RULE_r", "EVAL", "deferred",
                                      priority=3)
            assert observation.passed is False
        finally:
            unregister_outcome("deferred")


class TestMQCVerdictRuleRegistration:
    """A new gating condition is a registry entry, never an edit."""

    def MQC_CMN_UNI_112109_registered_verdict_rule_is_evaluated_without_core_change(self) -> None:
        """The rule is evaluated and its breach reported under its own identifier.

        Returns:
            None
        """
        @register_verdict_rule("V99")
        def _always_fires(population: Any, config: Any, as_of: date) -> None:
            """Fire whenever any graded observation exists.

            Args:
                population: The split observation sets.
                config: Unused.
                as_of: Unused.

            Returns:
                tuple: Whether it fired, and why.
            """
            del config, as_of
            return bool(population.graded), "a registered rule fired without a core change"

        try:
            observations = [
                Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass"),
                Observation("MQC_TASK_x::MQC_RULE_r", "EVAL", "pass", priority=3),
            ]
            result = verdict(observations, VerdictConfig(), _TODAY)
            assert "V99" in result.breached_rules
            assert result.green is False
        finally:
            unregister_verdict_rule("V99")

        assert "V99" not in [
            getattr(rule, "rule_id", "") for rule in registered_verdict_rules()
        ]


class TestMQCDemotionOrdering:
    """Which case gives way when a ceiling binds, and which never does."""

    def MQC_CMN_UNI_112100_demotion_orders_single_match_before_multiple(self) -> None:
        """Match count is claim strength, which makes the order mechanical.

        A case satisfying three conditions at or above its level has a
        materially better claim than one qualifying on a single condition, so
        the weaker claim gives way first rather than the argument being had
        again each time a ceiling binds.

        Returns:
            None
        """
        weak = DemotionCandidate(
            "MQC_TASK_weak::MQC_RULE_r", "EVAL", 1, ["P1_ATTRIBUTION"]
        )
        strong = DemotionCandidate(
            "MQC_TASK_strong::MQC_RULE_r", "EVAL", 1,
            ["P1_ATTRIBUTION", "P1_TOOL_COMPLIANCE", "P0_RUN_INTEGRITY"],
        )

        ordered = demotion_order([strong, weak])
        assert [entry.case_id for entry in ordered] == [
            "MQC_TASK_weak::MQC_RULE_r", "MQC_TASK_strong::MQC_RULE_r"
        ]
        assert weak.claim_strength == 1
        assert strong.claim_strength == 3

    def MQC_CMN_UNI_112101_security_cases_are_never_demoted(self) -> None:
        """Excluded entirely, never merely ordered last.

        Appearing at the end of a list is one budget change away from being
        demoted. Security coverage does not compete for the budget at all, so
        it is not in the list.

        Returns:
            None
        """
        security = DemotionCandidate(
            "MQC_TASK_sec::MQC_RULE_r", "SEC", 0, ["P0_SAFETY_CRITICAL_MODEL"]
        )
        functional = DemotionCandidate(
            "MQC_TASK_fn::MQC_RULE_r", "EVAL", 1, ["P1_ATTRIBUTION"]
        )

        ordered = demotion_order([security, functional])
        assert [entry.case_id for entry in ordered] == ["MQC_TASK_fn::MQC_RULE_r"]
        assert security.demotable is False

    def MQC_CMN_UNI_112130_a_case_below_its_ceiling_is_detectable_from_its_record(self) -> None:
        """Nothing extra has to be stored to see that a case was demoted.

        A priority below the most severe matched condition is exactly what
        demotion produces, so the signal is derivable rather than recorded, and
        it cannot fall out of step with the assignment it describes.

        Returns:
            None
        """
        demoted = DemotionCandidate(
            "MQC_TASK_d::MQC_RULE_r", "EVAL", 2, ["P1_ATTRIBUTION"]
        )
        at_ceiling = DemotionCandidate(
            "MQC_TASK_a::MQC_RULE_r", "EVAL", 1, ["P1_ATTRIBUTION"]
        )

        assert demoted.demoted is True
        assert at_ceiling.demoted is False
        assert count_demoted([demoted, at_ceiling]) == 1

    def MQC_CMN_UNI_112131_a_priority_above_every_matched_condition_is_a_breach(self) -> None:
        """A priority without a named condition is not assignable (G6).

        An unmatched case is a breach rather than an unconstrained one, which
        is the difference between a ceiling and a suggestion.

        Returns:
            None
        """
        overclaimed = DemotionCandidate(
            "MQC_TASK_o::MQC_RULE_r", "EVAL", 0, ["P2_DOCUMENTED_BEHAVIOUR"]
        )
        unmatched = DemotionCandidate("MQC_TASK_u::MQC_RULE_r", "EVAL", 0, [])
        legitimate = DemotionCandidate(
            "MQC_TASK_l::MQC_RULE_r", "EVAL", 0, ["P0_RUN_INTEGRITY"]
        )

        assert exceeds_ceiling(overclaimed) is True
        assert exceeds_ceiling(unmatched) is True
        assert exceeds_ceiling(legitimate) is False


class TestMQCEngineExpansion:
    """Adding an evaluated engine is declarative, and every step is checked."""

    def MQC_CMN_UNI_112145_a_registered_adapter_off_the_roster_is_reported(
        self, tmp_path: Path
    ) -> None:
        """A registered adapter is rostered or carries a dated reason.

        An adapter absent from the roster cannot be selected. That is allowed
        while it is recorded under ``not_rostered`` with a reason and an
        expiry, and reported once the record is missing or has lapsed.

        **The shipped roster is included**, because the gap this covers was
        real: ``grok`` registered, declared its credential variable, and was
        absent from the roster, so the engine could not be selected and nothing
        said so.

        Design: ``extensibility_standard.md`` section 3.4.

        Args:
            tmp_path (Path): For the negative controls.

        Returns:
            None
        """
        shipped = Path(__file__).resolve().parents[2] / "config" / "engines.yaml"
        registered = sorted(registered_engines())

        assert "grok" in registered, (
            "this case reads the shipped adapters and found no grok, so it is "
            "no longer exercising the gap it was written for"
        )
        assert not unrostered_adapters(shipped, registered, _AS_OF), (
            "a registered adapter can neither run nor explain itself: "
            + "; ".join(unrostered_adapters(shipped, registered, _AS_OF))
        )

        # AN ADAPTER NOBODY DECLARED AT ALL, which is what shipping one and
        # forgetting the roster entry looks like.
        roster = tmp_path / "engines.yaml"
        roster.write_text(
            "engines:\n  gemini:\n    model: gemini-3.8-flash\n", encoding="utf-8"
        )
        problems = unrostered_adapters(roster, ["gemini", "mistral"], _AS_OF)

        assert len(problems) == 1
        assert "mistral" in problems[0]
        assert "nothing records why" in problems[0]

        # AN ABSENCE THAT NEVER LAPSES, which is where an adapter goes to be
        # forgotten. The reason alone does not excuse it.
        roster.write_text(
            "engines:\n  gemini:\n    model: gemini-3.8-flash\n"
            "not_rostered:\n  mistral:\n    reason: no fixtures recorded\n",
            encoding="utf-8",
        )
        problems = unrostered_adapters(roster, ["gemini", "mistral"], _AS_OF)

        assert len(problems) == 1
        assert "no expiry date" in problems[0]

        # AND ONE THAT HAS LAPSED, measured against the injected date rather
        # than the clock so the boundary is testable.
        roster.write_text(
            "engines:\n  gemini:\n    model: gemini-3.8-flash\n"
            "not_rostered:\n  mistral:\n    reason: no fixtures recorded\n"
            "    expires_on: 2026-09-30\n",
            encoding="utf-8",
        )
        problems = unrostered_adapters(roster, ["gemini", "mistral"], _AS_OF)

        assert len(problems) == 1
        assert "has passed" in problems[0]

        # A CURRENT EXCUSE REPORTS NOTHING, which is what makes the check a
        # record of decisions rather than a prohibition on shipping an adapter.
        roster.write_text(
            "engines:\n  gemini:\n    model: gemini-3.8-flash\n"
            "not_rostered:\n  mistral:\n    reason: no fixtures recorded\n"
            "    expires_on: 2026-11-30\n",
            encoding="utf-8",
        )
        assert not unrostered_adapters(roster, ["gemini", "mistral"], _AS_OF)


    def MQC_CMN_UNI_112146_an_identifier_outside_its_module_block_is_reported(
        self,
    ) -> None:
        """Every identifier's digits say what its tokens say.

        An identifier is six positional digits: domain, layer, module,
        category, case. This reads the layer and module tokens off each name
        and checks the digits that encode them.

        **Nothing checked the previous allocation**, which is how `EXE/UNI`
        came to sit inside `EVL`'s block, `EVL/UNI` inside `CAS`'s and
        `CMN/UNI` past its last allocated block, all at once and silently.

        **The duplicate-binding check cannot see this.** Two modules occupying
        one block are two distinct identifiers, so counting bindings balances.

        Design: ``test_taxonomy.md`` section 3.2.1.4.

        Returns:
            None
        """
        problems = identifier_block_problems(_REPOSITORY_ROOT)

        assert not problems, (
            "identifiers carry digits their tokens contradict, so a module "
            "occupies a block it was not allocated: " + "; ".join(problems)
        )
