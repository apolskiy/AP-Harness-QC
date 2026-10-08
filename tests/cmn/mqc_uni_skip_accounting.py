# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for what a skip counts as, and what releases one.

Covers `MQC_CMN_UNI_112341` and `112342`, inventoried in
``docs/design/cmn_verdict_and_cli.md`` section 10.

**One subject: the accounting a skip receives.** A skip is a non-pass whatever
its cause, and whether it is counted as a failure is decided by the reason it
carries (`harness_test_taxonomy.md` section 7.4.1). The one thing that can turn a
counted skip back into an exclusion is a release dispensation product
management has recorded (section 4.6.13).

A failure here is **not a model finding**, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

from datetime import date

import pytest

from cmn.layers import (
    is_registered_skip_reason,
    outcome_properties,
    skip_counts_as_failure,
)
from cmn.quarantine import QuarantineEntry, dispensed_ids, released_by_dispensation

pytestmark = pytest.mark.unit


class TestMQCSkipAccounting:
    """What the pass rate does with a case that produced no measurement."""

    def MQC_CMN_UNI_112341_a_skipped_case_absent_from_the_pass_rate_is_reported(
        self,
    ) -> None:
        """A skip reaches the denominator, and its cause decides whether it counts.

        **Both halves are asserted here**, because either alone reports
        coverage it does not have. The outcome registration says a skip may be
        counted at all; the reason rule says which skips are. A registration of
        false would have made every reason moot, and a rule returning true for
        everything would have charged the model for our own fixtures.

        Returns:
            None
        """
        properties = outcome_properties("skip")
        assert properties.counts_in_pass_rate, (
            "a skipped case left the pass-rate denominator, so the rate was "
            "stated over whatever happened to run"
        )
        assert not properties.is_pass, "a skip was counted as a pass"

        # THE MODEL'S NON-PASSES, each a case that did not pass for a reason
        # the model owns or that nobody attributed.
        for reason in ("quarantined", "dependency", "incomplete"):
            assert is_registered_skip_reason(reason), reason
            assert skip_counts_as_failure(reason), reason
        assert skip_counts_as_failure(None), (
            "a skip nobody attributed was treated as evidence that the model "
            "was blameless"
        )
        assert skip_counts_as_failure(""), "an empty reason was excused"

        # OURS AND NOBODY'S, which charging to the model is the misattribution
        # the four taxonomy families exist to prevent.
        for reason in ("environmental", "unsupported"):
            assert is_registered_skip_reason(reason), reason
            assert not skip_counts_as_failure(reason), reason


class TestMQCBlockerRelease:
    """The one recorded decision that releases a blocker, and its guards."""

    def MQC_CMN_UNI_112342_a_blocker_released_without_a_dispensation_is_reported(
        self,
    ) -> None:
        """Quarantine saves a run's cost and never buys a pass.

        **Three states, and only one releases.** An entry carrying no
        reference is the ordinary case and releases nothing. An entry carrying
        one while unconfirmed releases nothing either, because section 4.6.4
        holds that a missing observed date or model is our bookkeeping failing
        and the entry's expiry cannot be evaluated. A confirmed entry naming
        the tracker reference releases, and names it.

        Returns:
            None
        """
        parked = QuarantineEntry(
            case_id="MQC_TASK_a::MQC_RULE_r",
            reason="a finding under repair",
            quarantined_on=date(2026, 9, 20),
            observed_model="gemini-2.5-flash",
        )
        assert released_by_dispensation(parked) == "", (
            "a quarantine entry released a blocker with no decision recorded"
        )

        unconfirmed = QuarantineEntry(
            case_id="MQC_TASK_b::MQC_RULE_r",
            reason="a finding under repair",
            release_accepted_in="MQC-914",
        )
        assert released_by_dispensation(unconfirmed) == "", (
            "an entry with no observed date or model carried a dispensation, "
            "so a release was accepted against a finding whose expiry cannot "
            "be evaluated"
        )

        released = QuarantineEntry(
            case_id="MQC_TASK_c::MQC_RULE_r",
            reason="a finding under repair",
            quarantined_on=date(2026, 9, 20),
            observed_model="gemini-2.5-flash",
            release_accepted_in="MQC-914",
        )
        assert released_by_dispensation(released) == "MQC-914"

        # AND THE SET THE DENOMINATOR READS HOLDS EXACTLY THE RELEASED ONE,
        # which is the half a per-entry check cannot establish.
        assert dispensed_ids([parked, unconfirmed, released]) == frozenset(
            {"MQC_TASK_c::MQC_RULE_r"}
        )

        # A BLANK REFERENCE IS NOT A REFERENCE. Whitespace would otherwise
        # release a blocker while recording nothing a reader could go and read.
        whitespace = QuarantineEntry(
            case_id="MQC_TASK_d::MQC_RULE_r",
            reason="a finding under repair",
            quarantined_on=date(2026, 9, 20),
            observed_model="gemini-2.5-flash",
            release_accepted_in="   ",
        )
        assert released_by_dispensation(whitespace) == ""
