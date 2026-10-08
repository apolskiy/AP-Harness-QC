# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Builders the metadata cases assert against.

Specified by ``harness_test_taxonomy.md`` section 13.

**Extracted 2026-10-05**, when ``mqc_uni_metadata.py`` stood at 998 lines
against the thousand-line ceiling. The module is a list of claims about
metadata; a valid observation to vary and a requirement-name parser are the
apparatus those claims need, and apparatus is not a claim.

**Public names, deliberately.** These were ``_graded`` and
``_requirement_name`` while they were private to one module. A support module
is an interface, and a leading underscore on something another module imports
says the opposite of what is true.
"""

import re
from typing import Any, Optional

from cmn.observations import Observation


def graded_observation(**overrides: Any) -> Observation:
    """Build a graded observation over a valid base.

    Args:
        **overrides: Fields to replace.

    Returns:
        Observation: The built record.
    """
    payload = {
        "case_id": "MQC_TASK_a::MQC_RULE_r", "layer": "EVAL", "outcome": "pass",
        "priority": 2, "engine": "gemini", "mode": "replay",
        "requested_model": "gemini-flash-latest", "resolved_model": "gemini-flash-002",
        "duration": 310, "duration_kind": "measured",
    }
    payload.update(overrides)
    return Observation(**payload)


def requirement_name(entry: str) -> Optional[str]:
    """Return the distribution name a requirement string begins with.

    Args:
        entry (str): A requirement such as ``pylint>=3.3,<4.0``.

    Returns:
        Optional[str]: The name, or ``None`` where the entry carries no name
        this simply, such as a URL requirement. **None rather than a guess**,
        because a wrong name would silently report a tool as unpinned.
    """
    found = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", entry.strip())
    return found.group(1) if found is not None else None
