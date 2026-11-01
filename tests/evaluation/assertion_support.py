# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The assertion factory the evaluation case modules build their checks from.

Created: 2026-10-30
Last updated: 2026-10-30

This file contains ``programmatic_assertion``, which builds one
:class:`ingestion.schemas.ProgrammaticAssertion` over a valid base so a case
declares only the kind, the parameters and whatever field it is varying.

**It is a sibling module rather than a helper inside a case module**, because
collection does not reach here and ``code-style.md`` keeps a case module to
cases (`harness_test_taxonomy.md` section 13). ``mqc_uni_assertions.py`` carried
this function and is declared in ``config/support_extraction.yaml`` as a
definition to extract; this is that extraction, so the declaration goes with it.
"""

from typing import Any

from ingestion.schemas import ProgrammaticAssertion


def programmatic_assertion(
    kind: str, parameters: dict[str, Any], **overrides: object
) -> ProgrammaticAssertion:
    """Build an assertion over a valid base.

    Args:
        kind (str): The assertion kind.
        parameters (dict): Its parameters.
        **overrides (object): Fields to replace, such as ``assertion_id`` or
            ``taxonomy_code``.

    Returns:
        ProgrammaticAssertion: The built record, at ``violation`` severity
        unless an override says otherwise.
    """
    payload: dict[str, object] = {
        "assertion_id": f"MQC_ASR_{kind}",
        "kind": kind,
        "parameters": parameters,
        "taxonomy_code": "QC_LLM_SCHEMA_VIOLATION",
        "severity": "violation",
    }
    payload.update(overrides)
    return ProgrammaticAssertion.from_dict(payload)
