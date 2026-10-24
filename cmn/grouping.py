# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The grouping tree a readiness view is read from: epic, feature and story.

Created: 2026-10-24
Last updated: 2026-10-24

This file contains ``Grouping``, the declaration a repository publishes under;
``load_grouping``, which reads it from ``config/allure_features.yaml``;
``story_for``, which names a scenario from a test class; ``story``, the marker
a case names its own scenario with; ``grouping_problems``, which reports a
collected module declaring no capability, a capability spelled outside the
vocabulary, an entry naming no module, and a declared epic that is not the
distribution's own name; and ``reporter_import_problems``, which reports any
module importing Allure outside the one boundary allowed to.

The collection hook in ``cmn/pytest_support.py`` reads these and labels every
item, so the three grouping labels arrive derived rather than typed on a class.
The checks here run in the unit layer, before anything is generated: a module
nobody mapped would otherwise publish its results under no capability at all,
and the only way to find that out is to read a report.

**Nothing here calls into Allure.** The declaration is read, the names are
computed, and the hook does the labelling, which is the division
``cmn/reporting.py`` already keeps: a function that called into a reporter
could only be tested by running one.

Design: ``docs/design/harness_test_taxonomy.md`` section 16.
"""

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest
import yaml

from cmn.case_summary import case_modules, cases_in
from cmn.document_naming import project_name

# WHERE THE DECLARATION LIVES, in each repository that runs cases. Both
# declare their own, because the epic is what tells a collector reading two
# result sets which repository produced one (section 16.5).
DECLARATION: Final[str] = "config/allure_features.yaml"

# THE PREFIX EVERY TEST CLASS CARRIES, which says nothing about the scenario
# and comes off before the name is read. `pytest.ini` collects
# `python_classes = TestMQC*`, so this is the whole of the constant part.
_CLASS_PREFIX: Final[str] = "TestMQC"

# A RUN OF CAPITALS STAYS WHOLE, so `TestMQCCLIOptions` reads as "CLI options"
# rather than as four initials. The first alternative takes capitals not
# followed by a lowercase letter, which is an acronym; the second takes one
# capital and the word after it.
_WORDS: Final[re.Pattern[str]] = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*")


@dataclass(frozen=True)
class Grouping:
    """What a repository publishes its results under.

    Args:
        epic (str): The repository, as every result's epic label.
        features (frozenset): The declared vocabulary of capability names.
        modules (dict): Each collected test module, by its path relative to
            the root, mapped to the one capability it tests.
    """

    epic: str
    features: frozenset[str]
    modules: dict[str, str]


def load_grouping(root: Path) -> Grouping:
    """Return the declaration a repository publishes under.

    **An absent or malformed file yields an empty declaration rather than
    raising**, because the caller's own report is the better message: a
    collection hook that raised here would refuse the whole run over a
    reporting label, and :func:`grouping_problems` names what is missing.

    Args:
        root (Path): The repository root.

    Returns:
        Grouping: The declaration, empty where there is nothing to read.
    """
    path = root / DECLARATION
    if not path.is_file():
        return Grouping(epic="", features=frozenset(), modules={})
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return Grouping(epic="", features=frozenset(), modules={})
    if not isinstance(loaded, dict):
        return Grouping(epic="", features=frozenset(), modules={})
    declared = loaded.get("modules") or {}
    return Grouping(
        epic=str(loaded.get("epic") or ""),
        features=frozenset(str(name) for name in (loaded.get("features") or [])),
        modules={str(module): str(feature) for module, feature in declared.items()},
    )


def story_for(class_name: str) -> str:
    """Return the scenario a test class names.

    ``TestMQCMutationLock`` reads as ``Mutation lock``: the prefix comes off,
    the remainder splits on its capitals, the first word keeps its case and
    the rest are lowercased unless they are acronyms.

    Args:
        class_name (str): The class's own name.

    Returns:
        str: The scenario, or an empty string for a name carrying nothing
        beyond the prefix, which is a class the hook then leaves unlabelled.
    """
    remainder = class_name.removeprefix(_CLASS_PREFIX)
    words = _WORDS.findall(remainder)
    if not words:
        return ""
    spoken = [words[0]] + [
        word if word.isupper() and len(word) > 1 else word.lower() for word in words[1:]
    ]
    return " ".join(spoken)


def collected_modules(root: Path) -> list[str]:
    """Return every test module holding cases, relative to the root.

    **A module holding no case needs no capability.** The glob
    ``pytest.ini`` collects admits a module that defines none, and a
    capability for a file with nothing in it would be a branch with no leaf.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: Posix-form paths, sorted.
    """
    return [
        module.relative_to(root).as_posix()
        for module in case_modules(root)
        if cases_in(module)
    ]


def grouping_problems(root: Path) -> list[str]:
    """Report every disagreement between the declaration and the repository.

    Four kinds, in a stable order: an epic that is not the distribution's own
    name, a collected module declaring no capability, a capability outside the
    declared vocabulary, and an entry naming a module the repository does not
    hold.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One sentence per disagreement, empty where there is none.
    """
    grouping = load_grouping(root)
    problems: list[str] = []

    distribution = project_name(root)
    if not grouping.epic:
        problems.append(f"{DECLARATION} declares no epic, so no result carries one")
    elif distribution and grouping.epic.lower() != distribution:
        problems.append(
            f"{DECLARATION} declares the epic {grouping.epic!r}, which is not the "
            f"distribution name {distribution!r}, so a collector reading two "
            f"repositories cannot tell which produced a result"
        )

    for module in collected_modules(root):
        if module not in grouping.modules:
            problems.append(
                f"{module} holds cases and declares no capability in {DECLARATION}, "
                f"so its results group under nothing"
            )

    for module, feature in sorted(grouping.modules.items()):
        if feature not in grouping.features:
            problems.append(
                f"{DECLARATION} maps {module} to the capability {feature!r}, which "
                f"the declared vocabulary does not hold"
            )
        if not (root / module).is_file():
            problems.append(
                f"{DECLARATION} maps {module}, which this repository does not hold"
            )

    return problems


# THE ONE MODULE THAT MAY IMPORT THE REPORTER, which owns the stand-in used
# where it is not installed (section 16.7).
REPORTER_BOUNDARY: Final[str] = "cmn/reporter.py"

# AND THE TREES THAT ARE NOT OURS.
_SKIPPED: Final[frozenset[str]] = frozenset({
    ".venv", "build", "dist", "__pycache__", ".git", "node_modules",
})

_REPORTING_PACKAGES: Final[frozenset[str]] = frozenset({
    "allure", "allure_commons", "allure_pytest",
})


def story(name: str) -> pytest.MarkDecorator:
    """Return the marker naming one case's scenario, overriding the derived one.

    **A marker rather than ``allure.story``**, which applies this same marker
    and costs an import of a library the suite must run without. A case that
    names its own scenario therefore depends on nothing a developer might not
    have installed (section 16.7).

    Args:
        name (str): The scenario, as a reader of a report should see it.

    Returns:
        pytest.MarkDecorator: The label marker, which the grouping hook then
        leaves alone because the item already declares a story.
    """
    return pytest.mark.allure_label(name, label_type="story")


def reporter_import_problems(root: Path) -> list[str]:
    """Report every module importing the reporting library directly.

    One module may: :data:`REPORTER_BOUNDARY`, which owns the stand-in. Any
    other import of it is a module that fails to load on a machine where the
    reporting extra is absent, and a test module that fails to load takes the
    run with it.

    **Parsed, not matched**, because this project has already corrected a
    scanner that could not tell a definition from one inside a string.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per offending import, naming the module and the
        line, empty where only the boundary imports it.
    """
    problems: list[str] = []
    for source in sorted(root.rglob("*.py")):
        if _SKIPPED & set(source.parts):
            continue
        relative = source.relative_to(root).as_posix()
        if relative == REPORTER_BOUNDARY:
            continue
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            named: list[str] = []
            if isinstance(node, ast.Import):
                named = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                named = [node.module.split(".")[0]]
            for package in named:
                if package in _REPORTING_PACKAGES:
                    problems.append(
                        f"{relative} line {node.lineno} imports {package}, which is "
                        f"absent on a machine without the reporting extra, so the "
                        f"module fails to load and takes the run with it"
                    )
    return problems
