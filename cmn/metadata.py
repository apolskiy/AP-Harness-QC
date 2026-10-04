# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Result metadata emission, and the diagnostic summary that says what a run is not.

Specified by ``docs/design/cmn_verdict_and_cli.md`` section 5,
``docs/design/test_taxonomy.md`` section 9, and ``docs/design/ci_pipeline.md``
section 6.5.

**Run-scoped fields are emitted twice**, once in a manifest and again on every
result. Collectors key on per-test rows, so a field living only in a manifest
may never reach per-test history, and a stored result whose thresholds cannot be
recovered is uninterpretable years later. Repeating seven fields across the
suite's rows costs nothing measurable.

**A truncated duration is excluded from latency statistics.** It records how
long the harness waited, not how long the model took. Averaging them in would
measure the harness's patience, and a case that timed out at the ceiling would
drag its own baseline upward until genuinely slow responses looked normal.

**A debug summary opens by saying the run is diagnostic and gates nothing.** A
reviewer, or the operator a week later, can read a diagnostic green as a suite
green, and a notification makes that more likely rather than less because it
arrives looking like every other build notification.
"""

import logging
import platform
from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Final, Optional

from cmn.observations import Observation, RunContext, require_complete_result
from cmn.registries import registered_codes

logger = logging.getLogger(__name__)

# The prefix a collector's pattern matches. A debug artifact deliberately does
# not carry it, which is one of the two independent mechanisms excluding a
# diagnostic run from the durable record.
_COLLECTED_PREFIX: Final[str] = "mqc-results"
_DEBUG_PREFIX: Final[str] = "diagnostic-local"

_CHANGED_AREAS: Final[frozenset[str]] = frozenset({"harness", "tests", "both", "none"})


def emit_result(observation: Observation, run: RunContext) -> dict[str, Any]:
    """Build one emitted result, carrying the run-scoped fields with it.

    Args:
        observation (Observation): What one execution produced.
        run (RunContext): The run-scoped fields.

    Returns:
        dict: The complete result.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when a required field is
            missing, or when the observation carries an unregistered taxonomy
            code. **An unregistered code reaching the record makes it
            uncountable**: every later tally by root-cause class would silently
            omit it.
    """
    if observation.taxonomy_code is not None:
        require_registered_code(observation.taxonomy_code)

    emitted: dict[str, Any] = {
        "case_id": observation.case_id,
        "layer": observation.layer,
        "observation_index": observation.observation_index,
        "families": list(observation.families),
        "primary_family": observation.primary_family,
        "engine": observation.engine,
        "mode": observation.mode,
        "requested_model": observation.requested_model,
        "resolved_model": observation.resolved_model,
        "outcome": observation.outcome,
        "skip_reason": observation.skip_reason,
        "taxonomy_code": observation.taxonomy_code,
        "priority": observation.priority,
        "priority_conditions": list(observation.priority_conditions),
        "requirement_ids": list(observation.requirement_ids),
        "score": observation.score,
        "scale_id": observation.scale_id,
        "rubric_result": observation.rubric_result,
        "duration": observation.duration,
        "duration_kind": observation.duration_kind,
        "output_tokens": observation.output_tokens,
        # FLAT ON THE WIRE, nested in use. A collector reads standard formats
        # and should not have to learn this project's nesting to find a count.
        "input_tokens": observation.tokens.candidate.input_tokens,
        "thinking_tokens": observation.tokens.candidate.thinking_tokens,
        "cached_input_tokens": observation.tokens.candidate.cached_input_tokens,
        "judge_input_tokens": observation.tokens.judge.input_tokens,
        "judge_output_tokens": observation.tokens.judge.output_tokens,
        "judge_thinking_tokens": observation.tokens.judge.thinking_tokens,
        "demoted": observation.demoted,
    }
    emitted.update(run.as_fields())
    return require_complete_result(emitted)


def require_registered_code(taxonomy_code: str) -> str:
    """Refuse a code that is not in the single registry.

    Args:
        taxonomy_code (str): The code about to be emitted.

    Returns:
        str: The code, once it is known to be registered.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR``. ``test_taxonomy.md``
            section 6 is the single registry, and a code emitted from outside
            it would be invisible to every count drawn from the record.
    """
    if taxonomy_code not in registered_codes():
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: {taxonomy_code!r} is not a registered taxonomy "
            f"code, so a result carrying it could not be counted by root-cause class"
        )
    return taxonomy_code


def unemitted_codes(emitted: list[str]) -> list[str]:
    """Return registered codes that no result emitted.

    The other direction of the same check. A code registered and never emitted
    is either dead or a site that forgot to attach it, and both are worth
    reporting even though neither fails a run.

    Args:
        emitted (list): Every code the run emitted.

    Returns:
        list[str]: The unemitted codes, sorted.
    """
    return sorted(registered_codes() - set(emitted))


def latency_statistics(observations: list[Observation]) -> dict[str, Optional[float]]:
    """Return latency over the measured durations only.

    Args:
        observations (list): Every observation.

    Returns:
        dict: The mean and the sample count. **Truncated durations are
        excluded**, and the count says how many contributed so a reader can
        tell a thin sample from a thick one. Absent rather than zero when
        nothing was measured.
    """
    measured = [entry.duration for entry in observations if entry.counts_in_latency]
    return {
        "mean_duration": mean(measured) if measured else None,
        "sample_count": len(measured),
        "excluded_truncated": len(observations) - len(measured),
    }


def artifact_name(run: RunContext, suffix: str = "") -> str:
    """Return the artifact name for one run.

    **A debug artifact does not match the collector's pattern.** That is one of
    two independent mechanisms excluding it from the durable record; the other
    is the row marking carrying ``run_context`` and ``gated``. Structural
    separation alone fails the day someone widens the pattern, and marking alone
    fails if nobody filters on it.

    Args:
        run (RunContext): The run-scoped fields.
        suffix (str): An optional discriminator, such as a platform.

    Returns:
        str: The artifact name.
    """
    prefix = _DEBUG_PREFIX if run.run_context == "ci_debug" else _COLLECTED_PREFIX
    return f"{prefix}-{suffix}" if suffix else prefix


def matches_collector_pattern(name: str) -> bool:
    """Report whether a collector would pick this artifact up.

    Args:
        name (str): The artifact name.

    Returns:
        bool: True when the name carries the collected prefix.
    """
    return name.startswith(_COLLECTED_PREFIX)


def current_platform() -> str:
    """Return the platform this run executed on.

    The harness is verified on two platforms (A18), and a result that does not
    say which produced it cannot support the comparison that verification
    exists to make.

    Returns:
        str: The platform identifier.
    """
    return platform.system().lower()


@dataclass(frozen=True)
class DiagnosticSummary:
    """What a debug run reports about itself.

    **It opens by saying what it is not.** A reviewer can read a diagnostic
    green as a suite green, and a notification makes that more likely rather
    than less, because it arrives looking like every other build notification.

    Attributes:
        workflow (str): Which workflow produced it.
        job (str): Which job.
        run_number (int): So the run is findable again a week later.
        run_id (str): The same, from the notification alone.
        code_ref (str): The harness and test code, resolved to a commit,
            because a branch name moves.
        fixture_ref (str): The recorded responses, resolved to a commit. Equal
            to ``code_ref`` in the ordinary case, and **the whole point when it
            is not**.
        changed_areas (str): ``harness``, ``tests``, ``both`` or ``none``.
        mode (str): Whether responses were observed or replayed.
        engine (str): From where.
        resolved_models (dict): Per engine. The premise every checkpoint
            comparison rests on: our code caused this, because the model did
            not change.
        selection_mode (str): How much of the suite this covers.
        case_count (int): The same.
    """

    workflow: str
    job: str
    run_number: int
    run_id: str
    code_ref: str
    changed_areas: str
    mode: str
    engine: str
    selection_mode: str
    case_count: int
    fixture_ref: str = ""
    resolved_models: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Default the fixture ref and refuse an unregistered changed area.

        Returns:
            None

        Raises:
            ValueError: With ``QC_HARNESS_PARSER_ERROR`` for an unregistered
                changed area.
        """
        if not self.fixture_ref:
            # The ordinary case: fixtures come from whatever code_ref is. An
            # empty value would read as "unknown" rather than "the same", and
            # the two mean very different things to a checkpoint comparison.
            object.__setattr__(self, "fixture_ref", self.code_ref)
        if self.changed_areas not in _CHANGED_AREAS:
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: changed areas {self.changed_areas!r} is not "
                f"one of {sorted(_CHANGED_AREAS)}"
            )

    @property
    def refs_diverge(self) -> bool:
        """Report whether code and fixtures came from different commits.

        Returns:
            bool: True when they differ, which is the condition the two-ref
            diagnostic exists for and the one context where a stale fixture is
            the answer rather than a defect.
        """
        return self.code_ref != self.fixture_ref

    def render(self) -> str:
        """Return the summary as text, opening with what the run is not.

        Returns:
            str: The rendered summary.
        """
        lines = [
            "This run is diagnostic. It carries no verdict and gates nothing.",
            "A green result here means the work is ready to be offered, never "
            "that it is ready to merge.",
            "",
            f"Workflow: {self.workflow}",
            f"Job: {self.job}",
            f"Run: {self.run_number} ({self.run_id})",
            f"Code ref: {self.code_ref}",
            f"Fixture ref: {self.fixture_ref}"
            + (" (diverged)" if self.refs_diverge else ""),
            f"Changed areas: {self.changed_areas}",
            f"Mode: {self.mode}",
            f"Engine: {self.engine}",
            f"Selection: {self.selection_mode}, {self.case_count} cases",
        ]
        for engine in sorted(self.resolved_models):
            lines.append(f"Resolved model, {engine}: {self.resolved_models[engine]}")
        return "\n".join(lines) + "\n"


def changed_areas_from(changed_paths: list[str]) -> str:
    """Classify a change as touching the harness, the tests, both or neither.

    **The distinction matters when reading a result.** A run where only tests
    changed and results moved points at the tests; a run where only the harness
    changed and results moved points at the harness. An undifferentiated diff
    leaves the reader to work that out from paths.

    Args:
        changed_paths (list): The changed file paths.

    Returns:
        str: ``harness``, ``tests``, ``both`` or ``none``.
    """
    production = {"ingestion/", "execution/", "evaluation/", "cmn/"}
    touched_harness = any(
        path.startswith(tuple(production)) for path in changed_paths
    )
    touched_tests = any(
        path.startswith("tests/") or path.startswith("conftest.py")
        for path in changed_paths
    )
    if touched_harness and touched_tests:
        return "both"
    if touched_harness:
        return "harness"
    if touched_tests:
        return "tests"
    return "none"
