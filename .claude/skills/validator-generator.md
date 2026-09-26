<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# Skill: Validator Generator for AP-Harness-QC

## Context
Use this skill to convert raw JSON/YAML payloads into strict, typed schema validators for the **Tier 1 Ingestion API** (`ingestion/`). Every payload crossing a tier boundary passes through one of these validators before dispatch, per `../rules/framework-rules.md`.

Output must satisfy `../rules/code-style.md` section 6 and score **10.00/10** against `.pylintrc`.

## Hard Constraints
* **Dataclass Schemas**: use `@dataclass(frozen=True)` with a `from_dict` classmethod. Frozen because an ingested record is evidence, not working state.
* **Strict Validation**: `from_dict` validates all required keys *before* instantiation and raises `KeyError` naming the missing field.
* **Explicit Casting**: coerce at the boundary with `str(...)`, `int(...)`, `float(...)`. Never trust the incoming type.
* **Exception Chaining**: re-raise with `raise ... from error`.
* **Narrow Catching**: `KeyError`, `ValueError`, `TypeError`, `json.JSONDecodeError`. No bare `except:` and no `except Exception:`.
* **Built-In Generics**: `dict[str, Any]`, `list[str]`, `frozenset[int]`. Do not import `Dict`/`List` from `typing`.
* **Variables**: minimum 3 characters in every scope, comprehension targets and `except ... as` bindings included.
* **Docstrings**: Google style, typed `Args:`, mandatory `Returns:`.
* **Taxonomy**: validation failures map to `QC_HARNESS_PARSER_ERROR` on malformed input, or `QC_LLM_SCHEMA_VIOLATION` when a model output fails its contract.

## Inputs Required
* Sample JSON payload from the target source.
* Which tier boundary the record crosses (Golden Rules, Task Data, or Model Output).
* Which fields are mandatory versus optional.

## Execution Template

```python
"""Schema validators for golden rule records ingested by the Tier 1 API."""

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = frozenset({"rubric_id", "threshold", "criteria"})


@dataclass(frozen=True)
class GoldenRuleSet:
    """Ground-truth assertions and scoring rubric for a single evaluation case.

    Attributes:
        rubric_id (str): Stable identifier for the rubric.
        threshold (float): Minimum passing score for the LLM-as-a-Judge pass.
        criteria (dict[str, Any]): Named scoring criteria and their weights.
        description (Optional[str]): Human-readable rubric summary.
    """

    rubric_id: str
    threshold: float
    criteria: dict[str, Any]
    description: Optional[str] = None

    @classmethod
    def from_dict(cls, raw_payload: dict[str, Any]) -> "GoldenRuleSet":
        """Validates and converts a raw mapping into a :class:`GoldenRuleSet`.

        Args:
            raw_payload (dict[str, Any]): Raw decoded rubric mapping.

        Returns:
            GoldenRuleSet: The validated, immutable rubric record.

        Raises:
            KeyError: If any mandatory field is absent from ``raw_payload``.
            ValueError: If ``threshold`` cannot be coerced to a float.
        """
        missing_fields = _REQUIRED_FIELDS - frozenset(raw_payload)
        if missing_fields:
            logger.error(
                "QC_HARNESS_PARSER_ERROR: rubric payload missing %s",
                sorted(missing_fields),
            )
            raise KeyError(
                f"Missing mandatory schema field(s): {sorted(missing_fields)}"
            )

        try:
            parsed_threshold = float(raw_payload["threshold"])
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"QC_HARNESS_PARSER_ERROR: threshold is not numeric: "
                f"{raw_payload['threshold']!r}"
            ) from error

        return cls(
            rubric_id=str(raw_payload["rubric_id"]),
            threshold=parsed_threshold,
            criteria=dict(raw_payload["criteria"]),
            description=(
                str(raw_payload["description"])
                if raw_payload.get("description") is not None
                else None
            ),
        )
```

## Pre-Delivery Checklist
1. All mandatory fields checked *before* construction, with the missing names in the message.
2. Every value explicitly cast at the boundary.
3. Zero identifiers under 3 characters.
4. No bare or broad exception handlers; every re-raise chains with `from error`.
5. Logging uses lazy `%s` interpolation, not f-strings.
6. `pylint --rcfile=.pylintrc ingestion/` reports 10.00/10.
7. A matching `MQC_ING_UNI_#####` acceptance test and rejection test exist for the validator.
