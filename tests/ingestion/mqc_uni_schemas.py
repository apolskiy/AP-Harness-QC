# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for schema validation and the ingest invariants.

Covers `MQC_ING_UNI_111300` through `111314` and `111319` through `111325`, as
inventoried in ``docs/design/tier1_ingestion.md`` section 13.1.

**These are preconditions, not graded tests.** A failure here is **not a
model finding**
rather than a finding about a model, which is why the module carries no
priority marker: preconditions are equally mandatory and there is no budget to
allocate. See ``framework-rules.md`` section 3.3.

Each test names the identifier it satisfies in its own name, so a result in a
JUnit file resolves back to the inventory row without a lookup table.
"""

from typing import Any
import pytest

from cmn.registries import is_registered_constraint_kind

from ingestion.integrity import check_referential_integrity
from ingestion.schemas import (
    Anchor,
    canonical_identifier,
    Constraint,
    GoldenRuleSet,
    ProgrammaticAssertion,
    RubricCriterion,
    TaskDataSet,
    ToolDefinition,
    ToolExpectation,
)

pytestmark = pytest.mark.unit


class TestMQCTaskSchema:
    """Validation of `TaskDataSet`, the record describing what is sent."""

    def MQC_ING_UNI_111300_accepts_complete_task_payload(
        self,
        sample_task_payload: dict[str, Any],
    ) -> None:
        """A payload carrying every required field builds a record.

        Args:
            sample_task_payload (dict): Minimal valid payload.

        Returns:
            None
        """
        task = TaskDataSet.from_dict(sample_task_payload)
        assert task.task_id == "MQC_TASK_sample"
        assert task.rubric_ids == ["MQC_RULE_sample"]

    def MQC_ING_UNI_111302_rejects_task_missing_user_prompt(
        self,
        sample_task_payload: dict[str, Any],
    ) -> None:
        """A task without a prompt names the absent field, not merely 'invalid'.

        Args:
            sample_task_payload (dict): Minimal valid payload.

        Returns:
            None
        """
        del sample_task_payload["user_prompt"]
        with pytest.raises(KeyError, match="QC_DATA_REQUIRED_FIELD_MISSING") as caught:
            TaskDataSet.from_dict(sample_task_payload)
        assert "user_prompt" in str(caught.value)

    def MQC_ING_UNI_111303_rejects_task_missing_rubric_ids(
        self,
        sample_task_payload: dict[str, Any],
    ) -> None:
        """A task judged by nothing is rejected at ingest.

        Args:
            sample_task_payload (dict): Minimal valid payload.

        Returns:
            None
        """
        del sample_task_payload["rubric_ids"]
        with pytest.raises(KeyError, match="QC_DATA_REQUIRED_FIELD_MISSING"):
            TaskDataSet.from_dict(sample_task_payload)

    def MQC_ING_UNI_111304_rejects_empty_rubric_ids_list(
        self,
        sample_task_payload: dict[str, Any],
    ) -> None:
        """An empty list is present and carries nothing, so it is rejected.

        The code differs from the missing case deliberately: a forgotten field
        and a placeholder left in are different authoring errors.

        Args:
            sample_task_payload (dict): Minimal valid payload.

        Returns:
            None
        """
        sample_task_payload["rubric_ids"] = []
        with pytest.raises(ValueError, match="QC_DATA_REQUIRED_FIELD_EMPTY"):
            TaskDataSet.from_dict(sample_task_payload)

    def MQC_ING_UNI_111305_rejects_unknown_yaml_key(
        self,
        sample_task_payload: dict[str, Any],
    ) -> None:
        """A typo in an optional field would otherwise take a default silently.

        Args:
            sample_task_payload (dict): Minimal valid payload.

        Returns:
            None
        """
        sample_task_payload["system_instructon"] = "typo"
        with pytest.raises(KeyError, match="QC_DATA_UNKNOWN_FIELD") as caught:
            TaskDataSet.from_dict(sample_task_payload)
        assert "system_instructon" in str(caught.value)

    def MQC_ING_UNI_111307_reports_all_missing_fields_not_only_first(self) -> None:
        """Every absent field is named in one message.

        An author correcting hand-written data wants the whole list rather than
        one field per run.

        Returns:
            None
        """
        with pytest.raises(KeyError) as caught:
            TaskDataSet.from_dict({"task_id": "MQC_TASK_bare"})
        message = str(caught.value)
        assert "rubric_ids" in message
        assert "user_prompt" in message

    def MQC_ING_UNI_111308_accepts_task_with_no_optional_fields(
        self,
        sample_task_payload: dict[str, Any],
    ) -> None:
        """Every optional field takes its declared default when absent.

        Comparing the whole record rather than each field asserts every default
        at once, and fails if a field is ever added without a default being
        decided for it.

        Args:
            sample_task_payload (dict): Payload carrying only required fields.

        Returns:
            None
        """
        expected = TaskDataSet(
            task_id="MQC_TASK_sample",
            rubric_ids=["MQC_RULE_sample"],
            user_prompt="Rewrite the summary to match the posting.",
        )
        assert TaskDataSet.from_dict(sample_task_payload) == expected

    @pytest.mark.parametrize("supplied", ["", "   ", "\t\n "])
    def MQC_ING_UNI_111320_rejects_mandatory_field_supplied_as_whitespace_only(
        self, sample_task_payload: dict[str, Any], supplied: Any
    ) -> None:
        """Whitespace is stripped before emptiness is tested, so blanks are caught.

        Args:
            sample_task_payload (dict): Minimal valid payload.
            supplied (str): A value that looks present and carries nothing.

        Returns:
            None
        """
        sample_task_payload["user_prompt"] = supplied
        with pytest.raises(ValueError, match="QC_DATA_REQUIRED_FIELD_EMPTY"):
            TaskDataSet.from_dict(sample_task_payload)

    def MQC_ING_UNI_111322_distinguishes_missing_from_empty_in_emitted_code(
        self, sample_task_payload: dict[str, Any]
    ) -> None:
        """The two authoring errors carry different codes, because fixes differ.

        Args:
            sample_task_payload (dict): Minimal valid payload.

        Returns:
            None
        """
        absent = dict(sample_task_payload)
        del absent["user_prompt"]
        with pytest.raises(KeyError) as missing_case:
            TaskDataSet.from_dict(absent)

        blank = dict(sample_task_payload)
        blank["user_prompt"] = ""
        with pytest.raises(ValueError) as empty_case:
            TaskDataSet.from_dict(blank)

        assert "QC_DATA_REQUIRED_FIELD_MISSING" in str(missing_case.value)
        assert "QC_DATA_REQUIRED_FIELD_EMPTY" in str(empty_case.value)

    def MQC_ING_UNI_111323_non_ascii_content_survives_an_explicit_encoding_read(
        self, sample_task_payload: dict[str, Any]
    ) -> None:
        """Non-ASCII text round-trips unchanged through validation.

        The platform hazard this guards is in the loader, where an unqualified
        open reads cp1252 on Windows. This asserts the record itself alters
        nothing, so a later mismatch localizes to the read rather than here.

        Args:
            sample_task_payload (dict): Minimal valid payload.

        Returns:
            None
        """
        # Written as escapes so the source stays ASCII. The characters are the
        # point of the test, and a literal would depend on this file surviving
        # an editor that re-saves as cp1252, which is the failure being tested.
        original = "Rubric anchor with an ellipsis \u2026 and an en dash \u2013 inside"
        sample_task_payload["user_prompt"] = original
        assert TaskDataSet.from_dict(sample_task_payload).user_prompt == original

    @pytest.mark.parametrize("reserved", ["nul", "CON", "com1", "LPT9", "aux.json"])
    def MQC_ING_UNI_111325_case_id_matching_a_windows_reserved_device_name_is_rejected(
        self, sample_task_payload: dict[str, Any], reserved: Any
    ) -> None:
        """An identifier that cannot become a directory on Windows is refused.

        Args:
            sample_task_payload (dict): Minimal valid payload.
            reserved (str): A reserved device name, in various spellings.

        Returns:
            None
        """
        sample_task_payload["task_id"] = reserved
        with pytest.raises(ValueError, match="QC_DATA_IDENTIFIER_UNSAFE"):
            TaskDataSet.from_dict(sample_task_payload)


class TestMQCGoldenRuleSchema:
    """Validation of `GoldenRuleSet`, including invariants G1 and G6."""

    def MQC_ING_UNI_111331_a_rule_set_naming_an_unregistered_family_is_reported(
        self,
    ) -> None:
        """Every declared family is registered, and no family is repeated.

        **Each value, not the first.** A rule naming two families fails if
        either is unregistered, so a second value cannot reach the durable
        record unresolvable while the first vouches for it.

        **A repeat is refused** because the order is load-bearing: the first
        value is the primary family, and a duplicate makes that ambiguous while
        counting the case twice in a per-family cost total.

        **Absent is permitted here and required one level up.** Which rules must
        declare a family is a property of a shipped corpus rather than of the
        schema, and `MQC_CAS_UNI_115414` holds the corpus to it.

        Design: ``harness_test_taxonomy.md`` sections 11.7.2 and 11.8.

        Returns:
            None
        """
        base = {
            "rule_id": "MQC_RULE_fam",
            "priority": 2,
            "priority_conditions": ["P2_DOCUMENTED_BEHAVIOUR"],
            "assertions": [{
                "assertion_id": "A_FAM",
                "kind": "contains",
                "parameters": {"value": "anything"},
                "taxonomy_code": "QC_LLM_SOURCE_ALTERATION",
                "severity": "violation",
            }],
        }

        declared = GoldenRuleSet.from_dict(
            {**base, "families": ["source_fidelity", "output_shape"]}
        )
        assert declared.families == ("source_fidelity", "output_shape"), (
            "the declared order was not preserved, so the primary family is "
            "whatever a set iteration produced"
        )

        with pytest.raises(ValueError, match="QC_DATA_INVARIANT_VIOLATION"):
            GoldenRuleSet.from_dict({**base, "families": ["invented_family"]})

        # THE SECOND VALUE IS CHECKED TOO, which is the half a first-value-only
        # check would pass.
        with pytest.raises(ValueError, match="are not registered"):
            GoldenRuleSet.from_dict(
                {**base, "families": ["output_shape", "invented_family"]}
            )

        with pytest.raises(ValueError, match="repeats a family"):
            GoldenRuleSet.from_dict(
                {**base, "families": ["output_shape", "output_shape"]}
            )

        assert not GoldenRuleSet.from_dict(base).families

    def MQC_ING_UNI_111301_accepts_complete_golden_rule_payload(
        self,
        sample_rule_payload: dict[str, Any],
    ) -> None:
        """A rule set carrying a rubric and a registered condition builds.

        Args:
            sample_rule_payload (dict): Minimal valid payload.

        Returns:
            None
        """
        rule = GoldenRuleSet.from_dict(sample_rule_payload)
        assert rule.rule_id == "MQC_RULE_sample"
        assert rule.priority == 2
        assert rule.rubric is not None

    def MQC_ING_UNI_111306_rejects_non_numeric_threshold(
        self,
        sample_rule_payload: dict[str, Any],
    ) -> None:
        """A threshold that will not cast is a malformed source, not a typo.

        Args:
            sample_rule_payload (dict): Minimal valid payload.

        Returns:
            None
        """
        sample_rule_payload["rubric"]["threshold"] = "high"
        with pytest.raises(ValueError, match="QC_DATA_MALFORMED_SOURCE"):
            GoldenRuleSet.from_dict(sample_rule_payload)

    def MQC_ING_UNI_111309_rejects_rule_set_with_no_assertions_rubric_or_tools(
        self, sample_rule_payload: dict[str, Any]
    ) -> None:
        """G1: a rule set that judges nothing would report green in silence.

        Args:
            sample_rule_payload (dict): Minimal valid payload.

        Returns:
            None
        """
        del sample_rule_payload["rubric"]
        with pytest.raises(ValueError, match="QC_DATA_INVARIANT_VIOLATION"):
            GoldenRuleSet.from_dict(sample_rule_payload)

    def MQC_ING_UNI_111315_rejects_empty_priority_conditions(
        self,
        sample_rule_payload: dict[str, Any],
    ) -> None:
        """G6: a priority with no named condition is not assignable.

        Args:
            sample_rule_payload (dict): Minimal valid payload.

        Returns:
            None
        """
        sample_rule_payload["priority_conditions"] = []
        with pytest.raises(ValueError, match="QC_DATA_REQUIRED_FIELD_EMPTY"):
            GoldenRuleSet.from_dict(sample_rule_payload)

    def MQC_ING_UNI_111316_rejects_unregistered_priority_condition_id(
        self, sample_rule_payload: dict[str, Any]
    ) -> None:
        """G6: free text would permit 'because it is important'.

        Args:
            sample_rule_payload (dict): Minimal valid payload.

        Returns:
            None
        """
        sample_rule_payload["priority_conditions"] = ["P1_SEEMS_IMPORTANT"]
        with pytest.raises(ValueError, match="QC_DATA_INVARIANT_VIOLATION") as caught:
            GoldenRuleSet.from_dict(sample_rule_payload)
        assert "P1_SEEMS_IMPORTANT" in str(caught.value)

    def MQC_ING_UNI_111317_rejects_priority_above_matched_condition_ceiling(
        self, sample_rule_payload: dict[str, Any]
    ) -> None:
        """G6: matching only a P2 condition cannot justify P0.

        Args:
            sample_rule_payload (dict): Minimal valid payload.

        Returns:
            None
        """
        sample_rule_payload["priority"] = 0
        with pytest.raises(ValueError, match="QC_DATA_INVARIANT_VIOLATION"):
            GoldenRuleSet.from_dict(sample_rule_payload)

    def MQC_ING_UNI_111318_accepts_priority_demoted_below_matched_ceiling(
        self, sample_rule_payload: dict[str, Any]
    ) -> None:
        """G6 states a ceiling, not an assignment, so demotion is legitimate.

        This is the boundary that makes the demotion rule workable: budget
        pressure is absorbed downward without the level losing its meaning.

        Args:
            sample_rule_payload (dict): Minimal valid payload.

        Returns:
            None
        """
        sample_rule_payload["priority"] = 4
        assert GoldenRuleSet.from_dict(sample_rule_payload).priority == 4

    def MQC_ING_UNI_111321_rejects_mandatory_list_field_supplied_empty(
        self, sample_rule_payload: dict[str, Any]
    ) -> None:
        """An empty mandatory list is present and carries nothing.

        Args:
            sample_rule_payload (dict): Minimal valid payload.

        Returns:
            None
        """
        sample_rule_payload["priority_conditions"] = []
        with pytest.raises(ValueError, match="QC_DATA_REQUIRED_FIELD_EMPTY"):
            GoldenRuleSet.from_dict(sample_rule_payload)

    def MQC_ING_UNI_111324_case_ids_differing_only_by_letter_case_are_rejected(self) -> None:
        """Two identifiers with one canonical form collide on Windows.

        Detection lives in the loader, which sees a whole file. This asserts the
        canonical form the loader compares is case-insensitive, so a loader
        failure localizes to the loader rather than to this helper.

        Returns:
            None
        """
        assert canonical_identifier("MQC_TASK_Alpha") == canonical_identifier("mqc_task_alpha")
        assert canonical_identifier("MQC_TASK_alpha") != canonical_identifier("MQC_TASK_beta")


class TestMQCRubricSchema:
    """Validation of rubric records, including invariants G2 and G3."""

    def MQC_ING_UNI_111310_rejects_rubric_with_empty_criteria(
        self,
        sample_rule_payload: dict[str, Any],
    ) -> None:
        """G2: a rubric judging nothing is a silent no-op.

        Args:
            sample_rule_payload (dict): Minimal valid payload.

        Returns:
            None
        """
        sample_rule_payload["rubric"]["criteria"] = []
        with pytest.raises(ValueError, match="QC_DATA_REQUIRED_FIELD_EMPTY"):
            GoldenRuleSet.from_dict(sample_rule_payload)

    def MQC_ING_UNI_111311_rejects_anchors_missing_level_three(
        self,
        sample_anchors: dict[int,
        dict[str, str]],
    ) -> None:
        """G3: levels 1, 3 and 5 are required, and the message names the gap.

        Args:
            sample_anchors (dict): Valid anchors at 1, 3 and 5.

        Returns:
            None
        """
        del sample_anchors[3]
        with pytest.raises(ValueError, match="QC_DATA_REQUIRED_FIELD_MISSING") as caught:
            RubricCriterion.from_dict(
                {
                    "criterion_id": "C_QUALITY",
                    "name": "Quality",
                    "description": "Whether the response meets the bar",
                    "anchors": sample_anchors,
                }
            )
        assert "[3]" in str(caught.value)

    def MQC_ING_UNI_111312_accepts_anchors_with_only_one_three_five(
        self,
        sample_anchors: dict[int,
        dict[str, str]],
    ) -> None:
        """G3 requires three anchors and permits five, so the minimum is valid.

        Requiring all five is authoring burden without proportional benefit, and
        a judge discriminates better against few sharply distinguished anchors.

        Args:
            sample_anchors (dict): Anchors at exactly 1, 3 and 5.

        Returns:
            None
        """
        criterion = RubricCriterion.from_dict(
            {
                "criterion_id": "C_QUALITY",
                "name": "Quality",
                "description": "Whether the response meets the bar",
                "anchors": sample_anchors,
            }
        )
        assert sorted(criterion.anchors) == [1, 3, 5]

    @pytest.mark.parametrize("level", [0, 6, -1])
    def MQC_ING_UNI_111313_rejects_anchor_level_outside_one_to_five(
        self, sample_anchors: dict[int, dict[str, str]], level: Any
    ) -> None:
        """G3: a level outside the scale is an invariant violation.

        Args:
            sample_anchors (dict): Valid anchors at 1, 3 and 5.
            level (int): A level outside the permitted scale.

        Returns:
            None
        """
        sample_anchors[level] = {"description": "Off the scale"}
        with pytest.raises(ValueError, match="QC_DATA_INVARIANT_VIOLATION"):
            RubricCriterion.from_dict(
                {
                    "criterion_id": "C_QUALITY",
                    "name": "Quality",
                    "description": "Whether the response meets the bar",
                    "anchors": sample_anchors,
                }
            )


class TestMQCSupportingSchemas:
    """Validation of the records the two halves are assembled from."""

    def MQC_ING_UNI_111314_rejects_overlapping_required_and_forbidden_tools(self) -> None:
        """G4: no response can satisfy a contradictory expectation.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="QC_DATA_INVARIANT_VIOLATION") as caught:
            ToolExpectation.from_dict(
                {"required_tools": ["search"], "forbidden_tools": ["search", "browse"]}
            )
        assert "search" in str(caught.value)

    def MQC_ING_UNI_111319_rejects_mandatory_field_supplied_as_empty_string(self) -> None:
        """A present but empty mandatory field is a placeholder left in.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="QC_DATA_REQUIRED_FIELD_EMPTY"):
            Constraint.from_dict({"constraint_id": "C1", "text": "", "kind": "prohibition"})

    def MQC_ING_UNI_111326_assertion_severity_is_declared_not_inferred(self) -> None:
        """Severity is authored, because one kind can be either.

        A regex check may guard a structural necessity or a cosmetic preference,
        so inferring severity from the assertion kind would be wrong half the
        time.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="QC_DATA_INVARIANT_VIOLATION"):
            ProgrammaticAssertion.from_dict(
                {
                    "assertion_id": "A1",
                    "kind": "regex",
                    "parameters": {"pattern": "x"},
                    "taxonomy_code": "QC_LLM_FORMAT_VIOLATION",
                    "severity": "important",
                }
            )

    def MQC_ING_UNI_111327_tool_definition_requires_a_parameters_schema(self) -> None:
        """An empty schema is ambiguous between 'no arguments' and 'unfilled'.

        The mandatory-non-empty rule resolves it by requiring the shape to be
        stated, so a tool taking no arguments says so explicitly.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="QC_DATA_REQUIRED_FIELD_EMPTY"):
            ToolDefinition.from_dict(
                {"tool_name": "search", "description": "Search", "parameters_schema": {}}
            )

    def MQC_ING_UNI_111328_anchor_exemplar_is_optional_and_preserved(self) -> None:
        """An exemplar is optional, and an absent one stays absent.

        Returns:
            None
        """
        without = Anchor.from_dict({"description": "Meets the bar"})
        with_exemplar = Anchor.from_dict(
            {"description": "Meets the bar", "exemplar": "A response scoring here"}
        )
        assert without.exemplar is None
        assert with_exemplar.exemplar == "A response scoring here"


class TestMQCConstraintKindRegistry:
    """What the open vocabulary has promoted, and what it refused."""

    def MQC_ING_UNI_111329_count_and_ordering_are_registered_constraint_kinds(
        self,
    ) -> None:
        """Promotion records that a kind earned a name, not that the set closed.

        The instruction-following corpus authored seven constraints across the
        two, which is the repetition section 8 says triggers promotion, and
        neither fits a registered kind: a bullet ceiling is a bound on how much
        rather than output shape, and a response can satisfy every shape
        constraint while ordering its content wrongly.

        **`form` was refused in the same pass**, because capitalization and
        sentence completeness are output shape and `format` already covers
        them. A vocabulary that grows with every author's phrasing describes
        nothing.

        Returns:
            None
        """
        assert is_registered_constraint_kind("count")
        assert is_registered_constraint_kind("ordering")
        assert not is_registered_constraint_kind("form")

        # The vocabulary stays OPEN. An unregistered kind warns and is
        # permitted, so a typo surfaces without failing a run.
        assert not is_registered_constraint_kind("prohibiton")


class TestMQCAdversarialRubric:
    """R6: a rubric that can never be scored is refused where it is explained."""

    def MQC_ING_UNI_111330_a_declared_adversarial_task_with_a_rubric_is_refused(
        self,
        sample_task_payload: dict[str, Any],
        sample_rule_payload: dict[str, Any],
    ) -> None:
        """The pair makes a case that cannot pass and does not say why.

        A declared adversarial case reaches no judge (A19), so its rubric can
        never be scored, and `tier3_evaluation.md` section 4D does not pass a
        rule whose authored rubric went unscored. **The pair is therefore a
        case that always fails, for a reason visible nowhere in the result.**

        That symptom has been corrected three times in this project, so it is
        refused at ingest where the message can name the remedy.

        Args:
            sample_task_payload (dict): Minimal valid task payload.
            sample_rule_payload (dict): Minimal valid rule payload, carrying a
                rubric.

        Returns:
            None
        """
        rule = GoldenRuleSet.from_dict(dict(sample_rule_payload))
        assert rule.rubric is not None, "the payload must carry a rubric to test this"

        declared = dict(sample_task_payload)
        declared["contains_adversarial_content"] = True
        declared["rubric_ids"] = [rule.rule_id]
        adversarial = TaskDataSet.from_dict(declared)

        # REFUSED AT INGEST, and the message names the remedy rather than
        # leaving a reader to discover it from a case that always fails.
        with pytest.raises(ValueError, match="QC_DATA_INVARIANT_VIOLATION") as raised:
            check_referential_integrity([adversarial], [rule])
        assert adversarial.task_id in str(raised.value)
        assert "grade by assertion" in str(raised.value)

        # THE SAME TASK WITHOUT THE DECLARATION IS FINE. The judge runs, the
        # rubric is scored, and nothing here applies.
        ordinary_payload = dict(sample_task_payload)
        ordinary_payload["rubric_ids"] = [rule.rule_id]
        check_referential_integrity([TaskDataSet.from_dict(ordinary_payload)], [rule])

        # AND A DECLARED TASK WHOSE RULE AUTHORS NO RUBRIC IS THE DESIGN, not
        # an omission: it grades resistance by assertion. Returning without
        # raising is the assertion.
        deterministic_payload = dict(sample_rule_payload)
        deterministic_payload.pop("rubric", None)
        deterministic_payload["assertions"] = [
            {
                "assertion_id": "MQC_ASR_probe",
                "kind": "not_contains",
                "parameters": {"value": "CANARY"},
                "taxonomy_code": "QC_LLM_INJECTION_SUSCEPTIBLE",
                "severity": "violation",
            }
        ]
        deterministic = GoldenRuleSet.from_dict(deterministic_payload)
        assert deterministic.rubric is None
        check_referential_integrity([adversarial], [deterministic])
