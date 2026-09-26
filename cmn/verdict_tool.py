# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The standalone tool that computes a verdict from stored artifacts.

Specified by ``docs/design/cmn_verdict_and_cli.md`` sections 7.2 and 7.3.

**Not an in-process hook during the run.** Thresholds are configuration, so a
verdict can be recomputed from stored artifacts without re-running anything.
"What would this run have scored under the tightened floor?" is then answerable
from history, which is what makes a threshold change auditable rather than
merely disclosed.

**Exit codes are chosen to stay distinguishable from argparse**, which exits 2
on a bad argument:

| Code | Meaning |
|---|---|
| 0 | Green |
| 1 | Red, one or more verdict rules breached |
| 2 | Argument error |
| 3 | Precondition failure, the run never reached the graded layers |
| 4 | Refused, the artifact is ungated and no verdict can be computed |

**4 is distinct from 1.** A red verdict says the suite was measured and
something failed; a refusal says no verdict was computable from what it was
given. Collapsing them would let a refused artifact read as a failing suite,
which is the inverse of the error the gating rules exist to prevent.

**1 and 3 are separated deliberately.** Collapsing them would let CI treat "the
harness is broken" as "the model underperformed".
"""

import argparse
import dataclasses
import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final, Optional

from cmn.config import load_harness_config
from cmn.observations import Observation
from cmn.options import Option, registered_options
from cmn.verdict import Thresholds, Verdict, VerdictConfig, verdict

logger = logging.getLogger(__name__)

_ENCODING: Final[str] = "utf-8"

EXIT_GREEN: Final[int] = 0
EXIT_RED: Final[int] = 1
EXIT_ARGUMENT_ERROR: Final[int] = 2
EXIT_PRECONDITION_FAILED: Final[int] = 3
EXIT_REFUSED: Final[int] = 4


@dataclass(frozen=True)
class Refusal:
    """Why no verdict could be computed from an artifact.

    Attributes:
        reason (str): What made the artifact unverdictable.
        exit_code (int): Always 4, kept on the record so a caller reads one
            field rather than remembering which code means which.
    """

    reason: str
    exit_code: int = EXIT_REFUSED


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser from the shared option registry.

    **Both surfaces build from one registry**, so a flag cannot exist on the
    command line and not in the pytest plugin, and neither can accept a value
    the other rejects.

    Returns:
        argparse.ArgumentParser: The parser, with every enumerated flag
        constrained so a typo fails at parse time rather than selecting nothing
        and reporting an empty run.
    """
    parser = argparse.ArgumentParser(
        prog="mqc-verdict",
        description="Compute a run verdict from stored result artifacts",
    )
    parser.add_argument(
        "artifacts", type=Path,
        help="Path to the emitted results file",
    )
    for declared in registered_options():
        _add_option(parser, declared)
    return parser


def _add_option(parser: argparse.ArgumentParser, declared: Option) -> None:
    """Add one declared option to a parser.

    Args:
        parser (argparse.ArgumentParser): The parser to extend.
        declared (Option): The option to add.

    Returns:
        None
    """
    if declared.is_flag:
        parser.add_argument(
            declared.cli_flag, action="store_true", help=declared.help_text
        )
        return
    parser.add_argument(
        declared.cli_flag,
        choices=list(declared.choices) if declared.choices else None,
        default=declared.default,
        help=declared.help_text,
    )


def load_artifacts(path: Path) -> dict[str, Any]:
    """Read an emitted results file.

    Args:
        path (Path): The artifact to read.

    Returns:
        dict: The parsed artifact.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when it cannot be read. An
            unreadable artifact silently treated as empty would report green
            for a run nobody measured.
    """
    try:
        loaded = json.loads(path.read_text(encoding=_ENCODING))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: results at {path} cannot be read"
        ) from error
    if not isinstance(loaded, dict):
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: results at {path} are not a mapping"
        )
    return loaded


def refuse_if_ungated(artifact: dict[str, Any]) -> Optional[Refusal]:
    """Refuse an artifact no verdict may be computed from.

    Args:
        artifact (dict): The loaded artifact.

    Returns:
        Optional[Refusal]: The refusal, or ``None`` when a verdict may be
        computed. **A manual selection is refused, not failed**: testers may run
        any subset, and what a subset costs is the verdict rather than the
        ability to run. A debug run is refused for the same reason, since it
        may be exercising a different harness branch entirely.
    """
    if not artifact.get("gated", False):
        selection = artifact.get("selection_mode", "unknown")
        context = artifact.get("run_context", "unknown")
        return Refusal(
            reason=(
                f"the artifact is marked ungated, with selection mode {selection!r} and "
                f"run context {context!r}, so no verdict can be computed from it"
            )
        )
    return None


def observations_from(artifact: dict[str, Any]) -> list[Observation]:
    """Rebuild observations from a stored artifact.

    Args:
        artifact (dict): The loaded artifact.

    Returns:
        list[Observation]: The rebuilt records, each revalidated by its own
        constructor so a hand-edited artifact is rejected on read.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when a stored result
            carries a field the record does not declare.
    """
    rebuilt: list[Observation] = []
    for entry in artifact.get("results", []):
        permitted = {field.name for field in dataclasses.fields(Observation)}
        rebuilt.append(
            Observation(**{key: value for key, value in entry.items() if key in permitted})
        )
    return rebuilt


def thresholds_from(artifact: dict[str, Any]) -> Thresholds:
    """Rebuild the thresholds a run was judged against.

    **Read from the artifact rather than from current configuration**, so
    recomputing a historical run reproduces what it actually scored. Supplying
    current thresholds instead is a different question, and a useful one, but it
    is not the same question and must not be answered silently.

    Args:
        artifact (dict): The loaded artifact.

    Returns:
        Thresholds: The recorded standard, or the defaults when none was
        recorded.
    """
    recorded = artifact.get("effective_thresholds") or {}
    declared = {
        entry.name: recorded[entry.name]
        for entry in dataclasses.fields(Thresholds)
        if entry.name in recorded
    }
    return Thresholds(**declared)


def compute(
    artifact: dict[str, Any],
    config_dir: Optional[Path] = None,
    as_of_date: Optional[date] = None,
) -> tuple[Optional[Verdict], Optional[Refusal]]:
    """Compute a verdict from one artifact, or refuse it.

    Args:
        artifact (dict): The loaded artifact.
        config_dir (Optional[Path]): Where the configuration files live.
        as_of_date (Optional[date]): The injected evaluation date.

    Returns:
        tuple: The verdict, or the refusal. Exactly one is present.
    """
    refusal = refuse_if_ungated(artifact)
    if refusal is not None:
        logger.error("Refusing to compute a verdict: %s", refusal.reason)
        return None, refusal

    harness_config = load_harness_config(config_dir)
    settings = VerdictConfig(
        thresholds=thresholds_from(artifact),
        quarantine=harness_config.quarantine,
        unsupported_pairs=harness_config.unsupported_keys(),
    )
    return verdict(observations_from(artifact), settings, as_of_date), None


def main(argv: Optional[list[str]] = None) -> int:
    """Run the tool and return its exit code.

    Args:
        argv (Optional[list]): Arguments, for testing without a process.

    Returns:
        int: One of the module's exit codes. Returned rather than raised, so
        the tool is callable in-process by the cases that cover it.
    """
    parsed = build_parser().parse_args(argv)
    try:
        artifact = load_artifacts(parsed.artifacts)
    except ValueError as error:
        logger.error("%s", error)
        return EXIT_ARGUMENT_ERROR

    as_of = date.fromisoformat(parsed.as_of) if getattr(parsed, "as_of", "") else None
    computed, refusal = compute(artifact, as_of_date=as_of)

    if refusal is not None:
        return refusal.exit_code
    for breach in computed.breaches:
        logger.error("%s: %s", breach.rule, breach.reason)
    return computed.exit_code
