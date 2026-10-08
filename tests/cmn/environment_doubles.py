# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The doubles `mqc_uni_environments.py` drives the environment scope with.

**A sibling module collection does not reach**, per `MQC_CMN_UNI_112328`: a
case module holds cases, and a double defined beside one is support code the
suite would otherwise try to collect.

Each class carries only the surface the code under test reads: a marker's args
and kwargs, an item's identifier and markers, a hook that records what it was
handed, and a session whose exit status the gate may raise.
"""

from typing import Any


class Marker:
    """One `environment` marker as pytest reports it."""

    def __init__(self, *scopes: str, sibling: str = "") -> None:
        """Hold the declared scopes and the sibling.

        Args:
            *scopes: The declared scope names.
            sibling (str): The sibling directory, where one is named.

        Returns:
            None
        """
        self.args = scopes
        self.kwargs = {"sibling": sibling}


class Item:
    """A collected item carrying whatever markers the case gives it."""

    def __init__(self, nodeid: str, *markers: Marker) -> None:
        """Hold the identifier and the markers.

        Args:
            nodeid (str): The node identifier.
            *markers: The `environment` markers it declares.

        Returns:
            None
        """
        self.nodeid = nodeid
        self.name = nodeid.rsplit("::", 1)[-1]
        self._markers = markers

    def iter_markers(self, name: str = "") -> tuple[Marker, ...]:
        """Return the declared markers.

        Args:
            name (str): The marker name pytest asks for.

        Returns:
            tuple: The markers, which are all of this one kind.
        """
        return self._markers if name in ("", "environment") else ()


class Hook:
    """The deselection hook, recording what it was handed."""

    def __init__(self) -> None:
        """Start with nothing deselected.

        Returns:
            None
        """
        self.deselected: list[Any] = []

    def pytest_deselected(self, items: list[Any]) -> None:
        """Record the deselection.

        Args:
            items (list): What was dropped.

        Returns:
            None
        """
        self.deselected.extend(items)


class Config:
    """Just enough configuration to carry the hook."""

    def __init__(self) -> None:
        """Hold a recording hook.

        Returns:
            None
        """
        self.hook = Hook()


class Report:
    """One skipped report as the terminal reporter holds it."""

    def __init__(self, nodeid: str) -> None:
        """Hold the identifier.

        Args:
            nodeid (str): The node identifier.

        Returns:
            None
        """
        self.nodeid = nodeid


class Reporter:
    """The terminal reporter's statistics, with skips in them."""

    def __init__(self, *skipped: str) -> None:
        """Hold the skipped reports.

        Args:
            *skipped: Node identifiers that skipped.

        Returns:
            None
        """
        self.stats = {"skipped": [Report(nodeid) for nodeid in skipped]}


class Manager:
    """A plugin manager returning one reporter."""

    def __init__(self, reporter: Any) -> None:
        """Hold the reporter.

        Args:
            reporter (Any): What `get_plugin` returns.

        Returns:
            None
        """
        self._reporter = reporter

    def get_plugin(self, name: str) -> Any:
        """Return the reporter for its own name.

        Args:
            name (str): The plugin asked for.

        Returns:
            Any: The reporter, or None for anything else.
        """
        return self._reporter if name == "terminalreporter" else None


class Session:
    """A session whose exit status the gate may raise."""

    def __init__(self, reporter: Any, exitstatus: int = 0) -> None:
        """Hold the reporter and the status.

        Args:
            reporter (Any): The terminal reporter.
            exitstatus (int): What pytest would exit with.

        Returns:
            None
        """
        self.config = type("_Cfg", (), {"pluginmanager": Manager(reporter)})()
        self.exitstatus = exitstatus
