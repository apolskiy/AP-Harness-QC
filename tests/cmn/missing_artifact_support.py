# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Stand-ins for the cases that feed a reader a missing or malformed artifact.

Created: 2026-11-16
Last updated: 2026-11-17

This file contains ``LabelledItem``, which ``mqc_uni_missing_artifact.py`` hands
to ``cmn.missing_artifact.skip_for_missing_artifact`` to read the Allure label
markers the skip adds, without an Allure runtime in the session;
``ArtifactItem``, a cascade item a missing-artifact skip can write to;
``carry_config``, a configuration naming a carry file; ``carry_provenance``,
the provenance such a band stamps; ``MALFORMED_CARRY_FILES`` and
``write_malformed_carry``, one body per way a carry file can be unusable;
``carry_population``, a dependent of a carried foundation beside a case resting
on nothing; and ``band_outcomes``, which runs the cascade's session start,
collection and setup over a population.
"""

import json
import os
import platform
from pathlib import Path
from typing import Any, Final, Optional

import pytest

from cmn.dependencies import (
    adopt_prerequisites,
    arrange_dependencies,
    enforce_dependencies,
    reset_dependency_state,
)
from cmn.prerequisites import Provenance
from tests.cmn.selection_support import SimulatedConfig, SimulatedItem

# ONE BODY PER WAY A CARRY FILE CAN BE UNUSABLE, each refused by the reader
# (`cmn_verdict_and_cli.md` section 10.28.8). The provenance is filled in by
# the caller where a body needs one.
MALFORMED_CARRY_FILES: Final[dict[str, str]] = {
    "empty": "",
    "not JSON": "{outcomes: yes",
    "not a mapping": "[]",
    "no provenance": '{"outcomes": {"90003": true}}',
    "no outcomes": '{"provenance": PROVENANCE}',
    "outcomes not a mapping": '{"provenance": PROVENANCE, "outcomes": ["90003"]}',
    "held not a boolean": '{"provenance": PROVENANCE, "outcomes": {"90003": "false"}}',
}


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


class ArtifactItem(SimulatedItem):
    """A cascade item that a missing-artifact skip can write its properties to."""

    def __init__(
        self, name: str, *, base: bool = False, depends: tuple = (),
        priority: Optional[int] = None,
    ) -> None:
        """Build the item with no properties and no added markers.

        Args:
            name (str): The test callable's name.
            base (bool): Whether it is marked foundational.
            depends (tuple): Identifiers it declares a dependency on.
            priority (Optional[int]): Its band.

        Returns:
            None
        """
        super().__init__(name, base=base, depends=depends, priority=priority)
        self.user_properties: list[tuple[str, Any]] = []
        self.nodeid = f"tests/sample.py::{name}"
        self.added: list[Any] = []

    def add_marker(self, marker: Any) -> None:
        """Record a marker as pytest's item would.

        Args:
            marker (Any): The marker added.

        Returns:
            None
        """
        self.added.append(marker)

    def artifact_properties(self) -> dict[str, str]:
        """Return the missing-artifact properties the item carries.

        Returns:
            dict[str, str]: Property name to value, for the ``mqc_artifact_`` ones.
        """
        return {
            str(name): str(value) for name, value in self.user_properties
            if str(name).startswith("mqc_artifact_")
        }


def carry_config(path: str) -> SimulatedConfig:
    """Return the configuration of a replay band on gemini naming a carry file.

    Args:
        path (str): The carry file the band names.

    Returns:
        SimulatedConfig: Answering ``--carry-outcomes``, ``--engine``,
        ``--mode`` and ``--priority``.
    """
    return SimulatedConfig({
        "--carry-outcomes": path, "--engine": "gemini", "--mode": "replay", "--priority": "2",
    })


def carry_provenance(**moved: str) -> Provenance:
    """Return the provenance the band of :func:`carry_config` stamps, a field optionally moved.

    Args:
        **moved (str): Fields to replace.

    Returns:
        Provenance: What the band compares a carry file against.
    """
    fields = {
        "rule_set_hash": "",
        "code_ref": os.environ.get("MQC_CODE_REF", ""),
        "case_ref": os.environ.get("MQC_CASE_REF", ""),
        "engine": "gemini",
        "mode": "replay",
        "platform": platform.system(),
        "band": "1",
    }
    fields.update(moved)
    return Provenance(**fields)


CARRY_DEPENDENT: Final[str] = "MQC_EVL_EVAL_134000_rests_on_a_carried_foundation"
CARRY_INDEPENDENT: Final[str] = "MQC_EVL_EVAL_134111_rests_on_nothing"


def carry_population() -> list[ArtifactItem]:
    """Return a dependent of carried foundation 90003 and a case resting on nothing.

    Returns:
        list[ArtifactItem]: The two items, as a P2 band collects them.
    """
    return [
        ArtifactItem(CARRY_DEPENDENT, priority=2, depends=("90003",)),
        ArtifactItem(CARRY_INDEPENDENT, priority=2),
    ]


def write_malformed_carry(path: Path, body: str) -> Path:
    """Write one of :data:`MALFORMED_CARRY_FILES`, its provenance filled in.

    Args:
        path (Path): Where to write.
        body (str): The body, ``PROVENANCE`` standing for this band's provenance.

    Returns:
        Path: The path written.
    """
    provenance = json.dumps(carry_provenance().as_fields())
    path.write_text(body.replace("PROVENANCE", provenance), encoding="utf-8")
    return path


def band_outcomes(config: SimulatedConfig, items: list[Any]) -> dict[str, str]:
    """Run the cascade's session start, collection and setup over the items.

    The cascade state is reset before and after, so a case leaves none behind.

    Args:
        config (SimulatedConfig): The band's configuration.
        items (list): The collected items.

    Returns:
        dict[str, str]: Item name to ``runs``, or to the message it skipped with.
    """
    reset_dependency_state()
    try:
        adopt_prerequisites(config)
        arrange_dependencies(items)
        outcomes: dict[str, str] = {}
        for item in items:
            try:
                enforce_dependencies(item)
            except pytest.skip.Exception as skipped:
                outcomes[item.name] = str(skipped)
                continue
            outcomes[item.name] = "runs"
        return outcomes
    finally:
        reset_dependency_state()
