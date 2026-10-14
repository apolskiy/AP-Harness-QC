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


def distribution_suite(at_zero: int, at_one: int, total: int) -> list[Observation]:
    """Build a passing suite with an exact priority distribution.

    **The denominator is chosen by the caller** so a share lands on a ceiling
    rather than near it, which is what the boundary cases in
    ``mqc_uni_thresholds.py`` need and what section 8.2 of
    ``cmn_verdict_and_cli.md`` tabulates.

    Args:
        at_zero (int): How many case definitions sit at P0.
        at_one (int): How many sit at P1.
        total (int): How many case definitions there are in all.

    Returns:
        list[Observation]: A passing precondition followed by ``total``
        passing graded observations, one per case definition.

    Raises:
        ValueError: When the two bands together exceed the total.
    """
    if at_zero + at_one > total:
        raise ValueError(
            f"{at_zero} at P0 and {at_one} at P1 exceed a total of {total}"
        )
    built = [Observation("MQC_TASK_pre::MQC_RULE_pre", "UNI", "pass")]
    built += [
        graded(f"MQC_TASK_z{index}::MQC_RULE_r", priority=0) for index in range(at_zero)
    ]
    built += [
        graded(f"MQC_TASK_o{index}::MQC_RULE_r", priority=1) for index in range(at_one)
    ]
    built += [
        graded(f"MQC_TASK_t{index}::MQC_RULE_r", priority=3)
        for index in range(total - at_zero - at_one)
    ]
    return built


def scored_observations(case_id: str, scores: list[float]) -> list[Observation]:
    """Build one case's judged observations.

    Args:
        case_id (str): The case every observation belongs to.
        scores (list[float]): One score per observation.

    Returns:
        list[Observation]: The observations, all passing.
    """
    return [
        Observation(case_id, "EVAL", "pass", priority=2, score=score)
        for score in scores
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
