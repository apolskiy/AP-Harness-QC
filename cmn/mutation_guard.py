# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Refuse a run while a harness module is under mutation, and log an audit's progress.

Design: ``docs/design/harness_test_taxonomy.md`` section 15.12.

A backup or a lock beside a module means a mutation audit is running or one
died. A run started by that audit proceeds; any other run refuses with
``QC_HARNESS_PREFLIGHT_FAILURE``, after restoring and verifying a module an
abandoned audit left. The audit writes a progress log, one flushed line per
event, which a refusal quotes.
"""

import ctypes
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Mapping, Optional

import pytest
import yaml

# WHERE THE REAL FILE WAITS while a mutant is in place, and who holds it.
BACKUP_SUFFIX: Final[str] = ".mutation-backup"
LOCK_SUFFIX: Final[str] = ".mutation-lock"

# SET BY THE AUDIT for every run it launches, to its own process id.
AUDIT_ENV: Final[str] = "MQC_MUTATION_AUDIT"

# WHERE THE BASELINE IS DECLARED and where the progress logs go, from the root.
MANIFEST: Final[str] = "config/mutation_survivors.yaml"
PROGRESS_DIR: Final[str] = "reports/mutation"
_PROGRESS_INFIX: Final[str] = ".mutation-progress-"
_STAMP: Final[str] = "%Y%m%dT%H%M%SZ"

# THE PACKAGES A RUN IMPORTS, the only places a mutant can sit.
_PACKAGES: Final[tuple[str, ...]] = ("ingestion", "execution", "evaluation", "cmn", "tools")

_CODE: Final[str] = "QC_HARNESS_PREFLIGHT_FAILURE"

# WINDOWS PROCESS QUERY, used because the POSIX liveness signal terminates a
# process there: the access right, the error for a process we may not open,
# and the exit code a running process reports.
_QUERY_LIMITED_INFORMATION: Final[int] = 0x1000
_ACCESS_DENIED: Final[int] = 5
_STILL_ACTIVE: Final[int] = 259


def module_digest(text: str) -> str:
    """Return the digest of a module's content, newlines normalized.

    Args:
        text (str): The module source.

    Returns:
        str: The hex SHA-256 of the content with newlines as LF.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def process_alive(pid: int) -> bool:
    """Report whether a process is running, without signalling it.

    Design: ``harness_test_taxonomy.md`` section 15.11.

    Args:
        pid (int): The process identifier.

    Returns:
        bool: True when the process exists. On Windows the process is opened
        for a query and its exit code read.
    """
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _windows_process_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _windows_process_alive(pid: int) -> bool:
    """Report whether a Windows process is running, by querying its exit code.

    Args:
        pid (int): The process identifier.

    Returns:
        bool: True when the process exists. A process that may not be opened
        exists; one that cannot be found has exited.
    """
    kernel = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
    # A HANDLE IS POINTER-WIDE, and ctypes returns a C int unless told
    # otherwise, which truncates it on a 64-bit process.
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
    kernel.GetExitCodeProcess.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong))
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    handle = kernel.OpenProcess(_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ctypes.get_last_error() == _ACCESS_DENIED
    try:
        code = ctypes.c_ulong()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == _STILL_ACTIVE
    finally:
        kernel.CloseHandle(handle)


def imported_harness_root() -> Path:
    """Return the root of the harness this process imported.

    Returns:
        Path: The directory holding the ``cmn`` package: a checkout, a sibling
        checkout, or an installed distribution.
    """
    return Path(__file__).resolve().parents[1]


def _utc_now() -> datetime:
    """Return the current time in UTC.

    Returns:
        datetime: Now, timezone-aware.
    """
    return datetime.now(timezone.utc)


def _progress_prefix(module: str) -> str:
    """Return the file-name prefix a module's progress logs share.

    Args:
        module (str): The module path relative to the root, as the manifest keys it.

    Returns:
        str: The path flattened with dots, followed by the progress infix.
    """
    return module.replace("/", ".") + _PROGRESS_INFIX


class ProgressLog:
    """One audit's progress, one flushed line per event.

    Design: ``harness_test_taxonomy.md`` section 15.12.3.

    Attributes:
        path (Path): The log file, named for the module and the audit's start.
    """

    def __init__(self, path: Path, module: str) -> None:
        """Hold a log that has already been created.

        Args:
            path (Path): The log file.
            module (str): The module path relative to the root.

        Returns:
            None
        """
        self._path = path
        self._module = module

    @property
    def path(self) -> Path:
        """Return the log file.

        Returns:
            Path: Where the lines are written.
        """
        return self._path

    @classmethod
    def begin(cls, root: Path, module: str, *, now: Optional[datetime] = None) -> "ProgressLog":
        """Create a module's log, named for the start time, and write its first line.

        Args:
            root (Path): The repository root.
            module (str): The module path relative to the root.
            now (Optional[datetime]): The start time, or None for the clock.

        Returns:
            ProgressLog: The log, holding ``started pid <n>``.
        """
        started = now or _utc_now()
        directory = root / PROGRESS_DIR
        directory.mkdir(parents=True, exist_ok=True)
        log = cls(directory / f"{_progress_prefix(module)}{started.strftime(_STAMP)}", module)
        log.line(f"started pid {os.getpid()}", now=started)
        return log

    def line(self, event: str, *, now: Optional[datetime] = None) -> None:
        """Append one event, stamped, and flush it to disk before returning.

        Args:
            event (str): What happened.
            now (Optional[datetime]): The time to stamp, or None for the clock.

        Returns:
            None
        """
        stamp = (now or _utc_now()).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{stamp} {event}\n")
            handle.flush()
            os.fsync(handle.fileno())

    def finish(self, event: str, *, now: Optional[datetime] = None) -> None:
        """Write the last line and delete every older log of the module.

        Args:
            event (str): The outcome, recorded as ``finished: <event>``.
            now (Optional[datetime]): The time to stamp, or None for the clock.

        Returns:
            None
        """
        self.line(f"finished: {event}", now=now)
        for older in self._path.parent.glob(f"{_progress_prefix(self._module)}*"):
            if older != self._path:
                older.unlink(missing_ok=True)


def latest_progress(
    root: Path, module: str, *, now: Optional[datetime] = None
) -> Optional[str]:
    """Return the newest progress log's last line and how long ago it was written.

    Args:
        root (Path): The repository root.
        module (str): The module path relative to the root.
        now (Optional[datetime]): The time to measure from, or None for the clock.

    Returns:
        Optional[str]: ``last progress "<line>", written <n> minutes ago``, or
        None when the module has no log.
    """
    logs = sorted((root / PROGRESS_DIR).glob(f"{_progress_prefix(module)}*"))
    if not logs:
        return None
    lines = logs[-1].read_text(encoding="utf-8").splitlines()
    if not lines:
        return None
    last = lines[-1]
    stamp, _, event = last.partition(" ")
    try:
        written = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return f'last progress "{last}"'
    minutes = int(((now or _utc_now()) - written).total_seconds() // 60)
    return f'last progress "{event}", written {minutes} minutes ago'


def _declared_digest(root: Path, module: str) -> Optional[str]:
    """Return the digest the manifest declares for a module.

    Args:
        root (Path): The repository root.
        module (str): The module path relative to the root.

    Returns:
        Optional[str]: The declared digest, or None when there is none.
    """
    manifest = root / MANIFEST
    if not manifest.is_file():
        return None
    loaded = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    entry = (loaded.get("survivors") or {}).get(module) or {}
    return entry.get("digest")


def _lock_holder(lock: Path) -> tuple[int, str]:
    """Return the process id and start time a lock records.

    Args:
        lock (Path): The lock file, which may be absent or unreadable.

    Returns:
        tuple[int, str]: The pid, zero when unknown, and the recorded start.
    """
    try:
        held = json.loads(lock.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0, "at an unrecorded time"
    return int(held.get("pid") or 0), str(held.get("started") or "at an unrecorded time")


def _held_modules(root: Path) -> list[Path]:
    """Return every module carrying a backup or a lock beside it.

    Args:
        root (Path): The harness root.

    Returns:
        list[Path]: The modules, sorted, each once.
    """
    found: set[Path] = set()
    for package in _PACKAGES:
        base = root / package
        if not base.is_dir():
            continue
        for suffix in (BACKUP_SUFFIX, LOCK_SUFFIX):
            for marker in base.rglob(f"*{suffix}"):
                found.add(marker.with_name(marker.name[: -len(suffix)]))
    return sorted(found)


def _recoveries(module: Path, backup: Path) -> str:
    """Return the two ways out of a restore that did not hold.

    Args:
        module (Path): The module.
        backup (Path): Its backup, kept.

    Returns:
        str: Both recoveries, in words.
    """
    return (
        f"The backup is kept. Copy {backup} over {module}, or restore {module} "
        f"with git, then run again"
    )


def _restore(root: Path, module: Path, relative: str, progress: str) -> str:
    """Restore a module from an abandoned backup and verify it, keeping the backup on failure.

    Design: ``harness_test_taxonomy.md`` section 15.12.2.

    Args:
        root (Path): The harness root.
        module (Path): The module an abandoned audit left.
        relative (str): Its path relative to the root.
        progress (str): The abandoned audit's last progress, in words.

    Returns:
        str: The refusal, saying whether the restore held.
    """
    backup = module.with_name(module.name + BACKUP_SUFFIX)
    lead = f"{_CODE}: {relative} was left by an abandoned mutation audit ({progress})"
    try:
        module.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        found = module_digest(module.read_text(encoding="utf-8"))
    except OSError as error:
        return f"{lead}, and restoring it failed: {error}. {_recoveries(module, backup)}"
    declared = _declared_digest(root, relative)
    if found != declared:
        return (
            f"{lead}. The restored module hashes to {found} and {MANIFEST} declares "
            f"{declared}, so the restore is not the baseline. {_recoveries(module, backup)}"
        )
    backup.unlink(missing_ok=True)
    module.with_name(module.name + LOCK_SUFFIX).unlink(missing_ok=True)
    return (
        f"{lead}. It was restored from its backup and matches its declared digest; this "
        f"run imported the mutant, so run again"
    )


def mutation_state(
    root: Path, *, environ: Optional[Mapping[str, str]] = None,
    now: Optional[datetime] = None,
) -> Optional[str]:
    """Return why a run must not start against this harness, or None.

    Design: ``harness_test_taxonomy.md`` section 15.12.1.

    A module held by a live audit refuses the run unless the run is that
    audit's own. A backup no live process holds is restored and verified,
    and the run refused either way.

    Args:
        root (Path): The root of the harness the run imports.
        environ (Optional[Mapping[str, str]]): The environment, or None for ``os.environ``.
        now (Optional[datetime]): The time to measure progress from, or None.

    Returns:
        Optional[str]: The refusal, carrying ``QC_HARNESS_PREFLIGHT_FAILURE``,
        or None when nothing is under mutation.
    """
    own = (os.environ if environ is None else environ).get(AUDIT_ENV, "")
    refusals: list[str] = []
    for module in _held_modules(root):
        relative = module.relative_to(root).as_posix()
        lock = module.with_name(module.name + LOCK_SUFFIX)
        pid, started = _lock_holder(lock)
        progress = latest_progress(root, relative, now=now) or "no progress log"
        if lock.is_file() and process_alive(pid):
            if own == str(pid):
                continue
            refusals.append(
                f"{_CODE}: {relative} is under mutation by audit process {pid}, started "
                f"{started} ({progress}). End that process or wait for it to finish; this "
                f"run would measure its mutants"
            )
            continue
        if module.with_name(module.name + BACKUP_SUFFIX).is_file():
            refusals.append(_restore(root, module, relative, progress))
        else:
            # A LOCK ALONE, left by a dead audit that had restored its module.
            lock.unlink(missing_ok=True)
    return "\n".join(refusals) or None


def refuse_if_mutating(root: Path) -> None:
    """Abort the session with exit 3 when a harness module is under mutation.

    Args:
        root (Path): The root of the harness the run imports.

    Returns:
        None
    """
    refusal = mutation_state(root)
    if refusal is not None:
        pytest.exit(refusal, returncode=3)
