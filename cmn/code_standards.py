# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The code-style rules that no linter checks, as functions over a tree.

Extracted 2026-09-23, when the rules had to apply to two repositories rather
than one.

**Pylint checks none of these.** It has no opinion on whether an annotation is
present, on which annotation semantics a module selects, or on whether a file
says what licence it carries. Each rule stood in ``code-style.md`` while being
enforced by nothing, and the annotation rule in particular stood there from the
project's first commit while 597 test callables violated it.

**They are parameterised by root and licence rather than duplicated.** A case
repository is MIT and the harness is Apache-2.0, which is the only difference
between the two enforcements. Copying the checkers to state that one difference
would be two implementations of one rule, and the copy would drift in the
direction of whichever repository was edited less often.

``.pylintrc`` remains the enforcement for naming, line length and the rest. This
module is deliberately only the part pylint cannot express.
"""

import ast
import re
from datetime import date
from pathlib import Path
from typing import Any, Final

import yaml

from cmn.options import registered_options

# Not this project's source, so not this project's conventions to enforce.
COPYRIGHT_TAG: Final[str] = "SPDX-FileCopyrightText:"

# `logs` holds untracked working output, including the prompt log, which
# is never committed because it is the one place a credential could be
# pasted. The header rule binds tracked files.
# TREES THIS REPOSITORY DOES NOT AUTHOR. Vendored code, build output and tool
# caches, none of which a licence header belongs in.
#
# THE CACHES ARRIVED 2026-09-26, FROM A CI FAILURE THAT COULD NOT REPRODUCE
# LOCALLY. `pytest` writes `.pytest_cache/README.md`, which this scan read as a
# document the repository owns. It passed here and failed in CI for the worst
# possible reason: an earlier header pass had written a header INTO the local
# copy, so the local tree carried a property a fresh checkout did not, and the
# check was measuring the leftovers of its own remediation.
SKIPPED_TREES: Final[frozenset[str]] = frozenset(
    {"venv", ".venv", "build", "dist", "__pycache__", ".git",
     "node_modules", "logs",
     ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
     "htmlcov", ".eggs", "reports", "allure-results"}
)


def python_sources(root: Path) -> list[Path]:
    """Return every Python file a repository owns.

    Args:
        root (Path): The repository root.

    Returns:
        list[Path]: Sorted source paths, excluding vendored and generated
        trees. **Sorted** so a failure message names files in a stable order
        and a diff of two runs is readable.
    """
    return [
        source
        for source in sorted(root.rglob("*.py"))
        if not any(part in SKIPPED_TREES for part in source.parts)
    ]


def annotation_gaps(root: Path) -> list[str]:
    """Return every parameter and return type that carries no annotation.

    **Test code is held to this identically.** A test callable is a function
    like any other, and its fixtures are its parameters.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per gap, each naming file, line and callable.
    """
    gaps: list[str] = []
    for source in python_sources(root):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            where = f"{source.relative_to(root).as_posix()}:{node.lineno} {node.name}"
            if node.returns is None:
                gaps.append(f"{where} has no return annotation")
            arguments = node.args
            declared = (
                list(arguments.posonlyargs)
                + list(arguments.args)
                + list(arguments.kwonlyargs)
                + [entry for entry in (arguments.vararg, arguments.kwarg) if entry]
            )
            gaps.extend(
                f"{where} parameter {entry.arg} has no annotation"
                for entry in declared
                if entry.arg not in {"self", "cls"} and entry.annotation is None
            )
    return gaps


def future_annotation_imports(root: Path) -> list[str]:
    """Return every module selecting PEP 563 stringized annotations.

    Python 3.14 implements PEP 649, so annotations are already evaluated lazily
    and the import buys nothing. What it does instead is select PEP 563, which
    turns every annotation into a string and removes
    ``annotationlib.Format.VALUE``.

    **Parsed, never matched as a substring.** A file describing the rule names
    the import in a string literal, and a substring check reports itself. That
    over-reporting is what trains a check away on its second run.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: Relative paths of the offending modules.
    """
    offending: list[str] = []
    for source in python_sources(root):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "__future__"
                and any(alias.name == "annotations" for alias in node.names)
            ):
                offending.append(source.relative_to(root).as_posix())
    return offending


def header_problems(root: Path, licence: str) -> list[str]:
    """Return every file whose SPDX header is absent, misplaced or wrong.

    **Position is checked, not only presence.** The header sits above the
    module docstring, because a docstring must remain the first statement or
    ``__doc__`` is empty, and this project reads module docstrings as
    specification prose. A header pasted inside one would satisfy a presence
    check while silently emptying the documentation.

    Args:
        root (Path): The repository root.
        licence (str): The SPDX identifier this repository's files must
            declare. **Named rather than accepting any valid tag**, which is
            the entire point: code from one repository installs into another
            under a different licence, so a file separated from its repository
            has to carry its own correct answer.

    Returns:
        list[str]: One entry per problem.
    """
    expected = f"# SPDX-License-Identifier: {licence}"
    problems: list[str] = []

    for source in python_sources(root):
        content = source.read_text(encoding="utf-8")
        opening = content.splitlines()[:2]
        relative = source.relative_to(root).as_posix()

        if len(opening) < 2:
            problems.append(f"{relative} is too short to carry a header")
            continue
        if not opening[0].startswith("# SPDX-FileCopyrightText:"):
            problems.append(f"{relative} has no copyright line at the top")
        if opening[1] != expected:
            problems.append(f"{relative} does not declare {licence}")

        # The docstring must still be the first statement. Parsing settles that
        # rather than counting lines.
        if ast.get_docstring(ast.parse(content)) is None:
            problems.append(f"{relative} lost its module docstring")

    return problems


# How each format writes a comment. The header says the same two things in all
# of them; only the syntax differs, and each is the syntax that format's
# readers already expect.
MARKUP_STYLES: Final[dict[str, tuple[str, str, str]]] = {
    ".md": ("<!--", "", "-->"),
    ".yaml": ("", "# ", ""),
    ".yml": ("", "# ", ""),
}

# The licence text itself. A file stating its own terms needs no tag pointing
# at itself.
LICENCE_FILES: Final[frozenset[str]] = frozenset({"LICENSE", "NOTICE"})


def markup_sources(root: Path) -> list[Path]:
    """Return every document and data file the repository authors.

    **It walks the filesystem rather than asking git**, so "authors" is decided
    by :data:`SKIPPED_TREES` rather than by what is tracked. An earlier version
    of this docstring said "tracked", which was not what the code did and hid a
    real difference: a generated file in an ignored directory is untracked and
    was still being read.

    Args:
        root (Path): The repository root.

    Returns:
        list[Path]: Sorted markdown and YAML paths, excluding the trees in
        :data:`SKIPPED_TREES` and the licence files themselves.
    """
    found: list[Path] = []
    for suffix in sorted(MARKUP_STYLES):
        found.extend(
            source
            for source in root.rglob(f"*{suffix}")
            if not any(part in SKIPPED_TREES for part in source.parts)
            and source.stem not in LICENCE_FILES
        )
    return sorted(found)


def markup_header_problems(root: Path, licence: str) -> list[str]:
    """Return every document or data file whose SPDX header is absent or wrong.

    **A separate check from** :func:`header_problems` **rather than a widening
    of it.** A Python file must carry the header above its module docstring,
    because a docstring must remain the first statement or ``__doc__`` is
    empty. Markdown and YAML have no such constraint, so the two checks assert
    different things and folding them together would give one check two shapes.

    Args:
        root (Path): The repository root.
        licence (str): The SPDX identifier this repository's files declare.

    Returns:
        list[str]: One entry per problem.
    """
    problems: list[str] = []

    for source in markup_sources(root):
        opener, prefix, _ = MARKUP_STYLES[source.suffix]
        head = source.read_text(encoding="utf-8").splitlines()[:4]
        relative = source.relative_to(root).as_posix()

        if opener and (not head or head[0].strip() != opener):
            problems.append(f"{relative} does not open with {opener}")
            continue

        body = head[1:] if opener else head
        wanted = f"{prefix}SPDX-License-Identifier: {licence}"
        if not any(line.strip().startswith(f"{prefix}{COPYRIGHT_TAG}") for line in body):
            problems.append(f"{relative} has no copyright line")
        if not any(line.rstrip() == wanted for line in body):
            problems.append(f"{relative} does not declare {licence}")

    return problems


# The runbook, relative to a repository root. One per repository, because the
# harness names no consumer and the workflows differ anyway.
RUNBOOK: Final[str] = "docs/running_jobs.md"

# A documented dispatch, as the runbook spells it.
_DISPATCH = re.compile(r"gh workflow run\s+(\S+\.yml)")

# An input named on that command line. GitHub rejects an undeclared one, and
# the reader concludes the procedure is broken rather than the page.
_FIELD = re.compile(r"--field\s+([A-Za-z_][A-Za-z0-9_-]*)=")


def runbook_problems(root: Path) -> list[str]:
    """Report every documented dispatch that would be rejected.

    **Prose is checked because a reader who believes a page stops looking.**
    The failure is silent at authoring time and lands on whoever follows the
    procedure, which is the person least able to tell a wrong page from a
    broken workflow.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per problem, naming the command and what is wrong
        with it. An empty list means every documented dispatch would be
        accepted. **A missing runbook is not a problem here**, because whether
        a repository carries one is a separate question from whether the one it
        carries is correct.
    """
    runbook = root / RUNBOOK
    if not runbook.is_file():
        return []

    problems: list[str] = []
    for command in _dispatch_commands(runbook.read_text(encoding="utf-8")):
        workflow = _DISPATCH.search(command)
        if workflow is None:
            continue
        definition = root / ".github" / "workflows" / workflow.group(1)
        if not definition.is_file():
            problems.append(
                f"{RUNBOOK} dispatches {workflow.group(1)}, which does not exist"
            )
            continue
        declared = _declared_inputs(definition)
        for field in _FIELD.findall(command):
            if field not in declared:
                problems.append(
                    f"{RUNBOOK} passes --field {field} to {workflow.group(1)}, "
                    f"which declares {sorted(declared)}"
                )
    return problems


# THE TWO MANDATED ARTIFACTS, as the flags that write them.
# `testing-standards.md` section 5 requires both, so these are a pair and not
# a menu. Design `cmn_verdict_and_cli.md` section 7.1.0.3.
_JUNIT_FLAG: Final[str] = "--junitxml"
_ALLURE_FLAG: Final[str] = "--alluredir"

# `--out-dir` supplies both destinations at once, so an invocation naming it
# satisfies the mandate without either flag.
_DERIVES_BOTH: Final[str] = "--out-dir"

def artifact_mandate_gaps(root: Path) -> list[str]:
    """Report every workflow step emitting one mandated artifact and not both.

    Reads each workflow's ``run:`` blocks and reports a step naming
    ``--junitxml`` without ``--alluredir``, or the reverse, unless it names
    ``--out-dir``, which supplies both destinations.

    **Keyed on the artifact flags, not on the word pytest.** A step whose
    command comes from a matrix value never spells the runner, and one of the
    gaps this check exists for is exactly that shape. What the mandate governs
    is the artifacts a step emits, which the flags name directly.

    **A step naming neither flag is not reported**: it writes no artifact, so
    it is a selection probe or a resolver rather than a half-emitted result.

    Design: ``cmn_verdict_and_cli.md`` section 7.1.0.3.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per step, naming the workflow, the step and which
        artifact is missing. An empty list means every step that writes an
        artifact writes both.
    """
    folder = root / ".github" / "workflows"
    if not folder.is_dir():
        return []

    gaps: list[str] = []
    for workflow in sorted(folder.glob("*.yml")):
        parsed = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
        for job_name, job in (parsed.get("jobs") or {}).items():
            for step in (job or {}).get("steps") or []:
                script = str((step or {}).get("run") or "")
                if _DERIVES_BOTH in script:
                    continue
                has_junit = _JUNIT_FLAG in script
                has_allure = _ALLURE_FLAG in script
                if has_junit == has_allure:
                    continue
                missing = _ALLURE_FLAG if has_junit else _JUNIT_FLAG
                named = str((step or {}).get("name") or "an unnamed step")
                gaps.append(
                    f"{workflow.name} job {job_name} step {named!r} names "
                    f"{_JUNIT_FLAG if has_junit else _ALLURE_FLAG} and not "
                    f"{missing}, so it emits half the artifact contract"
                )
    return gaps


def _dispatch_commands(text: str) -> list[str]:
    """Return every fenced line that dispatches a workflow.

    Args:
        text (str): The runbook source.

    Returns:
        list[str]: The command lines. **Fenced blocks only**, so prose naming a
        workflow in passing is not read as a command somebody could run.
    """
    commands: list[str] = []
    fenced = False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced and "gh workflow run" in line:
            commands.append(line)
    return commands


def _declared_inputs(definition: Path) -> set[str]:
    """Return the dispatch inputs a workflow declares.

    Args:
        definition (Path): The workflow file.

    Returns:
        set[str]: Every declared input name, empty when the workflow takes
        none.
    """
    parsed = yaml.safe_load(definition.read_text(encoding="utf-8"))
    # PyYAML reads the bare key `on` as the boolean True, so both spellings
    # have to be tried. This is the one place the quirk is load-bearing.
    triggers = parsed.get(True) or parsed.get("on") or {}
    dispatch = triggers.get("workflow_dispatch") or {}
    return set((dispatch.get("inputs") or {}).keys())


# The calls that read or write a file and must say in which encoding. `open`
# is the builtin; the other two are Path methods, matched by attribute name
# because Tier-crossing would be the only way to know the receiver is a Path.
_ENCODED_CALLS: Final[frozenset[str]] = frozenset(
    {"open", "read_text", "write_text"}
)

# Binary modes carry no encoding and must not declare one. A call passing "rb"
# or "wb" is correct precisely by omitting it.
_BINARY_MODES: Final[frozenset[str]] = frozenset({"rb", "wb", "ab", "r+b", "w+b", "xb"})


def encoding_gaps(root: Path) -> list[str]:
    """Report every file read or write that declares no encoding.

    **Parsed, not matched.** A regex for ``open(`` cannot tell a call from the
    word in a docstring, and this project has already corrected one scanner
    that could not tell a definition from a definition inside a string.

    **This rule fails more quietly than any other here.** A missing encoding
    raises nothing: it reads ``cp1252`` on Windows and ``utf-8`` on Linux, so
    the same commit yields different values on the two platforms CI runs, and
    both runs report success.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per call, naming the file and line. Empty when
        every call declares an encoding or opens in a binary mode, which
        carries none and must not claim one.
    """
    problems: list[str] = []
    for source in python_sources(root):
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _called_name(node)
            if name not in _ENCODED_CALLS:
                continue
            if _is_binary_open(node) or _declares_encoding(node):
                continue
            problems.append(
                f"{source.relative_to(root).as_posix()}:{node.lineno} calls "
                f"{name} without an encoding, which reads cp1252 on Windows "
                f"and utf-8 on Linux and raises nothing either way"
            )
    return problems


def _called_name(node: ast.Call) -> str:
    """Return the name of the function a call invokes.

    Args:
        node (ast.Call): The call.

    Returns:
        str: The bare name, or the attribute for a method call, empty when
        neither applies.
    """
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _declares_encoding(node: ast.Call) -> bool:
    """Report whether a call passes an encoding.

    Args:
        node (ast.Call): The call.

    Returns:
        bool: True when an ``encoding`` keyword is present, whatever its
        value. **The value is not checked here**: ``utf-8-sig`` is correct at
        ingest, and a checker insisting on one spelling would report the
        deliberate choice as a defect.
    """
    return any(keyword.arg == "encoding" for keyword in node.keywords)


def _is_binary_open(node: ast.Call) -> bool:
    """Report whether a call opens a file in binary mode.

    Args:
        node (ast.Call): The call.

    Returns:
        bool: True when a literal binary mode is supplied, positionally or by
        keyword. A binary handle carries no encoding and declaring one raises.
    """
    modes = list(node.args[1:2])
    modes.extend(
        keyword.value for keyword in node.keywords if keyword.arg == "mode"
    )
    return any(
        isinstance(mode, ast.Constant) and mode.value in _BINARY_MODES
        for mode in modes
    )
def flag_coverage_declaration(path: Path) -> dict[str, dict[str, Any]]:
    """Read which side proves each registered flag does something.

    Args:
        path (Path): The declaration file.

    Returns:
        dict: Flag to its entry, carrying ``owner`` or ``gap``.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the file is absent or
            declares a flag the registry does not carry. **A declaration for a
            flag nobody registered is a stale entry**, and a stale entry in a
            coverage list is the thing the list exists to prevent.
    """
    if not path.is_file():
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: no flag coverage declaration at {path}"
        )
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    declared = dict((loaded.get("flags") or {}).items())
    registered = {entry.cli_flag for entry in registered_options()}
    unknown = sorted(set(declared) - registered)
    if unknown:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: flag coverage declares {unknown}, which "
            f"the option registry does not carry"
        )
    return declared


def flags_named_by_cases(root: Path) -> set[str]:
    """Return every registered flag some test module names.

    **Text, not syntax, and deliberately.** A flag reaches a case as a string
    in a command line, an option dictionary or a parametrised value, and there
    is no one syntactic shape to look for. The looseness is the right side to
    err on: this check asks whether anything claims to exercise the flag, and
    whether the claim is true is settled by injection rather than by parsing.

    Args:
        root (Path): The repository root to scan.

    Returns:
        set[str]: The flags named by at least one case.
    """
    named: set[str] = set()
    flags = [entry.cli_flag for entry in registered_options()]
    for source in root.rglob("mqc_*.py"):
        if any(part in SKIPPED_TREES for part in source.parts):
            continue
        text = source.read_text(encoding="utf-8")
        named.update(flag for flag in flags if flag in text)
    return named


def flag_coverage_problems(
    root: Path, owner: str, declaration: Path, as_of: date
) -> list[str]:
    """Return every flag this side owns and no case of its names, plus lapses.

    Args:
        root (Path): The repository root whose cases are scanned.
        owner (str): ``harness`` or ``consumer``, the share to assert.
        declaration (Path): The coverage declaration.
        as_of (date): The date expiries are judged against, injected so the
            check is not a function of when it runs.

    Returns:
        list[str]: One message per uncovered flag or expired gap, empty when
        this side's share holds.
    """
    declared = flag_coverage_declaration(declaration)
    named = flags_named_by_cases(root)
    problems: list[str] = []

    for entry in registered_options():
        flag = entry.cli_flag
        record = declared.get(flag)
        if record is None:
            problems.append(
                f"{flag} is registered and the coverage declaration does not "
                f"say who proves it works"
            )
            continue
        gap = record.get("gap")
        if gap is not None:
            expires = gap.get("expires_on")
            if isinstance(expires, date) and expires < as_of:
                problems.append(
                    f"{flag} has been a declared coverage gap since its expiry "
                    f"on {expires.isoformat()}: {gap.get('reason', '')!s}".strip()
                )
            continue
        if record.get("owner") == owner and flag not in named:
            problems.append(
                f"{flag} is owned by {owner} and no case names it, so nothing "
                f"establishes that it does anything"
            )
    return problems


# THE POSITIONAL SCHEME, as `test_taxonomy.md` section 3.2.1 states it. Held
# here rather than in the document alone, because a scheme nothing reads is the
# state the hundred-slot partition was in when it broke in three places.
_LAYER_DIGIT: Final[dict[str, str]] = {
    "UNI": "1", "SYS": "2", "EVAL": "3", "TOOL": "4", "SEC": "5",
}
_MODULE_DIGIT: Final[dict[str, str]] = {
    "ING": "1", "CMN": "2", "EXE": "3", "EVL": "4", "CAS": "5",
}

_IDENTIFIED = re.compile(r"^MQC_([A-Z]{3})_([A-Z]{3,5})_(\d+)_[a-z0-9_]+$")


def identifier_block_problems(root: Path) -> list[str]:
    """Report every collected callable whose digits contradict its tokens.

    An identifier is six positional digits: the domain, the layer, the module,
    the category and the case. This reads the layer and module tokens from the
    name and checks the digits that encode them.

    **It compares two halves of one name**, which is what makes it different
    from the duplicate-binding check: two modules occupying one block are two
    distinct identifiers, so counting bindings cannot see it.

    Design: ``test_taxonomy.md`` section 3.2.1.4.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per disagreement. Empty when every identifier's
        digits say what its tokens say.
    """
    problems: list[str] = []
    for source in sorted((root / "tests").rglob("*.py")):
        if "__pycache__" in source.parts:
            continue
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            matched = _IDENTIFIED.match(node.name)
            if matched is None:
                continue
            module, layer, digits = matched.groups()
            where = f"{source.relative_to(root).as_posix()}::{node.name}"
            if len(digits) != 6:
                problems.append(
                    f"{where} carries {len(digits)} digits, and the scheme is six"
                )
                continue
            expected_layer = _LAYER_DIGIT.get(layer)
            expected_module = _MODULE_DIGIT.get(module)
            if expected_layer is not None and digits[1] != expected_layer:
                problems.append(
                    f"{where} says layer {layer}, whose digit is "
                    f"{expected_layer}, and carries {digits[1]}"
                )
            if expected_module is not None and digits[2] != expected_module:
                problems.append(
                    f"{where} says module {module}, whose digit is "
                    f"{expected_module}, and carries {digits[2]}"
                )
    return problems


# SECTION 9.1'S TABLE, as that document writes it: a group, a backticked field
# and a scope. Parsed rather than copied, because a second list drifts and this
# one did. Design `test_taxonomy.md` section 9.5.
_FIELD_ROW: Final[re.Pattern] = re.compile(
    r"^\|[^|]*\|\s*`([a-z_]+)`\s*\|\s*(\*\*)?(Result|Run)(\*\*)?\s*\|"
)


def required_result_fields(taxonomy: Path) -> dict[str, str]:
    """Return every field section 9.1 declares, and the scope of each.

    **Read from the table rather than restated.** Section 9 calls itself the
    single normative list and its preamble names the hazard: two
    hand-maintained lists drift, and by 2026-10-03 there were three.

    Design: ``test_taxonomy.md`` section 9.5.

    Args:
        taxonomy (Path): The taxonomy document.

    Returns:
        dict: Field name to ``"Result"`` or ``"Run"``.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the table yields
            nothing, because a reader finding no rows would report no problems
            and pass for having read nothing.
    """
    declared: dict[str, str] = {}
    inside = False
    for line in taxonomy.read_text(encoding="utf-8").splitlines():
        if line.startswith("### 9.1"):
            inside = True
            continue
        if inside and line.startswith("### "):
            break
        if not inside:
            continue
        matched = _FIELD_ROW.match(line)
        if matched is not None:
            declared[matched.group(1)] = matched.group(3)

    if not declared:
        raise ValueError(
            "QC_HARNESS_PARSER_ERROR: section 9.1 yielded no fields, so this "
            "reader would report no problems by having read nothing"
        )
    return declared
