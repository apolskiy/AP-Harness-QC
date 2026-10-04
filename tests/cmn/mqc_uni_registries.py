# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""What every registry contains, pinned so growth is deliberate.

Covers ``MQC_CMN_UNI_112319``, inventoried in
``docs/design/cmn_verdict_and_cli.md`` section 10.33.

**Split from the metadata module on 2026-09-25**, when that module crossed the
thousand line ceiling. The split follows the subject: this is about what a
registry contains, and the rest of that module is about what a result record
carries.

**A registry with no case asserting its membership can drift.** Six of them
had public accessors nobody called and contents nobody asserted, which a sweep
read as dead code. Unasserted is not dead, and the two want opposite repairs.

A failure here is our defect, so the module carries no priority marker.
"""

import pytest

from cmn.layers import is_registered_skip_reason, registered_skip_reasons
from cmn.observations import registered_run_contexts, registered_selection_modes
from cmn.registries import (
    EvaluationFamily,
    is_registered_llm_code,
    is_registered_sec_code,
    register_evaluation_family,
    registered_evaluation_families,
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
            {"dependency", "environmental", "incomplete", "unsupported"}
        ), "the skip reasons changed, and each one decides a different treatment"

        assert registered_run_contexts() == frozenset({"ci", "ci_debug", "local"})
        assert registered_selection_modes() == frozenset(
            {"change_scoped", "full", "manual"}
        ), "a selection mode decides whether a run yields a verdict at all"

        assert registered_evaluation_families() == frozenset(
            {"code_comprehension", "output_shape", "requirement_match",
             "injection_resistance", "tool_compliance"}
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
