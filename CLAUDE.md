<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# AP-Harness-QC: AI Assistant Directives

Welcome to **AP-Harness-QC**, the harness half of an automated foundation model evaluation and LLM-as-a-Judge QC pipeline.

**This repository is the harness. The evaluation cases live in `AP-Model-QC`**, which consumes this one as a pinned dependency. Split 2026-09-23, closing A17; `DESIGN.md` section 5.1 carries the boundary and what it cost to find.

It publishes standard CI artifacts for read-only consumption and depends on no consumer.

## Mandatory Project Governance Files

Before generating proposals, architecture designs, or code, you MUST review and adhere to every governance file below. Paths are relative to the repository root (`AP-Harness-QC/`) and are the real on-disk locations.

1. `CLAUDE_LOG.md` (repo root, **tracked**): First-priority instruction. Log architecture decisions, trade-offs, and quality audits. The project's progress record, written for an external reader.
1b. `.claude/logs/PROMPT_LOG.md` (**not tracked**): Verbatim prompts and working notes. Never put raw prompts in `CLAUDE_LOG.md`.
2. `.claude/skills/skill-rules.md`: Workflow governance, the 4-phase execution pipeline (Phase 0 through Phase 3), Git safety, and logging rules.
3. `.claude/rules/code-style.md`: Variable rules (>= 3 chars, zero single-letter variables), Google docstrings, Python typing, documentation prose rules, and 10.00/10 Pylint compliance.
4. `.claude/rules/framework-rules.md`: Module separation across `ING`, `EXE`, `EVL` and `CMN`, the seven CI quality gates, test case types, and the four failure taxonomy families.
5. `.claude/rules/testing-standards.md`: Test naming (`MQC_<MODULE>_<LAYER>_<6DIGIT_ID>_<behavior>`), the inventory principle, change-scoped selection, pytest discovery, Allure and JUnit artifacts, and the downstream artifact contract.
6. `.claude/worktrees/worktree-rules.md`: Worktree isolation, branch boundaries, and environment safety.
7. `docs/harness_document_register.md`: **Every tracked document in this repository and what it holds. Read this before any documentation work and work through it on any review**: it is the only complete list, it is checked against the repository both ways by `MQC_CMN_UNI_112255`, and `DESIGN.md` section 3 is a reading order rather than an inventory. `harness_test_taxonomy.md` section 12 records what happened without it.

### Design Documents

**The register is the complete list; this section is the entry order.** A document absent from the list a reviewer holds is a document nobody reviews.

Governance states the rules; design documents state the specifications implementation is evaluated against.

* `DESIGN.md` (repo root): the referential index. Architecture, document map, and the decisions shaping everything downstream. **Read this before any individual design.**
* `docs/design/harness_test_taxonomy.md`: the single registry of identifiers, priorities and failure codes.
* `docs/design/harness_extensibility_standard.md`: how the system absorbs a new provider, layer or test type.
* `docs/design/harness_phase0_project_ambiguities.md`: every project-level decision, with what was rejected and why.
* `docs/design/tier1_ingestion.md`, `tier2_execution.md`, `tier3_evaluation.md`, `cmn_verdict_and_cli.md`: module specifications.
* `docs/design/harness_ci_pipeline.md`: the four workflows and the credential boundary.
* `docs/testing/harness_test_plan.md` and `rtm_harness.csv`: the requirements the preconditions satisfy, traced both ways.

**Documents that live in `AP-Model-QC` and are referenced from here**: `model_evaluation_test_plan.md` and `rtm_model.csv`. They are never copied into this repository, and `harness_test_taxonomy.md` is never copied out of it: `framework-rules.md` section 4.1 forbids a second registry.

### Supporting Skill Templates
* `.claude/skills/test-generator.md`: Scaffold for new `MQC_*` pytest modules.
* `.claude/skills/validator-generator.md`: Scaffold for `@dataclass` schema validators.

### Enforcement Configuration
* `.pylintrc`: Machine-enforced naming and the `fail-under=10.0` gate.
* `pytest.ini`: `MQC_*` discovery overrides and marker registry.

## Core Directives
* **Logging First:** Always begin and end tasks by documenting requirements, design choices, and audit metrics in `CLAUDE_LOG.md`. Verbatim prompts go to `.claude/logs/PROMPT_LOG.md` instead: the tracked log records decisions, not phrasing.
* **Strict Phased Workflow:** NEVER generate implementation code directly. Complete Phase 0 (Ambiguity Resolution), Phase 1 (Discussion), and Phase 2 (Design Doc) first. Phase 0 closes only when every blocking ambiguity has a recorded decision.
* **10.00/10 Pylint Compliance:** All generated Python code MUST achieve a 10.00/10 Pylint score against `.pylintrc`.
* **Descriptive Variable Naming:** Single-character variables (`i`, `e`, `x`, `k`, `v`) are strictly forbidden. All variable names MUST be at least 3 characters long.
* **Zero Direct Git Commits:** Do NOT execute git commit, git push, or direct branch operations.
* **Mandatory `MQC` Project Prefix:** The `MQC` prefix is required on every test artifact without exception, modules (`mqc_<layer>_<component>.py`), classes (`TestMQC<Component>`), and callables (`MQC_<LAYER>_<6DIGIT_ID>_<behavior>`). It is not a property of the layer and does not vary by test type. The `test_` prefix is prohibited at every level. The `<LAYER>` token (`UNI`, `SYS`, `EVAL`, and any later addition) is an extensible registry defined in `.claude/rules/testing-standards.md`; extending it never relaxes the prefix requirement.
* **Designed Means Shipped:** everything in the design documents ships in v1. Nothing specified is deferred and nothing ships undesigned. A v2 feature re-enters Phase 0 before it is built; it never arrives as an amendment to running code.
* **Downstream Reporting Only:** this repository publishes standard CI artifacts for read-only downstream consumption. It MUST NOT depend on, import from, or write into any consumer, and it names none.
* **The Harness Owns No Case Data:** task data, golden rules, replay fixtures and code excerpts belong to `AP-Model-QC`. A check here that reads a file that repository owns is a boundary violation, and one shipped undetected until the split made it real. If a new check needs case data, the check belongs on the other side.
* **Every Tracked File Carries An SPDX Header, Written When The File Is Created:** Python takes two comment lines above the module docstring, markdown an HTML comment, YAML the `#` prefix it already uses. All name Apache-2.0 here. `code-style.md` sections 1.1 and 1.2 have the forms, and `MQC_CMN_UNI_112502` and `112503` enforce them. **A generator emitting a file emits the header with it**, and a header added in a later pass means the step was skipped: 54 files once accumulated without one because each was written to solve something else. `LICENSE` and `NOTICE` are excluded, being the licence text itself.
