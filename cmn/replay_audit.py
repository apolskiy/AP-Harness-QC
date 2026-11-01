# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Replay store audit, which checks the recorded responses a replay run reads.

Created: 2026-10-07
Last updated: 2026-11-01

This file contains ``missing_recordings``, which reports a blocking-band case
with no recording for a rostered engine; ``divergent_recordings``, which
reports a case whose recordings, judgements aside, do not share one request
hash; and ``stale_judgements``, which reports a judgement whose recorded
prompt does not hold the response its own candidate recording holds.

The case repository's precondition cases call all three against its replay
fixtures, so a store that is incomplete or refreshed in part fails the unit
layer before a replay run trusts it.

**A case holds one recording per observation and nothing required them to
answer the same request.** Three observations of one task carried one request
hash and the fourth and fifth carried another, left from before a prompt
changed, and nothing read them because the escalation rule never drew them.

**A store refreshed in part is worse than one wholly stale**, because the half
that loads looks current. The same guard sits one step away on the judgement
side: a judgement is refused on its request hash by the run that draws it, so
a judgement the escalation never reaches is refused by nothing. Specified by
``cmn_verdict_and_cli.md`` sections 12.4.1 and 12.4.2.
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
# (`AP-Model-QC` `consumer_ci.md` section 3.12.6).
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
    (section 3.12.6).

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


def stale_judgements(root: Path, judgements: str = "judgements") -> list[str]:
    """Return every judgement that does not hold the response it scored.

    **Read from the files rather than from a run**, for the reason
    ``divergent_recordings`` is: ``load_judgement`` refuses a judgement whose
    request hash moved, and it refuses it on the run that draws it, so a
    judgement no escalation reaches is refused by nothing.

    **The recorded prompt is what makes the comparison possible here.** It
    carries the candidate response verbatim, so a judgement is compared with
    the recording it scored without composing a request, loading a rubric or
    reading the corpus, none of which this module may do.

    **A judgement carrying no prompt is an abstention, not a tolerance.** One
    recorded before the prompt was stored is rebuilt from the observation it
    scored, so it replays correctly and holds nothing to compare; reporting it
    would report the age of a file as a defect.

    Args:
        root (Path): The replay fixture root, holding one directory per engine
            and the judgement subtree beside them.
        judgements (str): The subdirectory holding judgements.

    Returns:
        list[str]: One sentence per finding, naming both engines, the case and
        the observation. Sorted, so two runs report in the same order.
    """
    problems: list[str] = []
    store = root / judgements
    if not store.is_dir():
        return problems

    for judgement in sorted(store.rglob("*.json")):
        parts = judgement.relative_to(store).parts
        if len(parts) != 5:
            # A FILE AT ANOTHER DEPTH IS NOT A JUDGEMENT. `JudgementKey.path`
            # writes candidate, judge, task, rule and observation, and nothing
            # else is loadable as a judgement at all.
            continue
        candidate_engine, judge_engine, task_id, rule_id, name = parts
        subject = (
            f"{task_id}::{rule_id} observation {name.removesuffix('.json')}, "
            f"produced by {candidate_engine} and judged by {judge_engine}"
        )
        recording = root / candidate_engine / task_id / rule_id / name
        if not recording.is_file():
            logger.warning("QC_HARNESS_FIXTURE_STALE %s", "/".join(parts))
            problems.append(
                f"{subject} is judged and has no recording, so the judgement "
                f"outlived the response it scored and no run can draw it to "
                f"find out; record the observation or remove the judgement"
            )
            continue
        prompt = _prompt_of(judgement)
        if not prompt:
            continue
        scored = _response_text(recording)
        if not scored or scored in prompt:
            continue
        logger.warning("QC_HARNESS_FIXTURE_STALE %s", "/".join(parts))
        problems.append(
            f"{subject} was scored against a response the recording no longer "
            f"holds, so a run drawing it skips on a stale fixture rather than "
            f"reading a score; the recording holds {len(scored)} characters "
            f"the {len(prompt)}-character prompt does not carry"
        )
    return problems


def _prompt_of(judgement: Path) -> str:
    """Return the rendered prompt a stored judgement carries.

    Args:
        judgement (Path): The judgement fixture.

    Returns:
        str: The prompt with line endings normalized, empty where the file
        carries none or will not parse. **An unparsable file is the loader's
        finding**, and reporting it here would name one defect as two.
    """
    try:
        payload = json.loads(judgement.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(payload.get("prompt", "") or "").replace("\r\n", "\n")


def _response_text(recording: Path) -> str:
    """Return the candidate text a recording holds.

    Args:
        recording (Path): The candidate fixture.

    Returns:
        str: The response text, stripped and with line endings normalized.
        Empty where the file will not parse or records no text, a response
        carrying none being a block or a refusal rather than a comparison.
    """
    try:
        payload = json.loads(recording.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    response = payload.get("response")
    if not isinstance(response, dict):
        return ""
    return str(response.get("text", "") or "").replace("\r\n", "\n").strip()
