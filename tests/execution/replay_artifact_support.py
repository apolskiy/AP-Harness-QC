# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unreadable recordings and judgements, for the cases feeding the replay store a bad file.

Created: 2026-11-17
Last updated: 2026-11-17

This file contains ``UNREADABLE_RECORDINGS`` and ``MALFORMED_JUDGEMENTS``, one
body per way a recording or a judgement can exist and be unusable;
``write_body``, which writes one where the store looks for it;
``raised_missing``, which returns the ``FixtureMissing`` a load raised; and the
case identifier and judge model ``mqc_uni_replay_artifacts.py`` reads them
under.
"""

from pathlib import Path
from typing import Any, Callable, Final

import pytest

from execution.replay import FixtureMissing

CASE_ID: Final[str] = "MQC_TASK_alpha::MQC_RULE_grounding"
JUDGE_MODEL: Final[str] = "gemini-2.5-flash"

# ONE BODY PER WAY A RECORDING CAN EXIST AND BE UNUSABLE, each read as missing
# rather than stale, since none carries a hash to compare (`tier2_execution.md`
# section 7.6.2).
UNREADABLE_RECORDINGS: Final[dict[str, str]] = {
    "empty": "",
    "not JSON": "{ truncated",
    "not an object": "[]",
    "no request hash": '{"resolved_model": "m", "response": {"text": "t"}}',
    "no response": '{"request_hash": "h", "resolved_model": "m"}',
    "response not a mapping": '{"request_hash": "h", "resolved_model": "m", "response": []}',
}

# ONE BODY PER WAY A JUDGEMENT CAN EXIST AND BE UNUSABLE.
MALFORMED_JUDGEMENTS: Final[dict[str, str]] = {
    "empty": "",
    "not JSON": "{ truncated",
    "not an object": "[]",
    "no request hash": '{"judge_model": "gemini-2.5-flash", "reply": {}}',
    "no judge model": '{"request_hash": "sha256:any", "reply": {}}',
    "no reply": '{"request_hash": "sha256:any", "judge_model": "gemini-2.5-flash"}',
}


def raised_missing(call: Callable[[], Any]) -> FixtureMissing:
    """Return the ``FixtureMissing`` a load raised, failing where it raised another error.

    Args:
        call (Callable): The load, taking no arguments.

    Returns:
        FixtureMissing: What it raised.
    """
    with pytest.raises(FixtureMissing) as caught:
        call()
    return caught.value


def write_body(path: Path, body: str) -> Path:
    """Write a body where the store looks for a recording or judgement.

    Args:
        path (Path): The file the store reads.
        body (str): What to write.

    Returns:
        Path: The path written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path
