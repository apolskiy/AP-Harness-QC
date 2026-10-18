# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The join of a task and a rule set into the case that is run.

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
