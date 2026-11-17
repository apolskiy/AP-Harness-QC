# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""A stand-in pytest item that records the markers and properties a skip adds to it.

Created: 2026-11-16
Last updated: 2026-11-16

This file contains ``LabelledItem``, which ``mqc_uni_missing_artifact.py`` hands
to ``cmn.missing_artifact.skip_for_missing_artifact`` to read the Allure label
markers the skip adds, without an Allure runtime in the session.
"""

from typing import Any


class LabelledItem:
    """A pytest item reduced to what a missing-artifact skip writes to."""

    def __init__(self) -> None:
        """Start with no markers and no properties.

        Returns:
            None
        """
        self.user_properties: list[tuple[str, Any]] = []
        self.nodeid = "tests/sample.py::test_sample"
        self._markers: list[Any] = []

    def add_marker(self, marker: Any) -> None:
        """Record a marker as pytest's item would.

        Args:
            marker (Any): The marker added.

        Returns:
            None
        """
        self._markers.append(marker)

    def labels(self) -> list[tuple[str, str]]:
        """Return each Allure label marker as its type and value, in the order added.

        Returns:
            list[tuple[str, str]]: ``(label_type, value)`` per ``allure_label`` marker.
        """
        return [
            (str(marker.kwargs.get("label_type")), str(marker.args[0]))
            for marker in self._markers
            if marker.name == "allure_label"
        ]
