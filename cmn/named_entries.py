# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Reading a named test list, from ``--tests`` or ``--tests-file``, into case identifiers.

Created: 2026-11-19
Last updated: 2026-11-19

This file contains ``requested_entries``, which reads the entries a run named
from whichever flag supplied them and refuses a malformed one, and
``entry_identifiers``, which reduces each entry to its case identifier.

``cmn.selection`` calls both at collection: ``select_named_tests`` to resolve
the list against the collected cases, and ``deselect_unrequested_audits`` to
tell whether a mutation audit was named. A refusal here stops the run before
anything is selected.

Split from ``cmn/selection.py`` on 2026-11-19, when running a named case alone
took that module past the nine-hundred-line runway.

Specified by ``docs/design/cmn_verdict_and_cli.md`` section 7.8.1.
"""

import re
from pathlib import Path
from typing import Final

from cmn.pytest_support import case_identifier

# WHAT A --tests-file ENTRY MAY CONTAIN. A test identifier is digits and a test
# callable's name is word characters, so anything else is a format error:
# punctuation in a line means a pasted list, a sentence, or a pytest nodeid,
# and none of the three is a name this resolves. Design section 7.8.1.1.
_ENTRY_CHARACTERS: Final[re.Pattern] = re.compile(r"^[A-Za-z0-9_]+$")


def requested_entries(inline: str, named_file: str) -> tuple[list[str], bool]:
    """Return the entries a run asked for, from whichever flag supplied them.

    **The two flags take different separators, each natural to its medium.** A
    command line has no newlines, so ``--tests`` is comma separated.
    ``--tests-file`` takes **one entry per line**, so a thousand tests are a
    thousand lines: the line count is the test count, and a diff shows one line
    per change.

    A comma inside a file line is refused rather than split. Accepting it would
    cost the property the format exists for, and treating the line as one entry
    would report a missing test for a name that was never one.

    **Every other punctuation mark is refused too.** A test identifier is
    digits and a test callable's name is word characters, so a period, an
    exclamation mark, a semicolon or a colon in a line means a pasted list, a
    sentence or a pytest nodeid. None resolves to a case, and each would
    otherwise be reported as a test that was not found, which says the wrong
    thing: the entry is malformed rather than missing.

    Design: ``cmn_verdict_and_cli.md`` section 7.8.1.

    Args:
        inline (str): The ``--tests`` value.
        named_file (str): The ``--tests-file`` value.

    Returns:
        tuple: The entries, in the order given with blank lines and ``#``
        comments dropped, and whether they came from a file. **The source
        decides what an unresolvable entry costs**: a hand-typed list is short
        and was typed seconds ago, while a curated file is long and one typo in
        it must not void the rest. Section 7.8.3.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when both flags are given,
            when the named file is absent, when nothing yields an entry, or
            when a file line carries a comma or any other punctuation. A
            malformed line is refused where a missing test is skipped, because
            the two say different things and take different corrections.
    """
    if inline and named_file:
        raise ValueError(
            "QC_HARNESS_PARSER_ERROR: --tests and --tests-file were both "
            "given, and they disagree about what an unresolvable entry costs. "
            "Name one source"
        )

    from_file = bool(named_file)
    if from_file:
        source = Path(named_file)
        if not source.is_file():
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: --tests-file names {source} and it "
                f"does not exist, so the selection would run nothing"
            )
        raw = source.read_text(encoding="utf-8")
    else:
        raw = inline

    entries: list[str] = []
    for number, line in enumerate(raw.splitlines(), start=1):
        without_comment = line.split("#", 1)[0].strip()
        if not without_comment:
            continue
        if from_file:
            if "," in without_comment:
                raise ValueError(
                    f"QC_HARNESS_PARSER_ERROR: --tests-file line {number} "
                    f"carries a comma. A file takes one entry per line, so "
                    f"the line count is the test count"
                )
            if _ENTRY_CHARACTERS.match(without_comment) is None:
                offending = sorted({
                    character for character in without_comment
                    if not (character.isalnum() or character == "_")
                })
                raise ValueError(
                    f"QC_HARNESS_PARSER_ERROR: --tests-file line {number} "
                    f"carries {' '.join(repr(found) for found in offending)}, "
                    f"which a test identifier or name cannot contain. One "
                    f"identifier or one test name per line"
                )
            entries.append(without_comment)
        else:
            entries.extend(
                part.strip() for part in without_comment.split(",") if part.strip()
            )

    if not entries:
        raise ValueError(
            "QC_HARNESS_PARSER_ERROR: the named test selection yielded no "
            "entries, so it would run nothing and report green"
        )
    return entries, from_file


def entry_identifiers(entries: list[str]) -> dict[str, str]:
    """Return each entry's case identifier, keyed by identifier.

    **Both spellings reduce to the same handle.** An entry is a bare number or
    a full test callable name, and the number is what resolution uses: a
    behaviour suffix changes when the behaviour is reworded, and a list that
    broke on a rename is one nobody maintains.

    Design: ``cmn_verdict_and_cli.md`` section 7.8.1.

    Args:
        entries (list[str]): The entries a run named.

    Returns:
        dict[str, str]: Identifier to the entry that named it, so a message can
        quote what the caller wrote rather than what it resolved to.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when an entry carries no
            identifier at all. That is distinguished from an entry naming a
            test the suite lacks, because the two take different corrections.
    """
    wanted: dict[str, str] = {}
    unresolvable: list[str] = []
    for entry in entries:
        found = entry if entry.isdigit() else case_identifier(entry)
        if found is None:
            unresolvable.append(entry)
        else:
            wanted[found] = entry

    if unresolvable:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: --tests names {', '.join(unresolvable)}, "
            f"which carry no case identifier. Name a case by its number or by "
            f"its full test name"
        )
    return wanted
