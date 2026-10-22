# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Builds the run context every row of a session carries, and the record that vouches for it.

Created: 2026-10-21
Last updated: 2026-10-21

This file contains ``session_run_context``, which builds the session's
``RunContext`` from the environment, the recorded invocation and the
preconditions; ``adopt_run_context``, which hands it to every case that
follows; and ``publish_preconditions_record``, which writes or removes the
record a preconditions job leaves for the graded jobs after it.

Each repository's ``conftest.py`` calls ``adopt_run_context`` once the
selection is final and ``publish_preconditions_record`` last at session finish.
The context decides whether a row is gated, so whether the verdict tool judges
the run and whether a collector keeps its rows.

Specified by ``docs/design/cmn_verdict_and_cli.md`` section 7.1.4.
"""

import logging
import platform
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from cmn.emission import begin_case
from cmn.environments import is_precondition
from cmn.observations import RunContext, detected_run_context
from cmn.prerequisites import (
    Provenance,
    read_preconditions_record,
    write_preconditions_record,
)

logger = logging.getLogger(__name__)


def session_run_context(
    config: Any, items: Sequence[Any], environ: Mapping[str, str],
    *, system: Optional[str] = None,
) -> RunContext:
    """Return the run context this session's rows carry.

    The context is read from the environment, the selection mode from the
    recorded invocation, and the preconditions count as executed when the
    session selected any, or when ``--preconditions-record`` names a record an
    earlier job wrote for the same commits and platform. Design:
    ``cmn_verdict_and_cli.md`` section 7.1.4.

    Args:
        config (Any): pytest's configuration, carrying ``mqc_invocation``.
        items (Sequence): The selected items.
        environ (Mapping): The process environment.
        system (Optional[str]): The platform, defaulting to this one.

    Returns:
        RunContext: The run-scoped fields.

    Raises:
        ValueError: With ``QC_HARNESS_PREREQUISITE_MISMATCH`` when the named
            record was written for other commits or another platform.
    """
    executed = any(is_precondition(str(getattr(item, "nodeid", ""))) for item in items)
    named = str(config.getoption("--preconditions-record", "") or "")
    if named and not executed:
        executed = read_preconditions_record(
            Path(named), _precondition_provenance(environ, system)
        )
    return RunContext(
        run_context=detected_run_context(environ),
        selection_mode=config.mqc_invocation.selection_mode,
        preconditions_executed=executed,
    )


def adopt_run_context(
    config: Any, items: Sequence[Any], environ: Mapping[str, str]
) -> RunContext:
    """Build the session's run context and hand it to every case that follows.

    Called once the selection is final, from each repository's
    ``pytest_collection_modifyitems``.

    Args:
        config (Any): pytest's configuration.
        items (Sequence): The selected items.
        environ (Mapping): The process environment.

    Returns:
        RunContext: The context adopted.
    """
    run = session_run_context(config, items, environ)
    begin_case(run)
    logger.info(
        "Run context %s, selection %s, preconditions %s: %s",
        run.run_context, run.selection_mode,
        "held" if run.preconditions_executed else "not executed",
        "gated" if run.gated else "not gated",
    )
    return run


def publish_preconditions_record(session: Any, environ: Mapping[str, str]) -> None:
    """Write or remove the precondition record a session's preconditions earned.

    Only a session that selected preconditions writes, and only when it exits
    0, which with zero skips enforced means every precondition passed. Called
    last in ``pytest_sessionfinish``, after the refusals that raise the exit
    status.

    Args:
        session (Any): The finishing session.
        environ (Mapping): The process environment.

    Returns:
        None
    """
    named = str(session.config.getoption("--preconditions-record", "") or "")
    items = getattr(session, "items", [])
    if not named or not any(is_precondition(str(item.nodeid)) for item in items):
        return
    write_preconditions_record(
        Path(named), _precondition_provenance(environ, None),
        passed=int(session.exitstatus) == 0,
    )


def _precondition_provenance(environ: Mapping[str, str], system: Optional[str]) -> Provenance:
    """Return the commits and platform a precondition record is guarded by.

    Args:
        environ (Mapping): The process environment, carrying the refs.
        system (Optional[str]): The platform, defaulting to this one.

    Returns:
        Provenance: Only the guarded fields set.
    """
    return Provenance(
        code_ref=environ.get("MQC_CODE_REF", ""),
        case_ref=environ.get("MQC_CASE_REF", ""),
        platform=system or platform.system(),
    )
