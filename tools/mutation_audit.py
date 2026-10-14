# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Change the production code and report what the suite failed to notice.

Specified in ``docs/design/harness_test_taxonomy.md`` section 15.

One operator or constant is rewritten at a time and the suite is re-run. A
change some case fails on is **killed**; a change nothing fails on is a
**survivor**, and a survivor names behaviour nothing asserts.

**A survivor is not automatically a missing case.** Some changes cannot alter
any observable result, and those are findings about the production code rather
than the tests. Section 15.3 draws that line and
``config/mutation_survivors.yaml`` records which kind each accepted entry is.

**The module is edited in place**, because it has to be importable at the path
the suite imports it from. The original is written to a sibling backup first,
so a run killed between the write and the restore is recoverable by the next
one (section 15.5).
"""

import argparse
import ast
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Optional

import yaml

logger = logging.getLogger(__name__)

# COMPARISON COUNTERPARTS. The threshold hole lived here: a boundary that drifts
# from `>` to `>=` changes which runs pass and nothing else about the code.
_COMPARE: Final[dict[type, type]] = {
    ast.Lt: ast.LtE, ast.LtE: ast.Lt,
    ast.Gt: ast.GtE, ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
    ast.In: ast.NotIn, ast.NotIn: ast.In,
    ast.Is: ast.IsNot, ast.IsNot: ast.Is,
}
_BOOL: Final[dict[type, type]] = {ast.And: ast.Or, ast.Or: ast.And}

# PYTEST EXITS 5 WHEN IT COLLECTS NOTHING, which is not zero, so a run that
# matched no path would otherwise read as a mutant the suite had killed. The
# first version of this tool reported ten of ten killed for exactly that reason.
_NOTHING_COLLECTED: Final[int] = 5

# WHERE THE REAL FILE WAITS while a mutant is in place. A kill between the write
# and the restore leaves the mutant on disk and only this says what was there.
_BACKUP_SUFFIX: Final[str] = ".mutation-backup"

# EVERY SUBPROCESS CARRIES ONE, per taxonomy section 14. The unit suite takes
# about 22 seconds, so this is a hang ceiling rather than a budget.
_RUN_TIMEOUT_SEC: Final[int] = 600

_PASSED = re.compile(r"(\d+) passed")


@dataclass(frozen=True)
class MutationPoint:
    """One change this tool knows how to make.

    Attributes:
        kind (str): Which family of change, such as ``compare``.
        node_index (int): The node's position in ``ast.walk`` order, which is
            deterministic for a given tree and is how the point is addressed in
            a freshly parsed copy.
        operator_index (int): Which operator within a comparison, zero
            elsewhere.
        lineno (int): The line the change lands on, for the report.
        label (str): What the change does, in words.
    """

    kind: str
    node_index: int
    operator_index: int
    lineno: int
    label: str

    def describe(self) -> str:
        """Return the one-line form used in a report and a declaration.

        Returns:
            str: The line number and what changed.
        """
        return f"line {self.lineno}: {self.label}"


def mutation_points(source: str) -> list[MutationPoint]:
    """Return every change this tool can make to one module.

    **Addressed by walk order rather than by line**, because a line can carry
    several points and a report has to distinguish them.

    Args:
        source (str): The module's text.

    Returns:
        list[MutationPoint]: Every point, in walk order.
    """
    found: list[MutationPoint] = []
    for index, node in enumerate(ast.walk(ast.parse(source))):
        if isinstance(node, ast.Compare):
            for position, operator in enumerate(node.ops):
                counterpart = _COMPARE.get(type(operator))
                if counterpart is not None:
                    found.append(MutationPoint(
                        "compare", index, position, node.lineno,
                        f"{type(operator).__name__} to {counterpart.__name__}",
                    ))
        elif isinstance(node, ast.BoolOp):
            found.append(MutationPoint(
                "bool", index, 0, node.lineno,
                f"{type(node.op).__name__} to {_BOOL[type(node.op)].__name__}",
            ))
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                found.append(MutationPoint(
                    "bool_const", index, 0, node.lineno,
                    f"{node.value} to {not node.value}",
                ))
            elif isinstance(node.value, (int, float)):
                found.append(MutationPoint(
                    "number", index, 0, node.lineno,
                    f"{node.value} to {node.value + 1}",
                ))
    return found


def _mutate(tree: ast.Module, point: MutationPoint) -> bool:
    """Apply exactly one point to a parsed tree, in place.

    Args:
        tree (ast.Module): A freshly parsed copy of the module.
        point (MutationPoint): The change to make.

    Returns:
        bool: True when the addressed node was found and changed.
    """
    for index, node in enumerate(ast.walk(tree)):
        if index != point.node_index:
            continue
        if point.kind == "compare" and isinstance(node, ast.Compare):
            node.ops[point.operator_index] = _COMPARE[
                type(node.ops[point.operator_index])
            ]()
            return True
        if point.kind == "bool" and isinstance(node, ast.BoolOp):
            node.op = _BOOL[type(node.op)]()
            return True
        if point.kind == "bool_const" and isinstance(node, ast.Constant):
            node.value = not node.value
            return True
        if point.kind == "number" and isinstance(node, ast.Constant):
            node.value = node.value + 1
            return True
        return False
    return False


def recover(module: Path) -> Optional[str]:
    """Restore a module from an abandoned backup, if one is there.

    **The caller is expected to stop.** A backup means an earlier run was
    killed with a mutant in place, so any suite that ran since reported results
    about code nobody wrote.

    Args:
        module (Path): The module about to be mutated.

    Returns:
        Optional[str]: What was recovered, or None when nothing was.
    """
    backup = module.with_suffix(module.suffix + _BACKUP_SUFFIX)
    if not backup.is_file():
        return None
    module.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8",
                      newline="\n")
    backup.unlink()
    return (
        f"{module} was left mutated by an earlier run and has been restored "
        f"from {backup.name}; verify the suite before mutating again"
    )


def run_targets(
    root: Path, targets: list[str], *, stop_early: bool
) -> subprocess.CompletedProcess:
    """Run the named pytest targets from a repository root.

    Args:
        root (Path): The repository to run in.
        targets (list[str]): Each pytest argument, as its own element.
        stop_early (bool): Whether to stop at the first failure, which makes a
            killed mutant cheap and leaves a survivor costing a full run.

    Returns:
        subprocess.CompletedProcess: The finished run.
    """
    command = [sys.executable, "-m", "pytest", *targets, "-q", "--no-header",
               "-p", "no:randomly", "--tb=no"]
    if stop_early:
        command.append("-x")
    return subprocess.run(
        command, cwd=root, capture_output=True, text=True, check=False,
        timeout=_RUN_TIMEOUT_SEC,
    )


def control_problem(root: Path, module: Path, targets: list[str]) -> Optional[str]:
    """Report why the audit must not run, or None when it may.

    **Rewriting a module from its syntax tree strips every comment**, so a
    target carrying a header or runway scan fails on the reformatting alone and
    would kill every mutant for the wrong reason. The control is the unparsed
    module with nothing changed: it has to pass, and it has to have collected
    something.

    Args:
        root (Path): The repository root.
        module (Path): The module to be mutated.
        targets (list[str]): The pytest arguments.

    Returns:
        Optional[str]: The reason to refuse, or None.
    """
    original = module.read_text(encoding="utf-8")
    module.write_text(ast.unparse(ast.parse(original)), encoding="utf-8",
                      newline="\n")
    try:
        control = run_targets(root, targets, stop_early=False)
    finally:
        module.write_text(original, encoding="utf-8", newline="\n")

    passed = _PASSED.search(control.stdout)
    collected = int(passed.group(1)) if passed else 0
    if control.returncode != 0 or collected == 0:
        return (
            f"control failed: exit {control.returncode}, {collected} case(s) "
            f"collected. Unparsing alone must pass, or every mutant is killed "
            f"by the reformatting rather than by the change"
        )
    logger.info("Control: %d case(s) pass against the unparsed module", collected)
    return None


def survivors(
    root: Path, module: Path, targets: list[str], *, limit: int = 0
) -> list[MutationPoint]:
    """Return every change the suite failed to notice.

    Args:
        root (Path): The repository root.
        module (Path): The production module to mutate.
        targets (list[str]): The pytest arguments naming what to run.
        limit (int): Stop after this many points, or zero for all of them.

    Returns:
        list[MutationPoint]: The survivors, in walk order.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when a backup from a
            killed run was found, or when the control did not pass, or when a
            run collected nothing part-way through.
    """
    recovered = recover(module)
    if recovered is not None:
        raise ValueError(f"QC_HARNESS_PARSER_ERROR: {recovered}")

    refusal = control_problem(root, module, targets)
    if refusal is not None:
        raise ValueError(f"QC_HARNESS_PARSER_ERROR: {refusal}")

    original = module.read_text(encoding="utf-8")
    backup = module.with_suffix(module.suffix + _BACKUP_SUFFIX)
    backup.write_text(original, encoding="utf-8", newline="\n")

    points = mutation_points(original)
    if limit:
        points = points[:limit]

    survived: list[MutationPoint] = []
    try:
        for point in points:
            tree = ast.parse(original)
            if not _mutate(tree, point):
                continue
            ast.fix_missing_locations(tree)
            try:
                mutant = ast.unparse(tree)
            except (ValueError, RecursionError):
                continue
            module.write_text(mutant, encoding="utf-8", newline="\n")

            done = run_targets(root, targets, stop_early=True)
            if done.returncode == _NOTHING_COLLECTED:
                raise ValueError(
                    f"QC_HARNESS_PARSER_ERROR: pytest collected nothing at "
                    f"{point.describe()}, so no result from this run means "
                    f"anything"
                )
            if done.returncode == 0:
                survived.append(point)
                logger.warning("SURVIVED %s", point.describe())
    finally:
        module.write_text(original, encoding="utf-8", newline="\n")
        backup.unlink(missing_ok=True)
    return survived


def declared_survivors(path: Path) -> dict[str, dict[str, Any]]:
    """Return the accepted survivors, per module.

    Args:
        path (Path): ``config/mutation_survivors.yaml``.

    Returns:
        dict: Module path to its declaration. Empty when the file is absent,
        which is the state a repository with no accepted survivor is in.
    """
    if not path.is_file():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return loaded.get("survivors") or {}


def survivor_problems(
    module: str, found: list[MutationPoint], declaration: dict[str, Any]
) -> list[str]:
    """Compare what survived against what was accepted, in both directions.

    **A declared entry that no longer survives is a problem too**, because it
    describes a gap that has been closed and the list is meant to shrink.

    Args:
        module (str): The module path, as the declaration keys it.
        found (list[MutationPoint]): What survived this run.
        declaration (dict): The entry for this module, or an empty mapping.

    Returns:
        list[str]: One entry per disagreement. Empty when every survivor is
        declared and every declaration still survives.
    """
    accepted = {
        str(entry.get("mutation", "")): entry
        for entry in (declaration.get("accepted") or [])
    }
    surviving = {point.describe() for point in found}

    problems: list[str] = []
    for undeclared in sorted(surviving - set(accepted)):
        problems.append(
            f"{module}: {undeclared} survived and is not declared, so some "
            f"behaviour on that line is asserted by nothing"
        )
    for closed in sorted(set(accepted) - surviving):
        problems.append(
            f"{module}: {closed} is declared as an accepted survivor and no "
            f"longer survives, so the declaration overstates the gap"
        )
    return problems


def main(argv: Optional[list[str]] = None) -> int:
    """Audit one module from the command line.

    Args:
        argv (Optional[list[str]]): Arguments, or None for ``sys.argv``.

    Returns:
        int: ``0`` when every survivor is declared, ``1`` otherwise, ``4``
        when the audit refused to run.
    """
    parser = argparse.ArgumentParser(
        prog="mutation-audit",
        description="Report production changes the suite fails to notice",
    )
    parser.add_argument("module", type=Path, help="The production module")
    parser.add_argument(
        "--target", action="append", default=[],
        help="A pytest argument, repeated once per argument",
    )
    parser.add_argument("--limit", type=int, default=0,
                        help="Stop after this many mutation points")
    parsed = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        found = survivors(root, root / parsed.module, parsed.target,
                          limit=parsed.limit)
    except (ValueError, subprocess.TimeoutExpired) as error:
        logger.error("%s", error)
        return 4

    problems = survivor_problems(
        parsed.module.as_posix(), found,
        declared_survivors(root / "config/mutation_survivors.yaml").get(
            parsed.module.as_posix(), {}
        ),
    )
    for problem in problems:
        logger.error("%s", problem)
    logger.info("%d survivor(s), %d undeclared", len(found), len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
