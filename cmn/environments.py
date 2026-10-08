# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Which environment a case needs, and what happens where it is absent.

Specified in ``docs/design/harness_test_taxonomy.md`` section 7.5.1.

**A skip is an outcome and this is not one.** "This case could not have run
here" is a statement about the selection, so a case whose scope the environment
does not satisfy is deselected before it runs rather than skipped: it leaves the
run's total instead of putting a non-outcome in it.

**This repository names no consumer.** A scope needing a sibling checkout takes
the directory name from the case that declares it, so the name stays in the test
that already knew it and nothing here depends on a consumer existing.
"""

import logging
import os
from pathlib import Path
from typing import Any, Final, Optional

import pytest

from cmn.config import ci_markers

logger = logging.getLogger(__name__)

# THE REGISTERED SCOPES, pinned like every other registry so that adding one is
# deliberate: a new scope is a new way for a precondition to leave a run, which
# is the thing section 7.5.1 exists to control.
_ENVIRONMENT_SCOPES: Final[frozenset[str]] = frozenset({"local", "paired"})

_MARKER: Final[str] = "environment"


def registered_environment_scopes() -> frozenset[str]:
    """Return every registered environment scope.

    Returns:
        frozenset[str]: ``local`` for a developer's machine and ``paired`` for a
        sibling checkout, which are counted differently by nothing: a case is
        either this run's to measure or it is not.
    """
    return _ENVIRONMENT_SCOPES


def under_ci() -> bool:
    """Report whether this process is running on a CI runner.

    Returns:
        bool: True when any recognised runner variable is set. **The names come
        from the credential loader's own registry**, so a case scoped to a
        developer's machine and the loader that is inert on a runner cannot
        disagree about what a runner is.
    """
    return any(marker in os.environ for marker in ci_markers())


def scope_available(scope: str, sibling: str = "", root: Optional[Path] = None) -> bool:
    """Report whether one declared scope is satisfied here.

    Args:
        scope (str): A registered scope.
        sibling (str): For ``paired``, the sibling directory the case needs,
            named by the case rather than by this module.
        root (Optional[Path]): The repository root, defaulting to this file's.

    Returns:
        bool: True when a case declaring the scope may run here.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the scope is not
            registered. Treating an unknown scope as available would run a case
            somewhere it declared it could not, and treating it as absent would
            drop a case on a typo; both are silent.
    """
    if scope not in _ENVIRONMENT_SCOPES:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: environment scope {scope!r} is not "
            f"registered; one of {', '.join(sorted(_ENVIRONMENT_SCOPES))}"
        )
    if scope == "local":
        return not under_ci()
    base = (root or Path(__file__).resolve().parents[1]).parent
    return bool(sibling) and (base / sibling).is_dir()


def declared_scopes(item: Any) -> list[tuple[str, str]]:
    """Return every environment scope one case declares.

    Args:
        item (Any): The collected test.

    Returns:
        list: Each scope with the sibling it names, empty where the case
        declares none.
    """
    declared: list[tuple[str, str]] = []
    for marker in item.iter_markers(name=_MARKER):
        sibling = str(marker.kwargs.get("sibling", "") or "")
        declared.extend((str(scope), sibling) for scope in marker.args)
    return declared


def unavailable_here(item: Any, root: Optional[Path] = None) -> str:
    """Return the first declared scope this environment does not satisfy.

    Args:
        item (Any): The collected test.
        root (Optional[Path]): The repository root.

    Returns:
        str: The scope name, or an empty string where every declared scope is
        satisfied. **A case declaring none is always available**, which keeps
        the mechanism opt-in.
    """
    for scope, sibling in declared_scopes(item):
        if not scope_available(scope, sibling, root):
            return scope
    return ""


def deselect_unavailable_environments(
    config: Any, items: list[Any], root: Optional[Path] = None
) -> int:
    """Deselect every case whose declared scope this environment lacks.

    **Deselected, not skipped**, which is the whole of section 7.5.1: a case
    taken out of the selection leaves the run's total, and a skipped one reports
    a non-outcome inside it.

    Args:
        config (Any): The pytest configuration, for the deselection hook.
        items (list): The collected items, modified in place.
        root (Optional[Path]): The repository root.

    Returns:
        int: How many were deselected.
    """
    keep, drop = [], []
    reasons: dict[str, int] = {}
    for item in items:
        absent = unavailable_here(item, root)
        if absent:
            drop.append(item)
            reasons[absent] = reasons.get(absent, 0) + 1
        else:
            keep.append(item)
    if not drop:
        return 0
    config.hook.pytest_deselected(items=drop)
    items[:] = keep
    for scope, count in sorted(reasons.items()):
        logger.info(
            "%d case(s) deselected: this environment is not %s", count, scope
        )
    return len(drop)


def refuse_precondition_skips(session: Any) -> int:
    """Fail the run where an ungraded precondition skipped.

    **Zero skips, enforced rather than stated.** A precondition measures our
    harness and every one is unconditionally blocking, so a skipped one measured
    nothing and there is no acceptable proportion of that. A harness unit job
    reported green at 99.44% with four skips before this existed.

    Design: ``harness_test_taxonomy.md`` section 7.5.1.

    Args:
        session (Any): The finishing session, whose exit status is raised.

    Returns:
        int: How many precondition skips were found. **Zero leaves the exit
        status alone**, so this adds a failure and never removes one.
    """
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return 0
    offenders = [
        report for report in reporter.stats.get("skipped", [])
        if is_precondition(getattr(report, "nodeid", ""))
    ]
    if not offenders:
        return 0
    for report in offenders:
        logger.error(
            "QC_HARNESS_PRECONDITION_SKIPPED %s skipped, and a precondition "
            "that did not run measured nothing",
            getattr(report, "nodeid", "?"),
        )
    logger.error(
        "%d precondition(s) skipped, so the run exits 3: a precondition needing "
        "something this environment lacks declares an environment scope and is "
        "deselected instead",
        len(offenders),
    )
    session.exitstatus = _PRECONDITION_EXIT
    return len(offenders)


# EXIT 3 IS ALREADY "NOTHING TRUSTWORTHY WAS MEASURED", which is exactly what an
# unmeasured precondition leaves behind. A new code would need a reader to learn
# one more thing to reach the same remedy.
_PRECONDITION_EXIT: Final[int] = 3

# THE TWO UNGRADED LAYERS, read from the node identifier because a skip reported
# from collection or setup carries no marker a hook can read.
_PRECONDITION_LAYERS: Final[tuple[str, ...]] = ("_UNI_", "_SYS_")


def is_precondition(nodeid: str) -> bool:
    """Report whether a node identifier names an ungraded precondition.

    **Read from the identifier rather than from a marker**, because a skip
    reported from collection or setup carries no marker a hook can read.

    Args:
        nodeid (str): The pytest node identifier.

    Returns:
        bool: True when the callable's layer token is ungraded.
    """
    return any(layer in nodeid for layer in _PRECONDITION_LAYERS)


def environment_marker() -> str:
    """Return the marker name a case declares its scope with.

    Returns:
        str: ``environment``, so ``pytest.ini`` and the checks read one value.
    """
    return _MARKER


def mark_environment(*scopes: str, sibling: str = "") -> Any:
    """Return the marker a case applies to declare its environment scope.

    Args:
        *scopes: The registered scopes the case needs.
        sibling (str): For ``paired``, the sibling directory, named here by the
            case so this repository names no consumer.

    Returns:
        Any: The pytest marker.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when a scope is not
            registered, refused at import rather than at collection so a typo
            cannot silently drop a case.
    """
    for scope in scopes:
        if scope not in _ENVIRONMENT_SCOPES:
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: environment scope {scope!r} is not "
                f"registered; one of {', '.join(sorted(_ENVIRONMENT_SCOPES))}"
            )
    return pytest.mark.environment(*scopes, sibling=sibling)
