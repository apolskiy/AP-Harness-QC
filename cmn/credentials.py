# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Credential recognition, by the name of a field and by the value in it.

Created: 2026-10-12
Last updated: 2026-10-21

This file contains ``FORBIDDEN_KEYS``, the exact field names refused in a
configuration file; ``credential_shaped_name``, which reports a field name that
reads as a credential; and ``credential_shaped_value``, which reports a value
carrying a credential's issued prefix.

``cmn.config`` refuses a credential-shaped key when it loads a file, and
``execution/replay.py`` reports every credential-shaped field or value in a
replay fixture store, so a secret in a committed file or a recording is caught
by the precondition suite.

**Split from ``config.py`` on 2026-10-11**, when storing the composed request
in a fixture needed the same predicates and the addition took that module to
1008 lines, past the thousand-line ceiling. Credentials are their own subject,
which is the split ``code-style.md`` section 5.1 asks for rather than a number.

**One registry.** Configuration loading refuses a credential-shaped key and the
fixture screen reports one, and both read the patterns here so the two cannot
disagree (``framework-rules.md`` section 4.1).
"""

import re
from typing import Any, Final

# A CREDENTIAL'S EXACT FIELD NAME, for a configuration file. Refused at load,
# because a credential reaching a committed file is disclosed.
FORBIDDEN_KEYS: Final[frozenset[str]] = frozenset(
    {"api_key", "apikey", "secret", "token", "password", "credential"}
)

# A CREDENTIAL'S FIELD NAME. Matched at the end, so `API_KEY` and
# `ANTHROPIC_API_KEY` both hit and `KEYWORD` does not.
_CREDENTIAL_SHAPED: Final[re.Pattern] = re.compile(
    r"(KEY|TOKEN|SECRET|CREDENTIAL|PASSWORD)$", re.IGNORECASE
)

# A CREDENTIAL'S VALUE, BY ITS ISSUED PREFIX. The name check above catches a
# field somebody called `api_key`; this catches a secret pasted into a field
# called anything at all, which is the case a name pattern cannot see.
_CREDENTIAL_VALUE_PREFIXES: Final[tuple[str, ...]] = (
    "sk-", "sk-ant-", "AIza", "xai-", "ghp_", "Bearer ",
)


def credential_shaped_name(name: str) -> bool:
    """Report whether a field name reads as a credential.

    One predicate rather than a second copy of the pattern, so a check added
    later screens for what configuration loading already refuses
    (``framework-rules.md`` section 4.1).

    Args:
        name (str): The field name.

    Returns:
        bool: True where the name ends in a credential word.
    """
    return bool(_CREDENTIAL_SHAPED.search(str(name)))


def credential_shaped_value(value: Any) -> bool:
    """Report whether a value reads as an issued credential.

    **The value and not only the name**, because a secret pasted into a field
    called ``note`` is still disclosed, and the name pattern cannot see it.

    Args:
        value (Any): The value, screened only where it is a string.

    Returns:
        bool: True where the value begins with a known credential prefix.
    """
    if not isinstance(value, str):
        return False
    return any(value.startswith(prefix) for prefix in _CREDENTIAL_VALUE_PREFIXES)
