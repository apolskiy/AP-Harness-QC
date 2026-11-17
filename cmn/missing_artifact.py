# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Missing artifacts: the record naming one, the skip it causes, and the exit 3 it forces.

Created: 2026-11-16
Last updated: 2026-11-17

This file contains ``MissingArtifact``, the record of a file a case reads and
its own run does not produce, found absent, empty, unreadable or missing a
mandatory field; ``skip_for_missing_artifact``, which skips the case at setup
naming the artifact in its message, its JUnit properties and its Allure labels;
``raise_missing_artifact`` and ``MissingArtifactSkip``, the same skip raised
from a case's call, which ``label_missing_artifact_skip`` labels from the
makereport hook; ``skip_unreplayed_case``, which skips a replay case whole once
its observations show a missing or stale judgement;
``declared_missing_artifact`` and ``skip_declared_missing``, which read
``--missing-artifact`` and skip every graded case it covers at setup;
``missing_artifact_count``,
which counts those skips; and ``refuse_missing_artifacts``, which makes the run
exit 3 where any occurred.

A reader of an artifact decides at setup, before a request is formed, so a live
run spends nothing on a case it could not measure. The other cases run and
count, and the exit 3 at session end sends the gap for investigation: a missing
artifact is a test bug or an environment bug, never a model finding.

A replay case is the exception, decided once its observations have replayed,
because which judgements it needs is known only then; replay spends nothing.

Design: ``docs/design/harness_test_taxonomy.md`` sections 5.1.3 to 5.1.3.2.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Final, NoReturn, Optional

import pytest

from cmn.environments import is_precondition

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

# A JUDGEMENT THE PIPELINE COULD NOT READ, and the code a stale one carries
# (`tier3_evaluation.md` section 6.5).
_UNAVAILABLE: Final[str] = "judgement_unavailable"
_STALE: Final[str] = "QC_HARNESS_FIXTURE_STALE"

# AN ARTIFACT A CI STEP FOUND MISSING BEFORE PYTEST STARTED (taxonomy section
# 5.1.3.2).
_DECLARED_FLAG: Final[str] = "--missing-artifact"
_DECLARED_DETAIL: Final[str] = "declared missing to this run by --missing-artifact"


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


class MissingArtifactSkip(pytest.skip.Exception):
    """pytest's skip, carrying the artifact that caused it.

    Raised during a case's call, where no item is in reach, so the makereport
    hook can label the result from it (taxonomy section 5.1.3.1).

    Attributes:
        missing (MissingArtifact): What the case could not read.
    """

    def __init__(self, missing: MissingArtifact) -> None:
        """Build the skip, its message the artifact's.

        Args:
            missing (MissingArtifact): What the case could not read.

        Returns:
            None
        """
        super().__init__(missing.message())
        self.missing = missing


def _properties(missing: MissingArtifact) -> list[tuple[str, str]]:
    """Return the JUnit properties naming one missing artifact.

    Args:
        missing (MissingArtifact): The artifact.

    Returns:
        list[tuple[str, str]]: ``mqc_artifact_kind`` and ``mqc_artifact_path``.
    """
    return [(_KIND_PROPERTY, missing.kind), (_PATH_PROPERTY, missing.path)]


def _add_labels(item: Any, missing: MissingArtifact) -> None:
    """Add the Allure label markers naming one missing artifact to an item.

    Args:
        item (Any): The pytest item.
        missing (MissingArtifact): The artifact.

    Returns:
        None
    """
    for label_type, value in (
        ("taxonomy_code", ARTIFACT_MISSING),
        ("artifact_kind", missing.kind),
        ("artifact_path", missing.path),
    ):
        item.add_marker(pytest.mark.allure_label(value, label_type=label_type))


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
    item.user_properties.extend(_properties(missing))
    _add_labels(item, missing)
    logger.warning("%s %s", getattr(item, "nodeid", "?"), missing.message())
    pytest.skip(missing.message())


def declared_missing_artifact(config: Any) -> Optional[MissingArtifact]:
    """Return the artifact ``--missing-artifact KIND=PATH`` declares missing, if any.

    Args:
        config (Any): pytest's configuration.

    Returns:
        Optional[MissingArtifact]: The artifact, or ``None`` where the flag is
        absent or empty.

    Raises:
        pytest.UsageError: Naming the flag and its value, where the value has no
            ``=``, names a kind outside :data:`ARTIFACT_KINDS` or an empty path.
    """
    value = str(config.getoption(_DECLARED_FLAG, "") or "").strip()
    if not value:
        return None
    kind, separator, path = value.partition("=")
    if not separator:
        raise pytest.UsageError(f"{_DECLARED_FLAG} {value!r} names no path; give KIND=PATH")
    try:
        return MissingArtifact(kind=kind.strip(), path=path.strip(), detail=_DECLARED_DETAIL)
    except ValueError as error:
        raise pytest.UsageError(f"{_DECLARED_FLAG} {value!r}: {error}") from error


def skip_declared_missing(item: Any) -> None:
    """Skip a graded case at setup where the run declares an artifact missing.

    Called from a consumer's ``pytest_runtest_setup``. A precondition runs.

    Args:
        item (Any): The pytest item being set up.

    Returns:
        None: Where nothing is declared, or the item is a precondition.

    Raises:
        pytest.skip.Exception: Through :func:`skip_for_missing_artifact`.
    """
    missing = declared_missing_artifact(item.config)
    if missing is None or is_precondition(str(getattr(item, "nodeid", ""))):
        return
    skip_for_missing_artifact(item, missing)


def raise_missing_artifact(missing: MissingArtifact) -> NoReturn:
    """Skip the case from inside its call, carrying the artifact for the makereport hook.

    Args:
        missing (MissingArtifact): What the case could not read.

    Returns:
        NoReturn: It always raises.

    Raises:
        MissingArtifactSkip: Carrying the artifact and its message.
    """
    logger.warning("%s", missing.message())
    raise MissingArtifactSkip(missing)


def label_missing_artifact_skip(item: Any, call: Any, report: Any) -> bool:
    """Label a phase that raised :class:`MissingArtifactSkip` as a setup skip is labelled.

    The item gains the JUnit properties and the Allure label markers, which
    Allure reads at teardown, and the report gains the properties, pytest having
    copied the item's before this runs. The report's reason becomes
    ``Skipped: <message>``, as a plain skip's reads, where pytest had written the
    class's qualified name. Called from the makereport hook.

    Args:
        item (Any): The pytest item.
        call (Any): The phase's call information.
        report (Any): The phase's report.

    Returns:
        bool: True where the phase raised the skip and was labelled.
    """
    raised = getattr(getattr(call, "excinfo", None), "value", None)
    if not isinstance(raised, MissingArtifactSkip):
        return False
    item.user_properties.extend(_properties(raised.missing))
    report.user_properties.extend(_properties(raised.missing))
    _add_labels(item, raised.missing)
    longrepr = getattr(report, "longrepr", None)
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        report.longrepr = (longrepr[0], longrepr[1], f"Skipped: {raised.missing.message()}")
    return True


def skip_unreplayed_case(results: Iterable[Any]) -> None:
    """Skip the whole case where any observation's judgement is missing or stale in replay.

    Read once every observation has replayed, since which judgements a case
    needs is known only then. A judgement unavailable for any other reason, an
    unreachable or a withheld judge, is left to the caller (taxonomy section
    5.1.3.1).

    Args:
        results (Iterable[Any]): One evaluation result per observation, in order.

    Returns:
        None: Where no observation carries a replay gap.

    Raises:
        MissingArtifactSkip: For the first observation whose judgement is
            absent or unreadable, naming it.
        pytest.skip.Exception: With ``QC_HARNESS_FIXTURE_STALE`` for the first
            whose judgement no longer answers its request.
    """
    for index, entry in enumerate(results):
        missing = getattr(entry, "missing_artifact", None)
        if missing is not None:
            raise_missing_artifact(missing)
        stale = getattr(entry, "judge_skipped_reason", None) == _UNAVAILABLE and _STALE in (
            getattr(entry, "taxonomy_codes", None) or ()
        )
        if stale:
            pytest.skip(
                f"{_STALE}: the judgement of observation {index} no longer answers its "
                f"request, so the case was not decided on the others; re-record it"
            )


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
