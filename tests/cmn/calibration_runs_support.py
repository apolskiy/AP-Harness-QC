# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""A collected case carrying named markers, for the calibration selection cases.

Created: 2026-11-10
Last updated: 2026-11-10

This file contains :class:`MarkedItem`, a collected case whose
``get_closest_marker`` answers for the markers it was built with.

``mqc_uni_calibration_runs.py`` uses it with ``mutation_tool_support.AuditConfig``
to call ``cmn.calibration_runs.deselect_unrequested_calibration`` without a
pytest session.
"""

from typing import Any


class MarkedItem:
    """A collected case, carrying its name and the markers it declares."""

    def __init__(self, name: str, *markers: str) -> None:
        """Hold the case.

        Args:
            name (str): The callable's name, carrying its identifier.
            *markers (str): The marker names it carries.

        Returns:
            None
        """
        self.name = name
        self.nodeid = f"tests/x.py::T::{name}"
        self._markers = frozenset(markers)

    def get_closest_marker(self, name: str) -> Any:
        """Return the marker asked for, where the case carries it.

        Args:
            name (str): The marker name.

        Returns:
            Any: A marker naming itself, or None.
        """
        return name if name in self._markers else None
