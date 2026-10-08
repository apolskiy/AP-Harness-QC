# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Whether a finding is named by the most serious thing that happened.

Covers ``MQC_CMN_UNI_112330``, inventoried in
``docs/design/cmn_verdict_and_cli.md`` section 10 and designed in
``test_taxonomy.md`` section 6.4.

**Split from ``mqc_uni_metadata.py`` on 2026-10-05**, which the one case took
to 1024 lines against the thousand-line ceiling. The ranking is its own
subject: that module is about what a result carries, this one about which of
several codes names the finding.

A failure here is **not a model finding**, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

import pytest

from cmn.registries import (
    code_criticality,
    most_critical,
    registered_codes,
    unranked_codes,
)

pytestmark = pytest.mark.unit


class TestMQCCodeCriticality:
    """Whether a finding is named by the most serious thing that happened."""

    def MQC_CMN_UNI_112330_a_registered_code_without_a_rank_is_reported(
        self,
    ) -> None:
        """Every model and security code carries a criticality rank.

        **A code added without a rank sorts last silently.** That is the right
        behaviour for a report, which must still be produced, and the wrong
        place to discover the gap: a new security code would classify below
        inconsistency until somebody noticed a finding reading oddly.

        **The order is asserted, not just the completeness.** A table that is
        full and wrong would pass a completeness check, so the two claims the
        ranking exists to make are both named here: a compromise outranks a
        disagreement, and a disagreement is last.

        Design: ``test_taxonomy.md`` section 6.4.

        Returns:
            None
        """
        unranked = unranked_codes()
        assert not unranked, (
            f"{len(unranked)} registered code(s) carry no criticality rank, so "
            f"each sorts below every ranked code and would classify a finding "
            f"as the least serious thing that happened: {sorted(unranked)}"
        )

        # THE TWO CLAIMS THE RANKING EXISTS TO MAKE. Both were false before
        # 2026-10-05: two P0 security failures were catalogued as consistency
        # observations because `consistent()` emitted the only code in the
        # message.
        assert most_critical(
            ["QC_LLM_INCONSISTENT", "QC_LLM_INJECTION_SUSCEPTIBLE"]
        ) == "QC_LLM_INJECTION_SUSCEPTIBLE", (
            "a model obeying an injected instruction is classified as a "
            "disagreement, which reads to a vendor as a quality nit"
        )
        assert code_criticality("QC_LLM_INCONSISTENT") == max(
            code_criticality(code) for code in registered_codes()
            if code.startswith(("QC_LLM_", "QC_SEC_"))
        ), (
            "inconsistency is not the least critical code, so it can name a "
            "finding where something more serious also fired"
        )
        assert code_criticality("QC_SEC_JUDGE_HIJACK") < code_criticality(
            "QC_LLM_INJECTION_SUSCEPTIBLE"
        ), (
            "a hijacked judge does not outrank a susceptible candidate, and "
            "the judge is the instrument every other number depends on"
        )
