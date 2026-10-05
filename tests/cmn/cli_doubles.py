# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Stand-ins for the pytest objects the CLI cases drive.

Specified by ``test_taxonomy.md`` section 13.

**Extracted 2026-10-05**, when ``mqc_uni_cli.py`` stood at 965 lines against
the thousand-line ceiling. These are doubles, which is a subject of its own:
``provider_doubles.py`` and ``judge_doubles.py`` are the same shape, and this
module was the one place a double still sat beside the cases that use it.

**Public names, deliberately.** A support module is an interface, and a leading
underscore on something another module imports says the opposite of what is
true.
"""

from types import SimpleNamespace
from typing import Any, Optional

# THE REAL CONFTEST, because `plugin_registrations` reports what this
# repository's conftest registers. A double of it would be asserting against
# this module rather than against the plugin surface.
import conftest


class RecordingParser:
    """A stand-in for pytest's parser that records what a hook registered.

    **In process, and deliberately not a subprocess.** Invoking pytest to read
    its help text fails on Windows under pytest with an invalid handle, which is
    the same platform quirk the excerpt cases hit. The harness is verified on
    both platforms, so a case that only runs on one is not a case.

    It records what **our hook** did, which is the thing that can drift. How
    pytest then parses those registrations is pytest's business and not ours to
    assert.

    Attributes:
        registered (list): Every flag the hook added, in order.
        choices (dict): The choices declared per flag.
    """

    def __init__(self) -> None:
        """Start with nothing recorded.

        Returns:
            None
        """
        self.registered: list[str] = []
        self.choices: dict[str, Any] = {}

    def getgroup(self, name: str, description: str = "") -> "RecordingParser":
        """Return this recorder as the requested option group.

        Args:
            name (str): The group name.
            description (str): Ignored.

        Returns:
            RecordingParser: This recorder.
        """
        del name, description
        return self

    def addoption(self, flag: str, **settings: Any) -> None:
        """Record one registered flag.

        Args:
            flag (str): The flag as it appears on a command line.
            **settings (Any): What the hook declared for it.

        Returns:
            None
        """
        self.registered.append(flag)
        self.choices[flag] = settings.get("choices")


def plugin_registrations() -> RecordingParser:
    """Run the pytest hook against a recording parser.

    Returns:
        RecordingParser: What the hook registered.
    """
    recorder = RecordingParser()
    conftest.pytest_addoption(recorder)
    return recorder
class FakeInvocationParams:
    """The raw arguments pytest records for a run.

    Attributes:
        args (list): Exactly what the caller wrote.
    """

    def __init__(self, args: list[str]) -> None:
        """Hold the arguments.

        Args:
            args (list[str]): The raw command line.

        Returns:
            None
        """
        self.args = args


class FakeConfig:
    """Enough of pytest's config to exercise the invocation record.

    **Built here rather than through a pytest run** because the question is what
    `configure_invocation` concludes from a given command line, and spinning up a
    session to ask it would make the case slower and less specific.
    """

    def __init__(
        self,
        args: list[str],
        values: dict[str, Any],
        option_values: Optional[dict[str, Any]] = None,
    ) -> None:
        """Hold the command line, the parsed values and the option namespace.

        ``option_values`` becomes ``config.option``, holding only the keys
        given, so a plugin that is not loaded is modelled by leaving its
        destination out rather than by setting it to ``None``.

        Args:
            args (list[str]): The raw command line.
            values (dict[str, Any]): What pytest would have parsed from it.
            option_values (Optional[dict]): The attributes ``config.option``
                carries.

        Returns:
            None
        """
        self.invocation_params = FakeInvocationParams(args)
        self._values = values
        self.option = SimpleNamespace(**(option_values or {}))
        self.mqc_invocation: Any = None

    def getoption(self, name: str, default: Any = None) -> Any:
        """Return a parsed value, as pytest would.

        Args:
            name (str): The option's destination name.
            default (Any): What to return when it is unset.

        Returns:
            Any: The value.
        """
        return self._values.get(name, default)
