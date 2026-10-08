# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The dependency cascade: ordering, enforcement, probing and the carry file.

Specified by ``cmn_verdict_and_cli.md`` section 10.28.

**Split from ``pytest_support.py`` on 2026-10-07**, which the probe took to 919
lines against the nine-hundred-line runway ceiling. The subject is one: a case
whose result others presuppose is marked ``base``, its dependents are ordered
after it, and what happens to them when it does not hold.

**What stayed behind is name parsing and marker reading.** ``case_module``,
``case_identifier`` and ``item_priority`` are used by the cascade and owned by
neither it nor this module's subject.

**Replay probes and live skips** (section 10.28.2.1): a dependent of a failed
foundation may carry its own defect rather than a second report of the
foundation's, and nothing can tell which without running it.
"""

import logging
import os
import platform
from pathlib import Path
from typing import Any, Final

import pytest

from cmn.prerequisites import Provenance, read_outcomes, write_outcomes
from cmn.pytest_support import case_identifier, item_priority

logger = logging.getLogger(__name__)



_UNMET: Final[str] = "QC_HARNESS_DEPENDENCY_UNMET"

# THE CASCADE'S MEMORY, keyed by the five-digit identifier of a base case.
# Module level because pytest hooks are free functions and the two halves of
# the cascade run in different hooks: one records, the other reads.
_BASE_OUTCOMES: dict[str, bool] = {}

# IDENTIFIERS ADMITTED FROM AN EARLIER BAND, kept apart from the outcomes so
# `unknown_dependencies` can tell a foundation this execution collected from
# one it is entitled to assume. Design section 7.6.
_CARRIED: set[str] = set()

def reset_dependency_state() -> None:
    """Forget every recorded base outcome.

    Returns:
        None: Used between runs in the same process, which is what a test of
        the cascade itself needs.
    """
    _BASE_OUTCOMES.clear()
    _CARRIED.clear()

def adopt_carried_outcomes(carried: dict[str, bool]) -> None:
    """Seed the cascade with foundations an earlier band established.

    **Seeded, not merged over.** An outcome this execution records itself wins,
    because it measured the case and the carried record only remembers it.

    Args:
        carried (dict): Identifier to whether that foundation held.

    Returns:
        None
    """
    for identifier, held in carried.items():
        _BASE_OUTCOMES.setdefault(str(identifier), bool(held))
    _CARRIED.update(str(identifier) for identifier in carried)

def carried_identifiers() -> frozenset[str]:
    """Return the identifiers admitted from an earlier band.

    Returns:
        frozenset[str]: The carried identifiers, empty for a first band.
    """
    return frozenset(_CARRIED)

def established_outcomes() -> dict[str, bool]:
    """Return every base outcome this execution knows.

    **Including the carried ones**, so a third band reads one record rather
    than one per band it follows.

    Returns:
        dict: Identifier to whether that foundation held.
    """
    return dict(_BASE_OUTCOMES)

def _run_provenance(config: pytest.Config) -> Provenance:
    """Return what this execution would stamp on a carried record.

    **The refs come from the environment**, because a commit is a property of
    the checkout rather than of the invocation, and CI is where they exist. A
    local run leaves them empty, which still matches another local run of the
    same tree.

    Args:
        config (pytest.Config): The active configuration.

    Returns:
        Provenance: The fields a later band is matched against.
    """
    return Provenance(
        rule_set_hash=str(getattr(config, "mqc_rule_set_hash", "") or ""),
        code_ref=os.environ.get("MQC_CODE_REF", ""),
        case_ref=os.environ.get("MQC_CASE_REF", ""),
        engine=str(config.getoption("--engine", "") or ""),
        mode=str(config.getoption("--mode", "") or ""),
        platform=platform.system(),
        band=str(config.getoption("--priority", "") or "all"),
    )

def adopt_prerequisites(config: pytest.Config) -> None:
    """Read base outcomes an earlier band published, if a file was named.

    Args:
        config (pytest.Config): The active configuration, read for
            ``--carry-outcomes``.

    Returns:
        None

    Raises:
        ValueError: With ``QC_HARNESS_PREREQUISITE_MISMATCH`` when the record
            was not produced by this run. Refused rather than ignored, because
            both fallbacks are worse than stopping: re-running the
            prerequisites is the waste this avoids, and assuming they held is
            an assertion nobody measured (design section 7.6.1).
    """
    named = str(config.getoption("--carry-outcomes", "") or "")
    if not named:
        return
    carried = read_outcomes(Path(named), _run_provenance(config))
    adopt_carried_outcomes(carried.outcomes)

def publish_prerequisites(config: pytest.Config) -> None:
    """Write what this execution established, for the next band.

    Args:
        config (pytest.Config): The active configuration.

    Returns:
        None
    """
    named = str(config.getoption("--carry-outcomes", "") or "")
    if not named:
        return
    write_outcomes(Path(named), _run_provenance(config), established_outcomes())

def record_base_outcome(item: pytest.Item, passed: bool) -> None:
    """Record whether a foundational case held.

    **A foundation that did not run did not hold.** A base case skipped during
    setup, because its own dependency failed, produces no measurement, so its
    dependents must skip rather than error. Recording only the call phase left
    a chain reporting an unmet dependency as a hard error two links down.

    Args:
        item (pytest.Item): The test that ran.
        passed (bool): Whether it passed. False for a skip, which is the
            distinction a chain depends on.

    Returns:
        None
    """
    if item.get_closest_marker("base") is None:
        return
    identifier = case_identifier(item.name)
    if identifier is None:
        logger.warning(
            "%s is marked base and carries no identifier, so nothing can "
            "depend on it", item.name,
        )
        return
    _BASE_OUTCOMES[identifier] = passed

def record_from_report(item: pytest.Item, report: Any) -> None:
    """Record a foundational outcome from whichever phase reported it.

    **The outcome decides, not the phase**, which is the distinction the
    calling hooks previously got wrong by recording only ``call``.

    A middle link in a chain is both a foundation and a dependent: when its own
    dependency does not hold, :func:`enforce_dependencies` skips it from
    ``pytest_runtest_setup``, and that skip is reported with ``when ==
    "setup"``. Recording only the call phase left **no entry at all** for it, so
    the next link found an unknown identifier and hard-failed, reporting "no
    collected case declares this as base" about a case that was collected and
    marked base (design section 10.28.5).

    Args:
        item (pytest.Item): The test that ran.
        report (Any): The phase report pytest produced.

    Returns:
        None: A ``setup`` skip or error records ``False``, because a case that
        did not reach its call phase is a foundation that did not hold. **Only
        the call phase can record a pass**, since nothing earlier has measured
        anything.
    """
    if report.when == "call":
        record_base_outcome(item, report.passed)
    elif report.when == "setup" and not report.passed:
        record_base_outcome(item, False)

def declared_dependencies(item: pytest.Item) -> list[str]:
    """Return the identifiers a test declares it depends on.

    Args:
        item (pytest.Item): The collected test.

    Returns:
        list[str]: The five-digit identifiers, empty when it declares none.
    """
    declared: list[str] = []
    for marker in item.iter_markers(name="depends_on"):
        declared.extend(str(argument) for argument in marker.args)
    return declared

def declared_bases(items: list[pytest.Item]) -> dict[str, list[pytest.Item]]:
    """Return the collected foundational cases, by identifier.

    Args:
        items (list): The collected test items.

    Returns:
        dict[str, list]: Identifier to the items declaring it. **A list rather
        than one item**, because a parametrized foundation is several items
        under one identifier and every one of them has to hold.
    """
    bases: dict[str, list[pytest.Item]] = {}
    for item in items:
        if item.get_closest_marker("base") is None:
            continue
        identifier = case_identifier(item.name)
        if identifier is None:
            logger.warning(
                "%s is marked base and carries no identifier, so nothing can "
                "depend on it", item.name,
            )
            continue
        bases.setdefault(identifier, []).append(item)
    return bases

def unknown_dependencies(items: list[pytest.Item]) -> list[str]:
    """Return every dependency naming an identifier nothing declares as base.

    **Asked at collection because that is where it has an answer.** At setup an
    absent identifier means either that nothing declares it or that its base
    has not run yet, and those are unrelated situations that reached one branch
    (design section 10.28.6).

    Args:
        items (list): The collected test items.

    Returns:
        list[str]: One message per offender, in collection order, empty when
        every dependency resolves.
    """
    bases = declared_bases(items)
    # A CARRIED FOUNDATION IS A KNOWN ONE. An earlier band in this job ran
    # it and published whether it held, so a dependent here is resolvable
    # without collecting it again (design section 7.6).
    known = set(bases) | set(_CARRIED)
    return [
        f"{item.name} depends on {identifier}, which no collected case "
        f"declares as base"
        for item in items
        for identifier in declared_dependencies(item)
        if identifier not in known
    ]

def order_by_dependency(items: list[pytest.Item]) -> list[pytest.Item]:
    """Return the items with every foundation ahead of its dependents.

    **A depth-first post-order walk**, which is a topological sort that
    preserves the incoming order wherever it does not have to change it.
    Randomisation is a feature of this suite, so the cascade takes exactly as
    much order as it needs and independent cases stay shuffled.

    Args:
        items (list): The collected test items, in whatever order collection
            and ``pytest-randomly`` produced.

    Returns:
        list[pytest.Item]: The same items, reordered.

    Raises:
        ValueError: With ``QC_HARNESS_DEPENDENCY_UNMET`` naming a cycle. **Two
            cases each declaring the other foundational is a design error in
            the cases**, and silently picking one to run first would let it
            survive.
    """
    bases = declared_bases(items)
    ordered: list[pytest.Item] = []
    settled: set[int] = set()

    def visit(item: pytest.Item, walking: list[pytest.Item]) -> None:
        """Emit one item after everything it depends on.

        Args:
            item (pytest.Item): The item to place.
            walking (list): The current path, for cycle reporting.

        Returns:
            None

        Raises:
            ValueError: When the path revisits an item.
        """
        if id(item) in settled:
            return
        if any(id(seen) == id(item) for seen in walking):
            names = " -> ".join(seen.name for seen in walking + [item])
            raise ValueError(
                f"QC_HARNESS_DEPENDENCY_UNMET: foundational cases form a "
                f"cycle, so no order satisfies them: {names}"
            )
        walking.append(item)
        for identifier in declared_dependencies(item):
            for foundation in bases.get(identifier, ()):
                visit(foundation, walking)
        walking.pop()
        settled.add(id(item))
        ordered.append(item)

    for item in items:
        visit(item, [])
    return ordered

def dependency_closure(chosen: list[pytest.Item], items: list[pytest.Item]) -> set[str]:
    """Return every identifier the chosen items rest on, transitively.

    Args:
        chosen (list): The items the band selected.
        items (list): Everything collected, to resolve bases against.

    Returns:
        set[str]: The identifiers needed as foundations.
    """
    by_identifier = declared_bases(items)
    needed: set[str] = set()
    frontier = list(chosen)
    while frontier:
        current = frontier.pop()
        for identifier in declared_dependencies(current):
            if identifier in needed:
                continue
            needed.add(identifier)
            frontier.extend(by_identifier.get(identifier, []))
    return needed

def inverted_priority_dependencies(items: list[pytest.Item]) -> list[str]:
    """Return every dependency resting on a less blocking foundation.

    **Dependencies run with the priority ordering, never against it.** A case
    may depend only on cases at least as blocking as itself, so a P0 may rest on
    a P0, a P1 on a P0 or a P1, and so on. The numbers move the other way from
    the severity, so the test is that the foundation's number is no larger.

    **Why it is an error rather than a preference.** A P0 failure fails the run;
    a P1 failure answers to the pass floor and may be tolerated. A P0 resting on
    a P1 therefore claims a guarantee its own foundation does not carry. It also
    makes the band sequence unsatisfiable: the corpus that produced this check
    had band 0 resting on band 1 and band 1 resting on band 0, so no ordering
    resolved.

    Args:
        items (list): The collected test items.

    Returns:
        list[str]: One message per inverted edge, empty when the cascade runs
        with the priority ordering.
    """
    ranked: dict[str, int] = {}
    for item in items:
        identifier = case_identifier(item.name)
        level = item_priority(item)
        if identifier is not None and level is not None:
            ranked[identifier] = level

    inverted: list[str] = []
    for item in items:
        dependent = item_priority(item)
        if dependent is None:
            continue
        for identifier in declared_dependencies(item):
            foundation = ranked.get(identifier)
            if foundation is not None and foundation > dependent:
                inverted.append(
                    f"{item.name} is P{dependent} and depends on {identifier}, "
                    f"which is P{foundation}: a foundation cannot be less "
                    f"blocking than what rests on it"
                )
    return inverted

def arrange_dependencies(items: list[pytest.Item]) -> None:
    """Reorder the collected items in place, refusing an unresolvable suite.

    Args:
        items (list): The collected test items, replaced in place because that
            is the contract ``pytest_collection_modifyitems`` has with pytest.

    Returns:
        None

    Raises:
        ValueError: With ``QC_HARNESS_DEPENDENCY_UNMET`` when a dependency
            names no collected base, or when the declarations form a cycle.
            **Reported once, naming every offender**, rather than erroring per
            dependent at setup.
    """
    inverted = inverted_priority_dependencies(items)
    if inverted:
        # REFUSED BEFORE THE UNKNOWN CHECK, because an inverted edge makes
        # the band ordering unsatisfiable and reports as a cycle between
        # bands, which sends a reader looking for the wrong thing.
        raise ValueError(
            "QC_DATA_INVARIANT_VIOLATION: a foundation is less blocking "
            "than what rests on it; " + "; ".join(inverted)
        )
    unknown = unknown_dependencies(items)
    if unknown:
        raise ValueError(
            "QC_HARNESS_DEPENDENCY_UNMET: a dependency on a case that does "
            "not exist is satisfied by nothing existing to fail; "
            + "; ".join(unknown)
        )
    items[:] = order_by_dependency(items)

def probes_dependents(item: pytest.Item) -> bool:
    """Report whether this run measures a dependent of a failed foundation.

    **Replay probes and live skips** (design section 10.28.2.1). The dependent
    may carry its own defect rather than a second report of the foundation's,
    and nothing can tell which without running it; replay runs it free, and a
    live run would spend quota on what the next replay gives away.

    Args:
        item (pytest.Item): The test about to run, for its invocation.

    Returns:
        bool: True in replay mode. **False where the mode is unset**, so a
        caller that never configured one is treated as spending.
    """
    # AN ITEM WITHOUT A CONFIG HAS NO MODE, which is the unset case the
    # docstring names: treated as spending, so a caller that configured
    # nothing never probes.
    config = getattr(item, "config", None)
    if config is None:
        return False
    return str(config.getoption("--mode", "") or "") == "replay"

def enforce_dependencies(item: pytest.Item) -> None:
    """Skip or probe a test whose foundation did not hold.

    **Skipped, never failed.** A dependent that did not run produced no
    measurement, and recording a failure would assert something about a model
    nobody asked. The reason is ``dependency``, which the verdict already
    excludes from the skip denominator so one foundational failure does not
    also breach the skip ceiling.

    **In replay it is probed rather than skipped**: executed, recorded, and
    counted in no denominator, because its failure may be its own and fixing
    the foundation would not fix it (design section 10.28.2.1). The marker is
    left on the item for the reporting hook, which is what keeps the result
    out of every aggregate.

    Args:
        item (pytest.Item): The test about to run.

    Returns:
        None

    **Only the outcome is decided here.** Whether the identifier exists at all
    is a question about the collected population, which `arrange_dependencies`
    answers at collection where the population is known.
    """
    for identifier in declared_dependencies(item):
        # ABSENT MEANS DID NOT RUN, WHICH IS DID NOT HOLD. The other reading,
        # that nothing declares this identifier, is settled at collection by
        # `arrange_dependencies`, which also orders every base ahead of its
        # dependents. Asking here could not tell the two apart, and reported
        # an ordering accident as a missing case (design section 10.28.6).
        if _BASE_OUTCOMES.get(identifier, False):
            continue
        if probes_dependents(item):
            # MEASURED, AND COUNTED NOWHERE. The marker tells the reporting
            # hook to record this as `probe`, which the outcome registry
            # declares false in all four denominators, so one behaviour
            # cannot be reported twice.
            item.add_marker(pytest.mark.probe(identifier))
            logger.info(
                "%s %s did not hold, so %s is probed and counted in no "
                "denominator",
                _UNMET, identifier, item.name,
            )
            continue
        logger.warning(
            "%s %s did not hold, so %s was not executed",
            _UNMET, identifier, item.name,
        )
        pytest.skip(f"{_UNMET}: foundational case {identifier} did not hold")
