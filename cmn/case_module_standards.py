# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Where a test module's supporting code is allowed to live.

Specified by ``docs/design/harness_test_taxonomy.md`` section 13.

**A collected test module holds cases, and nothing else holds cases.** The
functions and classes that support them belong in a sibling module that
collection never reaches, which ``pytest.ini`` already arranges: it collects
``mqc_*.py`` alone, so ``graded_support.py`` and ``provider_doubles.py`` are
imported and never collected.

**This is a separate module from ``code_standards.py`` on purpose.** That one is
about the source a reader writes, this one about where test support lives, and
putting the second reader in the first would have taken it past the
thousand-line ceiling — which is the same pressure this rule exists to relieve,
one level up.

**Named for case modules rather than test modules**, because ``.pylintrc``
refuses a module name beginning with ``test_``: pytest would try to collect it
from some invocations, and a reader cannot tell a checker from a suite by its
name alone. The first draft was ``test_module_standards`` and the naming rule
rejected it, correctly.
"""

import ast
import logging
from datetime import date
from pathlib import Path
from typing import Final

from cmn.declared_gaps import declared_entries, lapsed_problems

logger = logging.getLogger(__name__)

# COLLECTION IS THE BOUNDARY, not a naming preference. `pytest.ini` sets
# `python_files = mqc_*.py`, so a module outside that glob is support by
# construction and no rule has to be remembered for it.
COLLECTED_GLOB: Final[str] = "mqc_*.py"

# A FIXTURE IS NOT SUPPORT CODE. It is wiring for the cases in its own module,
# bound to them by name, and pytest's own idiom puts it beside them or in a
# conftest. Moving fixtures to a support module would make the cases harder to
# read in exchange for a tidier line count, which is the wrong trade.
_FIXTURE_MARKER: Final[str] = "fixture"

# THE CALLS THAT CAN BLOCK FOREVER. Spelled as the source spells them, because
# the AST is unparsed back to text for comparison.
_BOUNDED_CALLS: Final[frozenset[str]] = frozenset({
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.check_output",
    "subprocess.check_call",
    "subprocess.call",
})

# TREES THAT ARE NOT OURS. A virtual environment and a build directory carry
# third-party source whose subprocess calls are not this project's to bound.
_SKIPPED: Final[frozenset[str]] = frozenset({
    ".venv", "build", "__pycache__", ".git", "node_modules",
})


def inline_support(module: Path) -> list[str]:
    """Return the module-level support definitions a test module carries.

    **Parsed, not matched.** A ``def`` inside a string literal is data, and
    this project embeds some deliberately: a traceability case exercising a
    stale reference, and fixture sub-suites run in a subprocess.

    Args:
        module (Path): The module to read.

    Returns:
        list[str]: ``"function name"`` or ``"class Name"`` per definition, in
        source order. Empty for a module that holds only cases, its fixtures
        and its constants. **A module that will not parse yields nothing
        here** and fails its own collection separately, which keeps one defect
        from being reported as two.
    """
    try:
        tree = ast.parse(module.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    found: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decorators = [ast.unparse(item) for item in node.decorator_list]
            if any(_FIXTURE_MARKER in item for item in decorators):
                continue
            found.append(f"function {node.name}")
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("Test"):
            found.append(f"class {node.name}")
    return found


def extraction_problems(
    tests: Path, root: Path, registry: Path, as_of: date
) -> list[str]:
    """Report test modules holding support code, and registry entries that lapsed.

    Three directions, because each catches a different failure:

    * a collected module defining support that nothing declares is the rule
      being broken by a new module or a new helper,
    * a declared entry past its expiry is a conversion that stopped,
    * a declared entry whose module holds no support any more is a closed gap
      still listed, which is the defect this project has found in three other
      registries.

    Args:
        tests (Path): The test tree to scan.
        root (Path): The repository root, for reporting relative paths.
        registry (Path): The declaration of modules not yet extracted.
        as_of (date): The date expiries are judged against, injected so the
            check is not a function of when it runs.

    Returns:
        list[str]: One message per problem, empty when the rule holds.
    """
    declared = declared_entries(registry, "not_yet_extracted")
    problems: list[str] = []
    seen: set[str] = set()

    for module in sorted(tests.rglob(COLLECTED_GLOB)):
        relative = module.relative_to(root).as_posix()
        carried = inline_support(module)
        record = declared.get(relative)
        if record is not None:
            seen.add(relative)
            if not carried:
                problems.append(
                    f"{relative} is recorded as not yet extracted and "
                    f"holds no support definitions any more, so the entry "
                    f"outlived the work. Remove it"
                )
                continue
            problems.extend(
                lapsed_problems(
                    relative, record, as_of, "not yet extracted"
                )
            )
            continue
        if carried:
            problems.append(
                f"{relative} is collected as a test module and defines "
                f"{len(carried)} support definition(s) ({', '.join(carried)}), "
                f"which belong in a sibling module collection does not reach. "
                f"Declare it in the registry with a reason and an expiry, or "
                f"extract it"
            )

    # AND AN ENTRY FOR A MODULE THAT IS GONE, which is how a registry survives
    # a rename and keeps asserting something about a path nothing provides.
    for relative in sorted(set(declared) - seen):
        problems.append(
            f"{relative} is recorded as not yet extracted and is not a "
            f"collected test module in this repository, so the entry asserts "
            f"something about a path that does not exist"
        )
    return problems


def unbounded_subprocess_calls(root: Path) -> list[str]:
    """Report every subprocess invocation that passes no timeout.

    **An unbounded wait is the worst failure shape available.** A crash names
    itself; a hang names nothing, arrives after the longest possible delay, and
    presents as an environmental fault on whichever platform happened to stall.
    One cancelled a Windows job 22 minutes into a run that reported `failure`
    with no failing job and no log.

    **Read from the AST, so a call spelled across several lines is still seen**,
    and so a mention inside a string literal is not.

    **The keyword is checked, never the value.** Whether a particular bound is
    right is a judgement; whether a bound exists is not, and only the second is
    mechanical.

    Design: ``harness_test_taxonomy.md`` section 14.

    Args:
        root (Path): The repository root to scan.

    Returns:
        list[str]: One entry per unbounded call, naming the file and line.
    """
    problems: list[str] = []
    for source in sorted(root.rglob("*.py")):
        if any(part in _SKIPPED for part in source.parts):
            continue
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = ast.unparse(node.func)
            if called not in _BOUNDED_CALLS:
                continue
            if any(keyword.arg == "timeout" for keyword in node.keywords):
                continue
            problems.append(
                f"{source.relative_to(root).as_posix()}:{node.lineno}: "
                f"{called} passes no timeout, so a child that stalls blocks "
                f"forever and the job is cancelled rather than failed"
            )
    return problems
