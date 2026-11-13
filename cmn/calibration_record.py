# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The calibration record a calibration session writes and a ladder reads.

Created: 2026-11-12
Last updated: 2026-11-12

This file contains ``CalibrationRecord``, the record's fields;
``write_calibration_record`` and ``read_calibration_record``, which store and
load it as JSON; ``record_invalidity``, which says why a record does not cover
the judge and samples now, or nothing when it does; ``adopt_calibration_record``,
which a session given ``--calibration-record`` under a live judge calls at
session start, adopting a valid record's families as carried calibration
outcomes and remembering an invalid record's reason; ``invalid_record_reason``,
which ``cmn.calibration_runs`` reads at collection to skip every judged case;
and ``publish_calibration_record``, which a session given
``--record-calibration`` calls at session end.

The case repository's ``conftest.py`` calls the adoption after the carried band
outcomes and the publication at session finish, with a digest of its
calibration samples, because the harness owns no case data.

Specified by ``docs/design/tier3_evaluation.md`` section 9.4.2.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Callable, Final, Mapping, Optional

from cmn.config import load_engines, load_judge_engine, load_judge_model, packaged_roster_path
from cmn.dependencies import adopt_carried_outcomes, established_outcomes
from cmn.layers import layer_properties
from cmn.options import resolve_judge_mode
from cmn.project_clock import project_today
from cmn.pytest_support import case_identifier

logger = logging.getLogger(__name__)

_PARSER: Final[str] = "QC_HARNESS_PARSER_ERROR"
_LIVE: Final[str] = "live"

ServedReader = Callable[[str, str], dict[str, str]]

# THE REASON A RECORD READ AT SESSION START DID NOT COVER THIS JUDGE, kept
# until collection, where the family mapping arrives and every judged case is
# wired to a calibration that did not hold. None where no record was read or
# the one read is valid.
_INVALID: dict[str, Optional[str]] = {"reason": None}


@dataclass(frozen=True)
class CalibrationRecord:
    """What one calibration session established about one judge.

    Attributes:
        judge_engine (str): The engine the samples were sent to.
        judge_model (str): The model the run named for it.
        judge_served_version (str): What the provider declared it served.
        judge_served_digest (str): The digest of that declaration.
        samples_digest (str): A digest of the calibration samples.
        code_ref (str): The harness commit.
        case_ref (str): The case repository commit.
        recorded (str): The UTC date, ISO format.
        families (dict): Family to ``{"identifier": str, "held": bool}``.
    """

    judge_engine: str
    judge_model: str
    judge_served_version: str
    judge_served_digest: str
    samples_digest: str
    code_ref: str
    case_ref: str
    recorded: str
    families: dict[str, dict[str, Any]] = field(default_factory=dict)


_FIELDS: Final[tuple[str, ...]] = tuple(entry.name for entry in fields(CalibrationRecord))


def reset_calibration_record_state() -> None:
    """Forget the reason a record read earlier in this process was invalid.

    Returns:
        None
    """
    _INVALID["reason"] = None


def invalid_record_reason() -> Optional[str]:
    """Return why the record this session read does not cover its judge.

    Returns:
        Optional[str]: The reason, or None where no record was read or it is
        valid.
    """
    return _INVALID["reason"]


def write_calibration_record(path: Path, record: CalibrationRecord) -> None:
    """Write a record as JSON, creating its directory.

    Args:
        path (Path): Where it goes.
        record (CalibrationRecord): What to write.

    Returns:
        None
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(record), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_calibration_record(path: Path) -> Optional[CalibrationRecord]:
    """Read a record, or nothing where none exists.

    Args:
        path (Path): The record.

    Returns:
        Optional[CalibrationRecord]: The record, None where the file is absent.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when it will not parse or
            lacks a field: a committed record that cannot be read is our
            defect, not an unmet prerequisite.
    """
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{_PARSER}: calibration record {path} will not parse: {error}") from error
    if not isinstance(loaded, dict):
        raise ValueError(f"{_PARSER}: calibration record {path} is not an object")
    missing = [name for name in _FIELDS if name not in loaded]
    if missing:
        raise ValueError(f"{_PARSER}: calibration record {path} lacks {', '.join(missing)}")
    families = loaded["families"]
    if not isinstance(families, dict) or not all(
        isinstance(entry, dict) and "identifier" in entry and "held" in entry
        for entry in families.values()
    ):
        raise ValueError(
            f"{_PARSER}: calibration record {path} gives a family without its "
            f"identifier and whether it held"
        )
    return CalibrationRecord(**{name: loaded[name] for name in _FIELDS})


def record_invalidity(record: Optional[CalibrationRecord], judge_engine: str,
                      served: Mapping[str, str], samples_digest: str) -> Optional[str]:
    """Return why a record does not cover the judge and samples now.

    Design: ``tier3_evaluation.md`` section 9.4.2. Age never invalidates it.

    Args:
        record (Optional[CalibrationRecord]): The record read, None if absent.
        judge_engine (str): The judge engine this session uses.
        served (Mapping[str, str]): What the judge serves now, empty where it
            could not be read.
        samples_digest (str): The digest of the calibration samples now.

    Returns:
        Optional[str]: The reason, or None for a valid record.
    """
    if record is None:
        return f"no calibration record for the judge {judge_engine}"
    if record.judge_engine != judge_engine:
        return (
            f"the calibration record calibrated the judge {record.judge_engine}, "
            f"not {judge_engine}"
        )
    if record.samples_digest != samples_digest:
        return f"the calibration samples changed since the record of {record.recorded}"
    if not served.get("served_digest"):
        return (
            f"the judge {judge_engine}'s served identity could not be read, so nothing "
            f"establishes it is the judge calibrated on {record.recorded}"
        )
    if served["served_digest"] != record.judge_served_digest:
        return (
            f"the judge {judge_engine} now serves {served.get('served_version', '')}, and "
            f"the record of {record.recorded} calibrated {record.judge_served_version}"
        )
    return None


def adopt_calibration_record(config: Any, samples_digest: str, *,
                             served_reader: Optional[ServedReader] = None) -> Optional[str]:
    """Read the record a session names, and adopt its families or its reason.

    Design: ``tier3_evaluation.md`` section 9.4.2. Called at session start,
    after the carried band outcomes. A valid record's families become carried
    calibration outcomes, a family that did not hold carrying why; an invalid
    record's reason is kept for ``cmn.calibration_runs`` to apply at
    collection.

    Args:
        config (Any): pytest's configuration, read for ``--calibration-record``,
            ``--mode``, ``--judge-mode`` and ``--judge-engine``.
        samples_digest (str): The digest of the calibration samples now.
        served_reader (Optional[ServedReader]): Reads what the judge serves,
            ``execution.preflight.served_facts`` by default.

    Returns:
        Optional[str]: Why the record is invalid, or None where it is valid or
        nothing was read.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the record will not
            parse or lacks a field.
    """
    named = str(config.getoption("--calibration-record", "") or "")
    if not named or _judge_mode(config) != _LIVE:
        return None
    engine, model = _judge(config)
    record = read_calibration_record(Path(named))
    served = (served_reader or _served_facts)(engine, model) if record is not None else {}
    reason = record_invalidity(record, engine, served, samples_digest)
    if record is None or reason is not None:
        reason = f"{reason} at {named}"
        _INVALID["reason"] = reason
        logger.warning("Calibration record invalid, every judged case will skip: %s", reason)
        return reason
    outcomes = {str(entry["identifier"]): bool(entry["held"]) for entry in record.families.values()}
    reasons = {
        str(entry["identifier"]): (
            f"the calibration of {family} did not hold when recorded on {record.recorded}"
        )
        for family, entry in record.families.items() if not entry["held"]
    }
    adopt_carried_outcomes(outcomes, reasons)
    logger.info(
        "Calibration record of %s adopted for %d famil(ies), %d held",
        record.recorded, len(outcomes), sum(outcomes.values()),
    )
    return None


def publish_calibration_record(config: Any, samples_digest: str, families: Mapping[str, str], *,
                               served_reader: Optional[ServedReader] = None) -> Optional[Path]:
    """Write what this calibration session established about its judge.

    Design: ``tier3_evaluation.md`` section 9.4.2. A calibration case that
    did not run is recorded as not held, since it measured nothing.

    Args:
        config (Any): pytest's configuration, read for ``--record-calibration``
            and ``--judge-engine``.
        samples_digest (str): The digest of the calibration samples.
        families (Mapping[str, str]): Case name to family, naming every
            calibration case.
        served_reader (Optional[ServedReader]): Reads what the judge serves,
            ``execution.preflight.served_facts`` by default.

    Returns:
        Optional[Path]: The record written, None where the session named none
        or measured no calibration case.
    """
    named = str(config.getoption("--record-calibration", "") or "")
    if not named:
        return None
    established = established_outcomes()
    calibrations = calibration_identifiers(families)
    if not any(identifier in established for identifier in calibrations):
        logger.warning("No calibration case ran, so no calibration record was written to %s", named)
        return None
    engine, model = _judge(config)
    served = (served_reader or _served_facts)(engine, model)
    record = CalibrationRecord(
        judge_engine=engine,
        judge_model=model,
        judge_served_version=served.get("served_version", ""),
        judge_served_digest=served.get("served_digest", ""),
        samples_digest=samples_digest,
        code_ref=os.environ.get("MQC_CODE_REF", ""),
        case_ref=os.environ.get("MQC_CASE_REF", ""),
        recorded=project_today().isoformat(),
        families={
            family: {"identifier": identifier, "held": established.get(identifier, False)}
            for identifier, family in calibrations.items()
        },
    )
    path = Path(named)
    write_calibration_record(path, record)
    logger.info("Calibration record of %s written to %s", engine, path)
    return path


def calibration_identifiers(families: Mapping[str, str]) -> dict[str, str]:
    """Return the mapping's names in the calibration layer's block, by identifier.

    Args:
        families (Mapping[str, str]): Case name to family.

    Returns:
        dict[str, str]: Identifier to family.
    """
    low, high = layer_properties("CAL").id_block
    found: dict[str, str] = {}
    for name, family in families.items():
        identifier = case_identifier(name)
        if identifier is not None and identifier.isdigit() and low <= int(identifier) <= high:
            found[identifier] = family
    return found


def _judge_mode(config: Any) -> str:
    """Return the mode the judge runs in.

    Args:
        config (Any): pytest's configuration.

    Returns:
        str: ``live``, ``replay`` or empty.
    """
    return resolve_judge_mode(
        str(config.getoption("--mode", "") or ""),
        str(config.getoption("--judge-mode", "") or ""),
    )


def _judge(config: Any) -> tuple[str, str]:
    """Return the judge engine and model this session uses.

    Resolved as ``execution.judge_channel.judge_channel_from_roster`` does:
    the named engine's roster model, or the configured judge.

    Args:
        config (Any): pytest's configuration, read for ``--judge-engine``.

    Returns:
        tuple[str, str]: Engine and model.
    """
    roster_path = packaged_roster_path()
    roster = load_engines(roster_path)
    requested = str(config.getoption("--judge-engine", "") or "")
    if requested:
        entry = roster.get(requested)
        return requested, entry.model if entry is not None else ""
    return load_judge_engine(roster_path), load_judge_model(roster_path, roster)


def _served_facts(engine: str, model: str) -> dict[str, str]:
    """Ask the judge's provider what it serves.

    Imported when called: ``execution`` imports ``cmn``, and nothing in
    ``cmn`` imports ``execution`` at load.

    Args:
        engine (str): The judge engine.
        model (str): The judge model.

    Returns:
        dict[str, str]: ``served_version`` and ``served_digest``, empty on failure.
    """
    from execution.preflight import served_facts  # pylint: disable=import-outside-toplevel
    return served_facts(engine, model)
