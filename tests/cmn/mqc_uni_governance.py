# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions that hold the suite to its own governance.

Covers `MQC_CMN_UNI_112303`, specified in ``docs/design/cmn_verdict_and_cli.md``
section 10.2.

**This module tests the project rather than the product.** Everything else here
asserts that the harness measures a model correctly; this asserts that the
harness was built the way the governance says it must be.

A failure here is **not a model finding**, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

import ast
import csv
import re
from pathlib import Path
from typing import Final, Optional

import pytest

from cmn.config import forbidden_keys
from cmn.layers import layer_properties, registered_layers
from cmn.traceability import MatrixRow, untraced_tests

pytestmark = pytest.mark.unit

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

# AN INVENTORY ROW CARRIES A CATEGORY AND A BEHAVIOUR NAME. A citation in
# ordinary prose carries neither, and harness documents cite consumer case
# numbers freely. Matching any row whose first cell is an identifier counted
# those citations, which is what sent the first version of this check reading
# the sibling checkout. Design section 10.19.2.
_INVENTORY_IDENTIFIER: Final[re.Pattern] = re.compile(
    r"^\|\s*`(\d{6})`\s*\|\s*[PNB]\s*\|\s*`[a-z0-9_]+`"
)

_DESIGN_DIRECTORY = _REPOSITORY_ROOT / "docs" / "design"
_TEST_DIRECTORY = _REPOSITORY_ROOT / "tests"

# A collected test callable, as pytest.ini and .pylintrc both define it.
# A test DEFINITION, not any mention of one. The `def` prefix is load-bearing:
# a test module naming an identifier inside a string literal, as a traceability
# case must in order to exercise a stale reference, is not a test the suite
# collects. Matching the bare pattern reported those literals as undesigned
# tests, which is exactly the over-reporting that trains a check away on its
# second run.
# A TEST CALLABLE'S NAME, matched against a PARSED function definition rather
# than against source text. The `def` prefix is gone from the pattern because
# the parse supplies it: a definition inside a string literal is data, and a
# regex over text cannot tell the two apart. A module embedding a sub-suite as
# a fixture is the case that proved it could not.
_TEST_CALLABLE = re.compile(
    r"^MQC_([A-Z]{3})_([A-Z]{3,5})_(\d{6})_([a-z0-9_]{3,60})$"
)


def _defined_callables(module: Path) -> list[tuple[str, str, str, str]]:
    """Return every test callable a module actually defines.

    **Parsed, not matched.** A string literal carrying ``def MQC_...`` is data,
    and this project has two reasons to embed one: a traceability case
    exercising a stale reference, and a fixture sub-suite run in a subprocess.
    Neither is a test this suite collects.

    Args:
        module (Path): The module to read.

    Returns:
        list[tuple]: Module code, layer, number and behaviour for each
        definition. **A module that will not parse yields nothing here** and
        fails its own collection separately, which keeps one defect from
        being reported as two.
    """
    try:
        tree = ast.parse(module.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    found: list[tuple[str, str, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        matched = _TEST_CALLABLE.match(node.name)
        if matched is not None:
            found.append(matched.groups())
    return found

# An inventory row, as every module design writes one.
_INVENTORY_ROW = re.compile(r"^\|\s*`(\d{6})`\s*\|\s*[PNB]\s*\|")

# A row that also quotes its behaviour name. Rows explaining a case in prose
# carry no name and are not candidates for the comparison below.
_NAMED_ROW = re.compile(r"^\|\s*`(\d{6})`\s*\|\s*[PNB]\s*\|\s*`([a-z0-9_]+)`")

# The behaviour suffix .pylintrc permits on a callable.
_BEHAVIOUR_LIMITS = (3, 60)


# Which module each design document inventories. A row is keyed by module and
# number together, because the five-digit blocks are partitioned per module
# (test_taxonomy.md section 3.2.1) and a bare number would let a case match the
# WRONG module's row. That is worse than no check: it passes for the wrong
# reason, which is how the overlap that prompted this went unnoticed.
_DOCUMENT_MODULES = {
    "tier1_ingestion.md": "ING",
    "tier2_execution.md": "EXE",
    "tier3_evaluation.md": "EVL",
    "cmn_verdict_and_cli.md": "CMN",
}


def _inventoried_identifiers() -> set[str]:
    """Collect every inventoried identifier, keyed by module and number.

    Returns:
        set[str]: Entries of the form ``ING:10001``, so a case can only match
        the inventory of the module it belongs to.
    """
    found: set[str] = set()
    for document in _DESIGN_DIRECTORY.glob("*.md"):
        module = _DOCUMENT_MODULES.get(document.name)
        if module is None:
            continue
        for line in document.read_text(encoding="utf-8").split("\n"):
            match = _INVENTORY_ROW.match(line.strip())
            if match is not None:
                found.add(f"{module}:{match.group(1)}")
    return found


def _inventory_rows() -> dict[str, str]:
    """Collect every inventory row, keyed by module and number.

    Returns:
        dict[str, str]: ``ING:10001`` to the behaviour name the design gives it.
    """
    found: dict[str, str] = {}
    for document in _DESIGN_DIRECTORY.glob("*.md"):
        module = _DOCUMENT_MODULES.get(document.name)
        if module is None:
            continue
        for line in document.read_text(encoding="utf-8").split("\n"):
            match = _NAMED_ROW.match(line.strip())
            if match is not None:
                found[f"{module}:{match.group(1)}"] = match.group(2)
    return found


def _collected_behaviours() -> dict[str, str]:
    """Collect every test callable as identifier mapped to behaviour name.

    Returns:
        dict[str, str]: Identifier to the behaviour name the test carries.
    """
    found: dict[str, str] = {}
    for module in _TEST_DIRECTORY.rglob("mqc_*.py"):
        for code, _layer, number, behaviour in _defined_callables(module):
            found[f"{code}:{number}"] = behaviour
    return found


def _collected_identifiers() -> dict[str, Path]:
    """Collect every test callable identifier the suite defines.

    Matching the source rather than importing the modules, so a module that
    fails to import is a separate failure rather than making this check
    silently pass by finding nothing.

    Returns:
        dict[str, Path]: Identifier mapped to the file defining it.
    """
    found: dict[str, Path] = {}
    for module in _TEST_DIRECTORY.rglob("mqc_*.py"):
        for code, _layer, number, _behaviour in _defined_callables(module):
            found[f"{code}:{number}"] = module
    return found

def _collected_tests() -> list[tuple[str, str, str, str]]:
    """Return every test callable the suite defines.

    **A test DEFINITION, not any mention of one.** Read from the parsed syntax
    rather than from source text, because a ``def`` inside a string literal is
    data and a regex cannot tell it from a definition. Two modules here embed
    one: a traceability case exercising a stale reference, and the dependency
    cascade's fixture sub-suite.

    Returns:
        list[tuple]: Module, layer, number and behaviour for each test.
    """
    found: list[tuple[str, str, str, str]] = []
    for source in sorted(_TEST_DIRECTORY.rglob("*.py")):
        found.extend(_defined_callables(source))
    return found

# A document-map row naming a design and stating a case count. Written as
# "87 cases" in the map and "**Inventory: 87 cases" in the design itself.
_INDEX_ROW = re.compile(
    r"\|\s*`(?P<path>docs/design/[a-z0-9_]+\.md)`\s*\|.*?(?P<count>\d+)\s+cases"
)
_INVENTORY_TOTAL = re.compile(r"^\*\*Inventory:\s*(?P<count>\d+)\s+cases")


def _inventory_total(design: Path) -> Optional[int]:
    """Return the case count a design states for itself.

    Args:
        design (Path): The design document.

    Returns:
        Optional[int]: The stated total, or ``None`` when the design states no
        inventory. **Absent is not zero**: a design with no inventory is not a
        defect, and the registries legitimately have none.
    """
    for line in design.read_text(encoding="utf-8").splitlines():
        match = _INVENTORY_TOTAL.match(line.strip())
        if match is not None:
            return int(match.group("count"))
    return None

def _credential_reads(tree: ast.AST) -> list[str]:
    """Return every credential-shaped environment variable a module reads.

    **Reuses ``forbidden_keys()`` rather than listing names.** That registry
    already defines credential-shaped for configuration loading, and
    ``GEMINI_API_KEY`` lowercased contains ``api_key``, so one set answers both
    questions. A second list would be the drift this module has corrected
    three times.

    Args:
        tree (ast.AST): A parsed module.

    Returns:
        list[str]: The names read, in source order. **Writes are excluded**: a
        test setting a fake through ``monkeypatch.setenv`` is constructing a
        fixture, while a test reading one depends on the caller's environment.
    """
    forbidden = forbidden_keys()
    found: list[str] = []

    def _is_credential(name: str) -> bool:
        lowered = name.lower()
        return any(fragment in lowered for fragment in forbidden)

    for node in ast.walk(tree):
        # os.getenv("NAME") and os.environ.get("NAME")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"getenv", "get"} and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    if _is_credential(first.value) and _reads_environ(node.func):
                        found.append(first.value)
        # os.environ["NAME"]
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            value = node.slice.value
            if isinstance(value, str) and _is_credential(value):
                if isinstance(node.value, ast.Attribute) and node.value.attr == "environ":
                    found.append(value)
    return found


def _reads_environ(func: ast.Attribute) -> bool:
    """Report whether an attribute call reaches the process environment.

    Args:
        func (ast.Attribute): The called attribute.

    Returns:
        bool: True for ``os.getenv`` and ``os.environ.get``, false for an
        unrelated ``.get`` on a dictionary, which is extremely common.
    """
    if func.attr == "getenv":
        return isinstance(func.value, ast.Name) and func.value.id == "os"
    return isinstance(func.value, ast.Attribute) and func.value.attr == "environ"


class TestMQCAuthoringOrder:
    """The suite refuses to ship a test its design never mentioned."""

    def MQC_CMN_UNI_112303_collected_test_absent_from_an_inventory_fails_the_run(self) -> None:
        """Every collected test identifier appears in a design inventory.

        A12 requires a design change to be documented before it is built. The
        order itself cannot be checked, since nothing records when a line was
        written, but the state that results from skipping it can: a test with
        no inventory row is exactly that state.

        The failure message names the file, because the correction is to return
        to the design rather than to delete the test.

        Returns:
            None
        """
        inventoried = _inventoried_identifiers()
        collected = _collected_identifiers()
        assert collected, "no test callables were found, so this check proves nothing"

        undesigned = {
            identifier: path
            for identifier, path in collected.items()
            if identifier not in inventoried
        }
        assert not undesigned, (
            "tests exist whose identifiers appear in no design inventory: "
            + ", ".join(
                f"{identifier} in {path.relative_to(_REPOSITORY_ROOT).as_posix()}"
                for identifier, path in sorted(undesigned.items())
            )
        )


class TestMQCInventoryNames:
    """A design can specify a name nothing may carry, and a test can drift."""

    def MQC_CMN_UNI_112305_inventory_name_violating_the_callable_pattern_is_reported(self) -> None:
        """An inventory row must name something a callable may be called.

        A design specifying an unimplementable name is a defect in the design,
        and the person who meets it is implementing something unrelated and has
        to stop to correct a document.

        Returns:
            None
        """
        shortest, longest = _BEHAVIOUR_LIMITS
        offending = {
            identifier: behaviour
            for identifier, behaviour in _inventory_rows().items()
            if not shortest <= len(behaviour) <= longest
        }
        assert not offending, (
            "inventory rows name behaviours a callable may not carry: "
            + ", ".join(
                f"{identifier} ({len(behaviour)} characters)"
                for identifier, behaviour in sorted(offending.items())
            )
        )

    def MQC_CMN_UNI_112306_test_name_disagreeing_with_its_inventory_row_is_reported(self) -> None:
        """An implemented behaviour name matches the one its design gives it.

        `112303` compares identifiers and says nothing about names, so a test
        renamed without its row being updated satisfies it completely. The code
        and the document then describe the same case differently, which is the
        authoring order failing from the direction it is least expected.

        Returns:
            None
        """
        inventory = _inventory_rows()
        built = _collected_behaviours()
        divergent = {
            identifier: (inventory[identifier], behaviour)
            for identifier, behaviour in built.items()
            if identifier in inventory and inventory[identifier] != behaviour
        }
        assert not divergent, (
            "tests carry behaviour names their inventory rows do not: "
            + ", ".join(
                f"{identifier} design={designed!r} code={coded!r}"
                for identifier, (designed, coded) in sorted(divergent.items())
            )
        )


class TestMQCOneIdentifierOneCallable:
    """Two callables may not claim one identifier, which a set cannot see."""

    def MQC_CMN_UNI_112326_an_identifier_bound_by_two_callables_is_reported(
        self,
    ) -> None:
        """Each module, layer and number names at most one test callable.

        **Counts bindings rather than collecting them.** Every other suite-side
        check keys on an identifier, so two callables claiming one enter a
        mapping as a single entry and the comparison balances; this one groups
        by identifier and reports any group holding more than one definition.

        Keyed by module, layer and number together, not by the number alone:
        the five-digit blocks are partitioned per module, so
        ``MQC_EVL_UNI_114605`` and ``MQC_EXE_UNI_113022`` are two cases and not a
        collision.

        Design: ``cmn_verdict_and_cli.md`` section 10.10.1.

        Returns:
            None
        """
        bindings: dict[str, list[str]] = {}
        for module in sorted(_TEST_DIRECTORY.rglob("*.py")):
            for code, layer, number, behaviour in _defined_callables(module):
                identifier = f"MQC_{code}_{layer}_{number}"
                bindings.setdefault(identifier, []).append(
                    f"{module.relative_to(_REPOSITORY_ROOT).as_posix()}"
                    f"::{identifier}_{behaviour}"
                )

        assert bindings, "no test callables were found, so this check read nothing"

        doubled = {
            identifier: sites
            for identifier, sites in bindings.items()
            if len(sites) > 1
        }
        assert not doubled, (
            "identifiers are bound by more than one test callable, so every "
            "check keyed on an identifier silently reads one of them: "
            + "; ".join(
                f"{identifier} bound at {' and '.join(sorted(sites))}"
                for identifier, sites in sorted(doubled.items())
            )
        )


class TestMQCLiveMatrixAgainstTheSuite:
    """The matrix checked against something that is not the matrix."""

    def MQC_CMN_UNI_112313_a_collected_test_named_in_no_matrix_row_is_reported(
        self,
    ) -> None:
        """A check whose inputs come from its subject proves only self-consistency.

        `112312` runs the real matrix through T1 to T5 and derives both
        ``declared`` and ``named`` from that same matrix, so T1 and T3 cannot
        fail and T4 receives the matrix as the suite. A test the suite contains
        and the matrix omits is invisible to it.

        **This supplies the collected suite**, which is the only source that is
        not the matrix, and fails in both directions.

        Returns:
            None
        """
        matrix = _REPOSITORY_ROOT / "docs" / "testing" / "rtm_harness.csv"
        with matrix.open(encoding="utf-8-sig", newline="") as handle:
            rows = [MatrixRow.from_row(entry) for entry in csv.DictReader(handle)]

        collected = {
            f"MQC_{module}_{layer}_{number}_{behaviour}"
            for module, layer, number, behaviour in _collected_tests()
        }

        named = {test_id for row in rows for test_id in row.test_ids}
        dangling = sorted(named - collected)

        assert not dangling, (
            f"{len(dangling)} matrix rows name a test the suite does not "
            f"contain: {', '.join(dangling[:8])}"
        )

        # ONE IMPLEMENTATION, TWO CALLERS. The consumer rebuilt this comparison
        # inline and asserted one direction of it, so two of its own cases ran
        # untraced while its preconditions stayed green. `MQC_CAS_UNI_115602`
        # now calls the same function against the other matrix.
        untraced = untraced_tests(rows, collected)

        assert not untraced, (
            f"{len(untraced)} collected tests appear in no matrix row, so the "
            f"requirement each satisfies is unrecorded: "
            f"{', '.join(entry.subject for entry in untraced[:8])}"
        )


class TestMQCIndexAgainstDesigns:
    """The document map checked against the documents it maps."""

    def MQC_CMN_UNI_112314_an_index_case_count_disagreeing_with_its_design_is_reported(
        self,
    ) -> None:
        """Each design was internally consistent and the index was not.

        `112203` checks a design's stated total against its own rows and was
        passing throughout, because it is scoped to a document while this drift
        is between documents.

        **The number stays and is checked** rather than being removed: the
        map's value is that a reader sees the shape of the project without
        opening six files, and a map without the numbers is a list of
        filenames.

        Returns:
            None
        """
        index = (_REPOSITORY_ROOT / "DESIGN.md").read_text(encoding="utf-8")
        disagreements: list[str] = []

        for line in index.splitlines():
            row = _INDEX_ROW.search(line)
            if row is None:
                continue
            design = _REPOSITORY_ROOT / row.group("path")
            if not design.is_file():
                disagreements.append(f"{row.group('path')} is indexed and absent")
                continue

            stated = int(row.group("count"))
            actual = _inventory_total(design)
            if actual is None:
                disagreements.append(
                    f"{design.name} is indexed with {stated} cases and states no "
                    f"inventory of its own"
                )
            elif actual != stated:
                disagreements.append(
                    f"{design.name}: the index says {stated} cases, the design "
                    f"says {actual}"
                )

        assert not disagreements, (
            "the index restates a fact that lives in the designs, and the "
            "restatement is what rots: " + "; ".join(disagreements)
        )


    def MQC_CMN_UNI_112323_a_readme_count_disagreeing_with_the_designs_is_reported(
        self,
    ) -> None:
        """The README is the front door and its two numbers had both drifted.

        It claimed 498 cases against 462 inventoried, and 144 requirements
        against 184 traced. **Neither was ever checked.** `112314` compares the
        index to the designs and `112203` compares a design to its own rows, and
        the README sat outside both while being the first thing a reader sees.

        **The numbers stay and are checked** rather than being removed, for the
        reason `112314` gives: a front page whose value is showing the shape of
        the project cannot do that without them.

        Returns:
            None
        """
        readme = (_REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        disagreements: list[str] = []

        inventoried = sum(
            total
            for total in (
                _inventory_total(design)
                for design in sorted((_REPOSITORY_ROOT / "docs/design").glob("*.md"))
            )
            if total is not None
        )
        stated_cases = re.search(r"\*\*(\d+) cases, all passing\*\*", readme)
        if stated_cases is None:
            disagreements.append("the README states no case count")
        elif int(stated_cases.group(1)) != inventoried:
            disagreements.append(
                f"the README says {stated_cases.group(1)} cases, the designs "
                f"inventory {inventoried}"
            )

        with open(
            _REPOSITORY_ROOT / "docs/testing/rtm_harness.csv",
            encoding="utf-8",
            newline="",
        ) as handle:
            traced = len(list(csv.DictReader(handle)))
        stated_reqs = re.search(r"Requirements traced \| (\d+),", readme)
        if stated_reqs is None:
            disagreements.append("the README states no requirement count")
        elif int(stated_reqs.group(1)) != traced:
            disagreements.append(
                f"the README says {stated_reqs.group(1)} requirements, the "
                f"matrix carries {traced}"
            )

        assert not disagreements, (
            f"{len(disagreements)} README figure(s) disagree with what they "
            f"describe: {'; '.join(disagreements)}"
        )

    def MQC_CMN_UNI_112327_a_graded_case_defined_here_is_reported(self) -> None:
        """No case defined in this repository belongs to a graded layer.

        **A green suite here is a statement about the instrument, not about any
        model.** `UNI` exercises our modules in isolation and `SYS` drives the
        harness end to end over recorded transcripts; neither reaches a
        provider. The graded layers live in `AP-Model-QC`, where a failure is a
        finding about a vendor's product rather than an instrument defect.

        **The README invited the other reading**, stating 549 passing cases on
        the front page of a project described as foundation-model QC, which is
        why this was added on 2026-10-05.

        **Graded is read from the layer registry, never named here.** A graded
        layer registered tomorrow is covered the day it is added, which is the
        arrangement `cmn/layers.py` exists to make possible.

        **It does not forbid the string `EVAL`.** Cases here construct synthetic
        observations in graded layers deliberately, to exercise the machinery
        that handles graded results: that plumbing is tested with fabricated
        data and never with a model. What is checked is the layer token in a
        case's own identifier, and `112307` separately establishes that the
        token agrees with the positional digit, without which this would be
        reading a label rather than a fact.

        Design: ``cmn_verdict_and_cli.md`` section 4.9.8.

        Returns:
            None
        """
        graded = {
            layer for layer in registered_layers()
            if layer_properties(layer).graded
        }
        assert graded, (
            "the layer registry reports no graded layer, so this check would "
            "pass by having nothing to look for"
        )

        offenders: list[str] = []
        scanned = 0
        for source in sorted((_REPOSITORY_ROOT / "tests").rglob("*.py")):
            for _module, layer, number, behaviour in _defined_callables(source):
                scanned += 1
                if layer in graded:
                    offenders.append(
                        f"{source.relative_to(_REPOSITORY_ROOT)}: {number} "
                        f"{behaviour} is in graded layer {layer}"
                    )

        # THE SCAN FOUND CASES, which a check passing by reading nothing would
        # not. The same guard `112325` relies on.
        assert scanned > 400, (
            f"only {scanned} case definitions were found, so the scanner no "
            f"longer reads this suite and nothing here is being checked"
        )
        assert not offenders, (
            f"{len(offenders)} case(s) defined in the harness repository "
            f"belong to a graded layer, so a green run here would carry a "
            f"claim about a model: {offenders}"
        )

    def MQC_CMN_UNI_112325_an_inventory_row_without_an_implementation_is_reported(
        self,
    ) -> None:
        """Every design inventory row names a case some repository implements.

        Reads this repository's inventory rows, which carry a category and a
        behaviour name, and compares them against the test callables this suite
        defines. Reported rather than gated: an unimplemented row is the normal
        state while a family is authored.

        A citation in prose carries no category, so it is not counted, and the
        scan needs no second checkout. ``MQC_CAS_UNI_115405`` does the same for
        the consumer's inventories.

        Design: ``cmn_verdict_and_cli.md`` section 10.19.1.

        Returns:
            None
        """
        built: set[str] = set()
        for source in sorted((_REPOSITORY_ROOT / "tests").rglob("*.py")):
            for module, layer, number, behaviour in _defined_callables(source):
                assert module and layer and behaviour
                built.add(number)

        designed: dict[str, str] = {}
        for document in sorted(_REPOSITORY_ROOT.rglob("docs/**/*.md")):
            for line in document.read_text(encoding="utf-8").splitlines():
                found = _INVENTORY_IDENTIFIER.match(line.strip())
                if found is not None:
                    designed.setdefault(found.group(1), document.name)

        assert designed and built, "one of the two artefacts was not read"

        assert len(designed) > 400, (
            f"only {len(designed)} inventory rows were recognised, so the row "
            f"pattern no longer matches the inventories it is checking"
        )

        unbuilt = sorted(
            f"{number} [{document}]"
            for number, document in designed.items()
            if number not in built
        )

        # REPORTED, NOT GATED. The assertion is on the empty list because the
        # list is empty today: 627 rows, 627 implemented. Were a family mid
        # authoring, this would be relaxed to a logged count rather than
        # deleted, and the design row would stay either way.
        assert not unbuilt, (
            f"{len(unbuilt)} inventory row(s) name a case this suite does "
            f"not implement, so a designed case exists as design alone. Implement "
            f"it or record the omission with its reason; do not remove the row: "
            f"{unbuilt[:6]}"
        )



class TestMQCCredentialFreeSuite:
    """The harness proves itself without spending anybody's quota."""

    def MQC_CMN_UNI_112315_a_harness_test_reading_a_credential_is_reported(
        self,
    ) -> None:
        """Documented in four places, protected in CI, asserted by nothing.

        A test that read a credential would pass on any machine with a key
        exported and fail in CI, where the secret is unreachable from
        ``gate-on-change.yml`` by construction. The failure would arrive as a
        missing-environment error inside an unrelated assertion rather than as
        a statement that the test should not have needed a key at all.

        **Reads are flagged and writes are not.** A test setting a fake through
        ``monkeypatch.setenv`` is constructing a fixture. A test reading one is
        depending on the caller's environment, which is the defect.

        Returns:
            None
        """
        offending: list[str] = []
        sources = [_REPOSITORY_ROOT / "conftest.py", *_TEST_DIRECTORY.rglob("*.py")]

        for source in sorted(set(sources)):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            relative = source.relative_to(_REPOSITORY_ROOT).as_posix()
            for name in _credential_reads(tree):
                offending.append(f"{relative} reads {name}")

        assert not offending, (
            "the harness must prove itself without a credential, so a test may "
            "not read one: " + "; ".join(offending)
        )

        # Not vacuous: the helper finds a read when one is present. Parsed from
        # a snippet rather than matched as text, because this very file names
        # the shape it rejects.
        probe = ast.parse("import os\nkey = os.environ['GEMINI_API_KEY']\n")
        assert _credential_reads(probe) == ["GEMINI_API_KEY"]
        allowed = ast.parse("monkeypatch.setenv('GEMINI_API_KEY', 'fake')\n")
        assert not _credential_reads(allowed)
