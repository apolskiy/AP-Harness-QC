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
the suite imports it from. The original is written to a sibling backup before
any rewrite, the control's unparse included, so a run killed at any point is
recoverable by the next one (section 15.5).

**The baseline is declared rather than discovered.** The module has to hash to
the digest ``config/mutation_survivors.yaml`` declares for it, because a backup
is self-consistent and will faithfully preserve damage: a module an earlier run
left unparsed passes the control gate trivially, since unparsing is idempotent
(section 15.10).
"""

import argparse
import ast
import hashlib
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Optional

import yaml

logger = logging.getLogger(__name__)


class MutationRefusal(Exception):
    """The audit declined to measure, which is not a measurement.

    Every reason carries ``QC_HARNESS_AUDIT_REFUSED``: a backup from a killed
    run, a baseline that is not the declared module, a control that did not
    pass, a run that collected nothing. ``framework-rules.md`` section 4 gives
    that family the outcome "skip or broken, never fail", so a caller reports
    one as a skip.

    Separate from :exc:`ValueError` because the two answer different
    questions. A `ValueError` from this module means an argument was wrong; a
    refusal means the arguments were fine and the repository was not.

    Design: ``harness_test_taxonomy.md`` section 15.2.1.
    """

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

# WHERE THE BASELINE IS DECLARED. Read from the root rather than passed, for
# the same reason the backup suffix is a constant: it is a property of the
# project and not of a caller.
_MANIFEST: Final[str] = "config/mutation_survivors.yaml"

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


def module_digest(text: str) -> str:
    """Return the digest of a module's content, newlines normalized.

    Args:
        text (str): The module source.

    Returns:
        str: The hex SHA-256 of the content with newlines as LF, so a digest
        does not depend on how the file was checked out.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def baseline_problem(manifest: Path, module: str, text: str) -> Optional[str]:
    """Report why this content may not serve as a baseline, or None.

    Design: ``harness_test_taxonomy.md`` section 15.10.

    Args:
        manifest (Path): ``config/mutation_survivors.yaml``.
        module (str): The module path, as the declaration keys it.
        text (str): The content on disk.

    Returns:
        Optional[str]: The reason to refuse, or None when the content hashes
        to the declared digest.
    """
    declared = (declared_survivors(manifest).get(module) or {}).get("digest")
    found = module_digest(text)
    if not declared:
        return (
            f"{module} declares no baseline digest, so nothing establishes "
            f"that this content is the module the survivors were measured "
            f"against. Add `digest: {found}` beside its `accepted` list"
        )
    if declared != found:
        return (
            f"{module} hashes to {found} and {manifest.name} declares "
            f"{declared}. Either an earlier run left the module altered, or "
            f"it was edited and the survivors need re-measuring against it"
        )
    return None


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


def control_problem(
    root: Path, module: Path, targets: list[str], original: str
) -> Optional[str]:
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
        original (str): The baseline, which the caller has already backed up.
            **Passed rather than read**, because reading it here put the
            rewrite below outside the backup window (section 15.5).

    Returns:
        Optional[str]: The reason to refuse, or None.
    """
    module.write_text(ast.unparse(ast.parse(original)), encoding="utf-8",
                      newline="\n")
    # THE CALLER RESTORES, because the caller is what holds the backup. A
    # restore here would leave the caller unable to tell a control that ran
    # from one that never wrote anything.
    control = run_targets(root, targets, stop_early=False)

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
        MutationRefusal: With ``QC_HARNESS_AUDIT_REFUSED`` when a backup
            from a killed run was found, when the module does not hash to its
            declared digest, when the control did not pass, or when a run
            collected nothing part-way through. **A refusal is a skip**, per
            section 15.2.1: none of those says anything about the survivors.
    """
    recovered = recover(module)
    if recovered is not None:
        raise MutationRefusal(f"QC_HARNESS_AUDIT_REFUSED: {recovered}")

    # THE BASELINE IS CHECKED BEFORE ANYTHING IS WRITTEN, because every later
    # step treats this content as authoritative: the backup copies it and the
    # `finally` restores it. A damaged baseline that reaches those steps is
    # preserved by them rather than caught (section 15.10).
    original = module.read_text(encoding="utf-8")
    stale = baseline_problem(
        root / _MANIFEST, module.relative_to(root).as_posix(), original
    )
    if stale is not None:
        raise MutationRefusal(f"QC_HARNESS_AUDIT_REFUSED: {stale}")

    # THE BACKUP COMES BEFORE THE CONTROL, which rewrites the module too. It
    # was written after, which left the longest window in the audit unguarded.
    backup = module.with_suffix(module.suffix + _BACKUP_SUFFIX)
    backup.write_text(original, encoding="utf-8", newline="\n")

    try:
        refusal = control_problem(root, module, targets, original)
    finally:
        module.write_text(original, encoding="utf-8", newline="\n")
    if refusal is not None:
        backup.unlink(missing_ok=True)
        raise MutationRefusal(f"QC_HARNESS_AUDIT_REFUSED: {refusal}")

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
                raise MutationRefusal(
                    f"QC_HARNESS_AUDIT_REFUSED: pytest collected nothing at "
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


def declare_digest(manifest: Path, module: str, digest: str) -> None:
    """Record the baseline digest a module's survivors were measured against.

    **Edited in place rather than re-serialized.** Dumping the parsed mapping
    back would drop every comment, and the comments are the reasons section
    15.2 requires each accepted survivor to carry.

    Design: ``harness_test_taxonomy.md`` section 15.2.2.

    Args:
        manifest (Path): ``config/mutation_survivors.yaml``.
        module (str): The module path, as the declaration keys it.
        digest (str): The hex digest to declare.

    Returns:
        None
    """
    text = manifest.read_text(encoding="utf-8") if manifest.is_file() else ""
    entry = f"  {module}:\n"
    declared = (declared_survivors(manifest).get(module) or {}).get("digest")
    if declared:
        manifest.write_text(
            text.replace(f"    digest: {declared}\n",
                         f"    digest: {digest}\n", 1),
            encoding="utf-8", newline="\n",
        )
        return
    if entry in text:
        manifest.write_text(
            text.replace(entry, f"{entry}    digest: {digest}\n", 1),
            encoding="utf-8", newline="\n",
        )
        return
    # A MODULE WITH NO ENTRY AT ALL, which is an audited module that has
    # accepted nothing. The digest alone is the correct statement, and
    # `survivor_problems` reads an absent `accepted` as an empty list.
    opener = "" if text.endswith("\n") or not text else "\n"
    manifest.write_text(
        f"{text}{opener}{entry}    digest: {digest}\n",
        encoding="utf-8", newline="\n",
    )


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
    except (MutationRefusal, subprocess.TimeoutExpired) as error:
        logger.error("%s", error)
        return 4

    problems = survivor_problems(
        parsed.module.as_posix(), found,
        declared_survivors(root / _MANIFEST).get(
            parsed.module.as_posix(), {}
        ),
    )
    for problem in problems:
        logger.error("%s", problem)
    logger.info("%d survivor(s), %d undeclared", len(found), len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
