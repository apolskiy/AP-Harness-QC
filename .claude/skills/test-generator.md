<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# Skill: Test Generator for AP-Harness-QC

## Context
Use this skill when asked to author a new pytest module for **AP-Harness-QC**. Output must satisfy `../rules/testing-standards.md`, `../rules/code-style.md`, and `../rules/framework-rules.md` simultaneously, and must pass `pylint --rcfile=.pylintrc` at **10.00/10**.

This skill produces Phase 3 output only. Do not invoke it before a test plan exists at `docs/testing/<feature_name>_test_plan.md` and has been approved.

## Hard Constraints
* **`MQC` prefix is mandatory on all three levels.** It is the project prefix, not a layer attribute, and no test type is exempt:
  * Module: `mqc_<component>.py`, under `tests/`.
  * Class: `TestMQC<Component>`.
  * Callable: `MQC_<LAYER>_<5DIGIT_ID>_<behavior>`.
* **`test_` prefix is prohibited at every level.** `.pylintrc` rejects it via negative lookahead. A `test_` name would not be collected by `pytest.ini`, so it would lint clean and never run.
* **Layer token**: currently `UNI` / `SYS` / `EVAL`. If the plan calls for a layer not yet registered, stop and register it first (table row + `pytest.ini` marker + CI gate step) rather than inventing one inline.
* **Variables**: minimum 3 characters everywhere, including `except ... as`, comprehension targets, and lambdas. Use `error` not `e`, `index` not `i`, `item` is acceptable at 4 characters.
* **Typing**: every parameter and return annotated, including `-> None`.
* **Docstrings**: Google style with typed `Args:` entries and a mandatory `Returns:` section.
* **Exceptions**: catch narrowly. No bare `except:` and no `except Exception:`. Chain with `raise ... from error`.
* **Failure taxonomy**: every failure assertion names its `QC_LLM_*` or `QC_HARNESS_*` code from `../rules/framework-rules.md`.
* **Logging**: module-level `logger = logging.getLogger(__name__)` immediately after imports. Use lazy `%s` interpolation in logging calls; f-strings in logger calls trigger `W1203`.

## Inputs Required
* Target tier (`ingestion` / `execution` / `evaluation`).
* Layer and marker (`unit` / `system` / `evaluator`).
* Next unassigned 5-digit ID in that layer's block.
* Component under test and its validator/schema class.
* Expected failure taxonomy codes for the negative cases.

## Execution Template

```python
"""Test suite for the [Component Name] component of the [Tier] tier."""

import logging

import allure
import pytest

from ingestion.golden_rules import GoldenRuleSet

logger = logging.getLogger(__name__)

_EXPECTED_RUBRIC_KEYS = frozenset({"rubric_id", "threshold", "criteria"})


@pytest.mark.unit
@allure.epic("AP-Harness-QC")
@allure.feature("Ingestion")
class TestMQCGoldenRuleParser:
    """Validates golden rule ingestion and schema boundary enforcement."""

    @allure.story("Schema Acceptance")
    def MQC_UNI_10001_accepts_complete_rubric_payload(
        self, golden_rule_payload: dict
    ) -> None:
        """Confirms a fully populated rubric payload parses into a schema object.

        Args:
            golden_rule_payload (dict): Fixture supplying a valid rubric mapping.

        Returns:
            None

        Raises:
            AssertionError: If parsing fails or required fields are dropped.
        """
        with allure.step("Parse the golden rule payload"):
            parsed_rules = GoldenRuleSet.from_dict(golden_rule_payload)

        with allure.step("Verify every mandatory rubric key survived parsing"):
            resolved_keys = frozenset(parsed_rules.criteria.keys())
            missing_keys = _EXPECTED_RUBRIC_KEYS - resolved_keys
            assert not missing_keys, (
                f"QC_LLM_SCHEMA_VIOLATION: rubric keys dropped during parsing: "
                f"{sorted(missing_keys)}"
            )

    @allure.story("Schema Rejection")
    def MQC_UNI_10002_rejects_payload_missing_threshold(
        self, golden_rule_payload: dict
    ) -> None:
        """Confirms a rubric payload lacking ``threshold`` raises :exc:`KeyError`.

        Args:
            golden_rule_payload (dict): Fixture supplying a valid rubric mapping.

        Returns:
            None

        Raises:
            AssertionError: If the parser accepts an incomplete payload.
        """
        incomplete_payload = {
            field_name: field_value
            for field_name, field_value in golden_rule_payload.items()
            if field_name != "threshold"
        }

        with allure.step("Assert the parser refuses the incomplete payload"):
            with pytest.raises(KeyError) as raised_error:
                GoldenRuleSet.from_dict(incomplete_payload)

        logger.info(
            "QC_HARNESS_PARSER_ERROR path exercised: %s", raised_error.value
        )
        assert "threshold" in str(raised_error.value), (
            "QC_LLM_SCHEMA_VIOLATION: rejection message must name the missing field"
        )
```

## Pre-Delivery Checklist
Confirm each item before presenting generated tests:
1. Zero identifiers under 3 characters, comprehension targets included.
2. `MQC` prefix present on the module, the class, and every callable; no `test_` anywhere; the 5-digit ID is unused and drawn from the registered layer's block.
3. Marker on the class matches the layer; `pytest.ini` registers it.
4. Allure `epic` / `feature` / `story` present; `allure.step` wraps each action.
5. Every assertion message carries a taxonomy code.
6. `pylint --rcfile=.pylintrc tests/` reports 10.00/10.
7. Result logged to `CLAUDE_LOG.md` at the repository root, with the Pylint score and naming audit.
