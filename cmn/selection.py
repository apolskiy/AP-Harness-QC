# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Choosing which cases a run executes, and refusing a choice that selects none.

Specified by ``docs/design/cmn_verdict_and_cli.md`` sections 7.7 and 7.8.

**Split from ``pytest_support.py`` on 2026-10-03**, when the selection flags
took that module past the thousand-line ceiling. Selection is its own concern:
it reads flags, resolves them against a matrix or a list of names, and leaves
the collection holding what the caller asked for.

**Every path that would select nothing raises instead.** A selector's failure
mode is silence: a misspelled family resolves to nothing, runs nothing and
exits zero, which no artifact can tell from a passing run. The one exception is
an unresolvable entry in a ``--tests-file`` list, which is reported as a
skipped row so that one typo costs that entry and not the run.
"""

import logging
import re
from pathlib import Path
from typing import Any, Final

import pytest

from cmn.registries import UNMET_DEPENDENCY
from cmn.pytest_support import (
    case_identifier,
    case_module,
    item_priority,
    registered_priority_levels,
)
from cmn.dependencies import (
    carried_identifiers,
    dependency_closure,
)
from cmn.traceability import (
    cases_for_index_values,
    load_case_index,
    cases_for_families,
    cases_for_requirements,
    load_matrix_rows,
)

logger = logging.getLogger(__name__)

_UNMET: Final[str] = UNMET_DEPENDENCY

# WHAT A --tests-file ENTRY MAY CONTAIN. A test identifier is digits and a test
# callable's name is word characters, so anything else is a format error:
# punctuation in a line means a pasted list, a sentence, or a pytest nodeid,
# and none of the three is a name this resolves. Design section 7.8.1.1.
_ENTRY_CHARACTERS: Final[re.Pattern] = re.compile(r"^[A-Za-z0-9_]+$")

def _restrict_items(
    config: pytest.Config,
    items: list[pytest.Item],
    chosen: list[pytest.Item],
    described: str,
    keep_preconditions: bool = True,
    detail: str = "",
) -> int:
    """Keep the chosen cases and their foundations, deselecting the rest.

    **Extracted 2026-10-03 from ``select_priority_bands``**, when a second
    selector needed the same rules. Two copies of "which foundations does this
    selection need" would eventually disagree, and the disagreement would
    surface as a dependency naming no collected base: true, and
    indistinguishable from a corpus defect.

    **A precondition is never deselected.** It carries no priority and it is
    what establishes the corpus is loadable at all, so a selection dropping it
    would measure against an unchecked corpus.

    Args:
        config (pytest.Config): pytest's configuration, read for
            ``--with-prerequisites``.
        items (list): The collected items, filtered in place.
        chosen (list): The graded items the selection asked for.
        described (str): What the selection was, for the messages.
        detail (str): Where the excluded foundations sit, appended to the
            refusal. A band names the other bands, because an earlier band
            carries its outcome and that decides which remedy applies.
        keep_preconditions (bool): Whether a case carrying no priority survives
            the selection. **True for a band and False for a named list**, and
            the asymmetry is deliberate: a band measures graded cases and needs
            the corpus guards that establish the corpus is loadable, while a
            named list is the caller saying what to run. Keeping them would
            make a named list a no-op in this repository, where every case is a
            precondition. Design section 7.8.2.

    Returns:
        int: How many foundations were kept beyond the chosen set.

    Raises:
        ValueError: With ``QC_HARNESS_UNMET_PREREQUISITE`` when a chosen case
            rests on a foundation the selection excludes and
            ``--with-prerequisites`` was not given. Letting it drop would reach
            ``arrange_dependencies`` instead, which cannot say which of the two
            remedies applies.
    """
    carry = bool(config.getoption("--with-prerequisites", False))
    needed = dependency_closure(chosen, items)
    picked = set(chosen)

    # IDENTIFIED THE WAY `declared_bases` DOES rather than by substring: two
    # conventions for what a case is called would eventually disagree about
    # which foundations a selection needs, and `134205` is a substring of
    # `130015`.
    outside = {
        item for item in items
        if item not in picked
        and item_priority(item) is not None
        and case_identifier(item.name) in needed
        and case_identifier(item.name) not in carried_identifiers()
    }

    if outside and not carry:
        raise ValueError(
            f"{_UNMET}: {described} rests on foundations "
            f"{detail + ' ' if detail else ''}this selection does not include. "
            f"Run them first so their outcomes carry, or pass "
            f"--with-prerequisites to run them here"
        )

    keep, drop, foundations = [], [], []
    for item in items:
        if item in picked or (keep_preconditions and item_priority(item) is None):
            keep.append(item)
        elif item in outside:
            foundations.append(item)
            keep.append(item)
        else:
            drop.append(item)

    if drop:
        config.hook.pytest_deselected(items=drop)
        items[:] = keep
    return len(foundations)


def _comma_separated(raw: str) -> list[str]:
    """Return a comma-separated flag value as its non-empty entries.

    Args:
        raw (str): The raw value.

    Returns:
        list[str]: The entries, stripped, in the order given.
    """
    return [entry.strip() for entry in (raw or "").split(",") if entry.strip()]


def _resolve_traced(
    config: pytest.Config,
    families: list[str],
    requirements: list[str],
    tags: list[str],
) -> list[set[str]]:
    """Return one case set per dimension the caller named.

    **A family and a tag resolve through the per-case index and a requirement
    through the matrix.** The index is exact; the matrix is keyed by
    requirement, so resolving a family through it returns the whole row.

    Design: ``cmn_verdict_and_cli.md`` section 7.7.6.

    Args:
        config (pytest.Config): pytest's configuration.
        families (list[str]): The families asked for.
        requirements (list[str]): The requirements asked for.
        tags (list[str]): The tags asked for.

    Returns:
        list[set[str]]: One set of case names per dimension, for the caller to
        intersect.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when a dimension has no
            source to resolve through.
    """
    indexed = str(config.getoption("--case-index", "") or "")
    index = load_case_index(Path(indexed)) if indexed else {}

    # A TAG LIVES ONLY ON A CASE, so there is no row-grain fallback: the matrix
    # carries no tag column and none would fit a requirement-keyed schema.
    if tags and not index:
        raise ValueError(
            "QC_HARNESS_PARSER_ERROR: --tag resolves through the per-case index "
            "and no --case-index was given. A tag lives on a task, so there is "
            "nowhere else for it to resolve"
        )

    resolved: list[set[str]] = []
    if tags:
        resolved.append(set().union(
            *cases_for_index_values(index, tags, attribute="tags").values()
        ))
    if families and index:
        # EXACT. Through the matrix this returned the whole requirement row:
        # `source_fidelity` selected 15 cases of which 6 graded it.
        resolved.append(set().union(
            *cases_for_index_values(index, families, attribute="families").values()
        ))
    elif families:
        logger.warning(
            "--family resolved through the matrix at row grain because no "
            "--case-index was given, so the selection may include cases "
            "grading another family of the same requirement"
        )

    if not requirements and not (families and not index):
        return resolved

    named = str(config.getoption("--rtm", "") or "")
    if not named:
        asked = "--requirement" if requirements else "--family"
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: {asked} resolves through a traceability "
            f"matrix and no --rtm was given. This repository owns no case "
            f"matrix, so there is no default to fall back to"
        )
    rows = load_matrix_rows(Path(named))
    if families and not index:
        resolved.append(set().union(*cases_for_families(rows, families).values()))
    if requirements:
        resolved.append(
            set().union(*cases_for_requirements(rows, requirements).values())
        )
    return resolved


def select_traced_cases(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Deselect every graded case outside the requested families or requirements.

    **The selection a fix wants re-run.** A model fix maps to a behaviour, not
    to a module or a file, and the two registers naming behaviour are the
    evaluation family and the requirement.

    **A family and a tag resolve through the per-case index named by
    ``--case-index``, and a requirement through the matrix named by
    ``--rtm``.** Both are supplied by the caller, because this repository owns
    neither. Without an index a family falls back to the matrix at row grain
    and says so, and a tag refuses: a tag lives on a task and has nowhere else
    to resolve. Section 7.7.6.4.

    **Several values in one flag are a union and the two flags intersect**, so
    ``--family a,b`` is every case addressing either and adding
    ``--requirement r`` narrows that to the cases also covering ``r``.

    Design: ``cmn_verdict_and_cli.md`` section 7.7.

    Args:
        config (pytest.Config): pytest's configuration, read for ``--family``,
            ``--requirement``, ``--tag``, ``--rtm`` and ``--case-index``.
        items (list): The collected items, filtered in place.

    Returns:
        None

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when a selector is given
            without ``--rtm``, or when the resolution matches no collected
            case. **A selector's failure mode is silence**: a misspelled family
            resolves to nothing, runs nothing and exits zero, which no artifact
            can tell from a passing run. Section 7.7.3.
    """
    families = _comma_separated(str(config.getoption("--family", "") or ""))
    requirements = _comma_separated(str(config.getoption("--requirement", "") or ""))
    tags = _comma_separated(str(config.getoption("--tag", "") or ""))
    if not families and not requirements and not tags:
        return

    resolved = _resolve_traced(config, families, requirements, tags)

    # INTERSECTED ACROSS DIMENSIONS, united within one. Asking for a family and
    # a requirement asks for the cases that are both.
    wanted = set.intersection(*resolved) if len(resolved) > 1 else resolved[0]
    identifiers = {
        found for found in (case_identifier(name) for name in wanted)
        if found is not None
    }
    chosen = [
        item for item in items
        if item_priority(item) is not None
        and case_identifier(item.name) in identifiers
    ]

    described = ", ".join(
        part for part in (
            f"families {','.join(families)}" if families else "",
            f"requirements {','.join(requirements)}" if requirements else "",
            f"tags {','.join(tags)}" if tags else "",
        ) if part
    )
    if not chosen:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: {described} resolved to "
            f"{len(identifiers)} traced case(s) and none of them is collected, "
            f"so this run would measure nothing and report green"
        )

    foundations = _restrict_items(config, items, chosen, described)
    logger.info(
        "%s selected %d graded case(s), keeping %d foundation(s)",
        described, len(chosen), foundations,
    )



class _UnresolvedSelection(pytest.Item):
    """A reported placeholder for a named test the suite does not contain.

    **A nonexistent test cannot be skipped, because there is nothing to skip.**
    So the skip is given something to attach to: a collected item carrying the
    entry's own name, which skips with its reason and reaches JUnit and Allure
    as a row a reader can see. A warning would land in a log nobody opens for a
    run nobody doubts.

    Design: ``cmn_verdict_and_cli.md`` section 7.8.3.
    """

    def runtest(self) -> None:
        """Skip, naming the entry that resolved to nothing.

        Returns:
            None

        Raises:
            Skipped: Always. An unresolvable selection entry is a harness
                event, and ``framework-rules.md`` section 4 admits those as
                skip or broken, never as fail.
        """
        pytest.skip(
            f"QC_HARNESS_SELECTION_UNRESOLVED: test not found, {self.name!r} "
            f"matched no collected test"
        )

    def reportinfo(self) -> tuple[Any, int, str]:
        """Return where the report line points.

        Returns:
            tuple: The path, the line, and what to show.
        """
        return self.path, 0, f"unresolved selection entry {self.name!r}"

def _requested_entries(inline: str, named_file: str) -> tuple[list[str], bool]:
    """Return the entries a run asked for, from whichever flag supplied them.

    **The two flags take different separators, each natural to its medium.** A
    command line has no newlines, so ``--tests`` is comma separated.
    ``--tests-file`` takes **one entry per line**, so a thousand tests are a
    thousand lines: the line count is the test count, and a diff shows one line
    per change.

    A comma inside a file line is refused rather than split. Accepting it would
    cost the property the format exists for, and treating the line as one entry
    would report a missing test for a name that was never one.

    **Every other punctuation mark is refused too.** A test identifier is
    digits and a test callable's name is word characters, so a period, an
    exclamation mark, a semicolon or a colon in a line means a pasted list, a
    sentence or a pytest nodeid. None resolves to a case, and each would
    otherwise be reported as a test that was not found, which says the wrong
    thing: the entry is malformed rather than missing.

    Design: ``cmn_verdict_and_cli.md`` section 7.8.1.

    Args:
        inline (str): The ``--tests`` value.
        named_file (str): The ``--tests-file`` value.

    Returns:
        tuple: The entries, in the order given with blank lines and ``#``
        comments dropped, and whether they came from a file. **The source
        decides what an unresolvable entry costs**: a hand-typed list is short
        and was typed seconds ago, while a curated file is long and one typo in
        it must not void the rest. Section 7.8.3.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when both flags are given,
            when the named file is absent, when nothing yields an entry, or
            when a file line carries a comma or any other punctuation. A
            malformed line is refused where a missing test is skipped, because
            the two say different things and take different corrections.
    """
    if inline and named_file:
        raise ValueError(
            "QC_HARNESS_PARSER_ERROR: --tests and --tests-file were both "
            "given, and they disagree about what an unresolvable entry costs. "
            "Name one source"
        )

    from_file = bool(named_file)
    if from_file:
        source = Path(named_file)
        if not source.is_file():
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: --tests-file names {source} and it "
                f"does not exist, so the selection would run nothing"
            )
        raw = source.read_text(encoding="utf-8")
    else:
        raw = inline

    entries: list[str] = []
    for number, line in enumerate(raw.splitlines(), start=1):
        without_comment = line.split("#", 1)[0].strip()
        if not without_comment:
            continue
        if from_file:
            if "," in without_comment:
                raise ValueError(
                    f"QC_HARNESS_PARSER_ERROR: --tests-file line {number} "
                    f"carries a comma. A file takes one entry per line, so "
                    f"the line count is the test count"
                )
            if _ENTRY_CHARACTERS.match(without_comment) is None:
                offending = sorted({
                    character for character in without_comment
                    if not (character.isalnum() or character == "_")
                })
                raise ValueError(
                    f"QC_HARNESS_PARSER_ERROR: --tests-file line {number} "
                    f"carries {' '.join(repr(found) for found in offending)}, "
                    f"which a test identifier or name cannot contain. One "
                    f"identifier or one test name per line"
                )
            entries.append(without_comment)
        else:
            entries.extend(
                part.strip() for part in without_comment.split(",") if part.strip()
            )

    if not entries:
        raise ValueError(
            "QC_HARNESS_PARSER_ERROR: the named test selection yielded no "
            "entries, so it would run nothing and report green"
        )
    return entries, from_file


def _entry_identifiers(entries: list[str]) -> dict[str, str]:
    """Return each entry's case identifier, keyed by identifier.

    **Both spellings reduce to the same handle.** An entry is a bare number or
    a full test callable name, and the number is what resolution uses: a
    behaviour suffix changes when the behaviour is reworded, and a list that
    broke on a rename is one nobody maintains.

    Design: ``cmn_verdict_and_cli.md`` section 7.8.1.

    Args:
        entries (list[str]): The entries a run named.

    Returns:
        dict[str, str]: Identifier to the entry that named it, so a message can
        quote what the caller wrote rather than what it resolved to.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when an entry carries no
            identifier at all. That is distinguished from an entry naming a
            test the suite lacks, because the two take different corrections.
    """
    wanted: dict[str, str] = {}
    unresolvable: list[str] = []
    for entry in entries:
        found = entry if entry.isdigit() else case_identifier(entry)
        if found is None:
            unresolvable.append(entry)
        else:
            wanted[found] = entry

    if unresolvable:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: --tests names {', '.join(unresolvable)}, "
            f"which carry no case identifier. Name a case by its number or by "
            f"its full test name"
        )
    return wanted


def select_named_tests(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Run exactly the tests a caller named, and refuse a stale list.

    **For debugging the harness and case expansions across branches**, where
    work reaches ``main`` only through a stabilization branch and the list under
    stabilization is the unit a reviewer re-runs.

    **Resolved by identifier, never by substring.** ``134205`` is a substring of
    ``130015``, so a substring match silently selects a case nobody asked for,
    and the identifier is the only stable handle in the suite.

    **A named entry matching no collected test refuses, naming the entries.**
    That is the failure a branch workflow invites: a list written against one
    branch, re-run against another where a test was renamed or has not landed,
    selects fewer tests than it names and reports green on the subset. The
    caller's next action is editing the list, so a count would not say which
    line to change.

    Design: ``cmn_verdict_and_cli.md`` section 7.8.

    Args:
        config (pytest.Config): pytest's configuration, read for ``--tests``
            and ``--tests-file``.
        items (list): The collected items, filtered in place.

    Returns:
        None

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when an entry carries no
            resolvable identifier, or names no collected test.
    """
    inline = str(config.getoption("--tests", "") or "")
    named_file = str(config.getoption("--tests-file", "") or "")
    if not inline and not named_file:
        return

    entries, from_file = _requested_entries(inline, named_file)
    wanted = _entry_identifiers(entries)
    collected = {
        found for found in (case_identifier(item.name) for item in items)
        if found is not None
    }
    absent = sorted(
        entry for number, entry in wanted.items() if number not in collected
    )
    if absent and not from_file:
        # A HAND-TYPED LIST REFUSES. It is short, it was typed seconds ago and
        # nothing has run, so stopping is the cheapest correction.
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: --tests names {len(absent)} entry(ies) "
            f"matching no collected test: {', '.join(absent)}. Use --tests-file "
            f"to have them reported as skips instead. A list written "
            f"against another branch selects fewer tests than it names and "
            f"reports green on the subset"
        )
    for number in [key for key, entry in wanted.items() if entry in absent]:
        del wanted[number]

    chosen = [item for item in items if case_identifier(item.name) in wanted]
    if not chosen:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: the named selection resolved no "
            f"collected test from "
            f"{len(entries)} entry(ies), so this run would measure nothing and "
            f"report green"
        )

    described = f"{len(wanted)} named case(s)"
    foundations = _restrict_items(
        config, items, chosen, described, keep_preconditions=False
    )

    # EVERY UNRESOLVED ENTRY IS RECORDED, so a caller holding the config can
    # report what was not found without re-reading the file.
    config.unresolved_selection = tuple(absent)
    if absent:
        logger.warning(
            "QC_HARNESS_SELECTION_UNRESOLVED: %d --tests-file entry(ies) "
            "matched no "
            "collected test and are reported as skipped: %s",
            len(absent), ", ".join(absent),
        )
    logger.info(
        "%s selected %d case(s), keeping %d foundation(s)",
        described, len(chosen), foundations,
    )


def report_unresolved_selection(
    session: pytest.Session, items: list[pytest.Item]
) -> None:
    """Append a reported skip for every ``--tests`` entry that resolved to
    nothing.

    **Separate from the selection so the decision stays testable.** Building a
    node needs a real pytest session, which a unit double cannot supply, so
    what was not found is recorded on the configuration and this turns that
    record into rows.

    Design: ``cmn_verdict_and_cli.md`` section 7.8.3.

    Args:
        session (pytest.Session): The session the placeholders hang from.
        items (list): The collected items, appended to in place.

    Returns:
        None
    """
    for entry in getattr(session.config, "unresolved_selection", ()) or ():
        items.append(_UnresolvedSelection.from_parent(session, name=entry))


def selected_bands(raw: str) -> frozenset[int]:
    """Return the priority bands a run asked for.

    Args:
        raw (str): The comma-separated value of ``--priority``, empty for all.

    Returns:
        frozenset[int]: The bands, empty when none was named.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when a band is not 0 to 4.
            **Refused rather than ignored**, because a typo that silently
            selected everything would report a full run as a band.
    """
    if not raw or not raw.strip():
        return frozenset()
    bands: set[int] = set()
    for piece in raw.split(","):
        text = piece.strip()
        if not text:
            continue
        if not text.isdigit() or int(text) not in registered_priority_levels():
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: priority band {text!r} is not 0 to 4"
            )
        bands.add(int(text))
    return frozenset(bands)


def select_priority_bands(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Deselect every graded case outside the requested bands.

    **Preconditions are never deselected.** They carry no priority and they are
    what establishes that the corpus is loadable at all, so a band run that
    dropped them would measure against an unchecked corpus.

    **A band takes its foundations only when asked.** Inside the CI sequence
    the earlier band has already run them, so carrying them here would re-run
    work reported minutes ago and, where one failed, would colour this band
    with a failure belonging to another. `--with-prerequisites` is therefore
    explicit: inferring it would let a misconfigured job silently become a
    standalone run that passes having re-established its own premises.

    **Without it, a band needing an absent foundation refuses**, naming both
    remedies. Letting the foundation drop would surface as a dependency naming
    no collected base, which is true and indistinguishable from a corpus
    defect.

    Args:
        config (pytest.Config): pytest's configuration, read for ``--priority``.
        items (list): The collected items, filtered in place.

    Returns:
        None
    """
    carry = bool(config.getoption("--with-prerequisites", False))
    bands = selected_bands(str(config.getoption("--priority") or ""))
    if not bands:
        # THE FLAG ACTS ONLY THROUGH `--priority`, AND SAYS SO. pytest applies
        # `-k` before this hook, so the foundations are already gone and no
        # closure computed here can bring them back. Proceeding silently cost
        # two live recording runs that dispatched nothing and reported a skip
        # indistinguishable from a corpus defect. Design section 7.5.2.
        if carry and str(config.getoption("keyword", "") or ""):
            raise ValueError(
                "QC_HARNESS_PARSER_ERROR: --with-prerequisites selects "
                "foundations through --priority, and -k has already "
                "deselected them before collection reaches here. Name the "
                "band with --priority, or drop -k"
            )
        if carry:
            logger.warning(
                "--with-prerequisites has nothing to do: no --priority was "
                "given, so every case is collected and no foundation is absent"
            )
        return

    graded = sum(1 for item in items if item_priority(item) is not None)
    chosen = [item for item in items if item_priority(item) in bands]
    named = ",".join(str(band) for band in sorted(bands))

    # THE OTHER BANDS A FOUNDATION SITS IN, which the remedy depends on: an
    # earlier band carries its outcome, so naming the band is what tells a
    # reader which of the two remedies applies.
    elsewhere = sorted({
        str(item_priority(item)) for item in items
        if item_priority(item) not in (None, *bands)
        and case_identifier(item.name) in dependency_closure(chosen, items)
        and case_identifier(item.name) not in carried_identifiers()
    })
    foundations = _restrict_items(
        config, items, chosen, f"band {named}",
        detail=f"in band {','.join(elsewhere)}" if elsewhere else "",
    )

    # THE BAND IS WHAT WAS CHOSEN, not what survived. A foundation kept for the
    # band is graded and out of band, so reporting the kept set as the band
    # would overstate what this run measured.
    logger.info(
        "priority bands %s selected %d graded case(s) of %d, keeping %d foundation(s)",
        named, len(chosen), graded, foundations,
    )


# THE MODULES A CASE MAY BELONG TO, from `framework-rules.md` section 2 plus the
# consumer's own. A closed set, so a typo is refused rather than selecting
# nothing: `--module CNM` would otherwise run no case and report green.
_MODULES: Final[frozenset[str]] = frozenset({"ING", "EXE", "EVL", "CMN", "CAS"})


def select_modules(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Deselect every case outside the named modules.

    **The only selector needing no source but the collected suite.** A case
    identifier carries its module token, so nothing has to be resolved through
    a matrix or a corpus.

    Design: ``cmn_verdict_and_cli.md`` section 7.7.5.

    Args:
        config (pytest.Config): pytest's configuration, read for ``--module``.
        items (list): The collected items, filtered in place.

    Returns:
        None

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when a named module is
            outside the registered set, or when the selection matches no
            collected case. Either would otherwise run nothing and report
            green.
    """
    named = [
        entry.upper()
        for entry in _comma_separated(str(config.getoption("--module", "") or ""))
    ]
    if not named:
        return

    unknown = sorted(set(named) - _MODULES)
    if unknown:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: --module names {', '.join(unknown)}, "
            f"which is not a registered module; registered modules are "
            f"{', '.join(sorted(_MODULES))}"
        )

    wanted = set(named)
    chosen = [item for item in items if case_module(item.name) in wanted]
    if not chosen:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: no collected case belongs to "
            f"{', '.join(sorted(wanted))}, so this run would measure nothing "
            f"and report green"
        )

    # PRECONDITIONS ARE NOT KEPT, because a module selection is over every
    # case rather than over the graded ones: keeping them would make the flag a
    # no-op in this repository, as it would for a named list (section 7.8.2).
    foundations = _restrict_items(
        config, items, chosen, f"modules {','.join(sorted(wanted))}",
        keep_preconditions=False,
    )
    logger.info(
        "modules %s selected %d case(s), keeping %d foundation(s)",
        ",".join(sorted(wanted)), len(chosen), foundations,
    )
