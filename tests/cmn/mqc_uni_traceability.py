# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for RTM integrity, in both directions.

Covers `MQC_CMN_UNI_10132` through `10134` and `10185`, inventoried in
``docs/design/cmn_verdict_and_cli.md`` section 10.

**Two directions, structurally identical to Tier 1's R2 and R3 one level up.**
Every declared thing must be verified, and every verification must trace to
something declared. Checking one direction only leaves the matrix looking
complete while half the relation goes unchecked.

**`families` is derived, never authored.** A hand-maintained copy would be a
second statement of one fact, which is the drift this project has already
corrected more than once.

A failure here is our defect, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

import ast
import csv
import re
from pathlib import Path

import pytest

from cmn.traceability import (
    highest_assigned,
    register_ceiling,
    register_pressure,
    MatrixRow,
    check_matrix_integrity,
    model_only_columns,
    shared_columns,
    untraced_tests,
)

pytestmark = pytest.mark.unit

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _row(requirement_id: str, tests: str = "", families: str = "") -> MatrixRow:
    """Build one matrix row.

    Args:
        requirement_id (str): The requirement.
        tests (str): Semicolon-delimited covering tests.
        families (str): Semicolon-delimited families.

    Returns:
        MatrixRow: The built row.
    """
    return MatrixRow.from_row({
        "requirement_id": requirement_id,
        "requirement_text": "a requirement",
        "source": "self-authored",
        "category": "a section",
        "test_ids": tests,
        "families": families,
        "notes": "",
    })


class TestMQCMatrixIntegrity:
    """T1 through T5, each firing on exactly what it is for."""

    def MQC_CMN_UNI_10132_rtm_row_with_no_test_is_a_coverage_gap(self) -> None:
        """A requirement recorded and unverified is the more serious gap.

        A stale matrix misstates what exists; an uncovered requirement means
        the thing itself was never checked, and the matrix reports it rather
        than leaving it to be noticed.

        Returns:
            None
        """
        findings = check_matrix_integrity(
            [
                _row("MQC_REQ_HAR_ING_0001"),
                _row("MQC_REQ_HAR_ING_0002", "MQC_ING_UNI_10001_first_probe"),
            ],
            {"MQC_REQ_HAR_ING_0001", "MQC_REQ_HAR_ING_0002"},
            {"MQC_ING_UNI_10001_first_probe"},
        )
        uncovered = [entry for entry in findings if entry.check == "T2"]

        assert [entry.subject for entry in uncovered] == ["MQC_REQ_HAR_ING_0001"]
        assert uncovered[0].gap_type == "coverage"

    def MQC_CMN_UNI_10133_rtm_naming_absent_test_is_rejected(self) -> None:
        """A row naming a deleted test reports coverage that no longer runs.

        Returns:
            None
        """
        findings = check_matrix_integrity(
            [
                _row("MQC_REQ_HAR_ING_0001", (
                    "MQC_ING_UNI_10001_first_probe;"
                    "MQC_ING_UNI_19999_retired_probe"
                )),
            ],
            {"MQC_REQ_HAR_ING_0001"},
            {"MQC_ING_UNI_10001_first_probe"},
        )
        stale = [entry for entry in findings if entry.check == "T3"]

        assert [entry.subject for entry in stale] == ["MQC_ING_UNI_19999_retired_probe"]
        assert stale[0].gap_type == "stale reference"

    def MQC_CMN_UNI_10134_test_with_requirement_id_absent_from_rtm_is_rejected(self) -> None:
        """Coverage that exists and is unrecorded is invisible to every report.

        Returns:
            None
        """
        findings = check_matrix_integrity(
            [_row("MQC_REQ_HAR_ING_0001", "MQC_ING_UNI_10001_first_probe")],
            {"MQC_REQ_HAR_ING_0001"},
            {"MQC_ING_UNI_10001_first_probe", "MQC_ING_UNI_10002_second_probe"},
            test_requirements={"MQC_ING_UNI_10002_second_probe": ["MQC_REQ_HAR_ING_0099"]},
        )
        untracked = [entry for entry in findings if entry.check == "T4"]

        assert [entry.subject for entry in untracked] == ["MQC_ING_UNI_10002_second_probe"]
        assert "MQC_REQ_HAR_ING_0099" in untracked[0].detail

    def MQC_CMN_UNI_10192_a_declared_requirement_with_no_row_is_reported(self) -> None:
        """T1, the direction the other checks do not cover.

        A requirement the plan declares and the matrix omits leaves the matrix
        looking complete while the requirement goes untraced.

        Returns:
            None
        """
        findings = check_matrix_integrity(
            [_row("MQC_REQ_HAR_ING_0001", "MQC_ING_UNI_10001_first_probe")],
            {"MQC_REQ_HAR_ING_0001", "MQC_REQ_HAR_ING_0002"},
            {"MQC_ING_UNI_10001_first_probe"},
        )
        untraced = [entry for entry in findings if entry.check == "T1"]

        assert [entry.subject for entry in untraced] == ["MQC_REQ_HAR_ING_0002"]
        assert untraced[0].gap_type == "traceability"

    def MQC_CMN_UNI_10185_rtm_families_disagreeing_with_the_inventory_are_reported(self) -> None:
        """Families are derived, so a stated value can only be wrong.

        A row claiming three families whose cases belong to one is derived data
        restated wrongly, and it reports coverage breadth the suite does not
        have.

        Returns:
            None
        """
        findings = check_matrix_integrity(
            [_row("MQC_REQ_MDL_GND_0001", (
                    "MQC_EVL_EVAL_30001_first_graded_probe;"
                    "MQC_EVL_EVAL_30002_second_graded_probe"
                ),
                  families="requirement_match;code_comprehension")],
            {"MQC_REQ_MDL_GND_0001"},
            {"MQC_EVL_EVAL_30001_first_graded_probe", "MQC_EVL_EVAL_30002_second_graded_probe"},
            case_families={
                "MQC_EVL_EVAL_30001_first_graded_probe": "requirement_match",
                "MQC_EVL_EVAL_30002_second_graded_probe": "requirement_match",
            },
        )
        mismatched = [entry for entry in findings if entry.check == "T5"]

        assert [entry.subject for entry in mismatched] == ["MQC_REQ_MDL_GND_0001"]
        assert mismatched[0].gap_type == "derived data restated wrongly"

    def MQC_CMN_UNI_10193_families_agreeing_with_the_inventory_pass(self) -> None:
        """The counterweight: T5 must not fire on a correct row.

        Returns:
            None
        """
        findings = check_matrix_integrity(
            [_row("MQC_REQ_MDL_GND_0001", (
                    "MQC_EVL_EVAL_30001_first_graded_probe;"
                    "MQC_EVL_EVAL_30002_second_graded_probe"
                ),
                  families="code_comprehension;requirement_match")],
            {"MQC_REQ_MDL_GND_0001"},
            {"MQC_EVL_EVAL_30001_first_graded_probe", "MQC_EVL_EVAL_30002_second_graded_probe"},
            case_families={
                "MQC_EVL_EVAL_30001_first_graded_probe": "requirement_match",
                "MQC_EVL_EVAL_30002_second_graded_probe": "code_comprehension",
            },
        )
        assert not [entry for entry in findings if entry.check == "T5"]

    def MQC_CMN_UNI_10194_every_check_runs_rather_than_stopping_at_the_first(self) -> None:
        """A matrix touched rarely should not take several cycles to clean.

        Returns:
            None
        """
        findings = check_matrix_integrity(
            [
                _row("MQC_REQ_HAR_ING_0001"),
                _row("MQC_REQ_HAR_ING_0002", "MQC_ING_UNI_19999_retired_probe"),
            ],
            {"MQC_REQ_HAR_ING_0001", "MQC_REQ_HAR_ING_0002", "MQC_REQ_HAR_ING_0003"},
            set(),
            test_requirements={"MQC_ING_UNI_10005_third_probe": ["MQC_REQ_HAR_ING_0404"]},
        )
        assert {entry.check for entry in findings} == {"T1", "T2", "T3", "T4"}


class TestMQCMatrixSchema:
    """The matrices are validated data, not documents someone maintains."""

    def MQC_CMN_UNI_10195_an_unknown_matrix_column_is_rejected(self) -> None:
        """A column nothing reads is worse than a column that is missing.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR"):
            MatrixRow.from_row({
                "requirement_id": "MQC_REQ_HAR_ING_0001",
                "owner": "somebody",
            })

    def MQC_CMN_UNI_10196_the_harness_matrix_omits_the_families_column(self) -> None:
        """An always-empty column teaches a reader to ignore a column.

        Families apply to graded cases only, and a precondition tests the
        harness, which performs no task. The harness file therefore omits the
        column rather than carrying it blank, which needs no special case: an
        absent optional column takes its declared default.

        Returns:
            None
        """
        harness = _REPOSITORY_ROOT / "docs" / "testing" / "rtm_harness.csv"
        with harness.open(encoding="utf-8-sig", newline="") as handle:
            columns = next(csv.reader(handle))

        assert "families" not in columns
        assert set(columns) <= set(shared_columns())
        assert model_only_columns() == ("families",)

    def MQC_CMN_UNI_10197_the_live_harness_matrix_passes_every_check(self) -> None:
        """T2 against the real matrix: every row names at least one test.

        **This establishes T2 and nothing else, deliberately narrowed.** An
        earlier docstring claimed it ran the real matrix through every check,
        while deriving ``declared`` and ``named`` from that same matrix: T1
        cannot fail against requirements taken from the rows it checks, T3
        cannot fail against names taken from the rows it checks, and T4
        receives the matrix in place of the suite.

        A check whose inputs come from its subject can only confirm the subject
        is self-consistent. `11122` supplies the collected suite, which is the
        only source that is not the matrix.

        Returns:
            None
        """
        harness = _REPOSITORY_ROOT / "docs" / "testing" / "rtm_harness.csv"
        with harness.open(encoding="utf-8-sig", newline="") as handle:
            rows = [MatrixRow.from_row(entry) for entry in csv.DictReader(handle)]

        declared = {row.requirement_id for row in rows}
        named = {test_id for row in rows for test_id in row.test_ids}
        findings = check_matrix_integrity(rows, declared, named)

        assert not [entry for entry in findings if entry.check == "T2"]
        assert len(rows) > 100

    def MQC_CMN_UNI_11202_an_untraced_test_is_reported_against_either_matrix(
        self,
    ) -> None:
        """T7 against synthetic rows, which is the only way to see it fire.

        **The repository-level callers cannot be this case.** `11122` and
        `MQC_CAS_UNI_10460` run T7 against their real matrices, and both are
        green when the matrices are complete, so neither demonstrates that the
        check reports anything. This supplies a suite containing a test no row
        names.

        **And the complement matters as much.** A suite every row names yields
        nothing, because a check that reported on a clean input would be read as
        noise and then ignored.

        Returns:
            None
        """
        rows = [
            _row("MQC_REQ_HAR_EXE_0001", "MQC_EXE_UNI_10001_alpha"),
            _row("MQC_REQ_HAR_EXE_0002", "MQC_EXE_UNI_10002_beta"),
        ]

        clean = untraced_tests(
            rows, {"MQC_EXE_UNI_10001_alpha", "MQC_EXE_UNI_10002_beta"}
        )
        assert not clean, "a fully traced suite reported a gap"

        findings = untraced_tests(
            rows,
            {
                "MQC_EXE_UNI_10001_alpha",
                "MQC_EXE_UNI_10002_beta",
                "MQC_EXE_UNI_10003_gamma",
            },
        )

        assert [entry.subject for entry in findings] == ["MQC_EXE_UNI_10003_gamma"]
        assert findings[0].check == "T7"
        assert findings[0].gap_type == "untraced coverage"

        # NOT THE REVERSE DIRECTION, which is T3's. A row naming a test the
        # suite lacks is a stale reference, and reporting it here as well would
        # make one defect two findings.
        assert not untraced_tests(
            [_row("MQC_REQ_HAR_EXE_0003", "MQC_EXE_UNI_10009_deleted")], set()
        )




def _shipped_requirements() -> set[str]:
    """Return every requirement identifier both repositories declare.

    Returns:
        set[str]: The identifiers, read from the shipped matrices.
    """
    found: set[str] = set()
    for matrix in _matrix_paths():
        with matrix.open(encoding="utf-8-sig", newline="") as handle:
            found.update(
                row["requirement_id"].strip()
                for row in csv.DictReader(handle)
                if row.get("requirement_id")
            )
    return found


def _shipped_cases() -> set[str]:
    """Return every test callable both repositories define.

    Returns:
        set[str]: The identifiers, read from parsed function definitions so a
        name inside a string literal is data rather than a case.
    """
    pattern = re.compile(r"^MQC_[A-Z]+_[A-Z]{3,5}_\d{5}_[a-z0-9_]+$")
    found: set[str] = set()
    for root in _repository_roots():
        for source in (root / "tests").rglob("*.py"):
            try:
                tree = ast.parse(source.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            found.update(
                node.name
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and pattern.match(node.name)
            )
    return found


def _repository_roots() -> list[Path]:
    """Return every repository whose registers take part.

    Returns:
        list[Path]: This repository, plus the case repository when it sits
        beside it. **Absence is not a failure**: a clone of one repository
        alone still checks its own registers, and requiring both would make a
        precondition depend on a checkout nobody promised.
    """
    here = Path(__file__).resolve().parents[2]
    roots = [here]
    sibling = here.parent / "AP-Model-QC"
    if sibling.is_dir() and sibling != here:
        roots.append(sibling)
    return roots


def _matrix_paths() -> list[Path]:
    """Return every traceability matrix that ships.

    Returns:
        list[Path]: The matrices found beside each repository root.
    """
    return [
        matrix
        for root in _repository_roots()
        for matrix in sorted((root / "docs" / "testing").glob("rtm_*.csv"))
    ]


class TestMQCRequirementRegister:
    """The register of requirements, which had no rules of its own."""

    def MQC_CMN_UNI_11158_a_requirement_identifier_declared_twice_is_reported(
        self,
    ) -> None:
        """T1 reads the declared requirements as a set, so it cannot see this.

        A duplicate row either restates the first or **silently replaces what
        it meant**, and the matrix goes on looking complete either way.

        Found by hitting it: a script adding a row guarded itself with "if the
        identifier is present, this is done", the identifier belonged to an
        unrelated requirement, and the row was dropped. The visible symptom was
        a case traced nowhere, two hundred rows away.

        Returns:
            None
        """
        duplicated = [
            MatrixRow(
                requirement_id="MQC_REQ_HAR_CMN_0001",
                requirement_text="probe",
                source="self-authored",
                category="probe",
                test_ids=["MQC_CMN_UNI_10001_first_probe"],
            ),
            MatrixRow(
                requirement_id="MQC_REQ_HAR_CMN_0002",
                requirement_text="probe",
                source="self-authored",
                category="probe",
                test_ids=["MQC_CMN_UNI_10002_second_probe"],
            ),
            MatrixRow(
                requirement_id="MQC_REQ_HAR_CMN_0001",
                requirement_text="probe",
                source="self-authored",
                category="probe",
                test_ids=["MQC_CMN_UNI_10003_third_probe"],
            ),
        ]
        findings = check_matrix_integrity(
            duplicated,
            {"MQC_REQ_HAR_CMN_0001", "MQC_REQ_HAR_CMN_0002"},
            {
                "MQC_CMN_UNI_10001_first_probe",
                "MQC_CMN_UNI_10002_second_probe",
                "MQC_CMN_UNI_10003_third_probe",
            },
        )

        breaches = [entry for entry in findings if entry.check == "T6"]
        assert len(breaches) == 1, f"T6 reported {len(breaches)} findings: {findings}"
        assert breaches[0].subject == "MQC_REQ_HAR_CMN_0001"

        # REPORTED ONCE PER IDENTIFIER, not once per extra row, so three rows
        # sharing a number do not read as two separate problems.
        thrice = duplicated + [
            MatrixRow(
                requirement_id="MQC_REQ_HAR_CMN_0001",
                requirement_text="probe",
                source="self-authored",
                category="probe",
                test_ids=["MQC_CMN_UNI_10004_fourth_probe"],
            )
        ]
        repeated = [
            entry
            for entry in check_matrix_integrity(
                thrice,
                {"MQC_REQ_HAR_CMN_0001", "MQC_REQ_HAR_CMN_0002"},
                {
                    "MQC_CMN_UNI_10001_first_probe", "MQC_CMN_UNI_10002_second_probe",
                    "MQC_CMN_UNI_10003_third_probe", "MQC_CMN_UNI_10004_fourth_probe",
                },
            )
            if entry.check == "T6"
        ]
        assert len(repeated) == 1

        # AND A CLEAN MATRIX REPORTS NOTHING, or the check would fire on every
        # run and be trained away on its second.
        clean = [
            MatrixRow(
                requirement_id="MQC_REQ_HAR_CMN_0001",
                requirement_text="probe",
                source="self-authored",
                category="probe",
                test_ids=["MQC_CMN_UNI_10001_first_probe"],
            ),
            MatrixRow(
                requirement_id="MQC_REQ_HAR_CMN_0002",
                requirement_text="probe",
                source="self-authored",
                category="probe",
                test_ids=["MQC_CMN_UNI_10002_second_probe"],
            ),
        ]
        assert not [
            entry
            for entry in check_matrix_integrity(
                clean,
                {"MQC_REQ_HAR_CMN_0001", "MQC_REQ_HAR_CMN_0002"},
                {"MQC_CMN_UNI_10001_first_probe", "MQC_CMN_UNI_10002_second_probe"},
            )
            if entry.check == "T6"
        ]

    def MQC_CMN_UNI_11159_a_register_at_eighty_percent_of_its_ceiling_is_reported(
        self,
    ) -> None:
        """A ceiling that goes from silent to blocking is repaired badly.

        The quickest repair is adding a digit to new identifiers while the old
        ones keep four, which is **the mixed-width state the fixed width exists
        to prevent**. The warning band makes the deliberate repair the easy
        one, as the branch staleness ceiling does.

        **Named at the threshold exactly**, on both sides, because off by one
        at a boundary is the likeliest defect in any gate.

        Returns:
            None
        """
        ceiling = register_ceiling()
        assert ceiling == 9999, "four zero-padded digits give this range"

        threshold = int(ceiling * 0.8)

        # AT the threshold is not over it.
        assert not register_pressure({"MQC_HAR_CMN": threshold})
        assert register_pressure({"MQC_HAR_CMN": threshold + 1})

        # IT MEASURES THE CONSUMED RANGE, not the count. A register holding 25
        # requirements can have consumed 53 numbers, and counting would report
        # half the pressure that exists.
        sparse = {"MQC_HAR_EXE": threshold + 1}
        reported = register_pressure(sparse)
        assert reported and "MQC_HAR_EXE" in reported[0]

        # THE REAL REGISTERS ARE NOWHERE NEAR IT, which is the point of having
        # widened before it mattered.
        assert not register_pressure(highest_assigned())


    def MQC_CMN_UNI_11160_a_register_token_that_is_also_a_module_code_is_reported(
        self,
    ) -> None:
        """Widths were doing the work, and widths are not a namespace.

        `MQC_CAS_` once prefixed both of this project's registers. The
        requirement spelled **historically** `MQC_CAS_CI_0019`, now
        `MQC_REQ_CAS_CI_0019`, sat beside the case `MQC_CAS_UNI_10428`, and
        the two were told apart only by their third token. Nothing collided,
        because four digits and five never meet. **The hazard was the pattern,
        not the values**: a rename written for one register matched the other,
        and only a late lookahead stopped it clipping 458 case identifiers.

        **The shipped registers are read, not a permitted list.** A hardcoded
        set would pass while the real matrices drifted, which is the failure
        this project keeps correcting.

        Returns:
            None
        """
        requirement_tokens = {
            identifier.split("_")[1] for identifier in _shipped_requirements()
        }
        case_tokens = {
            identifier.split("_")[1] for identifier in _shipped_cases()
        }

        assert requirement_tokens, "no requirement registers were read"
        assert case_tokens, "no case modules were read"

        overlap = sorted(requirement_tokens & case_tokens)
        assert not overlap, (
            f"{overlap} names both a requirement register and a test module, "
            f"so a pattern written for one register matches the other"
        )

        # NOR A LAYER TOKEN, which is the other half of a case identifier and
        # the other way a register could collide.
        layers = {"UNI", "SYS", "EVAL", "TOOL", "SEC"}
        assert not requirement_tokens & layers, (
            f"{sorted(requirement_tokens & layers)} is a layer token"
        )

        # AND NO IDENTIFIER IS BOTH, which is the claim the tokens exist to
        # make structurally true rather than merely true today.
        both = _shipped_requirements() & _shipped_cases()
        assert not both, f"{sorted(both)} is both a requirement and a case"
