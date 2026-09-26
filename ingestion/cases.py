# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Construction of the evaluation case set from loaded tasks and rule sets.

Specified by ``docs/design/tier1_ingestion.md`` section 3.11. The
(task by rubric) pair is the unit of evaluation (A11, B10), so a task naming
three rubrics yields three cases and each is counted, prioritized and reported
separately.

**Cases are derived, never authored.** :class:`~ingestion.schemas.EvaluationCase`
has no ``from_dict`` for that reason, and this module is the only thing that
builds one.

**Invariant G5: the case stays a data type.** No scoring, no dispatch, no engine
knowledge. That is enforced by the architecture fitness function in design
section 11 rather than by convention, and this module keeps the factory
separate from the record so the record has nothing to attach behaviour to.
"""

import logging
from typing import Iterable

from ingestion.schemas import EvaluationCase, GoldenRuleSet, TaskDataSet, canonical_identifier

logger = logging.getLogger(__name__)

# Chosen so a case identifier stays readable and splits unambiguously: neither
# half may contain it, because a task or rule identifier that did would already
# have been refused as unsafe for a path segment.
_CASE_ID_SEPARATOR = "::"


def build_case_id(task_id: str, rule_id: str) -> str:
    """Compose the identifier for one (task by rubric) pair.

    Args:
        task_id (str): The task half.
        rule_id (str): The rule set half.

    Returns:
        str: ``<task_id>::<rule_id>``. Stable across runs by construction, since
        it derives only from two authored identifiers and nothing about when or
        where the run happened.
    """
    return f"{task_id}{_CASE_ID_SEPARATOR}{rule_id}"


def build_evaluation_cases(
    tasks: Iterable[TaskDataSet], rule_sets: Iterable[GoldenRuleSet]
) -> list[EvaluationCase]:
    """Join tasks to rule sets, producing one case per pair.

    Referential integrity is **not** re-checked here. R1 already establishes
    that every ``rubric_id`` resolves, and repeating the check would give two
    places to maintain one rule. A rule set that cannot be found at this point
    is a programming error rather than a data error, so it raises rather than
    being collected as a finding.

    Args:
        tasks (Iterable): Every loaded task.
        rule_sets (Iterable): Every loaded rule set.

    Returns:
        list[EvaluationCase]: One case per (task, rubric) pair, in task order
        then rubric order, so a run's case list is reproducible.

    Raises:
        KeyError: When a task names a rule set that was not loaded, which means
            referential integrity did not run before this did.
        ValueError: When two pairs produce identifiers that collide on a
            case-insensitive filesystem.
    """
    rules_by_id = {rule.rule_id: rule for rule in rule_sets}
    cases: list[EvaluationCase] = []
    for task in tasks:
        for rule_id in task.rubric_ids:
            rule = rules_by_id.get(rule_id)
            if rule is None:
                raise KeyError(
                    f"QC_DATA_INVARIANT_VIOLATION: {task.task_id} names rule set {rule_id} "
                    f"which was not loaded; referential integrity must run before case building"
                )
            cases.append(
                EvaluationCase(
                    case_id=build_case_id(task.task_id, rule.rule_id),
                    task=task,
                    golden_rules=rule,
                    priority=rule.priority,
                )
            )
    _reject_colliding_case_ids(cases)
    logger.info("Built %d evaluation cases from %d tasks", len(cases), len(list(rules_by_id)))
    return cases


def _reject_colliding_case_ids(cases: list[EvaluationCase]) -> None:
    """Raise when two case identifiers collide on a case-insensitive filesystem.

    Both halves are screened individually at ingest, so a collision here needs
    two pairs whose **combination** collides while neither half does. That is
    unlikely and worth catching anyway: a case identifier becomes a fixture
    directory, and a silent reuse corrupts replay on one platform only.

    Args:
        cases (list): The built cases.

    Returns:
        None

    Raises:
        ValueError: Naming each colliding group.
    """
    grouped: dict[str, list[str]] = {}
    for case in cases:
        grouped.setdefault(canonical_identifier(case.case_id), []).append(case.case_id)
    collisions = sorted(
        sorted(set(group)) for group in grouped.values() if len(set(group)) > 1
    )
    if collisions:
        logger.error("QC_DATA_IDENTIFIER_UNSAFE case identifier collisions %s", collisions)
        raise ValueError(
            f"QC_DATA_IDENTIFIER_UNSAFE: case identifiers differ only by letter case or "
            f"Unicode form and collide on a case-insensitive filesystem: {collisions}"
        )


def count_unique_case_definitions(cases: Iterable[EvaluationCase]) -> int:
    """Count distinct case definitions, which is the distribution denominator.

    A case observed three times is **one** definition. The distribution ceilings
    are measured over definitions rather than observations, because counting
    observations would let the repeat-run count change a percentage that is
    supposed to describe the suite's shape.

    Args:
        cases (Iterable): The built cases.

    Returns:
        int: The number of distinct case identifiers.
    """
    return len({case.case_id for case in cases})
