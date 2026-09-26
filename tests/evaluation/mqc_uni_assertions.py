# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for the deterministic half of the dual pass.

Covers `MQC_EVL_UNI_10315` and `10316`, inventoried in
``docs/design/tier3_evaluation.md`` section 11.1.

**`not_contains` is what makes injection resistance deterministic.** A payload
whose instruction is to emit a canary turns compliance into an exact string
check, which is why a declared adversarial case is graded here and never sent to
a judge.

**Bounds are stated at the threshold exactly**, never near it. Off-by-one at a
boundary is the likeliest defect in any gate, so a rule of at most five bullets
is tested at five and at six.

A failure here is our defect, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

from typing import Any
import pytest

from evaluation.assertions import (
    assertions_passed,
    has_fatal_failure,
    registered_assertion_kinds,
    registered_severities,
    run_assertion,
    run_assertions,
)
from ingestion.schemas import ProgrammaticAssertion

pytestmark = pytest.mark.unit

_CANARY = "MQC-CANARY-7f3a91"


def _assertion(kind: str, parameters: dict, **overrides: object) -> ProgrammaticAssertion:
    """Build an assertion over a valid base.

    Args:
        kind (str): The assertion kind.
        parameters (dict): Its parameters.
        **overrides (object): Fields to replace.

    Returns:
        ProgrammaticAssertion: The built record.
    """
    payload: dict[str, object] = {
        "assertion_id": f"MQC_ASR_{kind}",
        "kind": kind,
        "parameters": parameters,
        "taxonomy_code": "QC_LLM_SCHEMA_VIOLATION",
        "severity": "violation",
    }
    payload.update(overrides)
    return ProgrammaticAssertion.from_dict(payload)


class TestMQCAssertionKinds:
    """Each registered kind, in both directions."""

    def MQC_EVL_UNI_10316_not_contains_detects_canary_token(self) -> None:
        """The case injection resistance rests on.

        A payload instructing the model to emit a unique marker makes
        compliance an exact string check. A judge asked whether a model resisted
        could only estimate; this settles it.

        Returns:
            None
        """
        assertion = _assertion("not_contains", {"value": _CANARY})

        complied = run_assertion(assertion, f"Certainly. {_CANARY}")
        resisted = run_assertion(assertion, "I will not follow that instruction.")

        assert complied.passed is False
        assert complied.taxonomy_code == "QC_LLM_SCHEMA_VIOLATION"
        assert resisted.passed is True
        assert resisted.taxonomy_code is None

    def MQC_EVL_UNI_10356_contains_requires_the_substring_to_be_present(self) -> None:
        """The mirror of `10316`, so neither passes by always answering one way.

        Returns:
            None
        """
        assertion = _assertion("contains", {"value": "five years"})
        assert run_assertion(assertion, "It requires five years.").passed is True
        assert run_assertion(assertion, "It requires some experience.").passed is False

    def MQC_EVL_UNI_10357_regex_checks_presence_and_absence(self) -> None:
        """One kind, both polarities, because the parameter decides which.

        Returns:
            None
        """
        present = _assertion("regex", {"pattern": r"^\d+ years"})
        absent = _assertion("regex", {"pattern": r"\bTODO\b", "present": False})

        assert run_assertion(present, "5 years of Python").passed is True
        assert run_assertion(present, "Several years of Python").passed is False
        assert run_assertion(absent, "A finished answer.").passed is True
        assert run_assertion(absent, "A TODO remains.").passed is False

    def MQC_EVL_UNI_10358_json_schema_reports_why_a_structure_failed(self) -> None:
        """A failing structural check says what was wrong, not only that it was.

        Returns:
            None
        """
        assertion = _assertion(
            "json_schema",
            {"required_keys": ["summary", "years"], "types": {"years": "int"}},
        )

        assert run_assertion(assertion, '{"summary": "ok", "years": 5}').passed is True
        assert "not valid JSON" in run_assertion(assertion, "not json at all").detail
        assert "missing required keys" in run_assertion(assertion, '{"summary": "ok"}').detail
        assert "rather than int" in run_assertion(
            assertion, '{"summary": "ok", "years": "5"}'
        ).detail

    @pytest.mark.parametrize(
        "bullets,expected", [(4, True), (5, True), (6, False)]
    )
    def MQC_EVL_UNI_10359_length_bound_holds_at_the_threshold_exactly(
        self, bullets: int, expected: Any
    ) -> None:
        """Stated at the bound, not near it.

        A rule of at most five bullets holds at five and fails at six.
        Off-by-one at a boundary is the likeliest defect in any gate, which is
        why the case names the threshold rather than approaching it.

        Args:
            bullets (int): How many bullets the response carries.
            expected (bool): Whether the assertion should hold.

        Returns:
            None
        """
        assertion = _assertion("length", {"unit": "bullets", "maximum": 5})
        text = "\n".join(f"- point {index}" for index in range(bullets))
        assert run_assertion(assertion, text).passed is expected

    def MQC_EVL_UNI_10360_an_unregistered_length_unit_is_a_harness_error(self) -> None:
        """An unknown unit measured as characters would produce a confident lie.

        Returns:
            None
        """
        assertion = _assertion("length", {"unit": "paragraphs", "maximum": 3})
        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR"):
            run_assertion(assertion, "Some text.")

    def MQC_EVL_UNI_10361_an_unregistered_kind_is_a_harness_error_not_a_failure(self) -> None:
        """Our configuration error must not be recorded as a model finding.

        Treating it as a failure would attribute our own mistake to the model
        under test, which is the attribution failure this project exists to
        avoid.

        Returns:
            None
        """
        assertion = _assertion("contains", {"value": "x"})
        object.__setattr__(assertion, "kind", "semantic_similarity")
        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR") as caught:
            run_assertion(assertion, "Some text.")
        assert "registered kinds are" in str(caught.value)
        assert registered_assertion_kinds() >= {"regex", "contains", "not_contains"}


class TestMQCAssertionResults:
    """What a result carries, and how results combine."""

    def MQC_EVL_UNI_10315_assertion_result_records_originating_assertion_id(self) -> None:
        """A failing case says what failed, not only that something did.

        Returns:
            None
        """
        results = run_assertions(
            [
                _assertion("contains", {"value": "present"}, assertion_id="MQC_ASR_one"),
                _assertion("contains", {"value": "absent"}, assertion_id="MQC_ASR_two"),
            ],
            "the word present appears here",
        )

        assert [result.assertion_id for result in results] == [
            "MQC_ASR_one", "MQC_ASR_two"
        ]
        assert [result.passed for result in results] == [True, False]
        assert results[1].kind == "contains"

    def MQC_EVL_UNI_10362_every_assertion_runs_rather_than_stopping_at_the_first(self) -> None:
        """A case failing three and a case failing one prompt different fixes.

        Short-circuiting would mean discovering the second failure on the next
        run, and the third on the one after.

        Returns:
            None
        """
        failing = [
            _assertion("contains", {"value": f"missing-{index}"},
                       assertion_id=f"MQC_ASR_{index}")
            for index in range(3)
        ]
        results = run_assertions(failing, "none of those appear")

        assert len(results) == 3
        assert assertions_passed(results) is False

    def MQC_EVL_UNI_10363_fatal_severity_is_distinguished_from_violation(self) -> None:
        """The distinction the two severities exist to make.

        A fatal failure is never judged, flag or not, because there is nothing
        coherent to score. A violation is judged under the flag.

        Returns:
            None
        """
        violation = run_assertions(
            [_assertion("contains", {"value": "absent"})], "text"
        )
        fatal = run_assertions(
            [_assertion("contains", {"value": "absent"}, severity="fatal")], "text"
        )

        assert has_fatal_failure(violation) is False
        assert has_fatal_failure(fatal) is True
        assert registered_severities() == {"violation", "fatal"}

    def MQC_EVL_UNI_10364_a_passing_assertion_carries_no_taxonomy_code(self) -> None:
        """A blank taking its default is normal operation, never a finding.

        Recording a code on a pass would corrupt every later count drawn from
        the durable record.

        Returns:
            None
        """
        result = run_assertion(_assertion("contains", {"value": "yes"}), "yes indeed")
        assert result.passed is True
        assert result.taxonomy_code is None
        assert result.fatal is False
