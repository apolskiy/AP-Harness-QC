# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Stand-ins for the observations and the pytest call a replay-gap skip reads.

Created: 2026-11-17
Last updated: 2026-11-17

This file contains ``observation``, one evaluated observation measured or
carrying a gap; ``MISSING_JUDGEMENT``, the record of a judgement the store
could not find; ``call_raising`` and ``ReportDouble``, the call and report a
makereport hook hands ``cmn.missing_artifact.label_missing_artifact_skip``; and
``CALL_TIME_CONFTEST`` and ``CALL_TIME_CASES``, a wired session whose case
raises the skip during its call. ``mqc_uni_replay_gap.py`` reads them.
"""

from types import SimpleNamespace
from typing import Any, Final, Optional

from cmn.missing_artifact import ARTIFACT_MISSING, MissingArtifact

MISSING_JUDGEMENT: Final[MissingArtifact] = MissingArtifact(
    kind="judgement",
    path="tests/fixtures/replay/judgements/gemini/gemini/MQC_TASK_a/MQC_RULE_a/1.json",
    detail="is absent: no judgement of MQC_TASK_a::MQC_RULE_a observation 1",
)


def observation(
    *, passed: bool = True, unavailable: str = "", missing: Optional[MissingArtifact] = None,
    withheld: bool = False,
) -> Any:
    """Return one evaluated observation, measured or carrying a gap.

    Args:
        passed (bool): Whether it passed, for a measured one.
        unavailable (str): The code a judgement unavailable carries, empty
            where the judgement was available.
        missing (Optional[MissingArtifact]): The judgement replay could not use.
        withheld (bool): Whether the judge was withheld on request.

    Returns:
        Any: An object answering what an ``EvaluationResult`` answers here.
    """
    reason = "unjudged" if withheld else ("judgement_unavailable" if unavailable else None)
    return SimpleNamespace(
        passed=passed and not reason,
        judge_skipped_reason=reason,
        taxonomy_codes=[unavailable] if unavailable else [],
        missing_artifact=missing,
    )


def call_raising(error: BaseException) -> Any:
    """Return the call of a phase that raised one error.

    Args:
        error (BaseException): What the phase raised.

    Returns:
        Any: An object answering ``excinfo.value`` as pytest's ``CallInfo`` does.
    """
    return SimpleNamespace(excinfo=SimpleNamespace(value=error))


class ReportDouble:
    """A phase report reduced to what the labelling writes to."""

    def __init__(self) -> None:
        """Start skipped, with no properties.

        Returns:
            None
        """
        self.skipped = True
        self.user_properties: list[tuple[str, Any]] = []


# A CASE RAISING THE SKIP DURING ITS CALL, as a case holding no item must.
CALL_TIME_CONFTEST: Final[str] = '''
from typing import Any

import pytest

from cmn.missing_artifact import label_missing_artifact_skip, refuse_missing_artifacts


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: Any, call: Any) -> Any:
    outcome = yield
    label_missing_artifact_skip(item, call, outcome.get_result())


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    refuse_missing_artifacts(session)
'''

CALL_TIME_CASES: Final[str] = '''
from cmn.missing_artifact import MissingArtifact, raise_missing_artifact


def test_raises_in_its_call() -> None:
    raise_missing_artifact(MissingArtifact(
        kind="recording", path="replay/gemini/MQC_TASK_a/MQC_RULE_a/2.json",
        detail="is absent",
    ))


def test_has_its_artifacts() -> None:
    assert True
'''

CALL_TIME_MESSAGE: Final[str] = (
    f"{ARTIFACT_MISSING}: recording replay/gemini/MQC_TASK_a/MQC_RULE_a/2.json"
)
