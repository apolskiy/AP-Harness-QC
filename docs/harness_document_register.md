<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->

# Document Register

**Every tracked document in this repository, and what it holds.** Added
2026-10-04 at the project owner's instruction, after `harness_test_taxonomy.md` was
found to have fallen behind the changes made around it.

**This is the list a documentation review works through.** `DESIGN.md` section 3
says what to read **first** and what each design covers; this says what
**exists**. They answer different questions, and the second is the one a review
needs: a document absent from the list a reviewer holds is a document nobody
reviews.

**It is checked in both directions.** `MQC_CMN_UNI_112255` reports a tracked
document this register does not name, and a path this register names that is not
there. A register maintained by intention goes stale the first time a document is
added in a hurry, which is the pattern this project has corrected often enough
to stop writing new instances of.

**`CLAUDE.md` requires reading this before any work**, which is the other half:
a complete list nobody opens prevents nothing.

## Specifications

| Document | Holds |
|---|---|
| `DESIGN.md` | The referential index. Architecture, the reading order, and the decisions shaping everything downstream |
| `docs/design/harness_phase0_project_ambiguities.md` | Every project-level decision, with what was rejected and why. Cited as A1 to A13 and B1 to B10. A dated record, never rewritten |
| `docs/design/harness_test_taxonomy.md` | The single registry of identifiers, priorities, failure codes, the outcome model, verdict rules, required result metadata and the evaluation family registry |
| `docs/design/harness_extensibility_standard.md` | How the system absorbs a new provider, layer or test type. Tier contracts, adapter interface, conformance suites, schema versioning |
| `docs/design/tier1_ingestion.md` | Schemas, loaders, validation policy, referential integrity, ingest-time screening, calibration |
| `docs/design/tier2_execution.md` | Adapter interface, response and tool-call shapes, model version resolution, replay integrity, rate limiting |
| `docs/design/tier3_evaluation.md` | Ingress screening and isolation, dual-pass evaluation, judge invocation, aggregation, calibration |
| `docs/design/cmn_verdict_and_cli.md` | Verdict computation, both CLI surfaces, exit codes, configuration, metadata emission, RTM integrity, subset selection |
| `docs/design/harness_ci_pipeline.md` | The workflows, their triggers, the branch topology and pairing rule, the credential boundary, artifact naming |

## Test planning

| Document | Holds |
|---|---|
| `docs/testing/harness_test_plan.md` | Every harness requirement, traced to the precondition cases in the module designs |
| `docs/testing/rtm_harness.csv` | Harness requirements mapped to precondition cases, verified both ways |
| `docs/testing/identifier_map.csv` | Old to new identifier, from the move to six digits, so stored history stays readable |

## Operations and decisions

| Document | Holds |
|---|---|
| `docs/harness_document_register.md` | **This file.** Every tracked document and what it holds, checked against the repository both ways |
| `README.md` | **The latest state only.** What the project is, how to run it, the current figures. Never a history |
| `docs/harness_running_jobs.md` | How to run each workflow and what each one spends |
| `docs/harness_open_questions.md` | Decisions waiting on a person, and the blockers only the account owner can clear. **Not a backlog** |
| `CHANGELOG.md` | **How the project arrived at its current shape.** The history a reader needs to understand why something is the way it is |
| `CLAUDE_LOG.md` | Decisions and their reasoning in date order, written for an external reader. What was found, what it broke, what the injection showed |
| `docs/harness_problems_found.md` | **The index over the log**, grouping what this project found by the shape of the defect: model findings, machinery that was right and unreachable, checks that fed themselves, records wrong about their own reason, and tooling defects |

**`README.md`, `CHANGELOG.md` and `CLAUDE_LOG.md` divide by time, not by topic.**
The README says what is true now, the changelog says how it became true, and the
log says what was learned on the way. A reader wanting the current figures should
not have to read history to find them, and a reader wanting the reasoning should
not have to infer it from a figure.

## Governance

Each of these is normative and each is loaded before work begins, per
`CLAUDE.md`.

| Document | Holds |
|---|---|
| `CLAUDE.md` | The directive router: what to read, the core directives, the boundaries |
| `.claude/rules/code-style.md` | Naming, annotations, docstrings, imports, layout, cross-platform rules, the pylint gate |
| `.claude/rules/framework-rules.md` | Module separation, the CI quality gates, test case types, the failure taxonomy families |
| `.claude/rules/testing-standards.md` | Test naming, the inventory principle, authoring order, change-scoped selection, the artifact contract |
| `.claude/skills/skill-rules.md` | The phased execution pipeline, git safety, logging rules |
| `.claude/skills/test-generator.md` | Scaffold for a new `MQC_*` pytest module |
| `.claude/skills/validator-generator.md` | Scaffold for a `@dataclass` schema validator |
| `.claude/worktrees/worktree-rules.md` | Worktree isolation, branch boundaries, environment safety |

## What this register does not list

**Working material is not a project document.** The author's own notes are not
deliverables, are not tracked, and are deliberately absent from this list: a
register of what a reviewer works through should name what a reviewer can be
given. The governance files state where prompts go and that they are never
committed, which is the rule; this list is the inventory, and the two answer
different questions.

**Nothing is copied from working notes into `CLAUDE_LOG.md`**, which records
decisions and outcomes rather than phrasing. Verified 2026-10-05: no tracked
file in either repository quotes a prompt, and every reference to the author's
instructions attributes a decision rather than reproducing its wording.

## Documents in the case repository

Named here because this repository's designs cite them constantly and a reader
following a citation needs to know where it points. **They are never copied into
this repository**, per `CLAUDE.md`.

| Document | Holds |
|---|---|
| `model_evaluation_test_plan.md` | The evaluation requirements and the graded case inventory |
| `rtm_model.csv` | Evaluation requirements mapped to graded cases, with their evaluation families |
| `consumer_ci.md` | The case repository's own CI topology and harness pinning |

## Renamed documents

A renamed document keeps its former name recorded here, for the reason
`testing-standards.md` section 3.2 gives about identifiers: `CLAUDE_LOG.md`
carries the old path in entries that were true when written, and a reader of
that history has to be able to follow it.

**Renamed 2026-10-08** at the project owner's instruction, so an open editor tab
says which checkout a file belongs to (`code-style.md` section 7.2). A generic
name is a collision waiting to happen: any repository carrying tests has a
taxonomy, a pipeline, an extensibility standard and project phases.

| Now | Former name |
|---|---|
| docs/harness_running_jobs.md | was `docs/running_jobs.md` |
| docs/harness_document_register.md | was `docs/document_register.md` |
| docs/harness_open_questions.md | was `docs/OPEN_QUESTIONS.md` |
| docs/harness_problems_found.md | was `docs/problems_found.md` |
| docs/design/harness_test_taxonomy.md | was `docs/design/test_taxonomy.md` |
| docs/design/harness_ci_pipeline.md | was `docs/design/ci_pipeline.md` |
| docs/design/harness_extensibility_standard.md | was `docs/design/extensibility_standard.md` |
| docs/design/harness_phase0_project_ambiguities.md | was `docs/design/phase0_project_ambiguities.md` |

**Four names were deliberately left alone**, each already naming a harness tier
or a harness module, so a reader with one open knows where they are:
`tier1_ingestion.md`, `tier2_execution.md`, `tier3_evaluation.md` and
`cmn_verdict_and_cli.md`. `MQC_CMN_UNI_112346` holds that list and fails on a
fifth.
