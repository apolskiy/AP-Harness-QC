# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Citations between documents, and whether each one resolves.

The designs cite each other roughly two hundred times, because a citation is how
this project avoids restating a decision in two places. **A citation that
resolves to nothing is worse than a restatement**: the reader is sent somewhere
and finds nothing there.

Two failures, and the second is the worse one:

* **Dangling.** Four documents cited sections of ``harness_open_questions.md``
  that no longer exist. The reader knows they found nothing.
* **Duplicate.** ``tier2_execution.md`` numbered two sections ``7.8``, and two
  requirements cited that number for different specifications. Both resolve, so
  nothing reports it and the reader is simply misinformed.

Specified by ``.claude/rules/code-style.md`` section 7.3.
"""

import logging
import re
from pathlib import Path
from typing import Final, Iterable

logger = logging.getLogger(__name__)

_ENCODING: Final[str] = "utf-8"

# A HEADING'S NUMBER. Markdown heading, then a number like `7.13.2` or `2A`,
# then whitespace before the title. The number is the citable part.
#
# THE TRAILING PERIOD IS OPTIONAL AND OUTSIDE THE GROUP. A top-level heading in
# this project is written `## 8. The credential boundary` and a nested one
# `#### 7.13.2 A recording without a request`, so a pattern demanding
# whitespace straight after the number misses every top-level section and
# reports each citation of one as dangling. The first draft did exactly that:
# 91 of 97 reports were false, which would have buried the 6 real ones.
_HEADING: Final[re.Pattern] = re.compile(
    r"^#{1,6}\s+(\d+(?:\.\d+)*[A-Z]?)\.?\s", re.MULTILINE
)

# A CITATION. A markdown document's name, optionally in backticks, then
# `section` or `sections`, then one or more numbers joined by `and` or a comma.
_CITATION: Final[re.Pattern] = re.compile(
    r"`?([A-Za-z0-9_\-]+\.md)`?\s+sections?\s+"
    r"(\d+(?:\.\d+)*[A-Z]?(?:\s*(?:,|and)\s*\d+(?:\.\d+)*[A-Z]?)*)"
)

_NUMBER: Final[re.Pattern] = re.compile(r"\d+(?:\.\d+)*[A-Z]?")

# RECORDS OF WHAT WAS TRUE WHEN WRITTEN. A progress log cites the sections that
# existed then, and rewriting it to agree with a later correction is the one
# thing it must not do.
_HISTORICAL: Final[frozenset[str]] = frozenset({"CLAUDE_LOG.md", "CHANGELOG.md"})


def _citing_documents(root: Path) -> list[Path]:
    """Return the documents whose citations are checked.

    **`.claude/logs/` is excluded and that is not an optimisation.** It holds
    the untracked prompt log, which must not reach a published artifact: a
    check that reported a citation from it would quote its content into CI
    output. Nothing under that directory is read.

    Args:
        root (Path): The repository root.

    Returns:
        list[Path]: Markdown under ``docs/`` and ``.claude/``, plus the root's
        own documents, excluding the historical records and the logs.
    """
    found: list[Path] = []
    for folder in ("docs", ".claude"):
        found.extend(sorted((root / folder).rglob("*.md")))
    found.extend(sorted(root.glob("*.md")))
    return [
        path for path in found
        if path.name not in _HISTORICAL
        and ".git" not in path.parts
        and "logs" not in path.parts
    ]


def document_sections(path: Path) -> list[str]:
    """Return every section number this document numbers, in order.

    **With repeats**, because a repeat is the finding rather than something to
    collapse away.

    Args:
        path (Path): The document.

    Returns:
        list[str]: The numbers, as written.
    """
    try:
        text = path.read_text(encoding=_ENCODING)
    except (OSError, UnicodeDecodeError):
        logger.warning("%s could not be read for its headings", path)
        return []
    return _HEADING.findall(text)


def duplicate_sections(root: Path) -> list[str]:
    """Report every document numbering one section more than once.

    **The duplicate is the worse of the two failures.** A dangling citation
    sends a reader nowhere and they know it; a duplicate resolves, so nothing
    reports it and two citations of one number mean different things.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per document, naming the repeated numbers. Empty
        where every section is numbered once.
    """
    problems: list[str] = []
    for path in _citing_documents(root):
        numbers = document_sections(path)
        repeated = sorted({
            number for number in numbers if numbers.count(number) > 1
        })
        if repeated:
            problems.append(
                f"{path.relative_to(root).as_posix()} numbers "
                f"{', '.join(repeated)} more than once"
            )
    return problems


def _targets(root: Path) -> dict[str, Path]:
    """Return every markdown document in this repository, by file name.

    Args:
        root (Path): The repository root.

    Returns:
        dict[str, Path]: File name to its path. A name appearing twice maps to
        the first found, which is reported by the duplicate-document check
        rather than here.
    """
    found: dict[str, Path] = {}
    for path in sorted(root.rglob("*.md")):
        if ".git" in path.parts or ".venv" in path.parts or "build" in path.parts:
            continue
        found.setdefault(path.name, path)
    return found


def citations_in(path: Path) -> list[tuple[str, str]]:
    """Return every document and section this one cites.

    **A line carrying strikethrough is skipped.** A retired inventory row cites
    what it named when it was live, which is the record this project keeps
    deliberately.

    Args:
        path (Path): The document to read.

    Returns:
        list[tuple]: Each cited document name paired with one section number.
        A citation naming several sections yields one entry per number.
    """
    try:
        text = path.read_text(encoding=_ENCODING)
    except (OSError, UnicodeDecodeError):
        return []
    found: list[tuple[str, str]] = []
    for line in text.splitlines():
        if "~~" in line:
            continue
        for document, numbers in _CITATION.findall(line):
            for number in _NUMBER.findall(numbers):
                found.append((document, number))
    return found


def unresolved_citations(root: Path, owned: Iterable[str] = ()) -> list[str]:
    """Report every citation whose target is here and whose section is not.

    **Only a target this repository holds is checked.** A citation naming the
    other repository's document cannot be resolved from here, because the
    harness owns no case data and the installed wheel ships no tests. The
    cross-repository half declares the ``paired`` environment scope and is
    deselected where the sibling is absent (``code-style.md`` section 7.3).

    Args:
        root (Path): The repository root.
        owned (Iterable[str]): Extra document names to treat as resolvable,
            used by the paired caller to pass the sibling's documents.

    Returns:
        list[str]: One entry per unresolved citation, naming the citing
        document, the target and the section. Empty where every citation
        resolves.
    """
    targets = _targets(root)
    sections = {name: set(document_sections(path)) for name, path in targets.items()}
    extra = frozenset(owned)
    problems: list[str] = []
    for path in _citing_documents(root):
        where = path.relative_to(root).as_posix()
        for document, number in citations_in(path):
            if document not in targets or document in extra:
                # NOT OURS TO RESOLVE. Reported by the paired caller instead.
                continue
            if number not in sections[document]:
                problems.append(
                    f"{where} cites {document} section {number}, "
                    f"which that document does not number"
                )
    return sorted(set(problems))
