<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# CI Pipeline Design

> **Parent:** `DESIGN.md` section 3.2.
> **Status:** Implemented. A living specification, amended in the same change as the workflows it specifies.
> **Subject:** the GitHub Actions workflows: their triggers, jobs, secrets, artifacts and failure semantics.
> **Not in scope:** the CLI contract, specified in `cmn_verdict_and_cli.md` section 7; the gate sequence, normative in `framework-rules.md` section 1; selection rules, normative in `testing-standards.md` section 3.

---

## 1. What This Document Adds

The gates, the selection rules and the CLI already exist as specifications. What did not exist is the statement of **which workflow files hold them, what starts each one, and which of them can reach a credential.**

That last point is the reason this is a design document rather than a configuration detail. A1 decided that pull requests run without credentials, and that decision is only real if the workflow structure makes it true. A single workflow with conditional steps would put a secret reference in a file that pull requests execute, and the guarantee would rest on a conditional being correct forever.

---

## 2. Eight Workflows

Extended 2026-09-23. Four covered the gate, the probe, the live run and
diagnosis. Three more cover regression and failure triage, which the split and
the change-scoping rule between them made necessary. The eighth, added
2026-10-15, runs Gate 8, the mutation audit (section 5A).

| File | Starts on | Credentials | Emits durable record |
|---|---|---|---|
| `gate-on-change.yml` | Push, pull request, manual dispatch | None | Yes |
| `regress-harness-on-branch.yml` | Manual dispatch | None | Yes |
| `regress-consumers-on-merge.yml` | A green gate on `main` or `stabilization`, or manual dispatch | None | Yes |
| `probe-model-version-nightly.yml` | Manual dispatch. **Schedule withdrawn**, see 2.0.1 | Read-only model metadata | No |
| `evaluate-live-weekly.yml` | Manual dispatch. **Schedule withdrawn**, see 2.0.1 | Provider API keys | Yes |
| `diagnose-on-demand.yml` | Manual dispatch only | Optional | **No** |
| `audit-mutation-on-change.yml` | A push to `main` changing the harness or its suite, or manual dispatch | None | No |
| `debug-failures-on-demand.yml` | Manual dispatch only | Optional | **No** |

### 2.0 Why the gate is not already all of this

**The gate is scoped; a regression is not.** Section 3 makes a pull request run
only what the change can affect, which is the right trade for a gate that runs on
every push and the wrong one for establishing that a branch is wholly sound.
Those are different questions and a single workflow answering both would answer
neither: either every push pays for the full suite, or no run ever establishes
the full result.

**A regression run and a diagnostic run differ in what they cost, not in what
they cover.** `regress-harness-on-branch.yml` is gated and yields a verdict,
because it runs one ref as it stands with no filter. `debug-failures-on-demand.yml`
selects named tests and therefore yields none, for the same reason every manual
selection does.

| Question being asked | Workflow |
|---|---|
| Can this change merge? | `gate-on-change.yml` |
| Is this branch wholly sound, before I offer it? | `regress-harness-on-branch.yml` |
| Did `main` break anyone who pins us? | `regress-consumers-on-merge.yml` |
| Why did these particular tests fail? | `debug-failures-on-demand.yml` |
| Was it our harness or the model? | `diagnose-on-demand.yml` |
| Would the suite notice if this code were wrong? | `audit-mutation-on-change.yml` |

**Four files became seven rather than four files gaining flags**, on the naming
rule in section 2.1: a reader's first question about a run is why it happened,
and a filename is where that answer costs nothing.

### 2.0.1 No workflow is scheduled until `main` is stable

Decided 2026-09-26 by the project owner.

Three workflows carried a cron: the consumer regression weekly, the model-version
probe nightly, and the live evaluation weekly. **All three are now dispatch-only,
and the crons return when weekly regression is set up against a stable `main`.**

| Reason | |
|---|---|
| A cron against a moving branch | Produces a red nobody acts on, weekly, which trains readers to ignore the one signal that a regression is real |
| A cron that spends quota | Competed with corpus recording for the free tier's 20 requests per day per model. **That reason expired on 2026-09-28**, when both engines were funded (`harness_open_questions.md` section 2A, settled 2026-09-28); the two reasons above did not, and they are why no cron has returned |
| A cron on a broken workflow | `evaluate-live-weekly.yml` in **this** repository ran graded markers that collect nothing here, so it failed every Sunday for a structural reason (section 3.1.0) |

**On-change triggers are unaffected and are the point.** `gate-on-change.yml`
still runs on push and pull request, and `regress-consumers-on-merge.yml` still
runs on a green gate on the default branch, which is the trigger that makes it a
merge guard rather than a report.

**Two filenames now name a cadence they do not have.** `probe-model-version-nightly.yml`
and `evaluate-live-weekly.yml` are dispatch-only while their schedules are
withdrawn. They keep their names rather than being renamed twice: section 2.2
makes a filename a cross-workflow reference, and renaming now and back is churn
that `actionlint` would have to catch in between. The withdrawal is stated in each
file at the trigger it replaced.

### 2.0.2 When the live run fires, once the jobs are stable

Decided 2026-10-01 by the project owner, settling what section 2.0.1 withdrew.

**The live run measures what the replay run measures.** That is the answer to
what it is for: the same ladder against the same corpus, dispatched rather than
replayed. What it additionally buys is the recordings themselves, because a
newer engine or model version has no fixtures until something live produces
them, and a replay suite cannot characterise a version it has never met.

**Smoke tests matter**, and they are the part a replay run cannot establish at
all: whether the harness can still reach a provider.

**Nothing is scheduled until every job is stable.** That is unchanged from
2.0.1 and is the precondition for the rest of this section.

**The trigger is a conjunction over a disjunction:**

```
fire when   (7 or more days since the last live run)
      and   (the weekly slot has come  or  the resolved model version changed)
```

| Reading | Consequence |
|---|---|
| The floor is **and** | Never more than once a week, whichever condition fired it |
| The conditions are **or** | A new model version does not wait for Sunday |
| Version compared against | The last version a live run recorded, not the last probe |

**The probe is what makes the second condition cheap.**
`probe-model-version-nightly.yml` already resolves the served version nightly for
one request, so a version change is known without a graded run. Comparing against
the last **live run's** recorded version rather than the last probe's is what
keeps a single upgrade from firing twice.

**Why a floor and not a cap on cost.** A provider can serve a new version twice
in a week, and the cost of a live ladder is the corpus times the observation
count, which section 4.9.2.1 has just raised. The floor bounds spend by
construction; a budget ceiling bounds it by refusing mid-run, which is worse
when the run exists to produce fixtures.


### 2.1 Workflow file naming

**`<verb>[-<subject>]-<cadence>.yml`.** The verb is what the workflow does, the subject narrows it when the verb alone is ambiguous, and the cadence is the trigger that fires without anyone asking.

| Part | Values in use | Rule |
|---|---|---|
| Verb | `gate`, `regress`, `probe`, `evaluate`, `diagnose`, `debug`, `audit` | What this workflow is for. One word |
| Subject | `model-version`, `live`, `harness`, `consumers`, `failures`, `mutation` | Present only where the verb does not identify the workflow by itself |
| Cadence | `on-change`, `nightly`, `weekly`, `on-demand` | The unconditional trigger, not the secondary ones |

**A name like `ci.yml` describes every workflow in this directory and therefore none of them.** All four are continuous integration. The question a reader actually has is what a file runs and when it fires, and a filename is where that answer costs nothing to provide.

The naming matters more as workflows are added than it does now. A directory of four files can be learned by opening them; a directory of ten cannot, and the moment to fix a naming scheme is before the files it has to distinguish exist.

Where a workflow has more than one trigger, **the cadence names the unconditional one.** `evaluate-live-weekly.yml` also fires on dispatch from the probe, and the weekly schedule was what ran regardless of whether anything else worked. Naming a file after a conditional trigger would make it read as optional.

**While a schedule is withdrawn the name records the intended cadence, not the current one** (section 2.0.1). That is the lesser of two wrongs: a name is a cross-workflow reference, and renaming a workflow twice costs a dangling reference in between.

| Future workflow | Name it |
|---|---|
| A nightly free-tier quota check | `probe-quota-nightly.yml` |
| A weekly coverage report | `report-coverage-weekly.yml` |
| A live run split onto its own dispatch trigger | `evaluate-live-on-dispatch.yml` |

**Cross-workflow dispatch references a filename**, so the probe names the live workflow explicitly. Renaming either one is a paired change, and `actionlint` in the `lint` job catches a dangling reference before it reaches a scheduled run that nobody is watching.

**The split follows the credential boundary, not convenience.** `gate-on-change.yml` contains no reference to any secret, so there is no conditional to get wrong and no path by which a pull request from a fork reaches one. This is the structural half of A1; the other half is that `evaluate-live-weekly.yml` runs only from the default branch.

Four files also mean four independent answers to "why did this run", which is the question a reader of the durable record asks first.

---

## 3. `gate-on-change.yml`: Everything Deterministic, No Quota

### 3.1 Jobs

| Job | Gate | Runs | Blocks |
|---|---|---|---|
| `lint` | 1 | `pylint` against `.pylintrc`, plus `actionlint` | Everything |
| `unit` | 2 | `pytest -m unit` | `system` |
| `system` | 3 | `pytest -m system --mode replay` | Nothing |

Each declares `needs` on its predecessor, so a precondition failure leaves the next job **skipped rather than failed**. That distinction is the one recorded when the A2 conflict was resolved: a harness failure must not present as a model finding.

**Two test-executing jobs in this repository**, `unit` and `system`. `lint` executes none.

### 3.1.0 Gates 4 to 7 are the consumer's, corrected 2026-09-26

**This table specified a `graded` job and a `verdict` job here, and neither could run.** They were written when the pipeline was specified as one shape for one repository, and the split (A17) made them unrunnable without anybody noticing, because Gate 1 failed on the first commit that ever executed this workflow and all four downstream steps were skipped.

| What it did | Why it could not work |
|---|---|
| `pytest -m evaluator`, `-m tool`, `-m sec` | **This repository holds no graded case.** `CLAUDE.md` states the harness owns no case data, so each marker matched zero tests and pytest exited 5 |
| `cmn.verdict_tool collected/results.json` | **Nothing writes that file.** Section 5 of `cmn_verdict_and_cli.md` emits observations as Allure and JUnit for a downstream collector to assemble |

**Where each one lives.** Gates 4 to 6 and the verdict run in `AP-Model-QC`'s own `gate-on-change.yml`, against its cases, which is where a model is actually measured. A harness change is proved against real cases by `regress-consumers-on-merge.yml`, which checks out a consumer against the candidate and runs the consumer's deterministic gates.

**What this repository owes instead is proof that the instrument works**, and that is `MQC_CMN_SYS_122000` to `122002` inside Gate 3: the whole chain on a synthetic corpus, from the ingestion join through replay dispatch and the dual pass to a computed verdict, asserting it reaches **both** a green and a red. A harness that cannot report red about a failing model cannot be trusted when it reports green.

**`regress-harness-on-branch.yml` carried the same four steps** and they are removed for the same reason. `evaluate-live-weekly.yml` still carries them and and what a harness-only live run should measure was settled on 2026-10-01: the same ladder, fired weekly or on a version change, specified in section 2.0.2 below.

**Section 3.1.1 below describes the three-step graded job as the consumer runs it**, and its requirement of three separate JUnit files is a requirement on that pipeline.

#### 3.1.1 The graded job runs three steps, not one command

| Step | Gate | Command | Artifact |
|---|---|---|---|
| Evaluator | 4 | `pytest -m evaluator --engine <e> --mode replay` | `junit_mqc_eval.xml` |
| Tool | 5 | `pytest -m tool --engine <e> --mode replay` | `junit_mqc_tool.xml` |
| Security | 6 | `pytest -m sec --engine <e> --mode replay` | `junit_mqc_sec.xml` |

**Combining them into one invocation would emit one JUnit file where `framework-rules.md` section 1 requires three**, and would erase the separation that makes `SEC` its own suite. That separation is not cosmetic: `SEC` is exempt from the distribution ceilings precisely so security coverage never competes with functional coverage for a budget, and a single merged result set makes the exemption unverifiable from the artifacts.

#### 3.1.2 Every job runs on both operating systems

`ubuntu-26.04` and `windows-latest`, as **separate jobs with `fail-fast: false`**, for the reason B9 gives for engines: the default would let one platform's failure cancel the other, and a collapsed job lets a pass on one platform mask a failure on the other. **The Ubuntu image is pinned and the Windows label is not**, for the reasons in `DESIGN.md` section 5.0.2.

| Job | Platforms |
|---|---|
| `lint`, `unit`, `system` | Both |
| `evaluate-live-weekly.yml` | Ubuntu only |

**Separate means separate in every sense that matters**, and each of these is a requirement rather than a consequence:

| Property | Consequence |
|---|---|
| Its own status check, named per platform | Branch protection can require each independently |
| Its own pass, fail or skip | Neither result is inferred from the other |
| Its own logs and artifacts | A Windows failure is diagnosed from Windows output |
| Independently re-runnable | A flake on one platform does not force re-running both |
| `os` on every result row | The record attributes a finding to a platform without inference |

##### 3.1.2.1 One job definition, two jobs

The platforms come from a matrix over `os`, so there is one definition producing two jobs, rather than two definitions.

**This is the A12 form**: adding a platform is a list entry, not a copied block. Two hand-maintained definitions would drift, and the drift would be invisible until the platforms disagreed for a reason that had nothing to do with the code under test.

**The single definition is also a standing check on the portability claim.** Every step must be expressible identically on both platforms, which is exactly what `code-style.md` section 8 requires of documented commands. If a step ever needs a per-platform variant, that is a finding about the harness rather than a reason to split the definition: it means something is not portable, and the honest response is to fix it or to narrow the supported-platform claim in `DESIGN.md` section 5.0.

A conditional inside a step is the warning sign. One is a compromise worth recording; several mean the two platforms are running different harnesses, at which point the matrix is asserting a portability that no longer holds.

**Platform coverage tests the harness, not the model.** A second platform on the live suite doubles quota consumption and learns nothing new about the model, while the replay legs already establish that our code behaves identically on both. This is the same split as the engine legs, where replay is free and live is not.

`os` joins the required result metadata for the same reason `engine` and `mode` are there: a result that cannot say where it ran cannot be compared with one that can, and it becomes a collector parameter column at no cost.

**Alternating platforms between runs is precluded**, per A18 and `harness_extensibility_standard.md` section 7. A gated run executes every supported platform; a scheme that runs one platform on one commit and the other on the next is forbidden rather than merely unchosen, because it cannot separate a platform difference from the change between the two runs.

This binds `gate-on-change.yml` and `evaluate-live-weekly.yml`. It does not bind `diagnose-on-demand.yml`, which may name a single platform and yields no verdict either way.

#### 3.1.3 Replay covers every engine, because it is free

The `graded` job runs as a matrix over all three engines. Replay consumes no quota and no wall-clock beyond CPU, so restricting it to one engine would discard coverage for nothing.

This also removes a trap. `--engine` defaults to `gemini` and emits a warning into the artifact when defaulted, per A7.4. A `gate-on-change.yml` that named no engine would produce that warning on every run, which trains readers to ignore the one signal that says a record is not what it appears to be.

Replay legs run fully parallel here. The serialization in section 5.3 exists to protect a shared provider quota, and replay legs contend for nothing.

### 3.2 Checkout depth

`fetch-depth: 0` on every job that computes selection. The default depth of 1 makes `git diff origin/<default>...HEAD` fail or return nothing, and an empty result is indistinguishable from "nothing changed", which would select no tests at all.

Selection falls back to a full run whenever the diff is empty or errors, per `testing-standards.md` section 3.7. **Selection logic defaults to running more, never less.**

### 3.3 Documentation-only changes, and the branch protection trap

`paths-ignore` is **not** used. A workflow skipped that way never reports its status check, and a required check that never reports leaves a documentation-only pull request permanently unmergeable, because branch protection waits for a result that will never arrive.

The workflow therefore always runs and always reports. The selection step resolves a documentation-only change to an empty test set, the jobs exit success immediately, and the check goes green in seconds. **The cost of always reporting is a few seconds; the cost of not reporting is a pull request nobody can merge.**

### 3.4 Concurrency

```
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
```

Superseded pull request runs are cancelled, which is safe here because nothing in `gate-on-change.yml` spends quota or writes anything a later run depends on. This is the opposite of the rule in `evaluate-live-weekly.yml`, for reasons given there.

### 3.5 Running the full suite manually, before a merge

`gate-on-change.yml` accepts `workflow_dispatch` in addition to push and pull request. A maintainer can run the full suite on a branch without opening a pull request, and after a merge the same workflow runs on the default branch automatically.

**A manual dispatch of `gate-on-change.yml` is gated.** It carries `run_context: ci`, supplies no filter, and therefore derives `selection_mode: full`. This is the same status a pull request run already holds: unmerged code, recorded, and backstopped by the merge run.

That is deliberately not the status of a debug run. The difference is not the branch and not the completeness of the selection; it is that `gate-on-change.yml` always runs one ref as it stands, while `diagnose-on-demand.yml` may assemble a run from parts that were never released together. Section 6.5 sets out why that distinction decides gating.

---

## 3A. `regress-harness-on-branch.yml`: The Whole Suite, On Demand, Gated

**What the gate deliberately does not do.** Section 3 scopes a pull request run
to what the change can affect, which leaves a real question unanswered: is this
branch sound in full, not merely unbroken where it was touched?

| | `gate-on-change.yml` | `regress-harness-on-branch.yml` |
|---|---|---|
| Trigger | Push, pull request | Manual dispatch only |
| Selection | Change-scoped on a pull request | **Always full, never scoped** |
| Platforms | Both | Both |
| Engines | All three, replay | All three, replay |
| Verdict | Yes | **Yes** |

**It is gated, and that is the point.** It carries `run_context: ci`, supplies no
filter and therefore derives `selection_mode: full`, so the verdict it produces
is the real one. A developer running it before opening a pull request learns
what the merge run would say, a day earlier.

**It takes a `ref` input** so a maintainer can regress any branch without
checking it out. That is a convenience rather than a capability: the run is
still one ref as it stands, which is what separates it from a diagnostic run
assembling a tree from parts that were never released together.

---

## 3B. `regress-consumers-on-merge.yml`: Finding Out Before The Consumer Does

**This is the fan-out section 11 named as the capability a split provides**, and
the reason the split was worth doing.

A harness change is verified here against this repository's own preconditions.
Those prove the instrument works; they say nothing about whether a case set that
pins this harness still passes. Split, that question is answerable: a harness
candidate runs against every case repository declaring compatibility with it.

| Trigger | Scope |
|---|---|
| A **green** gate on `main` or `stabilization` | Every registered consumer, at its paired ref |
| Weekly schedule | Every registered consumer, unconditionally |

**The weekly run exists for the same reason the live one does.** A consumer can
break without this repository changing, because a case set moves on its own. A
detector that only fires on our own merges would miss that entirely.

**It fires from a green gate rather than from a push.** Fanning out from a
commit whose own gate failed spends a consumer's CI to discover that a harness
already known to be broken is broken. That matters most on `stabilization`,
which is red by design while it is being stabilized, and it is the same rule the
consumer applies in the other direction under section 3C.

**The trigger carries the commit its gate passed on, and that commit is what is
checked out.** The branch may have moved on already; checking out the branch
would fan out from a commit no gate has seen, which is the window 3C.2 closes on
the other side of the same relationship.

**Each consumer is tested at the ref paired with the branch that was pushed**,
per the mapping in section 3C. A harness branch the mapping does not name falls
back to the consumer's `default_ref`, which is every feature branch: requiring a
registry entry per feature branch would make the registry the thing that stops a
branch being tested.

### 3B.1 Consumers are a registry, not a hardcoded list

`config/consumers.yaml` names each case repository and the ref to test against.
Adding a consumer is an entry, which is A12 applied to CI.

**A consumer that cannot be reached is a harness event, never a red suite.** A
private repository, a deleted branch or a rate-limited clone says nothing about
whether this harness is sound. It is recorded and reported, and the job that
reports it does not fail the run, on the same reasoning that makes a probe
failure a `QC_HARNESS_*` event rather than a model finding.

### 3B.2 What a consumer failure means, and what it does not

**It does not block this repository's merge.** By the time this workflow runs,
the merge has happened. What it produces is the earliest possible notice that a
consumer needs attention, which is strictly more than the consumer would have
had otherwise.

Treating it as a merge blocker would also invert the dependency: a case
repository could hold the harness hostage by carrying a failing case, and the
harness would be unable to release a fix for it.

---

### 3B.3 The graded replay runs here too, and only our codes fail it

Added 2026-10-01.

**The regression ran the consumer's deterministic gates and stopped there**, so
it asked whether a harness change broke the consumer's preconditions and never
whether it broke the graded path. Three harness defects reached `AP-Model-QC` on
2026-09-28 and **two of them broke the graded path**:

| Defect | Broke | Caught by this regression |
|---|---|---|
| `observation_index` collapsing three judgements into one file | Judgement replay | **No** |
| The engine roster read by directory adjacency | The graded gate's first step | **No** |
| `fill_gaps` set on a plan the channel never received | A live fill | No |

Both were found when the consumer's own gate went red after a push, which is
later and attributes the failure to whoever pushed the consumer rather than to
the harness change that caused it.

**A graded replay costs nothing.** It contacts no provider, needs no credential
and takes under two seconds, so the argument for excluding it was never cost.

#### 3B.3.1 The taxonomy decides what turns it red

**A model finding must not fail this job.** The consumer currently carries two,
and a harness regression that went red because `gemini-3.8-flash` overstates a
figure would be reporting the wrong subject: it would be red permanently, for
something no harness change can fix, which is how a signal stops being read.

So the step runs and **the outcome is judged by the code, not by the count**:

| Outcome in the graded replay | This job |
|---|---|
| `QC_HARNESS_*` anywhere | **Red.** Our change broke the consumer |
| An `error` rather than a failure | **Red.** Same reason, reported differently |
| `QC_LLM_*` or `QC_SEC_*` failures only | Green. The model underperformed, which is not this job's subject |
| A skip under `QC_HARNESS_DEPENDENCY_UNMET` | Green. A dependent of a model finding, not a harness fault |

That is `framework-rules.md` section 4 used as a gate rather than as a label:
the families split by what the code asserts about, and this job asserts about
the harness alone.

**The consumer's own gate keeps judging the model**, unchanged. Two jobs read
the same run and ask different questions of it, which is the point of having
the codes.

---

#### 3B.3.2 The gate ran for the first time on 2026-10-02, and failed to start

The step invoked `python tools/consumer_regression.py` from the workspace root.
**The job checks this repository out to `harness/`**, so the path does not
exist there and every run of the step ended:

```
python: can't open file '.../AP-Harness-QC/tools/consumer_regression.py'
```

**So the gate has never evaluated a report.** The replay step before it carries
`continue-on-error`, by design, because a model finding is the consumer's
business. That is what kept the job green while the gate did nothing: the only
step that could fail was the one that could not run.

| | Covered by | Before |
|---|---|---|
| The tool fails only on `QC_HARNESS_*` | `MQC_CMN_UNI_112523` | Yes |
| The workflow can reach the tool | **Nothing** | **No** |

**This is the fifth instance of one shape in this project.** `--max-spend`
accepted a ceiling that stopped nothing, `--priority` named a band and ran every
band, `--extra-columns` names a policy and reaches no code, `MQC_EXE_UNI_113000`
asserted half of what section 4.3 splits in two, and now a gate whose logic is
proven and whose invocation is not. **Each time the thing itself was right and
nothing established that it was reachable.**

`MQC_CMN_UNI_112524` resolves every script path a workflow step runs, against
the checkout layout that step executes in, so a path that cannot exist fails the
unit gate rather than passing silently in a job that reports success.


## 3C. Branch Topology, And Which Harness A Case Set Runs Against

Added 2026-09-23. Two repositories each carrying branches means a run is defined
by a **pair** of refs, and the pairing has to be decided rather than assumed.

| Repository | Branch | Holds |
|---|---|---|
| `AP-Harness-QC` | `main` | The harness the main regression runs on, and what test development is written against |
| `AP-Harness-QC` | `stabilization-*` | One cycle's harness stabilization, and the extensions new cases need before they can exist |
| `AP-Harness-QC` | `expand-*`, `extend-*`, `debug-*` | One unit of work each |
| `AP-Model-QC` | `main` | Every case that works |
| `AP-Model-QC` | `stabilization-*` | One cycle's cases being stabilized before they merge to `main` |
| `AP-Model-QC` | `expand-*`, `extend-*`, `debug-*` | One unit of work each |

Every branch other than `main` is dated and names its kind, section 3C.6.

**The pairing follows from what each branch is for**, and only one pairing is
non-obvious. A case expansion needing no new harness capability pairs with
harness `main`, because that is what its cases run against once merged. A case
expansion **requiring a harness extension** pairs with the harness branch
carrying that capability, named by the entry the branch adds to the mapping
when it is cut (section 3C.6.6), because the capability exists nowhere else
yet.

That second case is the one that matters, and it is why the pin cannot be a
constant.

### 3C.1 The pin is data, not a dependency string

`pyproject.toml` carrying `ap-harness-qc @ git+...@main` states one pairing for
every branch, so the expansion case above cannot be expressed at all. Editing
the pin to reach `stabilization` makes the edit **part of the change**, and
merging the change merges the wrong pin with it.

`AP-Model-QC/config/harness_pin.yaml` maps a case branch to a harness ref
instead. The mapping is data carried on the branch, the workflow resolves it,
and merging an expansion branch restores the `main` pairing because the mapping
says so rather than because somebody remembered to revert a line.

The declaration in `pyproject.toml` stays, and becomes a **floor rather than a
pairing**: it is what a clone installs when nothing resolves a pin, which is the
right default precisely because `main` is the branch required to be green.

### 3C.2 Green is a property of a commit, never of a branch

"Is `main` green" has no answer, because `main` moves. **The ref is resolved to
a commit first, the commit's status is what gets asked about, and the same
commit is what gets installed.**

Resolving a ref, checking the branch, then installing the branch would leave a
window in which the commit installed is not the commit checked, and the window
is widest exactly when the harness is busiest. This is the same failure as a
replay fixture whose stored request hash no longer matches: the thing measured
is not the thing verified.

### 3C.3 Absence of a result is not a pass

| Status of the required workflow on that commit | Green |
|---|---|
| Concluded `success` | **Yes** |
| Concluded `failure`, `timed_out` or `cancelled` | No |
| Still running, or queued | No |
| No run exists for that commit at all | **No** |

The last row is the one that costs something to get right. A commit with no run
is the normal state of a branch pushed seconds ago, and treating it as green
because nothing failed is how an unverified harness becomes the instrument. It
is the same defect as a mistyped identifier selecting zero tests and exiting
clean, which section 6A.2 already guards on the other side.

**`gate-on-change.yml` is the single required workflow.** It runs on push, so
every commit on every branch gets one, which is what makes it usable as a
requirement. `regress-harness-on-branch.yml` is dispatch-only and therefore
cannot be required of an arbitrary commit; when it has also passed that is
strictly more evidence, and it substitutes for nothing.

### 3C.4 The check cannot live in the thing it checks

The resolution runs in `AP-Model-QC`, uses the standard library only, and
imports nothing from this repository. That is a constraint rather than a
preference: **a check fetched from the harness would be asking an unverified ref
to vouch for itself**, and it must run before the harness is installed anyway,
which is a circular dependency as well as a circular argument.

It is also the consumer's decision to make. This repository publishes a status;
what a consumer refuses to run against is its own policy, and the
**Downstream Reporting Only** directive means this repository neither enforces
nor knows about it.

### 3C.5 Required on `main`, advisory on a stabilization branch

A single strictness setting cannot serve both branches. Refusing on any
non-green harness ref would block case stabilization precisely while the harness
is being stabilized, which is when the pairing exists to be used. Refusing
nowhere would let a red harness produce results on `main`.

| Case branch | Paired harness ref not green | Outcome |
|---|---|---|
| `main` | **Refused.** Exit 4, the job fails | Nothing is installed and nothing is measured |
| `stabilization-*`, expansion | Proceeds, **ungated** | Runs, produces no verdict, records the code |

**An ungated run here is the same object a manual selection produces.** Section
3.3 of `testing-standards.md` withholds a verdict when the selection was not
harness-computed; this withholds one when the **instrument** was not
established. Neither is a punishment and both refuse to let a partial result
read as a full one.

`QC_HARNESS_UPSTREAM_UNVERIFIED` is recorded in both rows. It is distinct from
`QC_HARNESS_DEPENDENCY_UNMET`, which section 3B.1 uses for a consumer that could
not be reached: **unmet means unavailable, and unverified means available but
not established.** The operator response differs, so collapsing them would cost
the distinction that makes either actionable.

The strictness is per-branch data in `harness_pin.yaml` rather than a constant
in a workflow, so raising or lowering it is an entry rather than an edit to
control flow.

---


### 3C.6 Every working branch is dated, and carries what it is for

Added 2026-09-24, superseding the long-lived `stabilization` branch this
section first described. **`main` is the master branch.** Every other branch is cut from it,
merged back into it, and deleted.

```
<kind>-<referent>-<MM-DD-YYYY>
```

| Part | Is | Example |
|---|---|---|
| `<kind>` | `expand`, `extend`, `stabilization` or `debug` | `extend` |
| `<referent>` | **What the work is** | `MQC-1234` |
| `<MM-DD-YYYY>` | The day it was cut from main | `09-24-2026` |

```
extend-MQC-1234-09-24-2026
expand-115005-09-24-2026
stabilization-v1.2.0-09-24-2026
```

**The referent comes first because it is the key.** Several branches are cut on
one day and none of them is distinguished by that, so ordering by date groups
unrelated work and separates related work. The stamp anchors the end, which is
also what lets a referent carry hyphens of its own.

**The month leads on purpose.** Staleness is measured in weeks, so the month is
the digit that answers the question, and putting it first makes a stale branch
visible in a listing without reading any date in full. Under `DD-MM-YYYY` the
leading digits would be the day, which is noise for the one thing the stamp
exists to signal.

**This is deliberately not ISO 8601 and must not be corrected into it.** It
does not sort lexically, and that is the point: sorting by date is not what a
branch listing is for. The cost is that `MM-DD` reads as `DD-MM` in much of the
world, so the parser accepts exactly this order and reports a transposed stamp
rather than reinterpreting it as a different date.

**`main` never merges into a branch.** A branch that has fallen behind is
**succeeded**, not caught up, by the procedure in section 3C.6.4. That is what
makes the date mean something: it is the last moment this branch and `main`
agreed.

#### 3C.6.1 A working branch names its work, an integration branch names its cycle

A date says when. For a **working** branch it does not say what, and a listing
of six dates is a listing of six unknowns, so `expand`, `extend` and `debug`
each carry a referent naming the one unit of work they hold.

**The referent is a constrained vocabulary rather than prose**, and it is a
registry in the sense `testing-standards.md` uses for layer tokens: adding a
kind is a row, not a code change.

| Kind | Shape | Checked |
|---|---|---|
| Ticket | `MQC-1234`, `AP-88` | Shape only |
| Case identifier | `115005`, `112504` | **Shape and existence** |
| Release | `v1.2.0` | Shape only |

**The case-identifier kind is the one that earns its keep.** A branch claiming
to fix `115005` where no such case is inventoried is a typo, and the gate reports
it on the first push rather than at review. This project has been bitten by an
identifier that bound to nothing often enough to check the cheap instances.

**A ticket is checked for shape and never for existence**, because reaching an
issue tracker from a precondition would put a network call in the one layer
that is required to run without one, and would make the gate fail when somebody
else's service is down.

**One referent per working branch.** Work spanning three cases takes a ticket
covering them, because a branch naming three things is a branch doing three
things.

##### An integration branch is named for the day it was cut

```
stabilization-09-24-2026
stabilization-v1.2.0-09-24-2026
```

**`stabilization-<MM-DD-YYYY>`, the date of its creation, is the name.** The
project owner set it on 2026-10-21 as the goal for every stabilization branch;
the referent form below stays permitted for a release, and is the exception.

**Doing several things is what an integration branch is for.** It collects
whatever merged in one cycle, which is genuinely not one referent, and forcing
one means picking arbitrarily among the tickets it carries. That is worse than
omitting it: `stabilization-MQC-1234-09-24-2026` asserts the branch is about
`MQC-1234` when it is about five tickets, and a name that asserts something
false is worse than one that asserts less.

**For a cycle the date is the identity rather than a timestamp on it.** There
is normally one stabilization branch per cycle, so the date already
distinguishes it, which is the job a referent does on a working branch.

**This is not an exception to the rule.** The rule is that a branch names what
it holds. A working branch holds one unit of work and names it; an integration
branch holds a cycle and names the cycle. Stating it per kind is the rule being
precise, not a carve-out for an inconvenient case, and the distinction is
mechanical rather than a matter of judgement: `MQC_CMN_UNI_112510` accepts a
bare stamp for `stabilization` and `112505` refuses one for every other kind.

**A referent is still permitted where a real one exists**, such as a release
being stabilized. What is removed is the obligation to invent one.

#### 3C.6.2 Everything reaches main through a stabilization branch

| From | To | Permitted |
|---|---|---|
| `expand-*`, `extend-*`, `debug-*` | `stabilization-*` | Yes |
| `stabilization-*` | `main` | Yes |
| `expand-*`, `extend-*`, `debug-*` | **`main`** | **No** |
| `main` | Anything | **No** |

**One route into main means one place the integration is tested.** A second
route is a route around the test, and the branch that takes it is the one
nobody thought needed integrating, which is the branch most likely to need it.

#### 3C.6.3 The date is a staleness ceiling, not a label

A branch that cannot take `main` and has not been succeeded is testing an
integration that no longer exists. How long it has been doing so is exactly
what its name records.

| Age | Gate |
|---|---|
| 0 to 13 days | Green, silent |
| 14 to 29 days | Green, **age reported in the job summary** |
| 30 days or more | **Red, until the branch is succeeded** |

**The warning band exists so the ceiling is not an ambush.** A branch turning
red overnight with no notice would be resolved by editing the date, which is
the one repair that makes the name lie. Two weeks of visible warning is enough
to succeed a branch deliberately.

**The stamp is compared against the commit date, not against a clock read at
assertion time.** A rule that changes its answer between two runs of the same
commit is not checkable, and this project computes verdicts from an injected
date for the same reason.

#### 3C.6.4 A stale branch is succeeded, never caught up

The remedy preserves the direction of the rule rather than carving an exception
out of it.

1. Cut a **new** branch from current `main`, dated today, carrying the same
   referent.
2. Merge the **stale branch into the new one**.
3. Continue there. The stale branch is abandoned and deleted.

```
main            A---B---C---D---E
                 \               \
stab/09-24        X---Y           \          (stale at 30 days)
                       \           \
stab/10-24              \-----------M---Z    (work continues here)
```

**The work moves onto a fresh base. The base is never dragged to the work.**
`main` is still merged into nothing, so the rule needs no exception, and the
history is preserved by a merge rather than rewritten by a rebase.

**The new branch's date is honest on the day it is created**, which is the
property editing a stamp would destroy. Succession restarts the clock because
the branch genuinely agrees with `main` again, and that is the only thing the
date was ever claiming.

This is written for `stabilization`, where it matters most because an
integration branch collects several branches and outlives all of them, but
nothing about it is specific to that kind.

#### 3C.6.5 Succession is not a back-merge, and the check must not confuse them

The merge in step 2 has the stale branch as its incoming parent, which is
**not** an ancestor of `main`: it carries the unmerged work that is the whole
reason the branch existed.

A back-merge is the opposite shape, an incoming parent that `main` already
contains. That is what the no-back-merge check reads, so succession passes it
without needing to be named as an exception. **A check that had to special-case
the approved remedy would be a check nobody could reason about.**

#### 3C.6.6 What this costs, and why it is still right

Dated branches are short-lived by construction, so the pairing mapping gains an
entry per stabilization cycle rather than carrying two constants. **That entry
is added on the branch when it is cut**, which is the same carried-on-the-branch
property section 3C.1 already relies on, and merging removes it for free.

The alternative, one long-lived `stabilization` in each repository, needs an
exception to the no-back-merge rule within a week of being written. **A rule
with an exception for the case that occurs weekly is not a rule**, and the
exception would have been granted to the branch whose divergence matters most.

#### 3C.6.7 Specified and built, and not yet enforced, by decision

Recorded 2026-10-21 at the project owner's instruction. **`cmn.branch_policy`
implements every rule in section 3C.6 and is called only by precondition
cases**, `MQC_CMN_UNI_112505` to `112510` here and `MQC_CAS_UNI_115314` and
`115315` in `AP-Model-QC`, which check the referents its pin entries name. No workflow runs it on a pull request, and
`main` carries no branch protection requiring it, so today a branch can merge
into `main` directly.

**That is deliberate.** The policy exists so that unstable or untested builds
never reach `main`: every new branch merges into a stabilization branch, which
merges into `main` only once green, and a stabilization branch that expires is
merged into a new one cut from `main`. Enforcing it while the demo is still
being built would route every change through a stabilization cycle before there
is anything stable to protect. **It takes effect once the demo is finalized, or
near enough, and ready for expansion.** The project owner set the point on
2026-10-21: branches are tested once the demo is in the portfolio, and **until
then changes merge directly into `main`**, since neither repository is live in
it.

| | State |
|---|---|
| Rules, section 3C.6 | Specified |
| `cmn.branch_policy` | Built, with its cases passing |
| A pull-request job calling it, and branch protection on `main` requiring that job | **Not yet built.** The step that switches the policy on |

**The requirements in section 3C.6 are satisfied as functions, not as a gate.**
Until the job exists, a red here means a function returned the wrong answer,
never that a branch was refused.

#### 3C.6.8 A branch a workflow or a pairing names is one the policy accepts

Added 2026-10-21. **`regress-consumers-on-merge.yml` triggered on `main` and a
bare `stabilization`, and `config/consumers.yaml` paired a bare
`stabilization`**, both left from the single long-lived branch this section
replaced. The naming check refuses that name, so a correctly named
`stabilization-10-21-2026` would have triggered nothing and paired with the
default.

**So every branch a workflow's `push`, `pull_request` or `workflow_run` filter
names, and every key of a consumer's `refs`, is `main`, `**` for every branch, a
name `name_problems` accepts, or a `<kind>-*` pattern over a registered kind.** A cycle's dated stabilization branch
adds its own literal pairing when it is cut, as `AP-Model-QC`
`config/harness_pin.yaml` already does, and falls back to the consumer's `main`
until then.

`cmn.workflow_standards.unaccepted_branch_names` reports each name that is none
of the three, and `MQC_CMN_UNI_112421` calls it with this root.

## 4. `probe-model-version-nightly.yml`: A Change Detector, Not A Test Run

### 4.1 What it does

For each registered engine, resolve the model version the adapter would use and compare it against the recorded baseline. Nothing is evaluated and no case executes.

The probe reuses `execution/preflight.py`, which exists regardless: `MQC_REQ_HAR_EXE_0005` requires the resolved version to be recorded and makes its absence a preflight failure. **The probe is that code called on a schedule.**

### 4.2 What a change does

A changed version writes the new baseline and dispatches `evaluate-live-weekly.yml` for **that engine only**. An unchanged version ends the run.

| Probe result | Action | Record |
|---|---|---|
| Version unchanged | Nothing | Baseline timestamp updated |
| Version changed | Dispatch `evaluate-live-weekly.yml`, that engine | New version recorded with the previous one |
| Probe fails | Alert, no dispatch | Recorded as a harness event, never a model finding |

**A probe failure is not a test failure.** It means the detector is broken, which is an instrument defect, and the weekly run still covers the period regardless. Treating it as a red suite would be the same category error the `QC_HARNESS_*` family exists to prevent.

### 4.3 Why it is worth having

Detecting a provider's model change on the morning it happens costs a metadata call. The alternative, a nightly full live run, mostly re-measures an unchanged model at full price.

It also improves attribution, which matters more than the saving. A regression surfacing the morning after a recorded version change is attributable to that change. The same regression in a weekly run covers seven days of candidate causes. That attribution problem is exactly what A2 and A8 exist to address.

---

## 5. `evaluate-live-weekly.yml`: The Only Workflow That Spends

### 5.1 Triggers

| Trigger | Scope |
|---|---|
| Weekly schedule | All engines, full |
| Dispatch from `probe-model-version-nightly.yml` | The one engine whose version changed |

**The weekly run is unconditional because a version string is not a guarantee.** Providers revise a model behind a stable identifier, so a probe reporting no change is evidence rather than proof. This is the same structure as change-scoped pull request runs backstopped by a full run on merge: a cheap detector is only safe when something unconditional stands behind it.

### 5.2 Engine legs

| Engine | Mode in v1 | Why |
|---|---|---|
| `gemini` | Live | Free tier, judge and candidate, per A3 |
| `openai` | Replay | No key provisioned, per A3 |
| `claude` | Replay | No key provisioned, per A3 |

The decision that each engine gets its own CI job still holds; two of the three simply never spend quota. **`--engine` and `--mode` stay orthogonal**, so provisioning a key later is a configuration change and not a refactor. That orthogonality is the whole point of A6's flag design.

### 5.3 Serialization

```
strategy:
  max-parallel: 1
concurrency:
  group: live-${{ matrix.engine }}-${{ matrix.mode }}
  cancel-in-progress: false
```

**`max-parallel` orders legs within a run; `concurrency` prevents overlap between runs.** They are not interchangeable, and using the wrong one here has a specific failure: a concurrency group holds exactly one pending job, so placing bands in one makes them contend for a single waiting slot, and the losers surface as cancelled, which reads as failure.

`cancel-in-progress: false`, unlike `gate-on-change.yml`. A cancelled live run has already spent its quota and leaves a partial record.

The group is keyed on engine **and** mode so replay legs never wait on a live leg, since they contend for nothing.

### 5.4 Request spacing and observation count

Three observations per case, per A4, against the consumer's graded corpus, which carries 69 cases as of 2026-09-26. The count lives there rather than here, and the figure above was stale because this document restated it. Spacing is configured per engine because free-tier ceilings differ, and the two must be designed together: tripling observations triples request volume against the same ceiling.

Exhausted backoff **skips** rather than fails, per `MQC_REQ_HAR_EXE_0010`. The goal is measuring a model, not load-testing a provider.

---

## 5A. `audit-mutation-on-dispatch.yml`: Gate 8, Which Tests The Tests

Added 2026-10-15, and **made manual on 2026-10-24**: the audit measures
neither the harness nor a model and cost about ten hours of project time in
the week before, so it is a tool somebody points at a module rather than a tax
on every push. Specified by `harness_test_taxonomy.md` sections 15 and 15.6A;
this section states only the job.

| | |
|---|---|
| Starts on | **A manual dispatch, and nothing else.** No push, no path filter, no schedule. It takes the module to audit and a ref to narrow it to, both optional |
| Runs | `python -m tools.mutation_declarations`, then `pytest -m mutation tests/mutation`, Ubuntu only: platform coverage is the gate's question, not this one's |
| Stops before measuring | A declaration that is not the module on disk. Six hashes decide it, so a manifest that cannot describe the commit costs an install rather than the whole audit, taxonomy section 15.7.2 |
| Credentials | None. It mutates our code and runs our suite; nothing reaches a provider |
| Blocks | Nothing. **No required status**: a survivor is a fact about coverage, taxonomy section 15.6 |
| Red when | A survivor is undeclared, a declaration no longer survives, **or an audit refused**, taxonomy section 15.7.1 |
| Concurrency | One per ref, superseded runs cancelled: an audit of a commit `main` has moved past answers nothing |
| Record | An artifact outside the collector's pattern, so a coverage audit never reads as a measurement. The summary carries the elapsed time of the measurement and how many audited modules it reached |

**A refusal is a skip at the case and red at the job.** The edit that
triggered the run usually invalidates the edited module's digest, so this is
the ordinary path and the summary says which module to re-measure and
re-declare rather than leaving a green job over audits that did not run.

**Not in the pull-request sequence**, for the cost taxonomy section 15.7
measured: minutes per module against seconds for every precondition.

**The cheap question is asked first.** A measurement costs minutes per module,
and the comparison deciding whether it is worth starting costs 48 milliseconds,
so the job compares every declaration before it measures one and stops there
when the manifest does not describe the repository. Taxonomy section 15.7.2
carries why that is a cost decision rather than a change to what a case
reports.

**The trigger covers the audit's own tools as a pattern rather than by name.**
`tools/mutation_audit.py` was named when the audit was one file. The manifest
API moved to `tools/mutation_declarations.py` on 2026-10-23 and the parallel
measurement to `tools/mutation_parallel.py`, and neither path triggered
anything, so a change to what gets audited ran no audit.
`tools/mutation_*.py` covers the next split as well, and
`MQC_CMN_UNI_112379` asserts that every file matching it is matched by a
declared path.

## 6. `diagnose-on-demand.yml`: Runnable, Never Counted, Never Silent

Ships in v1. It exists for work that cannot use `gate-on-change.yml`: a new harness implementation or a new test case, on a branch, where the point is to find out whether the thing works at all.

### 6.1 Three independent exclusions

| Mechanism | Implementation |
|---|---|
| Structural | Artifact named outside the collector's pattern, section 7 |
| Row marking | Every result carries `run_context: ci_debug` and `gated: false` |
| Derivation | `gated` is false because `run_context` is not `ci`, whatever the selection was |

**Three, because the first two assume something the third does not.** Structural separation fails the day someone widens a collector pattern. Row marking fails if nobody filters on it. Both originally rested on a debug run carrying a manual selection, which stops being true the moment somebody runs the full suite on a branch to validate a harness change.

The third is the load-bearing one, and it is stronger than a selection rule. **A branch carrying new harness code produces results describing a harness that does not exist on the default branch.** The measuring instrument was different, so the results are wrong to record however carefully the selection was made.

A debug run therefore returns pytest's exit status and never a verdict code.

### 6.2 Exclusion from the record is not exclusion from notification

These are different questions and the design keeps them apart.

Whether a result enters the durable record is a question about **what it means**: an unbacked selection on an unreleased harness means nothing as reliability history. Whether someone is told the run finished is a question about **who is waiting**, and a developer blocked on a branch is waiting.

| Concern | Debug run |
|---|---|
| Durable record | Excluded, three ways |
| Overall CI status | Excluded, see below |
| Commit status check | **None emitted** |
| The person who dispatched it | Notified |

**`diagnose-on-demand.yml` emits no commit status check at all.** This is deliberate and is the mechanism that keeps it out of overall CI status: branch protection can only read checks that exist. A workflow that reports a check and then asks to be ignored relies on configuration nobody revisits, while a workflow that reports nothing cannot be misread.

That is also why notification is routed to a person rather than to the commit. A notification tells someone their run finished; a status check tells the repository whether a commit is fit to merge. Debug answers the first and must never appear to answer the second.

### 6.3 What gets sent

| Event | Channel |
|---|---|
| Run fails | GitHub's native notification to the dispatching actor |
| Run passes after the previous run on that branch failed | Job summary, plus webhook when configured |
| Run passes after a pass | Job summary only |

**The transition is the signal worth pushing.** A failure is already delivered natively and needs nothing built. A pass after a pass is noise. A pass following a failure is the moment the developer was waiting for, and it is the only one GitHub does not surface by itself.

**Transition detection needs no stored state.** The previous run's conclusion for the same workflow and branch is already in the run history, so the job reads it rather than keeping a baseline. A baseline file would be a second source of truth that can drift, for a signal the platform already holds.

**A first run on a branch has no previous conclusion**, which is not a transition. The comparison is therefore stated at that boundary and covered by `MQC_CMN_UNI_112212`. This is the same shape as the probe's absent baseline in section 4: a missing prior value means there is nothing to compare, not that something changed.

The webhook is read from a repository variable and is **absent by default**, so a clone of this repository runs the debug workflow without it and simply gets the job summary. Nothing in the design requires an external service.

### 6.4 Checkpoint diagnostics: two refs, not a rollback

When results degrade and `probe-model-version-nightly.yml` reports no model version change, three causes remain: our harness changed, the model drifted behind a stable version string, or the run was flaky. Separating them by reverting the default branch is expensive and disruptive, and it treats a diagnostic question as a release decision.

`diagnose-on-demand.yml` takes **two refs instead of one**:

| Input | Default | Supplies |
|---|---|---|
| `code_ref` | The dispatching branch | Harness and test code |
| `fixture_ref` | Whatever `code_ref` is | Recorded responses under `tests/fixtures/replay/` |

Fixtures are committed, so a checkpoint's fixtures come with its code by default and the two-ref form costs nothing when it is not used. Separating them is what makes attribution possible:

| `code_ref` | `fixture_ref` | Mode | Answers | Spends |
|---|---|---|---|---|
| Current | Current | Live | The ordinary run | Yes |
| Current | Checkpoint N | Replay | Did our evaluation change, holding the model's answers fixed | No |
| Checkpoint N | Current | Replay | Did our request composition change | No |
| Checkpoint N | Current | Live | Was the regression ours or the model's | Yes |
| Checkpoint N | Checkpoint N | Replay | Reproduces run N exactly | No |

**The second row is the one that needs no quota and answers the most common question.** Holding the recorded responses fixed and varying only the harness isolates our own scoring, parsing and assertion changes completely. If the current harness scores checkpoint N's responses differently than it did then, nothing about the model is involved.

**The last row is a purity check as well as a baseline.** Re-running a checkpoint against its own fixtures must reproduce that run's verdict exactly. If it does not, something non-deterministic has entered a computation that `MQC_REQ_HAR_CMN_0001` requires to be a pure function of observations, configuration and an injected date.

#### 6.4.1 Divergent refs make staleness a finding, not a fault

`MQC_REQ_HAR_EXE_0009` requires a stale fixture to be reported rather than silently replayed, on the basis that replaying a recorded answer to a different question is a corruption. **Under divergent refs, that report is the result rather than an error.**

A stale hash means the request composition changed between the two checkpoints, which is exactly what the third row of the table is asking. The run therefore reports staleness per fixture as a diagnostic finding and continues, rather than treating it as a harness defect and stopping. `MQC_EXE_UNI_113605` states this, and it is the only context in which a stale fixture is not a problem.

#### 6.4.2 Why this is not a rollback

The default branch does not move. Nothing is reverted, no release is withdrawn, and no history is rewritten. A checkout of an old ref inside a diagnostic job is a read, and its results are ungated by construction, so a checkpoint run cannot become a verdict about anything.

**This is also why the two-ref form forces the third gating condition rather than merely benefiting from it.** A run combining code from one checkpoint with fixtures from another describes a configuration that was never released. It is a legitimate experiment and an invalid observation.

### 6.5 The summary says what the run is not

Every debug run writes a job summary opening with an explicit statement that the run is diagnostic, carries no verdict, and gates nothing, followed by what it was and then the results.

| Field | Why it is there |
|---|---|
| Workflow and job name | A notification is worthless if the reader cannot tell which job produced it |
| Run number and run identifier | The run has to be findable again a week later, from the notification alone |
| `code_ref`, resolved to a commit | A branch name moves; the commit is what was actually executed |
| `fixture_ref`, resolved to a commit | Equal to `code_ref` in the ordinary case, and the whole point when it is not |
| Changed areas: harness, tests, or both | Says what the run is actually exercising |
| Mode and engine | Whether responses were observed or replayed, and from where |
| Resolved model version per engine | Lets a reader confirm the model was constant, which is the premise a checkpoint comparison rests on |
| Selection mode and case count | How much of the suite this covers |

**Changed areas are reported as harness, tests, or both**, resolved by comparing changed paths against the production modules and `tests/`. The distinction matters when reading a result: a run where only tests changed and results moved points at the tests, and a run where only harness changed and results moved points at the harness. Reporting a single undifferentiated diff leaves the reader to work that out from paths.

**The resolved model version is in the summary because it is the premise of every checkpoint comparison.** The reasoning "our code caused this, because the model did not change" is only sound if the model demonstrably did not change, and a reader should not have to open an artifact to confirm it.

This exists because of a failure already recorded against the exit codes: **a reviewer, or the operator a week later, can read a diagnostic green as a suite green.** A notification makes that more likely, not less, because it arrives looking like every other build notification. The run name is set dynamically to carry the branch and the diagnostic marker for the same reason, so the Actions list is unambiguous before anything is opened.

**A green debug run does not make code mergeable.** It means the developer's work is ready to be offered, at which point `gate-on-change.yml` gates it under the ordinary rules. The notification announces readiness to open a pull request, never readiness to merge.

---

## 6A. `debug-failures-on-demand.yml`: Re-Running Exactly What Failed

`diagnose-on-demand.yml` selects by **marker expression**, which answers "run
the security suite" and cannot answer "run these four tests". A triage loop
needs the second: a run fails, and the question is why *those* cases failed, not
what an entire layer does.

| Input | Supplies |
|---|---|
| `tests` | Newline or comma separated test identifiers, or `nodeid` paths |
| `repeat` | How many times to run them, for a suspected flake |
| `mode`, `engine` | As elsewhere |

**It yields no verdict, and refuses to pretend otherwise.** A hand-typed set of
test identifiers is the definition of a manual selection under section 3.3, so
it carries `run_context: ci_debug` with `gated: false`, writes an artifact the
collector pattern does not match, and reports no status check. The three
independent exclusions of section 6.1 apply unchanged.

### 6A.1 Repeat is what separates a flake from a failure

A single re-run of a failing test tells you it still fails, which you knew. Ten
runs of it tell you whether it fails *consistently*, and that is the distinction
triage actually turns on.

**The summary reports the pass count rather than a verdict**, because a test
that passed six times in ten has not passed. Reporting a green because the last
attempt succeeded is precisely the reading this workflow exists to prevent.

### 6A.2 The identifiers are validated before anything runs

A mistyped identifier selects nothing, and pytest exits cleanly having run zero
tests. **That reads exactly like a run where everything passed**, which is the
failure mode section 7.3 of `cmn_verdict_and_cli.md` calls out for an unknown
case identifier.

The workflow therefore collects first, compares what was requested against what
was collected, and fails the step when any requested identifier matched nothing.

---

## 7. Artifacts

### 7.1 Naming

| Workflow | Artifact name |
|---|---|
| `gate-on-change.yml`, `evaluate-live-weekly.yml` | `mqc-reports-<layer>-<engine>-<mode>` |
| `diagnose-on-demand.yml` | `scratch-diagnose-<run_id>` |

A collector pattern anchors on `mqc-reports-`. **The debug name does not begin with that prefix**, so exclusion does not depend on a negative match, which is the kind of pattern that breaks quietly when someone edits it.

Names must stay stable across runs. Renaming a published artifact breaks downstream history for this repository, and nothing downstream can tell a rename from a gap.

### 7.2 Contents

JUnit XML and Allure raw results, per `testing-standards.md` section 5. No bespoke summary file: collectors parse standard formats, so a hand-rolled one would be read by nothing.

### 7.3 Retention

90 days, GitHub's maximum for public repositories. This is why durable history depends on something outside this repository collecting artifacts, and why the project does not attempt its own history store.

### 7.4 The report is generated and published, and the artifact stays the contract

Added 2026-10-24 at the project owner's ruling, with the reason the ruling
came from: pytest output answers which case failed, and the report is what a
reader assesses readiness from.

**Nothing rendered the results.** Every run uploaded Allure raw results and
`harness_running_jobs.md` section 5.2 told a reader to install the Allure
command line and generate a report from a downloaded artifact. That is three
steps and a toolchain between a run and the picture, so in practice the
picture was never looked at, and a format nobody renders is a format nobody
reads.

| | Answers | Where |
|---|---|---|
| JUnit XML | Which case failed | The artifact, as before |
| Allure raw results | What it did, with its steps and parameters | The artifact, as before |
| **The generated report** | **Whether the thing is ready**, by feature and by severity | **GitHub Pages, per repository** |

#### 7.4.1 Both repositories publish, and they answer different questions

| Repository | Published by | Says |
|---|---|---|
| `AP-Harness-QC` | `gate-on-change.yml`, on a push to the default branch | Instrument health: the preconditions that have to hold before any model result means anything |
| `AP-Model-QC` | `publish-report-on-merge.yml`, on a gate completing | Model readiness, **one report per engine**, each rendered from that engine's own run of one commit (`consumer_ci.md` section 4.22.2) |

**A pull request does not publish.** A fork's run cannot hold the Pages
credential, and a run that could would overwrite the default branch's picture
with a proposal's, so the pull request keeps the artifact it already had.

**The rule is reachability, not one guard**, because the two repositories reach
it differently. The harness gate is triggered by a push and by a pull request,
so its publishing job names the event. The case repository gates four targets
in four workflows on every push, so one publisher there would race three
others: its publisher sits outside them, triggered by their completion on the
default branch, and names no event because no pull request can reach it.

#### 7.4.2 Why this is not the history store section 7.3 refuses

**The refusal is about a record of truth, and it stands.** What section 7.3
rules out is this repository becoming the durable store a collector should be,
with results that exist nowhere else and a retention policy of its own.

| | The artifacts | The published report |
|---|---|---|
| Holds a result that exists nowhere else | No | **No.** Every case in it came from the uploaded artifacts |
| Read by a downstream collector | Yes, that is the contract | No, and nothing is invited to |
| Survives the 90 days | No | Yes, which is what makes it worth publishing |

**The trend directory is a convenience and not evidence.** Allure carries
history by reading the previous report before generating the next, so the run
fetches the published site's history directory first. Where that fetch finds
nothing, which is every first run and any run after the site is reset, **the
report generates without history rather than failing**: a missing trend is a
weaker picture, and a failed publish over a missing trend would be a job going
red about nothing.

`testing-standards.md` section 5 carries the amendment, because the sentence
that needed changing is there.

#### 7.4.3 It is its own job, and it never gates a merge

**A rendering failure says nothing about the code.** The deploy is a job of its
own taking `needs:` on the gates, so it runs only against results that passed,
and it fails visibly on its own row. That is the arrangement Gate 8 already has
for the same reason (section 5A).

**"Without blocking anything" takes `continue-on-error`, and this section said
it before it was true.** Corrected 2026-10-24, on the first push where the job
ran: a job failing inside a gate workflow makes the **run** conclude failure,
and the case repository's pairing resolver reads a run's conclusion rather than
a job's. So a Pages setting nobody had enabled refused all four model gates
with `QC_HARNESS_UPSTREAM_UNVERIFIED`, and the repository that measures models
measured nothing.

| | The job | The run |
|---|---|---|
| Without `continue-on-error` | Red | **Red**, and every consumer pinning the commit refuses it |
| With it | **Red, on its own row** | Green, which is what the gates established |

**The rule is about reachability, as the trigger rule is.** A publishing job in
a workflow whose other jobs are gates declares `continue-on-error: true`; a
publisher that is a workflow of its own, as the case repository's is, has no
conclusion to poison and declares nothing. `MQC_CMN_UNI_420005` checks the
first and does not require the second.

**Least privilege, on that job alone.** `pages: write` and `id-token: write`
are declared on the publishing job rather than at the workflow level, so no
step that runs a test can reach the deployment credential.

#### 7.4.4 One prerequisite is a repository setting rather than a change here

**Pages must be enabled with GitHub Actions as its source**, once per
repository, in the repository's settings. Until it is, the deploy job fails
with `Failed to create deployment (status: 404)` on its own row while the gates
stay green, which is the correct failure shape: the picture is missing and
nothing about the measurement is in doubt. **That shape is bought by
`continue-on-error`** (section 7.4.3), and this paragraph claimed it before it
was true.

This is the same boundary as the onboarding rule in `testing-standards.md`
section 5. A setting outside the tree is named in the documentation and not
pretended to be code.

`MQC_CMN_UNI_420005` and `MQC_REQ_HAR_CMN_0219`.

#### 7.4.5 Inclusion is decided by the commit, never by a run's conclusion

Added 2026-10-28, after the case repository's site reported a clean sweep on a
day three of its four gates were red.

**A red gate publishes, and that is what the site is for.** Section 7.4 makes
the published report a readiness view, and an engine carrying findings is the
one a reader needs rendered. That repository's publisher refused to start unless
the triggering gate had concluded `success`, and filtered the artifacts it
downloaded the same way, so the only engine to reach the site was the one with
no finding against it.

| Inclusion decided by | What a reader sees on a day three gates are red |
|---|---|
| The run's conclusion | One engine's report, and no sign the other three exist |
| **The head commit** | Four reports, three of them carrying the findings |

**The conclusion is the wrong question for a second reason.** A `workflow_run`
trigger fires once per completing workflow, so the job read whichever gate
happened to wake it and discarded three engines' results on the strength of a
fourth engine's outcome.

**No condition is needed for reachability either**, which is what the guard
resembled. `workflow_run` with `branches: [main]` cannot be reached by a pull
request at all, so section 7.4.3's concern about a proposal overwriting the
branch picture is already answered by the trigger.

`cmn.workflow_standards.report_publication_gaps` reports a publishing job that
reads a conclusion, in its condition or in its scripts.
`MQC_CMN_UNI_420005` plants one, and `MQC_CAS_UNI_430002` reads the shipped
workflows and failed against them before the fix. The case repository's
`consumer_ci.md` section 4.22.2.1 carries the decision from its own side.

---

## 8. Secrets

| Name | Needed by | Present in v1 |
|---|---|---|
| `GEMINI_API_KEY` | `probe-model-version-nightly.yml`, `evaluate-live-weekly.yml` | Yes |
| `OPENAI_API_KEY` | `evaluate-live-weekly.yml` if the leg goes live | No |
| `ANTHROPIC_API_KEY` | `evaluate-live-weekly.yml` if the leg goes live | No |

Secrets are held in a GitHub **Environment** named `live`. Environment scoping means the secret is unreachable from a workflow that does not name the environment, which makes A1's guarantee structural rather than conventional.

`gate-on-change.yml` names no environment and references no secret.

### 8.1 The boundary is trigger trust, not workflow count

Amended 2026-09-23, resolving a conflict this document held against itself. An earlier wording said secrets were referenced **only** by the probe and the weekly run, while section 6.4 specifies two diagnostic combinations that run live and spend. Both cannot be true, and the narrower statement was the stale one.

**What A1 protects against is an untrusted trigger reaching a credential**, not a third workflow existing:

| Workflow | Trigger | Who can fire it | Reaches `live` |
|---|---|---|---|
| `gate-on-change.yml` | Push, pull request | **Anyone, including a fork** | No |
| `probe-model-version-nightly.yml` | Schedule, dispatch | Schedule, or a maintainer | Yes |
| `evaluate-live-weekly.yml` | Schedule, dispatch | Schedule, or a maintainer | Yes |
| `diagnose-on-demand.yml` | **Manual dispatch only** | A maintainer with write access | Yes |

`workflow_dispatch` cannot be fired from a fork and cannot be fired by a pull request. The one workflow an untrusted party can trigger is the one that names no environment, and that is the whole of the guarantee.

**The environment is also where a spending control belongs.** A live diagnostic run costs quota, and GitHub environment protection rules (required reviewers, a deployment branch list) apply to whichever workflow names it. Putting the diagnostic workflow inside the environment brings it under that control rather than outside it.

**Naming the environment does not make a diagnostic run gated.** Gating is derived from `selection_mode`, precondition execution and `run_context`, none of which a credential touches. A live diagnostic run still carries `run_context: ci_debug`, still writes an artifact the collector pattern does not match, and still reports no status check.

The section 2 table's `Optional` is correct as written and is now explained here rather than left to inference: the credential is needed only for the live combinations in section 6.4, and a replay diagnostic needs none.

**The two absent keys are not a gap.** Their legs run in replay, which needs no credential, and the orthogonal flag design means adding a key later changes configuration only.


### 8.2 A credential in Actions made an unenforced ceiling matter

Added 2026-10-04, the day the first provider keys reached Actions.

**`--max-spend` was implemented, covered and passed by nothing.** The flag
reaches the dispatch session, accumulates toward refusal and fails closed on an
unpriced model; `MQC_CAS_UNI_115208` and `115409` establish that. **No workflow
set a value**, so every live leg ran with no ceiling.

**It was harmless until it was not.** Before 2026-10-04 no key existed in either
repository's Actions, so no CI run could spend whatever it asked for. Creating
the `live` environments turned a dormant gap into a live one, which is the
general shape worth recording: a control that is unreachable costs nothing until
the thing it controls becomes reachable.

#### 8.2.1 The ceiling, and the arithmetic behind it

**Two dollars per run**, as a workflow input so a dispatcher can lower it.

| | |
|---|---|
| Measured cost of a recording run | **Six cents** for the `SEC` family, 2026-09-28 |
| A full graded run for one engine | Cents, including the judge |
| The account's monthly limit | **$20 per provider**, recorded in `harness_open_questions.md` section 1 |
| The ceiling | $2.00, which is roughly thirty times the measured cost and a tenth of the monthly limit |

**The figure is a backstop, not a budget.** It exists to stop a loop, a
mispriced model or an escalation storm, not to ration ordinary runs: a run that
approaches it has gone wrong rather than done more work.

#### 8.2.2 What counts as a step that can spend

| Flag | Why it spends |
|---|---|
| `--mode live` | Dispatches to the candidate |
| `--judge-mode live` | Dispatches to the judge whatever the candidate mode. A replayed judge loads a stored judgement and never dispatches (`tier2_execution.md` section 7.9) |
| `--mode ${{ matrix.mode }}` | May be live on one leg of the matrix, so it is treated as spending |

`MQC_CMN_UNI_112257` and `MQC_CAS_UNI_115418` report a step that can dispatch
live and names no ceiling, one implementation called with each root.

**The check reads whole invocations, not lines.** A CI pytest call is written
across several lines with trailing backslashes, and the first version of this
check reported a step that carried both flags because they sat on different
lines. **A check that over-reports is one a reader learns to skip**, which is
worse than the gap it was written for.


### 8.3 One lint invocation, and a YAML parse that is not a schema check

Added 2026-10-04 after a push turned the harness gate red on a commit that had
been green locally, twice over, for two unrelated reasons.

#### 8.3.1 Four pylint invocations, four path lists

| Where | Omitted |
|---|---|
| `testing-standards.md` | `cmn/`, `tools/`, `conftest.py` |
| `docs/harness_running_jobs.md` | `tools/`, `conftest.py` |
| `gate-on-change.yml` | `tools/` |
| `regress-harness-on-branch.yml` | Nothing |

**The path list is part of the command.** A file in an omitted directory passes
one gate and fails another, which arrives as a red on a commit already reported
green, and a contributor following either document lints less than CI does.

**That is how this one surfaced.** A `conftest.py` line went to 154 characters.
Local linting followed neither document and omitted `conftest.py`, so it passed;
the gate lints it and failed on both platforms. **The defect was in the file and
the reason it escaped was in the command.**

All four now carry the broadest list, and
`MQC_CMN_UNI_112151` compares every invocation in the repository against the
others, reading the workflows and the tracked prose alike: a documented command
a reader copies is as load-bearing as the one CI runs.

#### 8.3.2 A workflow that parses is not a workflow that validates

The same push produced a second failed run whose **name was a filename** and
whose job count was zero. GitHub had rejected the workflow schema.

**The cause was a duplicate `inputs:` key** under `workflow_dispatch`, from
adding a spend-ceiling input to a stanza that already had one. YAML permits a
duplicate mapping key and resolves it last-wins, so:

| | |
|---|---|
| `yaml.safe_load` | **Accepted it**, and the earlier of the two blocks was silently discarded |
| What that discarded | The `max_spend` input, so the flag would have been unavailable |
| GitHub's validator | Rejected the file, reporting a failed run with no jobs |
| What a reader sees | A run named `.github/workflows/evaluate-live-weekly.yml` with nothing in it |

**A parse check answers a weaker question than a schema check**, and this
project had been treating them as the same: every workflow edit in the preceding
days was verified with `yaml.safe_load` and nothing else. `actionlint` runs in
CI and would have caught it, which is the right tool; the gap was in the local
step before the push, not in the pipeline.

**The remedy is to run the linter rather than the parser.** `actionlint` is
already a step in two workflows, so the fix is to use it locally and not to add
a second checker.

### 8.4 A workflow check follows a local `uses:`, or it goes blind

Added 2026-10-09, before the band jobs were collapsed into a composite action.

**`pylint_invocations` and the checks beside it read `run:` lines out of a
job.** Eight call sites in the case repository depend on seeing the pytest
invocation there: the attribution-ladder check, the engine-naming checks, the
green-gate check.

**Factor that invocation anywhere and those checks go quiet rather than red.**
A check that finds nothing reports agreement, which is the failure mode this
project treats as worst: a green that means nothing was read.

So `run_lines` resolves a local `uses:` and includes the referenced definition's
own `run:` lines. A composite action at `./.github/actions/band` is read as part
of the job that uses it.

| Reference | Followed |
|---|---|
| `./.github/actions/<name>` | Yes, its `action.yml` steps are read |
| `./.github/workflows/<name>.yml` | Yes, its jobs' steps are read |
| `actions/checkout@v5` | No. A third-party action is not this repository's prose |

**A missing local reference is a problem, not a silence.** A `uses:` naming a
path that does not exist means the workflow is broken, and the reader says so
rather than returning the lines it did find.

**This is a strict improvement whatever happens to the band jobs.** The checks
were already blind to anything factored out; nothing had been factored out yet,
so the weakness was latent rather than absent.

**The reader is the case repository's, so the requirement is too.** This was
first registered here as `MQC_REQ_HAR_CMN_0150` with `MQC_CMN_UNI_112349`, and
that was the wrong register: `pylint_invocations` here reads workflow files for
lint invocations and never walks a job's steps, while
`tests/cases/workflow_support.run_lines` there walks its own repository's. The
requirement is `MQC_REQ_CAS_CI_0050`, traced by `MQC_CAS_UNI_115726`.

**Both retired numbers stay retired.** Nothing was implemented against
either, and the authoring order is what caught it: design, trace, then code,
so the mis-registration cost a row rather than a module.

### 8.5 Every engine a workflow offers is an engine on the roster

Added 2026-10-14, after grok was found missing from four workflows ten days
after it was rostered.

**grok was rostered on 2026-10-04** with an adapter, a price, a recording run,
and a gate and weekly caller of its own in `AP-Model-QC`. Four workflows still
offered three engines:

| Workflow | Where the list sits |
|---|---|
| `debug-failures-on-demand.yml` | The `engine` choice input |
| `diagnose-on-demand.yml` | The `engine` choice input |
| `regress-harness-on-branch.yml` | The `engine` matrix |
| `AP-Model-QC` `debug-cases-on-demand.yml` | The `engine` choice input |

**This is `AP-Model-QC` `consumer_ci.md` section 4.19.3 one file further out.**
That section found the case repository's target list was a hand-written copy of
the roster and replaced it with a read. The workflows hold copies too, and a
copy written in YAML is one no Python check was reading. A dispatch menu
missing a rostered engine is quiet: the engine is simply not offered, and
nothing says why.

#### 8.5.1 The rule

**An engine list written in a workflow names exactly the rostered engines.** A
rostered engine missing from it is reported, and so is a name the roster does
not carry, because a stale name left after a retirement is the same drift in
the other direction.

| Read | Where |
|---|---|
| A choice input named `engine` | Its `options`, under `workflow_dispatch` or `workflow_call` inputs |
| A matrix dimension named `engine` | `strategy`, `matrix`, `engine`, when it is a list |

**Order is not compared.** A dispatch menu carries no meaning in its order, and
requiring the roster's order would report a reordering nobody needs to act on.

**A free-text `engine` input is not a list** and is not read. The harness
refuses an unrostered value at argument parsing (`MQC_CMN_UNI_112150`).

#### 8.5.2 What it does not read yet

**A matrix written as `include` entries is not read.** `evaluate-live-weekly.yml`
is the only one, and its legs pair each engine with a mode: gemini live, openai
and claude replay. **That pairing breaks the project owner's rule of
2026-10-08**, that a graded case runs against live agents only and replay on
both sides is for harness tests. Adding grok there is a decision about its
mode, which belongs to the replay correction rather than to this one. It is an
open item, and the check is widened when that workflow is redesigned.

#### 8.5.3 Enforced, from one implementation

`cmn.workflow_standards.engine_list_gaps` reports each list disagreeing with the
roster it is given, naming the workflow, the list and the engines missing or
extra. `MQC_CMN_UNI_112366` and `MQC_CAS_UNI_115743` call it with each root and
the roster read from the installed harness, the one-implementation-two-callers
arrangement section 8.2.2 already uses.

#### 8.5.4 A workflow that can run any engine live offers every engine's key

Added 2026-10-14, the same day and the same shape.

**A key is offered to a step only by name.** A secret set on the repository or
on the `live` environment reaches a step only through an assignment naming it in
that workflow, so a secret that exists is not a secret a run can read.
`debug-failures-on-demand.yml`, `diagnose-on-demand.yml` and `AP-Model-QC`
`debug-cases-on-demand.yml` each offer every rostered engine and a live mode,
and each assigned only the judge's key. A live debug run against openai,
claude or grok would refuse at preflight, which is correct and reported as our
configuration, and quiet enough to read as a skip nobody ordered.

**`AP-Model-QC` `consumer_ci.md` section 4.19.3 already had this rule for one
workflow**, `evaluate-engine.yml`, checked by `MQC_CAS_UNI_115710`. This widens
it to every workflow the same reasoning applies to.

| A workflow is checked when it | Read from |
|---|---|
| Lets the engine be chosen from a list | An `engine` choice input or matrix, as section 8.5.1 |
| And can run live | A `mode` choice input offering `live` |

**What is required is the assignment, not a mention**: `NAME` set from the
secret of the same name, anywhere in the workflow. A name in a comment sets
nothing. Which variable each engine needs comes from its adapter, so a caller
passes the declared variables and the check knows no provider.

`cmn.workflow_standards.unoffered_credentials` reports each workflow missing an
assignment. `MQC_CMN_UNI_112367` and `MQC_CAS_UNI_115744` call it with each root
and the variables the rostered adapters declare. **The value is never read**;
what is checked is the wiring, which is the part a roster addition forgets.

### 8.6 A job that runs graded cases is gated on the preconditions, or it spends on an unchecked instrument

Added 2026-10-25, after a corpus that had stopped loading was measured four
times.

**The rule is older than this section and is stated in three places.**
`framework-rules.md` section 1 makes Gate 2 blocking, `testing-standards.md`
says the graded layers do not execute if a precondition fails because running
them "spends provider quota to generate noise", and `AP-Model-QC`
`consumer_ci.md` section 3.12 expresses it as a job graph. **Five workflows
across the two repositories run graded cases and one of them implemented it.**

#### 8.6.1 What that cost, which is the reason for the section

On 2026-10-24 two assertions were added to the relay rules naming a constraint
that no task sends, so the join failed referential integrity and
`MQC_CAS_UNI_115000` reported `QC_DATA_INVARIANT_VIOLATION`. **Four graded
sweeps ran over it**, one per engine, and each reported ordinary findings: the
graded suite builds one case at a time, so a corpus-wide check is the only
thing that sees a dangling reference, and nothing in the ladder ran one.

**The register those sweeps produced was still valid**, because the assertions
themselves ran, and that is luck rather than a property. A reference that had
been dangling into a rule rather than out of one would have changed what was
graded, and the findings would have been filed against three vendors with
nothing saying the instrument was red.

#### 8.6.2 Two shapes satisfy it, and the difference is what the job holds

| Shape | A graded job | Chosen where |
|---|---|---|
| The job graph | `needs:`, directly or transitively, a job that runs the preconditions | A gate whose job names are read as a dashboard. `consumer_ci.md` section 3.12: the band is the diagnosis, so Gate 2 leaves the graded job entirely |
| Step order | Runs a precondition invocation in an earlier step of its own job, which a failure stops | A job holding a checkout it fetched. `regress-consumers-on-merge.yml` runs the consumer's own preconditions from the registry and then replays its graded layers, and splitting that across jobs would fetch the consumer twice |

**Both prevent the spend and neither is a relaxation of the other.** What the
job graph buys beyond step order is the diagnosis, and that is worth having
where somebody reads job names to decide what broke; it buys nothing in a job
whose subject is one fetched repository.

#### 8.6.3 What is read, and what is deliberately not

| Read | Why |
|---|---|
| Every workflow whose file name does not end `-on-demand` | A debug run's rows are `ci_debug` and yield no verdict, which is what a debug workflow is for. Section 8.2.2 and `consumer_ci.md` section 4.21 draw the same line |
| A local `uses:`, followed into the referenced definition | Section 8.4. The case repository's only graded invocation lives in a composite action, so a reader of jobs alone would call that job ungraded and report nothing |
| A step whose `working-directory` is a checkout the job fetched | **Not as a graded job of ours.** The cases, the corpus and therefore the preconditions belong to that checkout, and the repository that owns them asserts them in its own gate |
| Nothing computed | A marker or a command reaching a step through an input or a matrix carries no literal to compare, which is how every check over these files already behaves |

**The third row is a boundary rather than an exemption**, and it is the
`CLAUDE.md` rule about owning no case data applied to CI: a job that installs
another repository and runs its cases is measuring that repository's corpus
against our code, and what gates it is that repository's precondition command.

#### 8.6.4 The two instances this found

| Workflow | Was | Is |
|---|---|---|
| `evaluate-live-weekly.yml` | One `evaluate` job, needing nothing, running the graded layers live under a `--max-spend` ceiling | A `preconditions` job runs `pytest -m unit` and `pytest -m system`, and `evaluate` needs it |
| `AP-Model-QC` `evaluate-engine.yml` | Four graded invocations across three rungs, gated on `resolve` alone | A `preconditions` job ahead of rung 1, which every rung reaches through the chain |

**A scheduled retirement is not a reason to leave it.**
`evaluate-live-weekly.yml` is retired at a later step of the probe and
calibration plan and is fixed here anyway, which is the reasoning
`consumer_ci.md` section 4.21 used about the same workflow's selection.

**The ladder is the one that mattered**, because it is the workflow that
spends: rung 2 pays for a live judge and rung 3 for a live candidate, and both
were reachable with the corpus in the state section 8.6.1 describes.

#### 8.6.5 Enforced, from one implementation

`cmn.ci_gating.ungated_graded_jobs` reports every graded job that
reaches no precondition invocation, naming the file, the job and what it needs.
`MQC_CMN_UNI_112189` and `MQC_CAS_UNI_115782` call it with each root, the
one-implementation-two-callers arrangement sections 8.3, 8.5 and 8.5.4 already
use. `MQC_REQ_HAR_CMN_0226`, and `MQC_REQ_CAS_PRE_0015` on the other side.

**It is not `actionlint`'s subject and not a schema question.** The definition
is valid YAML and a valid workflow either way; what is wrong is the shape of
the dependency, which only a reader that knows what the layers mean can see.

---

## 9. Exit Codes To Job Status

**The codes and their meanings are normative in `cmn_verdict_and_cli.md` section 7.3 and are not restated here.** This section owns only the mapping from a code to a job outcome, which is the part that belongs to the pipeline.

An earlier version of this table restated all five meanings, which contradicted this document's own scope note declaring the CLI contract out of scope. Two statements of one fact is the drift pattern that has already produced two defects here, and restating a table while declaring it out of scope is the worst form of it.

| Code | Job outcome |
|---|---|
| 0 | Success |
| 1 | Failure |
| 2 | Failure, configuration defect |
| 3 | Failure, **distinct from 1** |
| 4 | Failure, **distinct from 1** |

**3 and 4 must not collapse into 1.** A red verdict says the suite measured something and it failed. A precondition failure says nothing was measured. A refusal says no verdict was computable from what was supplied. Collapsing them lets CI read "the harness is broken" as "the model underperformed", which inverts the attribution the whole design protects.

The CI step therefore reports the code rather than only its success or failure, so the distinction survives into the run summary.

---

## 10. What Is Tested About CI Itself

Workflow files are configuration, not collected code, so `pytest.ini` never sees them and `.pylintrc` is not run against them. They are covered three ways:

| Concern | Covered by |
|---|---|
| Selection logic correctness | `MQC_CMN_UNI_112120` through `112209` |
| Debug exclusion | `MQC_CMN_UNI_112210`, `112211` |
| Verdict gating on selection mode | `MQC_CMN_UNI_112123` through `112125` |
| A full selection on a debug branch staying ungated | `MQC_CMN_UNI_112126` |
| Notification transition detection | `MQC_CMN_UNI_112212` |
| Engine lists matching the roster | `MQC_CMN_UNI_112366` (section 8.5) |
| Every rostered engine's key offered where any engine can run live | `MQC_CMN_UNI_112367` (section 8.5.4) |
| Workflow syntax | `actionlint` in the `lint` job |

**The logic is tested in Python; the YAML is linted.** Putting decision logic in workflow expressions would move it somewhere no test can reach, which is why selection and gating live in `cmn/` and the workflows only call them.

### 10.1 A workflow change is linted before the push, on the machine that made it

Added 2026-10-24, after a push went red on one finding in a step written the
same day: `shellcheck`'s SC2012, counting files with `ls` piped into `wc`
inside the new publishing job. **Every other gate had passed and nothing
downstream ran**, so the cost of the finding was a full cycle for a line.

| | |
|---|---|
| What it reported | `gate-on-change.yml:174:9: shellcheck reported issue in this script: SC2012` |
| What it cost | The `unit`, `system` and `publish` jobs skipped behind the lint job, so the push measured nothing |
| Where the tool was | **Installed on the machine the change was written on**, as `actionlint` and `shellcheck` both |

**`actionlint` runs `shellcheck` over every `run:` block**, which is the half a
Python check cannot reach: `cmn/workflow_standards.py` reads what a step
*names* and has no opinion on the shell it writes. So a change to a workflow
is verified by running `actionlint` from the repository root, which takes under
a second and needs no arguments, and the suite's own workflow checks are run
as they always were.

**The earlier wording said actionlint "runs in CI"**, which is true and reads
as somebody else's job. It runs there as the gate; it runs here as the check.

| Changed | Run |
|---|---|
| A workflow definition | `actionlint`, then the precondition suite |
| Anything else | The precondition suite, as before |

---

## 11. The Split, As Built

Recorded 2026-09-23. `DESIGN.md` section 5.1 carries the boundary; this section carries what it changed about the pipeline, which is the part a split changes most.

| Repository | Workflows |
|---|---|
| Harness | The gate, both regression workflows, the probe, the live run, and the two diagnostic workflows |
| Cases | Its own gate and live run, each pinning a harness version |

**The fan-out is built rather than described.** An earlier version of this section named it as the capability a split would provide and did not exist here. `regress-consumers-on-merge.yml` is that capability, and section 3B carries it.

Two things stayed as designed. `probe-model-version-nightly.yml` belongs to the harness, since resolving a model version is adapter behaviour rather than a property of any case set. The two-ref diagnostic keeps `fixture_ref` and gains `harness_ref` and `cases_ref` on the case side, which is the arrangement section 6.4 approximated within one tree.

**The artifact contract needed no change at all.** Names already carry layer, engine and mode rather than anything repository-shaped, and a collector reading standard formats does not care how many repositories produced them. That is a consequence of naming the contract as formats rather than as an interface, and it is the one prediction here that survived contact unchanged.

---

## 12. Traceability

| Decision | Section |
|---|---|
| A1 fixtures on PR, live on schedule | §2, §8 |
| A3 engine funding and judge choice | §5.2 |
| A4 three observations | §5.4 |
| A6 engine and mode orthogonal | §5.2 |
| A7 rate limits skip, not fail | §5.4 |
| A14 change-triggered live runs | §4, §5.1 |
| B3 Python 3.14, single version | §3.1 |
