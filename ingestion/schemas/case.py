# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The record for one evaluation case, a task paired with one rule set that judges it.

Created: 2026-10-18
Last updated: 2026-10-21

This file contains :class:`EvaluationCase`, which holds the case identifier,
the task, the rule set and the priority carried from the rule set.

**It is built, never authored.** :func:`ingestion.cases.build_evaluation_cases`
creates one per task and rubric pair, and the run dispatches, evaluates and
gates by priority one case at a time.

Design: ``docs/design/tier1_ingestion.md`` sections 3.0 and 3.11.
"""

import logging
from dataclasses import dataclass

from ingestion.schemas.task import (
    TaskDataSet,
)
from ingestion.schemas.rules import (
    GoldenRuleSet,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvaluationCase:
    """One (task by rubric) unit, derived rather than authored.

    Invariant G5: this stays a data type. No scoring, no dispatch, no engine
    knowledge. It has no ``from_dict`` because nobody authors one; a factory
    builds it from a task and a rule set after the join.

    Attributes:
        case_id (str): ``<task_id>::<rule_id>``, stable across runs.
        task (TaskDataSet): What was sent.
        golden_rules (GoldenRuleSet): How it is judged.
        priority (int): Carried from the rule set, for the verdict gate.
    """

    case_id: str
    task: TaskDataSet
    golden_rules: GoldenRuleSet
    priority: int
