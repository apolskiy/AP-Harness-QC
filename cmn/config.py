# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Configuration loading for the three files that are data rather than code.

Specified by ``docs/design/cmn_verdict_and_cli.md`` section 8.

| File | Why config, not code |
|---|---|
| ``engines.yaml`` | Adding an engine is an entry, never a module (B8) |
| ``unsupported.yaml`` | A capability gap must not consume skip budget (A13) |
| ``quarantine.yaml`` | An entry expires, and an expired one fails the run |

**Credentials are never in configuration.** They are read from the environment
at runtime and redacted from every log and artifact, so a configuration file
committed to the repository can never carry one.

**Every file open declares its encoding.** On Windows the default is
``cp1252``, so a reason string containing an em dash would read as mojibake with
no exception raised, which is the class of platform difference that reaches the
durable record silently.
"""

import logging
import re
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Final, Iterable, Optional

import yaml

from cmn.verdict import QuarantineEntry

logger = logging.getLogger(__name__)

_ENCODING: Final[str] = "utf-8"

# Key names that must never appear in a configuration file. A credential in
# configuration is committed, and a committed credential is disclosed.
_FORBIDDEN_KEYS: Final[frozenset[str]] = frozenset(
    {"api_key", "apikey", "secret", "token", "password", "credential"}
)

_REDACTED: Final[str] = "[REDACTED]"


@dataclass(frozen=True)
class EngineConfig:
    """One engine's roster entry.

    Attributes:
        engine (str): The registered engine name.
        model (str): The model identifier to request. Supplied here rather than
            in a case, per B8.
        spacing_sec (float): Minimum interval between live requests. Free-tier
            ceilings differ, so this is per engine.
        observations (int): How many repeat observations per case (A4).
        timeout_ms (int): Changing it changes results, so it is recorded.
    """

    engine: str
    model: str
    spacing_sec: float = 0.0
    observations: int = 3
    timeout_ms: int = 60000


@dataclass(frozen=True)
class UnsupportedPair:
    """One declared (case, engine) pair that cannot run.

    Attributes:
        case_id (str): Which case.
        engine (str): Which engine.
        reason (str): Why the pair cannot run, which is a capability statement
            rather than a failure.
    """

    case_id: str
    engine: str
    reason: str

    @property
    def key(self) -> str:
        """Return the pair as one identifier.

        Returns:
            str: Case and engine joined, for membership tests.
        """
        return f"{self.case_id}::{self.engine}"


def load_yaml_config(path: Path) -> dict[str, Any]:
    """Read one configuration file, refusing anything that carries a secret.

    Args:
        path (Path): The file to read.

    Returns:
        dict: The parsed mapping. **An absent file yields an empty mapping**
        rather than raising: a repository with no quarantine entries has no
        quarantine file, and that is a starting condition rather than an error.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the file will not
            parse, does not contain a mapping, or carries a forbidden key.
    """
    if not path.is_file():
        logger.info("No configuration at %s; continuing with defaults", path)
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding=_ENCODING))
    except yaml.YAMLError as error:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: {path} is not valid YAML"
        ) from error

    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: {path} parsed to {type(loaded).__name__} "
            f"rather than a mapping"
        )
    _refuse_credentials(path, loaded)
    return loaded


def _refuse_credentials(path: Path, payload: Any) -> None:
    """Refuse a configuration carrying anything credential-shaped.

    Checked at load rather than trusted, because a credential reaching a
    committed file is disclosed, and the check costs one walk of a small
    mapping.

    Args:
        path (Path): The file, for the message.
        payload (Any): The parsed structure, walked recursively.

    Returns:
        None

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` naming the key but
            **never the value**, which would put the secret in the log that
            reported it.
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower().replace("-", "_") in _FORBIDDEN_KEYS:
                raise ValueError(
                    f"QC_HARNESS_PARSER_ERROR: {path} carries {key!r}, and credentials "
                    f"are read from the environment rather than configuration"
                )
            _refuse_credentials(path, value)
    elif isinstance(payload, list):
        for entry in payload:
            _refuse_credentials(path, entry)


def load_engines(path: Path) -> dict[str, EngineConfig]:
    """Load the engine roster.

    Args:
        path (Path): The roster file.

    Returns:
        dict: Engine name to its configuration.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when an entry names no
            model. An engine with no model would dispatch against the adapter
            default, and the run would record a model nobody configured.
    """
    loaded = load_yaml_config(path)
    engines: dict[str, EngineConfig] = {}
    for name, entry in (loaded.get("engines") or {}).items():
        if not isinstance(entry, dict) or not entry.get("model"):
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: engine {name!r} in {path} names no model"
            )
        engines[str(name)] = EngineConfig(
            engine=str(name),
            model=str(entry["model"]),
            spacing_sec=float(entry.get("spacing_sec", 0.0)),
            observations=int(entry.get("observations", 3)),
            timeout_ms=int(entry.get("timeout_ms", 60000)),
        )
    return engines


def load_unsupported(path: Path) -> list[UnsupportedPair]:
    """Load the declared capability gaps.

    Args:
        path (Path): The file.

    Returns:
        list[UnsupportedPair]: Every declared pair. **A declared gap is not an
        environmental failure**, so these are excluded from the skip
        denominator rather than counted against it (A13).

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when an entry carries no
            reason. An undeclared reason makes the exclusion unauditable, and
            an unauditable exclusion is how a real failure gets parked.
    """
    loaded = load_yaml_config(path)
    pairs: list[UnsupportedPair] = []
    for entry in loaded.get("unsupported") or []:
        if not entry.get("reason"):
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: an unsupported pair in {path} carries no "
                f"reason, so its exclusion from the skip budget cannot be audited"
            )
        pairs.append(
            UnsupportedPair(
                case_id=str(entry["case_id"]),
                engine=str(entry["engine"]),
                reason=str(entry["reason"]),
            )
        )
    return pairs


def load_quarantine(path: Path) -> list[QuarantineEntry]:
    """Load the quarantine list.

    Args:
        path (Path): The file.

    Returns:
        list[QuarantineEntry]: Every entry, each carrying an expiry.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when an entry carries no
            expiry or no reason. **Without expiry, quarantine becomes where
            failures go to be forgotten** and the pass floor stops meaning
            anything, because everything inconvenient has left the denominator.
    """
    loaded = load_yaml_config(path)
    entries: list[QuarantineEntry] = []
    for entry in loaded.get("quarantine") or []:
        if not entry.get("expires_on"):
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: quarantine entry {entry.get('case_id')!r} in "
                f"{path} carries no expiry, and an entry that never lapses removes a "
                f"case from the denominator permanently"
            )
        if not entry.get("reason"):
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: quarantine entry {entry.get('case_id')!r} in "
                f"{path} carries no reason"
            )
        entries.append(
            QuarantineEntry(
                case_id=str(entry["case_id"]),
                reason=str(entry["reason"]),
                expires_on=_coerce_date(entry["expires_on"], path),
            )
        )
    return entries


def _coerce_date(value: Any, path: Path) -> date:
    """Turn a configured value into a date.

    Args:
        value (Any): What the loader produced. PyYAML parses an unquoted ISO
            date into a ``date`` already; a quoted one arrives as a string.
        path (Path): The file, for the message.

    Returns:
        date: The parsed date.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when it will not parse.
    """
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: {value!r} in {path} is not an ISO date"
        ) from error


def redact(payload: Any) -> Any:
    """Return a copy with every credential-shaped value replaced.

    Applied before anything reaches a log or an artifact. A credential read
    from the environment at runtime is legitimate; a credential **written into
    a durable record** is disclosed to everyone who can read that record.

    Args:
        payload (Any): The structure to redact.

    Returns:
        Any: The redacted copy, leaving the original untouched.
    """
    if isinstance(payload, dict):
        return {
            key: _REDACTED
            if str(key).lower().replace("-", "_") in _FORBIDDEN_KEYS
            else redact(value)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redact(entry) for entry in payload]
    return payload


def forbidden_keys() -> frozenset[str]:
    """Return the key names configuration may never carry.

    Returns:
        frozenset[str]: The forbidden names.
    """
    return _FORBIDDEN_KEYS


@dataclass(frozen=True)
class Consumer:
    """One case repository that pins this harness.

    **A registry entry, not a hardcoded list** (A12 applied to CI). The fan-out
    in ``regress-consumers-on-merge.yml`` runs across whatever this names, and
    gains a consumer without a workflow change.

    Attributes:
        name (str): How the consumer appears in a job name and a summary.
        repository (str): The owner and repository to check out.
        refs (dict): Harness branch to consumer ref. **The pairing is per
            branch** because a run is defined by a pair of refs and not by
            either alone (``ci_pipeline.md`` section 3C), so stabilization work
            on one side is verified against stabilization work on the other.
        default_ref (str): The consumer ref for a harness branch the mapping
            does not name, which is every feature branch. A feature branch pairs
            with the consumer's main: that is what the change meets on merge.
        command (str): What to run inside it. **Deterministic gates only**: the
            fan-out answers whether the harness still works for this consumer,
            and a live run would answer a different question at a price.
    """

    name: str
    repository: str
    refs: dict[str, str] = field(default_factory=dict)
    default_ref: str = "main"
    command: str = 'pytest -m "unit or system" --mode replay'

    def ref_for(self, harness_branch: str) -> str:
        """Return the consumer ref paired with a branch of this repository.

        Args:
            harness_branch (str): The branch of this repository under test.

        Returns:
            str: The mapped ref, or :attr:`default_ref` when the branch is not
            named. **An unnamed branch is not an error**: feature branches are
            created constantly and requiring a registry entry for each would
            make the registry the thing that blocks a branch from being tested.
        """
        return self.refs.get(harness_branch, self.default_ref)


def load_consumers(path: Path) -> list[Consumer]:
    """Load the case repositories that pin this harness.

    Args:
        path (Path): The registry file.

    Returns:
        list[Consumer]: Every declared consumer. **An absent file yields an
        empty list**: a harness with no registered consumers is a starting
        condition rather than an error, and the fan-out simply has nothing to
        do.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when an entry names no
            repository. A consumer that cannot be located would be reported
            unreachable on every run, which reads as a consumer problem when it
            is a registry typo.
    """
    loaded = load_yaml_config(path)
    consumers: list[Consumer] = []
    for entry in loaded.get("consumers") or []:
        if not entry.get("repository"):
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: a consumer in {path} names no repository, "
                f"so it would report unreachable on every run"
            )
        declared = entry.get("refs") or {}
        consumers.append(
            Consumer(
                name=str(entry.get("name") or entry["repository"]),
                repository=str(entry["repository"]),
                refs={str(branch): str(ref) for branch, ref in declared.items()},
                default_ref=str(entry.get("default_ref", "main")),
                command=str(
                    entry.get("command", 'pytest -m "unit or system" --mode replay')
                ),
            )
        )
    return consumers


def unreachable_consumer_code() -> str:
    """Return the code a consumer that could not be checked out records.

    **A harness event, never a red suite.** A private repository, a deleted
    branch or a rate-limited clone says nothing about whether this harness is
    sound. It is the same reasoning that makes a probe failure a
    ``QC_HARNESS_*`` event rather than a model finding.

    Returns:
        str: The registered code.
    """
    return "QC_HARNESS_DEPENDENCY_UNMET"


# The judge when nothing names one. A3 decided Gemini on 2026-09-19; this is
# that decision expressed as a value rather than as prose. It is a fallback,
# not a policy: config/engines.yaml carries the project's standing choice and
# --judge-engine overrides both.
_FALLBACK_JUDGE_ENGINE: Final[str] = "gemini"


def load_judge_engine(path: Path) -> str:
    """Return the judge engine the roster file names.

    Args:
        path (Path): The engine roster file.

    Returns:
        str: The configured engine, or the built-in fallback when the file
        names none. **An unconfigured clone still runs**, which is the same
        reasoning that gives each adapter a ``DEFAULT_MODEL``.
    """
    loaded = load_yaml_config(path)
    declared = (loaded.get("judge") or {}).get("engine")
    return str(declared) if declared else _FALLBACK_JUDGE_ENGINE



def resolve_judge_engine(
    requested: Optional[str],
    roster: dict[str, EngineConfig],
    *,
    can_judge: Callable[[str], bool],
) -> str:
    """Return the engine that will grade, or refuse with a reason.

    **A pure function of the configured value, the roster and a capability
    lookup**, so it is testable without a provider. The lookup is injected
    rather than imported because ``evaluation/`` imports nothing from
    ``execution/`` and capabilities are a Tier 2 record; resolving here keeps
    that edge from existing (``tier3_evaluation.md`` section 5A.2).

    Args:
        requested (Optional[str]): The engine asked for, or ``None`` to take
            whatever the caller already resolved from configuration.
        roster (dict): The engine roster.
        can_judge (Callable): Returns whether an engine declares the
            ``structured_output`` capability.

    Returns:
        str: The engine that will grade.

    Raises:
        ValueError: With ``QC_HARNESS_PREFLIGHT_FAILURE`` when the engine is
            absent from the roster or cannot return structured output.
            **Refused at load time rather than at the first judge call**: the
            difference is a run that does not start against a run that spends
            quota on candidates and then cannot grade them.
    """
    engine = requested or _FALLBACK_JUDGE_ENGINE

    if engine not in roster:
        raise ValueError(
            f"QC_HARNESS_PREFLIGHT_FAILURE: judge engine {engine!r} is not on the "
            f"roster, which names {', '.join(sorted(roster)) or 'nothing'}. This is "
            f"a misconfigured instrument, not a finding about a model"
        )

    # The capability gate, and the only thing that qualifies an engine to judge.
    # No list of permitted judge engines exists, because one would have to be
    # edited whenever an adapter is added.
    if not can_judge(engine):
        raise ValueError(
            f"QC_HARNESS_PREFLIGHT_FAILURE: judge engine {engine!r} does not declare "
            f"structured_output, so its reply cannot be schema-constrained and the "
            f"rubric could not be read back from it"
        )

    return engine


# The subject the probe watches the judge under. THE ROLE, NOT THE ENGINE
# FILLING IT: re-pointing the judge at a different engine or model registers as
# a version change and dispatches a live run, which is correct, because a
# different judge is a different instrument and every score recorded under the
# previous one was produced by something that no longer exists.
JUDGE_PROBE_SUBJECT: Final[str] = "judge"


def load_judge_model(path: Path, roster: dict[str, EngineConfig]) -> str:
    """Return the model the judge will use.

    Args:
        path (Path): The engine roster file.
        roster (dict): The loaded roster, used for the fallback.

    Returns:
        str: The configured judge model, or the roster entry for the judge's
        engine when none is configured. **The fallback is the behaviour every
        existing configuration relies on**: before a judge model could be
        named, the judge resolved to whatever model the roster gave its engine.
        Returning nothing here would leave the judge unresolvable and every
        graded run reporting a misconfigured instrument.
    """
    declared = (load_yaml_config(path).get("judge") or {}).get("model")
    if declared:
        return str(declared)
    entry = roster.get(load_judge_engine(path))
    return entry.model if entry is not None else ""


def probe_subjects(
    roster: dict[str, EngineConfig], judge_engine: str, judge_model: str
) -> dict[str, str]:
    """Return every subject the version probe watches, and its model.

    **The judge is a subject in its own right.** The probe otherwise walks the
    roster, and a judge model that differs from every candidate model is not in
    the roster: detection would work only while the judge happened to share a
    model with a candidate, which is a coincidence rather than a property
    (``tier3_evaluation.md`` section 5A.4).

    Args:
        roster (dict): The engine roster.
        judge_engine (str): The engine the judge uses.
        judge_model (str): The model the judge uses.

    Returns:
        dict: Subject to model. Candidate subjects are keyed by engine; the
        judge is keyed :data:`JUDGE_PROBE_SUBJECT`.
    """
    subjects = {engine: entry.model for engine, entry in roster.items()}
    if judge_engine and judge_model:
        subjects[JUDGE_PROBE_SUBJECT] = judge_model
    return subjects


@dataclass(frozen=True)
class HarnessConfig:
    """Everything the three configuration files supply.

    Attributes:
        engines (dict): The engine roster.
        unsupported (list): Declared capability gaps.
        quarantine (list): Quarantined cases with their expiries.
        judge_engine (str): Which engine grades, per A3 and
            ``tier3_evaluation.md`` section 5A. Named here rather than
            hardcoded in ``evaluation/`` so selecting another is a
            configuration entry, never a code change.
        judge_model (str): Which model grades. **Separate from the candidate
            model on the same engine**, which is the configuration the probe
            could not see before section 5A.4.
    """

    engines: dict[str, EngineConfig] = field(default_factory=dict)
    unsupported: list[UnsupportedPair] = field(default_factory=list)
    quarantine: list[QuarantineEntry] = field(default_factory=list)
    judge_engine: str = _FALLBACK_JUDGE_ENGINE
    judge_model: str = ""

    def unsupported_keys(self) -> frozenset[str]:
        """Return every declared pair as one identifier.

        Returns:
            frozenset[str]: The pair keys.
        """
        return frozenset(pair.key for pair in self.unsupported)


def load_harness_config(config_dir: Optional[Path] = None) -> HarnessConfig:
    """Load all three configuration files from one directory.

    Args:
        config_dir (Optional[Path]): Where the files live. Defaults to
            ``config/`` beside the repository root.

    Returns:
        HarnessConfig: Everything configuration supplies, with absent files
        yielding empty collections rather than raising.
    """
    root = config_dir or Path("config")
    engines = load_engines(root / "engines.yaml")
    return HarnessConfig(
        engines=engines,
        unsupported=load_unsupported(root / "unsupported.yaml"),
        quarantine=load_quarantine(root / "quarantine.yaml"),
        judge_engine=load_judge_engine(root / "engines.yaml"),
        judge_model=load_judge_model(root / "engines.yaml", engines),
    )


# The credential file `.env.example` has always told readers to create. It is
# gitignored; `.env.example` is tracked and carries no real key.
ENV_FILE: Final[str] = ".env"

# Variables a CI runner sets. Their presence means credentials arrive from the
# GitHub Environment named `live`, and a file must not compete with that.
_CI_MARKERS: Final[tuple[str, ...]] = ("CI", "GITHUB_ACTIONS")

# WHAT A CREDENTIAL LOOKS LIKE. Matched loosely on purpose: the check
# reports a name nothing reads, and a typo is exactly the case it is for,
# so a pattern that demanded the correct spelling would miss every one.
_CREDENTIAL_SHAPED: Final[re.Pattern] = re.compile(
    r"(KEY|TOKEN|SECRET|CREDENTIAL|PASSWORD)$", re.IGNORECASE
)


def load_env_file(root: Path, environ: Optional[dict[str, str]] = None) -> list[str]:
    """Load a ``.env`` file into the environment, without overwriting it.

    **Explicit environment wins.** A variable already set is never replaced:
    somebody who exported a key in their shell meant that key, and a file
    quietly overriding it would succeed against the wrong account.

    **A value is never logged**, here or anywhere. Only names are, which is the
    same rule that governs artifacts.

    Args:
        root (Path): The directory holding the file.
        environ (Optional[dict]): The mapping to populate, defaulting to the
            real environment. Injected so a test never touches the process.

    Returns:
        list[str]: The names set by this call, in file order, excluding any
        that were already present. **An absent file returns nothing and is not
        an error**: the suite runs without credentials by design. **Under CI
        nothing is read at all**, because credentials there come from the
        GitHub Environment (section 10.34.3).

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` naming the line number of
            a line that is neither blank, a comment, nor ``NAME=VALUE``.
            **Skipping it would mean a key silently did not load**, and the
            symptom would be an authentication failure somewhere far away.
    """
    target = environ if environ is not None else os.environ

    # REFUSED UNDER CI, not merely unnecessary there. A credential file on a
    # runner would arrive by a path nobody audited, and "harmless because
    # nothing calls it" is the failure this project keeps correcting.
    if any(marker in target for marker in _CI_MARKERS):
        logger.info("%s ignored: CI supplies credentials from its own store", ENV_FILE)
        return []

    source = root / ENV_FILE
    if not source.is_file():
        return []

    applied: list[str] = []
    for number, raw in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        name = name.removeprefix("export ").strip()
        if not separator or not name:
            # WARNED, NOT REFUSED. Raising here broke on an ordinary note in a
            # real file, and a credential file that stops the suite is worse
            # than one that says which line it skipped. The line number is
            # named and the line never is, because it may carry a key.
            logger.warning(
                "%s line %d is not NAME=VALUE and was skipped. If a key was "
                "meant here it did not load",
                ENV_FILE, number,
            )
            continue
        if name in target:
            continue
        target[name] = value.strip().strip('"').strip("'")
        applied.append(name)

    if applied:
        logger.info(
            "%s supplied %d variable(s): %s", ENV_FILE, len(applied), ", ".join(applied)
        )
    return applied


def orphan_credentials(
    names: Iterable[str], engine_variables: Iterable[str]
) -> list[str]:
    """Return credential-shaped names no registered engine reads.

    **A credential nothing reads is a silent misconfiguration.** A name
    differing from the one an SDK expects by an underscore or a letter's case
    loads cleanly, sets a variable, and reaches no engine, and the file it lives
    in is one a reader is told not to print (design section 10.34.6).

    Args:
        names (Iterable[str]): The names a credential file assigns.
        engine_variables (Iterable[str]): The names the registered engines
            declare. **Passed in rather than imported**, because ``cmn`` does
            not import ``execution`` and a registry lookup here would create
            that edge.

    Returns:
        list[str]: Orphaned names in sorted order, empty when every
        credential-shaped name is read by something. **Names only, never
        values**: this check exists to be run against a real credential file.
    """
    known = {name.upper() for name in engine_variables}
    return sorted(
        name for name in names
        if _CREDENTIAL_SHAPED.search(name) and name.upper() not in known
    )


def warn_orphan_credentials(root: Path, engine_variables: Iterable[str]) -> list[str]:
    """Warn about a credential in the file that no engine reads.

    **A warning and not a refusal.** A file may legitimately carry a credential
    for something outside this harness, and refusing to start over a name we
    merely do not recognise would be the harness overreaching. What it must not
    do is stay silent (design section 10.34.6).

    Args:
        root (Path): The directory holding the credential file.
        engine_variables (Iterable[str]): The names registered engines read.

    Returns:
        list[str]: The orphaned names, already logged. **Names only.**
    """
    source = root / ENV_FILE
    if not source.is_file():
        return []
    assigned: list[str] = []
    for raw in source.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, _ = line.partition("=")
        if separator:
            assigned.append(name.removeprefix("export ").strip())

    orphans = orphan_credentials(assigned, engine_variables)
    for name in orphans:
        logger.warning(
            "%s names %s, which no registered engine reads. Check the "
            "spelling against the variable the provider's SDK expects",
            ENV_FILE, name,
        )
    return orphans
