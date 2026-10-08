# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""What a run spends on a case it already knows about, and what it learns.

Covers ``MQC_CMN_UNI_112338``, ``112339`` and ``112340``, inventoried in
``docs/design/cmn_verdict_and_cli.md`` section 12 and designed in sections
4.6.12 and 10.28.2.1.

**Two decisions with one subject: cost.** Quarantine stops a run paying to
measure a result somebody already holds. Probing spends nothing extra in replay
to learn whether a dependent carries its own defect. Both were settled by the
project owner on 2026-10-07, and both had the same defect before: the cheap
information was not taken and the expensive measurement was.

A failure here is **not a model finding**, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

from types import SimpleNamespace
from typing import Final

import pytest

from cmn.dependencies import (
    enforce_dependencies,
    probes_dependents,
    record_base_outcome,
    reset_dependency_state,
)
from cmn.layers import outcome_properties, registered_outcomes
from cmn.registries import is_registered_harness_code

from tests.cmn.cascade_doubles import cascade_item

pytestmark = pytest.mark.unit

_FOUNDATION: Final[str] = "154100"


class TestMQCCascadeCost:
    """What a run declines to pay for, and what it takes for free."""

    def MQC_CMN_UNI_112338_a_quarantined_case_reaching_dispatch_is_reported(
        self,
    ) -> None:
        """Quarantine saves the run's cost, which it did not.

        **It was read at verdict time only.** Nothing in selection or the
        pytest hooks knew of quarantine, so every run dispatched every
        quarantined case, spent the quota, and then removed the result from one
        statistic: the acceptance was free and the measurement was not, which
        is the wrong way round.

        **The code is registered**, because a skip carrying an unregistered
        code reaches the register as unclassified and is recordable by nothing.

        Design: ``cmn_verdict_and_cli.md`` section 4.6.12.

        Returns:
            None
        """
        assert is_registered_harness_code("QC_HARNESS_QUARANTINED"), (
            "the quarantine skip carries an unregistered code, so a run that "
            "declined to measure a case cannot say why in terms anything reads"
        )

        # AND IT IS NEITHER A PASS NOR A FAILURE. Quarantine accepts a finding;
        # the band counts the skip against the band it was selected into.
        # A SKIP IS A NON-PASS, per `test_taxonomy.md` section 7.4.1: in the
        # denominator and never the numerator, so declining to measure a case
        # reads as the failure it is. Quarantine saves the cost of measuring a
        # known failure and does not stop it being one.
        properties = outcome_properties("skip")
        assert not properties.is_pass, (
            "a skipped case reads as a pass, so quarantine would buy a green"
        )
        assert properties.counts_in_pass_rate, (
            "a skip leaves the pass-rate denominator, so a quarantined "
            "failure stops lowering the rate it should lower"
        )

    def MQC_CMN_UNI_112339_a_dependent_of_a_failure_is_probed_in_replay(
        self,
    ) -> None:
        """Replay measures the dependent; live declines to pay for it.

        **A dependent of a failed foundation may carry its own defect.** Fixing
        the foundation would not fix it, and nothing can tell which it is
        without running the dependent. Section 10.28.1 skipped it so one
        behaviour was not counted twice, which is right where the dependent
        fails for the foundation's reason and loses a finding where it fails
        for its own.

        **Replay runs it free**, so the information is taken on every CI band;
        a live run would spend quota on what the next replay gives away.

        Design: ``cmn_verdict_and_cli.md`` section 10.28.2.1.

        Returns:
            None
        """
        assert probes_dependents(cascade_item("probe", "replay")), (
            "replay declines to probe, so a dependent's own defect waits for "
            "the next round trip although measuring it costs nothing"
        )
        assert not probes_dependents(cascade_item("probe", "live")), (
            "a live run probes, spending quota on what the next replay would "
            "give away free"
        )
        # AN UNSET MODE IS TREATED AS SPENDING, so a caller that configured
        # nothing never probes.
        assert not probes_dependents(cascade_item("probe", "")), (
            "an unconfigured run probes, so the default spends"
        )
        assert not probes_dependents(SimpleNamespace(name="bare")), (
            "an item carrying no config probes, which would crash a caller "
            "that has no invocation to read"
        )

        # THE FOUNDATION FAILED: replay marks the dependent and lets it run,
        # and live skips it.
        reset_dependency_state()
        record_base_outcome(cascade_item(f"MQC_EVL_SEC_{_FOUNDATION}_x", "replay"), False)

        probed = cascade_item("MQC_EVL_SEC_154109_y", "replay", (_FOUNDATION,))
        enforce_dependencies(probed)
        assert probed.added, (
            "the probed dependent carries no marker, so the reporting hook "
            "cannot tell its result from a measured one"
        )

        with pytest.raises(BaseException) as raised:
            enforce_dependencies(cascade_item("MQC_EVL_SEC_154109_y", "live", (_FOUNDATION,)))
        assert "QC_HARNESS_DEPENDENCY_UNMET" in str(raised.value), (
            f"a live dependent of a failure did not skip with the cascade's "
            f"code: {raised.value}"
        )

    def MQC_CMN_UNI_112340_a_probe_is_counted_in_no_denominator(self) -> None:
        """A boundary, and the boundary is every denominator at once.

        **A probe is a measurement and not a verdict.** It is taken so a
        dependent's own defect is visible, and it enters no aggregate so that
        one behaviour cannot be reported twice: that is the whole of its
        accounting, and section 10.28.1's objection survives it intact.

        **The registry refuses an outcome that omits a denominator**, which is
        why this is a boundary rather than four separate claims.

        Design: ``cmn_verdict_and_cli.md`` section 10.28.2.1.

        Returns:
            None
        """
        assert "probe" in registered_outcomes(), (
            "the probe outcome is unregistered, so every probed observation "
            "reports a harness error instead of a result"
        )
        properties = outcome_properties("probe")
        for field in (
            "counts_in_pass_rate", "is_pass",
            "counts_in_skip_rate", "counts_in_distribution",
        ):
            assert not getattr(properties, field), (
                f"a probe declares {field}, so measuring a dependent of a "
                f"failure counts one behaviour twice in that denominator"
            )

        # AND THE NEIGHBOURS ARE UNCHANGED, or this would have moved an
        # existing outcome's accounting while adding one.
        assert outcome_properties("pass").is_pass
        assert outcome_properties("fail").counts_in_pass_rate
        assert outcome_properties("skip").counts_in_skip_rate
        assert not outcome_properties("broken").counts_in_pass_rate
