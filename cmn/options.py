# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""One option registry, feeding two surfaces that must not drift.

Specified by ``docs/design/cmn_verdict_and_cli.md`` sections 7 and 7.1.

**The flags reach the harness through two entry points**, the pytest plugin and
the standalone verdict tool. Declaring them twice would let one gain a value the
other rejects, and the failure would appear as a flag that works in one place
and not the other.

**Every flag that can change a result is recorded in result metadata.** A run
that dropped three columns, replayed instead of executing live, or used a
revised rule set must be distinguishable from one that did not. This is A6 and
A8 applied to the invocation itself.

**Defaults fail safe.** ``--mode`` defaults to replay so no unconfigured
invocation can spend quota or emit an unmarked live result, and
``--extra-columns`` defaults to reject. ``--engine`` defaults but **emits a
warning into the artifact when it does**, so a cloned repository running
unconfigured produces a record saying so (A7.4).
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Final, Optional

logger = logging.getLogger(__name__)

_DEFAULTED_ENGINE_CODE: Final[str] = "QC_DATA_ENGINE_DEFAULTED"


@dataclass(frozen=True)
class Option:
    """One flag, declared once for both surfaces.

    Attributes:
        name (str): The flag name without its leading dashes.
        default (Any): What it takes when absent.
        choices (Optional[tuple]): The permitted values, when enumerated. **An
            enumerated flag is validated at parse time**, so a typo fails
            before any case runs rather than deep inside one.
        help_text (str): What it does.
        recorded (bool): Whether it reaches result metadata. Every flag that
            can change a result must.
        is_flag (bool): Whether it is a boolean switch rather than a value.
        warns_when_defaulted (bool): Whether defaulting it emits a warning into
            the artifact.
    """

    name: str
    default: Any
    help_text: str
    choices: Optional[tuple[str, ...]] = None
    recorded: bool = True
    is_flag: bool = False
    warns_when_defaulted: bool = False

    @property
    def cli_flag(self) -> str:
        """Return the flag as it appears on a command line.

        Returns:
            str: The name with its leading dashes.
        """
        return f"--{self.name}"

    @property
    def metadata_key(self) -> str:
        """Return the key this flag is recorded under.

        Returns:
            str: The name with underscores, as a record field.
        """
        return self.name.replace("-", "_")


_OPTIONS: Final[tuple[Option, ...]] = (
    # NO choices TUPLE, FOR THE REASON `--judge-engine` ALREADY GIVES BELOW.
    # It carried one until 2026-10-04, enumerating gemini, openai and claude,
    # so rostering `grok` left the flag refusing an engine the roster named:
    # "invalid choice: 'grok'" against a `config/engines.yaml` that listed it.
    #
    # THE ARGUMENT WAS ALREADY WRITTEN DOWN, one flag away, and nobody applied
    # it here: an enumerated list has to be edited whenever an adapter is
    # added, which is the coupling the capability gate exists to avoid. The
    # roster is the registry and preflight refuses an engine absent from it.
    Option(
        name="engine",
        default="gemini",
        help_text="Which provider to dispatch against, from the engine roster",
        warns_when_defaulted=True,
    ),
    Option(
        name="mode",
        default="replay",
        choices=("live", "replay"),
        help_text="Whether to dispatch live or replay recorded fixtures",
    ),
    # EMPTY MEANS "WHATEVER --mode IS", which is why the default is not one of
    # the choices. A fixed default would silently change what `--mode live`
    # meant, and the two common quadrants need no flag at all.
    #
    # The quadrant this exists for is replay candidate with a live judge, which
    # isolates judge drift on real cases and cannot be expressed otherwise.
    # tier3_evaluation.md section 5A.5.
    Option(
        name="judge-mode",
        default="",
        choices=("", "live", "replay"),
        help_text="Whether the judge is live or replayed, empty to follow --mode",
    ),
    # NO choices TUPLE, deliberately. An enumerated list here would have to be
    # edited whenever an adapter is added, which is the coupling the capability
    # gate exists to avoid: config/engines.yaml names the roster and
    # resolve_judge_engine refuses anything absent from it or unable to return
    # structured output. tier3_evaluation.md section 5A.2.
    #
    # Empty default means "take what configuration says", which is gemini
    # (A3). It is not a manual selector: it changes which instrument grades,
    # never which cases run, so it does not withhold a verdict.
    Option(
        name="judge-engine",
        default="",
        help_text="Which engine grades, empty to take the configured default",
    ),
    Option(
        name="priority",
        default="",
        help_text="Comma-separated priority bands to select, empty for all",
    ),
    Option(
        name="golden-rules",
        default="",
        help_text="Path to the rule set, recorded as a content hash",
    ),
    Option(
        name="extra-columns",
        default="reject",
        choices=("reject", "drop"),
        help_text="What to do with an unknown column at ingest",
    ),
    Option(
        name="judge-on-failure",
        default=False,
        is_flag=True,
        help_text="Judge a case whose assertions failed at violation severity",
    ),
    Option(
        name="fill-gaps",
        default=False,
        is_flag=True,
        help_text="In live mode, dispatch only observations not already recorded",
    ),
    Option(
        name="carry-outcomes",
        default="",
        help_text=(
            "File holding base outcomes carried between the band executions of "
            "one job, read at start and rewritten at finish"
        ),
    ),
    Option(
        name="with-prerequisites",
        default=False,
        is_flag=True,
        help_text=(
            "Run the foundations a selected band rests on, for a band run alone"
        ),
    ),
    Option(
        name="keep-connection",
        default=False,
        is_flag=True,
        help_text="Hold the provider connection open between cases, for reuse",
    ),
    Option(
        name="max-spend",
        default=0.0,
        help_text=(
            "Abort the run before a request would take total spend past this "
            "many USD. Zero means no ceiling"
        ),
    ),
    Option(
        name="as-of",
        default="",
        help_text="ISO date the verdict is evaluated against, for quarantine expiry",
    ),
    # `--case` WAS RETIRED 2026-10-03. It was declared here, listed in the
    # design's selection table and claimed as covered in `flag_coverage.yaml`,
    # and nothing read it. `--tests` takes one identifier or many, so selecting
    # cases by identifier needed one spelling rather than two. Design section
    # 7.8.4. The name stays retired rather than reused.
    Option(
        name="observations",
        default=0,
        help_text="Override the configured observation count, a diagnostic selection",
    ),
    Option(
        name="out-dir",
        default="",
        help_text="Where artifacts are written, so a diagnostic run stays separate",
    ),
    Option(
        name="module",
        default="",
        help_text=(
            "Comma-separated modules whose cases to run, from ING, EXE, EVL, "
            "CMN and CAS"
        ),
    ),
    Option(
        name="family",
        default="",
        help_text=(
            "Comma-separated evaluation families whose cases to run, resolved "
            "through --rtm. Inclusive of a secondary family"
        ),
    ),
    Option(
        name="requirement",
        default="",
        help_text=(
            "Comma-separated requirement identifiers whose cases to run, "
            "resolved through --rtm"
        ),
    ),
    Option(
        name="tag",
        default="",
        help_text=(
            "Comma-separated task tags whose cases to run, resolved through "
            "--case-index"
        ),
    ),
    Option(
        name="case-index",
        default="",
        help_text=(
            "Path to the generated per-case index of families and tags. Makes "
            "--family exact and --tag possible. Not a selector"
        ),
    ),
    Option(
        name="rtm",
        default="",
        help_text=(
            "Path to the traceability matrix --family and --requirement "
            "resolve through. Not a selector"
        ),
    ),
    Option(
        name="tests",
        default="",
        help_text=(
            "Comma-separated test identifiers or names to run. An entry naming "
            "no collected test refuses the run"
        ),
    ),
    # SEPARATE FLAG RATHER THAN A VALUE PREFIX. pytest's parser reserves `@`
    # for argument files, so `--tests @list.txt` is expanded by argparse before
    # this flag sees it and every line after the first arrives as a path.
    # Design section 7.8.1.
    Option(
        name="tests-file",
        default="",
        help_text=(
            "File of test identifiers or names, one per line. An entry naming "
            "no collected test is reported as a skip and the rest run"
        ),
    ),
)

# Flags whose presence makes a selection manual, and therefore unverdictable.
# A hand-typed subset is arbitrary with no backstop; what it costs is the
# verdict, never the ability to run.
# `rtm` IS ABSENT DELIBERATELY. It names where a selection resolves through
# and selects nothing itself, so a run supplying it and no selector is a full
# run. Design section 7.7.1.
_MANUAL_SELECTORS: Final[frozenset[str]] = frozenset(
    {"priority", "observations", "tests", "tests-file", "family", "requirement",
     "module", "tag"}
)


def registered_options() -> tuple[Option, ...]:
    """Return every declared option.

    **Both surfaces build from this**, so a flag cannot exist on one and not the
    other, and neither can accept a value the other rejects.

    Returns:
        tuple[Option, ...]: The options, in declaration order.
    """
    return _OPTIONS


def option(name: str) -> Option:
    """Return one declared option.

    Args:
        name (str): The flag name.

    Returns:
        Option: Its declaration.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when undeclared.
    """
    for entry in _OPTIONS:
        if entry.name == name:
            return entry
    raise ValueError(
        f"QC_HARNESS_PARSER_ERROR: {name!r} is not a declared option; declared options "
        f"are {[entry.name for entry in _OPTIONS]}"
    )


def validate_value(name: str, value: Any) -> Any:
    """Refuse a value outside an enumerated flag's choices.

    **Validated at parse time.** A typo reaching the suite would select nothing
    and report an empty run, which reads exactly like a run where nothing
    needed to happen.

    Args:
        name (str): The flag name.
        value (Any): The supplied value.

    Returns:
        Any: The value, once it is known to be permitted.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` naming the permitted
            values, so a reader can correct the typo from the message alone.
    """
    declared = option(name)
    if declared.choices is not None and value not in declared.choices:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: {declared.cli_flag} does not accept {value!r}; "
            f"permitted values are {list(declared.choices)}"
        )
    return value


def defaults() -> dict[str, Any]:
    """Return every option's default, keyed as it is recorded.

    Returns:
        dict: Flag name to default value.
    """
    return {entry.metadata_key: entry.default for entry in _OPTIONS}


@dataclass(frozen=True)
class Invocation:
    """What one run was invoked with, and what that costs it.

    Attributes:
        supplied (dict): The flags the caller actually named.
        warnings (list): Warnings emitted into the artifact, such as a
            defaulted engine.
    """

    supplied: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def selection_mode(self) -> str:
        """Return how the selection was arrived at.

        Returns:
            str: ``manual`` when any filtering flag was supplied, otherwise
            ``full``. **Change-scoped selection is derived from the diff** by
            the runner and is set there rather than inferred from flags, which
            is what distinguishes it from a hand-typed subset.
        """
        if any(name in self.supplied for name in _MANUAL_SELECTORS):
            return "manual"
        return "full"

    @property
    def yields_verdict(self) -> bool:
        """Report whether a verdict may be computed from this invocation.

        Returns:
            bool: False for a manual selection. Testers may run any subset from
            a terminal; **what a subset costs is the verdict, not the ability to
            run**.
        """
        return self.selection_mode != "manual"

    def as_metadata(self) -> dict[str, Any]:
        """Return every recorded flag, defaults included.

        **Defaults are recorded, not omitted.** A run that took the default and
        one that named the same value explicitly produced the same result, and a
        reader of the artifact needs to know what applied rather than what was
        typed.

        Returns:
            dict: The effective value of every recorded option.
        """
        recorded = defaults()
        for entry in _OPTIONS:
            if entry.recorded and entry.metadata_key in self.supplied:
                recorded[entry.metadata_key] = self.supplied[entry.metadata_key]
        return recorded


def build_invocation(supplied: Optional[dict[str, Any]] = None) -> Invocation:
    """Validate what was supplied and record what defaulting it cost.

    Args:
        supplied (Optional[dict]): The flags the caller named.

    Returns:
        Invocation: The validated invocation, carrying any warnings.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` for an undeclared flag or
            a value outside an enumerated set.
    """
    named = dict(supplied or {})
    for name, value in named.items():
        declared = option(name.replace("_", "-") if name not in _by_name() else name)
        validate_value(declared.name, value)

    warnings: list[str] = []
    for entry in _OPTIONS:
        if entry.warns_when_defaulted and entry.metadata_key not in named:
            message = (
                f"{_DEFAULTED_ENGINE_CODE}: {entry.cli_flag} was not supplied and "
                f"defaulted to {entry.default!r}, so this run measured a provider "
                f"nobody chose"
            )
            logger.warning(message)
            warnings.append(message)
    return Invocation(supplied=named, warnings=warnings)


def _by_name() -> dict[str, Option]:
    """Return the options keyed by their declared name.

    Returns:
        dict: Name to option.
    """
    return {entry.name: entry for entry in _OPTIONS}


def manual_selector_flags() -> frozenset[str]:
    """Return the flags whose presence makes a selection manual.

    Returns:
        frozenset[str]: The selector names.
    """
    return _MANUAL_SELECTORS


def resolve_judge_mode(mode: str, judge_mode: str) -> str:
    """Return the mode the judge runs in.

    Args:
        mode (str): The candidate mode.
        judge_mode (str): What ``--judge-mode`` supplied, empty to follow.

    Returns:
        str: ``live`` or ``replay``.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` for a live candidate with
            a replayed judge. **A judgement is a score of a specific
            response**, so replaying one against text the run has not produced
            yet answers a question nobody asked. The fixture machinery would
            report it as staleness on every case, which reads as a corpus
            problem rather than an impossible request, so it is refused here
            instead.
    """
    resolved = judge_mode or mode
    if mode == "live" and resolved == "replay":
        raise ValueError(
            "QC_HARNESS_PARSER_ERROR: --mode live with --judge-mode replay asks "
            "for a stored score of a response this run has not produced. A "
            "judgement is a score of a specific response"
        )
    return resolved
