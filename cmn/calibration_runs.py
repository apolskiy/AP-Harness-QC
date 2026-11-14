# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Decides which runs collect a calibration case, and what rests on it.

Created: 2026-11-10
Last updated: 2026-11-13

This file contains ``deselect_unrequested_calibration``, which deselects every
case carrying the ``calibration`` marker from a run whose marker expression
does not name it, and refuses a run that names it under a judge that is not
live; ``rest_judged_cases_on_calibration``, which makes each judged case depend
on its family's calibration case where the run collects both, where an
earlier job carried that case's outcome to a band session, or where a
calibration record was read, carrying every calibration case as not held when
that record is invalid; and ``calibration_marker``, the marker's name.

Both repositories' ``conftest.py`` call the deselection at collection, beside
the environment and audit deselection. A calibration case sends every
calibration sample of its family to a live judge
(``evaluation.calibration.calibrate_sample``), so it belongs
in the one run that asks for it and in no gate or stage that selects by layer.
The case repository calls the dependency wiring after its selectors, with the
family of each judged case, so a family whose calibration failed is skipped
with ``QC_HARNESS_DEPENDENCY_UNMET`` rather than reported.

Specified by ``docs/design/tier3_evaluation.md`` sections 9.2, 9.4, 9.4.1
and 9.4.2.
"""

import logging
import re
from typing import Any, Final, Mapping

import pytest

from cmn.calibration_record import calibration_identifiers, invalid_record_reason
from cmn.dependencies import adopt_carried_outcomes, carried_identifiers
from cmn.options import resolve_judge_mode
from cmn.pytest_support import case_identifier

logger = logging.getLogger(__name__)

_MARKER: Final[str] = "calibration"
_UNMET: Final[str] = "QC_HARNESS_DEPENDENCY_UNMET"

# NAMED, AND NOT NAMED TO BE EXCLUDED. `evaluator and not calibration` names
# the marker in order to leave it out, which is not a request.
_ASKED: Final[re.Pattern] = re.compile(r"(?<!not )\bcalibration\b")

_LIVE: Final[str] = "live"


def calibration_marker() -> str:
    """Return the marker a calibration case carries beside its layer marker.

    Returns:
        str: ``calibration``.
    """
    return _MARKER


def deselect_unrequested_calibration(config: Any, items: list[Any]) -> int:
    """Deselect every calibration case a run did not ask for.

    Design: ``tier3_evaluation.md`` section 9.2. A run asks by a marker
    expression naming ``calibration``. Deselected rather than skipped, so a
    case nobody asked for leaves the total.

    Args:
        config (Any): pytest's configuration, read for ``markexpr``, ``--mode``
            and ``--judge-mode``.
        items (list): The collected items, filtered in place.

    Returns:
        int: How many calibration cases were deselected.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the run asks for
            calibration and its judge is not live, since every sample would
            be scored by a stored reply or by none.
    """
    if _ASKED.search(str(config.getoption("markexpr", "") or "")):
        judge = resolve_judge_mode(
            str(config.getoption("--mode", "") or ""),
            str(config.getoption("--judge-mode", "") or ""),
        )
        if judge != _LIVE:
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: calibration was asked for with the judge "
                f"{judge or 'unset'}; it sends every calibration sample to a live judge, so it "
                f"needs --judge-mode live"
            )
        return 0
    drop = [item for item in items if item.get_closest_marker(_MARKER) is not None]
    if not drop:
        return 0
    config.hook.pytest_deselected(items=drop)
    items[:] = [item for item in items if item not in drop]
    logger.info("%d calibration case(s) deselected: the run did not ask for them", len(drop))
    return len(drop)


def rest_judged_cases_on_calibration(items: list[Any], families: Mapping[str, str]) -> int:
    """Make each judged case depend on its family's calibration case, collected or carried.

    Design: ``tier3_evaluation.md`` sections 9.4, 9.4.1 and 9.4.2. Each
    collected calibration case is marked ``base``, and each other collected
    case whose family has one, or whose family's calibration case an earlier
    job carried in the calibration layer's identifier block, gains a
    ``depends_on`` naming it, so the cascade skips the judged cases of a
    family whose calibration did not hold. Where the session read an invalid
    calibration record, every calibration case the mapping names is first
    carried as not held, with the record's reason. Called after every selector
    and before ``arrange_dependencies``, and after the carried outcomes and
    the calibration record are adopted.

    Args:
        items (list): The collected items, marked in place.
        families (Mapping[str, str]): Case name to family, naming every
            calibration case and the judged cases only.

    Returns:
        int: How many cases were made to depend on a calibration case.

    Raises:
        ValueError: With ``QC_HARNESS_DEPENDENCY_UNMET`` when a collected
            calibration case's family is not named, since no judged case could
            rest on it.
    """
    foundations: dict[str, list[str]] = {}
    for item in items:
        if item.get_closest_marker(_MARKER) is None:
            continue
        family = families.get(_case_name(item))
        identifier = case_identifier(item.name)
        if family is None or identifier is None:
            raise ValueError(
                f"{_UNMET}: calibration case {item.name} names no family, so no "
                f"judged case can rest on it"
            )
        item.add_marker(pytest.mark.base)
        foundations.setdefault(family, []).append(identifier)
    _carry_invalid_record(families)
    for identifier, family in _carried_calibration(families).items():
        if identifier not in foundations.get(family, []):
            foundations.setdefault(family, []).append(identifier)

    wired = 0
    for item in items:
        if item.get_closest_marker(_MARKER) is not None:
            continue
        resting_on = foundations.get(families.get(_case_name(item), ""), [])
        if resting_on:
            item.add_marker(pytest.mark.depends_on(*resting_on))
            wired += 1
    if wired:
        logger.info(
            "%d judged case(s) rest on the calibration of %s", wired, ", ".join(sorted(foundations))
        )
    return wired


def _carry_invalid_record(families: Mapping[str, str]) -> None:
    """Carry every calibration case as not held where the session's record is invalid.

    Design: ``tier3_evaluation.md`` section 9.4.2. The reason the record was
    read as invalid goes with each, so every judged case skips naming it
    before its judge is called.

    Args:
        families (Mapping[str, str]): Case name to family, naming every
            calibration case of the corpus.

    Returns:
        None
    """
    reason = invalid_record_reason()
    if reason is None:
        return
    calibrations = calibration_identifiers(families)
    adopt_carried_outcomes(
        {identifier: False for identifier in calibrations},
        {identifier: reason for identifier in calibrations},
    )


def _carried_calibration(families: Mapping[str, str]) -> dict[str, str]:
    """Return each carried calibration identifier with its family.

    Design: ``tier3_evaluation.md`` section 9.4.1. Only an identifier in the
    calibration layer's block is a calibration: the carried record also holds
    every foundation an earlier band established.

    Args:
        families (Mapping[str, str]): Case name to family, naming every
            calibration case of the corpus.

    Returns:
        dict[str, str]: Carried calibration identifier to its family.
    """
    carried = carried_identifiers()
    return {
        identifier: family
        for identifier, family in calibration_identifiers(families).items()
        if identifier in carried
    }


def _case_name(item: Any) -> str:
    """Return a collected case's callable name, without a parameter suffix.

    Args:
        item (Any): The collected item.

    Returns:
        str: ``originalname`` where pytest set one, otherwise ``name``.
    """
    return str(getattr(item, "originalname", None) or item.name)
