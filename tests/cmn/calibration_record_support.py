# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The judge identities and family mapping the calibration record's cases use.

Created: 2026-11-12
Last updated: 2026-11-12

This file contains ``SERVED``, ``MOVED`` and ``UNREADABLE``, readers standing in
for ``execution.preflight.served_facts`` that return a judge's served identity,
a different one, and none; ``FAMILIES``, a case name to family mapping holding
two calibration cases and two judged cases; ``record_options``, which builds the
options a session reading or writing a record carries; ``write_record``, which
writes a record as a calibration session would; ``forget_record_state``, which
clears what a case adopted; and the case names those mappings use.

``mqc_uni_calibration_record.py`` imports them. It sits in a sibling module
because collection does not reach this file, and `MQC_CMN_UNI_112328` reports
support code defined inside a collected case module.

Specified by ``docs/design/tier3_evaluation.md`` section 9.4.2.
"""

from pathlib import Path
from typing import Callable, Final

from cmn.calibration_record import publish_calibration_record, reset_calibration_record_state
from cmn.dependencies import adopt_carried_outcomes, reset_dependency_state
from tests.cmn.mutation_tool_support import AuditConfig

CAL_FIDELITY: Final[str] = "MQC_EVL_CAL_174906_source_fidelity_exemplars_score_at_their_levels"
CAL_SHAPE: Final[str] = "MQC_EVL_CAL_174903_output_shape_exemplars_score_at_their_levels"
JUDGED_FIDELITY: Final[str] = "MQC_CAS_EVAL_134910_a_source_fidelity_case"
JUDGED_SHAPE: Final[str] = "MQC_CAS_EVAL_134911_an_output_shape_case"
UNJUDGED: Final[str] = "MQC_CAS_EVAL_134912_a_case_graded_by_assertion_alone"

FAMILIES: Final[dict[str, str]] = {
    CAL_FIDELITY: "source_fidelity", CAL_SHAPE: "output_shape",
    JUDGED_FIDELITY: "source_fidelity", JUDGED_SHAPE: "output_shape",
}

SAMPLES_DIGEST: Final[str] = "a1b2c3d4e5f60718"


def _served(version: str, digest: str) -> Callable[[str, str], dict[str, str]]:
    """Return a reader standing in for ``served_facts`` that always answers the same.

    Args:
        version (str): The served version it reports.
        digest (str): The served digest it reports.

    Returns:
        Callable: Taking an engine and a model, returning the served facts.
    """
    def read(engine: str, model: str) -> dict[str, str]:
        """Return the fixed served identity, whatever is asked.

        Args:
            engine (str): The judge engine, unused.
            model (str): The judge model, unused.

        Returns:
            dict[str, str]: ``served_version`` and ``served_digest``.
        """
        del engine, model
        return {"served_version": version, "served_digest": digest}
    return read


def _unreadable(engine: str, model: str) -> dict[str, str]:
    """Stand in for a provider whose served identity could not be read.

    Args:
        engine (str): The judge engine, unused.
        model (str): The judge model, unused.

    Returns:
        dict[str, str]: Empty, as ``served_facts`` returns on failure.
    """
    del engine, model
    return {}


SERVED: Final[Callable[[str, str], dict[str, str]]] = _served("claude-opus-5-5", "00aa11bb22cc33dd")
MOVED: Final[Callable[[str, str], dict[str, str]]] = _served("claude-opus-5-6", "99ff88ee77dd66cc")
UNREADABLE: Final[Callable[[str, str], dict[str, str]]] = _unreadable


def forget_record_state() -> None:
    """Forget every outcome and record reason a case adopted.

    Returns:
        None
    """
    reset_dependency_state()
    reset_calibration_record_state()


def write_record(tmp_path: Path, outcomes: dict[str, bool], *, judge: str = "claude") -> Path:
    """Write a record as a calibration session would, and forget the session.

    Args:
        tmp_path (Path): Where the record goes.
        outcomes (dict): Calibration identifier to whether it held.
        judge (str): The judge engine the session named.

    Returns:
        Path: The record.
    """
    path = tmp_path / "calibration" / f"{judge}.json"
    options = record_options(write=path)
    options["--judge-engine"] = judge
    forget_record_state()
    adopt_carried_outcomes(outcomes)
    publish_calibration_record(AuditConfig(tmp_path, [], options), SAMPLES_DIGEST, FAMILIES,
                               served_reader=SERVED)
    forget_record_state()
    return path


def record_options(*, read: Path | None = None, write: Path | None = None,
                   judge_mode: str = "live") -> dict[str, str]:
    """Return the options a session reading or writing a calibration record carries.

    Args:
        read (Path | None): The record to read, ``--calibration-record``.
        write (Path | None): The record to write, ``--record-calibration``.
        judge_mode (str): ``--judge-mode``; the candidate is always replayed.

    Returns:
        dict[str, str]: Option name to value.
    """
    return {
        "--mode": "replay", "--judge-mode": judge_mode, "--judge-engine": "claude",
        "--calibration-record": str(read) if read else "",
        "--record-calibration": str(write) if write else "",
    }
