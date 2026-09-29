<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# AP-Harness-QC: Design Overview

> **Status:** current as of 2026-09-28. **Phase 3: the harness is implemented across all four modules and seven CI workflows, the graded model evaluations are written, and the security family is recorded and passing against a paid tier.** What remains unrecorded is the `EVAL` and `TOOL` corpus, which section 7.4 carries as a known gap. The 3-phase workflow in `.claude/skills/skill-rules.md` forbade code before a closed Phase 0 register and an approved Phase 2 design, and that order is now enforced mechanically by `MQC_CMN_UNI_10183`, `10186` and `10187` rather than by intention.
>
> **Purpose:** the referential basis for every other design document. It states what the system is, which document holds which decision, and where the boundaries between them fall. It does not restate their contents.

---

## 0. Reading Order

Three steps, in order. Each assumes the one before it.

1. **`README.md`** states what the repository is and its current state.
2. **`DESIGN.md`** (this document) gives the architecture, the document map, and the decisions that shape everything downstream.
3. **The individual design documents** under `docs/design/` carry the specifications themselves.

A reviewer who follows that sequence never meets a term before it has been defined. Within step 3, read the three normative references in section 3.1 before any module design, since the module designs cite them by item number rather than restating them.

---

## 1. What This Is

An automated evaluation harness for foundation models. It ingests hand-authored evaluation cases, dispatches them to one or more public LLM endpoints, judges the responses with a combination of deterministic assertions and an LLM-as-a-Judge pass, and produces a verdict with a durable per-test record.

**The deliverable is the evaluation of the model, not the harness.** The harness is a product for QA automation engineers and is never released to a customer. That distinction governs the document structure described in section 4.

---

## 2. Architecture

Three tiers plus a cross-cutting module. Each exposes a stable interface; crossing a boundary means satisfying that interface, never reaching into an implementation.

| Module | Code | Responsibility |
|---|---|---|
| Ingestion | `ING` | Files to validated, typed objects. No network, no engine knowledge |
| Execution | `EXE` | Dispatch to provider endpoints, response normalization, tool-call capture |
| Evaluation | `EVL` | Programmatic assertions plus LLM-as-a-Judge scoring |
| Cross-cutting | `CMN` | CLI, configuration, verdict computation, metadata emission, traceability |

Data flows in one direction, and **no tier drives the sequence**. The orchestrating test holds the case, calls each tier through an injected fixture, and passes each only the subset it needs. Tiers emit **results**; a reporting hook assembles those results with the case metadata into observations written to artifacts. `CMN` reads observations from artifacts and decides what they mean.

Tier 3 never receives `priority`, so it is structurally incapable of producing a complete observation. That is deliberate: nothing about how severely a failure will be treated should be visible to the component deciding whether it failed.


### 2.1 Repository layout

```
ingestion/                    ING: files to validated, typed objects. No network
  schemas.py                  Frozen dataclasses; from_dict with strict key checking
  loaders.py                  CSV and YAML readers. No type inference, blank is not null
  integrity.py                The five cross-schema checks, R1 to R5
  screening.py                Boundary injection screen, unless declared adversarial
  cases.py                    Task and rubric join; one EvaluationCase per pair
execution/                    EXE: dispatch, normalization, tool-call capture
  adapters/
    base.py                   The stable interface, plus ConfiguredAdapter and
                              ProviderFacts, which three adapters converged on
    registry.py               Engine name to adapter. What the battery parametrizes over
    gemini.py                 Judge and candidate, live. The default engine
    openai.py                 Replay only under A3, until a key is provisioned
    claude.py                 Replay only under A3, until a key is provisioned
  dispatch.py                 One request per case. No loop, no tool execution.
                              Also pacing, retry and the circuit breaker
  normalize.py                Canonical response shape. Vendor types stop at this line
  replay.py                   Fixture store keyed by case, engine, observation index
  preflight.py                Model version resolution; its absence fails the run
evaluation/                   EVL: programmatic assertions plus LLM-as-a-Judge
  isolation.py                UnauthoredMaterial: A19 trust boundary, made a type
  screening.py                Post-execution screen. Never a model call
  assertions.py               Conjunctive gates; every assertion passes or the case fails
  judge.py                    Schema-constrained invocation and reply validation
  aggregation.py              Scale-declaring aggregation; scales never mix
  calibration.py              Drift detection against anchored exemplars
  pipeline.py                 The six steps in order, and the decisions between them
cmn/                          CMN: CLI, configuration, verdict, metadata, traceability
  options.py                  One option registry, feeding pytest and the verdict tool
  verdict_tool.py             The standalone tool. Exit codes 0, 1, 2, 3, 4
  config.py                   Configuration loading; refuses a credential-shaped key
  verdict.py                  Pure function of observations, configuration, injected date
  layers.py                   Layer and outcome registries the verdict reads, never names
  observations.py             The observation record; gated is derived, never set
  demotion.py                 Ordering when a ceiling binds; security never demoted
  metadata.py                 Result emission and the diagnostic summary
  traceability.py             T1 to T5 checks over the two matrices
  registries.py               Taxonomy codes, priority conditions, evaluation families
  vectors.py                  The injection vector registry, SHARED by both screens
  pytest_support.py           The pytest hooks, called by BOTH repositories' conftests
  code_standards.py           The rules pylint cannot express, over a root and a licence
tools/
  generate_requirements.py    Generates the requirements files from pyproject.toml
conftest.py                   Fixture injection, priority to severity, option surface
tests/                        testpaths in pytest.ini. Module from directory,
                              layer from filename; taxonomy section 2.1
  ingestion/mqc_uni_*.py      Harness preconditions; a failure is our defect
  ingestion/mqc_sys_*.py
  execution/mqc_uni_*.py
  execution/mqc_sys_*.py
  execution/provider_doubles.py   Provider-shaped doubles. Not collected: no mqc_ prefix
  evaluation/mqc_uni_*.py     Harness preconditions for the evaluation tier
  evaluation/mqc_sys_*.py
  cmn/mqc_uni_*.py
                              The GRADED layers are absent by design. mqc_eval_*,
                              mqc_tool_* and mqc_sec_* live in AP-Model-QC with
                              the data they exercise, along with the replay
                              fixtures and the code excerpts. Section 5.1 carries
                              the boundary
config/                       Loaded by cmn/config.py. NEVER a credential
  engines.yaml                Engine roster: model, spacing, observations, timeout
  unsupported.yaml            Declared capability gaps, each with its reason
  consumers.yaml              Case repositories the fan-out verifies against
  quarantine.yaml             Quarantined cases, each with an expiry
docs/design/                  Module specifications and the Phase 0 register
docs/testing/                 Test plans and the two traceability matrices
.github/workflows/            Named <verb>-<subject>-<cadence>.yml, see the CI design
  gate-on-change.yml          Blocking gate, replay, no credentials
  regress-harness-on-branch.yml     Full unscoped suite on one ref, gated
  regress-consumers-on-merge.yml    Fan-out: does this branch still pass its paired consumers
  probe-model-version-nightly.yml   Detects a model version change, dispatches
  evaluate-live-weekly.yml    The only workflow that spends provider quota
  diagnose-on-demand.yml      Ungated troubleshooting, two refs, never recorded
  debug-failures-on-demand.yml      Re-runs named tests, repeats to find a flake
```

#### Where implementation diverged from the first draft of this tree

Recorded 2026-09-23 rather than quietly corrected, because a layout naming files that do not exist is worse than none: a reader trusts it.

| First drafted as | Built as | Why |
|---|---|---|
| `evaluation/screen.py`, `aggregate.py` | `screening.py`, `aggregation.py` | Matching `ingestion/screening.py`. A noun and a verb for one concept read as two concepts |
| `cmn/cli.py` | `options.py` and `verdict_tool.py` | The registry and the tool consuming it are separate concerns, and the registry feeds two surfaces |
| `cmn/selection.py` | Folded into `options.py` | Selection mode is derived from which flags were supplied, so it lives with the flags |
| `cmn/ci_report.py` | Folded into `metadata.py` | The diagnostic summary is result metadata for a run that produces no verdict |
| Not drafted | `evaluation/pipeline.py` | The six steps needed somewhere to be sequenced |
| Not drafted | `cmn/layers.py`, `observations.py`, `demotion.py` | Registries the verdict reads, split out so it names no layer |
| Not drafted | `cmn/vectors.py` | One vector registry, shared, so the two screens cannot disagree |
| Not drafted | `execution/adapters/registry.py` | The conformance battery parametrizes over it |

**A file name carries what nothing else carries, and nothing more.** The module is in the path, so repeating it in the name duplicates the path. The layer is in no path, so it goes in the name. That one principle produces both halves of the convention, including the half that looks inconsistent: harness modules take no prefix and test modules take two tokens. Normative in `test_taxonomy.md` section 2.1.

**Production modules carry no `mqc_` prefix; test modules must.** The prefix is a requirement on test artifacts, because those are what the suite collects and what reaches a durable record under a name that must stay unambiguous. A production module is never collected and never named in a result, so prefixing it would add noise without adding identity. `.pylintrc` accepts both spellings for exactly this reason.

**Tests mirror the production modules rather than the layers.** Change-scoped selection resolves changed paths to the tests covering them, so a test tree shaped like the production tree makes that mapping direct. Gates select by marker, not by path, which leaves the layer free to be an attribute of a class rather than a directory. Shaping the tree by layer instead would make the marker redundant, scatter one module's tests across five directories, and leave path-scoped selection with nothing to resolve against.

**`selection.py` and `ci_report.py` exist because CI decisions are Python, not YAML.** `ci_pipeline.md` section 10 states that decision logic lives where a test can reach it and the workflow files only call it. Selection resolves a diff into a test set, a `selection_mode` and a changed-area split of harness against tests; `ci_report.py` assembles the diagnostic summary and decides whether a run is a failure-to-pass transition. Both were specified with test cases before they had a module, which a layout written ahead of the CI design did not anticipate.

**The deliberately broken code excerpts live in the case repository**, along with the guards asserting they still exhibit their defects. They moved there on 2026-09-23: they are input to graded cases, and a harness check reading them was a cross-boundary dependency that only became visible when the boundary became real. Section 5.1 records what that cost to find.


---


### 2.2 Identifiers that moved, and the gaps they leave

Added 2026-09-25, from an RTM review.

Section 2.1 records paths that were drafted under one name and built under
another. **The same thing happens to identifiers and nothing recorded it**, so
the matrices carry gaps a reader cannot interpret.

| Retired | Became | Why |
|---|---|---|
| `MQC_REQ_HAR_CMN_0027` | `MQC_REQ_CAS_PRE_0001` | The excerpt guards read case-side data, so the requirement moved with them at the split (section 5.1) |
| `MQC_REQ_HAR_EVL_0034`, `0035` | **Nothing** | The judge panel is out of scope (A3.2). Measuring judge divergence is a finding about judges, and acting on it needs a judge over the judges |
| `MQC_REQ_HAR_CMN_0079` | **Nothing** | As above: it configured the panel |
| `MQC_EVL_UNI_10392`, `10393` | **Nothing** | The cases for panel divergence and panel failure |
| `MQC_CMN_UNI_11167` | **Nothing** | The case for the configured panel |

**A retirement to nothing is not the same as a relocation.** The rows above the
rule moved and are alive elsewhere; these were withdrawn because the feature was
declared out of scope, and their numbers stay retired so no later case can
inherit a meaning it does not have.

**An identifier is never reused**, here as for test cases: a retired number
stays retired so downstream history cannot silently rebind it. A gap in the
numbering is therefore expected and is not a defect.

**What was missing is the explanation, not the number.** A reader of
`rtm_harness.csv` sees `MQC_REQ_HAR_CMN` jump from 26 to 28 and has no way to
learn that 27 is alive in the other repository. `DESIGN.md` said so in prose at
section 5.1 and `CHANGELOG.md` said so in passing; **neither is where somebody
reading the register is looking.**

#### 2.2.1 The gaps that are not relocations

Most gaps are simply unallocated. The blocks were partitioned per module with
room to grow, and numbers were assigned as requirements were written rather
than contiguously:

| Block | Allocated | Highest | Gaps |
|---|---|---|---|
| `MQC_REQ_HAR_CMN` | 71 | 76 | 5 |
| `MQC_REQ_HAR_EXE` | 43 | 71 | 28 |
| `MQC_REQ_HAR_ING` | 32 | 48 | 16 |
| `MQC_REQ_HAR_EVL` | 27 | 35 | 8 |

**An unallocated number is not a missing requirement.** The check that matters
is the one `MQC_CMN_UNI_11122` performs in both directions: every requirement
has a case and every case names a requirement. It passes, and it would fail if
a gap meant something had been lost rather than never written.

**Two identifiers are deliberately absent and always will be.**
`MQC_REQ_HAR_ING_0099` and `MQC_REQ_HAR_ING_0404` appear only in
`tests/cmn/mqc_uni_traceability.py`, as the unknown requirement a test names to
prove the T4 check reports one. A checker for dangling references has to name
something dangling.

## 3. Document Map

### 3.1 Normative references

Read these before any other document; the rest assume them.

| Document | Holds |
|---|---|
| `docs/OPEN_QUESTIONS.md` | Decisions waiting on a person, and the blockers only the account owner can clear. **Not a backlog**: unfinished work is a known gap in section 7.4 | **Live** |
| `docs/design/phase0_project_ambiguities.md` | Every project-level decision, with the options considered and the reason each was chosen. Items are cited elsewhere as A1 to A13 and B1 to B10. A dated record: it is never rewritten to match later decisions |
| `docs/design/test_taxonomy.md` | What every identifier means. Module and layer registries, priority definitions and distribution ceilings, the outcome model, four failure taxonomy families, the run verdict rules, required result metadata |
| `docs/design/extensibility_standard.md` | How the system absorbs a new provider, layer, suite, or unanticipated test type. Tier API contracts, the adapter interface, conformance suites, interface stability tiers, schema versioning, deprecation |

### 3.2 Module and pipeline designs

| Document | Covers | Status |
|---|---|---|
| `docs/design/tier1_ingestion.md` | Schemas, both loaders, validation policy, referential integrity, ingest-time injection screening, calibration, aggregation strategies. 89 cases | **Implemented** |
| `docs/design/cmn_verdict_and_cli.md` | Verdict computation, the two CLI surfaces, exit codes, configuration, metadata emission, RTM integrity, diagnostic runs, subset selection. 189 cases | **Implemented** |
| `docs/design/ci_pipeline.md` | The seven workflows, their triggers, the branch topology and pairing rule, the credential boundary, artifact naming, secrets, exit code mapping. Probe cases live in the Tier 2 inventory | **Implemented** |
| `docs/design/tier2_execution.md` | Adapter interface, canonical response and tool-call shapes, model version resolution, replay integrity, rate limiting, conformance suite. 112 cases | **Implemented** |
| `docs/design/tier3_evaluation.md` | Ingress screening and isolation, dual-pass evaluation, judge invocation and reply validation, aggregation, calibration. 101 cases | **Implemented** |

`ci_pipeline.md` is the one entry here that specifies no module. It describes how the four modules are executed rather than what any of them does, and it sits in this table because a reader looking for specifications should find all of them in one place.


### 3.3 Test planning

| Document | Covers | Status |
|---|---|---|
| `docs/testing/harness_test_plan.md` | 113 harness requirements, traced to the precondition cases in the module designs | **Implemented, traced both ways** |
| `model_evaluation_test_plan.md` **in `AP-Model-QC`** | 73 evaluation requirements and 69 graded cases across `EVAL`, `TOOL` and `SEC` | Written, and all 69 cases built |
| `docs/testing/rtm_harness.csv` | Harness requirements mapped to precondition cases | Written |
| `rtm_model.csv` **in `AP-Model-QC`** | Evaluation requirements mapped to graded cases | Written |

### 3.4 Governance and record

| File | Tracked | Holds |
|---|---|---|
| `CLAUDE.md` | Yes | Directive router |
| `.claude/rules/`, `.claude/skills/`, `.claude/worktrees/` | Yes | Code style, framework rules, testing standards, workflow governance |
| `CLAUDE_LOG.md` | Yes | Decisions and their reasoning, in date order, written for an external reader |
| `CHANGELOG.md` | Yes | Release history. Versioning begins when harness implementation is complete |
| `.claude/logs/PROMPT_LOG.md` | **No** | Working notes |

---

## 4. Why The Documents Divide As They Do

**Design documents describe the harness. Test plans describe the model under evaluation.** The split follows the layer taxonomy rather than being an arbitrary partition:

| | Design document | Test plan |
|---|---|---|
| Subject | The harness | The agent and model |
| Layers | `UNI`, `SYS` | `EVAL`, `TOOL`, `SEC` |
| Assumes | Nothing | That the harness is complete |
| Released to a customer | No | Yes |

Harness tests appear in a test plan only as a stated precondition, never as its content. This also explains why `UNI` and `SYS` are ungraded: they do not measure the product, so they do not belong in the product's quality budget.

---

## 5. Decisions That Shape Everything Downstream

Stated here because a reader encountering them for the first time in a module design would lack the context. Full reasoning is in the Phase 0 register.

| Decision | Consequence |
|---|---|
| **Zero recurring cost** (A3) | A free-tier judge minimises the cost of expansion and repeated runs, which is what allows tests and harness to be iterated freely while stabilising. Paid engines can be added once stable; adopters supply their own keys |
| **Fixtures on pull request, live on a schedule** (A1) | The blocking gate is deterministic and free, credentials reach only the scheduled workflow, and fork pull requests work |
| **A model regression never blocks a merge** (A2, amended) | Red on a scheduled run is an alert. Nobody is pressured to loosen a threshold to unblock work |
| **A harness failure is a skip, not a failure** (A11.2) | `failed` thereafter denotes only a genuine model finding |
| **Replayed results are marked as replayed** (A6) | The downstream record never ingests a fabricated observation as a real one |
| **Capture tool calls, never execute them** (A9) | Tool compliance is measurable without the harness becoming an agent |
| **Isolation is the defence, detection is a measurement** (A5) | Candidate output never enters judge instruction text. Screening is programmatic and never a model call, because an LLM asked to detect injection is itself injectable |
| **Identifiers are never reused** | Retired test IDs, taxonomy codes and condition identifiers stay retired, so stored history cannot rebind a name to different behaviour |
| **One repository for harness and cases** (A17) | A demonstration constraint, not the production arrangement. Two repositories would let a case set run against a chosen harness version and let either roll back alone. The split boundary is documented and verified in section 5.1 |

---

### 5.0 Supported platforms

The harness is Python and adopters run it on machines this project did not choose. **Verified support and claimed support are separate lists**, because a claim CI does not exercise is a claim nobody checked.

| | Verified by CI | Claimed |
|---|---|---|
| Linux | `ubuntu-24.04`, pinned | Ubuntu 22.04 or later, and glibc distributions such as CentOS Stream |
| Windows | `windows-latest`, the current Windows Server image | Windows 11 or later |
| macOS | Not run | **Not claimed** |

`windows-latest` is not Windows 11. It shares the same path, filesystem and encoding semantics, so the claim holds, but what CI proves is the runner image.

#### 5.0.2 The Ubuntu image is pinned, and the Windows one is not yet

Changed 2026-09-26. **`ubuntu-latest` was a moving label**, and GitHub announced it
migrating to Ubuntu 26 on 19 October 2026, which it warns about on every run.

**Pinning is the engineering answer here rather than warning suppression.**
`code-style.md` section 8 exists because a platform difference that silently
changes a value is worse than one that raises: an encoding default, a path
separator, a filesystem's case sensitivity. An OS major arriving unannounced is
exactly that class of change, and it would arrive on a green branch with nothing
attributing it.

| | Moving label | Pinned image |
|---|---|---|
| An OS major arrives | Unannounced, on somebody's unrelated commit | When this line is edited |
| Maintenance | None | **A deliberate bump, and a run that proves it** |
| Warning noise | On every run, until it is not a warning | None |

**The cost is real and is accepted:** a pinned image stops receiving the newer
OS's coverage, so Ubuntu 26 compatibility is unknown until the pin moves. That is
the trade this project already makes everywhere else, preferring a failure that
names its cause to a difference nobody attributed.

**Windows stays on the moving label** because GitHub has announced no migration
for it, and pinning a label this project has not verified would risk a red run to
remove a warning that does not exist. The stale claim that `windows-latest` is
Windows Server 2022 is corrected above: it moved, which is the same argument for
pinning it when a migration is announced.

**macOS is a known gap, not an oversight.** It is excluded because no machine is available here to reproduce a failure on, and a CI leg nobody can debug is a liability rather than coverage. Its two risk axes are each covered individually, POSIX paths by Ubuntu and a case-insensitive filesystem by Windows; only the combination is untested. Reasoning in A18.

Both platforms run on every commit as separate jobs, and the live suite runs on Ubuntu alone because platform coverage tests the harness rather than the model. `.claude/rules/code-style.md` section 8 carries the engineering rules this imposes, each of which names a defect that is silent on one platform.

### 5.0.1 Dependencies are declared once, and the requirements files are derived

Specified 2026-09-23, after an audit found a dependency the suite relies on and nothing declared.

**`pyproject.toml` is the single declaration.** Runtime dependencies sit in `dependencies`, and everything the gates need sits in the `dev` extra. CI installs with `pip install --editable ".[dev]"`, so the file CI reads is the file a maintainer edits.

**Ranges, not pins.** An unpinned harness measures a moving target: a parser upgrade that changes how a sentence is counted would read as a model regression, which is the attribution failure this project exists to avoid. Ranges allow patch releases and nothing wider.

#### Why `requirements.txt` exists anyway, and why it is not a second declaration

Tooling expects it. PyCharm offers to install from a requirements file and does not read an optional-dependency extra, and a contributor who opens the project should not have to know which of two conventions this repository chose.

**They are generated from `pyproject.toml`, never hand-edited**, and `MQC_CMN_UNI_11108` fails the run when they disagree. That is the same rule applied everywhere else here: two statements of one fact drift, so either there is one statement or there is a check. A generated file plus a check is the second form, not an exception to the rule.

| File | Contains |
|---|---|
| `requirements.txt` | The runtime `dependencies` |
| `requirements-dev.txt` | The `dev` extra, and `-r requirements.txt` |

#### `pytest-randomly` is a dependency, not a convenience

It shuffles test order on every run, and **the suite depends on that for a guarantee it would otherwise lack.** The extension cases in `tests/cmn/mqc_uni_extensibility.py` register a layer, an outcome and a verdict rule, then remove each one again. A cleanup that failed would change the distribution denominator for every case running afterwards, and the failure would land on whichever case happened to run last.

Random ordering is what makes that detectable. Without it the suite runs in declaration order every time, and an ordering dependency introduced later would pass consistently in CI while failing on any machine that happened to have the plugin installed.

The audit found it installed locally and undeclared, which is the worse arrangement of the two: **local runs held a guarantee CI did not**, so CI was the weaker check while appearing to be the stronger one.

### 5.1 Two repositories, and what the split cost to find

**Split 2026-09-23**, closing A17. The harness lives here; the evaluation cases live in `AP-Model-QC`, which consumes this repository as a dependency rather than containing it.

A17 recorded one repository as a deliberate demonstration trade and named the trigger for reversing it: the moment the project is used rather than read. The case inventory reaching a size where a version matrix matters is that moment, and the split was done before the first commit, which is the cheapest it will ever be.

| Capability | One repository | Now |
|---|---|---|
| A case set runs against a chosen harness version | No | Yes, the pairing is an input |
| Harness and cases version independently | No, one commit is both | Yes |
| Roll back cases without reverting harness fixes | No | Yes, or either, or both |
| A harness change re-verified against every case set | Not expressible | Yes, fan out across consumers |

#### What sits on each side

| This repository, `AP-Harness-QC` | `AP-Model-QC` |
|---|---|
| The four modules and their precondition suites | The graded cases, `EVAL`, `TOOL` and `SEC` |
| Every module design, `ci_pipeline.md`, `extensibility_standard.md` | `model_evaluation_test_plan.md`, `rtm_model.csv` |
| `harness_test_plan.md`, `rtm_harness.csv` | `data/tasks/`, `data/rules/` |
| `tools/`, generators and maintenance scripts | `tests/fixtures/replay/`, recorded responses |
| `test_taxonomy.md`, the single registry | Recorded fixtures and the code excerpts |
| `gate-on-change.yml`, `probe-model-version-nightly.yml` | Its own gate, pinning a harness version |

**`test_taxonomy.md` stays here and is not duplicated.** It is the single registry of identifiers, priorities and failure codes, and `framework-rules.md` section 4.1 forbids a second one. The case repository references it rather than vendoring a copy, which also keeps the Apache licence on this side from travelling into an MIT repository by accident.

#### The boundary was verified, and the verification had a hole in it

Section 5.1 previously claimed the split boundary had been checked rather than assumed, and for **documents** that was true: every design sat cleanly on one side. What it did not check was **tests**.

Five harness preconditions read case-side data. `MQC_CMN_UNI_10171` through `10173`, `11105` and `11106`, **all five since relocated and no longer defined here**, guarded the code excerpts, and the excerpts are input to graded cases specified in `model_evaluation_test_plan.md`. A harness check reading a file that belongs to another repository is a boundary violation that only appears when the boundary becomes real.

**They move to the case repository**, along with `MQC_REQ_HAR_CMN_0027`, the requirement they satisfy. They live there now as `MQC_CAS_UNI_10401` through `10405`. The reasoning is the one the guards themselves state: a stale excerpt is a defect in the thing that owns it, and the excerpts are owned by the cases.

**This is the split paying for itself before it was finished.** A cross-boundary dependency invisible in one tree became a failing test the moment the tree divided, which is the whole argument for dividing it.

---

**Everything designed here ships in v1.** The design documents are the v1 scope, exactly: nothing specified is deferred, and nothing ships that was not designed first. A v2 feature re-enters Phase 0 and is designed before it is built, rather than arriving as an amendment to something already running.

This closes a failure this project has already hit more than once, where a document described behaviour that did not exist and a reader had no way to tell. Under this rule the question cannot arise: if it is specified here, it is in v1, and if it is not here, it is not built.

---

## 6. Recurring Principles

These appear independently in several documents. Named here so the repetition reads as a pattern rather than an accident.

**Declare, do not silently allow.** Unsupported engine pairs, adversarial fixtures, quarantined cases, dropped columns, and unregistered constraint kinds are permitted only by explicit declaration carrying a reason.

**Record anything that can vary and change a result.** Execution mode, resolved model version, rule-set content hash, CLI flags, and the effective threshold values are all emitted with the result. A run judged against loosened criteria is then visible in history as a change in the recorded standard, not as an unexplained improvement.

**Every declared thing must be verified, in both directions.** A constraint sent to a model must have a check (R3); a check must trace to a constraint (R2); a requirement must have a test (T2); a test must trace to a requirement (T4).

**Prefer including a check to omitting one.** Justifying why a case exists is easier than justifying why one is absent, and an absent case is rarely a decision. It is usually an oversight that nobody notices until the thing it would have caught has already happened. Where a check is cheap and deterministic, it is written.

**Documentation is a standard and a compass.** Where implementation finds a better structure, the change is discussed and documented before it is built, not recorded afterwards. A reader therefore never sees documentation that has fallen behind, and stale documentation is worse than none because it reads as verified. `CHANGELOG.md` records the evolution once versioning begins.

**Harness counts and model counts are never summed.** They measure different subjects, and a combined figure implies one population where there are two. Without a working harness there is no point running model tests at all, which is why the precondition layers gate rather than contribute.

**Price a test by how reliably it can be measured.** A check depending on a parser, a tokenizer or anything that can disagree with a reasonable human reading cannot carry a blocking priority, however important the behaviour. Blocking on an artefact of tooling rather than on the model's output inverts what the gate is for.

**Fail safe under uncertainty.** An empty file diff selects a full run, not none. A zero denominator returns "unanswerable", never "fine". Defaults are `replay` and `reject`.

**Verify enforcement, do not assume it.** Every lint and collection rule in this repository was confirmed with a deliberately non-compliant probe. Two defects were found that way: a `test_` prefixed callable that passed the lint gate while never being collected, and a class-level marker routing a test into the wrong gate.

---

## 7. Current State

**Measured 2026-09-28, not recalled.** Every number below was counted from a
collection run rather than remembered, which is the correction this table
needed: it previously read "Implementation code: None" while 584 harness cases
passed against it, and **understating what exists misleads a reader exactly as
much as overstating it**.

| | |
|---|---|
| Phase 0 | Closed. No open items |
| Phase 1 | Complete for every tier |
| Phase 2 | **Complete.** Four module designs, two test plans and two matrices |
| Phase 3 | **Underway.** The design is implemented, the corpus is authored, and the security family is recorded in full. The `EVAL` and `TOOL` families are not recorded, which costs judge quota as well as candidate quota |
| Implementation code | 46 modules, roughly 15,300 lines across `ingestion/`, `execution/`, `evaluation/` and `cmn/` |
| Harness cases | **584**: 564 precondition (`UNI`) and 20 system (`SYS`), across `ING`, `EXE`, `EVL` and `CMN` |
| Case-repository preconditions | **47** (`CAS_UNI`), guarding the corpus, the excerpts and the pin |
| Model evaluation cases | **66, inventory and suite agreeing**: 37 `EVAL`, 8 `TOOL`, 21 `SEC` |
| Requirements traced | 173 harness, 67 model, both directions checked by `MQC_CMN_UNI_11122` |
| Recorded fixtures | 8 security responses, **all at observation 0**. Under A4.1 each case needs three, so the corpus is one third recorded and every graded case reports `QC_HARNESS_FIXTURE_MISSING` |

**What is not done.** Recording. A4.1 raised the corpus from 54 responses to
162, of which 8 exist, and those 8 are the first of three samples each rather
than complete cases. **They are incomplete, not wrong**: a fixture recorded
before the decision is still a valid observation zero. The corpus is authored and the pipeline is verified against it in
replay; **what remains is spending the quota to record what the models
actually say.**

**The 66 and the suite now agree**, the twelve unwritten security cases having
been written on 2026-09-26.

**The reverse check is still absent and still matters.** `MQC_CMN_UNI_10183`
checks that every collected case has an inventory row; nothing checks that every
inventory row has a case, which is why twelve designed cases, nine of them P0,
reported nothing at all for as long as they did. Section 7.4 keeps it on the
record: closing one instance is not the same as closing the class.

**Scope is organised by family.** A family is a task type with its own input shape and its own source of ground truth, registered in `test_taxonomy.md` §11 and carried on every graded result. Three are registered for v1, below. The set is expected to grow, and §11.2 states the four steps that admit a new one.

**A family earns admission by supplying ground truth for a property that would otherwise be judged.** That is the common thread between the three, not subject matter: provided source material makes fabrication a set operation, parsers make shape constraints countable, and a defective excerpt makes falsehood an exact comparison. A family gradable only by rubric adds cases without adding confidence.


### 7.1 v1 Test Plan Scope: Requirement Matching Family

Recorded as scope, and since discharged: `model_evaluation_test_plan.md` section 9.8 specifies this family and cases `30019` through `30028` implement it.

**The task.** A user supplies resume material and a job posting's requirements, and asks for the summaries rewritten to match the posting as closely as possible without claiming anything the candidate does not have.

**Why it earns a place in v1.** It carries roughly a dozen independently checkable constraints, most of them deterministic, so it exercises the dual-evaluation pass rather than leaning on a judge. More unusually it supplies **ground truth for fabrication**: because the source material is provided, every claim in the output either traces back to it or does not, making invention a set operation rather than a judged opinion. Most anti-hallucination evaluation cannot do better than asking one model whether another invented something.

#### 7.1.1 Input

Three documents, carried as `context_documents` on the task. No schema change is required.

| Document | Shape |
|---|---|
| `summary` | Prose achievement bullets, each a category label followed by evidence, usually carrying a measurable |
| `technical_summary` | Categorised technology inventory, comma separated |
| `education` | Degree, field, institution, and a date that **may be absent** for older degrees |
| `employment_history` | Optional. A secondary source for years of experience when the summary does not state it |

#### 7.1.2 Gates

Four gates, each separately nameable. A model reporting only that the match is insufficient has followed the instruction partly, since the four prompt different user decisions.

| Gate | Threshold | Nature |
|---|---|---|
| Mandatory match | 78% | Below this the nice-to-have set is **not evaluated at all** |
| Key skills | 80% | Hard sub-gate, independent of the overall mandatory figure |
| Degree level | Met, or equivalence judged | Hard gate where the posting specifies one |
| Combined | 85% | Only consulted when mandatory sits between 78 and 84% |

| Mandatory | Condition | Outcome |
|---|---|---|
| Below 78% | Nice-to-have not evaluated | Warn, naming the mandatory cutoff |
| 78 to 84% | Combined at least 85% | Proceed |
| 78 to 84% | Combined below 85% | Warn, naming the combined shortfall |
| 85% or above | Nice-to-have irrelevant | Proceed |

Row one carries a behavioural check as well as an arithmetic one: a model that reports a nice-to-have percentage after failing the mandatory cutoff has done work it was told to skip, and that is visible in the output.

#### 7.1.3 The combined figure is a pooled count

Combined equals mandatory matched plus nice-to-have matched, divided by all requirements.

Mandatory dominates automatically because postings list more mandatory items, so no weight parameter has to be invented. Checked against two real postings at 78% mandatory with every nice-to-have met, the pooled figure lands at 84.9% and 84.3% respectively, both just failing. The effective floor therefore falls at 78 to 79% mandatory on its own, which is where it was set.

An explicit weighted average would have broken here. At a 70/30 split favouring mandatory, a 78% mandatory match cannot reach 85% combined even with every nice-to-have met, so the bottom of the band would be unreachable. Any mandatory weight above roughly 0.68 has that effect.

#### 7.1.4 How requirements match

The split is by requirement **phrasing**, not by requirement type. Named technologies are not uniformly deterministic.

| Connector | Example | String matching sufficient |
|---|---|---|
| Closed AND list | "Python, Go, Javascript" | Yes |
| Closed OR list | "Python, Go, or Rust" | Yes |
| Open enumeration | "PostgreSQL, Redis or similar databases" | Partly. See 7.1.4.1 |
| Exemplar | "a framework such as Playwright" | **No**, the named items are illustrations |
| Inferred skill | "strong debugging skills" | **No**, judged from achievement evidence |

Correct interpretation of the first two is mandatory and is **observably testable**: a fixture can be built where reading a disjunction as a conjunction drops mandatory match below the floor and flips the gate outcome, so the interpretation is revealed by behaviour rather than needing reasoning to be inspected.

##### 7.1.4.1 Open enumeration is a three-slot disjunction

"Docker, Kubernetes or similar" is **three slots joined by OR**, the third fillable by a category equivalent. Any one slot satisfies the line completely. The connector in the requirement text decides the arithmetic entirely.

| Requirement | Candidate holds Docker only | Why |
|---|---|---|
| "Docker, Kubernetes or similar" | **100%** | Disjunction, one slot filled |
| "Docker, Kubernetes" | 50% | Conjunction, one of two |
| "Docker, Kubernetes, Podman" | 33.33% | Conjunction, one of three |

**Deterministic first, judged only as fallback.** A candidate holding one of the named items matches by string presence with no judgement involved. Only when no named item matches does the third slot engage, and only then is category similarity judged.

This is what admits open enumerations to the key-skill sub-gate without softening it: the common case stays hard, and the judged path is the exception.

**How each item matched is recorded**, either named or similarity-judged. A report reading "key skills 80%, one item matched by similarity judgement" tells a reviewer how much of a hard gate was in fact soft. Without that record, a gate that quietly became judged looks identical to one that did not.

It also forms a test category: does the model correctly judge a category equivalent as similar, and correctly refuse something unrelated.

##### 7.1.4.2 The per-requirement match record

**Mandatory.** Every requirement carries a record of how it was evaluated. Its purpose is diagnostic, so a failing case is where it is consulted.

| Field | Content |
|---|---|
| `requirement_id` | Identity |
| `connector` | Closed AND, closed OR, open enumeration, exemplar, or inferred |
| `match_method` | Named string match, alias match, similarity judgement, inference, or unmatched |
| `credit` | Fractional value awarded for this line |
| `evidence_source` | Which supplied document carried the evidence |
| `rationale` | Present only for similarity judgements and inferences |

**Why failure is where it earns its place.** A mandatory figure of 76% warns, but the figure alone cannot say whether the candidate lacks the requirements or the matcher failed to find what they have. Those are entirely different problems with entirely different fixes:

| Cause | Meaning | Family |
|---|---|---|
| Candidate genuinely lacks the requirement | A real gap, correctly reported | Not a defect |
| Alias missing, so `K8s` never matched `Kubernetes` | **Our matcher is wrong** | `QC_HARNESS_*` |
| Parsing dropped a technical summary line | **Our loader is wrong** | `QC_DATA_*` |
| Similarity judgement wrongly rejected a category equivalent | A model finding about the judge | `QC_LLM_*` |

Without the record these are indistinguishable, and a false negative caused by a missing alias reads exactly like a candidate shortfall. The suite would report a model finding where the defect is ours, which inverts the distinction the whole taxonomy rests on.

The record is **attached to the artifact**, not only written to a log, so it survives into the durable history and reaches a reviewer working from the artifact alone. On a failing case it is the diagnostic payload; on a passing one it shows how much of a hard gate was carried by judgement rather than by string presence.

**Granularity.** A list-bearing line is one requirement with fractional credit. Three named languages score 0, 33.33, 66.66 or 100 percent of that single line. Two named container technologies with one held score 50%.

**Inferred skills** are judged from evidence rather than matched as phrases. A bullet describing custom log parsers that cut troubleshooting time by 45% demonstrates debugging without containing the word.

**An alias registry is required.** A posting writing `Javascript` against a resume writing `JavaScript`, or `K8s` against `Kubernetes`, produces a false negative, and a false negative on a key skill can flip a gate. Normalization is a registry in the sense of `extensibility_standard.md` section 6, extended by entry rather than by code.

#### 7.1.5 Degree

| Element | Treatment |
|---|---|
| Level | Hard gate, ordered Associate, Bachelor, Master, Doctorate. "BS or higher" is satisfied by BS, MS or PhD |
| Field | **Not evaluated** |
| Equivalence clause | Optional judgement gate, reached only when the level gate fails |

A missing date on the education line is a required negative fixture. Degrees older than roughly ten years commonly omit it, so a parser demanding one fails on exactly the candidates with the most experience.

#### 7.1.6 Years of experience

Not a skill, and therefore outside the key-skill sub-gate. It is a **modifier rather than a countable requirement**: the years line is **removed from the requirement denominator** and replaced by a penalty, so a shortfall is not punished twice by failing a line and taking a penalty for the same gap.

**Three percentage points against the mandatory figure for each year below the stated minimum, capped at 30 points.**

`adjusted mandatory = max(0, mandatory - min(3 * years_short, 30))`

| Requirement | Candidate | Penalty | Note |
|---|---|---|---|
| 10 years | 15 years | None | |
| 10 years | 8 years | 6 points | |
| 10 years | 7 years | 9 points | |
| 10 years | Under 1 year | 30 points | Cap reached at ten years short |
| 10 years | Not extractable | 30 points | See below |

The floor at zero still matters despite the cap, since a mandatory figure below 30 would otherwise go negative.

**When years cannot be extracted** from either the summary or the employment history, the maximum 30 point penalty applies. This is deterministic and needs no clarification round.

**It also produces a useful invariant.** The highest possible mandatory figure is 100%, so an unextractable years value yields at most 70% adjusted, which is below the 78% floor. **An unextractable years figure therefore always warns.** That is a single assertion covering the whole case, and it gives a candidate a concrete reason to state experience explicitly.

**Disclosure rule.** What the output states depends on **who produced the figure**.

| Source of the figure | Output states | Rationale |
|---|---|---|
| Stated explicitly in the summary | The stated figure, unchanged. "15+" stays "15+" | The candidate already made a disclosure decision, and the tool does not second-guess it |
| Derived by calculation from employment dates | The requirement minimum, with a plus when the calculated value exceeds it | When the tool is the one computing, it discloses only what is needed |
| Neither stated nor calculable | **Prompt the user**, naming the 30 point penalty and the possible disqualification | The model cannot assert a figure it cannot derive |

The principle underneath both halves: **the tool never reduces what the candidate chose to disclose, and never volunteers more than necessary when it is deriving the figure itself.** The purpose of the second row is avoiding age discrimination while still meeting the stated minimum.

Understating a derived figure does **not** conflict with the no-fabrication rule, since stating "8+ years" while holding fifteen is true. A fabrication check comparing output claims against the source must therefore be **directional for numeric values**: stating less than the source supports is permitted, stating more is not. The obvious implementation flags the correct behaviour as a violation, so this warrants its own fixture.

**Failure modes differ by row:**

| Row | Failure | Code |
|---|---|---|
| Stated | Rewrote "15+" down to "8+", altering a figure the source gave | `QC_LLM_SOURCE_ALTERATION` |
| Calculated | Emitted the full calculated total instead of the requirement floor | `QC_LLM_OVER_DISCLOSURE` |
| Incalculable | Proceeded without prompting | `QC_LLM_AMBIGUITY_UNHANDLED` |

Prompting is graded as a property of a single response. The harness never replies to it, consistent with Tier 2 issuing one request per case.

| Years | Penalty | Output behaviour |
|---|---|---|
| Stated or calculable, meets minimum | None | Per the disclosure rule above |
| Stated or calculable, below minimum | 3 points per year, capped at 30 | Warn |
| Neither stated nor calculable | Full 30 points | **Prompt the user** |

The penalty can flip a gate unaided in ordinary cases too. A candidate at 88% mandatory falling three years short lands at 79%, one point above the floor, which makes it a useful boundary for the permutation matrix.

#### 7.1.7 Other graded constraints

No claim absent from the source material. Wording adjusted where a held skill maps to a requirement. Bullet format with at most six bullets per section, recorded as `QC_LLM_LENGTH_VIOLATION` when breached. Measurable achievements ordered above the rest. No em dashes or pipe characters, which break ATS parsing and therefore carry a functional reason rather than a stylistic one.

#### 7.1.8 Two categories, kept separate

Section headers signal mandatory versus optional through wording that varies completely between postings, and the classification is **semantic rather than lexical**. "Ways To Stand Out From The Crowd" contains none of preferred, optional, nice or bonus, yet is plainly optional. A corpus of fourteen real phrasings exists from five postings.

* **Matching cases** supply the split **pre-labelled** in the fixture, so a failure is unambiguously a matching failure.
* **Header classification** is its own category, fed the fourteen phrasings plus invented ones. An unfamiliar header is also a natural clarification-seeking case.

Conflating them makes a failure impossible to attribute, since misreading a header and matching badly look identical in the output.

#### 7.1.9 Fixture generation by ablation

Permutation levels at 0, 78, 79, 80, 81, 84, 86, 90 and 100 percent mandatory, hitting every gate from both sides.

Variants are **derived by ablation from one high-match original** rather than authored separately. Removing named technologies lowers the deterministic match, removing measurables tests the ordering rule, and thinning achievement evidence weakens the inferable skills. Each ablation moves the figure in a known direction, so the expected result is computed rather than estimated and the harness knows the right answer.

#### 7.1.10 Resolved during scoping

All items raised while scoping this family are now closed: the combined figure is a pooled count; the years penalty caps at 30 points; an unextractable years value takes the full cap and flags; the years line is removed from the requirement denominator; and open-enumeration requirements are admitted to the key-skill sub-gate through deterministic-first matching with a judged fallback that is recorded as such.

A dedicated resume-tailoring project may follow separately. This entry covers only its use as an evaluation case family.

---

### 7.2 v1 Test Plan Scope: Constrained Output Shape

Recorded as scope alongside 7.1. Not yet authored.

**The task.** A model is instructed to hold its output to a quantitative shape, such as no sentence exceeding seven words, a fixed bullet count, or a character ceiling.

**Why it earns a place.** Compliance is a count rather than a judgement, so the whole category is deterministic. It also targets a known weakness: length constraints are among the instructions models most reliably violate, and a violation is unambiguous rather than arguable.

#### 7.2.1 What counts as a sentence

**A sentence carries a subject and a verb.** Punctuation alone does not define one.

`Dr. Smith earned $1.5M in Q3.` is **one** sentence of six words, and passes a seven-word ceiling. `Dr.` is a title, not a sentence. `1.5` is a number. Naive splitting on a period would report three sentences and fail the case on an artefact of the parser.

**Fragments are task-dependent.** A one or two word utterance is usually an emotional beat, legitimate in fiction, a screenplay or dialogue, and wrong in most other output. Fragment tolerance is therefore declared on the constraint rather than fixed globally, so a task can permit what another forbids.

#### 7.2.2 Priority follows measurement reliability

These checks differ sharply in how reliably they can be measured, and priority follows that rather than the importance of the behaviour (see `test_taxonomy.md` section 4.1.2).

| Check | Determinism | Priority |
|---|---|---|
| Sentence begins with a capital | Pure string test | P2 |
| Words per sentence | Requires segmentation | P3 |
| Subject and verb present | Requires linguistic analysis | P4 |

**Capitalization earns the highest of the three precisely because it needs no parser.** It does require **declared exceptions**, since `iPhone`, `eBay` and code identifiers legitimately break the rule, which is the same declare-rather-than-silently-allow pattern used elsewhere.

The two parser-dependent checks cannot reach P0 or P1 at all. Those levels block, and blocking on a segmenter's disagreement with a reasonable reading would fail a run on tooling rather than on the model.

#### 7.2.3 Binary gate, recorded distribution

Any violating sentence fails the case, per the conjunctive assertion model. The record additionally carries the **compliance rate and the worst offender**.

"Nine of ten sentences complied, the worst at fourteen words" and "three of ten complied, the worst at forty" are different findings, and a single failed assertion hides the distinction that tells a reader whether the model nearly complied or ignored the instruction.

Violations are recorded as `QC_LLM_LENGTH_VIOLATION`, distinct from `QC_LLM_FORMAT_VIOLATION` because one concerns quantity and the other prohibited characters. The resume family's bullet ceiling in 7.1.7 uses the same code, which it previously lacked.

#### 7.2.4 Permutation dimensions

| Dimension | Values |
|---|---|
| Limit | 5, 7, 10, 15 words per sentence |
| Content resistance | A simple fact compresses; a causal explanation resists |
| Constraint interaction | Each constraint alone, then combined |

**Constraint interaction is the dimension worth building for.** Testing a character prohibition and a length ceiling separately, then together, measures whether constraints **compose** or whether satisfying one degrades compliance with the other. Models commonly trade one instruction against another under pressure, and a suite testing each constraint in isolation would never observe it.

**A composite case depends on its components.** Each multi-constraint case declares `depends_on` naming the single-constraint cases it combines. If a constraint fails in isolation, the composite is skipped rather than run: testing it in combination measures nothing new, and a failure would be attributed to interaction when the cause is the component. See `test_taxonomy.md` section 4.1.3.

---

### 7.3 v1 Test Plan Scope: Code Comprehension Family

**A job posting does not come with code.** This is a separate task family, not a variant of the requirement-matching one, and it is registered here because the cases exist in `model_evaluation_test_plan.md` section 4.4 while the v1 scope named only the two families above.

#### 7.3.1 Input

| Item | Shape |
|---|---|
| Excerpt | A Python function under twenty lines carrying a known defect, supplied as a `context_document` |
| Question | Asks what the excerpt does, or what is wrong with it |

No schema change is required, for the same reason the resume documents needed none: an excerpt is context carried on the task.

#### 7.3.2 Why it earns a place in v1

**It converts judged properties into asserted ones.** The other two families rely on a rubric wherever a claim cannot be checked mechanically, and `MQC_REQ_MDL_GND_0004`, "states no verifiable falsehood", is the hardest case: establishing that a claim is false needs knowledge the harness does not hold.

A defective excerpt supplies that knowledge.

| Defect class | Ground truth from | Settles |
|---|---|---|
| Syntactic | The parser | Where the error is and what kind it is |
| Logical | Executing the function against known inputs | What the code actually returns |

This is the same office the resume family performs for fabrication, where provided source material makes invention a set operation. Here a parser and an interpreter make falsehood an exact comparison. **Both families were chosen because they supply ground truth for a property that is otherwise judged**, which is the criterion for admitting a family to v1 rather than a preference for a subject area.

#### 7.3.3 The three fixtures

| Fixture | Defect | Verified by |
|---|---|---|
| `top_scorers_syntactic.py` | An unclosed parenthesis | The parser naming line 2 |
| `top_scorers_logical.py` | A discarded `sorted` result, so a line does nothing | The wrong rows returned, exit code zero |
| `settle_order.py` | An unvalidated coupon against a wrongly computed discount | A settlement at or below zero |

**The first two are the same function**, so defect class is the only variable between them rather than being confounded with subject matter or length.

The logical twin induces a failure the syntactic one cannot: **code that looks like it works invites a description of what it evidently intends rather than what it does**, so a summary drawn from the function name is a fabrication with mechanically checkable ground truth. That is `MQC_REQ_MDL_GND_0001`.

#### 7.3.4 What it exercises, and what it does not

It supplies formulations for three grounding requirements, `MQC_REQ_MDL_GND_0001`, `GND_002` and `GND_004`. **It introduces no requirement of its own**, which is the point: a grounding requirement is domain-independent, and this family exists to test that the behaviour holds when the same demand arrives in a different domain.

It does not exercise the requirement-matching gates in section 7.1 or the shape constraints in section 7.2. Those measure different things and carry their own cases.

**This family is not about evaluating a model's ability to write code.** It uses code as material with checkable ground truth. A family measuring code generation would need its own correctness criteria, an execution sandbox and a security posture for running model output, none of which is in v1.

### 7.4 Known gaps, recorded rather than left silent

Added 2026-09-25 from a documentation review, which is how they were found.

`testing-standards.md` requires that a case deliberately not written is
**recorded as a known gap with its reason**, so the omission is a decision on
the record rather than a silence. These were silent.

| Gap | Size | Why it was invisible |
|---|---|---|
| ~~Security cases `50010` to `50021` designed and unwritten~~ | **Closed 2026-09-26** | Twelve corpus pairs and twelve cases written. Writing them found that two attack families had no vector at all (`tier1_ingestion.md` section 7.3) |
| No recorded response for any `EVAL` or `TOOL` case | 48 cases | Expected, and now the only recording gap: the `SEC` family was completed 2026-09-28 at a measured cost of six cents. These two spend judge quota as well as candidate quota, which is the difference |
| ~~Repeat observations are never dispatched~~ | **Closed 2026-09-25** | A4.1 decided three; every graded case now observes three times and the consistency check reads the result |

**Only the middle row is still open**, and it is open by plan rather than by
oversight: recording an `EVAL` or `TOOL` response costs quota, and the evaluator
family spends it on the judge as well as the candidate.

**What the security recording established, which the estimate could not.**
Thinking runs at **six to seven times** the visible output on this model and
is billed as output, so every cost figure produced before those counts were
captured understated the bill by roughly five times.
`cmn_verdict_and_cli.md` section 12 carries the measurement.

**What closing the first row taught, which outlived the gap.** Writing the twelve
cases found that two whole attack families matched no vector at all and had
looked screened on an incidental match (`tier1_ingestion.md` section 7.3). The
check that would have caught it — a case declaring the vector it is *about* —
is recorded in `OPEN_QUESTIONS.md` section 2.4.1 and not built.

**The reverse inventory check is still not built, deliberately.** An inventory
row without an implementation is the *normal* state while a family is being
authored, so a hard failure would block the authoring order this project
requires. The right shape is a report rather than a gate, which is why it sits in
`OPEN_QUESTIONS.md` section 2.1 as a question for the project owner.

**What the third row's closure changed.** A4.1 settled three observations per
case, so a fixture is no longer a single sample presented as a characterisation.
Reading them is the consistency check and the `RUN_UNSOUND` condition above it
(`cmn_verdict_and_cli.md` sections 4.9.1 and 4.9.2), neither of which is a
numbered verdict rule.

---

**Known specification gaps**, recorded rather than left implicit: Tier 2 and Tier 3 designs, the test plan, and both traceability matrices.
