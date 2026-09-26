# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Model version resolution, and the nightly probe built on it.

Specified by ``docs/design/tier2_execution.md`` section 5 and
``docs/design/ci_pipeline.md`` section 4.

**The resolved identifier, never the requested one.** Aliases float, and
recording only the request hides precisely the event that makes a later score
change uninterpretable. A run whose model identity is unknown produces scores
nobody can interpret, so preflight failure aborts before any case runs.

**The probe is this code called on a schedule.** It resolves each engine's
version and compares it against a recorded baseline, which is a metadata call
rather than an evaluation. Detecting a provider's model change the morning it
happens costs almost nothing; a nightly full live run mostly re-measures an
unchanged model at full price.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Optional

logger = logging.getLogger(__name__)

_ENCODING: Final[str] = "utf-8"


@dataclass(frozen=True)
class ProbeOutcome:
    """What one engine's version probe found.

    Attributes:
        engine (str): Which engine was probed.
        resolved_model (Optional[str]): What the provider reported, or ``None``
            when the probe itself failed.
        previous_model (Optional[str]): The recorded baseline, or ``None`` on a
            first run.
        changed (bool): Whether a live run should be dispatched.
        failed (bool): Whether the probe could not reach a version at all.
    """

    engine: str
    resolved_model: Optional[str]
    previous_model: Optional[str]
    changed: bool
    failed: bool

    @property
    def should_dispatch(self) -> bool:
        """Report whether this outcome warrants a live run.

        Returns:
            bool: True only on a real change. **A probe failure dispatches
            nothing**: it means the detector is broken, which is our defect, and
            the unconditional weekly run covers the period regardless. Treating
            it as a change would spend quota to investigate our own bug.
        """
        return self.changed and not self.failed


def require_resolved_version(engine: str, resolved: Optional[str]) -> str:
    """Return the resolved version, aborting preflight when there is none.

    Args:
        engine (str): The engine being checked.
        resolved (Optional[str]): What the adapter resolved, if anything.

    Returns:
        str: The resolved version.

    Raises:
        ValueError: With ``QC_HARNESS_VERSION_UNAVAILABLE``. Preflight failure
            aborts the run before any case executes, because scores carrying an
            unknown model identity cannot be interpreted afterwards and would
            reach the durable record looking exactly like scores that can.
    """
    if resolved is None or not str(resolved).strip():
        logger.error("QC_HARNESS_VERSION_UNAVAILABLE %s returned no usable version", engine)
        raise ValueError(
            f"QC_HARNESS_VERSION_UNAVAILABLE: {engine} returned no usable model version, "
            f"so the run aborts before any case executes"
        )
    return str(resolved).strip()


def load_baseline(path: Path) -> dict[str, str]:
    """Read the recorded model version per engine.

    Args:
        path (Path): The baseline file.

    Returns:
        dict[str, str]: Engine to last-seen version. An **absent file returns an
        empty mapping** rather than raising: a first run has no baseline, and
        that is a starting condition rather than an error.
    """
    if not path.is_file():
        logger.info("No version baseline at %s; this is a first run", path)
        return {}
    try:
        loaded = json.loads(path.read_text(encoding=_ENCODING))
        return {str(engine): str(version) for engine, version in loaded.items()}
    except (json.JSONDecodeError, AttributeError, TypeError, ValueError) as error:
        logger.error("QC_HARNESS_PARSER_ERROR baseline at %s is unreadable", path)
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: version baseline at {path} cannot be read"
        ) from error


def write_baseline(path: Path, baseline: dict[str, str]) -> Path:
    """Record the current model version per engine.

    Args:
        path (Path): The baseline file.
        baseline (dict): Engine to version.

    Returns:
        Path: Where it was written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding=_ENCODING, newline="\n"
    )
    return path


def probe_engine(engine: str, resolved: Any, baseline: dict[str, str]) -> ProbeOutcome:
    """Compare one engine's current version against its baseline.

    Args:
        engine (str): The engine probed.
        resolved (Any): What the adapter resolved, or ``None`` on failure.
        baseline (dict): The recorded baseline.

    Returns:
        ProbeOutcome: What was found, and whether it warrants a live run.
    """
    previous = baseline.get(engine)

    if resolved is None or not str(resolved).strip():
        logger.warning("QC_HARNESS_VERSION_UNAVAILABLE probe could not resolve %s", engine)
        return ProbeOutcome(engine, None, previous, changed=False, failed=True)

    current = str(resolved).strip()

    if previous is None:
        logger.info("Recording first baseline for %s at %s", engine, current)
        return ProbeOutcome(engine, current, None, changed=False, failed=False)

    if current != previous:
        logger.warning("Model version for %s moved from %s to %s", engine, previous, current)
        return ProbeOutcome(engine, current, previous, changed=True, failed=False)

    return ProbeOutcome(engine, current, previous, changed=False, failed=False)


def probe_all(resolved_by_engine: dict[str, Any], baseline_path: Path) -> list[ProbeOutcome]:
    """Probe every engine and update the baseline.

    The baseline is updated for every engine that resolved, including ones that
    changed, so a change dispatches once rather than on every subsequent run.
    An engine whose probe failed leaves its baseline untouched, because
    overwriting it with nothing would make the next run report a change that
    never happened.

    Args:
        resolved_by_engine (dict): Engine to resolved version, or ``None``.
        baseline_path (Path): Where the baseline is recorded.

    Returns:
        list[ProbeOutcome]: One outcome per engine, in engine-name order so a
        run's output is reproducible.
    """
    baseline = load_baseline(baseline_path)
    outcomes = [
        probe_engine(engine, resolved_by_engine[engine], baseline)
        for engine in sorted(resolved_by_engine)
    ]
    for outcome in outcomes:
        if outcome.resolved_model is not None:
            baseline[outcome.engine] = outcome.resolved_model
    write_baseline(baseline_path, baseline)
    return outcomes


def engines_to_dispatch(outcomes: list[ProbeOutcome]) -> list[str]:
    """Return the engines a live run should be dispatched for.

    Args:
        outcomes (list): What the probe found.

    Returns:
        list[str]: Engine names, sorted. **Only the changed engine**, not all of
        them: a version move on one provider says nothing about the others, and
        dispatching all three would spend quota to re-measure two unchanged
        models.
    """
    return sorted(outcome.engine for outcome in outcomes if outcome.should_dispatch)
