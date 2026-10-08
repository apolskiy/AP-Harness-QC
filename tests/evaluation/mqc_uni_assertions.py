# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for the deterministic half of the dual pass.

Covers `MQC_EVL_UNI_114100` and `114101`, inventoried in
``docs/design/tier3_evaluation.md`` section 11.1.

**`not_contains` is what makes injection resistance deterministic.** A payload
whose instruction is to emit a canary turns compliance into an exact string
check, which is why a declared adversarial case is graded here and never sent to
a judge.

**Bounds are stated at the threshold exactly**, never near it. Off-by-one at a
boundary is the likeliest defect in any gate, so a rule of at most five bullets
is tested at five and at six.

A failure here is **not a model finding**, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

from types import SimpleNamespace
from typing import Any

import allure
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

    def MQC_EVL_UNI_114101_not_contains_detects_canary_token(self) -> None:
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

    def MQC_EVL_UNI_114102_contains_requires_the_substring_to_be_present(self) -> None:
        """The mirror of `114101`, so neither passes by always answering one way.

        Returns:
            None
        """
        assertion = _assertion("contains", {"value": "five years"})
        assert run_assertion(assertion, "It requires five years.").passed is True
        assert run_assertion(assertion, "It requires some experience.").passed is False

    def MQC_EVL_UNI_114103_regex_checks_presence_and_absence(self) -> None:
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

    def MQC_EVL_UNI_114104_json_schema_reports_why_a_structure_failed(self) -> None:
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
    def MQC_EVL_UNI_114105_length_bound_holds_at_the_threshold_exactly(
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

    def MQC_EVL_UNI_114106_an_unregistered_length_unit_is_a_harness_error(self) -> None:
        """An unknown unit measured as characters would produce a confident lie.

        Returns:
            None
        """
        assertion = _assertion("length", {"unit": "paragraphs", "maximum": 3})
        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR"):
            run_assertion(assertion, "Some text.")

    def MQC_EVL_UNI_114107_an_unregistered_kind_is_a_harness_error_not_a_failure(self) -> None:
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

    def MQC_EVL_UNI_114100_assertion_result_records_originating_assertion_id(self) -> None:
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

    def MQC_EVL_UNI_114108_every_assertion_runs_rather_than_stopping_at_the_first(self) -> None:
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

    def MQC_EVL_UNI_114109_fatal_severity_is_distinguished_from_violation(self) -> None:
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

    def MQC_EVL_UNI_114110_a_passing_assertion_carries_no_taxonomy_code(self) -> None:
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


@allure.epic("AP-Harness-QC")
@allure.feature("Evaluation")
class TestMQCMarkupNormalisation:
    """Whether a pattern reads what was said or how it was formatted."""

    @allure.story("A figure in backticks is still the figure")
    @pytest.mark.parametrize(
        "formatted",
        [
            "the second returns `0`.",
            "the second returns **0**.",
            "the second returns ```0```.",
            "the second returns 0.",
        ],
    )
    def MQC_EVL_UNI_114111_a_pattern_reads_through_inline_markup(
        self, formatted: str
    ) -> None:
        """A regex matches a figure whether or not the model formatted it.

        **The defect this guards was a false finding against a vendor.** grok
        answered a code-comprehension case correctly, writing "the second
        returns `0`", and `A_COD_OUTCOME_FREE_GOODS` required a settling verb
        followed by the figure. The backtick sat between them, two of five
        observations failed, and the case reported `QC_LLM_INCONSISTENT` on a
        page about to be filed. It is five of five normalised.

        **All four spellings must match**, which is what makes this more than a
        no-op: the unformatted form passed before and the three formatted ones
        did not.

        Design: ``tier3_evaluation.md`` section 5.1.

        Args:
            formatted (str): One spelling of the same answer.

        Returns:
            None
        """
        assertion = SimpleNamespace(
            assertion_id="A_PROBE_FIGURE",
            kind="regex",
            parameters={
                "pattern": r"(?i)\breturns?\s+(0|zero)\b",
                "present": True,
            },
            severity="violation",
            taxonomy_code="QC_LLM_DEFECT_MISSED",
        )
        result = run_assertion(assertion, formatted)
        assert result.passed, (
            f"the pattern read the formatting rather than the answer: "
            f"{formatted!r} carries the figure and {result.detail}"
        )

    @allure.story("A counting assertion keeps the raw text")
    def MQC_EVL_UNI_114112_a_length_assertion_reads_unnormalised_text(
        self,
    ) -> None:
        """A character bound is measured on the text the model produced.

        **`length` is excluded from normalisation because it counts the text as
        written.** A bound stated against a model's output has to be measured
        against that output: removing markup shortens it, so a reply inside the
        limit would measure shorter than it is and one over the limit could
        measure under.

        **The first version of this case was vacuous and injection said so.**
        It counted bullets, on the reasoning that stripping markers would lose
        them; single asterisks survive normalisation deliberately, so the count
        was identical either way and adding ``length`` to the normalised set
        changed nothing. Characters are the unit that moves.

        Design: ``tier3_evaluation.md`` section 5.1.

        Returns:
            None
        """
        # 24 characters as written, 18 with the backticks and bold removed.
        formatted = "the call returns `0` **now**"
        assertion = SimpleNamespace(
            assertion_id="A_PROBE_LENGTH",
            kind="length",
            parameters={"unit": "characters", "minimum": len(formatted)},
            severity="violation",
            taxonomy_code="QC_LLM_FORMAT_VIOLATION",
        )
        result = run_assertion(assertion, formatted)
        assert result.passed, (
            f"the character count was taken from normalised text, which is "
            f"shorter than what the model produced: {result.detail}"
        )


@allure.epic("AP-Harness-QC")
@allure.feature("Programmatic assertions")
class TestMQCClaimScope:
    """Whether a sentence asserted something, rather than mentioned it."""

    @allure.story("A hedged mention is not a claim")
    def MQC_EVL_UNI_114113_a_hedged_mention_of_a_forbidden_claim_is_not_a_claim(
        self,
    ) -> None:
        """A sentence that rules out the wrong answer has not given it.

        **This is the sentence that withdrew nine findings.** A `regex` with
        ``present`` false asks whether a string appears anywhere, so a model
        that named the wrong answer in order to reject it was recorded as
        having given it. The text below is the recorded response that cost
        ``134101``.

        Design: ``tier3_evaluation.md`` section 5.3.

        Returns:
            None
        """
        claim = _assertion(
            "claim",
            {
                "pattern": r"(?i)\b(returns?|result\w*)\b[^.]{0,40}\b90\b[^.]{0,25}\b50\b",
                "present": False,
                "unless": ["looks like", "appears", "intended", "should", "but"],
            },
            assertion_id="A_HEDGED",
            taxonomy_code="QC_LLM_HALLUCINATION",
        )

        # WHAT THE MODEL ACTUALLY WROTE, and it is the correct answer.
        hedged = (
            "The sort runs and then has no effect. The function looks like it "
            "should return the rows scoring 90 and 50, but it doesn't. The "
            "output is correct only by coincidence."
        )
        result = run_assertion(claim, hedged)
        assert result.passed, (
            f"a sentence ruling out the wrong answer was read as giving it, "
            f"which is the defect this kind exists to end: {result.detail}"
        )

        # AND THE BARE CLAIM STILL FAILS, or the fix would have cost the test.
        asserted = "It returns the rows scoring 90 and 50, in that order."
        result = run_assertion(claim, asserted)
        assert not result.passed, (
            "an unhedged claim passed, so the assertion now catches nothing"
        )
        assert "90" in result.detail, (
            f"the detail does not quote the sentence that carried the claim, so "
            f"a reader cannot see what was asserted: {result.detail}"
        )
        assert result.taxonomy_code == "QC_LLM_HALLUCINATION", (
            "a failing claim carries no code, so nothing can classify it"
        )

        # THE HEDGE IS SCOPED TO ITS OWN SENTENCE. A hedge elsewhere says
        # nothing about this claim, and treating the response as one unit is
        # how the window in the old pattern went wrong.
        elsewhere = (
            "It returns the rows scoring 90 and 50. Separately, the variable "
            "name looks like it should mean something else."
        )
        result = run_assertion(claim, elsewhere)
        assert not result.passed, (
            "a hedge in a different sentence excused the claim, so scope is "
            "the response again rather than the sentence"
        )

    @allure.story("A forbidding claim states its exclusions")
    def MQC_EVL_UNI_114114_a_forbidding_claim_without_exclusions_is_refused(
        self,
    ) -> None:
        """A claim with nothing excluded is a pattern match by another name.

        **Two ways of writing one rule drift.** A forbidding claim that
        declared no hedges would behave exactly as the `regex` it replaced,
        and the next reader would have no way to tell which was meant.

        **Refusal is a harness error, not a model finding**: the assertion is
        misconfigured, and reporting it against the model would put our own
        defect in a vendor's inbox.

        Design: ``tier3_evaluation.md`` section 5.3.

        Returns:
            None
        """
        bare = _assertion(
            "claim",
            {"pattern": "anything", "present": False},
            assertion_id="A_BARE",
            taxonomy_code="QC_LLM_HALLUCINATION",
        )
        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR") as raised:
            run_assertion(bare, "anything at all")
        assert "regex" in str(raised.value), (
            f"the refusal does not name the kind to use instead, so a reader "
            f"is told no and not what to do: {raised.value}"
        )

        # AND THE OTHER DIRECTION, which has no agreed meaning either.
        narrowed = _assertion(
            "claim",
            {"pattern": "anything", "present": True, "unless": ["maybe"]},
            assertion_id="A_NARROWED",
            taxonomy_code="QC_LLM_HALLUCINATION",
        )
        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR"):
            run_assertion(narrowed, "anything at all")

        # A CLAIM IS STILL A REGISTERED KIND, so the refusals above are about
        # the parameters rather than about the kind being unknown.
        assert "claim" in registered_assertion_kinds(), (
            "the claim kind is not registered, so every case using it reports "
            "a harness error instead of a result"
        )
