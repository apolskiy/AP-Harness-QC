# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Decides which runs collect a calibration case, and what rests on it.

Created: 2026-11-10
Last updated: 2026-11-11

This file contains ``deselect_unrequested_calibration``, which deselects every
case carrying the ``calibration`` marker from a run whose marker expression
does not name it, and refuses a run that names it under a judge that is not
live; ``rest_judged_cases_on_calibration``, which makes each judged case depend
on its family's calibration case where the run collects both; and
``calibration_marker``, the marker's name.

Both repositories' ``conftest.py`` call the deselection at collection, beside
the environment and audit deselection. A calibration case sends every
calibration sample of its family to a live judge
(``evaluation.calibration.calibrate_sample``), so it belongs
in the one run that asks for it and in no gate or rung that selects by layer.
The case repository calls the dependency wiring after its selectors, with the
family of each judged case, so a family whose calibration failed is skipped
with ``QC_HARNESS_DEPENDENCY_UNMET`` rather than reported.

Specified by ``docs/design/tier3_evaluation.md`` sections 9.2 and 9.4.
"""

import logging
import re
from typing import Any, Final, Mapping

import pytest

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
    """Make each judged case depend on its family's calibration case, where both are collected.

    Design: ``tier3_evaluation.md`` section 9.4. Each collected calibration
    case is marked ``base``, and each other collected case whose family has
    one gains a ``depends_on`` naming it, so the cascade skips the judged
    cases of a family whose calibration did not hold. Called after every
    selector and before ``arrange_dependencies``.

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


def _case_name(item: Any) -> str:
    """Return a collected case's callable name, without a parameter suffix.

    Args:
        item (Any): The collected item.

    Returns:
        str: ``originalname`` where pytest set one, otherwise ``name``.
    """
    return str(getattr(item, "originalname", None) or item.name)
