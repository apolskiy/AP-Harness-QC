# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""A nested pytest session wired by the caller, for cases that read real reports.

Created: 2026-11-06
Last updated: 2026-11-06

This file contains ``run_wired_session``, which writes a conftest and a case
module into a directory and runs pytest over them in a subprocess, returning
the finished process, and ``unwired_conftests``, which names what either
repository's conftest lacks of the passw wiring. The cases in
``mqc_uni_broken.py`` and ``mqc_uni_passw.py`` use them to run real pytest
reports through the hooks both repositories wire, rather than imitations of them.
"""

import subprocess
import sys
from pathlib import Path
from typing import Final

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

# A CONFIG FILE OF ITS OWN, carrying no discovery keys, so the wired session
# takes pytest's defaults and collects `test_` names rather than this
# repository's `MQC_` overrides. The flag it is passed to selects a *config
# file*: it was once given `conftest.py`, which pytest 9.1 accepted as a file
# holding no configuration and 9.2 refuses by extension, so a session that was
# isolated by accident is now isolated by declaration.
_SESSION_INI: Final[str] = "[pytest]\n"


def run_wired_session(
    directory: Path, conftest: str, cases: str, *, extra: tuple[str, ...] = ()
) -> subprocess.CompletedProcess[str]:
    """Write a wired conftest and its cases, and run pytest over them.

    Args:
        directory (Path): Where the session is written, usually ``tmp_path``.
        conftest (str): The conftest source, wiring the hooks under test.
        cases (str): The case module source, using pytest's default names.
        extra (tuple): Further pytest arguments, such as ``--junitxml``.

    Returns:
        subprocess.CompletedProcess: The finished run, its output captured as
        text. Run from the repository root, so the session imports this
        checkout's ``cmn``.
    """
    (directory / "conftest.py").write_text(conftest, encoding="utf-8")
    (directory / "test_sample.py").write_text(cases, encoding="utf-8")
    (directory / "pytest.ini").write_text(_SESSION_INI, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:randomly", "-p", "no:cacheprovider",
         "--rootdir", str(directory), "-c", str(directory / "pytest.ini"), *extra,
         str(directory)],
        cwd=REPOSITORY_ROOT, capture_output=True, text=True, check=False, timeout=120,
        stdin=subprocess.DEVNULL,
    )


def unwired_conftests() -> list[str]:
    """Return what each repository's conftest lacks of the passw wiring.

    Returns:
        list[str]: One line per conftest and missing call, empty when both are wired.
    """
    return [
        f"{conftest} lacks {wired}"
        for conftest in (REPOSITORY_ROOT / "conftest.py",
                         REPOSITORY_ROOT.parent / "AP-Model-QC" / "conftest.py")
        if conftest.is_file()
        for wired in ("mark_passw(outcome.get_result(), item)", "passw_count(", "passw=")
        if wired not in conftest.read_text(encoding="utf-8")
    ]
