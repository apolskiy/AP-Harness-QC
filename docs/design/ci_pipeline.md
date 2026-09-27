<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# CI Pipeline Design

> **Parent:** `DESIGN.md` section 3.2.
> **Status:** Phase 2 design document, awaiting review before Phase 3.
> **Subject:** the GitHub Actions workflows: their triggers, jobs, secrets, artifacts and failure semantics.
> **Not in scope:** the CLI contract, specified in `cmn_verdict_and_cli.md` section 7; the gate sequence, normative in `framework-rules.md` section 1; selection rules, normative in `testing-standards.md` section 3.

---

## 1. What This Document Adds

The gates, the selection rules and the CLI already exist as specifications. What did not exist is the statement of **which workflow files hold them, what starts each one, and which of them can reach a credential.**

That last point is the reason this is a design document rather than a configuration detail. A1 decided that pull requests run without credentials, and that decision is only real if the workflow structure makes it true. A single workflow with conditional steps would put a secret reference in a file that pull requests execute, and the guarantee would rest on a conditional being correct forever.

---

## 2. Seven Workflows

Extended 2026-09-23. Four covered the gate, the probe, the live run and
diagnosis. Three more cover regression and failure triage, which the split and
the change-scoping rule between them made necessary.

| File | Starts on | Credentials | Emits durable record |
|---|---|---|---|
| `gate-on-change.yml` | Push, pull request, manual dispatch | None | Yes |
| `regress-harness-on-branch.yml` | Manual dispatch | None | Yes |
| `regress-consumers-on-merge.yml` | A green gate on `main` or `stabilization`, or manual dispatch | None | Yes |
| `probe-model-version-nightly.yml` | Manual dispatch. **Schedule withdrawn**, see 2.0.1 | Read-only model metadata | No |
| `evaluate-live-weekly.yml` | Manual dispatch. **Schedule withdrawn**, see 2.0.1 | Provider API keys | Yes |
| `diagnose-on-demand.yml` | Manual dispatch only | Optional | **No** |
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
| A cron that spends quota | Competes with corpus recording for the free tier's 20 requests per day per model (`OPEN_QUESTIONS.md` section 2.6) |
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

### 2.1 Workflow file naming

**`<verb>[-<subject>]-<cadence>.yml`.** The verb is what the workflow does, the subject narrows it when the verb alone is ambiguous, and the cadence is the trigger that fires without anyone asking.

| Part | Values in use | Rule |
|---|---|---|
| Verb | `gate`, `probe`, `evaluate`, `diagnose` | What this workflow is for. One word |
| Subject | `model-version`, `live` | Present only where the verb does not identify the workflow by itself |
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

**What this repository owes instead is proof that the instrument works**, and that is `MQC_CMN_SYS_20301` to `20303` inside Gate 3: the whole chain on a synthetic corpus, from the ingestion join through replay dispatch and the dual pass to a computed verdict, asserting it reaches **both** a green and a red. A harness that cannot report red about a failing model cannot be trusted when it reports green.

**`regress-harness-on-branch.yml` carried the same four steps** and they are removed for the same reason. `evaluate-live-weekly.yml` still carries them and is recorded in `OPEN_QUESTIONS.md` section 2.7, because what a harness-only live run should measure is a question about quota rather than about structure.

**Section 3.1.1 below describes the three-step graded job as the consumer runs it**, and its requirement of three separate JUnit files is a requirement on that pipeline.

#### 3.1.1 The graded job runs three steps, not one command

| Step | Gate | Command | Artifact |
|---|---|---|---|
| Evaluator | 4 | `pytest -m evaluator --engine <e> --mode replay` | `junit_mqc_eval.xml` |
| Tool | 5 | `pytest -m tool --engine <e> --mode replay` | `junit_mqc_tool.xml` |
| Security | 6 | `pytest -m sec --engine <e> --mode replay` | `junit_mqc_sec.xml` |

**Combining them into one invocation would emit one JUnit file where `framework-rules.md` section 1 requires three**, and would erase the separation that makes `SEC` its own suite. That separation is not cosmetic: `SEC` is exempt from the distribution ceilings precisely so security coverage never competes with functional coverage for a budget, and a single merged result set makes the exemption unverifiable from the artifacts.

#### 3.1.2 Every job runs on both operating systems

`ubuntu-latest` and `windows-latest`, as **separate jobs with `fail-fast: false`**, for the reason B9 gives for engines: the default would let one platform's failure cancel the other, and a collapsed job lets a pass on one platform mask a failure on the other.

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

**Alternating platforms between runs is precluded**, per A18 and `extensibility_standard.md` section 7. A gated run executes every supported platform; a scheme that runs one platform on one commit and the other on the next is forbidden rather than merely unchosen, because it cannot separate a platform difference from the change between the two runs.

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

## 3C. Branch Topology, And Which Harness A Case Set Runs Against

Added 2026-09-23. Two repositories each carrying branches means a run is defined
by a **pair** of refs, and the pairing has to be decided rather than assumed.

| Repository | Branch | Holds |
|---|---|---|
| `AP-Harness-QC` | `main` | The harness the main regression runs on, and what test development is written against |
| `AP-Harness-QC` | `stabilization` | Harness stabilization, and the extensions new cases need before they can exist |
| `AP-Harness-QC` | Feature branches | One harness change each |
| `AP-Model-QC` | `main` | Every case that works |
| `AP-Model-QC` | `stabilization` | Cases being stabilized before they merge to `main` |
| `AP-Model-QC` | Expansion branches | One coverage expansion each |

**The pairing follows from what each branch is for**, and only one pairing is
non-obvious. A case expansion needing no new harness capability pairs with
harness `main`, because that is what its cases run against once merged. A case
expansion **requiring a harness extension** pairs with harness `stabilization`,
because the capability it depends on exists nowhere else yet.

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

Added 2026-09-24, superseding the long-lived `stabilization` branch described
above. **`main` is the master branch.** Every other branch is cut from it,
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
expand-10428-09-24-2026
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
| Case identifier | `10428`, `11143` | **Shape and existence** |
| Release | `v1.2.0` | Shape only |

**The case-identifier kind is the one that earns its keep.** A branch claiming
to fix `10428` where no such case is inventoried is a typo, and the gate reports
it on the first push rather than at review. This project has been bitten by an
identifier that bound to nothing often enough to check the cheap instances.

**A ticket is checked for shape and never for existence**, because reaching an
issue tracker from a precondition would put a network call in the one layer
that is required to run without one, and would make the gate fail when somebody
else's service is down.

**One referent per working branch.** Work spanning three cases takes a ticket
covering them, because a branch naming three things is a branch doing three
things.

##### The integration kind may omit it, and usually should

```
stabilization-09-24-2026
stabilization-v1.2.0-09-24-2026
```

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
mechanical rather than a matter of judgement: `MQC_CMN_UNI_11152` accepts a
bare stamp for `stabilization` and `11144` refuses one for every other kind.

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

**A probe failure is not a test failure.** It means the detector is broken, which is our defect, and the weekly run still covers the period regardless. Treating it as a red suite would be the same category error the `QC_HARNESS_*` family exists to prevent.

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

**A first run on a branch has no previous conclusion**, which is not a transition. The comparison is therefore stated at that boundary and covered by `MQC_CMN_UNI_10175`. This is the same shape as the probe's absent baseline in section 4: a missing prior value means there is nothing to compare, not that something changed.

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

A stale hash means the request composition changed between the two checkpoints, which is exactly what the third row of the table is asking. The run therefore reports staleness per fixture as a diagnostic finding and continues, rather than treating it as a harness defect and stopping. `MQC_EXE_UNI_10239` states this, and it is the only context in which a stale fixture is not a problem.

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
| Selection logic correctness | `MQC_CMN_UNI_10162` through `10165` |
| Debug exclusion | `MQC_CMN_UNI_10166`, `10167` |
| Verdict gating on selection mode | `MQC_CMN_UNI_10168` through `10170` |
| A full selection on a debug branch staying ungated | `MQC_CMN_UNI_10174` |
| Notification transition detection | `MQC_CMN_UNI_10175` |
| Workflow syntax | `actionlint` in the `lint` job |

**The logic is tested in Python; the YAML is linted.** Putting decision logic in workflow expressions would move it somewhere no test can reach, which is why selection and gating live in `cmn/` and the workflows only call them.

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
