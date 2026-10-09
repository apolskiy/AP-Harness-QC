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
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final

logger = logging.getLogger(__name__)


# WHICH BANDS MAY NOT REST ON AN ABSENCE. A blocking band answers for every
# case it selected, so an unmeasured one cannot be rounded up; a lower band is
# governed by a pass floor and a missing recording costs it coverage instead
# (`AP-Model-QC` `consumer_ci.md` section 3.12.4).
_BLOCKING_PRIORITIES: Final[frozenset[int]] = frozenset({0, 1})


def missing_recordings(
    root: Path,
    engines: Iterable[str],
    cases: Mapping[str, Any],
    fixtures: str = "tests/fixtures/replay",
) -> list[str]:
    """Report every blocking-band case with no recording for a rostered engine.

    **A missing recording is an absence the floor cannot tell from a refusal.**
    A provider declining a prompt is a measurement and is recorded as one; no
    recording at all means the case was never asked, and a blocking band built
    on that establishes nothing.

    **It fails rather than being declarable.** A case that is not selected is
    never recorded and never executed, so a tolerated gap is a permanent one
    (section 3.12.4).

    Args:
        root (Path): The case repository root.
        engines (Iterable[str]): The rostered candidate engines.
        cases (Mapping[str, Any]): Case identifier to the joined case, each
            carrying ``golden_rules.priority``.
        fixtures (str): Where recordings live, relative to the root.

    Returns:
        list[str]: One entry per missing pair, naming the engine, the case and
        what closes it. Sorted, so two runs report in the same order.
    """
    store = root / fixtures
    problems: list[str] = []
    for engine in sorted(set(engines)):
        for case_id, case in sorted(cases.items()):
            priority = getattr(getattr(case, "golden_rules", None), "priority", None)
            if priority not in _BLOCKING_PRIORITIES:
                continue
            task, _, rule = str(case_id).partition("::")
            folder = store / engine / task / rule
            if folder.is_dir() and any(folder.glob("*.json")):
                continue
            problems.append(
                f"{engine} has no recording for P{priority} case {case_id}, so a "
                f"blocking band would skip it rather than measure it; record it "
                f"with a live run"
            )
    if problems:
        logger.error(
            "%d blocking-band case(s) have no recording, so a band would rest "
            "on an absence", len(problems),
        )
    return problems


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
