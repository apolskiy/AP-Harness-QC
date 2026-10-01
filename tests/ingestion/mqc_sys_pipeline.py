# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""System preconditions for the joined ingestion pipeline.

Covers `MQC_ING_SYS_20001` through `20007`, inventoried in
``docs/design/tier1_ingestion.md`` section 13.2.

**These are integration cases because the checks they cover need both halves.**
Referential integrity runs after the join, since a rule set cannot be told
whether its `constraint_ref` resolves until it is paired with a task. Unit
cases could not reach them without inventing the join, which would test the
invention rather than the pipeline.

A failure here is our defect, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

from typing import Any

import pytest

from ingestion.cases import build_case_id, build_evaluation_cases, count_unique_case_definitions
from ingestion.integrity import check_referential_integrity
from ingestion.schemas import GoldenRuleSet, TaskDataSet

pytestmark = pytest.mark.system

_ANCHORS = {
    1: {"description": "Fails the criterion"},
    3: {"description": "Meets it partially"},
    5: {"description": "Meets it fully"},
}

_CONSTRAINT = {
    "constraint_id": "C_NO_INVENTION",
    "text": "Claim nothing absent from the source material.",
    "kind": "prohibition",
}

_TOOL = {
    "tool_name": "search",
    "description": "Search the supplied documents",
    "parameters_schema": {"type": "object", "properties": {}},
}


def _rubric(constraint_ref: str | None = None) -> dict[str, Any]:
    """Build a rubric payload, optionally referencing a constraint.

    Args:
        constraint_ref (Optional[str]): The constraint the criterion judges.

    Returns:
        dict: The rubric payload.
    """
    criterion: dict[str, Any] = {
        "criterion_id": "C_GROUNDED",
        "name": "Grounding",
        "description": "Every claim traces to the source",
        "anchors": _ANCHORS,
    }
    if constraint_ref is not None:
        criterion["constraint_ref"] = constraint_ref
    return {"criteria": [criterion], "threshold": 3.0}


def _assertion(assertion_id: str, constraint_ref: str) -> dict[str, Any]:
    """Build a regex assertion referencing one constraint.

    Args:
        assertion_id (str): The assertion identifier.
        constraint_ref (str): The constraint it checks.

    Returns:
        dict: The assertion payload.
    """
    return {
        "assertion_id": assertion_id,
        "kind": "regex",
        "parameters": {"pattern": "nothing", "present": False},
        "taxonomy_code": "QC_LLM_SOURCE_ALTERATION",
        "severity": "violation",
        "constraint_ref": constraint_ref,
    }


def _task(**overrides: Any) -> TaskDataSet:
    """Build a task, with overrides applied over a valid base.

    Args:
        **overrides (Any): Fields to replace.

    Returns:
        TaskDataSet: The built record.
    """
    payload: dict[str, Any] = {
        "task_id": "MQC_TASK_alpha",
        "rubric_ids": ["MQC_RULE_grounding"],
        "user_prompt": "Rewrite the summary to match the posting.",
    }
    payload.update(overrides)
    return TaskDataSet.from_dict(payload)


def _rule(**overrides: Any) -> GoldenRuleSet:
    """Build a rule set, with overrides applied over a valid base.

    Args:
        **overrides (Any): Fields to replace.

    Returns:
        GoldenRuleSet: The built record.
    """
    payload: dict[str, Any] = {
        "rule_id": "MQC_RULE_grounding",
        "priority": 2,
        "priority_conditions": ["P2_DOCUMENTED_BEHAVIOUR"],
        "rubric": _rubric(),
    }
    payload.update(overrides)
    return GoldenRuleSet.from_dict(payload)


class TestMQCReferentialIntegrity:
    """The five checks that need both halves of the join."""

    def MQC_ING_SYS_20001_rejects_task_referencing_unknown_rubric_id(self) -> None:
        """R1: a dangling reference means the case is judged by nothing.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="QC_DATA_INVARIANT_VIOLATION") as caught:
            check_referential_integrity(
                [_task(rubric_ids=["MQC_RULE_absent"])], [_rule()]
            )
        assert "R1" in str(caught.value)

    def MQC_ING_SYS_20002_rejects_constraint_ref_with_no_matching_constraint(self) -> None:
        """R2: grading a model on an instruction it never received is unfair.

        The finding it produces looks like a model defect and is ours, which is
        what makes this check worth more than its size suggests.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="QC_DATA_INVARIANT_VIOLATION") as caught:
            check_referential_integrity(
                [_task()], [_rule(rubric=_rubric("C_NO_INVENTION"))]
            )
        assert "R2" in str(caught.value)

    def MQC_ING_SYS_20003_rejects_constraint_sent_but_never_checked(self) -> None:
        """R3: an instruction sent and never verified is a rule nobody tests.

        This is the check nobody writes. Nothing surfaces it, and the result
        looks entirely normal.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="QC_DATA_INVARIANT_VIOLATION") as caught:
            check_referential_integrity([_task(constraints=[_CONSTRAINT])], [_rule()])
        assert "R3" in str(caught.value)

    def MQC_ING_SYS_20004_rejects_tool_expectation_for_unoffered_tool(self) -> None:
        """R4: forbidding a tool never offered proves nothing about the model.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="QC_DATA_INVARIANT_VIOLATION") as caught:
            check_referential_integrity(
                [_task()], [_rule(tool_expectation={"forbidden_tools": ["search"]})]
            )
        assert "R4" in str(caught.value)

    def MQC_ING_SYS_20007_rejects_contradictory_tool_expectation_after_the_join(self) -> None:
        """R5 at the joined level, which G4 cannot reach alone.

        G4 rejects an intersection when one expectation is built. R5 repeats the
        check after the join, where a contradictory pair could arrive from two
        individually valid halves. The design specified five checks and
        inventoried four; this is the fifth.

        Returns:
            None
        """
        rule = _rule(tool_expectation={"required_tools": ["search"]})
        forbidden = frozenset({"search"})
        contradictory = GoldenRuleSet(
            rule_id=rule.rule_id,
            priority=rule.priority,
            priority_conditions=rule.priority_conditions,
            rubric=rule.rubric,
            tool_expectation=type(rule.tool_expectation)(
                required_tools=rule.tool_expectation.required_tools,
                forbidden_tools=forbidden,
            ),
        )
        with pytest.raises(ValueError, match="QC_DATA_INVARIANT_VIOLATION") as caught:
            check_referential_integrity([_task(available_tools=[_TOOL])], [contradictory])
        assert "R5" in str(caught.value)

    def MQC_ING_SYS_20012_several_rules_may_divide_a_task_s_constraints_between_them(
        self,
    ) -> None:
        """R3 is a claim about a task and was asked of one rule at a time.

        Every task in the corpus named one rule for the project's whole life, so
        "referenced by at least one check" and "referenced by this rule" were the
        same sentence. A consumer split one rule into four specialised ones, one
        constraint each, and R3 reported **twelve violations over a corpus in
        which every constraint is checked**.

        **The pair scoping was coercive, not merely wrong.** Satisfying it meant
        every rule checking every constraint, so one rule carried all four
        assertions; four graded cases then bound that rule, assertions are
        conjunctive, and one failing assertion failed all four. An invariant
        satisfiable only by a worse design is a defect in the invariant.

        **`20003` still reports the real case**, which is what makes this a
        widening rather than a weakening: a constraint no rule the task names
        checks remains an instruction sent and never verified.

        Returns:
            None
        """
        second = {
            "constraint_id": "C_NO_SPECULATION",
            "text": "Do not speculate about causes.",
            "kind": "prohibition",
        }
        task = _task(
            rubric_ids=["MQC_RULE_grounded", "MQC_RULE_unspeculative"],
            constraints=[_CONSTRAINT, second],
        )

        # EACH RULE CHECKS ONE CONSTRAINT AND IGNORES THE OTHER, which is what
        # specialising a rule means and what the pair scoping forbade.
        grounded = _rule(
            rule_id="MQC_RULE_grounded",
            rubric=None,
            assertions=[_assertion("A_GROUNDED", "C_NO_INVENTION")],
        )
        unspeculative = _rule(
            rule_id="MQC_RULE_unspeculative",
            rubric=None,
            assertions=[_assertion("A_UNSPECULATIVE", "C_NO_SPECULATION")],
        )

        check_referential_integrity([task], [grounded, unspeculative])

        # AND A CONSTRAINT NO RULE CHECKS IS STILL REFUSED. Dropping one rule
        # leaves its constraint sent and verified by nothing.
        with pytest.raises(ValueError, match="C_NO_SPECULATION"):
            check_referential_integrity([task], [grounded])

    def MQC_ING_SYS_20008_a_fully_consistent_corpus_passes_every_check(self) -> None:
        """All five checks satisfied at once, which no negative case proves.

        Five passing negatives establish that each check fires. Only this
        establishes that they can all be satisfied together, which is the
        claim an author relies on when writing a case.

        Returns:
            None
        """
        check_referential_integrity(
            [_task(constraints=[_CONSTRAINT], available_tools=[_TOOL])],
            [
                _rule(
                    rubric=_rubric("C_NO_INVENTION"),
                    tool_expectation={"required_tools": ["search"]},
                )
            ],
        )


class TestMQCCaseConstruction:
    """Building the (task by rubric) unit after the join."""

    def MQC_ING_SYS_20005_builds_one_case_per_task_rubric_pair(self) -> None:
        """The unit of evaluation is the pair, not the task.

        Returns:
            None
        """
        tasks = [
            _task(rubric_ids=["MQC_RULE_grounding", "MQC_RULE_shape"]),
            _task(task_id="MQC_TASK_beta", rubric_ids=["MQC_RULE_grounding"]),
        ]
        rules = [_rule(), _rule(rule_id="MQC_RULE_shape", priority=3)]
        cases = build_evaluation_cases(tasks, rules)
        assert len(cases) == 3
        assert count_unique_case_definitions(cases) == 3
        assert [case.priority for case in cases] == [2, 3, 2]

    def MQC_ING_SYS_20006_case_id_is_stable_across_runs(self) -> None:
        """An identifier derives only from two authored names.

        Nothing about when or where a run happened enters it, which is what
        lets a downstream record match this case to the same case next week.

        Returns:
            None
        """
        first = build_evaluation_cases([_task()], [_rule()])
        second = build_evaluation_cases([_task()], [_rule()])
        assert first[0].case_id == second[0].case_id
        assert first[0].case_id == build_case_id("MQC_TASK_alpha", "MQC_RULE_grounding")

    def MQC_ING_SYS_20010_colliding_case_ids_are_rejected_after_the_join(self) -> None:
        """Two pairs whose combined identifiers collide on a filesystem.

        Both halves are screened individually at ingest, so reaching this needs
        a combination that collides while neither half does. It is unlikely and
        worth catching: a case identifier becomes a fixture directory, and a
        silent reuse corrupts replay on one platform only.

        Returns:
            None
        """
        tasks = [_task(task_id="MQC_TASK_Alpha"), _task(task_id="MQC_TASK_alpha")]
        with pytest.raises(ValueError, match="QC_DATA_IDENTIFIER_UNSAFE"):
            build_evaluation_cases(tasks, [_rule()])

    def MQC_ING_SYS_20011_a_tool_expectation_may_itself_check_a_constraint(self) -> None:
        """A constraint can be verified by an expectation, not only a criterion.

        R3 collects references from assertions, rubric criteria and the tool
        expectation. Omitting any one source would report a constraint as
        unchecked while something checks it, which is a false finding about
        data that is correct.

        Returns:
            None
        """
        check_referential_integrity(
            [_task(constraints=[_CONSTRAINT], available_tools=[_TOOL])],
            [
                _rule(
                    tool_expectation={
                        "required_tools": ["search"],
                        "constraint_ref": "C_NO_INVENTION",
                    }
                )
            ],
        )

    def MQC_ING_SYS_20009_case_building_requires_integrity_to_have_run(self) -> None:
        """An unresolvable reference here is a programming error, not bad data.

        R1 already establishes that every reference resolves. Re-checking would
        put one rule in two places, so this path raises instead, and the message
        says which step was skipped.

        Returns:
            None
        """
        with pytest.raises(KeyError, match="QC_DATA_INVARIANT_VIOLATION") as caught:
            build_evaluation_cases([_task(rubric_ids=["MQC_RULE_absent"])], [_rule()])
        assert "referential integrity" in str(caught.value)
