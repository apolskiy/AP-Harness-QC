# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Parallel mutation audit, which measures each point in its own copy of the repository.

Created: 2026-10-21
Last updated: 2026-10-23

This file contains ``parallel_survivors``, which audits one module with several
workers and returns the changes nothing failed on, in walk order;
``worker_copies``, which lays out one copy of the repository per worker beside
a link to every sibling repository; ``remove_copies``, which removes the
links first and then the copies; and ``seeing_modules``, which lists the test
modules whose imports reach the audited module, run first against each mutant
(section 15.16).

**The ``MUT`` cases call it through ``tests/mutation/mutation_support.py``**, in
the ``audit-mutation-on-change`` workflow and on request, and an author runs it
through the audit's command line::

    python -m tools.mutation_audit cmn/verdict.py --workers 4

**The repository's module is never written.** The control and every mutant run
in a copy, so the audit's lock is marked isolated and an ordinary run, the Model
Repository's included, proceeds while it holds. ``tools/mutation_audit.py``
remains the in-place audit, one point at a time, and supplies the baseline
check, the lock, the mutants and the run of each point.

Specified by ``docs/design/harness_test_taxonomy.md`` sections 15.15 and 15.16.
"""

import ast
import os
import queue
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from typing import Callable, Final

from cmn.code_standards import python_sources
from cmn.mutation_guard import ProgressLog, module_digest, stop_requested
from tools.mutation_declarations import baseline_refusal
from tools.mutation_audit import (
    DEFAULT_WORKERS,
    MutationPoint,
    MutationRefusal,
    control_problem,
    held_audit,
    mutant_source,
    mutation_points,
    run_targets,
)

_MANIFEST: Final[str] = "config/mutation_survivors.yaml"
_NOTHING_COLLECTED: Final[int] = 5

# NEVER COPIED: credentials, environments, build output, caches, reports and
# logs. `.git` is copied, because cases read the index.
_LEFT_OUT: Final[tuple[str, ...]] = (
    ".env", ".venv", "venv", "build", "dist", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", "htmlcov", ".eggs", "reports",
    "allure-results", "allure-report", ".idea", "node_modules", "logs",
    "*.egg-info", "*.mutation-lock", "*.mutation-backup",
)


def _link(target: Path, link: Path) -> None:
    """Link a directory, as a symbolic link or, where that is refused, a junction.

    Args:
        target (Path): The directory linked to.
        link (Path): Where the link is made.

    Returns:
        None

    Raises:
        OSError: When neither kind of link can be made.
    """
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            raise
        import _winapi  # pylint: disable=import-outside-toplevel,import-error
        _winapi.CreateJunction(str(target), str(link))


def worker_copies(root: Path, count: int) -> list[Path]:
    """Lay out one copy of the repository per worker, each beside links to its siblings.

    Args:
        root (Path): The repository root.
        count (int): How many copies.

    Returns:
        list[Path]: Each copy's root, named as the repository is.

    Raises:
        MutationRefusal: When a sibling cannot be linked, since a paired case
            would then be deselected in the copies and not in place.
    """
    base = Path(tempfile.mkdtemp(prefix="mqc-mutation-"))
    siblings = [entry for entry in root.parent.iterdir() if entry.is_dir() and entry != root]
    copies: list[Path] = []
    try:
        for number in range(1, count + 1):
            home = base / f"worker-{number}"
            home.mkdir()
            for sibling in siblings:
                _link(sibling, home / sibling.name)
            copy = home / root.name
            shutil.copytree(root, copy, ignore=shutil.ignore_patterns(*_LEFT_OUT))
            copies.append(copy)
    except OSError as error:
        remove_copies(copies or [base / "worker-1" / root.name])
        raise MutationRefusal(
            f"QC_HARNESS_AUDIT_REFUSED: the worker copies could not be laid out with "
            f"their siblings linked ({error}), so a paired case would see a different "
            f"repository than it does in place"
        ) from error
    return copies


def _clear_read_only(function: Callable[[str], object], path: str, _error: BaseException) -> None:
    """Make a read-only file writable and retry the removal, as git's packs need.

    Args:
        function (Callable): The removal that failed.
        path (str): The file it failed on.
        _error (BaseException): Why, unused.

    Returns:
        None
    """
    os.chmod(path, 0o700)
    function(path)


def remove_copies(copies: list[Path]) -> None:
    """Remove each copy's sibling links first, then the copies and their directory.

    **Links first**, so no removal can follow one into a real repository.

    Args:
        copies (list[Path]): The copies :func:`worker_copies` returned.

    Returns:
        None
    """
    for copy in copies:
        home = copy.parent
        if not home.is_dir():
            continue
        for entry in home.iterdir():
            if entry.is_symlink():
                entry.unlink()
            elif os.path.isjunction(entry):
                os.rmdir(entry)
    if copies:
        shutil.rmtree(copies[0].parent.parent, onexc=_clear_read_only)


def _dotted(root: Path, path: Path) -> str:
    """Return the import name of a repository file, a package's being its directory's."""
    parts = list(path.relative_to(root).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _imported(tree: ast.Module, name: str) -> set[str]:
    """Return every name one module's imports could bind, with each package they pass through.

    Args:
        tree (ast.Module): The module's syntax tree.
        name (str): The module's own import name, for relative imports.

    Returns:
        set[str]: Candidate import names; the caller keeps the repository's own.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = name.split(".")[: -node.level]
                base = ".".join([*anchor, base] if base else anchor)
            found.add(base)
            found.update(f"{base}.{alias.name}" for alias in node.names)
    return found


def seeing_modules(root: Path, module: Path) -> list[str]:
    """Return the test modules whose imports reach a module, directly or through others.

    Read from the syntax tree of every Python file in the repository, so a case
    reaching the module only through a nested session or a file read is not
    listed; section 15.16 is why that costs a second run and never a result.

    Args:
        root (Path): The repository root.
        module (Path): The audited module.

    Returns:
        list[str]: Test module paths relative to the root, sorted.
    """
    names = {_dotted(root, path): path for path in python_sources(root)}
    edges = {
        name: {found for found in _imported(ast.parse(path.read_text(encoding="utf-8")), name)
               if found in names and found != name}
        for name, path in names.items()
    }
    target = _dotted(root, module)
    seeing: list[str] = []
    for name, path in names.items():
        # THE MUTATION LAYER IS LEFT OUT: an audit runs `-m unit`, and naming
        # one of its modules brings its conftest in under the root's name
        # (section 15.16.1).
        if not path.name.startswith("mqc_") or path.name.startswith("mqc_mut_"):
            continue
        reached, frontier = set(), [name]
        while frontier:
            current = frontier.pop()
            for following in edges[current] - reached:
                reached.add(following)
                frontier.append(following)
        if target in reached:
            seeing.append(path.relative_to(root).as_posix())
    return sorted(seeing)


class _Measurement:
    """The points of one audit, shared by its workers."""

    def __init__(self, root: Path, module: str, original: str, points: list[MutationPoint],
                 progress: ProgressLog) -> None:
        """Hold the audit's shared state.

        Args:
            root (Path): The repository root, where a stop request is read.
            module (str): The module path relative to the root.
            original (str): The baseline each mutant is made from.
            points (list): Every point, in walk order.
            progress (ProgressLog): Where each event is written.

        Returns:
            None
        """
        self.root, self.module, self.original = root, module, original
        self.points, self.progress = points, progress
        self.pending: "queue.Queue[int]" = queue.Queue()
        for number in range(1, len(points) + 1):
            self.pending.put(number)
        self.outcomes: dict[int, int] = {}
        self.stopped_at = 0
        self._lock = threading.Lock()

    def line(self, text: str) -> None:
        """Write one progress line, one writer at a time."""
        with self._lock:
            self.progress.line(text)

    def run(self, copy: Path, targets: list[str], first: list[str]) -> None:
        """Measure points in one copy until none remain or a stop is requested.

        Args:
            copy (Path): This worker's copy of the repository.
            targets (list[str]): The pytest arguments, whose outcome decides a survivor.
            first (list[str]): The seeing cases' arguments, run first, or empty
                where nothing imports the module (section 15.16).

        Returns:
            None
        """
        target = copy / self.module
        while True:
            try:
                number = self.pending.get_nowait()
            except queue.Empty:
                return
            if stop_requested(self.root, os.getpid()):
                with self._lock:
                    self.stopped_at = min(filter(None, (self.stopped_at, number)))
                return
            point = self.points[number - 1]
            mutant = mutant_source(self.original, point)
            if mutant is None:
                continue
            place = f"point {number} of {len(self.points)}"
            self.line(f"{place} started: {point.describe()}")
            target.write_text(mutant, encoding="utf-8", newline="\n")
            try:
                code = run_targets(copy, first or targets, stop_early=True).returncode
                # A MISS BY THE SEEING CASES IS NOT A SURVIVOR until the full
                # targets miss it too (section 15.16).
                if first and code in (0, _NOTHING_COLLECTED):
                    code = run_targets(copy, targets, stop_early=True).returncode
            finally:
                target.write_text(self.original, encoding="utf-8", newline="\n")
            with self._lock:
                self.outcomes[number] = code
            self.line(f"{place} {'survived' if code == 0 else 'killed'}")


def parallel_survivors(
    root: Path, module: Path, targets: list[str], *, workers: int = DEFAULT_WORKERS,
    limit: int = 0, remeasure: bool = False,
) -> list[MutationPoint]:
    """Return every change the suite failed to notice, measured in parallel copies.

    Args:
        root (Path): The repository root.
        module (Path): The production module to mutate, which is never written.
        targets (list[str]): The pytest arguments naming what to run.
        workers (int): How many copies measure at once.
        limit (int): Stop after this many points, or zero for all of them.
        remeasure (bool): True to take the module on disk as the baseline
            instead of comparing it with the declared digest (section 15.10.2).

    Returns:
        list[MutationPoint]: The survivors, in walk order.

    Raises:
        MutationRefusal: With ``QC_HARNESS_AUDIT_REFUSED`` when a stop was
            requested, the module is not its declared baseline, the copies could
            not be laid out, the control did not pass, or a run collected nothing.
    """
    with held_audit(root, module, isolated=True) as progress:
        # THE TWO CHEAP REFUSALS ARE RAISED HERE, inside the lock and in this
        # order: a stop asked for ends the audit before it touches anything,
        # and a baseline that is not the declared module is refused before any
        # copy is laid out. They sit above the measurement so that whether the
        # run was asked to re-measure is answered once, by the caller that was
        # told (section 15.10.2).
        if stop_requested(root, os.getpid()):
            raise MutationRefusal(
                "QC_HARNESS_AUDIT_REFUSED: stopped on request before its control"
            )
        stale = baseline_refusal(
            root / _MANIFEST, module.relative_to(root).as_posix(),
            module.read_text(encoding="utf-8"), remeasure=remeasure,
        )
        if stale is not None:
            raise MutationRefusal(f"QC_HARNESS_AUDIT_REFUSED: {stale}")
        found = _measured(root, module, targets, progress, max(1, workers), limit)
    progress.finish(f"untouched, {len(found)} survivor(s)")
    return found


def _control_in(copy: Path, relative: str, targets: list[str], original: str) -> None:
    """Run the control in one copy and restore that copy's module after it.

    Args:
        copy (Path): The copy the control runs in.
        relative (str): The module path relative to the root.
        targets (list[str]): The pytest arguments.
        original (str): The baseline.

    Returns:
        None

    Raises:
        MutationRefusal: When the control did not pass.
    """
    module = copy / relative
    try:
        refusal = control_problem(copy, module, targets, original)
    finally:
        module.write_text(original, encoding="utf-8", newline="\n")
    if refusal is not None:
        raise MutationRefusal(f"QC_HARNESS_AUDIT_REFUSED: {refusal}")

def _first_targets(
    root: Path, module: Path, targets: list[str], progress: ProgressLog
) -> list[str]:
    """Return the arguments that run the seeing cases first, or empty where none see the module.

    Args:
        root (Path): The repository root.
        module (Path): The audited module.
        targets (list[str]): The full targets.
        progress (ProgressLog): Where the count is written.

    Returns:
        list[str]: The targets narrowed to the seeing test modules.
    """
    seeing = seeing_modules(root, module)
    progress.line(f"{len(seeing)} test module(s) see the module and run first")
    return [*targets, *seeing] if seeing else []

def _measured(root: Path, module: Path, targets: list[str], progress: ProgressLog,
              workers: int, limit: int) -> list[MutationPoint]:
    """Copy, control and measure, the lock held and the baseline already accepted.

    Args:
        root (Path): The repository root.
        module (Path): The module under audit.
        targets (list[str]): The pytest arguments.
        progress (ProgressLog): Where each event is written.
        workers (int): How many copies measure at once.
        limit (int): Stop after this many points, or zero for all of them.

    Returns:
        list[MutationPoint]: The survivors, in walk order.

    Raises:
        MutationRefusal: As :func:`parallel_survivors` describes.
    """
    relative = module.relative_to(root).as_posix()
    original = module.read_text(encoding="utf-8")
    points = mutation_points(original)[: limit or None]
    progress.line(f"baseline {module_digest(original)[:8]}, {len(points)} points, "
                  f"{workers} workers")
    copies = worker_copies(root, min(workers, max(1, len(points))))
    try:
        progress.line("control started")
        _control_in(copies[0], relative, targets, original)
        progress.line("control passed")
        first = _first_targets(root, module, targets, progress)
        # THE SEEING CASES ARE CONTROLLED TOO, or a first pass failing on its
        # own reads as a kill of every mutant (section 15.16.1).
        if first:
            progress.line("control of the seeing cases started")
            _control_in(copies[0], relative, first, original)
            progress.line("control of the seeing cases passed")
        shared = _Measurement(root, relative, original, points, progress)
        threads = [threading.Thread(target=shared.run, args=(copy, targets, first))
                   for copy in copies]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        remove_copies(copies)
    if shared.stopped_at:
        raise MutationRefusal(
            f"QC_HARNESS_AUDIT_REFUSED: stopped on request at point {shared.stopped_at} of "
            f"{len(points)}"
        )
    if _NOTHING_COLLECTED in shared.outcomes.values():
        raise MutationRefusal(
            "QC_HARNESS_AUDIT_REFUSED: pytest collected nothing at a point, so no result "
            "from this run means anything"
        )
    return [points[number - 1] for number in sorted(shared.outcomes)
            if shared.outcomes[number] == 0]
