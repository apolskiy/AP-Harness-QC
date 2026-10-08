# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Running a nested suite under a bound, because a hang reports nothing.

Specified by ``harness_test_taxonomy.md`` section 14.

**Five cases spawn a nested pytest** to observe something the parent process
cannot see about itself: a dependency skip, a collection reordering, a
published artifact, a ``--tests-file`` miss. Each was unbounded until
2026-10-05, when a Windows job was cancelled 22 minutes into a run that
reported ``failure`` with no failing job and no log.

**A bound turns the worst failure shape into an ordinary one.** A hang arrives
as an absence after the longest possible delay and reads as an environmental
fault on whichever platform stalled; an expiry arrives as a named failure with
the command and the budget in it.
"""

import subprocess
from pathlib import Path
from typing import Final, Optional, Sequence

import pytest

# TWO ORDERS OF MAGNITUDE above the 3.4s worst case observed locally, and two
# below the 22 minute hang this exists to prevent. **Generous on purpose**: a
# bound tuned close to the observed duration converts a slow runner into a red,
# which relocates flakiness rather than removing it.
NESTED_SUITE_TIMEOUT: Final[float] = 300.0


def run_bounded(
    command: Sequence[str],
    cwd: Path,
    timeout: float = NESTED_SUITE_TIMEOUT,
    env: Optional[dict[str, str]] = None,
) -> subprocess.CompletedProcess[str]:
    """Run a nested suite, failing the case rather than hanging it.

    **``stdin`` is closed explicitly.** pytest has replaced the standard
    handles by the time a case runs, and a child inheriting a replaced handle
    can block on Windows waiting for input nobody will send.

    Args:
        command (Sequence[str]): The argument vector, never a shell string.
        cwd (Path): The working directory for the child.
        timeout (float): The budget in seconds.
        env (Optional[dict]): A complete environment, or ``None`` to inherit.

    Returns:
        subprocess.CompletedProcess[str]: The finished child, whatever its exit
        code. **``check`` is false**, because a nested suite is expected to fail
        in most of these cases: its failure is the evidence.

    Raises:
        Failed: With ``QC_HARNESS_SUBPROCESS_TIMEOUT`` when the budget expires,
            naming the command and the bound. **Our defect, never a finding
            about a model**, so it carries a harness code.
    """
    try:
        return subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as expired:
        pytest.fail(
            f"QC_HARNESS_SUBPROCESS_TIMEOUT: the nested suite did not finish "
            f"within {timeout:.0f}s, so this case bounded a hang instead of "
            f"waiting for a runner to cancel the job. Command: "
            f"{' '.join(str(part) for part in command)}"
        )
        raise AssertionError("unreachable") from expired
