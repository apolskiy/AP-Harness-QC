# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The quarantine file loader, which reads one engine's entries into records.

Created: 2026-11-15
Last updated: 2026-11-15

This file contains ``load_quarantine``, which reads one
``quarantine/<engine>.yaml`` into ``QuarantineEntry`` records and refuses an
entry without a reason or a ticket, and ``load_quarantine_for``, which finds
that file for an engine beneath a configuration directory.

A consumer reads its quarantine through these at collection and asks
``cmn.quarantine.in_force_cases`` which entries hold their case out; the verdict
tool reads them to report what was quarantined. The directory is **the
consumer's**, which owns the graded cases an entry can be about.

**Split from ``cmn/config.py`` on 2026-11-15**, when the entry's two new fields
took that module past a thousand lines (``code-style.md`` section 5.1). It
imports the configuration reader, and nothing in ``cmn/config.py`` imports it,
so the two cannot form a cycle.

Specified by ``docs/design/cmn_verdict_and_cli.md`` sections 4.6.3, 4.6.4 and
4.6.15.
"""

import re
from pathlib import Path
from typing import Final

from cmn.config import coerce_date, load_yaml_config
from cmn.quarantine import QuarantineEntry

# WHAT A TICKET REFERENCE MAY LOOK LIKE. An absolute URL, or a tracker key of
# the PROJECT-123 shape. Required since 2026-11-15 (design section 4.6.15), and
# validated because nothing else reads it: an annotation nothing reads is where a typo
# survives, and the point of the field is that somebody can follow it later.
_TICKET_REFERENCE: Final[re.Pattern] = re.compile(
    r"^(?:https?://\S+|[A-Z][A-Z0-9]+-\d+)$"
)

# WHERE A QUARANTINE FILE LIVES, one per engine. Design section 4.6.3.
_QUARANTINE_DIRECTORY: Final[str] = "quarantine"


def load_quarantine(path: Path) -> list[QuarantineEntry]:
    """Load one engine's quarantine list.

    **An absent file is an empty quarantine**, which is the default state and
    needs no file to say so.

    An entry missing ``quarantined_on`` or ``observed_model`` loads as
    unconfirmed rather than being refused: the condition is our bookkeeping
    failing and is reported as ``QC_HARNESS_QUARANTINE_UNCONFIRMED``, never as
    a parse failure or a red run (design section 4.6.4).

    ``originally_quarantined_on`` takes ``quarantined_on`` where the file
    omits it, and ``ends_on_model_change`` defaults to ``true`` (design section
    4.6.15).

    Args:
        path (Path): The file.

    Returns:
        list[QuarantineEntry]: Every entry, each carrying what provenance it
        has.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when an entry carries no
            reason, no ticket, a ticket reference that is neither a URL nor a
            tracker key, or an ``ends_on_model_change`` that is not a boolean.
    """
    loaded = load_yaml_config(path)
    entries: list[QuarantineEntry] = []
    for entry in loaded.get("quarantine") or []:
        if not entry.get("reason"):
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: quarantine entry "
                f"{entry.get('case_id')!r} in {path} carries no reason"
            )
        ticket = str(entry.get("ticket") or "")
        # A CASE IS NEVER HELD OUT WITHOUT AN ISSUE AGAINST IT, or it becomes
        # an untracked bug nobody sees. Design section 4.6.15.
        if not ticket:
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: quarantine entry "
                f"{entry.get('case_id')!r} in {path} carries no ticket, and a "
                f"case cannot be quarantined without an issue opened against it"
            )
        if not _TICKET_REFERENCE.match(ticket):
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: quarantine entry "
                f"{entry.get('case_id')!r} in {path} carries the ticket "
                f"reference {ticket!r}, which is neither an absolute URL nor a "
                f"tracker key of the PROJECT-123 shape, so nobody can follow it"
            )
        # THE DISPENSATION TAKES THE SAME VALIDATION AS THE TICKET, and for a
        # stronger reason: it is the only thing that lets a blocker release,
        # and a reference nobody can follow records that somebody said so
        # rather than what was decided. Design section 4.6.13.
        accepted = str(entry.get("release_accepted_in") or "")
        if accepted and not _TICKET_REFERENCE.match(accepted):
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: quarantine entry "
                f"{entry.get('case_id')!r} in {path} accepts a release in "
                f"{accepted!r}, which is neither an absolute URL nor a tracker "
                f"key of the PROJECT-123 shape, so the decision cannot be read"
            )
        stamped = entry.get("quarantined_on")
        held = coerce_date(stamped, path) if stamped else None
        # THE DAY THE HOLD BEGAN NEVER MOVES; an entry written before the
        # field existed takes the one date it has. Design section 4.6.15.
        began = entry.get("originally_quarantined_on")
        ends = entry.get("ends_on_model_change", True)
        if not isinstance(ends, bool):
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: quarantine entry "
                f"{entry.get('case_id')!r} in {path} sets ends_on_model_change "
                f"to {ends!r}, which is not true or false"
            )
        entries.append(
            QuarantineEntry(
                case_id=str(entry["case_id"]),
                reason=str(entry["reason"]),
                quarantined_on=held,
                observed_model=str(entry.get("observed_model") or ""),
                ticket=ticket,
                release_accepted_in=accepted,
                originally_quarantined_on=coerce_date(began, path) if began else held,
                ends_on_model_change=ends,
            )
        )
    return entries


def load_quarantine_for(config_dir: Path, engine: str) -> list[QuarantineEntry]:
    """Load the quarantine list for one engine.

    Reads ``quarantine/<engine>.yaml`` beneath ``config_dir``. **An unnamed
    engine or an absent file yields nothing**, so a run that names no engine
    does no expiry work.

    Design: ``cmn_verdict_and_cli.md`` section 4.6.3.

    Args:
        config_dir (Path): Where the configuration files live.
        engine (str): The candidate engine, whose findings the entries record.

    Returns:
        list[QuarantineEntry]: Every entry for that engine.
    """
    if not engine:
        return []
    return load_quarantine(
        config_dir / _QUARANTINE_DIRECTORY / f"{engine}.yaml"
    )
