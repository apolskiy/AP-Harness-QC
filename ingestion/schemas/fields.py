# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Field validation helpers shared by every schema record's ``from_dict``.

Created: 2026-10-18
Last updated: 2026-10-21

This file contains the checks a record applies to its raw mapping, normalising
text, refusing unknown keys, requiring fields to be present and filled,
coercing integers and floats, and refusing identifiers unsafe as a path
segment, plus the public ``canonical_identifier``, the form two identifiers
are compared in to find a filesystem collision.

**The task, rubric and rule records call these helpers while they are built**,
so a bad field raises at load with its ``QC_DATA_*`` code. The loaders and
case building use ``canonical_identifier`` to refuse identifiers that would
collide on disk.

Design: ``docs/design/tier1_ingestion.md`` sections 3.0 and 5.
"""

import logging
import unicodedata
from dataclasses import fields
from typing import Any, Optional

from cmn.registries import (
    is_windows_reserved_name,
)

logger = logging.getLogger(__name__)


def _normalize_text(value: Any) -> str:
    """Cast a value to text and strip surrounding whitespace.

    Stripping happens before any emptiness check, so that a whitespace-only
    value is caught rather than passing as three characters. Line endings are
    normalized to LF so that a value read on Windows and the same value read on
    Linux produce identical records, and therefore identical request hashes.

    Args:
        value (Any): The incoming value, of unknown type by assumption.

    Returns:
        str: The cast, newline-normalized, stripped text.
    """
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def _reject_unknown_keys(payload: dict[str, Any], record_type: type, owner: str) -> None:
    """Raise when a payload carries keys the record does not declare.

    A typo in a required field is caught by the required-field check. A typo in
    an **optional** field would otherwise take a default silently, and the case
    would be scored against criteria nobody wrote. That is the reason this check
    exists at all.

    Args:
        payload (dict): The incoming mapping.
        record_type (type): The dataclass whose fields are permitted.
        owner (str): Identifier used in the message, for locating the record.

    Returns:
        None

    Raises:
        KeyError: Naming every unknown key, sorted, with ``QC_DATA_UNKNOWN_FIELD``.
    """
    declared = {entry.name for entry in fields(record_type)}
    unknown = sorted(set(payload) - declared)
    if unknown:
        logger.error("QC_DATA_UNKNOWN_FIELD %s unknown keys %s", owner, unknown)
        raise KeyError(
            f"QC_DATA_UNKNOWN_FIELD: {record_type.__name__} {owner} "
            f"carries unknown keys {unknown}"
        )


def _require_present_and_filled(
    payload: dict[str, Any], required: tuple[str, ...], record_name: str, owner: str
) -> None:
    """Raise when required fields are absent or present but empty.

    Both problems are collected across the whole payload before raising, because
    an author correcting hand-written data wants every error at once rather than
    one per run.

    Args:
        payload (dict): The incoming mapping.
        required (tuple): Field names that must be present and non-empty.
        record_name (str): The record type name, for the message.
        owner (str): Identifier used in the message, for locating the record.

    Returns:
        None

    Raises:
        KeyError: When any required field is absent, naming all of them.
        ValueError: When any required field is present but empty, naming all of
            them. Raised only once no field is missing, so that the two codes
            never contend for one message.
    """
    missing = sorted(name for name in required if name not in payload)
    if missing:
        logger.error("QC_DATA_REQUIRED_FIELD_MISSING %s absent %s", owner, missing)
        raise KeyError(
            f"QC_DATA_REQUIRED_FIELD_MISSING: {record_name} {owner} "
            f"is missing required fields {missing}"
        )

    empty = sorted(name for name in required if _is_empty(payload[name]))
    if empty:
        logger.error("QC_DATA_REQUIRED_FIELD_EMPTY %s empty %s", owner, empty)
        raise ValueError(
            f"QC_DATA_REQUIRED_FIELD_EMPTY: {record_name} {owner} "
            f"carries empty required fields {empty}"
        )


def _is_empty(value: Any) -> bool:
    """Report whether a value counts as empty for a mandatory field.

    Presence alone is insufficient: ``user_prompt: ""`` supplies the key and
    satisfies a presence check while carrying nothing. Whitespace-only text is
    empty for the same reason, which is why text is stripped before the test.

    Args:
        value (Any): The supplied value.

    Returns:
        bool: True when the value carries nothing usable. ``False`` and ``0``
        are **not** empty; they are legitimate values that happen to be falsy,
        and treating them as empty would reject valid data.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, frozenset, dict)):
        return not value
    return False


def _reject_unsafe_identifier(identifier: str, owner: str) -> str:
    """Return an identifier after refusing forms that break on a platform.

    Two rules, both from A18, and both guarding a failure that occurs on exactly
    one supported platform:

    * A Windows reserved device name cannot become a directory at all, so an
      identifier that reaches a fixture path must not take one.
    * Identifiers are compared case-sensitively by this harness, and a
      filesystem may not agree. The canonical form returned here is what callers
      compare, so that a collision is detected rather than discovered.

    Args:
        identifier (str): The identifier as authored.
        owner (str): Identifier used in the message, for locating the record.

    Returns:
        str: The identifier, unchanged, once it is known to be safe.

    Raises:
        ValueError: When the identifier collides with a reserved device name.
    """
    if is_windows_reserved_name(identifier):
        logger.error("QC_DATA_IDENTIFIER_UNSAFE %s reserved device name %s", owner, identifier)
        raise ValueError(
            f"QC_DATA_IDENTIFIER_UNSAFE: {owner} identifier {identifier!r} collides with a "
            f"Windows reserved device name and cannot become a path segment"
        )
    return identifier


def canonical_identifier(identifier: str) -> str:
    """Return the form used to detect identifiers that collide on a filesystem.

    Case folding rather than lowercasing, because ``str.casefold`` handles
    scripts where the two differ. Unicode is normalized first so that two
    spellings of one character do not present as distinct identifiers.

    Args:
        identifier (str): The identifier as authored.

    Returns:
        str: The canonical form. Two identifiers sharing one canonical form
        coexist on Linux and collide on Windows, which is why they are rejected
        at ingest rather than left to a later platform-specific surprise.
    """
    return unicodedata.normalize("NFKC", identifier).casefold()


def _optional_text(value: Any) -> Optional[str]:
    """Normalize an optional text field, preserving absence.

    Args:
        value (Any): The supplied value, possibly ``None``.

    Returns:
        Optional[str]: ``None`` when absent, otherwise the normalized text. An
        explicitly supplied empty string stays an empty string rather than
        becoming ``None``: for an optional field the two are different authoring
        statements, and collapsing them would discard one.
    """
    return None if value is None else _normalize_text(value)


def _coerce_int(value: Any, field_name: str, owner: str) -> int:
    """Cast a value to an integer at the boundary, refusing what will not cast.

    Args:
        value (Any): The supplied value.
        field_name (str): Field name, for the message.
        owner (str): Record identifier, for the message.

    Returns:
        int: The cast value.

    Raises:
        ValueError: When the value is not an integer or an integral string.
    """
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"QC_DATA_MALFORMED_SOURCE: {owner} field {field_name} expects an integer, "
            f"received {value!r}"
        ) from error


def _coerce_float(value: Any, field_name: str, owner: str) -> float:
    """Cast a value to a float at the boundary, refusing what will not cast.

    Args:
        value (Any): The supplied value.
        field_name (str): Field name, for the message.
        owner (str): Record identifier, for the message.

    Returns:
        float: The cast value.

    Raises:
        ValueError: When the value is not numeric.
    """
    try:
        return float(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"QC_DATA_MALFORMED_SOURCE: {owner} field {field_name} expects a number, "
            f"received {value!r}"
        ) from error
