# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""What a run publishes about each observation, and about a failing case.

Specified in ``docs/design/cmn_verdict_and_cli.md`` sections 5.1 to 5.4.

**Pure builders.** A function that called into Allure could only be tested by
running a reporter; these return mappings, which are tested by reading them.
The emission itself happens where the cases are, because the harness owns no
graded case.
"""

import logging
from typing import Any, Optional, Sequence

from cmn.config import redact
from cmn.metadata import emit_result
from cmn.observations import Observation, RunContext

logger = logging.getLogger(__name__)

# Fields that are structures rather than scalars. A parameter is a column, so
# these are rendered rather than handed over as objects: a collector reading a
# standard format should not have to learn this project's nesting.
_RENDERED: frozenset[str] = frozenset(
    {"priority_conditions", "requirement_ids", "effective_thresholds", "cli_flags"}
)


def observation_parameters(
    observation: Observation, run: Optional[RunContext] = None
) -> dict[str, str]:
    """Return every field section 9 requires, as parameters to emit.

    Combines the per-result mapping with the run-scoped one, so one observation
    publishes both halves and a collector reading a single row need not join
    anything. A list or mapping is rendered to text, because a parameter is a
    column.

    **An absent value is omitted rather than emitted empty.** A parameter
    present with no value reads as measured-and-empty, and the fields that are
    legitimately absent say something: a precondition carries no priority, and
    a pass carries no taxonomy code.

    Design: ``cmn_verdict_and_cli.md`` section 5.2.

    Args:
        observation (Observation): The observation to describe.
        run (Optional[RunContext]): The run-scoped fields, omitted when the
            caller has none.

    Returns:
        dict: Parameter name to value, every value a string.
    """
    collected: dict[str, Any] = dict(emit_result(observation, run or RunContext(
        run_context="local", selection_mode="manual", preconditions_executed=False,
    )))

    parameters: dict[str, str] = {}
    for name, value in collected.items():
        if value is None or value == "" or value == [] or value == {}:
            continue
        if name in _RENDERED or isinstance(value, (list, dict)):
            parameters[name] = ", ".join(
                f"{key}={item}" for key, item in sorted(value.items())
            ) if isinstance(value, dict) else ", ".join(str(item) for item in value)
            continue
        parameters[name] = str(value)
    return parameters


def vendor_report(
    case_id: str, calls: Sequence[Any], outcomes: Sequence[bool]
) -> dict[str, Any]:
    """Return the reproduction a provider ticket is written from.

    Carries **every** observation of the case in index order, each with the
    request sent, the response returned, the model that served it and whether
    it passed. The failing observation is frequently not the first, and
    ``QC_LLM_INCONSISTENT`` is a claim about the set that no single call can
    support.

    Credentials are removed by :func:`cmn.config.redact` before anything is
    returned, because a credential written into a durable record is disclosed
    to everyone who can read it.

    Design: ``cmn_verdict_and_cli.md`` section 5.3.

    Args:
        case_id (str): Which case the calls belong to.
        calls (Sequence): The dispatch outcomes, in observation order.
        outcomes (Sequence[bool]): Whether each observation passed, in the same
            order.

    Returns:
        dict: The case, how many observations it took, how many passed, and the
        calls themselves. **An outcome carrying no response contributes its
        taxonomy code and no call**, which is what a skipped or broken
        observation has to report.
    """
    observations: list[dict[str, Any]] = []
    for index, call in enumerate(calls):
        response = getattr(call, "response", None)
        record: dict[str, Any] = {
            "observation_index": getattr(call, "observation_index", index),
            "engine": str(getattr(call, "engine", "") or ""),
            "mode": str(getattr(call, "mode", "") or ""),
            "passed": bool(outcomes[index]) if index < len(outcomes) else None,
            "taxonomy_code": getattr(call, "taxonomy_code", None),
        }
        if response is not None:
            record["requested_model"] = str(getattr(response, "requested_model", ""))
            record["resolved_model"] = str(getattr(response, "resolved_model", ""))
            record["request"] = getattr(call, "request", None)
            record["response"] = (
                response.as_mapping() if hasattr(response, "as_mapping") else None
            )
        observations.append(record)

    return redact({
        "case_id": case_id,
        "observations_taken": len(observations),
        "observations_passed": sum(1 for passed in outcomes if passed),
        "calls": observations,
    })
