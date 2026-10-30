# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Shared pytest hook bodies, which each repository's ``conftest.py`` delegates to.

Created: 2026-09-23
Last updated: 2026-10-29

This file contains ``add_mqc_options``, which registers the execution flags
from the shared option registry; ``configure_invocation``, which records what
the run was invoked with and adopts the corpus selection and artifact
destinations; ``require_rostered_engine``; ``label_priority_severity``, which
turns a priority marker into an Allure severity; ``label_grouping``, which
gives each item the epic, feature and story a report groups by; and the readers
``case_module``, ``case_identifier``, ``item_priority`` and ``announce_test``.

pytest calls these through the hooks of both repositories' ``conftest.py`` at
option parsing, configuration, collection and setup, so both suites accept the
same flags and label the same way before any case runs.

Extracted 2026-09-23, when the split made a second ``conftest.py`` necessary.

**A consumer's suite is invoked with the same flags as ours.** ``--mode
replay`` is in the fan-out command in ``config/consumers.yaml``, and a flag
pytest has not been told about is an argument error before a single test runs.
A case repository therefore has to register the option registry exactly as this
one does.

**Two conftest files registering the same flags would drift**, and the symptom
would be a report contradicting the run it describes: a consumer accepting a
value we reject, or defaulting a flag differently and attributing the
difference to the model. ``cmn_verdict_and_cli.md`` section 7.1 already names
two surfaces for the option registry, the pytest parser and the standalone
verdict tool, and neither states a flag twice. A consumer is a third caller of
the first surface, not a second definition of it.

The consumer's ``conftest.py`` is therefore a delegation:

.. code-block:: python

    from cmn.pytest_support import (
        add_mqc_options, configure_invocation, label_priority_severity,
        select_priority_bands,
    )

    def pytest_addoption(parser): add_mqc_options(parser)
    def pytest_configure(config): configure_invocation(config)
    def pytest_runtest_setup(item): enforce_dependencies(item)
    def pytest_collection_modifyitems(config, items):
        label_priority_severity(items)
        label_grouping(items, config.rootpath)
        select_priority_bands(config, items)
        arrange_dependencies(items)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(item, call):
        record_from_report(item, (yield).get_result())

**Fixtures are deliberately not here.** The harness fixtures build
:class:`~ingestion.schemas.EvaluationCase` records from sample payloads, which
is harness test scaffolding rather than a capability a case repository
consumes. Exporting them would put harness-internal shapes into a consumer's
namespace and invite a case to assert against one.
"""

import logging
import re
from pathlib import Path
from typing import Any, Final, Optional

import pytest

from cmn.config import load_engines, packaged_roster_path
from cmn.environments import is_precondition
from cmn.grouping import load_grouping, story_for
from cmn.options import Option, build_invocation, registered_options
from cmn.provenance import provenance_fields, testsuite_properties, write_provenance
from cmn.report_categories import write_categories

logger = logging.getLogger(__name__)

# P0 blocks, P4 is trivial. The mapping is the one place the two vocabularies
# meet, and it is here rather than in a conftest so a consumer cannot hold a
# different opinion about what P2 means.
_SEVERITY_BY_PRIORITY: dict[int, str] = {
    0: "blocker",
    1: "critical",
    2: "normal",
    3: "minor",
    4: "trivial",
}


def _add_pytest_option(group: Any, declared: Option) -> None:
    """Add one declared option to a pytest parser group.

    Args:
        group (Any): The option group.
        declared (Option): Its registration.

    Returns:
        None
    """
    if declared.is_flag:
        group.addoption(
            declared.cli_flag, action="store_true", default=declared.default,
            help=declared.help_text,
        )
        return
    group.addoption(
        declared.cli_flag,
        # Declared on every enumerated flag, so a typo fails at parse time with
        # the valid values listed rather than deep inside a run that has already
        # spent quota.
        choices=list(declared.choices) if declared.choices else None,
        default=declared.default,
        help=declared.help_text,
    )


def add_mqc_options(parser: Any) -> None:
    """Declare the execution flags from the shared option registry.

    **The first of the two surfaces** (``cmn_verdict_and_cli.md`` section 7.1).
    The standalone verdict tool builds its ``argparse`` parser from the same
    registry, so a flag cannot exist on one surface and not the other, and
    neither can accept a value the other rejects.

    ``pytest_addoption`` is argparse-backed, so these gain autogenerated help
    through ``pytest --help`` without a second parser competing for
    ``sys.argv``.

    Args:
        parser (Any): pytest's parser.

    Returns:
        None
    """
    group = parser.getgroup("mqc", "AP-Model-QC execution options")
    for declared in registered_options():
        _add_pytest_option(group, declared)



def _flags_named(config: Any) -> frozenset[str]:
    """Return the flags the caller actually wrote, however they wrote them.

    **Comparing a value against its default cannot answer this.** Choosing the
    default explicitly and choosing nothing produce the same value, so
    `--engine gemini` read as an unchosen provider and every deliberate run
    carried `QC_DATA_ENGINE_DEFAULTED`. A warning that fires when the thing it
    warns about did not happen is worse than no warning: it teaches the reader
    to skip the line.

    **Both spellings count.** pytest accepts `--engine gemini` and
    `--engine=gemini`, and a reader choosing the second did not choose less.

    Args:
        config (Any): pytest's configuration, carrying the raw invocation.

    Returns:
        frozenset[str]: Every flag present on the command line, including its
        leading dashes. **Empty where the invocation is unavailable**, which
        falls back to the value comparison rather than raising: a warning is not
        worth failing a run over.
    """
    params = getattr(config, "invocation_params", None)
    arguments = list(getattr(params, "args", ()) or ())
    return frozenset(
        argument.split("=", 1)[0]
        for argument in arguments
        if isinstance(argument, str) and argument.startswith("-")
    )


# RESOLVED WHEN THE RUN IS CONFIGURED, not read per call. The corpus is loaded
# by cached functions that hold no configuration, which is the same reason
# `adopt_carried_outcomes` resolves here. Design section 4.6.
_CORPUS_SELECTION: dict[str, Optional[str]] = {"root": None, "unknown_columns": None}


def adopt_corpus_selection(config: Any) -> None:
    """Record which corpus the run names and how its CSV is to be read.

    Args:
        config (Any): pytest's configuration.

    Returns:
        None
    """
    named = config.getoption("--golden-rules", None)
    policy = config.getoption("--extra-columns", None)
    _CORPUS_SELECTION["root"] = str(named) if named else None
    _CORPUS_SELECTION["unknown_columns"] = str(policy) if policy else None


def corpus_selection() -> tuple[Optional[Path], Optional[str]]:
    """Return the corpus the run named and its unknown-column policy.

    **Both may be absent, and absent is not a default.** This repository owns no
    corpus, so it cannot know what "repo default" means; the caller substitutes
    its own. Design section 4.6.

    Returns:
        tuple: The named corpus root or ``None``, and the policy or ``None``.
    """
    root = _CORPUS_SELECTION["root"]
    return (Path(root) if root else None), _CORPUS_SELECTION["unknown_columns"]


# WHAT EACH MANDATED ARTIFACT IS CALLED UNDER `--out-dir`, and the pytest option
# each destination lives in. `testing-standards.md` section 5 mandates both, so
# this is a pair and not a list to choose from. Design section 7.1.0.2.
# THE OPTION HOLDING THE RAW RESULTS DIRECTORY, named once because the
# destination table sets it and the category file is written into it.
_ALLURE_DESTINATION: Final[str] = "allure_report_dir"

# THE ONE MODE WITH A PROVIDER TO ASK. A replay run's version is in the fixture
# it reads and a precondition run holds no credential (design section 5.6.2).
_LIVE_MODE: Final[str] = "live"

_ARTIFACT_DESTINATIONS: Final[tuple[tuple[str, str], ...]] = (
    ("xmlpath", "junit.xml"),
    (_ALLURE_DESTINATION, "allure-results"),
)


def adopt_artifact_destinations(config: Any) -> list[str]:
    """Point each unnamed artifact destination inside the named output directory.

    Reads ``--out-dir`` and sets pytest's ``xmlpath`` and the Allure report
    directory to ``junit.xml`` and ``allure-results`` beneath it. **A
    destination the caller named is left alone**, so an explicit ``--junitxml``
    redirects that artifact while the other is still written.

    Does nothing when ``--out-dir`` is absent, and skips a destination whose
    option pytest does not have: ``allure-pytest`` is a ``[dev]`` dependency, so
    its option is missing when the plugin is not loaded.

    Design: ``cmn_verdict_and_cli.md`` section 7.1.0.2.

    Args:
        config (Any): pytest's configuration.

    Returns:
        list: The destinations set, as ``option=path`` strings, for the record.
    """
    named = config.getoption("out_dir", "")
    if not named:
        return []

    root = Path(str(named))
    adopted: list[str] = []
    for attribute, leaf in _ARTIFACT_DESTINATIONS:
        if not hasattr(config.option, attribute):
            continue
        if getattr(config.option, attribute):
            continue
        setattr(config.option, attribute, str(root / leaf))
        adopted.append(f"{attribute}={root / leaf}")

    if adopted:
        logger.info("Artifacts derived from --out-dir %s: %s", root, ", ".join(adopted))
    return adopted


def adopt_report_categories(config: Any) -> Optional[Path]:
    """Write the failure-cause classification beside the run's raw results.

    A report's Categories tab is built from a file in the results directory,
    so it is written at configuration rather than at the end: a run that
    crashes still leaves a classifiable result set behind.

    **Does nothing where the run writes no Allure results**, which covers a run
    invoked without the directory and a machine without the reporting extra,
    whose option does not exist at all (``harness_test_taxonomy.md`` section
    16.7). **A failed write is logged and never raises**, a classification
    being a reporting convenience that must not cost a measurement.

    Design: ``harness_test_taxonomy.md`` section 16.9.

    Args:
        config (Any): pytest's configuration.

    Returns:
        Optional[Path]: The file written, or ``None`` where none was.
    """
    if not hasattr(config.option, _ALLURE_DESTINATION):
        return None
    named = getattr(config.option, _ALLURE_DESTINATION) or ""
    if not named:
        return None
    try:
        return write_categories(Path(str(named)))
    except OSError as error:
        logger.warning(
            "Report categories were not written to %s: %s", named, error
        )
        return None


def asks_the_provider(config: Any) -> bool:
    """Say whether this run has a provider to ask what it serves.

    **Only a live run does.** A replay run measured a recording, so the version
    that produced its responses is in the fixture and is both the correct
    answer and the only one available; a precondition run holds no credential
    by design and has nothing to ask. Asking regardless is what would make a
    suite of 960 preconditions contact four vendors to label itself
    (``tier2_execution.md`` section 5.2.1).

    Args:
        config (Any): pytest's configuration.

    Returns:
        bool: True only where the mode is live and an engine was selected.
    """
    if str(getattr(config.option, "mode", "") or "") != _LIVE_MODE:
        return False
    return bool(str(getattr(config.option, "engine", "") or ""))


def adopt_provenance(config: Any, reader: Any) -> dict[str, str]:
    """Build what this run measured against, and write the half a report reads.

    **One implementation and two callers**, each repository's ``conftest.py``,
    which is the arrangement ``framework-rules.md`` section 4.1 asks for. The
    mapping is returned as well as written because the two artifacts are
    selected by separate flags: a run given ``--junitxml`` and no
    ``--alluredir`` still states its subject, and a mapping built inside one
    writer could not reach the other (design section 5.6).

    A report's environment block is built from a file in the results
    directory, so it is written at configuration for the reason
    :func:`adopt_report_categories` is: a run that crashes still leaves a
    report saying what it was measuring. **A failed write is logged rather than
    raised**, and a run writing no Allure results writes nothing: provenance is
    a reporting obligation that must not cost a measurement.

    **The reader is passed in rather than imported.** Asking a provider means
    calling an adapter, and ``cmn`` does not import ``execution``: that
    direction is the module separation in ``framework-rules.md`` section 2.
    Taking the callable keeps the decision about **when** to ask here, where
    both repositories share it, and the ability to ask there, where the
    adapters are.

    Args:
        config (Any): pytest's configuration.
        reader (Any): A callable taking an engine and a model and returning
            the served facts, as ``execution.preflight.served_facts`` does.
            **Called only where :func:`asks_the_provider` holds.**

    Returns:
        dict[str, str]: As :func:`cmn.provenance.provenance_fields` returns.
    """
    engine = str(getattr(config.option, "engine", "") or "")
    model = rostered_model(engine)
    served: dict[str, str] = {}
    if model and asks_the_provider(config):
        served = reader(engine, model)
    fields = provenance_fields(
        engine=engine,
        mode=str(getattr(config.option, "mode", "") or ""),
        requested_model=model,
        served=served,
    )
    _write_provenance_beside_results(config, fields)
    return fields


def _write_provenance_beside_results(
    config: Any, fields: dict[str, str]
) -> Optional[Path]:
    """Write the mapping where an Allure report reads it, if the run writes one.

    Args:
        config (Any): pytest's configuration.
        fields (dict): As :func:`adopt_provenance` returns.

    Returns:
        Optional[Path]: The file written, or ``None`` where none was.
    """
    if not hasattr(config.option, _ALLURE_DESTINATION):
        return None
    named = getattr(config.option, _ALLURE_DESTINATION) or ""
    if not named:
        return None
    try:
        return write_provenance(Path(str(named)), fields)
    except OSError as error:
        logger.warning("Run provenance was not written to %s: %s", named, error)
        return None


def publish_run_provenance(recorder: Any, fields: dict[str, str]) -> None:
    """Record the same mapping as the properties a JUnit report carries.

    **Run scoped, through the session fixture.** The per-case form warns under
    the ``xunit2`` family pytest writes by default, and it would cost a format
    downgrade for a label that does not vary between cases
    (design section 5.6.2).

    Args:
        recorder (Any): pytest's ``record_testsuite_property`` fixture.
        fields (dict): As :func:`run_provenance` returns.

    Returns:
        None
    """
    for name, value in testsuite_properties(fields):
        recorder(name, value)


def rostered_model(engine: str) -> str:
    """Return the model the roster asks for, or empty where it cannot be read.

    **Public because ``conftest.py`` needs the same answer.** It asks the
    provider what it serves, which takes the model identifier, and a second
    roster read there would be two implementations of one question.

    Args:
        engine (str): The engine selected for this run.

    Returns:
        str: The configured model identifier, empty where the roster is absent
        or names no such engine. **Empty rather than raising**: provenance is
        reporting, and a run must not fail because its own label is incomplete.
    """
    if not engine:
        return ""
    try:
        roster = load_engines(packaged_roster_path())
    except (OSError, ValueError) as error:
        logger.warning("Provenance could not read the engine roster: %s", error)
        return ""
    entry = roster.get(engine)
    return entry.model if entry is not None else ""


def configure_invocation(config: Any) -> None:
    """Record what the run was invoked with, and warn on a defaulted engine.

    **Every flag that can change a result is recorded**, and a defaulted engine
    emits a warning into the artifact so a cloned repository running
    unconfigured produces a record saying so (A7.4).

    Args:
        config (Any): pytest's configuration.

    Returns:
        None
    """
    named = _flags_named(config)
    supplied = {
        declared.metadata_key: config.getoption(declared.metadata_key)
        for declared in registered_options()
        if declared.cli_flag in named
        or config.getoption(declared.metadata_key, None) not in (None, declared.default)
    }
    invocation = build_invocation(supplied)
    config.mqc_invocation = invocation
    adopt_corpus_selection(config)
    adopt_artifact_destinations(config)
    # AFTER THE DESTINATION IS FINAL, so the classification lands where the
    # results do whether the directory was named or derived from --out-dir
    # (`harness_test_taxonomy.md` section 16.9).
    adopt_report_categories(config)
    # THE ROSTER GATES THE RUN, not the adapter registry and not a list in the
    # option registry. An engine with an adapter and no roster entry dispatched
    # against the adapter's default model, which for grok was one the provider
    # does not serve. Design `tier2_execution.md` section 3.5.
    require_rostered_engine(
        str(config.getoption("--engine", "") or ""),
        load_engines(packaged_roster_path()),
    )
    for warning in invocation.warnings:
        logger.warning("%s", warning)


def require_rostered_engine(engine: str, roster: dict[str, Any]) -> None:
    """Refuse an engine the roster does not configure.

    **The roster is the list, and it is the expandable one.** Adding a provider
    is an entry in ``config/engines.yaml``, and until it has one the engine does
    not run. On the list it works, off the list it refuses, and the remedy is
    named in the message.

    **Two lists exist and only one of them can gate a run.** The adapter
    registry says code exists for a provider; the roster says a model, an
    observation count and a request spacing are configured for it. An engine
    with an adapter and no roster entry resolved its model to ``None`` and
    dispatched against the **adapter's own default**, which is how
    ``--engine grok`` would have run against ``grok-4``: a model the provider
    does not serve, failing per case rather than refusing once.

    **Refusing once is the point.** A 404 on every case reads as a broken
    harness or an unavailable provider; one refusal naming the roster reads as
    configuration not yet done, which is what it is.

    Design: ``tier2_execution.md`` section 3.5.

    Args:
        engine (str): The engine a run named.
        roster (dict): The loaded engine roster.

    Returns:
        None

    Raises:
        ValueError: With ``QC_HARNESS_PREFLIGHT_FAILURE`` when the engine has no
            roster entry, naming every engine that does. **A preflight code
            rather than a parser one**: the flag's value is well formed and the
            configuration for it is absent, which is an environment fact.
    """
    if not engine or engine in roster:
        return
    raise ValueError(
        f"QC_HARNESS_PREFLIGHT_FAILURE: engine {engine!r} is not on the roster, "
        f"so no model, observation count or request spacing is configured for "
        f"it and a run would dispatch against the adapter's own default. "
        f"Rostered engines are {sorted(roster)}. Add an entry to "
        f"config/engines.yaml, or declare its absence under not_rostered"
    )


def registered_priority_levels() -> frozenset[int]:
    """Return every priority level the scale defines.

    **Read from the severity map rather than restated as a range.** The map is
    what translates a priority into an Allure label, so a level that can be
    assigned is exactly a level that can be reported, and a second statement of
    0 to 4 would be a copy that drifts.

    Returns:
        frozenset[int]: The assignable levels.
    """
    return frozenset(_SEVERITY_BY_PRIORITY)


def label_priority_severity(items: list[pytest.Item]) -> None:
    """Translate the priority marker into an Allure severity label.

    **One source of truth, two consumers.** The run-verdict gate reads the
    marker and downstream analysis reads the label. Maintaining the label by
    hand would give two places to state one fact.

    **A precondition carries no priority and therefore no severity.** The hook
    leaves it unset rather than inventing a default, because a default would
    make preconditions sortable by a severity nobody assigned
    (``framework-rules.md`` section 3.3).

    Args:
        items (list): The collected test items.

    Returns:
        None
    """
    for item in items:
        marker = item.get_closest_marker("priority")
        if marker is None:
            continue
        level = int(marker.args[0])
        severity = _SEVERITY_BY_PRIORITY.get(level)
        if severity is None:
            logger.warning(
                "Test %s carries priority %d, which is not 0 to 4", item.name, level
            )
            continue
        item.add_marker(pytest.mark.allure_label(severity, label_type="severity"))


# THE LABEL MARKER ALLURE READS, which both hooks below write and read. A
# decorator writes the same marker, which is what makes a declared label
# visible here and therefore overridable.
_LABEL_MARKER: Final[str] = "allure_label"


def _declared_label_types(item: pytest.Item) -> set[str]:
    """Return every label type an item already carries.

    Args:
        item (pytest.Item): The collected item.

    Returns:
        set[str]: The ``label_type`` of each Allure label marker on the item,
        its class and its module.
    """
    return {
        str(marker.kwargs.get("label_type") or "")
        for marker in item.iter_markers(name=_LABEL_MARKER)
    }


def label_grouping(items: list[pytest.Item], root: Path) -> None:
    """Give each collected item the epic, feature and story a report groups by.

    The epic and the capability come from ``config/allure_features.yaml`` and
    the story from the test class, so the grouping arrives derived rather than
    typed on 239 classes (``harness_test_taxonomy.md`` section 16).

    **A label an item already declares is left alone.** Allure unions the
    label markers an item carries and treats none of these three as unique, so
    adding one beside a declared one publishes both and the report grows a
    branch for each. A decorator is therefore an override rather than a
    competitor, which is what keeps a hand-written story worth writing
    (section 16.2.1).

    **A module with no declared capability is labelled with what there is.**
    The absence is a unit failure in its own case, and refusing the run from a
    collection hook would turn a reporting gap into a suite that does not
    execute.

    Args:
        items (list): The collected test items.
        root (Path): The repository root, which the declaration is read from
            and module paths are taken relative to.

    Returns:
        None
    """
    grouping = load_grouping(root)
    for item in items:
        declared = _declared_label_types(item)
        holder = getattr(item, "cls", None)
        story = story_for(holder.__name__) if holder is not None else ""
        try:
            module = item.path.relative_to(root).as_posix()
        except ValueError:
            module = ""
        wanted = (
            ("epic", grouping.epic),
            ("feature", grouping.modules.get(module, "")),
            ("story", story),
        )
        for label_type, value in wanted:
            if value and label_type not in declared:
                item.add_marker(pytest.mark.allure_label(value, label_type=label_type))


# THE SUITES ROOT A PRECONDITION TAKES. It cannot be a band: a precondition
# carries no priority, sitting above the scale rather than inside it
# (`framework-rules.md` section 3.3). Design section 16.8.2.
PRECONDITION_SUITE: Final[str] = "Preconditions"

# THE LABEL NAMING THAT ROOT, which is in Allure's unique set, so a declared
# one replaces the module path the plugin would otherwise derive rather than
# publishing a second branch beside it (section 16.8.1).
_SUITE_ROOT: Final[str] = "parentSuite"
_TAG: Final[str] = "tag"


def label_band_suite(items: list[pytest.Item]) -> None:
    """Give each collected item the Suites root and the tag a reader filters by.

    A graded item's root is its band, ``P0`` through ``P4``, and a
    precondition's is :data:`PRECONDITION_SUITE`. The same value is published
    as a tag, because the Suites tab navigates and a tag filters, and a reader
    comparing one band inside the capability tree needs the second.

    **The module and the class are left to the plugin**, giving band, then
    module, then class. Those two levels are already the grouping wanted inside
    a band and they cost no code.

    **An item declaring its own root keeps it**, which is the override
    discipline section 16.2.1 states for a capability, applied to a label that
    replaces rather than unions.

    Design: ``harness_test_taxonomy.md`` section 16.8.

    Args:
        items (list): The collected test items.

    Returns:
        None
    """
    for item in items:
        marker = item.get_closest_marker("priority")
        if marker is not None:
            level = int(marker.args[0])
            if level not in _SEVERITY_BY_PRIORITY:
                continue
            root = f"P{level}"
        elif is_precondition(item.nodeid):
            root = PRECONDITION_SUITE
        else:
            continue
        if _SUITE_ROOT not in _declared_label_types(item):
            item.add_marker(pytest.mark.allure_label(root, label_type=_SUITE_ROOT))
        item.add_marker(pytest.mark.allure_label(root, label_type=_TAG))


# Identifiers look like MQC_<MODULE>_<LAYER>_<5 digits>_<behaviour>.
# FIVE OR SIX, DELIBERATELY. This extracts a number so the cascade can
# resolve a dependency; it does not validate the width, which
# `.pylintrc` enforces on every real definition. The dependency
# fixtures embed a sub-suite whose callables are named in the 90xxx
# range, and a resolver that refused them would break the cascade's own
# test. Design `harness_test_taxonomy.md` section 3.2.1.3.
_IDENTIFIER = re.compile(r"MQC_[A-Z]+_[A-Z]{3,5}_(\d{5,6})_")


def case_module(name: str) -> Optional[str]:
    """Return the module token a test name carries.

    Args:
        name (str): The test callable's name, such as
            ``MQC_CMN_UNI_112254_a_module_selection_keeps_only_...``.

    Returns:
        Optional[str]: The module, or ``None`` for a name that carries none.
        **Read from the name rather than from the path**, because the path
        gives the directory and a case's module is a property of its
        identifier, which `testing-standards.md` makes normative.
    """
    parts = name.split("_")
    return parts[1] if len(parts) > 2 and parts[0] == "MQC" else None


def case_identifier(name: str) -> Optional[str]:
    """Return the five-digit identifier a test name carries.

    Args:
        name (str): The test callable's name.

    Returns:
        Optional[str]: The identifier, or ``None`` for a name that carries
        none. **Identifiers are the only stable handle in the suite**: a
        behaviour suffix changes when the behaviour is reworded, and a
        dependency that breaks on a rename is one nobody maintains.
    """
    matched = _IDENTIFIER.search(name)
    return matched.group(1) if matched else None


def item_priority(item: pytest.Item) -> Optional[int]:
    """Return the priority a test declares, or None.

    Args:
        item (pytest.Item): The collected test.

    Returns:
        Optional[int]: The band, absent on a precondition which carries none.
    """
    marker = item.get_closest_marker("priority")
    if marker is None or not marker.args:
        return None
    try:
        return int(marker.args[0])
    except (TypeError, ValueError):
        return None


def announce_test(item: pytest.Item) -> str:
    """Log which case is about to run, before it runs.

    **Emitted from setup, so a crash leaves the name behind.** A traceback
    names the line that raised and not the case that reached it, and a process
    killed mid-request leaves no traceback at all. The last announced name is
    the one thing that locates the work either way, which is what a mean time
    to repair is measured against.

    **The node identifier rather than the callable's name**, because it carries
    the module and the class as well: that is the code segment a reader opens,
    and `framework-rules.md` section 3.1 holds that naming the segment is what
    a result establishes.

    Design: ``harness_test_taxonomy.md`` section 8.3.1.

    Args:
        item (pytest.Item): The test about to run.

    Returns:
        str: The line that was logged, so a case can assert it without
        reaching into the logging machinery.
    """
    line = f"RUNNING {getattr(item, 'nodeid', '?')}"
    logger.info("%s", line)
    return line
