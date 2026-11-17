# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Missing artifacts: the record naming one, the setup skip it causes, and the exit 3 it forces.

Created: 2026-11-16
Last updated: 2026-11-16

This file contains ``MissingArtifact``, the record of a file a case reads and
its own run does not produce, found absent, empty, unreadable or missing a
mandatory field; ``skip_for_missing_artifact``, which skips the case at setup
naming the artifact in its message, its JUnit properties and its Allure labels;
``missing_artifact_count``, which counts those skips; and
``refuse_missing_artifacts``, which makes the run exit 3 where any occurred.

A reader of an artifact decides at setup, before a request is formed, so a live
run spends nothing on a case it could not measure. The other cases run and
count, and the exit 3 at session end sends the gap for investigation: a missing
artifact is a test bug or an environment bug, never a model finding.

Design: ``docs/design/harness_test_taxonomy.md`` section 5.1.3.
"""

import logging
from dataclasses import dataclass
from typing import Any, Final, NoReturn

import pytest

logger = logging.getLogger(__name__)

ARTIFACT_MISSING: Final[str] = "QC_HARNESS_ARTIFACT_MISSING"

# A CLOSED SET, so an analysis of the stored results never meets a kind it
# cannot group (taxonomy section 5.1.3).
ARTIFACT_KINDS: Final[frozenset[str]] = frozenset({
    "recording",
    "judgement",
    "calibration_record",
    "carried_outcome",
    "spend_report",
    "corpus_pair",
})

_KIND_PROPERTY: Final[str] = "mqc_artifact_kind"
_PATH_PROPERTY: Final[str] = "mqc_artifact_path"
_MISSING_EXIT: Final[int] = 3


@dataclass(frozen=True)
class MissingArtifact:
    """A file a case reads, found absent or unusable.

    Attributes:
        kind (str): One of :data:`ARTIFACT_KINDS`.
        path (str): Where the artifact was looked for.
        detail (str): What was wrong with it: absent, empty, unparseable, or
            the mandatory field it lacks.
    """

    kind: str
    path: str
    detail: str

    def __post_init__(self) -> None:
        """Refuse a record naming no registered kind, no path or no explanation.

        Returns:
            None

        Raises:
            ValueError: Naming the field that is unusable.
        """
        if self.kind not in ARTIFACT_KINDS:
            raise ValueError(
                f"artifact kind {self.kind!r} is not one of {sorted(ARTIFACT_KINDS)}"
            )
        if not self.path.strip():
            raise ValueError(f"a missing {self.kind} names no path")
        if not self.detail.strip():
            raise ValueError(f"a missing {self.kind} at {self.path} says nothing about why")

    def message(self) -> str:
        """Return the skip message.

        Returns:
            str: ``QC_HARNESS_ARTIFACT_MISSING: <kind> <path>, <detail>``.
        """
        return f"{ARTIFACT_MISSING}: {self.kind} {self.path}, {self.detail}"


def skip_for_missing_artifact(item: Any, missing: MissingArtifact) -> NoReturn:
    """Skip the case at setup, naming the artifact wherever the result is read.

    The item gains the JUnit properties ``mqc_artifact_kind`` and
    ``mqc_artifact_path``, which pytest copies onto each phase report, and the
    Allure labels ``taxonomy_code``, ``artifact_kind`` and ``artifact_path`` as
    markers, which Allure reads at teardown.

    Args:
        item (Any): The pytest item being set up.
        missing (MissingArtifact): What it could not read.

    Returns:
        NoReturn: It always raises.

    Raises:
        pytest.skip.Exception: Carrying :meth:`MissingArtifact.message`.
    """
    item.user_properties.extend([
        (_KIND_PROPERTY, missing.kind), (_PATH_PROPERTY, missing.path),
    ])
    for label_type, value in (
        ("taxonomy_code", ARTIFACT_MISSING),
        ("artifact_kind", missing.kind),
        ("artifact_path", missing.path),
    ):
        item.add_marker(pytest.mark.allure_label(value, label_type=label_type))
    logger.warning("%s %s", getattr(item, "nodeid", "?"), missing.message())
    pytest.skip(missing.message())


def is_missing_artifact(report: Any) -> bool:
    """Report whether a phase report is a missing-artifact skip.

    Args:
        report (Any): A phase report from the reporter's statistics.

    Returns:
        bool: True where the report skipped and carries ``mqc_artifact_kind``.
    """
    if not getattr(report, "skipped", False):
        return False
    return any(
        name == _KIND_PROPERTY for name, _ in (getattr(report, "user_properties", None) or [])
    )


def missing_artifact_count(stats: dict[str, list[Any]]) -> int:
    """Count the cases skipped for a missing artifact.

    Args:
        stats (dict): The terminal reporter's statistics.

    Returns:
        int: How many skipped reports are missing-artifact skips.
    """
    return sum(1 for report in stats.get("skipped", []) if is_missing_artifact(report))


def refuse_missing_artifacts(session: Any) -> int:
    """Make the run exit 3 where any case skipped for a missing artifact.

    Args:
        session (Any): The finishing session, whose exit status is raised.

    Returns:
        int: How many cases skipped that way. **Zero leaves the exit status
        alone**, and so does a status already above 3.
    """
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return 0
    missing = missing_artifact_count(reporter.stats)
    if missing and int(session.exitstatus) < _MISSING_EXIT:
        logger.error(
            "%d case(s) skipped for a missing artifact, so the run exits 3: %s",
            missing, ARTIFACT_MISSING,
        )
        session.exitstatus = _MISSING_EXIT
    return missing
