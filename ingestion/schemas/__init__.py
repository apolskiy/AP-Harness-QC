# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Frozen schema records and the validation applied at the ingestion boundary.

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
