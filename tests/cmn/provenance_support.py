# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Stand-ins for pytest's configuration and a served-facts reader.

Created: 2026-10-29
Last updated: 2026-10-29

This file contains :class:`Config`, which carries the parsed options a run's
provenance reads, and :class:`Reader`, a served-facts reader that records
whether anything asked it.

``mqc_uni_provenance.py`` feeds these to ``cmn.pytest_support.adopt_provenance``
in place of a real invocation. `pytest.ini` collects only `mqc_*.py`, so nothing
here is collected.

**The reader records rather than returns only.** The property that matters most
is that a run which is not live asks no provider, and a run that asked and
discarded the answer would produce identical fields while spending the call. A
reader that only answered could not separate the two.
"""

from typing import Any


class Option:
    """The attributes of pytest's parsed options a run's provenance reads."""

    def __init__(self, **values: Any) -> None:
        """Set each named option.

        Args:
            **values (Any): The option names and their values.

        Returns:
            None
        """
        for name, value in values.items():
            setattr(self, name, value)


class Config:
    """Enough of pytest's configuration to drive the provenance functions."""

    def __init__(self, **values: Any) -> None:
        """Build a configuration carrying the given options.

        Args:
            **values (Any): The option names and their values.

        Returns:
            None
        """
        self.option = Option(**values)


class Reader:
    """A served-facts reader that records whether anything asked it."""

    def __init__(self, served: dict[str, str]) -> None:
        """Hold what to return and an empty record of calls.

        Args:
            served (dict): What to return when asked.

        Returns:
            None
        """
        self.served = served
        self.asked: list[tuple[str, str]] = []

    def __call__(self, engine: str, model: str) -> dict[str, str]:
        """Record the question and answer it.

        Args:
            engine (str): The engine asked about.
            model (str): The model asked about.

        Returns:
            dict[str, str]: What this reader was built with.
        """
        self.asked.append((engine, model))
        return dict(self.served)
