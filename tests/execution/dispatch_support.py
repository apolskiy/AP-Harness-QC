# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Support the dispatch cases share: a clock that never waits, and a plan builder.

Created: 2026-10-30
Last updated: 2026-10-30

This file contains ``FakeClock``, a monotonic clock that advances only when a
case tells it to, and ``plan_for``, which builds a :class:`DispatchPlan` rooted
in a temporary fixture store. Both are used by every collected module that
dispatches a case, which is why they sit here rather than in one of them.

**It carries no case and no fixture.** A ``@pytest.fixture`` is discovered in the
module that declares it, so each collected module keeps its own two-line wiring
and calls these. Support defined inside a collected case module is reported by
``MQC_CMN_UNI_112328``, and this file discharges the declaration
``config/support_extraction.yaml`` carried for ``mqc_uni_dispatch.py``.

Specified by ``docs/design/harness_test_taxonomy.md`` section 13.
"""

from typing import Any

from execution.dispatch import DispatchPlan


class FakeClock:
    """A monotonic clock that advances only when asked.

    Real time would make a spacing case a sleeping case, and a bounded-backoff
    case a case that sleeps repeatedly.

    Attributes:
        now (float): The current reading, in seconds.
    """

    def __init__(self) -> None:
        """Start the clock at zero.

        Returns:
            None
        """
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        """Return the current reading.

        Returns:
            float: Seconds since the clock started.
        """
        return self.now

    def sleep(self, seconds: float) -> None:
        """Advance the clock instead of waiting.

        Args:
            seconds (float): How long the dispatcher asked to wait.

        Returns:
            None
        """
        self.slept.append(seconds)
        self.now += seconds


def plan_for(tmp_path: Any, mode: str = "live", record: bool = False) -> DispatchPlan:
    """Build a dispatch plan rooted in a temporary fixture store.

    Args:
        tmp_path (Any): pytest's temporary directory.
        mode (str): ``live`` or ``replay``.
        record (bool): Whether a live response is recorded.

    Returns:
        DispatchPlan: The plan.
    """
    return DispatchPlan(mode=mode, fixture_root=tmp_path, record=record)
