# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Checks which model version each engine is serving, before a run and on a schedule.

Created: 2026-09-26
Last updated: 2026-10-29

This file contains ``require_resolved_version``, which returns the version a
provider reported or aborts when there is none; ``probe_engine`` and
``probe_all``, which compare each engine's version with a recorded baseline
and return a ``ProbeOutcome`` per engine; ``load_baseline`` and
``write_baseline``, which keep that baseline file; ``engines_to_dispatch``,
which names the engines whose version changed; ``served_digest`` and
``served_version``, which reduce a provider's declared properties to a
comparable value and to its own version field; ``probe_roster``, which asks
every rostered engine what it serves; and ``main``, the command line this is
invoked through.

**Preflight sits before the first case is dispatched**, so a run whose model
identity is unknown stops before it spends anything. The probe's outcome
decides which engines get a live run, and a probe that failed dispatches
nothing.

Specified by ``docs/design/tier2_execution.md`` section 5 and
``docs/design/harness_ci_pipeline.md`` section 4.

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

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Optional

from cmn.config import EngineConfig, load_engines
from execution.adapters.registry import adapter_for

logger = logging.getLogger(__name__)

_ENCODING: Final[str] = "utf-8"

# HOW MUCH OF THE DIGEST IS CARRIED. Sixteen hex characters is 64 bits, which
# is far more than change detection over four engines needs, and it fits a
# report's environment widget and a JUnit property where a full hash reads as
# noise. The subject is whether two runs met the same model, not whether an
# adversary can forge a match.
_DIGEST_LENGTH: Final[int] = 16

# WHICH FIELD IS THE PROVIDER'S OWN VERSION, in preference order. Gemini
# declares `version` separately from the name it was asked about, and the
# others carry only an identifier, so the fallback chain ends at the one every
# provider returns (`tier2_execution.md` section 5.2).
_VERSION_FIELDS: Final[tuple[str, ...]] = ("version", "id", "name", "model")

# EXIT 3, WHICH IS ALREADY RESERVED FOR AN INSTRUMENT DEFECT. A probe that
# cannot resolve an engine is a broken detector rather than a finding about a
# model, and `framework-rules.md` section 3.1 reserves 3 for exactly the sense
# that nothing trustworthy was measured (`cmn_verdict_and_cli.md` section 7.3).
_DETECTOR_BROKEN: Final[int] = 3

_DEFAULT_ROSTER: Final[str] = "config/engines.yaml"


@dataclass(frozen=True)
class ProbeOutcome:
    """What one engine's probe found.

    **``served`` is a comparable value, not a model name.** It carries the
    digest of everything the provider declares, because a pinned model id
    cannot move and comparing it detects nothing (``tier2_execution.md``
    section 5.1). The fields were called ``resolved_model`` and
    ``previous_model`` until 2026-10-29, which named a model while carrying a
    digest: the one-word-two-concepts collision `testing-standards.md` records
    twice, and these values reach a durable baseline file.

    Attributes:
        engine (str): Which engine was probed.
        served (Optional[str]): The digest of what the provider declares, or
            ``None`` when the probe itself failed.
        previous (Optional[str]): The recorded baseline, or ``None`` on a first
            run.
        changed (bool): Whether a live run should be dispatched.
        failed (bool): Whether the probe could not read the provider at all.
    """

    engine: str
    served: Optional[str]
    previous: Optional[str]
    changed: bool
    failed: bool

    @property
    def should_dispatch(self) -> bool:
        """Report whether this outcome warrants a live run.

        Returns:
            bool: True only on a real change. **A probe failure dispatches
            nothing**: it means the detector is broken, which is an
            instrument defect, and
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


def probe_engine(engine: str, served: Any, baseline: dict[str, str]) -> ProbeOutcome:
    """Compare what one engine serves now against its baseline.

    Args:
        engine (str): The engine probed.
        served (Any): The digest of what the provider declares, or ``None``
            where it could not be read.
        baseline (dict): The recorded baseline.

    Returns:
        ProbeOutcome: What was found, and whether it warrants a live run.
    """
    previous = baseline.get(engine)

    if served is None or not str(served).strip():
        logger.warning("QC_HARNESS_VERSION_UNAVAILABLE probe could not read %s", engine)
        return ProbeOutcome(engine, None, previous, changed=False, failed=True)

    current = str(served).strip()

    if previous is None:
        logger.info("Recording first baseline for %s at %s", engine, current)
        return ProbeOutcome(engine, current, None, changed=False, failed=False)

    if current != previous:
        logger.warning("What %s serves moved from %s to %s", engine, previous, current)
        return ProbeOutcome(engine, current, previous, changed=True, failed=False)

    return ProbeOutcome(engine, current, previous, changed=False, failed=False)


def probe_all(served_by_engine: dict[str, Any], baseline_path: Path) -> list[ProbeOutcome]:
    """Probe every engine and update the baseline.

    The baseline is updated for every engine that could be read, including ones
    that changed, so a change dispatches once rather than on every subsequent
    run. An engine whose probe failed leaves its baseline untouched, because
    overwriting it with nothing would make the next run report a change that
    never happened.

    Args:
        served_by_engine (dict): Engine to the digest of what it serves, or
            ``None`` where it could not be read.
        baseline_path (Path): Where the baseline is recorded.

    Returns:
        list[ProbeOutcome]: One outcome per engine, in engine-name order so a
        run's output is reproducible.
    """
    baseline = load_baseline(baseline_path)
    outcomes = [
        probe_engine(engine, served_by_engine[engine], baseline)
        for engine in sorted(served_by_engine)
    ]
    for outcome in outcomes:
        if outcome.served is not None:
            baseline[outcome.engine] = outcome.served
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


def served_digest(metadata: dict[str, Any]) -> str:
    """Return a stable comparable value over a provider's declared properties.

    **The whole object, not the identifier.** A pinned model id cannot move, so
    comparing it detects nothing; what moves when a provider revises a model is
    a declared property beside the name (``tier2_execution.md`` section 5.1).

    Args:
        metadata (dict): What the provider declared, from
            ``ProviderAdapter.served_metadata``.

    Returns:
        str: A truncated SHA-256 over the canonical rendering, or empty where
        the provider declared nothing. **Empty compares equal to empty**, so an
        engine nobody could read reports no change rather than a spurious one.
    """
    if not metadata:
        return ""
    canonical = json.dumps(metadata, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode(_ENCODING)).hexdigest()[:_DIGEST_LENGTH]


def served_version(metadata: dict[str, Any]) -> str:
    """Return the provider's own version field, or the identifier it declared.

    Args:
        metadata (dict): What the provider declared.

    Returns:
        str: The first of ``version``, ``id``, ``name`` or ``model`` the
        provider populated, or empty where it declared none.
    """
    for name in _VERSION_FIELDS:
        value = str(metadata.get(name, "")).strip()
        if value:
            return value
    return ""


def served_facts(engine: str, model: str) -> dict[str, str]:
    """Ask one engine what it serves, reduced to the two fields a run records.

    **This is the probe's second caller**, the one that records rather than
    detects (``tier2_execution.md`` section 5.2.1). A run calls it at setup so
    its report states what it measured against, which is what makes two runs
    comparable after the older one's results have aged out.

    Args:
        engine (str): The engine to ask.
        model (str): The model identifier to ask about.

    Returns:
        dict[str, str]: ``served_version`` and ``served_digest``. **Empty where
        the provider could not be read**, which the caller records as
        unrecorded rather than failing the run: a label that could not be
        written must not cost a measurement.
    """
    try:
        metadata = adapter_for(engine)(model).served_metadata()
    except Exception as error:  # pylint: disable=broad-except
        # BROAD, FOR THE REASON `probe_roster` GIVES. A run recording its own
        # provenance must not be ended by the label being unavailable.
        logger.warning(
            "QC_HARNESS_VERSION_UNAVAILABLE run provenance could not read %s: %s",
            engine,
            type(error).__name__,
        )
        return {}
    if not metadata:
        return {}
    return {
        "served_version": served_version(metadata),
        "served_digest": served_digest(metadata),
    }


def probe_roster(roster: dict[str, EngineConfig]) -> dict[str, dict[str, Any]]:
    """Ask every rostered engine what it is serving.

    **The roster, not the adapter registry.** A registered adapter absent from
    `config/engines.yaml` cannot be selected for a run, so probing it would
    watch a model nothing measures against.

    One engine's failure does not stop the others: a provider being unreachable
    is reported for that engine and leaves every other engine's answer intact.

    Args:
        roster (dict): Engine name to its roster entry.

    Returns:
        dict[str, dict[str, Any]]: Engine to its declared properties, empty for
        an engine whose provider could not be read.
    """
    served: dict[str, dict[str, Any]] = {}
    for engine in sorted(roster):
        adapter = adapter_for(engine)(roster[engine].model)
        try:
            served[engine] = adapter.served_metadata()
        except Exception as error:  # pylint: disable=broad-except
            # BROAD, AND DELIBERATELY. Every provider SDK raises its own
            # hierarchy and this is a detector: an unanticipated exception here
            # must leave the other engines readable rather than ending the
            # process, and `map_error` translates for a dispatch rather than
            # for a metadata call.
            logger.warning(
                "QC_HARNESS_VERSION_UNAVAILABLE probe could not read %s: %s",
                engine,
                type(error).__name__,
            )
            served[engine] = {}
    return served


def _report(outcomes: list[ProbeOutcome], served: dict[str, dict[str, Any]]) -> None:
    """Print one line per engine, stating the outcome rather than the reasoning.

    Args:
        outcomes (list): What the probe found.
        served (dict): Engine to its declared properties.

    Returns:
        None
    """
    for outcome in outcomes:
        version = served_version(served.get(outcome.engine, {}))
        if outcome.failed:
            state = "unreadable, so nothing is dispatched"
        elif outcome.previous is None:
            state = "first baseline recorded"
        elif outcome.changed:
            state = f"changed from {outcome.previous} to {outcome.served}"
        else:
            state = "unchanged"
        print(f"{outcome.engine}: {state}, version {version or 'unreported'}")


def main(argv: Optional[list[str]] = None) -> int:
    """Probe every rostered engine and report which ones moved.

    Walks the roster, asks each engine what it serves, compares a digest of
    that against the recorded baseline, writes the baseline back, and names the
    changed engines on standard output and in the output file when one is
    given.

    Design: ``tier2_execution.md`` section 5.3 and ``harness_ci_pipeline.md``
    section 4.

    Args:
        argv (Optional[list[str]]): Arguments, or ``None`` to read ``sys.argv``.

    Returns:
        int: 0 whether or not an engine changed, a change being the finding
        this exists to produce rather than a failure. 3 where any engine could
        not be read, which is a broken detector.
    """
    parser = argparse.ArgumentParser(
        description="Report which engines are serving a different model than recorded."
    )
    parser.add_argument(
        "--baseline", required=True, help="The JSON file recording the last seen digest per engine."
    )
    parser.add_argument(
        "--output", default="", help="A file to append changed_engines to, such as a step output."
    )
    parser.add_argument(
        "--roster", default=_DEFAULT_ROSTER, help="The engine roster to walk."
    )
    args = parser.parse_args(argv)

    served = probe_roster(load_engines(Path(args.roster)))
    outcomes = probe_all(
        {engine: served_digest(metadata) or None for engine, metadata in served.items()},
        Path(args.baseline),
    )
    _report(outcomes, served)

    changed = engines_to_dispatch(outcomes)
    print(f"changed_engines={','.join(changed)}")
    if args.output:
        with Path(args.output).open("a", encoding=_ENCODING, newline="\n") as handle:
            handle.write(f"changed_engines={','.join(changed)}\n")

    if any(outcome.failed for outcome in outcomes):
        return _DETECTOR_BROKEN
    return 0


if __name__ == "__main__":
    sys.exit(main())
