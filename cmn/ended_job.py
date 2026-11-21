# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Makes a run whose job ended on a failure exit 3, whatever else passed.

Created: 2026-11-21
Last updated: 2026-11-21

This file contains ``watch_job``, which a consumer calls with its pytest
configuration and the run's dispatch session when it builds that session;
``ended_job_lines``, the line its terminal summary leads with when the job
ended; and ``refuse_ended_job``, which its ``pytest_sessionfinish`` calls to
raise the exit status to 3 where a watched session's job ended.

**A job ends on a failure the dispatcher or the judge channel ended it on**
(``execution/job_end.py``): the candidate's code three cases running, five
failures running, an auth error, or a stopped judge. Every case after it
skipped, so the cases that passed before it are not a run's result, and the
exit says so.

**Keyed on the configuration, not global.** A unit case ending a session it
built for itself would otherwise end the run that executes it.

Specified by ``docs/design/tier2_execution.md`` section 8.3.4.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ("ended_job_lines", "refuse_ended_job", "watch_job")

# EACH CONFIGURATION'S SESSIONS, keyed by identity and holding the
# configuration, so an identity is never reused while its entry stands. **Not a
# weak mapping**: a configuration that cannot be weakly referenced would
# otherwise be watched by nothing, and its run would exit 0 after its job ended.
_WATCHED: dict[int, tuple[Any, list[Any]]] = {}


def _sessions_of(config: Any) -> list[Any]:
    """Return the sessions watched for a configuration, none where none are.

    Args:
        config (Any): The run's pytest configuration.

    Returns:
        list[Any]: The watched sessions.
    """
    entry = _WATCHED.get(id(config))
    return entry[1] if entry is not None and entry[0] is config else []


def watch_job(config: Any, session: Any) -> None:
    """Note a run's dispatch session, so the run's finish reads whether its job ended.

    Args:
        config (Any): The run's pytest configuration.
        session (Any): The run's ``DispatchSession``.

    Returns:
        None
    """
    sessions = _WATCHED.setdefault(id(config), (config, []))[1]
    if not any(watched is session for watched in sessions):
        sessions.append(session)


def ended_job_lines(config: Any) -> list[str]:
    """Return the line a run's summary leads with, one per watched job that ended.

    Args:
        config (Any): The run's pytest configuration.

    Returns:
        list[str]: Each names the role, the code, how many cases running it
        failed, and the failure's detail with its status, request id and
        message. Empty while no job has ended.
    """
    lines: list[str] = []
    for session in _sessions_of(config):
        ended = getattr(session, "job_end", None)
        if ended is None:
            continue
        lines.append(
            f"The job ended on the {ended.role}'s {ended.code}, {ended.repeats} cases "
            f"running, and every later case skipped: {ended.detail or ended.code}"
        )
    return lines


def refuse_ended_job(finishing: Any) -> bool:
    """Raise a finishing session's exit status to 3 where its run's job ended.

    Args:
        finishing (Any): The finishing pytest session, whose ``exitstatus`` is
            raised.

    Returns:
        bool: True where a watched job ended. A usage error's or an earlier
        refusal's status is kept, as ``JobState.exit_status`` keeps it.
    """
    ended = [
        session for session in _sessions_of(finishing.config)
        if getattr(session, "job_end", None) is not None
    ]
    for session in ended:
        status = session.exit_status(int(finishing.exitstatus))
        if status != int(finishing.exitstatus):
            logger.error(
                "the job ended on %s, so the run exits %d: %s",
                session.job_end.code, status, session.job_end.detail,
            )
            finishing.exitstatus = status
    return bool(ended)
