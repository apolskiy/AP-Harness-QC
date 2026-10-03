# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""What a branch may be called, how long it may live, and where it may merge.

Specified by ``docs/design/ci_pipeline.md`` section 3C.6.

**Every function here is pure.** A branch name, a base, a date and a set of
merge records go in; problems come out. Nothing reads git, nothing reads a
clock, and nothing reaches an issue tracker, so the whole policy is checkable
offline against synthetic input and a rule cannot change its answer between two
runs of one commit.

**One implementation, two repositories**, which is the parity mechanism
``consumer_ci.md`` section 5 states in full. The only per-repository input is
the set of case identifiers a referent may name, which differs because the
inventories differ. That is one rule over two inventories, not two rules.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Final, Optional

# The master branch. It is cut from nothing, merged into nothing, and exempt
# from the naming grammar because it is not a working branch.
MAIN: Final[str] = "main"

# The kind that integrates. Everything reaches MAIN through one of these, so a
# second route into MAIN is a route around the integration test.
INTEGRATION_KIND: Final[str] = "stabilization"

BRANCH_KINDS: Final[frozenset[str]] = frozenset(
    {"expand", "extend", INTEGRATION_KIND, "debug"}
)

# THE REFERENT REGISTRY. Adding a kind is a row, in the sense
# testing-standards.md uses for layer tokens. A date says when and a referent
# says what, and a branch listing of six dates is a listing of six unknowns.
#
# A TICKET IS CHECKED FOR SHAPE AND NEVER FOR EXISTENCE. Reaching an issue
# tracker from here would put a network call in the one layer required to run
# without one, and would fail the gate when somebody else's service is down.
REFERENT_KINDS: Final[dict[str, re.Pattern[str]]] = {
    "ticket": re.compile(r"^[A-Z][A-Z0-9]*-\d+$"),
    "case": re.compile(r"^\d{6}$"),
    "release": re.compile(r"^v\d+\.\d+\.\d+$"),
}

# THE REFERENT COMES FIRST BECAUSE IT IS THE KEY. Several branches are cut on
# one day and none of them is distinguished by that, so sorting by date groups
# unrelated work and separates related work. The stamp anchors the end, which
# is what lets the referent hold hyphens of its own.
#
# THE STAMP IS MM-DD-YYYY, AND THE MONTH LEADS ON PURPOSE. Staleness is
# measured in weeks, so the month is the digit that answers the question, and
# putting it first makes a stale branch visible in a branch listing without
# reading any date in full. Under DD-MM-YYYY the leading digits are the day,
# which is noise for the one thing the stamp exists to signal.
#
# THIS IS NOT ISO 8601 AND MUST NOT BE CORRECTED INTO IT. The stamp does not
# sort lexically, which is deliberate: sorting by date groups unrelated work,
# and the referent is what a listing should sort by.
#
# The cost is that MM-DD is read as DD-MM in most of the world. The parser
# therefore accepts exactly this order, so a transposed stamp is reported
# rather than silently accepted as a different date.
# THE REFERENT IS OPTIONAL IN THE GRAMMAR AND REQUIRED BY THE KIND. Making it
# optional here and enforcing it in name_problems is what lets the message say
# which kind omitted it, instead of reporting an unparseable name.
_BRANCH = re.compile(
    r"^(?P<kind>[a-z]+)(-(?P<referent>\S+))?-(?P<stamp>\d{2}-\d{2}-\d{4})$"
)

# The referent kind recorded for an integration branch that names its cycle.
# It is not absent, it is the date, which is the identity of the cycle.
CYCLE_REFERENT: Final[str] = "cycle"

# Staleness bands, in days since the branch was cut from MAIN.
WARN_AFTER_DAYS: Final[int] = 14
STALE_AFTER_DAYS: Final[int] = 30

_NAME_CODE: Final[str] = "QC_HARNESS_BRANCH_NAME"
_STALE_CODE: Final[str] = "QC_HARNESS_BRANCH_STALE"
_ROUTE_CODE: Final[str] = "QC_HARNESS_BRANCH_ROUTE"


@dataclass(frozen=True)
class Branch:
    """One parsed working branch.

    Attributes:
        kind (str): ``expand``, ``extend``, ``stabilization`` or ``debug``.
        cut_on (date): The day it was cut from ``main``.
        referent (Optional[str]): What the work is, ``None`` for an
            integration branch naming its cycle with the stamp alone.
        referent_kind (str): Which registered kind the referent matched, or
            ``cycle`` where the stamp is the identity.
    """

    kind: str
    cut_on: date
    referent: Optional[str]
    referent_kind: str


def parse_branch(name: str) -> Optional[Branch]:
    """Return the parsed branch, or ``None`` when the name does not conform.

    Args:
        name (str): The branch name.

    Returns:
        Optional[Branch]: The parse, or ``None``. **``main`` returns ``None``
        too**, because it is not a working branch; callers ask
        :func:`name_problems` whether that is a fault.
    """
    matched = _BRANCH.match(name)
    if matched is None:
        return None
    if matched.group("kind") not in BRANCH_KINDS:
        return None
    cut_on = _read_stamp(matched.group("stamp"))
    if cut_on is None:
        return None
    branch_kind = matched.group("kind")
    resolved = _resolve_referent(branch_kind, matched.group("referent"))
    if resolved is None:
        return None
    referent, referent_kind = resolved
    return Branch(branch_kind, cut_on, referent, referent_kind)


def _resolve_referent(
    branch_kind: str, referent: Optional[str]
) -> Optional[tuple[Optional[str], str]]:
    """Return the referent and its kind, or ``None`` when it resolves to none.

    Args:
        branch_kind (str): Which kind of branch carries it.
        referent (Optional[str]): The referent text, absent for a bare stamp.

    Returns:
        Optional[tuple]: The referent and its registered kind. **A bare stamp
        resolves for the integration kind only**: doing several things is what
        that branch is for, so any single referent would assert something false
        about the rest. ci_pipeline.md section 3C.6.1.
    """
    if referent is None:
        if branch_kind != INTEGRATION_KIND:
            return None
        return None, CYCLE_REFERENT
    for kind, pattern in REFERENT_KINDS.items():
        if pattern.match(referent):
            return referent, kind
    return None



def _read_stamp(stamp: str) -> Optional[date]:
    """Return the date a stamp names, or ``None`` when it names none.

    Args:
        stamp (str): The stamp, in ``MM-DD-YYYY`` order.

    Returns:
        Optional[date]: The parsed date. **A transposed day and month is
        rejected rather than reinterpreted**, because ``13-01-2026`` read as a
        date at all would be read as a different one than its author meant, and
        a stamp that quietly means something else is worse than one that fails.
    """
    month, day, year = stamp.split("-")
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def name_problems(name: str) -> list[str]:
    """Report every way a branch name departs from the grammar.

    Args:
        name (str): The branch name.

    Returns:
        list[str]: One entry per problem, empty when the name conforms.
        ``main`` is exempt and yields nothing.
    """
    if name == MAIN:
        return []

    matched = _BRANCH.match(name)
    if matched is None:
        return [
            f"{_NAME_CODE}: {name!r} is not <kind>-<referent>-<MM-DD-YYYY>; "
            f"kinds are {sorted(BRANCH_KINDS)}"
        ]

    problems: list[str] = []
    kind = matched.group("kind")
    if kind not in BRANCH_KINDS:
        problems.append(
            f"{_NAME_CODE}: {name!r} has kind {kind!r}, and the kinds are "
            f"{sorted(BRANCH_KINDS)}"
        )
    if _read_stamp(matched.group("stamp")) is None:
        problems.append(
            f"{_NAME_CODE}: {name!r} carries {matched.group('stamp')!r}, which "
            f"is not an MM-DD-YYYY date"
        )

    referent = matched.group("referent")
    if referent is None:
        # THE ONLY KIND THAT MAY NAME ITS CYCLE. A working branch holds one
        # unit of work and says which; an integration branch holds a cycle and
        # the stamp names it.
        if kind != INTEGRATION_KIND:
            problems.append(
                f"{_NAME_CODE}: {name!r} carries a stamp and no referent, and "
                f"only {INTEGRATION_KIND} may name its cycle that way. A "
                f"working branch holds one unit of work and says which"
            )
        return problems

    if not any(pattern.match(referent) for pattern in REFERENT_KINDS.values()):
        problems.append(
            f"{_NAME_CODE}: referent {referent!r} matches no registered kind; "
            f"kinds are {sorted(REFERENT_KINDS)}"
        )
    return problems


def referent_problems(name: str, known_case_ids: frozenset[str]) -> list[str]:
    """Report a case referent that names no inventoried case.

    **This is the kind that earns its keep.** A branch claiming to fix a case
    that does not exist is a typo, and it is reported on the first push rather
    than at review.

    Args:
        name (str): The branch name.
        known_case_ids (frozenset[str]): Every identifier inventoried in the
            repository the branch belongs to.

    Returns:
        list[str]: One entry when the referent is a case identifier that is not
        inventoried, empty otherwise. A name that does not parse yields
        nothing here, because :func:`name_problems` already reports it and one
        fault should not be counted twice.
    """
    branch = parse_branch(name)
    if branch is None or branch.referent_kind != "case":
        return []
    if branch.referent in known_case_ids:
        return []
    return [
        f"{_NAME_CODE}: {name!r} names case {branch.referent}, which is not "
        f"inventoried in this repository"
    ]


@dataclass(frozen=True)
class Staleness:
    """How far a branch has drifted from the ``main`` it was cut from.

    Attributes:
        days (int): Days since it was cut.
        band (str): ``silent``, ``warn`` or ``stale``.
        blocks (bool): Whether the gate fails on it.
    """

    days: int
    band: str
    blocks: bool


def staleness(name: str, as_of: date) -> Optional[Staleness]:
    """Return how stale a branch is, as of a supplied date.

    **The date is supplied, never read from a clock.** A rule that changes its
    answer between two runs of one commit is not checkable, which is the same
    reason the verdict function takes an injected date.

    Args:
        name (str): The branch name.
        as_of (date): The date to measure against, normally the commit date.

    Returns:
        Optional[Staleness]: The measurement, or ``None`` for ``main`` and for
        a name that does not parse.
    """
    branch = parse_branch(name)
    if branch is None:
        return None
    days = (as_of - branch.cut_on).days
    if days >= STALE_AFTER_DAYS:
        return Staleness(days, "stale", True)
    if days >= WARN_AFTER_DAYS:
        return Staleness(days, "warn", False)
    return Staleness(days, "silent", False)


def staleness_problems(name: str, as_of: date) -> list[str]:
    """Report a branch past the staleness ceiling.

    Args:
        name (str): The branch name.
        as_of (date): The date to measure against.

    Returns:
        list[str]: One entry when the branch blocks, empty otherwise.
    """
    measured = staleness(name, as_of)
    if measured is None or not measured.blocks:
        return []
    return [
        f"{_STALE_CODE}: {name!r} was cut {measured.days} days ago and the "
        f"ceiling is {STALE_AFTER_DAYS}. Succeed it: cut a new branch from "
        f"main dated today, merge this one into it, and continue there"
    ]


def route_problems(head: str, base: str) -> list[str]:
    """Report a merge that does not follow the one route into ``main``.

    Args:
        head (str): The branch merging.
        base (str): The branch merged into.

    Returns:
        list[str]: One entry per problem, empty when the route is permitted.
    """
    if head == MAIN:
        return [
            f"{_ROUTE_CODE}: main is merged into nothing, and this targets "
            f"{base!r}. A branch that has fallen behind is succeeded, not "
            f"caught up"
        ]
    if base != MAIN:
        return []

    branch = parse_branch(head)
    if branch is not None and branch.kind == INTEGRATION_KIND:
        return []
    return [
        f"{_ROUTE_CODE}: {head!r} targets main directly, and everything "
        f"reaches main through a {INTEGRATION_KIND} branch. A second route is "
        f"a route around the integration test"
    ]


@dataclass(frozen=True)
class MergeRecord:
    """One merge commit on a branch, reduced to what the policy reads.

    Attributes:
        sha (str): The merge commit.
        incoming_ref (str): What was merged in, for the message.
        incoming_in_main (bool): Whether ``main`` already contains the incoming
            parent. **This is the whole distinction.** A back-merge brings in
            something main already has; a succession brings in the unmerged
            work that is the reason the branch existed.
    """

    sha: str
    incoming_ref: str
    incoming_in_main: bool


def back_merge_problems(merges: list[MergeRecord]) -> list[str]:
    """Report a merge that brought ``main`` into a branch.

    **Succession passes this without being named as an exception**, because the
    stale branch it merges in is not contained in ``main``. A check that had to
    special-case its own approved remedy would be a check nobody could reason
    about.

    Args:
        merges (list[MergeRecord]): Every merge commit on the branch.

    Returns:
        list[str]: One entry per back-merge, empty when there is none.
    """
    return [
        f"{_ROUTE_CODE}: {record.sha} merged {record.incoming_ref!r} into this "
        f"branch and main already contains it. Main is merged into nothing; "
        f"succeed the branch instead"
        for record in merges
        if record.incoming_in_main
    ]
