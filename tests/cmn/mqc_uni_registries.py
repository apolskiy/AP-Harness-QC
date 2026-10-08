# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""What every registry contains, pinned so growth is deliberate.

Covers ``MQC_CMN_UNI_112319`` and ``112343``, inventoried in
``docs/design/cmn_verdict_and_cli.md`` section 10.33.

**Split from the metadata module on 2026-09-25**, when that module crossed the
thousand line ceiling. The split follows the subject: this is about what a
registry contains, and the rest of that module is about what a result record
carries.

**A registry with no case asserting its membership can drift.** Six of them
had public accessors nobody called and contents nobody asserted, which a sweep
read as dead code. Unasserted is not dead, and the two want opposite repairs.

A failure here is **not a model finding**, so the module carries no priority marker.
"""

import pytest

from cmn.layers import is_registered_skip_reason, registered_skip_reasons
from cmn.observations import registered_run_contexts, registered_selection_modes
from cmn.registries import (
    EvaluationFamily,
    evaluation_family,
    is_registered_llm_code,
    is_registered_sec_code,
    register_evaluation_family,
    registered_evaluation_families,
    unregister_evaluation_family,
)

pytestmark = pytest.mark.unit

class TestMQCRegistryMembership:
    """Six registries had accessors nobody called and contents nobody asserted."""

    def MQC_CMN_UNI_112319_a_registry_membership_change_without_a_case_is_reported(
        self,
    ) -> None:
        """Unasserted is not the same as dead, and wants the opposite repair.

        A sweep reported these accessors as dead code. **They are not dead,
        they are unasserted**: public, documented in no design, and referenced
        only inside their own modules. Dead code is deleted; an unasserted
        registry gets the case it was missing.

        **What a registry can do silently.** A member added is a vocabulary
        the design never sanctioned; a member removed is a value that was legal
        yesterday and loads as an error today. `112200` through `112202` check
        that emitted and documented codes are registered, which is the other
        direction entirely.

        **Pinned exactly, so growth is deliberate.** This case is a maintenance
        cost on purpose, like an inventory row: a registry gaining a member
        without anybody noticing is the thing being prevented.

        Returns:
            None
        """
        assert registered_skip_reasons() == frozenset(
            {"dependency", "environmental", "incomplete", "quarantined",
             "unsupported"}
        ), "the skip reasons changed, and each one decides a different treatment"

        assert registered_run_contexts() == frozenset({"ci", "ci_debug", "local"})
        assert registered_selection_modes() == frozenset(
            {"change_scoped", "full", "manual"}
        ), "a selection mode decides whether a run yields a verdict at all"

        assert registered_evaluation_families() == frozenset(
            {"code_comprehension", "output_shape", "requirement_match",
             "injection_resistance", "tool_compliance", "source_fidelity",
             "ambiguity_discrimination"}
        ), "a family is a ground-truth mechanism, not a label"

        # THE MEMBERSHIP PREDICATES AGREE WITH THE SETS, which is what makes
        # either safe to use: a predicate that drifted from its own registry
        # would answer confidently and wrongly.
        for reason in registered_skip_reasons():
            assert is_registered_skip_reason(reason)
        assert not is_registered_skip_reason("invented")

        # THE TWO CODE FAMILIES ARE DISTINCT, and each predicate refuses the
        # other's members. A code belonging to both would make a security
        # finding countable as a quality one.
        assert is_registered_llm_code("QC_LLM_TOOL_VIOLATION")
        assert not is_registered_llm_code("QC_SEC_INJECTION_ATTEMPT")
        assert is_registered_sec_code("QC_SEC_INJECTION_ATTEMPT")
        assert not is_registered_sec_code("QC_LLM_TOOL_VIOLATION")
        assert not is_registered_llm_code("QC_LLM_INVENTED")

        # REGISTERING A FAMILY IS A GUARDED OPERATION, and the guard is the
        # point: a family with no ground-truth mechanism is a label.
        with pytest.raises(ValueError):
            register_evaluation_family(
                EvaluationFamily(
                    identifier="unfounded",
                    input_shape="anything at all",
                    ground_truth="",
                )
            )


class TestMQCRuntimeRegistration:
    """The add and remove pair, which section 11.6 described and nobody ran."""

    def MQC_CMN_UNI_112343_a_registered_family_round_trips_and_leaves_no_trace(
        self,
    ) -> None:
        """A well-founded family is admitted, readable, and removable.

        **The refusal was covered and the mechanism it guards was not.** The
        only call in the suite rejected a family stating no ground-truth
        mechanism, so nothing had added one, read it back, or removed it, and
        the remove half was called by nothing in either repository. A sixth
        family added at runtime would have exercised an untested path.

        **The registry is left exactly as it was found**, which is the property
        the extension cases depend on: a case that registers and does not
        remove leaks a family into every case that runs after it, and the
        membership pin in ``112319`` would fail for a reason nobody could
        locate from its message.

        Design: ``harness_test_taxonomy.md`` section 11.6.

        Returns:
            None
        """
        before = registered_evaluation_families()
        assert "round_trip_probe" not in before

        admitted = register_evaluation_family(
            EvaluationFamily(
                identifier="round_trip_probe",
                input_shape="a synthetic record this case supplies",
                ground_truth="the identifier the case registered, compared exactly",
            )
        )
        assert admitted.identifier == "round_trip_probe", (
            "registration returned something other than the family it admitted"
        )

        # READABLE FROM THE REGISTRY, which is the half that makes the add
        # worth anything: a family nothing can look up is not registered.
        during = registered_evaluation_families()
        assert "round_trip_probe" in during
        looked_up = evaluation_family("round_trip_probe")
        assert looked_up is not None, (
            "the family is in the membership set and cannot be looked up, so "
            "the two accessors disagree about the same registry"
        )
        assert looked_up.ground_truth

        # AND ADDED WITHOUT DISTURBING WHAT WAS THERE.
        assert set(before) < set(during)
        assert set(during) - set(before) == {"round_trip_probe"}

        unregister_evaluation_family("round_trip_probe")

        after = registered_evaluation_families()
        assert "round_trip_probe" not in after, (
            "the family survived its removal, so a case registering one leaks "
            "it into every case that runs after it"
        )
        assert after == before, (
            "the registry is not what it was found as, so the round trip is "
            "not a round trip"
        )

        # REMOVING WHAT WAS NEVER THERE IS QUIET, because a case cleaning up
        # after a refused registration must not fail on the cleanup.
        unregister_evaluation_family("round_trip_probe")
        unregister_evaluation_family("never_registered")
        assert registered_evaluation_families() == before
