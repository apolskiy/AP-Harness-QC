# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Section checks: whether a cited section exists, exactly once, and in order.

Created: 2026-10-12
Last updated: 2026-10-22

This file contains ``live_documents``, the documents that describe the
repository as it is now rather than as it was; ``numbered_headings``, every
numbered heading a document carries with its line, and ``document_sections``,
the numbers alone;
``duplicate_sections``, which reports a document numbering one section twice;
``citations_in``, the document and section pairs a document cites;
``unresolved_citations``, which reports a citation whose target document is in
the repository and whose section is not; and ``section_key`` with
``disordered_sections``, which report a heading sorting at or before the
heading above it.

Precondition cases in both repositories call these with their own root, so a
dangling citation, an ambiguous one or a section out of order fails the unit
layer.

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
* **Out of order.** ``harness_ci_pipeline.md`` placed section 8.3 after 8.4.
  The citation resolves and the number is unique, so a reader is sent to the
  right section and has to scroll for it.

Specified by ``.claude/rules/code-style.md`` sections 7.3 and 7.5.
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
#
# EVERY SEGMENT MAY CARRY A LETTER, since 2026-10-15. `5A.3` was read as `5A`
# followed by text, so it was no section at all: two such headings in one
# document went unreported and a citation of one resolved to its parent.
_SEGMENTS: Final[str] = r"\d+[A-Z]?(?:\.\d+[A-Z]?)*"

# A BARE NUMBER IS A SECTION ONLY WHERE IT CARRIES A PERIOD, since 2026-10-21.
# A top-level heading in this project is written `## 8. The credential
# boundary`, and the period is the whole of what distinguishes it from a
# heading that opens with a number: `##### 429 is the one that is nobody's
# defect` is prose about an HTTP status. Both repositories hold four such
# headings, an HTTP status, two counts and a case identifier, and a pattern
# admitting them reads a document as numbering sections 429 and 107.
#
# A DOTTED NUMBER NEEDS NO PERIOD, because nothing else is shaped like one.
# Its trailing period stays optional and outside the group, so a section is
# returned as `7.13.2` whether or not the heading wrote `7.13.2.`.
_DOTTED: Final[str] = r"\d+[A-Z]?(?:\.\d+[A-Z]?)+"
_TOP: Final[str] = r"\d+[A-Z]?"
_HEADING: Final[re.Pattern] = re.compile(
    rf"^#{{1,6}}\s+(?:({_DOTTED})\.?|({_TOP})\.)\s", re.MULTILINE
)

# A FENCED BLOCK HOLDS NO HEADINGS. A document showing a heading as an example
# carries a line shaped exactly like a section of itself, which the period rule
# above cannot separate: the example is a section number.
#
# THE GENERATED CASE LIST IS NOT THE REASON, although it looks like it. Every
# test module opens those lines with a hash and a six-digit identifier and
# `testing-standards.md` quotes one, but a bare number carries no period, so
# the rule above already excludes them. An injection removing this fence
# handling went NOT CAUGHT on 2026-10-22 because the case asserted the case
# list and not an example heading. Design `code-style.md` section 7.5.1.
_FENCE: Final[re.Pattern] = re.compile(r"^\s*(?:```|~~~)")

# A CITATION. A markdown document's name, optionally in backticks, then
# `section` or `sections`, then one or more numbers joined by `and` or a comma.
_CITATION: Final[re.Pattern] = re.compile(
    r"`?([A-Za-z0-9_\-]+\.md)`?\s+sections?\s+"
    rf"({_SEGMENTS}(?:\s*(?:,|and)\s*{_SEGMENTS})*)"
)

_NUMBER: Final[re.Pattern] = re.compile(_SEGMENTS)

# RECORDS OF WHAT WAS TRUE WHEN WRITTEN. A progress log cites the sections that
# existed then, and rewriting it to agree with a later correction is the one
# thing it must not do.
_HISTORICAL: Final[frozenset[str]] = frozenset({"CLAUDE_LOG.md", "CHANGELOG.md"})


def live_documents(root: Path) -> list[Path]:
    """Return the documents that describe the repository as it is now.

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


def unfenced_lines(text: str) -> list[str]:
    """Return the document's lines with every fenced line blanked.

    **Blanked rather than removed, and returned as lines rather than joined**,
    so the nth entry is the nth line of the file. Joining and splitting again
    loses a trailing empty line, which is a line number that no longer matches
    the file for every caller that counts.

    Args:
        text (str): The document's text.

    Returns:
        list[str]: One entry per line, empty for a fence and for each line
        inside one.
    """
    kept: list[str] = []
    fenced = False
    for line in text.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
            kept.append("")
            continue
        kept.append("" if fenced else line)
    return kept


def numbered_headings(path: Path) -> list[tuple[int, str]]:
    """Return every numbered heading this document carries, with its line.

    Args:
        path (Path): The document.

    Returns:
        list[tuple]: Each heading's one-based line number paired with its
        section number, in the order they appear.
    """
    try:
        text = path.read_text(encoding=_ENCODING)
    except (OSError, UnicodeDecodeError):
        logger.warning("%s could not be read for its headings", path)
        return []
    found: list[tuple[int, str]] = []
    for lineno, line in enumerate(unfenced_lines(text), start=1):
        matched = _HEADING.match(line + "\n")
        if matched is not None:
            found.append((lineno, matched.group(1) or matched.group(2)))
    return found


def document_sections(path: Path) -> list[str]:
    """Return every section number this document numbers, in order.

    **With repeats**, because a repeat is the finding rather than something to
    collapse away.

    Args:
        path (Path): The document.

    Returns:
        list[str]: The numbers, as written, without a trailing period.
    """
    return [number for _, number in numbered_headings(path)]


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
    for path in live_documents(root):
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
    for path in live_documents(root):
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


# ONE COMPONENT OF A SECTION NUMBER, a count and an optional letter.
_COMPONENT: Final[re.Pattern] = re.compile(r"^(\d+)([A-Z]?)$")


def section_key(number: str) -> tuple[tuple[int, str], ...]:
    """Return the sort key for a section number, component by component.

    A letter sorts after the digit it follows, so the order is 5, 5.1, 5.3.1,
    5A, 5A.1, 5B, 6. A lettered section is a sibling inserted after the fact
    and its subsections belong with it rather than among its neighbour's.

    Args:
        number (str): A section number, as :func:`numbered_headings` returns
            it.

    Returns:
        tuple: One pair per component, the count then the letter. Empty for a
        number no heading pattern produces, which sorts before every real one.
    """
    parts: list[tuple[int, str]] = []
    for component in number.split("."):
        matched = _COMPONENT.match(component)
        if matched is None:
            return ()
        parts.append((int(matched.group(1)), matched.group(2)))
    return tuple(parts)


def disordered_sections(root: Path) -> list[str]:
    """Report every numbered heading sorting at or before the one above it.

    **Section 7.3 makes a citation resolve and says nothing about where the
    section sits.** A reader sent to section 8.3 found it after 8.4, which no
    check saw because the number existed, once.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per heading out of order, naming the document, the
        line and both numbers. Empty where every document ascends.

    Design: ``.claude/rules/code-style.md`` section 7.5.
    """
    problems: list[str] = []
    for path in live_documents(root):
        where = path.relative_to(root).as_posix()
        headings = numbered_headings(path)
        for index in range(1, len(headings)):
            lineno, number = headings[index]
            previous = headings[index - 1][1]
            if section_key(number) <= section_key(previous):
                problems.append(
                    f"{where} line {lineno} numbers {number} "
                    f"after {previous}"
                )
    return problems
