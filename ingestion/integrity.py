# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Referential integrity across the task and rule-set halves.

Specified by ``docs/design/tier1_ingestion.md`` section 6. The five checks run
**after** the join, because each needs both sides: a rule set cannot be told
whether its ``constraint_ref`` resolves until it is paired with a task.

Every violation emits ``QC_DATA_INVARIANT_VIOLATION`` at ERROR and aborts
ingestion. All violations are collected before raising, because an author
correcting hand-written data wants the whole list.

**R3 is the check nobody writes.** A constraint sent to the model and never
verified means the rule is untested and nothing surfaces it. Its converse R2
means grading a model on an instruction it never received, which produces a
finding about a model that did nothing wrong. Both yield plausible results,
which is exactly what makes them dangerous.
"""

import logging
from typing import Iterable

from cmn.registries import is_registered_constraint_kind
from ingestion.schemas import GoldenRuleSet, TaskDataSet

logger = logging.getLogger(__name__)


def check_referential_integrity(
    tasks: Iterable[TaskDataSet], rule_sets: Iterable[GoldenRuleSet]
) -> None:
    """Run R1 through R5 over a loaded corpus, reporting every violation.

    Args:
        tasks (Iterable): Every loaded task.
        rule_sets (Iterable): Every loaded rule set.

    Returns:
        None

    Raises:
        ValueError: Naming every violation found, with
            ``QC_DATA_INVARIANT_VIOLATION``. Raised once, after all five checks
            have run, so that one pass reports everything wrong.
    """
    task_list = list(tasks)
    rules_by_id = {rule.rule_id: rule for rule in rule_sets}
    violations: list[str] = []

    for task in task_list:
        violations.extend(_check_rubric_references(task, rules_by_id))
        named = [
            rules_by_id[rule_id]
            for rule_id in task.rubric_ids
            if rule_id in rules_by_id
        ]
        for rule in named:
            violations.extend(_check_constraint_references(task, rule))
            violations.extend(_check_tool_expectations(task, rule))
            violations.extend(_check_adversarial_has_no_rubric(task, rule))
        # R3 TAKES EVERY RULE AT ONCE. Its claim is that a constraint is checked
        # by something, and asking it of one rule at a time demanded that every
        # rule check every constraint: satisfiable only by refusing to
        # specialise rules. Design section 7.3.1.
        violations.extend(_check_every_constraint_is_checked(task, named))

    if violations:
        logger.error("QC_DATA_INVARIANT_VIOLATION %d referential violations", len(violations))
        detail = "; ".join(violations)
        raise ValueError(f"QC_DATA_INVARIANT_VIOLATION: referential integrity failed: {detail}")


def warn_unregistered_constraint_kinds(tasks: Iterable[TaskDataSet]) -> list[str]:
    """Report constraint kinds outside the registered core, without failing.

    The vocabulary is deliberately open, so an unregistered kind is permitted.
    It still warns, because a typo such as ``prohibiton`` would otherwise
    fragment the very analysis the codes exist to support, and a kind used
    repeatedly is a candidate for promotion into the registry.

    Args:
        tasks (Iterable): Every loaded task.

    Returns:
        list[str]: The unregistered kinds encountered, sorted and deduplicated.
        An empty list means every kind was registered.
    """
    unregistered = {
        constraint.kind
        for task in tasks
        for constraint in task.constraints
        if not is_registered_constraint_kind(constraint.kind)
    }
    for kind in sorted(unregistered):
        logger.warning("QC_DATA_UNKNOWN_FIELD unregistered constraint kind %s", kind)
    return sorted(unregistered)


def _check_rubric_references(
    task: TaskDataSet, rules_by_id: dict[str, GoldenRuleSet]
) -> list[str]:
    """Apply R1: every ``rubric_id`` resolves to a rule set.

    Args:
        task (TaskDataSet): The task under check.
        rules_by_id (dict): Every loaded rule set, keyed by identifier.

    Returns:
        list[str]: One message per dangling reference.
    """
    return [
        f"R1 {task.task_id} references rubric {rule_id} which does not exist"
        for rule_id in task.rubric_ids
        if rule_id not in rules_by_id
    ]


def _check_constraint_references(task: TaskDataSet, rule: GoldenRuleSet) -> list[str]:
    """Apply R2: every ``constraint_ref`` resolves to a constraint that was sent.

    A check referencing an instruction the model never received grades it on
    something it was not told, which is an unfair test producing a finding about
    a model that did nothing wrong.

    Args:
        task (TaskDataSet): The joined task.
        rule (GoldenRuleSet): The joined rule set.

    Returns:
        list[str]: One message per unresolvable reference.
    """
    sent = {constraint.constraint_id for constraint in task.constraints}
    return [
        f"R2 {rule.rule_id} check {holder} references constraint {reference} "
        f"which {task.task_id} never sent"
        for holder, reference in _declared_constraint_refs(rule)
        if reference not in sent
    ]


def _check_every_constraint_is_checked(
    task: TaskDataSet, rules: list[GoldenRuleSet]
) -> list[str]:
    """Apply R3: every constraint sent is referenced by at least one check.

    **Across every rule the task names, not one of them.** A rule that
    specialises on one constraint is correct and was previously reported once
    per constraint it was not about. Design section 7.3.1 records what the pair
    scoping cost.

    Args:
        task (TaskDataSet): The joined task.
        rules (list): Every rule set the task names, already resolved.

    Returns:
        list[str]: One message per constraint that nothing verifies.
    """
    referenced = {
        reference
        for rule in rules
        for _, reference in _declared_constraint_refs(rule)
    }
    # NAMES EVERY RULE THAT WAS ASKED, because "no rule checks it" is only
    # actionable alongside which rules were consulted.
    consulted = ", ".join(rule.rule_id for rule in rules) or "no rule"
    return [
        f"R3 {task.task_id} sends constraint {constraint.constraint_id} which "
        f"none of {consulted} checks"
        for constraint in task.constraints
        if constraint.constraint_id not in referenced
    ]



def _check_adversarial_has_no_rubric(
    task: TaskDataSet, rule: GoldenRuleSet
) -> list[str]:
    """R6: refuse a rubric that can never be scored.

    **A declared adversarial case reaches no judge** (A19), so a rubric on its
    rule set is dead. Under ``tier3_evaluation.md`` section 4D an
    authored-but-unscored rubric does not pass, so the pair produces a case
    that can never pass and does not say why.

    That symptom has been corrected three times in this project, so the pair is
    refused here where it can be explained rather than left to surface as a
    mysterious red.

    Args:
        task (TaskDataSet): The task, carrying its adversarial declaration.
        rule (GoldenRuleSet): One rule set judging it.

    Returns:
        list[str]: One violation when a declared task pairs with a rubric,
        empty otherwise.
    """
    if not task.contains_adversarial_content or rule.rubric is None:
        return []
    logger.error(
        "QC_DATA_INVARIANT_VIOLATION %s declares adversarial content and %s "
        "authors a rubric", task.task_id, rule.rule_id,
    )
    return [
        f"QC_DATA_INVARIANT_VIOLATION: {task.task_id} declares adversarial "
        f"content, so it reaches no judge, and {rule.rule_id} authors a rubric "
        f"that can never be scored. Remove the rubric and grade by assertion"
    ]


def _check_tool_expectations(task: TaskDataSet, rule: GoldenRuleSet) -> list[str]:
    """Apply R4 and R5 to a joined task and rule set.

    R4 catches a vacuous test: forbidding a tool that was never offered proves
    nothing about the model. R5 repeats invariant G4 at the joined level, where
    a contradictory pair could otherwise arrive from two valid halves.

    Args:
        task (TaskDataSet): The joined task.
        rule (GoldenRuleSet): The joined rule set.

    Returns:
        list[str]: One message per violation.
    """
    expectation = rule.tool_expectation
    if expectation is None:
        return []
    offered = {tool.tool_name for tool in task.available_tools}
    expected = expectation.required_tools | expectation.forbidden_tools
    findings = [
        f"R4 {rule.rule_id} names tool {name} which {task.task_id} never offered"
        for name in sorted(expected - offered)
    ]
    overlap = sorted(expectation.required_tools & expectation.forbidden_tools)
    if overlap:
        findings.append(
            f"R5 {rule.rule_id} names {overlap} as both required and forbidden"
        )
    return findings


def _declared_constraint_refs(rule: GoldenRuleSet) -> list[tuple[str, str]]:
    """Collect every constraint reference a rule set declares, with its holder.

    The holder is carried so a message can say which check is at fault, rather
    than only which constraint is unresolved.

    Args:
        rule (GoldenRuleSet): The rule set to inspect.

    Returns:
        list[tuple[str, str]]: Pairs of holder identifier and referenced
        constraint identifier, covering assertions, rubric criteria and the tool
        expectation. All three can reference a constraint, and omitting any one
        would let R3 report a constraint as unchecked when something checks it.
    """
    refs: list[tuple[str, str]] = [
        (assertion.assertion_id, assertion.constraint_ref)
        for assertion in rule.assertions
        if assertion.constraint_ref is not None
    ]
    if rule.rubric is not None:
        refs.extend(
            (criterion.criterion_id, criterion.constraint_ref)
            for criterion in rule.rubric.criteria
            if criterion.constraint_ref is not None
        )
    if rule.tool_expectation is not None and rule.tool_expectation.constraint_ref is not None:
        refs.append(("tool_expectation", rule.tool_expectation.constraint_ref))
    return refs
