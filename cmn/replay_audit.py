# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Whether a replay store answers one question per case.

**A case holds one recording per observation and nothing required them to
answer the same request.** Three observations of one task carried one request
hash and the fourth and fifth carried another, left from before a prompt
changed, and nothing read them because the escalation rule never drew them.

**A store refreshed in part is worse than one wholly stale**, because the half
that loads looks current. Specified by ``cmn_verdict_and_cli.md`` section
12.4.1.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def divergent_recordings(root: Path, judgements: str = "judgements") -> list[str]:
    """Return every case whose recordings do not share one request hash.

    **Read from the files rather than from a run**, so a recording nothing
    currently draws is still checked: the one this exists for was unread for a
    day, and would have surfaced only when an escalation first reached it.

    **Judgements are excluded, and that is not an exemption.** A judgement
    scores one candidate response, so its request carries that response and
    every observation's judgement answers a legitimately different request.
    Requiring them to agree would report the whole store.

    Args:
        root (Path): The replay fixture root, holding one directory per engine.
        judgements (str): The subdirectory holding judgements, excluded for the
            reason above.

    Returns:
        list[str]: One sentence per divergent case, naming the engine, the
        case and how the hashes split. Empty where every case agrees.
    """
    problems: list[str] = []
    if not root.is_dir():
        return problems

    for folder in sorted(path for path in root.rglob("*") if path.is_dir()):
        if judgements in folder.relative_to(root).parts:
            continue
        recordings = sorted(folder.glob("*.json"))
        if len(recordings) < 2:
            continue
        seen: dict[str, list[str]] = {}
        for recording in recordings:
            try:
                payload = json.loads(recording.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                # A FILE THAT WILL NOT PARSE IS THE LOADER'S FINDING, not this
                # one, and reporting it twice would name one defect as two.
                continue
            digest = str(payload.get("request_hash", ""))
            if not digest:
                continue
            seen.setdefault(digest, []).append(recording.stem)
        if len(seen) < 2:
            continue
        split = "; ".join(
            f"{digest[:12]} on observation(s) {', '.join(sorted(names))}"
            for digest, names in sorted(seen.items())
        )
        relative = folder.relative_to(root).as_posix()
        logger.warning("QC_HARNESS_FIXTURE_STALE %s", relative)
        problems.append(
            f"{relative} holds recordings answering {len(seen)} different "
            f"requests, so some of them answer a question the corpus no "
            f"longer asks: {split}"
        )
    return problems
