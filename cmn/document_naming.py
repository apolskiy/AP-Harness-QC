# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Whether a document's filename says which repository it belongs to.

Specified in ``.claude/rules/code-style.md`` section 7.2.

**An editor tab shows a filename rather than a checkout.** Two repositories
held a ``docs/running_jobs.md`` and a ``docs/document_register.md`` each, and a
change made in the wrong one parses, lints and commits: the mistake surfaces
later as a procedure that stopped matching the workflows it dispatches.

**A name already unambiguous needs nothing added.** The rule is satisfied by a
name being unmistakable, not by a prefix for its own sake, so a document whose
subject exists in one repository only passes on its own terms.
"""

import logging
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

# Conventional names a tool or a reader expects at a repository root. Renaming
# any of these hides it, and each is seen beside its checkout's name anyway.
_ROOT_CONVENTIONS: Final[frozenset[str]] = frozenset({
    "README.md", "DESIGN.md", "CHANGELOG.md", "CLAUDE.md", "CLAUDE_LOG.md",
    "LICENSE", "NOTICE",
})

# Trees whose contents are not this repository's tracked prose.
_SKIPPED_TREES: Final[frozenset[str]] = frozenset({
    ".git", "build", "__pycache__", ".venv", "node_modules", ".pytest_cache",
    "reports", "allure-results", "htmlcov", ".mypy_cache", ".ruff_cache",
})


def repository_token(root: Path) -> str:
    """Return the token a repository's document names carry.

    **Derived from the directory name rather than configured**, because a
    configured value is a second place for the answer to live and the
    repository already states it: ``AP-Harness-QC`` yields ``harness``.

    Args:
        root (Path): The repository root.

    Returns:
        str: The lowercase token, or an empty string where the directory name
        carries no recognisable one.
    """
    name = root.resolve().name.lower()
    for candidate in ("harness", "model"):
        if candidate in name:
            return candidate
    return ""


def documents_under(root: Path, folder: str = "docs") -> list[Path]:
    """Return every tracked markdown document beneath one folder.

    Args:
        root (Path): The repository root.
        folder (str): Which folder to read, ``docs`` by default.

    Returns:
        list[Path]: Each document, sorted, excluding generated trees.
    """
    base = root / folder
    if not base.is_dir():
        return []
    return sorted(
        path for path in base.rglob("*.md")
        if not _SKIPPED_TREES & set(path.parts)
    )


def undifferentiated_documents(
    root: Path, exempt: frozenset[str] = frozenset()
) -> list[str]:
    """Report every document under ``docs`` whose name names no repository.

    **The check is the filename, not the content.** A reader with a file open
    sees the name, and that is the whole failure this guards: a change made in
    the wrong repository because two checkouts offered the same name.

    Design: ``.claude/rules/code-style.md`` section 7.2.

    Args:
        root (Path): The repository root.
        exempt (frozenset[str]): Document names exempt beyond the root
            conventions, each a deliberate decision rather than an oversight.
            **Passed rather than inferred**, so an exemption is visible in the
            case that grants it.

    Returns:
        list[str]: One entry per document, naming it and the token it lacks.
        An empty list means every name says where it belongs.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the root's own name
            carries no recognisable token. Reporting every document as
            undifferentiated would be a wall of findings about one cause, and
            reporting none would pass a repository nobody could name.
    """
    token = repository_token(root)
    if not token:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: {root.resolve().name!r} carries no "
            f"repository token, so no document name can be checked against one"
        )

    problems: list[str] = []
    for path in documents_under(root):
        name = path.name
        if name in _ROOT_CONVENTIONS or name in exempt:
            continue
        if token in name.lower():
            continue
        problems.append(
            f"{path.relative_to(root).as_posix()} carries no {token!r}, so an "
            f"open editor tab does not say which repository it belongs to"
        )
    if problems:
        logger.warning(
            "%d document name(s) do not say which repository they belong to",
            len(problems),
        )
    return problems


def root_conventions() -> frozenset[str]:
    """Return the filenames exempt by convention at a repository root.

    Returns:
        frozenset[str]: The exempt names, pinned so growth is deliberate: each
        addition is one more file whose name says nothing about its checkout.
    """
    return _ROOT_CONVENTIONS
