# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Base outcomes carried between the band executions of one job.

Specified by ``docs/design/cmn_verdict_and_cli.md`` section 7.6.

**Only the outcome is carried, never the test.** The cascade crosses priority
bands: a P2 case depends on a P1 case, which is the normal shape rather than an
accident. Inside a CI sequence the P1 execution has already run it, so carrying
the test would re-run work reported minutes ago and, where it failed, would
colour the later band with a failure belonging to an earlier one.

**A base that did not hold still skips its dependents.** That is the property
lost by the obvious alternative of treating an absent base as non-gating: a P2
case would run and report a measurement presupposing something known to be
false.

**The record is validated and a mismatch refuses.** A carried outcome is
cross-run state, the category that fails silently: a stale record would let a
dependent pass on a foundation established against different code, different
rules or a different engine, and nothing would look wrong. The two available
fallbacks are both worse than stopping, since re-running the prerequisites is
the waste this avoids and assuming the foundation held is an assertion nobody
measured.
"""

import json
import logging
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Final, Iterable, Optional

logger = logging.getLogger(__name__)

_ENCODING: Final[str] = "utf-8"

_MISMATCH: Final[str] = "QC_HARNESS_PREREQUISITE_MISMATCH"
_PARSER: Final[str] = "QC_HARNESS_PARSER_ERROR"

# The fields a carried record must match on, in the order a mismatch reports
# them. `rule_set_hash` leads because it is the primary guard: a commit
# reference cannot see an uncommitted edit, and corpus edits between executions
# are normal working (`test_taxonomy.md` section 9.1.1).
_GUARDED: Final[tuple[str, ...]] = (
    "rule_set_hash", "code_ref", "case_ref", "engine", "mode", "platform",
)


def rule_set_digest(rule_sets: Iterable[Any]) -> str:
    """Return a content hash over the rules a run loaded.

    **The loaded records rather than the file bytes.** Hashing the YAML would
    make every comment edit a different corpus, and this project comments its
    corpus heavily: one session correcting eight assertions also rewrote the
    prose around them. Hashing what was parsed means the hash moves when the
    rules move.

    **Canonicalised before hashing**, with keys sorted and content normalised
    to LF, so the digest does not depend on how a file was checked out
    (``code-style.md`` section 8).

    Args:
        rule_sets (Iterable): The loaded rule records, typed loosely so this
            does not import Tier 1's schema for one attribute walk.

    Returns:
        str: ``sha256:`` and the digest, or the empty string for no rules,
        which is what a harness run with no corpus legitimately has.
    """
    summary: list[dict[str, Any]] = []
    for rules in rule_sets:
        summary.append(
            {
                "rule_id": str(getattr(rules, "rule_id", "")),
                "priority": getattr(rules, "priority", None),
                "conditions": sorted(
                    str(entry) for entry in getattr(rules, "priority_conditions", ())
                ),
                "assertions": [
                    {
                        "assertion_id": str(getattr(check, "assertion_id", "")),
                        "kind": str(getattr(check, "kind", "")),
                        "parameters": _canonical(getattr(check, "parameters", {})),
                    }
                    for check in getattr(rules, "assertions", ())
                ],
                "rubric": _canonical(_rubric_summary(getattr(rules, "rubric", None))),
            }
        )
    if not summary:
        return ""
    summary.sort(key=lambda entry: entry["rule_id"])
    payload = json.dumps(summary, sort_keys=True, ensure_ascii=True)
    return f"sha256:{sha256(payload.encode(_ENCODING)).hexdigest()}"


def _rubric_summary(rubric: Any) -> dict[str, Any]:
    """Return the parts of a rubric that change what a judge is asked.

    Args:
        rubric (Any): The rubric record, or ``None`` for a deterministic rule.

    Returns:
        dict: Its criteria, anchors and threshold, empty when absent.
    """
    if rubric is None:
        return {}
    criteria = []
    for criterion in getattr(rubric, "criteria", ()):
        criteria.append(
            {
                "criterion_id": str(getattr(criterion, "criterion_id", "")),
                "anchors": _canonical(getattr(criterion, "anchors", {})),
            }
        )
    return {"criteria": criteria, "threshold": getattr(rubric, "threshold", None)}


def _canonical(value: Any) -> Any:
    """Return a JSON-serialisable form with text normalised to LF.

    Args:
        value (Any): Any parsed corpus value.

    Returns:
        Any: The same value, with strings normalised and mappings made plain.
    """
    if isinstance(value, str):
        return value.replace("\r\n", "\n").replace("\r", "\n")
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if hasattr(value, "__dict__"):
        return _canonical(vars(value))
    return value


@dataclass(frozen=True)
class Provenance:
    """What a carried record must match to be admitted.

    Attributes:
        rule_set_hash (str): Which rules produced the outcomes. **The primary
            guard**, because it moves on an uncommitted edit and a commit
            reference does not.
        code_ref (str): The harness commit.
        case_ref (str): The corpus commit. Separate from ``code_ref``, which
            folded both before the repository split.
        engine (str): Which provider.
        mode (str): Observed or replayed.
        platform (str): The harness is verified on two, and a foundation
            holding on one and not the other is the case the band topology
            exists to surface.
        band (str): Which selection wrote the record, for the log rather than
            for matching: a later band legitimately reads an earlier band's.
    """

    rule_set_hash: str = ""
    code_ref: str = ""
    case_ref: str = ""
    engine: str = ""
    mode: str = ""
    platform: str = ""
    band: str = ""

    def as_fields(self) -> dict[str, str]:
        """Return the provenance as a plain mapping.

        Returns:
            dict: Every field, for serialisation.
        """
        return {name: str(getattr(self, name)) for name in (*_GUARDED, "band")}

    def disagreement(self, other: "Provenance") -> Optional[str]:
        """Return the first guarded field that differs, or None.

        **The field is named rather than the fact reported.** "Provenance
        mismatch" sends a reader to check six things, and the remedy differs by
        which one moved: a changed corpus means re-run the earlier band, a
        changed engine means this record belongs to another run entirely.

        Args:
            other (Provenance): The provenance the current run carries.

        Returns:
            Optional[str]: A message naming the field and both values.
        """
        for name in _GUARDED:
            stored = str(getattr(self, name))
            current = str(getattr(other, name))
            if stored != current:
                return (
                    f"{name} was {stored or '(empty)'} when the outcomes were "
                    f"recorded and is {current or '(empty)'} now"
                )
        return None


@dataclass(frozen=True)
class CarriedOutcomes:
    """Base outcomes from an earlier band, with the provenance admitting them.

    Attributes:
        provenance (Provenance): What produced them.
        outcomes (dict): Identifier to whether that foundation held.
    """

    provenance: Provenance
    outcomes: dict[str, bool] = field(default_factory=dict)


def write_outcomes(path: Path, provenance: Provenance, outcomes: dict[str, bool]) -> None:
    """Write the base outcomes an execution established.

    Args:
        path (Path): Where to write, under a run's report directory.
        provenance (Provenance): What produced them.
        outcomes (dict): Identifier to whether it held.

    Returns:
        None
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "provenance": provenance.as_fields(),
        "outcomes": {name: bool(held) for name, held in sorted(outcomes.items())},
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding=_ENCODING
    )
    logger.info("Recorded %d base outcome(s) for the next band", len(outcomes))


def read_outcomes(path: Path, provenance: Provenance) -> CarriedOutcomes:
    """Read base outcomes from an earlier band, refusing a record that moved.

    Args:
        path (Path): Where an earlier execution wrote.
        provenance (Provenance): What the current run carries.

    Returns:
        CarriedOutcomes: The stored outcomes, empty when no record exists,
        which is the ordinary case for the first band of a job.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the file will not
            parse, and with ``QC_HARNESS_PREREQUISITE_MISMATCH`` when a guarded
            field differs. **Refused rather than ignored**: falling back to
            re-running the prerequisites is the waste this avoids, and falling
            back to assuming they held is an assertion nobody measured.
    """
    if not path.is_file():
        return CarriedOutcomes(provenance=provenance)
    try:
        payload = json.loads(path.read_text(encoding=_ENCODING))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError(
            f"{_PARSER}: carried outcomes at {path} cannot be read"
        ) from error
    if not isinstance(payload, dict):
        raise ValueError(f"{_PARSER}: carried outcomes at {path} are not a mapping")

    stored_fields = payload.get("provenance") or {}
    stored = Provenance(
        **{name: str(stored_fields.get(name, "")) for name in (*_GUARDED, "band")}
    )
    moved = stored.disagreement(provenance)
    if moved is not None:
        raise ValueError(
            f"{_MISMATCH}: the outcomes at {path} were not produced by this run: "
            f"{moved}. Run the earlier band again rather than carrying them"
        )
    outcomes = {
        str(name): bool(held)
        for name, held in (payload.get("outcomes") or {}).items()
    }
    logger.info("Carried %d base outcome(s) from band %s", len(outcomes), stored.band)
    return CarriedOutcomes(provenance=stored, outcomes=outcomes)
