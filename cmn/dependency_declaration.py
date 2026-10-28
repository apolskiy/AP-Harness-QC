# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Reads a repository's declared dependencies and derives its requirements files.

Created: 2026-10-28
Last updated: 2026-10-28

This file contains ``read_declaration``, which returns the runtime and ``dev``
dependency lists a ``pyproject.toml`` declares; ``declared_names``, which
normalizes those specifiers to distribution names; ``render`` and
``generated_files``, which produce the contents ``requirements.txt`` and
``requirements-dev.txt`` should hold without writing them; and
``undeclared_imports``, which reports a package the code imports and the
declaration omits.

It is called with a repository root, so each repository's generator writes its
own files and each repository's case checks its own declaration from this one
implementation. A failure here means an install would not behave as the
repository describes: either the derived files disagree with the declaration, or
something the code imports arrives only on a machine that happens to have it.

**The headers are deliberately generic.** They state that the files are derived
and where the reasoning lives, and nothing about either repository in
particular, because prose repeated in two generated files is prose that drifts.
``DESIGN.md`` section 5.0.1 carries why a measurement dependency takes a range
and a gating tool takes an exact pin.

Specified by ``DESIGN.md`` section 5.0.1 and ``docs/design/cmn_verdict_and_cli.md``
section 10.5.
"""

import ast
import re
import sys
import tomllib
from pathlib import Path
from typing import Final

_ENCODING: Final[str] = "utf-8"

# TREES THAT ARE NOT A REPOSITORY'S SOURCE. A virtual environment holds the
# installed copy of every declared dependency, so walking into one reports the
# whole dependency tree as imported by this project.
_SKIPPED_TREES: Final[frozenset[str]] = frozenset(
    {"venv", ".venv", "build", "dist", "__pycache__"}
)

_RUNTIME_HEADER: Final[str] = """\
# GENERATED FROM pyproject.toml. Do not edit by hand.
#
# Regenerate with:  python tools/generate_requirements.py
#
# pyproject.toml is the single declaration. This file exists because tooling
# expects it, not because it is a second source of truth: PyCharm offers to
# install from a requirements file and does not read an optional-dependency
# extra, and a contributor should not have to know which convention was chosen.
#
# A runtime dependency takes part in a measurement, so it takes a range and a
# patch fix arrives without a commit. The gating tools are pinned exactly in
# requirements-dev.txt instead. DESIGN.md section 5.0.1 carries the distinction.
"""

_DEV_HEADER: Final[str] = """\
# GENERATED FROM pyproject.toml. Do not edit by hand.
#
# Regenerate with:  python tools/generate_requirements.py
#
# Everything the CI gates need, on top of the runtime dependencies. This is what
# `pip install --editable ".[dev]"` installs, and what CI uses.
#
# A gating tool is pinned exactly rather than ranged, because it decides what is
# collected and whether a gate passes: its drift changes the verdict on every
# other case at once and says nothing. DESIGN.md section 5.0.1.

-r requirements.txt
"""


def read_declaration(pyproject: Path) -> tuple[list[str], list[str]]:
    """Return the runtime and development dependencies as declared.

    Args:
        pyproject (Path): The declaration file.

    Returns:
        tuple: The runtime list and the development list, in declared order.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the declaration
            cannot be read. Generating an empty requirements file from an
            unreadable declaration would produce a file that installs nothing
            and says so nowhere.
    """
    try:
        data = tomllib.loads(pyproject.read_text(encoding=_ENCODING))
        project = data["project"]
        return (
            list(project["dependencies"]),
            list(project["optional-dependencies"]["dev"]),
        )
    except (OSError, tomllib.TOMLDecodeError, KeyError) as error:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: {pyproject} does not declare dependencies"
        ) from error


def declared_names(specifiers: list[str]) -> set[str]:
    """Return the distribution name each specifier declares, normalized.

    A name is lowercased with hyphens read as underscores, so that a
    declaration and an import name are compared in one spelling.

    **An extra is part of the name and is retained**, so ``ap-harness-qc[dev]``
    yields ``ap_harness_qc[dev]`` and not ``ap_harness_qc``. Stripping it would
    make a check unable to tell a dependency whose packages arrive only through
    an extra from one declared without it, and that is exactly the defect found
    in the case repository on 2026-10-28: pytest lives in this repository's
    ``dev`` extra, so an alias pointing at the bare distribution would have gone
    on passing with the extra removed.

    Args:
        specifiers (list): Requirement specifiers as declared.

    Returns:
        set: The distribution names with any extra, normalized.
    """
    return {
        re.split(r"[<>=!@]", entry)[0].strip().lower().replace("-", "_")
        for entry in specifiers
    }


def render(header: str, requirements: list[str]) -> str:
    """Render one requirements file.

    Args:
        header (str): The generated-file notice.
        requirements (list): The requirement specifiers.

    Returns:
        str: The file contents, newline terminated.
    """
    return header + "\n" + "\n".join(requirements) + "\n"


def generated_files(root: Path) -> dict[Path, str]:
    """Return the contents each generated file should have.

    Returning the contents rather than writing them is what lets a case compare
    without a temporary directory, and what lets this be called from a test
    without a side effect.

    Args:
        root (Path): The repository root.

    Returns:
        dict: Path to the contents it should hold.
    """
    runtime, development = read_declaration(root / "pyproject.toml")
    return {
        root / "requirements.txt": render(_RUNTIME_HEADER, runtime),
        root / "requirements-dev.txt": render(_DEV_HEADER, development),
    }


def imported_modules(root: Path) -> set[str]:
    """Return the top-level module of every import in a repository's sources.

    Parsed rather than pattern-matched. A regex over source lines also matches
    prose: a docstring line beginning "from the artifact alone" reads as an
    import of a package named "the", and the parser knows the difference.

    Args:
        root (Path): The repository root.

    Returns:
        set: The top-level module names imported anywhere under the root.
    """
    found: set[str] = set()
    for source in root.rglob("*.py"):
        if any(part in _SKIPPED_TREES for part in source.parts):
            continue
        for node in ast.walk(ast.parse(source.read_text(encoding=_ENCODING))):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return found


def undeclared_imports(
    root: Path, *, first_party: frozenset[str], aliases: dict[str, str]
) -> set[str]:
    """Report every third-party package the code imports and nothing declares.

    Such a dependency passes on the machine that happens to have it and fails
    on every other, which makes the failure a property of the environment
    rather than of the change that introduced it.

    Args:
        root (Path): The repository root.
        first_party (frozenset): Top-level modules this repository owns, which
            are not dependencies and are never declared.
        aliases (dict): Import name to the distribution providing it, for the
            cases where the two differ. A mapping a check has to state rather
            than infer: ``yaml`` comes from ``pyyaml``, and the import name is
            not derivable from the distribution name in either direction.

    Returns:
        set: The normalized distribution names that are imported and undeclared.
    """
    runtime, development = read_declaration(root / "pyproject.toml")
    declared = declared_names(runtime + development)
    third_party = {
        aliases.get(name, name)
        for name in imported_modules(root)
        if name not in sys.stdlib_module_names and name not in first_party
    }
    return third_party - declared
