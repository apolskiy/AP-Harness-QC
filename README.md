<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# AP-Harness-QC

**The harness.** An automated evaluation harness for foundation models: it
ingests hand-authored evaluation cases, dispatches them to provider endpoints,
judges the responses with deterministic assertions alongside an LLM-as-a-Judge
pass, and produces a verdict with a durable per-test record.

The evaluation cases it runs live in
[AP-Model-QC](https://github.com/apolskiy/AP-Model-QC), which consumes this
repository as a pinned dependency.

## Status

**Phase 3, and iterating.** All four modules implemented, seven CI workflows
written. The design is a specification rather than a description of what
exists: section 12 of `docs/design/tier1_ingestion.md` and the deferral tables
beside it carry what is specified and not yet built.

| Piece | State |
|---|---|
| `ingestion/`, `execution/`, `evaluation/`, `cmn/` | Implemented |
| Instrument suite (`UNI`, `SYS`) — tests **of this harness** | **568 cases, all passing**. Nothing here measures a model |
| Gate 1, pylint at `fail-under=10.0` | **10.00/10** |
| CI workflows | Seven, written and linted |
| Requirements traced | 259, none uncovered, none untraced |
| Specified and not yet built | Recorded as deferrals, not as silence |

Every case is inventoried in a design document before it is implemented, traced
in `docs/testing/rtm_harness.csv`, and checked in both directions by
`MQC_CMN_UNI_112303`, `112305`, `112306`, `112226` and `112313`. That order is
enforced mechanically rather than by intention.

## What A Green Suite Here Means, And What It Does Not

**Every test in this repository is a test of the instrument.** A green run says
the harness dispatches, judges, records and reports correctly. **It says nothing
whatsoever about any model.**

| Layer | Defined in | Subject | A failure is |
|---|---|---|---|
| `UNI` | here | our own modules, in isolation | **our defect** |
| `SYS` | here | this harness end to end, over recorded transcripts | **our defect** |
| `EVAL`, `TOOL`, `SEC` | [AP-Model-QC](https://github.com/apolskiy/AP-Model-QC) | a vendor's model against graded cases | **a finding about that model** |

**This repository defines no graded case, and `MQC_CMN_UNI_112327` enforces
that.** It reads which layers are graded from the layer registry rather than
naming them, so the rule covers a graded layer added later. Where a case here
carries `layer="EVAL"`, it is a fabricated observation exercising the machinery
that handles graded results — the plumbing is tested with synthetic data and
never with a provider.

**That separation is the reason there are two repositories.** A finding about a
model is only worth filing if the instrument that produced it is known-good, and
establishing that is this repository's entire job. It is a precondition for the
findings, not a result alongside them.

**The model results live in the other repository**, where four gates are
expected to be red because they found something. Its README states how many
cases run against each model and what each red means.

## Running It

```bash
python -m pip install --editable ".[dev]"
pytest -m unit
```

**No credentials are required.** `--mode` defaults to `replay`, so an
unconfigured clone cannot spend quota or emit an unmarked live result. See
`.env.example` for what each key unlocks; only `GEMINI_API_KEY` is provisioned
in v1, and only the live schedule needs it.

**To dispatch a debug, diagnostic or regression run, read
`docs/running_jobs.md` instead.** It is the whole operating procedure and it
requires no design reading: which of the three workflows, which inputs, what
comes back, and what each exit code means.

## Consuming It From A Case Repository

The harness reference is an **input**, which is the point of the split:

```bash
python -m pip install "ap-harness-qc @ git+https://github.com/apolskiy/AP-Harness-QC@main"
```

Swap `@main` for a tag, a stabilization branch or a commit. A regression is then
attributed by holding one side fixed and moving the other, rather than by
reverting a shared tree.

## What It Does

| Concern | Approach |
|---|---|
| Ingestion | Hand-authored YAML and CSV, validated into frozen typed records with strict referential integrity |
| Execution | One request per case across modular provider adapters. Tool calls are captured, never executed |
| Evaluation | Programmatic assertions gate the outcome; a rubric scores quality within it |
| Security | Candidate output is isolated from judge instructions by construction, and injection resistance is itself graded |
| Verdict | A pure function of observations, recomputable from stored artifacts |
| Cost | Runs on a free tier by design, so harness and cases can be iterated freely |

Results are published as standard CI artifacts, JUnit XML and Allure, for
read-only downstream consumption. This repository depends on no consumer and
names none.

**To download a run's results and view them**, `docs/running_jobs.md` section 5 has the artifact names, the `gh run download` line and the Allure commands, verified against Allure 2.41.0.

## Repository Layout

`DESIGN.md` section 2.1 holds the full tree with a line per file. In short:

| Path | Holds |
|---|---|
| `ingestion/`, `execution/`, `evaluation/`, `cmn/` | The four modules, one per architectural boundary |
| `tests/` | Mirrors the module tree; test layer is a pytest marker, not a directory |
| `docs/design/`, `docs/testing/` | Specifications, the harness test plan, traceability |
| `config/` | Engine roster, declared capability gaps, quarantine. Never a credential |
| `tools/` | Generators and maintenance scripts, never harness code |
| `.github/workflows/` | Seven workflows, named `<verb>[-<subject>]-<cadence>.yml` |

## Known Constraints

Evaluation is English-only, and the constraint is structural rather than
cosmetic: the sentence, capitalization and word-count checks are parsers with
English assumptions. Recorded as B11.

macOS is not claimed. CI verifies Ubuntu and Windows; the two risk axes are each
covered individually and only their combination is untested. Recorded as A18.

## Where To Start

Read in this order. Each step assumes the one before it.

1. **`README.md`** (this file) states what the repository is.
2. **`DESIGN.md`** gives the architecture, a map of every design document, and
   the decisions that shape the rest.
3. **`docs/design/`** holds the specifications themselves.

`CHANGELOG.md` records release history. `CLAUDE_LOG.md` is the running record of
decisions and the reasoning behind them.

## Licence

Apache 2.0, with a `NOTICE` file. The case repository is MIT: the patent grant
matters for a tool others depend on, and the cases are material people copy and
adapt. Every Python file carries an SPDX header, enforced by
`MQC_CMN_UNI_112502`.
