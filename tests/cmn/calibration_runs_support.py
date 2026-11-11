# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Collected cases carrying markers, for the calibration selection and dependency cases.

Created: 2026-11-10
Last updated: 2026-11-11

This file contains :class:`MarkedItem`, a collected case whose
``get_closest_marker`` answers for the markers it was built with, and
:class:`CollectedCase`, which carries real pytest marks and takes more, so the
dependency cascade reads it as it reads a collected item.

``mqc_uni_calibration_runs.py`` uses them with ``mutation_tool_support.AuditConfig``
to call ``cmn.calibration_runs`` and ``cmn.dependencies`` without a pytest
session.
"""

from typing import Any, Iterator, Optional

import pytest


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


class CollectedCase:
    """A collected case carrying pytest marks, which the cascade can add to and read.

    Attributes:
        name (str): The callable's name, carrying its identifier.
        originalname (str): The same name, as pytest gives an unparametrized case.
        nodeid (str): A node identifier carrying the name.
        config (None): No invocation, so no run opens an inquest.
    """

    def __init__(self, name: str, *markers: str) -> None:
        """Hold the case and the marks it was declared with.

        Args:
            name (str): The callable's name.
            *markers (str): The marker names it is declared with.

        Returns:
            None
        """
        self.name = name
        self.originalname = name
        self.nodeid = f"tests/x.py::T::{name}"
        self.config = None
        self._marks: list[Any] = [getattr(pytest.mark, marker).mark for marker in markers]

    def add_marker(self, marker: Any) -> None:
        """Add a mark, as pytest's item does.

        Args:
            marker (Any): A mark decorator.

        Returns:
            None
        """
        self._marks.append(marker.mark)

    def iter_markers(self, name: Optional[str] = None) -> Iterator[Any]:
        """Yield the marks carrying a name, or every mark.

        Args:
            name (Optional[str]): The marker name, or None for all.

        Yields:
            Any: Each matching mark, in the order added.
        """
        for mark in self._marks:
            if name is None or mark.name == name:
                yield mark

    def get_closest_marker(self, name: str) -> Any:
        """Return the first mark carrying a name.

        Args:
            name (str): The marker name.

        Returns:
            Any: The mark, or None.
        """
        return next(self.iter_markers(name), None)
