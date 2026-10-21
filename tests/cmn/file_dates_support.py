# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Support code for the file date case, the planted modules and scratch git history it reads.

Created: 2026-10-21
Last updated: 2026-10-21

This file contains ``planted_module``, which returns a small module whose
docstring carries two given date lines, and ``git_in``, which runs one git
command in a scratch repository with a fixed author and fails loudly.

It is imported by ``mqc_uni_file_dates.py`` in the ``unit`` precondition gate,
and is not collected itself, as its name carries no ``mqc_`` prefix.

Specified by ``docs/design/cmn_verdict_and_cli.md`` section 10.39.
"""

import subprocess
from pathlib import Path

HEADER = "# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy\n"


def planted_module(created: str, updated: str) -> str:
    """Return a small module whose docstring carries the two given date lines.

    Args:
        created (str): The ``Created`` value.
        updated (str): The ``Last updated`` value.

    Returns:
        str: The module source.
    """
    return (
        f'{HEADER}"""A planted module.\n\nCreated: {created}\nLast updated: {updated}\n\n'
        f'What it holds.\n"""\n\nVALUE = 1\n'
    )


def git_in(root: Path, *arguments: str) -> None:
    """Run one git command in a scratch repository, failing loudly.

    Args:
        root (Path): The scratch repository.
        *arguments (str): The git arguments.

    Returns:
        None
    """
    subprocess.run(
        ["git", "-c", "user.name=case", "-c", "user.email=case@example.invalid", *arguments],
        cwd=str(root), check=True, capture_output=True, stdin=subprocess.DEVNULL,
        timeout=60.0,
    )
