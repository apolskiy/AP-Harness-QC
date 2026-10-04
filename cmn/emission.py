# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Handing the record this project builds to the artifact that carries it.

Specified by ``docs/design/cmn_verdict_and_cli.md`` sections 5.2 to 5.4.1.

**Written 2026-10-03, closing the gap section 5.1 recorded.** Every part of the
record shipped and nothing published it: ``emit_result`` returned the whole
section 9 mapping, ``observation_parameters`` and ``vendor_report`` built the
published forms, and none had a caller outside the test suite. A real Allure
result carried empty parameters and a severity label, so a collector could not
say which engine produced it and the three-engine comparison was
unattributable from the artifact.

**The hook is where the two halves meet** (section 5.4.1). ``observe`` has the
configuration and what the tiers measured; the pytest item has the case. So the
measured half is recorded here as a run takes it, and the reporting hook
publishes it once the case's verdict is known, which is also the first point
that knows whether to attach the reproduction.

**Nothing here decides anything.** The parameters come from ``cmn.reporting``
and the fields from ``cmn.metadata``, both pure, because a function that called
into Allure could only be tested by running a reporter.
"""

import json
import logging
from typing import Any, Final, Optional

import allure

from cmn.observations import Observation, RunContext
from cmn.reporting import observation_parameters, vendor_report

logger = logging.getLogger(__name__)

# WHAT THE CURRENT CASE HAS MEASURED, cleared when it starts. A case's
# observations are taken in one call and published in the hook that reports it,
# so the two need a place to meet that neither owns. Design section 5.4.1.
_RECORDED: Final[list[tuple[Observation, Any]]] = []
_RUN: Final[dict[str, Optional[RunContext]]] = {"context": None}


def begin_case(run: Optional[RunContext] = None) -> None:
    """Forget the previous case's observations and adopt the run context.

    Called from ``pytest_runtest_setup``, so a case that records nothing
    publishes nothing rather than republishing its predecessor's measurements.

    Args:
        run (Optional[RunContext]): The run-scoped fields, kept across cases
            when not supplied.

    Returns:
        None
    """
    _RECORDED.clear()
    if run is not None:
        _RUN["context"] = run


def record_observation(observation: Observation, outcome: Any = None) -> None:
    """Record one observation and the call that produced it.

    **The call is retained on every observation, passing or failing**, because
    a case's verdict is not known while its observations are being taken: the
    passing observations of a failing case are exactly the ones a provider
    report needs. The condition is on the attachment, not on the record
    (section 5.3).

    Args:
        observation (Observation): What was measured.
        outcome (Any): The dispatch outcome, carrying the request and the
            response. Absent where nothing was dispatched.

    Returns:
        None
    """
    _RECORDED.append((observation, outcome))


def recorded_observations() -> tuple[tuple[Observation, Any], ...]:
    """Return what the current case has recorded, in the order taken.

    Returns:
        tuple: Each observation with the outcome that produced it.
    """
    return tuple(_RECORDED)


def representative(observations: list[Observation]) -> Observation:
    """Return the observation whose fields describe the case.

    **The first failing one, and the first otherwise.** A reader scanning a
    failed case wants the call that failed rather than whichever was dispatched
    first; on a passing case every observation agreed, so the first is as good
    as any. Design section 5.2.1.

    Args:
        observations (list[Observation]): Every observation, in index order.

    Returns:
        Observation: The representative.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the list is empty,
            because a case with no observation has nothing to represent and
            publishing a default would describe a measurement nobody took.
    """
    if not observations:
        raise ValueError(
            "QC_HARNESS_PARSER_ERROR: no observation to represent, so there is "
            "nothing to publish and a default would describe a measurement "
            "nobody took"
        )
    for observation in observations:
        if not observation.passed:
            return observation
    return observations[0]


def published_fields(
    observations: list[Observation], run: Optional[RunContext] = None
) -> dict[str, str]:
    """Return every parameter a case publishes, aggregates included.

    Design: ``cmn_verdict_and_cli.md`` section 5.2.1.

    Args:
        observations (list[Observation]): Every observation, in index order.
        run (Optional[RunContext]): The run-scoped fields.

    Returns:
        dict[str, str]: Parameter name to its rendered value. Carries the
        representative observation's fields, the population the case measured,
        and ``resolved_models`` **only where more than one model served it**,
        which is the unsound-run condition section 4.9.6 gates on and is
        otherwise already published as ``resolved_model``.
    """
    chosen = representative(observations)
    fields = dict(observation_parameters(chosen, run))
    fields["observations_taken"] = str(len(observations))
    fields["observations_passed"] = str(
        sum(1 for observation in observations if observation.passed)
    )

    served = sorted({
        observation.resolved_model for observation in observations
        if observation.resolved_model
    })
    if len(served) > 1:
        fields["resolved_models"] = ";".join(served)
    return fields


def publish_result(item: Any, report: Any) -> int:
    """Publish the current case's record to the artifact.

    **Called from the reporting hook on the call phase**, which is the only
    place holding both the measured half and the case, and where the verdict is
    known. Verified 2026-10-03 by emitting from it and reading the produced
    raw result: a parameter, a label and an attachment all reach the open
    result there (section 5.2.1.2).

    **A failing case attaches every call it made** and a passing one does not,
    per section 5.3: nothing is filed about a pass and prompts are large.

    Args:
        item (Any): The test that ran, read for its name.
        report (Any): The phase report pytest produced.

    Returns:
        int: How many observations were published, zero where the phase is not
        the call or the case recorded none. **A precondition records nothing
        and publishes nothing**, which is correct rather than a gap: it
        measures the harness and has no observation of a model.
    """
    if getattr(report, "when", "") != "call":
        return 0
    recorded = recorded_observations()
    if not recorded:
        return 0

    observations = [observation for observation, _ in recorded]
    for name, value in published_fields(observations, _RUN["context"]).items():
        allure.dynamic.parameter(name, value)

    # ALSO A LABEL, which `testing-standards.md` section 4 requires so that
    # root-cause class is filterable rather than only readable.
    chosen = representative(observations)
    if chosen.taxonomy_code is not None:
        allure.dynamic.label("taxonomy_code", chosen.taxonomy_code)

    if not report.passed:
        attach_history(item, recorded)
    return len(observations)


def attach_history(item: Any, recorded: tuple[tuple[Observation, Any], ...]) -> None:
    """Attach every call a failing case made, for a provider ticket.

    **Every observation, including the ones that passed.** A single
    disagreement earns two more observations, so the failing call is frequently
    not the first, and ``QC_LLM_INCONSISTENT`` is a claim about the set: a
    report carrying one call could not support it.

    Credentials are removed by :func:`cmn.reporting.vendor_report` before
    anything is written, because a credential in a durable record is disclosed
    to everyone who can read it.

    Args:
        item (Any): The test that ran, whose name identifies the case.
        recorded (tuple): Each observation with the outcome that produced it.

    Returns:
        None
    """
    # ALIGNED, NOT FILTERED. `vendor_report` reads the outcome for a call by
    # its position, so dropping an observation that dispatched nothing would
    # attribute the next one's result to the wrong call. An absent outcome
    # contributes its taxonomy code and no call, which the builder handles.
    calls = [outcome for _, outcome in recorded]
    report = vendor_report(
        getattr(item, "name", "unknown"),
        calls,
        [observation.passed for observation, _ in recorded],
    )
    allure.attach(
        json.dumps(report, indent=2, default=str),
        name="vendor-report",
        attachment_type=allure.attachment_type.JSON,
    )
    logger.info(
        "attached %d call(s) for %s, which is what a provider ticket is "
        "written from",
        sum(1 for call in calls if call is not None), report["case_id"],
    )
