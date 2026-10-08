# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""An item double for the cascade cases, in a sibling module.

A case module holds only cases (``harness_test_taxonomy.md`` section 13), so the item
double the cascade-policy cases need lives here.

**It carries a mode and its declared dependencies**, which is what the cascade
reads: whether to probe comes from the invocation, and what to wait for comes
from the marker.
"""

from types import SimpleNamespace
from typing import Any


def cascade_item(name: str, mode: str, depends: tuple[str, ...] = ()) -> Any:
    """Return an item double carrying a mode and its declared dependencies.

    Args:
        name (str): The test name.
        mode (str): What ``--mode`` supplied.
        depends (tuple): The identifiers it presupposes.

    Returns:
        Any: The double, recording any marker added to it.
    """
    added: list[Any] = []
    markers = [SimpleNamespace(name="depends_on", args=depends)] if depends else []
    return SimpleNamespace(
        name=name,
        nodeid=f"tests/{name}",
        config=SimpleNamespace(getoption=lambda flag, default="": mode),
        own_markers=markers,
        iter_markers=lambda name=None: [
            marker for marker in markers
            if name is None or marker.name == name
        ],
        add_marker=added.append,
        added=added,
        get_closest_marker=lambda wanted: next(
            (marker for marker in markers if marker.name == wanted), None
        ),
    )
