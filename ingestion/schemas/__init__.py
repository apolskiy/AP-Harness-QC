# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The typed records every loaded task and rule set becomes, under one import.

Created: 2026-10-18
Last updated: 2026-10-21

This package re-exports every schema record from the files that define them:
the task side, :class:`TaskDataSet` with :class:`Constraint`,
:class:`ContextDocument` and :class:`ToolDefinition`; the rule side,
:class:`GoldenRuleSet` with :class:`ProgrammaticAssertion`,
:class:`ToolExpectation`, :class:`Rubric`, :class:`RubricCriterion` and
:class:`Anchor`; the joined :class:`EvaluationCase`; and
``canonical_identifier``.

**The loaders build these records, and everything downstream reads them.**
Execution sends a task, evaluation judges against a rule set, and a record
that fails validation raises at load, so nothing later sees malformed data.

Specified by ``docs/design/tier1_ingestion.md`` sections 3 and 5. Every record
is a frozen dataclass with a ``from_dict`` classmethod, because an ingested
record is evidence rather than working state.

**The boundary rule** the field placement follows: :class:`TaskDataSet` is what
is sent to the model, :class:`GoldenRuleSet` is how the response is judged. The
same tool legitimately appears in both, as a definition on one side and an
expectation on the other.

Validation here reports **every** problem it finds rather than the first, on the
grounds that an author fixing hand-written data wants the whole list. Missing
and empty are different authoring errors carrying different codes: a missing
field was forgotten, an empty one had a placeholder left in it, and the fix
differs.

**One file per schema type, behind this one import** (design section 3.0).
Every public name is re-exported here, so no importer moves.
"""

from ingestion.schemas.fields import (
    canonical_identifier,
)
from ingestion.schemas.task import (
    Constraint,
    ContextDocument,
    ToolDefinition,
    TaskDataSet,
)
from ingestion.schemas.rubric import (
    Anchor,
    RubricCriterion,
    Rubric,
)
from ingestion.schemas.rules import (
    ProgrammaticAssertion,
    ToolExpectation,
    GoldenRuleSet,
)
from ingestion.schemas.case import (
    EvaluationCase,
)

__all__ = [
    "canonical_identifier",
    "Constraint",
    "ContextDocument",
    "ToolDefinition",
    "TaskDataSet",
    "Anchor",
    "RubricCriterion",
    "Rubric",
    "ProgrammaticAssertion",
    "ToolExpectation",
    "GoldenRuleSet",
    "EvaluationCase",
]
