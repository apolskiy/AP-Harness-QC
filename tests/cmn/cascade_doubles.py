# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""A stand-in pytest item for the dependency cascade cases.

Created: 2026-10-08
Last updated: 2026-10-21

This file contains ``cascade_item``, which returns an item double carrying an
invocation and the dependencies its marker declares. The cases in
``mqc_uni_cascade_policy.py`` hand it to the cascade functions in
``cmn.dependencies`` and ``cmn.emission`` in place of a collected item.

**It carries a mode and its declared dependencies**, which is what the cascade
reads: whether to dispatch unattributed comes from the invocation, and what to wait for comes
from the marker.

It lives in a sibling module because a case module holds only cases
(``harness_test_taxonomy.md`` section 13).
"""

from types import SimpleNamespace
from typing import Any


def cascade_item(
    name: str,
    mode: str,
    depends: tuple[str, ...] = (),
    *,
    fill_gaps: bool = False,
) -> Any:
    """Return an item double carrying an invocation and its dependencies.

    Args:
        name (str): The test name.
        mode (str): What ``--mode`` supplied.
        depends (tuple): The identifiers it presupposes.
        fill_gaps (bool): What ``--fill-gaps`` supplied. **Read since
            2026-10-11**, when only a gap-filling live run dispatches a
            dependent whose foundation did not hold (design section 10.28.2.3).

    Returns:
        Any: The double, recording any marker added to it. **A marker added is
        visible to `iter_markers`**, because the reporting hook reads the
        cascade's own marker back and a double that only appended would let a
        case pass against a marker nothing could find.
    """
    added: list[Any] = []
    markers = [SimpleNamespace(name="depends_on", args=depends)] if depends else []

    def _option(flag: str, default: Any = "") -> Any:
        """Answer for the two flags the cascade reads."""
        if flag == "--fill-gaps":
            return fill_gaps
        if flag == "--mode":
            return mode
        return default

    def _record(marker: Any) -> None:
        """Record a marker and make it findable, as pytest's does."""
        added.append(marker)
        markers.append(
            SimpleNamespace(
                name=getattr(marker, "name", ""),
                args=tuple(getattr(marker, "args", ())),
            )
        )

    return SimpleNamespace(
        name=name,
        nodeid=f"tests/{name}",
        config=SimpleNamespace(getoption=_option),
        own_markers=markers,
        iter_markers=lambda name=None: [
            marker for marker in markers
            if name is None or marker.name == name
        ],
        add_marker=_record,
        added=added,
        get_closest_marker=lambda wanted: next(
            (marker for marker in markers if marker.name == wanted), None
        ),
    )
