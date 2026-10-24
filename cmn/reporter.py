# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The reporter boundary: the one place that knows Allure might not be installed.

Created: 2026-10-24
Last updated: 2026-10-24

This file contains ``reporter``, which is the Allure module where it is
installed and a silent stand-in where it is not; ``reporting_available``, which
says which of the two is in use; and ``_Silent``, the stand-in itself.

Every module that publishes to a report goes through this name instead of
importing Allure, so a machine without it runs the suite rather than failing to
import it. The stand-in accepts the whole of the surface this project uses, a
parameter, a label, an attachment and a step block, and does nothing with any
of it.

**The report is how readiness is assessed and the suite is how it is
measured**, and only the second has to work everywhere. CI installs the
reporting extra and publishes a report; a developer on a fresh clone runs
``pytest -m unit`` and must not be stopped by a reporting library, nor by a
partial install of one.

Design: ``docs/design/harness_test_taxonomy.md`` section 16.7.
"""

import logging
from contextlib import nullcontext
from typing import Any, ContextManager, Final

logger = logging.getLogger(__name__)


class _SilentDynamic:
    """The runtime surface, when there is no runtime to publish to."""

    @staticmethod
    def parameter(name: str, value: Any) -> None:
        """Discard a published parameter.

        Args:
            name (str): The field.
            value (Any): Its value.

        Returns:
            None
        """
        del name, value

    @staticmethod
    def label(name: str, value: Any) -> None:
        """Discard a published label.

        Args:
            name (str): The label type.
            value (Any): Its value.

        Returns:
            None
        """
        del name, value


class _SilentAttachmentType:
    """The attachment types, as names with nothing behind them."""

    JSON: Final[str] = "application/json"
    TEXT: Final[str] = "text/plain"


class _Silent:
    """Accept everything this project publishes, and publish none of it.

    **Not an error and not a warning.** A run with no reporter installed is a
    complete run whose results reach the JUnit artifact and the log; the
    report is what it does not produce, and the person who did not install a
    reporter did not ask for one.
    """

    def __init__(self) -> None:
        """Hold the two surfaces Allure exposes under these names.

        **Instance attributes rather than class constants**, because the names
        are Allure's and are lowercase: a reader of ``cmn/emission.py`` sees
        the same call whichever of the two is in use.

        Returns:
            None
        """
        self.dynamic = _SilentDynamic()
        self.attachment_type = _SilentAttachmentType()

    @staticmethod
    def attach(body: Any, name: str = "", attachment_type: Any = None) -> None:
        """Discard an attachment.

        Args:
            body (Any): The content.
            name (str): Its name in a report.
            attachment_type (Any): Its media type.

        Returns:
            None
        """
        del body, name, attachment_type

    @staticmethod
    def step(title: str) -> ContextManager[None]:
        """Return a block that records nothing.

        Args:
            title (str): What the step would have been called.

        Returns:
            ContextManager[None]: A context doing nothing, so a caller's
            ``with`` statement reads the same either way.
        """
        del title
        return nullcontext()


try:  # pragma: no cover - the installed path is what every run takes
    import allure as _allure

    reporter: Any = _allure
    _AVAILABLE: Final[bool] = True
except ImportError:  # pragma: no cover - measured by a nested run instead
    reporter = _Silent()
    _AVAILABLE = False
    logger.info(
        "no Allure runtime is installed, so this run records its results and "
        "publishes no report"
    )


def reporting_available() -> bool:
    """Report whether a real Allure runtime is installed.

    Returns:
        bool: True where the module imported, False where the stand-in is in
        use. **Read by a case that needs a real reporter**, which declares the
        ``reporter`` environment scope and is deselected without one.
    """
    return _AVAILABLE
