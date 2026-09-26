<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# Framework Architecture & System Rules

## 1. CI Pipeline & Quality Gates

All pull requests and code additions must pass a multi-stage automated verification gate:
1. **Gate 1 - Static Analysis & Naming Gate**: Execution of `pylint --rcfile=.pylintrc` across all package modules. The >= 3 character naming rule is enforced mechanically by the `variable-rgx`, `argument-rgx`, `attr-rgx` and `inlinevar-rgx` patterns in `.pylintrc`, so a single-character binding fails the build rather than relying on review. Code must achieve a **10.00/10 score** before unit tests run.
2. **Gate 2 - Unit Precondition**: Execution of `MQC_<MODULE>_UNI_#####` tests via `pytest -m unit`. Ungraded: **100% pass and zero skips required**. Failure stops the pipeline.
3. **Gate 3 - System Precondition**: Execution of `MQC_<MODULE>_SYS_#####` tests via `pytest -m system` in **replay mode**. Ungraded: 100% pass required. A precondition that can flake is not a precondition, so it never runs live here; a live SYS smoke runs separately on the schedule.
4. **Gate 4 - Evaluator Agent Run** (graded): Execution of `MQC_<MODULE>_EVAL_#####` rubric and scoring tests via `pytest -m evaluator`. Subject to the priority gate and the 90% pass floor.
5. **Gate 5 - Tool-Use Compliance**: Execution of `MQC_<MODULE>_TOOL_#####` tests via `pytest -m tool`. Verifies the model invoked the tools it was instructed to use and avoided those it was forbidden. Tier 2 captures tool-call intent without executing it.
6. **Gate 6 - Model Security Suite** (graded): Execution of `MQC_<MODULE>_SEC_#####` tests via `pytest -m sec`. Injection resistance, prompt leakage and tool coercion. Runs as its own suite and is exempt from the priority distribution ceilings, so security coverage never competes with functional coverage for a budget.
7. **Gate 7 - Artifact Publication**: Upload JUnit XML and Allure raw results as stably-named GitHub Actions artifacts. This is the entire integration surface. A downstream collector pulls these read-only; this repository neither writes to a consumer nor blocks on one. No bespoke telemetry file is generated. See `testing-standards.md` section 5.

## 2. Module Separation Rules

Four modules. Each exposes a stable interface; crossing a boundary means satisfying that interface, never reaching into an implementation.

| Module | Code | Path | Owns |
|---|---|---|---|
| Ingestion | `ING` | `ingestion/` | Loading, validation, referential integrity |
| Execution | `EXE` | `execution/` | Dispatch, normalization, tool-call capture |
| Evaluation | `EVL` | `evaluation/` | Screening, isolation, assertions, judging |
| Cross-cutting | `CMN` | `cmn/` | CLI, configuration, verdict, metadata, traceability |

### Tier 1: Ingestion (`ING`)
* **Boundary rule**: `TaskDataSet` is **what you send**; `GoldenRuleSet` is **how you judge what comes back**. Every field placement follows from this. Tool definitions are input, tool expectations are judgement, and the same tool legitimately appears in both.
* **Schema enforcement**: all ingested data passes through frozen `@dataclass` validators with strict key checking, explicit casting, and rejection of unknown fields.
* **Referential integrity**: five cross-schema checks run after the join, including that every constraint sent to a model has a corresponding check.
* **No network, no engine knowledge.** Tier 1 does not know that engines exist.

### Tier 2: Execution (`EXE`)
* **Multi-provider dispatch** through modular adapters implementing one stable interface.
* **One request per case. No loop, no agentic cycle, no tool execution.** The model's tool-call *intent* is captured and recorded; it is never executed. Tool usage is **behaviour under test**, not a prohibition.
* **Provider-specific types stop at the adapter.** A vendor object reaching Tier 3 is a design defect.
* **Does not screen and does not evaluate.** An adapter that begins interpreting output has become a second evaluator with no rubric.

### Tier 3: Evaluation (`EVL`)
* **Owns the post-execution injection screen**, on the principle that the component the untrusted content threatens owns its own defence.
* **Isolation is the control, screening is a measurement.** Candidate output never enters the judge's instruction text. The screen is programmatic and never a model call, because a model asked to detect injection is itself injectable.
* **Dual-evaluation pass**: programmatic assertions plus LLM-as-a-Judge scoring. **Assertions are conjunctive gates**, so a case passes only when every assertion passes and the rubric clears its threshold.
* **Judge output is schema-constrained; candidate output deliberately is not**, so that schema-following remains measurable as a model quality.

### Cross-cutting (`CMN`)
* **The verdict is a pure function** of observations, configuration and an injected date. No clock, no filesystem, no environment.
* Owns the CLI contract, configuration loading, result metadata emission, and traceability checks.

## 3. Test Case Types

### 3.1 Layers

| Layer | Marker | Graded | Requirement |
|---|---|---|---|
| `UNI` | `unit` | No, precondition | 100% pass, zero skips. Blocks everything below |
| `SYS` | `system` | No, precondition | 100% pass, replay mode |
| `EVAL` | `evaluator` | Yes | Priority gate and the 90% pass floor |
| `TOOL` | `tool` | Yes | As above |
| `SEC` | `sec` | Yes | Own suite, exempt from distribution ceilings |

Preconditions test **our harness**; a failure is our defect. Graded layers test **the model**; a failure is a finding about a third party.

### 3.2 Categories

Every case is marked positive, negative or boundary. **Boundary cases are named at each threshold exactly**, not near it: a rule stated as "below 90%" is tested *at* 90%, because off-by-one at a boundary is the likeliest defect in any gate.

### 3.3 Priority

Graded cases carry P0 to P4 with the matched qualifying condition named; a priority without a named condition is not assignable.

**Preconditions carry no priority because they sit above the scale.** Every one is unconditionally blocking: a failure stops the graded layers executing, so the run exits 3 and measures nothing. P0 is the most severe level **within** the graded budget, and a budget only exists where claims compete for it. Preconditions do not compete, which is why the scale has nothing to say about them and why the absence of a marker is not a statement about stakes.

### 3.4 Foundational cases

A case whose result others presuppose is marked `base`. Its failure means dependents are **not executed** and are recorded as skipped with `QC_HARNESS_DEPENDENCY_UNMET`, never as failed.

## 4. Failure Taxonomy

Every failure carries a code, attached to the assertion message and to the Allure label so that root-cause class is recoverable from the artifact alone.

| Family | Asserts | Outcome |
|---|---|---|
| `QC_LLM_*` | The model under test performed poorly | Fail |
| `QC_HARNESS_*` | Our code or infrastructure broke | Skip or broken, never fail |
| `QC_DATA_*` | An ingestion event, carrying its own severity | Info, warning or error |
| `QC_SEC_*` | A security finding, neither quality nor harness | Fail, some blocking |

**The families split by what the code asserts about, not by severity.** A blank cell taking its default is normal operation and must not be recorded as a harness defect, or every later count of harness reliability is corrupted.

### 4.1 One registry

**`docs/design/test_taxonomy.md` section 6 is the single registry of codes.** This file states the families and their meaning; it deliberately does **not** restate the code list.

Two registries drift, and this file previously carried a stale copy naming two families when four existed. A code is registered in one place, and `MQC_CMN_UNI_10143` through `10145` verify that every emitted and referenced code is registered there.
