# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Reading a registry of declared absences, which this project keeps writing.

Specified by ``harness_extensibility_standard.md`` section 3.4.

**The idiom appeared a fourth time and pylint reported the duplication.**
``flag_coverage.yaml`` declares a flag no case proves, ``not_rostered`` an
adapter that ships and cannot be selected, ``support_extraction.yaml`` a case
module still holding its helpers, and ``module_runway.yaml`` a module already
past nine hundred lines. Each reads the same shape and checks the same two
things, so each had its own copy of both.

**A gap is a declared absence, not an exemption.** Every entry carries a reason
and an expiry, because a list with no expiry is where unproven things go to be
forgotten and the check stops meaning anything once everything inconvenient has
left its denominator.
"""

import logging
from datetime import date
from pathlib import Path
from typing import Any

from cmn.config import load_yaml_config

logger = logging.getLogger(__name__)


def declared_entries(registry: Path, section: str) -> dict[str, dict[str, Any]]:
    """Return the entries one declaration section carries.

    Args:
        registry (Path): The declaration to read.
        section (str): The top-level key holding the entries.

    Returns:
        dict[str, dict]: Entry name to its record. **Empty when the file is
        absent**, which is the finished state rather than an error: removing
        the last entry deletes the file.
    """
    if not registry.is_file():
        return {}
    payload = load_yaml_config(registry)
    entries = payload.get(section) or {}
    if not isinstance(entries, dict):
        return {}
    return {
        str(name): record if isinstance(record, dict) else {}
        for name, record in entries.items()
    }


def lapsed_problems(
    name: str, record: dict[str, Any], as_of: date, subject: str
) -> list[str]:
    """Report what is wrong with one declared entry.

    Two things, and each is a different failure: an entry with no reason is an
    exemption wearing a declaration's clothes, and an entry past its expiry is
    work that stopped.

    Args:
        name (str): What the entry names, for the message.
        record (dict): The entry's record.
        as_of (date): The date expiries are judged against, injected so a check
            is not a function of when it runs.
        subject (str): What being declared means here, such as ``"not yet
            extracted"``, so one message reads correctly for each registry.

    Returns:
        list[str]: One message per problem, empty when the entry holds.
    """
    problems: list[str] = []
    if not str(record.get("reason") or "").strip():
        problems.append(
            f"{name} is declared {subject} with no reason, which makes it an "
            f"exemption rather than a declared absence"
        )

    expires = record.get("expires_on")
    if not isinstance(expires, date):
        problems.append(
            f"{name} is declared {subject} with no expiry, and a list with no "
            f"expiry is where unfinished work goes to be forgotten"
        )
    elif expires < as_of:
        problems.append(
            f"{name} has been declared {subject} since its expiry on "
            f"{expires.isoformat()}: {record.get('reason', '')!s}".strip()
        )
    return problems
