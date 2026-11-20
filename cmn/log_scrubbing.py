# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Keeping credential values and URL query strings out of text, the log included.

Created: 2026-11-20
Last updated: 2026-11-20

This file contains ``REDACTED``, what a removed value is replaced with;
``credential_values``, the values of the environment variables whose names
read as credentials; ``scrub_text``, which replaces those values and removes
the query string of every URL in a text; and ``install_log_scrubbing`` with
``log_scrubbing_installed``, which put ``scrub_text`` in front of every log
record when it is created, and report whether it is there.

It runs at configuration, installed by ``cmn.pytest_support`` before any case,
and from then on for every record any logger creates, so a key an SDK or httpx
would print never reaches a handler. ``execution.wire`` reads the same values
to redact a recorded header by its value.

**By value, because a log message has no field names to match.** A record
factory rather than a filter on the handlers, because pytest attaches its
handlers per phase, after configuration.

Specified by ``docs/design/tier2_execution.md`` sections 7.15.2 and 7.15.5.
"""

import logging
import os
import re
from typing import Any, Callable, Final, Mapping, Optional

from cmn.credentials import credential_shaped_name

REDACTED: Final[str] = "[REDACTED]"

# A VALUE THIS SHORT IS NOT A CREDENTIAL, and replacing it would rewrite
# ordinary words wherever they appear: a variable set to "1" would turn every
# "1" in the log into the marker.
_SHORTEST_CREDENTIAL: Final[int] = 8

# A URL AND ITS QUERY STRING. The query ends at whitespace or a quote, which
# is where a URL quoted inside a message or a repr ends.
_QUERY: Final[re.Pattern] = re.compile(r"(https?://[^\s?#'\"<>]+)\?[^\s'\"<>]*")

# The marker an installed factory carries, so installing twice wraps once.
_MARKER: Final[str] = "_mqc_scrubbing"


def credential_values(environ: Optional[Mapping[str, str]] = None) -> tuple[str, ...]:
    """Return the values of every environment variable whose name reads as a credential.

    Args:
        environ (Optional[Mapping]): The environment, or the process's own.

    Returns:
        tuple[str, ...]: The values, longest first so a key containing a
        shorter one is replaced whole. Values shorter than eight characters
        are left out.
    """
    source = os.environ if environ is None else environ
    found = {
        str(value) for name, value in source.items()
        if credential_shaped_name(str(name)) and len(str(value)) >= _SHORTEST_CREDENTIAL
    }
    return tuple(sorted(found, key=len, reverse=True))


def scrub_text(text: str, environ: Optional[Mapping[str, str]] = None) -> str:
    """Return the text with every credential value replaced and every query string removed.

    Args:
        text (str): The text.
        environ (Optional[Mapping]): The environment the credential values
            are read from, or the process's own.

    Returns:
        str: The scrubbed text.
    """
    cleaned = _QUERY.sub(r"\1", text)
    for value in credential_values(environ):
        cleaned = cleaned.replace(value, REDACTED)
    return cleaned


def _scrubbing(previous: Callable[..., logging.LogRecord]) -> Callable[..., logging.LogRecord]:
    """Return a record factory scrubbing what the previous factory builds.

    Args:
        previous (Callable): The factory being wrapped.

    Returns:
        Callable: The scrubbing factory, carrying the marker.
    """

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        """Build a record, then scrub its rendered message.

        Args:
            *args (Any): As ``logging.LogRecord`` takes them.
            **kwargs (Any): As ``logging.LogRecord`` takes them.

        Returns:
            logging.LogRecord: The record, its message scrubbed where it
            carried anything to scrub.
        """
        record = previous(*args, **kwargs)
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            # A MESSAGE THAT CANNOT BE RENDERED is logging's own error to
            # report, at emit time; scrubbing it here would hide that.
            return record
        cleaned = scrub_text(message)
        if cleaned != message:
            record.msg = cleaned
            record.args = ()
        return record

    setattr(factory, _MARKER, True)
    return factory


def install_log_scrubbing() -> None:
    """Put the scrubbing in front of every log record from now on. Installing twice wraps once.

    Returns:
        None
    """
    if log_scrubbing_installed():
        return
    logging.setLogRecordFactory(_scrubbing(logging.getLogRecordFactory()))


def log_scrubbing_installed() -> bool:
    """Report whether every log record is scrubbed when it is created.

    Returns:
        bool: True when the current record factory is the scrubbing one.
    """
    return bool(getattr(logging.getLogRecordFactory(), _MARKER, False))
