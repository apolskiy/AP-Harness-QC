# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""What a run says it measured against, rendered for each artifact that carries it.

Created: 2026-10-29
Last updated: 2026-10-29

This file contains ``PROVENANCE_FILE`` and ``PROVENANCE_PREFIX``, the names a
report reads and a property carries; ``provenance_fields``, which builds the
mapping from a run's engine, mode, requested model and whatever the provider
declared; ``write_provenance``, which lands that mapping beside the raw results
as the file an Allure environment block is built from; and
``testsuite_properties``, the same mapping rendered as the name and value pairs
a JUnit report carries.

It runs at configuration, before any case executes, so a run that crashes
still leaves a report stating what it was measuring. Nothing downstream depends
on it: a failure costs the label on a report rather than a measurement, which
is why every entry here is permitted to be empty.

**Two artifacts, one mapping.** The Allure report reads a properties file and
a JUnit report carries properties under its root element, and a collector
parses the second. Rendering both from one mapping is what stops the two
disagreeing, which is the drift a single registry exists to prevent applied to
a label.

Specified by ``docs/design/cmn_verdict_and_cli.md`` section 5.6.
"""

import logging
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

_ENCODING: Final[str] = "utf-8"

# WHAT ALLURE READS, AND IT READS NOTHING ELSE. The environment widget is built
# from this file in the results directory, which is why a published report
# names no model until something writes it (design section 5.6.3).
PROVENANCE_FILE: Final[str] = "environment.properties"

# THE PREFIX A JUNIT PROPERTY CARRIES, so a collector can select this project's
# provenance from whatever else a runner records under the same element.
PROVENANCE_PREFIX: Final[str] = "mqc."

# THE ORDER THE FIELDS READ IN. A properties file is a mapping and a report
# renders it in the order given, so the run's subject comes before what it
# happened to be configured with.
_FIELD_ORDER: Final[tuple[str, ...]] = (
    "engine",
    "mode",
    "requested_model",
    "served_version",
    "served_digest",
)

# WHAT AN ABSENT VALUE READS AS. Never an empty string: a reader cannot tell
# an empty value from a field nobody wrote, and the whole purpose here is that
# a report states what it knows and what it does not.
_UNRECORDED: Final[str] = "unrecorded"


def provenance_fields(
    *, engine: str, mode: str, requested_model: str, served: dict[str, str]
) -> dict[str, str]:
    """Return what this run measured against, as an ordered mapping.

    **A replay run is not missing its provenance.** It records the engine, the
    mode and the model it asked for, and leaves the served fields unrecorded,
    because what it measured is a recording rather than a provider: the version
    that produced the response is in the fixture (``tier2_execution.md``
    section 5.2.1).

    Args:
        engine (str): The engine this run selected.
        mode (str): ``live`` or ``replay``.
        requested_model (str): What the roster asks for.
        served (dict): ``served_version`` and ``served_digest`` as
            ``execution.preflight.served_facts`` returns them, empty where the
            provider was not asked or could not be read.

    Returns:
        dict[str, str]: Every field in ``_FIELD_ORDER``, each either a value or
        ``unrecorded``. **Every key is always present**, so a collector reading
        two runs compares the same fields rather than discovering that one run
        wrote fewer.
    """
    supplied = {
        "engine": engine,
        "mode": mode,
        "requested_model": requested_model,
        "served_version": served.get("served_version", ""),
        "served_digest": served.get("served_digest", ""),
    }
    return {
        name: str(supplied.get(name, "")).strip() or _UNRECORDED for name in _FIELD_ORDER
    }


def write_provenance(results_dir: Path, fields: dict[str, str]) -> Path:
    """Write the mapping beside the raw results, as the file a report reads.

    Args:
        results_dir (Path): The Allure results directory this run writes to.
        fields (dict): As :func:`provenance_fields` returns.

    Returns:
        Path: The file written.

    Raises:
        OSError: Where the directory cannot be created or the file written.
            The caller logs it and carries on, provenance being a label rather
            than a measurement.
    """
    results_dir.mkdir(parents=True, exist_ok=True)
    destination = results_dir / PROVENANCE_FILE
    body = "".join(f"{name}={value}\n" for name, value in fields.items())
    destination.write_text(body, encoding=_ENCODING, newline="\n")
    logger.info("Run provenance written to %s", destination)
    return destination


def testsuite_properties(fields: dict[str, str]) -> list[tuple[str, str]]:
    """Return the mapping as the name and value pairs a JUnit report carries.

    **Prefixed, and run-scoped.** A JUnit property under the root element is
    written by ``record_testsuite_property``, which is session scoped and is
    the one form compatible with the ``xunit2`` family pytest writes by
    default; the per-case form warns under that family and would cost a format
    downgrade for provenance that does not vary per case (design section
    5.6.2).

    Args:
        fields (dict): As :func:`provenance_fields` returns.

    Returns:
        list[tuple[str, str]]: One pair per field, in the mapping's order, each
        name carrying :data:`PROVENANCE_PREFIX`.
    """
    return [(f"{PROVENANCE_PREFIX}{name}", value) for name, value in fields.items()]
