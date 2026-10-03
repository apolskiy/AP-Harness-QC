# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Programmatic injection screening at the ingestion boundary.

Specified by ``docs/design/tier1_ingestion.md`` section 7. This is the first of
three screens (A5); the others cover candidate output and judge replies and
belong to Tiers 2 and 3.

**What this screen is for:** catching injection-shaped content that entered our
own fixtures by accident. It is not a defence against a hostile model, because
nothing hostile has run yet.

**The trap it works around:** an injection-resistance test case must contain an
injection payload. Blanket screening would reject precisely the fixtures that
matter most, so a case declaring ``contains_adversarial_content`` bypasses the
screen and says so in the record. Declared, never silent.

**Detection is programmatic and never a model call.** A model asked to detect
injection is itself injectable, which relocates the problem rather than solving
it. Being deterministic also makes the screen unit-testable, which a model call
would not be.

**Detection is a measurement, not the defence.** Structural isolation is the
defence and it lives in Tier 3, where it covers everything the harness did not
author rather than the candidate output alone (A19). This module therefore
**reports** findings and does not decide what happens next.

**An undeclared match warns and does not abort** (A19), logging
``QC_DATA_UNDECLARED_ADVERSARIAL``. That is a decision rather than leniency: a
payload surviving ingest is the only case where this screen and the Tier 3
screen meet real accidental input, and aborting would destroy the measurement to
prevent nothing, since isolation applies either way.
"""

import logging
from dataclasses import dataclass
from typing import Iterable

from cmn.vectors import match_vectors
from ingestion.schemas import TaskDataSet

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScreenFinding:
    """One injection-shaped match in one field of one record.

    Attributes:
        task_id (str): Which task carried it.
        field_name (str): Which field, so an author can find it.
        vector (str): The registered vector name that matched.
        excerpt (str): A short excerpt around the match, for the record.
    """

    task_id: str
    field_name: str
    vector: str
    excerpt: str


def screen_task(task: TaskDataSet) -> list[ScreenFinding]:
    """Screen one task's authored text for injection-shaped content.

    A task declaring ``contains_adversarial_content`` is **not** screened. That
    is the documented opt-out for injection-resistance fixtures, which must
    contain a payload to be worth anything. The bypass is recorded at WARNING,
    so a declared case is visible in the record rather than silently skipped.

    Args:
        task (TaskDataSet): The task to screen.

    Returns:
        list[ScreenFinding]: Every match, empty when the task is clean or
        declared adversarial. **The caller decides what a finding means**:
        detection here is a measurement, and the defence is structural
        isolation in Tier 3.
    """
    if task.contains_adversarial_content:
        logger.warning(
            "QC_DATA_ADVERSARIAL_DECLARED %s declared adversarial; ingest screen bypassed",
            task.task_id,
        )
        return []

    findings: list[ScreenFinding] = []
    for field_name, text in _screenable_fields(task):
        findings.extend(_screen_text(task.task_id, field_name, text))
    return findings


def screen_corpus(tasks: Iterable[TaskDataSet]) -> list[ScreenFinding]:
    """Screen every task in a loaded corpus.

    Args:
        tasks (Iterable): Every loaded task.

    Returns:
        list[ScreenFinding]: Every match across the corpus, in task order.
    """
    return [finding for task in tasks for finding in screen_task(task)]


def _screenable_fields(task: TaskDataSet) -> list[tuple[str, str]]:
    """Return every authored text field of a task, named for reporting.

    Context documents are included because retrieval payloads are exactly where
    an injection would sit in a real attack, and a fixture that carries one
    accidentally is what this screen exists to find.

    Args:
        task (TaskDataSet): The task to inspect.

    Returns:
        list[tuple[str, str]]: Pairs of field name and text.
    """
    fields: list[tuple[str, str]] = [("user_prompt", task.user_prompt)]
    if task.system_instruction is not None:
        fields.append(("system_instruction", task.system_instruction))
    fields.extend(
        (f"context_documents[{document.document_id}]", document.content)
        for document in task.context_documents
    )
    fields.extend(
        (f"constraints[{constraint.constraint_id}]", constraint.text)
        for constraint in task.constraints
    )
    return fields


def _screen_text(task_id: str, field_name: str, text: str) -> list[ScreenFinding]:
    """Apply every registered vector to one field.

    The vectors come from ``cmn.vectors`` rather than from this module, so
    the Tier 3 screen looks for exactly the same things. `MQC_EVL_UNI_114608`
    asserts the two agree, and a second copy of the patterns would make that
    assertion a comparison that drifts (design section 7.2).

    Args:
        task_id (str): Owning task, for the finding.
        field_name (str): Owning field, for the finding.
        text (str): The authored text.

    Returns:
        list[ScreenFinding]: One finding per vector that matched. A field
        matching several vectors yields several findings, because the vectors
        describe different attacks and collapsing them would lose that.
    """
    findings = [
        ScreenFinding(task_id, field_name, match.vector, match.excerpt)
        for match in match_vectors(text)
    ]
    for finding in findings:
        logger.warning(
            "QC_DATA_UNDECLARED_ADVERSARIAL %s field %s matched %s",
            task_id, field_name, finding.vector,
        )
    return findings
