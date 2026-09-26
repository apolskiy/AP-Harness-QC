# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Generate the requirements files from the single declaration in pyproject.

Specified by ``DESIGN.md`` section 5.0.1.

**`pyproject.toml` is the declaration; these files are derived.** Tooling
expects a requirements file, and PyCharm in particular offers to install from
one and does not read an optional-dependency extra. A contributor opening the
project should not have to know which of two conventions this repository chose.

**They are never hand-edited.** ``MQC_CMN_UNI_11108`` fails the run when they
disagree with the declaration, which is the same rule applied everywhere else
here: two statements of one fact drift, so either there is one statement or
there is a check. A generated file plus a check is the second form rather than
an exception to the rule.

Run it with ``python tools/generate_requirements.py`` after changing a
dependency. The check tells you when you have forgotten.
"""

import sys
import tomllib
from pathlib import Path
from typing import Final

_ENCODING: Final[str] = "utf-8"

_RUNTIME_HEADER: Final[str] = """\
# GENERATED FROM pyproject.toml. Do not edit by hand.
#
# Regenerate with:  python tools/generate_requirements.py
# Checked by:       MQC_CMN_UNI_11108
#
# pyproject.toml is the single declaration (DESIGN.md section 5.0.1). This file
# exists because tooling expects it, not because it is a second source of truth.
#
# Ranges, not pins. An unpinned harness measures a moving target: a parser
# upgrade that changes how a sentence is counted would read as a model
# regression, which is the attribution failure this project exists to avoid.
# Ranges allow patch releases and nothing wider.
"""

_DEV_HEADER: Final[str] = """\
# GENERATED FROM pyproject.toml. Do not edit by hand.
#
# Regenerate with:  python tools/generate_requirements.py
# Checked by:       MQC_CMN_UNI_11108
#
# Everything the seven CI gates need, on top of the runtime dependencies.
# This is what `pip install --editable ".[dev]"` installs, and what CI uses.

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


def render(header: str, requirements: list[str]) -> str:
    """Render one requirements file.

    Args:
        header (str): The generated-file notice.
        requirements (list): The requirement specifiers.

    Returns:
        str: The file contents, newline terminated.
    """
    return header + "\n" + "\n".join(requirements) + "\n"


def generate(root: Path) -> dict[Path, str]:
    """Return the contents each generated file should have.

    Returning the contents rather than writing them is what lets the check
    compare without a temporary directory, and what lets this module be called
    from a test without a side effect.

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


def main() -> int:
    """Write the generated files.

    Returns:
        int: Zero on success.
    """
    root = Path(__file__).resolve().parents[1]
    for path, contents in generate(root).items():
        path.write_text(contents, encoding=_ENCODING, newline="\n")
        print(f"wrote {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
