# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""RTM integrity: every declared thing verified, every verification traced.

Specified by ``docs/design/cmn_verdict_and_cli.md`` section 6.

**Two directions, structurally identical to Tier 1's R2 and R3 one level up.**
A requirement with no test is a coverage gap; a test claiming a requirement that
has no row is untracked coverage. Checking one direction only would leave the
matrix looking complete while half the relation went unverified.

**The matrices are loaded through Tier 1's CSV loader**, so their columns are a
schema like any other: a blank cell takes the declared default, an unknown
column is rejected, and no value is type-inferred. They are validated data
rather than documents someone maintains.

**`families` is derived, never authored.** It is the distinct families of the
cases named in the same row, so it cannot disagree with the inventory. A
hand-maintained copy would be a second statement of one fact.
"""

import csv
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Iterable, Optional

logger = logging.getLogger(__name__)

_LIST_DELIMITER: Final[str] = ";"

# The columns both matrices share, plus the one only the model matrix carries.
# Families apply to graded cases only: a precondition tests the harness, which
# performs no task, so the column would be empty in every harness row and an
# always-empty column teaches a reader to ignore a column.
_SHARED_COLUMNS: Final[tuple[str, ...]] = (
    "requirement_id", "requirement_text", "source", "category", "test_ids", "notes",
)
_MODEL_ONLY_COLUMNS: Final[tuple[str, ...]] = ("families",)


@dataclass(frozen=True)
class TraceabilityFinding:
    """One integrity breach, naming the check and what it found.

    Attributes:
        check (str): ``T1`` through ``T6``.
        subject (str): The requirement or test the finding concerns.
        detail (str): What was wrong, stated so a reader needs no other
            context.
        gap_type (str): Whether the matrix is stale or coverage is missing.
    """

    check: str
    subject: str
    detail: str
    gap_type: str


@dataclass(frozen=True)
class MatrixRow:
    """One row of a traceability matrix.

    Attributes:
        requirement_id (str): ``MQC_HAR_*`` or ``MQC_MDL_*``.
        requirement_text (str): The requirement as the plan states it.
        source (str): Provenance, so a self-authored requirement stays
            distinguishable from an inherited one.
        category (str): Where the requirement comes from.
        test_ids (list): The covering tests.
        families (list): Derived from the cases named in ``test_ids``. Empty on
            a harness row, where the column is absent rather than blank.
        notes (str): Why the row reads as it does.
    """

    requirement_id: str
    requirement_text: str
    source: str
    category: str
    test_ids: list[str] = field(default_factory=list)
    families: list[str] = field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "MatrixRow":
        """Build a row from a loaded CSV record.

        Args:
            row (dict): The raw record.

        Returns:
            MatrixRow: The built record.

        Raises:
            ValueError: With ``QC_HARNESS_PARSER_ERROR`` for an unknown column.
                A column nobody declared would be silently ignored, and a
                matrix carrying data nothing reads is worse than one missing it.
        """
        permitted = set(_SHARED_COLUMNS) | set(_MODEL_ONLY_COLUMNS)
        unknown = sorted(set(row) - permitted)
        if unknown:
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: matrix row {row.get('requirement_id')!r} "
                f"carries unknown columns {', '.join(unknown)}"
            )
        return cls(
            requirement_id=str(row["requirement_id"]).strip(),
            requirement_text=str(row.get("requirement_text", "")).strip(),
            source=str(row.get("source", "")).strip(),
            category=str(row.get("category", "")).strip(),
            test_ids=_split(row.get("test_ids", "")),
            families=_split(row.get("families", "")),
            notes=str(row.get("notes", "")).strip(),
        )



def _check_t6(rows: list[MatrixRow]) -> list[TraceabilityFinding]:
    """T6: every requirement identifier is declared exactly once.

    **T1 reads the declared requirements as a set**, so a duplicate is
    invisible to it: the second row either restates the first or silently
    replaces what it meant, and the matrix goes on looking complete.

    The failure it produces surfaces somewhere else entirely. A script adding a
    row guarded itself with "if the identifier is present, this is done", the
    identifier belonged to an unrelated requirement, and the row was dropped;
    the visible symptom was a case traced nowhere, two hundred rows away.

    Args:
        rows (list): The loaded matrix rows.

    Returns:
        list[TraceabilityFinding]: One finding per duplicated identifier, in
        first-seen order so the report is reproducible.
    """
    seen: set[str] = set()
    duplicated: list[str] = []
    for row in rows:
        if row.requirement_id in seen and row.requirement_id not in duplicated:
            duplicated.append(row.requirement_id)
        seen.add(row.requirement_id)

    return [
        TraceabilityFinding(
            check="T6", subject=requirement,
            detail=(
                f"{requirement} is declared on more than one row, so the "
                f"second silently replaces what the first one meant"
            ),
            gap_type="traceability",
        )
        for requirement in duplicated
    ]


def _split(value: Optional[str]) -> list[str]:
    """Split a semicolon-delimited cell, dropping empties.

    Args:
        value (Optional[str]): The raw cell.

    Returns:
        list[str]: The entries. **A blank cell yields an empty list**, which
        takes the declared default rather than becoming a one-element list
        containing nothing.
    """
    if not value:
        return []
    return [entry.strip() for entry in str(value).split(_LIST_DELIMITER) if entry.strip()]



# Four zero-padded digits, per harness_test_plan.md section 2. The width is
# fixed in advance rather than grown on demand, because the cost of a narrow
# register is not widening it but the mixed state widening produces.
_REGISTER_DIGITS: Final[int] = 4

# The fraction of a register's range that triggers a warning. A ceiling that
# goes from silent to blocking is repaired by whatever is quickest, and here
# the quickest repair is the mixed width the fixed width exists to prevent.
_PRESSURE_FRACTION: Final[float] = 0.8

_REQUIREMENT_ID = re.compile(r"^(MQC_(?:HAR|CAS|MDL)_[A-Z]+)_(\d+)$")


def register_ceiling() -> int:
    """Return the highest number a requirement register can hold.

    Returns:
        int: The ceiling implied by the fixed identifier width.
    """
    return 10 ** _REGISTER_DIGITS - 1


def highest_assigned(requirement_ids: Optional[Iterable[str]] = None) -> dict[str, int]:
    """Return the highest number each register has consumed.

    **Consumed, not counted.** Identifiers are assigned in loose groups and a
    retired one stays retired, so a register holding 25 requirements can have
    consumed 53 numbers. Counting would report half the pressure that exists.

    Args:
        requirement_ids (Optional[Iterable[str]]): The identifiers to measure.
            Defaults to none, which yields an empty reading rather than
            reaching for a file: this module computes and never loads.

    Returns:
        dict[str, int]: Register prefix to its high-water mark.
    """
    highest: dict[str, int] = {}
    for identifier in requirement_ids or ():
        matched = _REQUIREMENT_ID.match(str(identifier).strip())
        if matched is None:
            continue
        register, number = matched.group(1), int(matched.group(2))
        highest[register] = max(highest.get(register, 0), number)
    return highest


def register_pressure(highest: dict[str, int]) -> list[str]:
    """Report every register that has consumed most of its range.

    Args:
        highest (dict): Register prefix to its high-water mark, as
            :func:`highest_assigned` returns.

    Returns:
        list[str]: One entry per register over the threshold, sorted so the
        report is reproducible. Empty when every register has room.
    """
    ceiling = register_ceiling()
    threshold = int(ceiling * _PRESSURE_FRACTION)
    return [
        f"{register} has consumed {mark} of {ceiling}, past the "
        f"{int(_PRESSURE_FRACTION * 100)} percent mark. Widen the identifier "
        f"before a mixed-width register becomes the quickest repair"
        for register, mark in sorted(highest.items())
        if mark > threshold
    ]


def check_matrix_integrity(
    rows: list[MatrixRow],
    declared_requirements: set[str],
    suite_tests: set[str],
    test_requirements: Optional[dict[str, list[str]]] = None,
    case_families: Optional[dict[str, str]] = None,
) -> list[TraceabilityFinding]:
    """Run every integrity check and collect all findings.

    **Every check runs, and every finding is collected.** Stopping at the first
    would mean fixing one stale reference and discovering the next on the
    following run, which for a matrix touched rarely means several cycles to
    reach a clean state.

    Args:
        rows (list): The loaded matrix rows.
        declared_requirements (set): Every requirement the plan declares.
        suite_tests (set): Every test the suite actually collects.
        test_requirements (Optional[dict]): Test name to the requirements it
            claims, for T4.
        case_families (Optional[dict]): Test name to its evaluation family, for
            T5.

    Returns:
        list[TraceabilityFinding]: Every breach found, in check order.
    """
    findings: list[TraceabilityFinding] = []
    traced = {row.requirement_id for row in rows}

    findings.extend(_check_t1(declared_requirements, traced))
    findings.extend(_check_t2(rows))
    findings.extend(_check_t3(rows, suite_tests))
    findings.extend(_check_t4(test_requirements or {}, traced))
    findings.extend(_check_t5(rows, case_families or {}))
    findings.extend(_check_t6(rows))
    return findings



def untraced_tests(
    rows: list[MatrixRow], suite_tests: set[str]
) -> list[TraceabilityFinding]:
    """T7: every test the suite collects is named in some matrix row.

    **The reverse of T3, and not a restatement of T4.** T3 reports a row naming
    a test that does not exist; this reports a test that exists and no row
    names. T4 reads the requirements a test declares for itself, so a test
    declaring none satisfies it by declaring none, which is the self-consistency
    problem one level down.

    **Called separately from :func:`check_matrix_integrity`**, because it is
    only meaningful against the complete collected suite: given a partial set it
    reports every test the caller omitted. Design section 6.0.1 carries it.

    Args:
        rows (list): The loaded matrix rows.
        suite_tests (set): **Every** test the suite collects, not a subset.

    Returns:
        list[TraceabilityFinding]: One per collected test no row names.
    """
    named = {test_id for row in rows for test_id in row.test_ids}
    return [
        TraceabilityFinding(
            check="T7", subject=test_id,
            detail=(
                "the suite collects this test and no matrix row names it, so the "
                "requirement it satisfies is unrecorded"
            ),
            gap_type="untraced coverage",
        )
        for test_id in sorted(suite_tests - named)
    ]


def _check_t1(declared: set[str], traced: set[str]) -> list[TraceabilityFinding]:
    """T1: every declared requirement has a matrix row.

    Args:
        declared (set): Requirements the plan declares.
        traced (set): Requirements the matrix carries.

    Returns:
        list[TraceabilityFinding]: One per untraced requirement.
    """
    return [
        TraceabilityFinding(
            check="T1", subject=requirement,
            detail="the plan declares this requirement and the matrix has no row for it",
            gap_type="traceability",
        )
        for requirement in sorted(declared - traced)
    ]


def _check_t2(rows: list[MatrixRow]) -> list[TraceabilityFinding]:
    """T2: every row names at least one test.

    Args:
        rows (list): The matrix rows.

    Returns:
        list[TraceabilityFinding]: One per uncovered requirement. **This is a
        coverage gap rather than a stale matrix**: the requirement is recorded
        and nothing verifies it, which is the more serious of the two.
    """
    return [
        TraceabilityFinding(
            check="T2", subject=row.requirement_id,
            detail="the matrix names no test for this requirement, so nothing verifies it",
            gap_type="coverage",
        )
        for row in rows if not row.test_ids
    ]


def _check_t3(rows: list[MatrixRow], suite_tests: set[str]) -> list[TraceabilityFinding]:
    """T3: every test named in the matrix exists in the suite.

    Args:
        rows (list): The matrix rows.
        suite_tests (set): Every test the suite collects.

    Returns:
        list[TraceabilityFinding]: One per stale reference. A row naming a
        deleted test reports coverage that no longer runs.
    """
    return [
        TraceabilityFinding(
            check="T3", subject=test_id,
            detail=(
                f"{row.requirement_id} names this test and the suite does not collect it"
            ),
            gap_type="stale reference",
        )
        for row in rows for test_id in row.test_ids if test_id not in suite_tests
    ]


def _check_t4(
    test_requirements: dict[str, list[str]], traced: set[str]
) -> list[TraceabilityFinding]:
    """T4: every test claiming a requirement has a matching row.

    Args:
        test_requirements (dict): Test name to claimed requirements.
        traced (set): Requirements the matrix carries.

    Returns:
        list[TraceabilityFinding]: One per untracked claim. Coverage that
        exists and is not recorded is invisible to every report drawn from the
        matrix.
    """
    return [
        TraceabilityFinding(
            check="T4", subject=test_name,
            detail=f"this test claims {requirement} and the matrix has no such row",
            gap_type="untracked coverage",
        )
        for test_name, claimed in sorted(test_requirements.items())
        for requirement in claimed if requirement not in traced
    ]


def _check_t5(
    rows: list[MatrixRow], case_families: dict[str, str]
) -> list[TraceabilityFinding]:
    """T5: every families value matches the cases named in the same row.

    Args:
        rows (list): The matrix rows.
        case_families (dict): Test name to its evaluation family.

    Returns:
        list[TraceabilityFinding]: One per disagreement. **Families are derived,
        never authored**, so a value disagreeing with the cases it summarises is
        derived data restated wrongly, which is the drift this check exists to
        catch.
    """
    findings: list[TraceabilityFinding] = []
    for row in rows:
        if not row.families:
            continue
        derived = sorted({
            case_families[test_id] for test_id in row.test_ids
            if test_id in case_families
        })
        if derived and sorted(row.families) != derived:
            findings.append(
                TraceabilityFinding(
                    check="T5", subject=row.requirement_id,
                    detail=(
                        f"the row states families {sorted(row.families)} and its cases "
                        f"belong to {derived}"
                    ),
                    gap_type="derived data restated wrongly",
                )
            )
    return findings


def shared_columns() -> tuple[str, ...]:
    """Return the columns both matrices carry.

    Returns:
        tuple[str, ...]: The shared column names.
    """
    return _SHARED_COLUMNS


def model_only_columns() -> tuple[str, ...]:
    """Return the columns only the model matrix carries.

    **The harness file omits the column rather than carrying it blank.** That
    needs no special case: an absent optional column takes its declared
    default, which is the ordinary loader rule.

    Returns:
        tuple[str, ...]: The model-only column names.
    """
    return _MODEL_ONLY_COLUMNS


def load_matrix_rows(path: Path) -> list["MatrixRow"]:
    """Return a traceability matrix at a caller-supplied path.

    **The path is the caller's and absent is not a default.** This repository
    owns no case matrix: ``rtm_harness.csv`` traces preconditions and carries no
    ``families`` column at all, so a default pointing at it would resolve every
    family to nothing. What this repository owns is the matrix **schema**, which
    is why reading one a caller names is within its remit.

    Design: ``cmn_verdict_and_cli.md`` section 7.7.1.

    Args:
        path (Path): The matrix to read.

    Returns:
        list: The loaded rows.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the file is absent. A
            selection resolving through a matrix that is not there would select
            nothing and report green.
    """
    if not path.is_file():
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: no traceability matrix at {path}, so a "
            f"--family or --requirement selection has nothing to resolve through"
        )
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [MatrixRow.from_row(entry) for entry in csv.DictReader(handle)]


def cases_for_families(
    rows: list["MatrixRow"], wanted: Iterable[str]
) -> dict[str, set[str]]:
    """Return the cases addressing each named family.

    **Inclusive of a secondary family.** A case where the family is secondary
    still exercises it, so omitting it from a regression set risks missing the
    regression the re-run exists to find. Primacy serves attribution rather
    than selection, which ``harness_test_taxonomy.md`` section 11.7.2 records as a
    correction to an earlier claim.

    Design: ``cmn_verdict_and_cli.md`` section 7.7.2.

    Args:
        rows (list): The matrix rows.
        wanted (Iterable[str]): The family identifiers asked for.

    Returns:
        dict[str, set[str]]: Each family to the case identifiers covering it.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when a named family
            appears in no row. **The matrix is what is checked, not the
            registry**: a family may be registered and carried by no case yet,
            and selecting it would run nothing while reporting green.
    """
    found: dict[str, set[str]] = {name: set() for name in wanted}
    for row in rows:
        declared = set(row.families)
        for name in found:
            if name in declared:
                found[name].update(row.test_ids)

    empty = sorted(name for name, cases in found.items() if not cases)
    if empty:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: no matrix row names "
            f"{', '.join(empty)}, so the selection would run nothing and "
            f"report green"
        )
    return found


def cases_for_requirements(
    rows: list["MatrixRow"], wanted: Iterable[str]
) -> dict[str, set[str]]:
    """Return the cases covering each named requirement.

    Design: ``cmn_verdict_and_cli.md`` section 7.7.1.

    Args:
        rows (list): The matrix rows.
        wanted (Iterable[str]): The requirement identifiers asked for.

    Returns:
        dict[str, set[str]]: Each requirement to the case identifiers covering
        it.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when a named requirement
            has no row, or has one naming no case. The second is the coverage
            gap T1 reports, and a run must not proceed on it.
    """
    by_requirement = {row.requirement_id: set(row.test_ids) for row in rows}
    found: dict[str, set[str]] = {}
    unknown: list[str] = []
    uncovered: list[str] = []
    for name in wanted:
        if name not in by_requirement:
            unknown.append(name)
        elif not by_requirement[name]:
            uncovered.append(name)
        else:
            found[name] = set(by_requirement[name])

    if unknown:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: the matrix has no row for "
            f"{', '.join(sorted(unknown))}, so the selection would run nothing "
            f"and report green"
        )
    if uncovered:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: {', '.join(sorted(uncovered))} is traced "
            f"to no case, which is a coverage gap rather than a selection"
        )
    return found


# ONE ROW PER CASE, which is the grain a selector needs. The matrix is keyed by
# requirement and names every case covering it, so resolving a family through
# it selects the whole row: `--family source_fidelity` returned 15 cases of
# which 6 graded it. Design `cmn_verdict_and_cli.md` section 7.7.6.
_INDEX_COLUMNS: Final[tuple[str, ...]] = ("case", "families", "tags")


@dataclass(frozen=True)
class CaseIndexEntry:
    """What one case grades and how it is tagged.

    Attributes:
        case (str): The test callable's name.
        families (tuple): Its evaluation families, primary first.
        tags (tuple): Its task's tags.
    """

    case: str
    families: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


def load_case_index(path: Path) -> dict[str, CaseIndexEntry]:
    """Return the generated per-case index, keyed by case.

    **Generated by the consumer from its corpus**, never authored: an index of
    69 cases maintained by hand drifts from the first corpus edit, which is the
    same argument that makes the matrix families column derived.

    Args:
        path (Path): The index to read.

    Returns:
        dict[str, CaseIndexEntry]: Case name to its entry.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the file is absent,
            carries the wrong columns, or yields no row. An empty index would
            make every selection through it refuse for the wrong reason.
    """
    if not path.is_file():
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: no case index at {path}, so a --tag "
            f"selection has nowhere to resolve and --family would fall back to "
            f"the matrix at row grain"
        )
    with path.open(encoding="utf-8-sig", newline="") as handle:
        # THE SPDX HEADER IS MANDATORY AND IS NOT DATA. `code-style.md` section
        # 1.2 requires every tracked file to carry it, and `csv.DictReader`
        # would take the first comment line as the header row.
        reader = csv.DictReader(
            line for line in handle if not line.lstrip().startswith("#")
        )
        missing = sorted(set(_INDEX_COLUMNS) - set(reader.fieldnames or ()))
        if missing:
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: the case index at {path} carries no "
                f"{', '.join(missing)} column"
            )
        entries = {
            str(row["case"]).strip(): CaseIndexEntry(
                case=str(row["case"]).strip(),
                families=tuple(_split(row.get("families", ""))),
                tags=tuple(_split(row.get("tags", ""))),
            )
            for row in reader if str(row.get("case", "")).strip()
        }

    if not entries:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: the case index at {path} names no case, "
            f"so every selection through it would refuse for the wrong reason"
        )
    return entries


def cases_for_index_values(
    index: dict[str, CaseIndexEntry], wanted: Iterable[str], *, attribute: str
) -> dict[str, set[str]]:
    """Return the cases carrying each named family or tag, exactly.

    **The index is also the vocabulary.** A value no case carries is refused
    rather than resolving to nothing, which is what lets `--tag contrl` fail
    instead of running nothing and reporting green.

    Args:
        index (dict): The loaded index.
        wanted (Iterable[str]): The values asked for.
        attribute (str): ``families`` or ``tags``.

    Returns:
        dict[str, set[str]]: Each value to the cases carrying it.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when a named value appears
            on no case.
    """
    found: dict[str, set[str]] = {name: set() for name in wanted}
    for entry in index.values():
        carried = set(getattr(entry, attribute))
        for name in found:
            if name in carried:
                found[name].add(entry.case)

    empty = sorted(name for name, cases in found.items() if not cases)
    if empty:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: no case carries the "
            f"{'family' if attribute == 'families' else 'tag'} "
            f"{', '.join(empty)}, so the selection would run nothing and "
            f"report green"
        )
    return found
