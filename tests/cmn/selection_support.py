# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The pytest stand-ins every selection case needs.

Shared by ``mqc_uni_dependency.py`` and ``mqc_uni_selection.py``.

**Extracted 2026-10-03**, when a second module needed the same two doubles. A
copy would have been reported by pylint's duplicate-code check, and the copy
that was not reported is the one that drifts: a double answering ``getoption``
differently from the one the band cases use would make two modules disagree
about what pytest does.

Holds no case of its own, so it carries no identifier.
"""

from typing import Any, Optional

import pytest


class FakeConfig:
    """The parts of pytest's configuration the band filter reads.

    Attributes:
        deselected (list): Items the filter reported as deselected.
    """

    def __init__(self, supplied: dict[str, Any]) -> None:
        """Build a stand-in answering ``getoption`` from what was supplied.

        **Keyed by the flag as a user types it**, dashes included, so a case
        names the thing under test rather than the field it lands in. That is
        also what `MQC_CMN_UNI_112522` looks for: a case exercising an option
        through its record alone leaves the flag ungreppable, and the flag is
        what a reader has.

        Args:
            supplied (dict): Option values, keyed by flag including dashes.

        Returns:
            None
        """
        self._supplied = supplied
        self.deselected: list[Any] = []
        self.hook = self

    def getoption(self, name: str, default: Any = None) -> Any:
        """Return a supplied option value.

        Args:
            name (str): The flag, with or without leading dashes.
            default (Any): What to return when it was not supplied.

        Returns:
            Any: The value.
        """
        wanted = f"--{name.lstrip('-').replace('_', '-')}"
        return self._supplied.get(wanted, default)

    def pytest_deselected(self, items: list[Any]) -> None:
        """Record what the filter deselected.

        Args:
            items (list): The deselected items.

        Returns:
            None
        """
        self.deselected.extend(items)



class FakeItem:
    """The parts of a pytest item the cascade reads.

    Attributes:
        name (str): The test callable's name.
    """

    def __init__(
        self, name: str, *, base: bool = False, depends: tuple = (),
        priority: Optional[int] = None,
    ) -> None:
        """Build a stand-in carrying the markers the cascade looks for.

        Args:
            name (str): The test callable's name.
            base (bool): Whether it is marked foundational.
            depends (tuple): Identifiers it declares a dependency on.
            priority (Optional[int]): The band it belongs to, absent on a
                precondition, which carries none.

        Returns:
            None
        """
        self.name = name
        self._base = base
        self._depends = depends
        self._priority = priority

    def get_closest_marker(self, marker_name: str) -> Optional[Any]:
        """Return the named marker, or ``None``.

        Args:
            marker_name (str): Which marker.

        Returns:
            Optional[Any]: The marker when present.
        """
        if marker_name == "base" and self._base:
            return pytest.mark.base
        if marker_name == "priority" and self._priority is not None:
            return pytest.mark.priority(self._priority)
        return None

    def iter_markers(self, name: str) -> list[Any]:
        """Return every instance of the named marker.

        Args:
            name (str): Which marker.

        Returns:
            list: The markers, empty when none apply.
        """
        if name != "depends_on" or not self._depends:
            return []
        return [pytest.mark.depends_on(*self._depends).mark]
