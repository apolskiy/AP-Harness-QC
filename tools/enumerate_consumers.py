# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The consumer enumerator, which resolves which ref of each consumer to verify.

Created: 2026-10-29
Last updated: 2026-10-29

This file contains ``paired_consumers``, which reads the consumer registry and
gives each entry the ref paired with the harness branch under test, and
``main``, the command line the workflow step runs.

The ``enumerate`` job of ``regress-consumers-on-merge.yml`` runs it and writes
its output to the file named by ``--output``, which the step sets to the
Actions output file. The ``verify`` job then fans out over the JSON it wrote,
one matrix leg per consumer.

Specified by ``docs/design/harness_ci_pipeline.md`` section 8.10.

**The pairing is resolved here rather than in a matrix expression.** A harness
branch with no entry falls back to the consumer's ``default_ref``, and a
workflow expression cannot express that without naming branches, which would
put a branch name in a file nobody updates when the branch is renamed.

**It was 20 lines of Python inline in the workflow until 2026-10-29.** It
decides which consumer refs a harness candidate is verified against, and
nothing linted or covered it.
"""

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Final, Optional

import yaml

logger = logging.getLogger(__name__)

_ENCODING: Final[str] = "utf-8"
_DEFAULT_REF: Final[str] = "main"

# Section 7.3 keeps the verdict codes clear of argparse, which exits 2. An
# unreadable registry is a refusal: a fan-out over an empty list verifies
# nothing and reports success.
_EXIT_ENUMERATED: Final[int] = 0
_EXIT_REFUSED: Final[int] = 4


def paired_consumers(registry_path: Path, branch: str) -> list[dict[str, Any]]:
    """Return each registered consumer with the ref paired to one harness branch.

    Args:
        registry_path (Path): The consumer registry to read.
        branch (str): The harness branch under test.

    Returns:
        list[dict]: One entry per consumer, each carrying a ``ref`` resolved
        from its own mapping, falling back to its ``default_ref`` and then to
        ``main``.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the registry is
            absent or will not parse. **Refused rather than treated as no
            consumers**: an empty fan-out verifies nothing and reads as green.
    """
    if not registry_path.is_file():
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: no consumer registry at {registry_path}"
        )
    try:
        registry = yaml.safe_load(registry_path.read_text(encoding=_ENCODING))
    except yaml.YAMLError as error:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: the registry at {registry_path} "
            f"will not parse"
        ) from error

    entries: list[dict[str, Any]] = []
    for entry in (registry or {}).get("consumers") or []:
        paired = dict(entry)
        mapping = paired.get("refs") or {}
        paired["ref"] = mapping.get(branch, paired.get("default_ref", _DEFAULT_REF))
        entries.append(paired)
    return entries


def main(argv: Optional[list[str]] = None) -> int:
    """Enumerate the consumers to verify and write the job's outputs.

    Args:
        argv (Optional[list]): Arguments, for calling in-process from a case.

    Returns:
        int: ``0`` once the registry was read, ``4`` when it could not be.
    """
    parser = argparse.ArgumentParser(
        prog="enumerate-consumers",
        description="Resolve which ref of each registered consumer to verify",
    )
    parser.add_argument("--branch", required=True, help="The harness branch under test")
    parser.add_argument("--sha", required=True, help="The harness commit under test")
    parser.add_argument(
        "--registry", default=Path("config/consumers.yaml"), type=Path,
        help="The consumer registry to read",
    )
    parser.add_argument(
        "--output", required=True, type=Path,
        help="The file to append the resolved outputs to",
    )
    parsed = parser.parse_args(argv)

    try:
        entries = paired_consumers(Path(parsed.registry), str(parsed.branch))
    except ValueError as error:
        logger.error("%s", error)
        return _EXIT_REFUSED

    # APPENDED, because the Actions output file accumulates across steps.
    # ONE LINE OF JSON, since a matrix is built with `fromJson` and a value
    # spanning lines is not readable by the expression that consumes it.
    lines = (
        f"consumers={json.dumps(entries)}\n"
        f"harness_branch={parsed.branch}\n"
        f"harness_sha={parsed.sha}\n"
    )
    with Path(parsed.output).open("a", encoding=_ENCODING, newline="\n") as handle:
        handle.write(lines)
    logger.info("enumerated %d consumer(s) against %s", len(entries), parsed.branch)
    return _EXIT_ENUMERATED


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
