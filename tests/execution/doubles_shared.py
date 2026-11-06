# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""What every provider's response doubles share: the invocation log and the default values.

Created: 2026-11-06
Last updated: 2026-11-06

This file contains :class:`MQCToolWasExecuted`, raised when an adapter acts on
a tool call; :class:`InvocationLog`, which a double records an execution
attempt on; and the default text, model and token counts a double carries when
a case does not set them.

:mod:`tests.execution.provider_doubles` and
:mod:`tests.execution.responses_doubles` build their doubles from these, so a
Responses double and a Chat Completions double refuse a tool execution the same
way and report the same counts. `pytest.ini` collects only `mqc_*.py`, so
nothing here is collected.
"""

from dataclasses import dataclass, field
from typing import Final

DEFAULT_TEXT: Final[str] = "The answer, grounded in the supplied document."
DEFAULT_MODEL: Final[str] = "served-build-001"
DEFAULT_TOKENS: Final[int] = 42

# DISTINCT FROM EACH OTHER ON PURPOSE. Equal defaults would let an adapter
# read the wrong count and still pass.
DEFAULT_INPUT: Final[int] = 137
DEFAULT_THINKING: Final[int] = 41
DEFAULT_CACHED: Final[int] = 19


class MQCToolWasExecuted(AssertionError):
    """An adapter invoked a tool the model merely intended to call.

    Raised by the doubles rather than recorded quietly, because executing a
    model's tool call is the one failure in Tier 2 that acts on the world.
    """


@dataclass
class InvocationLog:
    """What an adapter tried to execute, which must always be nothing.

    Attributes:
        invocations (list): Tool names an adapter attempted to run.
    """

    invocations: list[str] = field(default_factory=list)

    def executed(self, tool_name: str) -> None:
        """Record and refuse an execution attempt.

        Args:
            tool_name (str): The tool an adapter tried to run.

        Returns:
            None

        Raises:
            MQCToolWasExecuted: Always. Tool usage is behaviour under test.
        """
        self.invocations.append(tool_name)
        raise MQCToolWasExecuted(
            f"the adapter executed {tool_name}, which A9 forbids: tool-call intent "
            f"is the recorded artifact and is never acted on"
        )
