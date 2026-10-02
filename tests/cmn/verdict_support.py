# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The observations, suites and artifacts the verdict cases are built from.

Extracted 2026-10-02, when splitting the quarantine cases out of
``mqc_uni_verdict.py`` left three modules each carrying a copy of these.
Duplicated helpers drift, and a case comparing against a stale copy of a
passing suite reports about the copy.

**Not a test module.** ``pytest.ini`` collects ``mqc_*.py``, so this name is
deliberately outside that pattern, which is the same arrangement
``AP-Model-QC``'s ``graded_support.py`` uses.
"""

from datetime import date
from typing import Any

from cmn.observations import Observation

# The date every verdict case injects. The verdict reads no clock, so this is
# supplied rather than observed, and a fixed value keeps a boundary case from
# passing or failing by the calendar.
TODAY = date(2026, 9, 23)

# The case the quarantine cases quarantine. Named once because each of them
# asserts against the identifier the entry carries.
QUARANTINED_CASE = "MQC_TASK_q::MQC_RULE_r"


def graded(
    case_id: str, outcome: str = "pass", priority: int = 2, **extra: Any
) -> Observation:
    """Build one graded observation.

    Args:
        case_id (str): Which case.
        outcome (str): What it produced.
        priority (int): Its priority band.
        **extra: Any further field to set.

    Returns:
        Observation: The built record.
    """
    return Observation(
        case_id=case_id, layer="EVAL", outcome=outcome, priority=priority, **extra
    )


def passing_suite(count: int = 10) -> list[Observation]:
    """Build a suite that satisfies every rule.

    Args:
        count (int): How many graded observations to produce.

    Returns:
        list[Observation]: One passing precondition plus passing graded cases.
    """
    return [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")] + [
        graded(f"MQC_TASK_{index}::MQC_RULE_r") for index in range(count)
    ]


def gated_artifact(**overrides: Any) -> dict:
    """Build a gated artifact over a valid base.

    Args:
        **overrides: Fields to replace.

    Returns:
        dict: The artifact.
    """
    payload = {
        "gated": True,
        "run_context": "ci",
        "selection_mode": "full",
        "effective_thresholds": {},
        "results": [
            {"case_id": "MQC_TASK_pre::MQC_RULE_pre", "layer": "UNI",
             "outcome": "pass"},
            {"case_id": "MQC_TASK_a::MQC_RULE_r", "layer": "EVAL",
             "outcome": "pass", "priority": 2},
        ],
    }
    payload.update(overrides)
    return payload
