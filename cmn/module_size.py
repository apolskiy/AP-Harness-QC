# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""When a module is close enough to the ceiling that the next addition splits it.

Specified by ``.claude/rules/code-style.md`` section 5.1.

**The hard ceiling is a thousand lines and pylint enforces it.** The problem
with a hard limit alone is when it fires: twice on 2026-10-05 a module sat at
995 and 998 lines, so an unrelated prose edit would have failed the build, and
once a single new case took one to 1024 and had to be split in the middle of
another change.

**A ceiling nobody can plan around is a ceiling that fires at the worst
moment.** This reports a module at nine hundred lines or more, which is where
the next subject belongs in a module of its own.

**Its own module, which is the rule applying to itself.** ``code_standards.py``
stood at 892 lines when this was written, so adding a third reader to it would
have been the drift this exists to prevent.
"""

import logging
from datetime import date
from pathlib import Path
from typing import Final

from cmn.declared_gaps import declared_entries, lapsed_problems

logger = logging.getLogger(__name__)

# NINE HUNDRED, A HUNDRED SHORT OF THE HARD LIMIT. The margin is deliberate
# and it is not a runway for more cases: it is room for the prose, comments and
# docstrings an ordinary edit adds, so crossing the hard limit is always a
# decision rather than an accident.
RUNWAY_CEILING: Final[int] = 900

# TREES THAT ARE NOT OURS.
_SKIPPED: Final[frozenset[str]] = frozenset({
    ".venv", "build", "__pycache__", ".git", "node_modules",
})


def oversized_modules(root: Path) -> dict[str, int]:
    """Return every tracked module at the runway ceiling or beyond.

    Args:
        root (Path): The repository root.

    Returns:
        dict[str, int]: Repository-relative posix path to its line count, for
        modules of ``RUNWAY_CEILING`` lines or more.
    """
    found: dict[str, int] = {}
    for module in sorted(root.rglob("*.py")):
        if any(part in _SKIPPED for part in module.parts):
            continue
        lines = len(module.read_text(encoding="utf-8").splitlines())
        if lines >= RUNWAY_CEILING:
            found[module.relative_to(root).as_posix()] = lines
    return found


def runway_problems(root: Path, registry: Path, as_of: date) -> list[str]:
    """Report a module past the runway ceiling that nothing declares.

    Three directions, each catching a different failure:

    * a module at the ceiling with no entry is one whose next addition will
      fire the hard limit on somebody else's change,
    * a declared entry past its expiry is a split that stopped,
    * a declared entry whose module is back under the ceiling is a closed gap
      still listed.

    Args:
        root (Path): The repository root.
        registry (Path): The declaration of modules past the ceiling.
        as_of (date): The date expiries are judged against, injected so the
            check is not a function of when it runs.

    Returns:
        list[str]: One message per problem, empty when the rule holds.
    """
    oversized = oversized_modules(root)
    declared = declared_entries(registry, "past_the_runway")
    problems: list[str] = []

    for path, lines in sorted(oversized.items()):
        record = declared.get(path)
        if record is None:
            problems.append(
                f"{path} is {lines} lines, at or past the {RUNWAY_CEILING} "
                f"line runway ceiling, and nothing declares it. The next "
                f"subject added here belongs in a module of its own, named for "
                f"that subject; declare it with a reason and an expiry, or "
                f"split it"
            )
            continue
        problems.extend(
            lapsed_problems(
                f"{path} at {lines} lines", record, as_of,
                "past the runway ceiling",
            )
        )

    for path in sorted(set(declared) - set(oversized)):
        problems.append(
            f"{path} is declared as past the runway ceiling and is now under "
            f"{RUNWAY_CEILING} lines, so the entry outlived the work. Remove it"
        )
    return problems
