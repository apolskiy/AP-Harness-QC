# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Decides which runs collect a calibration case.

Created: 2026-11-10
Last updated: 2026-11-10

This file contains ``deselect_unrequested_calibration``, which deselects every
case carrying the ``calibration`` marker from a run whose marker expression
does not name it, and refuses a run that names it under a judge that is not
live; and ``calibration_marker``, the marker's name.

Both repositories' ``conftest.py`` call it at collection, beside the
environment and audit deselection. A calibration case sends every exemplar of
a rule to a live judge (``evaluation.calibration.calibrate``), so it belongs
in the one run that asks for it and in no gate or rung that selects by layer.

Specified by ``docs/design/tier3_evaluation.md`` section 9.2.
"""

import logging
import re
from typing import Any, Final

from cmn.options import resolve_judge_mode

logger = logging.getLogger(__name__)

_MARKER: Final[str] = "calibration"

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
            calibration and its judge is not live, since every exemplar would
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
                f"{judge or 'unset'}; it sends every exemplar to a live judge, so it "
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
