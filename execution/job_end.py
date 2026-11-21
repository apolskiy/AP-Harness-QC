# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""When a run's job ends on a failure, and what each failure says about itself.

Created: 2026-11-21
Last updated: 2026-11-21

This file contains ``JobEnd``, the record of the failure that ended a job: the
role that failed, its code, how many times running, and its detail;
``JobState``, the part of a run's ``DispatchSession`` that holds it, counts the
candidate's same-code streak, and turns an ended job's exit status into 3; and
``failure_detail``, which states one failure as its code, its role and engine,
then the status, request identifier, date and the provider's own message read
from the failed HTTP attempt.

**The dispatcher and the judge channel both end a job here.** The candidate
breaker in ``execution/dispatch.py`` ends it on one code three cases running,
five failures running of any code, or an auth error; the judge channel ends it
when the judge stops. Once ended, every later dispatch is a skip naming the
failure, sent to no provider, and the run exits 3 whatever else passed.

**An HTTP failure names no party.** The detail says what came back and from
where; whether the harness, the model or provider, a proxy or an edge caused it
is for the investigation the ended job asks for.

Specified by ``docs/design/tier2_execution.md`` sections 7.15.6 and 8.3.4.
"""

import json
from dataclasses import dataclass
from typing import Any, Final, Iterable, Optional

from execution.wire import WireAttempt

__all__ = ("JobEnd", "JobState", "SAME_CODE_THRESHOLD", "failed_attempts", "failure_detail")

# ONE CODE ON THIS MANY CASES RUNNING ENDS THE JOB (section 8.3.4). Two could
# be coincidence; the third is a request of unknown cost sent to confirm it.
SAME_CODE_THRESHOLD: Final[int] = 3

# THE STATUS AN ENDED JOB'S RUN EXITS WITH: nothing trustworthy was measured.
_ENDED_EXIT: Final[int] = 3

# A RUN THAT EXITED ON A USAGE ERROR KEEPS ITS STATUS, being a different
# statement (``cmn_verdict_and_cli.md`` section 3).
_KEPT_EXITS: Final[frozenset[int]] = frozenset({2, 3, 4})

# HEADERS NAMING THE REQUEST, in the order a provider is likeliest to send them.
_REQUEST_ID_HEADERS: Final[tuple[str, ...]] = (
    "x-request-id", "request-id", "x-goog-request-id", "cf-ray",
)


@dataclass(frozen=True)
class JobEnd:
    """The failure that ended a run's job.

    Attributes:
        role (str): ``candidate`` or ``judge``.
        code (str): The harness code it ended on.
        repeats (int): How many cases running failed toward it, 1 for a
            failure that ends a job at once.
        detail (str): The failure as :func:`failure_detail` states it.
    """

    role: str
    code: str
    repeats: int
    detail: str


def failed_attempts(attempts: Iterable[WireAttempt]) -> tuple[WireAttempt, ...]:
    """Return the attempts that failed: a non-2xx status, or no response.

    Args:
        attempts (Iterable[WireAttempt]): The attempts recorded.

    Returns:
        tuple[WireAttempt, ...]: Those failed, in the order sent.
    """
    return tuple(
        attempt for attempt in attempts
        if attempt.status is None or not 200 <= attempt.status < 300
    )


def _provider_message(attempt: WireAttempt) -> str:
    """Return what the provider said, from its error body, or the transport's message.

    Args:
        attempt (WireAttempt): A failed attempt.

    Returns:
        str: The ``error.message`` or ``message`` of a JSON body, the body
        itself otherwise, or the transport error's message.
    """
    if not attempt.error_body:
        return attempt.error_message
    try:
        parsed: Any = json.loads(attempt.error_body)
    except ValueError:
        return attempt.error_body
    if isinstance(parsed, list) and parsed:
        parsed = parsed[0]
    if isinstance(parsed, dict):
        inner = parsed.get("error")
        if isinstance(inner, dict) and inner.get("message"):
            return str(inner["message"])
        if isinstance(inner, str) and inner:
            return inner
        if parsed.get("message"):
            return str(parsed["message"])
    return attempt.error_body


def failure_detail(
    code: str, role: str, engine: str, attempts: Iterable[WireAttempt] = ()
) -> str:
    """State one failure: its code, role and engine, and what the last failed attempt carried.

    Args:
        code (str): The harness code.
        role (str): ``candidate`` or ``judge``.
        engine (str): The engine that failed.
        attempts (Iterable[WireAttempt]): The attempts the failure made.

    Returns:
        str: ``<code>: <role> <engine>, status <n>, request-id <id>, date
        <date>: <message>``, each part present only where the attempt carried
        it.
    """
    stated = f"{code}: {role} {engine}"
    failed = failed_attempts(attempts)
    if not failed:
        return stated
    last = failed[-1]
    parts = [stated]
    if last.status is not None:
        parts.append(f"status {last.status}")
    elif last.error:
        parts.append(last.error)
    request_id = next(
        (last.response_headers[name] for name in _REQUEST_ID_HEADERS
         if last.response_headers.get(name)),
        "",
    )
    if request_id:
        parts.append(f"request-id {request_id}")
    if last.response_headers.get("date"):
        parts.append(f"date {last.response_headers['date']}")
    message = _provider_message(last)
    return f"{', '.join(parts)}: {message}" if message else ", ".join(parts)


@dataclass
class JobState:
    """Whether a run's job has ended, and the candidate's same-code streak toward it.

    The job-ending half of ``DispatchSession``, which inherits it.

    Attributes:
        job_end (Optional[JobEnd]): The failure that ended the job, or None.
        streak_code (str): The code of the candidate's current same-code streak.
        streak_repeats (int): How many cases running carried it.
    """

    job_end: Optional[JobEnd] = None
    streak_code: str = ""
    streak_repeats: int = 0

    def end_job(self, role: str, code: str, repeats: int, detail: str) -> JobEnd:
        """End the job on a failure, keeping the first failure where it already ended.

        Args:
            role (str): ``candidate`` or ``judge``.
            code (str): The harness code.
            repeats (int): How many cases running failed toward it.
            detail (str): The failure, as :func:`failure_detail` states it.

        Returns:
            JobEnd: The failure the job ended on.
        """
        if self.job_end is None:
            self.job_end = JobEnd(role=role, code=code, repeats=repeats, detail=detail)
        return self.job_end

    def note_streak(self, code: str) -> int:
        """Extend the same-code streak by one failure, or start a new one.

        Args:
            code (str): The failed case's code.

        Returns:
            int: The streak's length after this failure.
        """
        if code == self.streak_code:
            self.streak_repeats += 1
        else:
            self.streak_code, self.streak_repeats = code, 1
        return self.streak_repeats

    def reset_streak(self) -> None:
        """Clear the same-code streak, as an answered case does.

        Returns:
            None
        """
        self.streak_code, self.streak_repeats = "", 0

    def exit_status(self, status: int) -> int:
        """Return the exit status a run finishing with ``status`` takes.

        Args:
            status (int): The status the run would otherwise exit with.

        Returns:
            int: 3 where the job ended and the run would otherwise exit 0 or 1;
            the status unchanged otherwise.
        """
        if self.job_end is None or status in _KEPT_EXITS:
            return status
        return _ENDED_EXIT
