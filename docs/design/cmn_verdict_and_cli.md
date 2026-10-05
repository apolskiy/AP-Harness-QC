<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# CMN: Verdict Computation, CLI and Configuration, Design

> **Parent:** `DESIGN.md` section 3.2. Read the normative references in section 3.1 first.
> **Status:** Phase 2 design document, awaiting review before Phase 3. Thereafter it is a **living specification**: where implementation improves on it, it is amended in the same change as the code.
> **Subject:** the **harness**. This module decides every run's outcome, so an error here misreports every result the project produces.
> **Authority:** decisions trace to `phase0_project_ambiguities.md` and `test_taxonomy.md` §7.
> **Phase 1:** discharged by the project-level Phase 0. This module raised no fresh ambiguity beyond the decisions already recorded there.
> **Contract:** per A12 this is a specification implementation is evaluated against. Where it is silent, the implementation must ask rather than choose.

---

## 1. Why This Module Exists Before The Others

`CMN` computes the verdict. Every other tier produces observations; this one decides what they mean.

That makes it the **only module whose defects are invisible in its own output**. A broken loader raises; a broken adapter times out; a broken verdict computer returns `green` and is believed. A suite that reports success incorrectly is worse than one that fails, because nothing prompts anyone to look.

It is also the **most testable component in the system**: the verdict is a pure function of an observation set, so every rule and every boundary is exercisable with synthetic data and no network, no engine and no quota.

---

## 2. Scope

**In scope:** CLI argument parsing, configuration loading, verdict computation, result metadata emission, RTM integrity checks.

**Out of scope:** ingestion (Tier 1), dispatch (Tier 2), judging (Tier 3). `CMN` knows about outcomes, never about how they were produced.

---

## 3. The Observation Record

**Field definitions live in `test_taxonomy.md` section 9, the single normative list.** This section states only what verdict computation does with them, so the two cannot drift as they previously had.

Verdict computation reads:

| Field | Used for |
|---|---|
| `layer` | Precondition or graded, and distribution exemption |
| `priority`, `priority_conditions` | The P0 and P1 gate, and demotion ordering |
| `outcome` | Pass rate and the priority gate |
| `skip_reason` | Three kinds of skip counted differently (section 4.4) |
| `gated` | An ungated artifact yields no verdict (section 7.1.1) |
| `effective_thresholds` | The standard applied, so a verdict is recomputable from stored artifacts |

The remaining fields are carried for the durable record and for diagnosis rather than for the verdict.

**Observations are assembled by the reporting hook**, not emitted by tiers. Tier 3 never receives `priority`, so it cannot produce a complete observation; the orchestrating test holds the case metadata and the hook merges it with the tier results. See `extensibility_standard.md` section 2.1.

## 4. Verdict Computation

### 4.1 It is a pure function

`verdict(observations, config, as_of_date) -> Verdict`

No clock, no filesystem, no environment. **The evaluation date is injected, never read from the system clock**: quarantine expiry depends on it, and a function that calls `now()` cannot be tested at a boundary without manipulating the machine.

This is the property that makes every rule below exercisable with synthetic observation sets.

### 4.2 Preconditions gate everything

`UNI` and `SYS` are evaluated first and separately:

* **100% pass required, zero skips permitted.** A unit test has nothing external to block it, so a skip means something is broken.
* **On failure the graded layers are not executed.** Their observations do not exist, and the verdict reports `PRECONDITION_FAILED` rather than computing graded rules against an empty set.

### 4.3 Graded rules

Evaluated in full: **not short-circuited**. See §4.7.

| # | Rule | Verdict |
|---|---|---|
| V1 | Any P0 or P1 observation not passing | Red |
| V2 | Overall pass rate below 90% | Red |
| V3 | Total skips above 20% | Red |
| V4 | P0/P1 skips above 10% | Red |
| V5 | Any quarantine entry expired as of `as_of_date`, by model change or the 21-day window | Red |
| V6 | Zero graded observations | Red: §4.5 |
| V7 | P0 share of the corpus above its ceiling | Red: §4.4 |
| V8 | P1 share above its ceiling | Red: §4.4 |
| V9 | Combined P0 and P1 share above its ceiling | Red: §4.4 |
| - | None of the above | Green |

**V7 to V9 were absent from this table until 2026-09-26 while living in the code**, and that omission had a consequence: sections 4.9.1 and 4.9.2 were written labelled `V6` and `V7`, numbers already taken. The soundness conditions those sections describe are **not verdict rules at all** and are no longer numbered as though they were — see §4.9.

### 4.4 Denominators and exclusions

Each metric uses a different denominator, and the distribution one is load-bearing (§4.2.2 of the taxonomy).

| Metric | Denominator | Excluded |
|---|---|---|
| Priority distribution | Unique (task × rubric) case definitions | `SEC` layer entirely |
| Pass rate (V2) | Executions | Quarantined cases |
| Skip rate (V3, V4) | Observations | `unsupported` pairs, `dependency` skips |

**Why dependency skips are excluded:** a foundational P0 failure cascades into many skips. Counting them would breach V3 as well, adding a derived failure on top of the real one and misdirecting diagnosis toward the environment. The run is already red from V1.

**Why unsupported pairs are excluded:** a declared capability gap is not an environmental failure, and leaving it in the denominator would trip V3 for a reason that is not a defect.

### 4.5 Empty and degenerate inputs

These are specified because they are where verdict computers are wrong in practice.

| Input | Verdict | Reason |
|---|---|---|
| Zero observations | **Red**, `NOTHING_MEASURED` | A run that measured nothing must never report green |
| Zero graded observations, preconditions passed | **Red**, `NOTHING_MEASURED` | Same |
| All graded cases quarantined | **Red**, `NOTHING_MEASURED` | Pass-rate denominator is zero; the suite verified nothing |
| All pairs unsupported | **Red**, `NOTHING_MEASURED` | Skip denominator is zero |
| Fewer than 30 graded case definitions | Distribution check reports counts and **returns no verdict**; other rules still apply | Below 30, one case moves the share by over 3% |

**No metric divides without first testing its denominator for zero.** A zero denominator means the question is unanswerable, which is never the same as the answer being "fine".

### 4.6 Quarantine

Revised 2026-10-02. An entry carries a case identifier, a reason, the date it
was quarantined, the model it was observed against, and an optional ticket
reference.

* Quarantined cases are excluded from the pass-rate denominator, never deleted
  from the suite.
* They are listed in the report.
* **An expired entry fails the run (V5).** Without expiry, quarantine becomes
  where failures go to be forgotten and the 90% floor stops meaning anything,
  because everything inconvenient has left the denominator.

#### 4.6.1 Why expiry exists here, and what it substitutes for

**Quarantine is not normally a place failures are forgotten, and expiry is not
normally needed.** In a project with a tracking system, a quarantined case is
linked to a ticket: the entry leaves quarantine when the bug is fixed, or stays
indefinitely on a recorded decision not to fix. **The ticket governs the
entry**, and if the problem returns the case catches it again, so nothing was
forgotten.

Two things remove that governor here:

| | Consequence |
|---|---|
| This demo runs no tracking system | Nothing outside the file decides when an entry should leave |
| **We neither test nor control the release of the models under test** | A fix is not ours to make or to observe, so "fixed" is not a state we can detect |

**Expiry is the workaround for both**, and naming it a workaround is the honest
description: it approximates a governor we do not have.

#### 4.6.2 The model is the trigger, and the calendar is the backstop

Section 4.1's premise is already stated for every comparison this project makes:
the model did not change. `mixed_model_engines` enforces it within a run.

**A quarantine entry is a comparison claim**: this case's failure is a known,
accepted finding about one model. **When the resolved model changes, the claim's
premise is gone** and the entry says nothing about what is now running. So the
primary trigger is not a date at all:

| Trigger | Fires when |
|---|---|
| **Model change** | The run's resolved model differs from the entry's `observed_model` |
| Time box | `as_of - quarantined_on >= 21 days` |

**The calendar is the backstop, not the rule.** It catches a model that does not
move while nobody looks at the entry again. The two together are the same pair
the live cadence already uses, weekly **or** the model updated, so quarantine
expiry and re-evaluation stay in step instead of running on unrelated clocks.

**Twenty-one days, and not a calendar month.** The scheduled cadence is weekly,
so 21 days is three scheduled runs of grace and still two if one is missed for
quota or a holiday. It is a multiple of seven, so expiry never drifts relative
to the run day; 30 is not, and an entry would lapse on a different weekday each
cycle. Twenty-eight would be the same argument with four runs of grace.

**Expired at the window, not after it.** `as_of - quarantined_on >= 21` makes
day 21 the first failing day, so "valid for 21 days" reads literally. Named at
the boundary exactly, per `testing-standards.md` section 3.2, by `112012`,
which already owned this boundary when it was a fixed expiry date and now
parametrises days 19 through 22. **A second boundary case was inventoried for
this and withdrawn**: two cases making one claim is the shape section 10.10.1
records, and extending the case that owns the boundary is what that section
says to do instead.

**The model comes from the run's own observations, which is what keeps
`verdict()` pure.** Every observation carries `resolved_model` (A8), so the
function needs no new input to answer "what is running now":

| The run's observations report | The model trigger |
|---|---|
| Exactly one resolved model | Compared against each entry's `observed_model` |
| None, as a run that recorded none | Cannot be evaluated; the window alone applies |
| **Several**, a mixed corpus | Cannot be evaluated; the window alone applies |

**A mixed corpus is deliberately not expired on model change.** Which of two
models an entry should be compared against has no answer, and guessing would
expire entries on an arbitrary pick. `mixed_model_engines` already reports that
run as mixed, which is the finding; silently expiring quarantine on top of it
would attach a second consequence to one cause.

**The window lives in `Thresholds` as `quarantine_window_days`**, so it is
carried into `effective_thresholds` and a stored verdict stays recomputable.
That is the same reason the pass floor is there rather than a constant: section
4.6.2 gives the reasoning for 21, and recording it means a verdict read later
does not depend on what the constant happens to be then.


#### 4.6.3 One file per engine, and an absent file is the default

**Quarantine is per engine**, because a finding is about one model on one
provider and an entry carries the model it was observed against. The files
follow the data:

```
config/quarantine/<engine>.yaml
```

**An absent file is an empty quarantine**, which is the default state and needs
no file to say so. That is the general rule for this mechanism: **quarantine is
assumed empty and is processed only when it holds something.** A run whose
engine has no file does no expiry work and does not consult the evaluation date.

| | Why |
|---|---|
| Per file rather than one keyed by engine | The per-engine state is readable and diffable on its own, and adding an engine adds a file rather than editing a shared one |
| Absent means empty | The default costs nothing to express, and an empty list in a file is the same statement with a file to maintain |
| **The candidate engine, not the judge** | An entry records a finding about the model under test. The judge is not under test (section 6.2 of `test_taxonomy.md`) |

#### 4.6.4 An undated entry is our defect, and is never red

An entry missing its `quarantined_on` or its `observed_model` **cannot be
evaluated**: there is nothing to measure the window against and nothing to
compare the model to.

**It is reported as `QC_HARNESS_QUARANTINE_UNCONFIRMED` and the run is not made
red by it.** `framework-rules.md` section 4 is explicit that `QC_HARNESS_*`
means our code or infrastructure broke and resolves to skip or broken, **never
fail**. An undated entry is the quarantine mechanism failing, not a finding
about a model, and failing the run for it would attribute our bookkeeping defect
to the model under test. That is the same error the consumer-regression gate
exists to avoid.

**The entry is still honoured while unconfirmed.** Dropping the exclusion would
let an already-accepted failure fail the run, which is the opposite of what the
entry records. So the case stays out of the denominator and the condition is
carried in the record.

**What stops it drifting forever** is that it is loud rather than fatal: the
count of unconfirmed entries is recorded in run metadata, so an entry that is
never confirmed is visible in every run that carries it, and the remedy is the
maintenance tool below rather than a red gate.

#### 4.6.5 The gate reads and a tool writes, because the verdict is pure

Confirming an entry means **re-running the case and writing a date into a
tracked file**. Section 4.1 makes the verdict a pure function of observations,
configuration and an injected date: no clock, no filesystem, no environment.

| Does | Where |
|---|---|
| Reads quarantine, computes expiry, reports expired and unconfirmed entries. **Writes nothing** | `verdict()`, inside the gate |
| Re-runs the case, stamps `quarantined_on` and `observed_model` when it still fails, removes the entry when it passes | A maintenance tool, invoked deliberately |

**A gate that rewrote tracked configuration would also race.** Platform and
band legs run in parallel by design, and two legs writing one quarantine file
is a lost update with a verdict attached to it.

**The tool re-observes under the escalation policy rather than once.** Section
4.9.2 sets three observations with two more on a single disagreement; removing
an entry on one green observation would un-quarantine a flaky case on its lucky
run, which is precisely the reading the escalation exists to prevent.

#### 4.6.6 The quarantine hash is recorded, because the verdict is uninterpretable without it

Quarantine changes the pass-rate denominator, so a stored pass rate cannot be
read without knowing which entries were excluded when it was computed. That is
the argument `112105` already makes for recording the thresholds: **a stored
result whose standard cannot be recovered is uninterpretable.**

Run metadata therefore carries a **`quarantine_hash`** beside `rule_set_hash`
and the resolved thresholds, over the entries the run consulted.

| | |
|---|---|
| What it detects | That the entries behind a recorded verdict are not the entries present now, whether changed deliberately or by accident |
| What it does not do | Prevent a change. It makes a verdict attributable to an exact quarantine state, which is what an audit needs |
| Precedent | `rule_set_hash`, for the same reason, and `QC_HARNESS_FIXTURE_STALE`, where a stored request hash no longer matching means replaying would answer a different question |
| Only the entries consulted | Hashing an engine that did not participate would imply it did. A run names one candidate engine |

**Over the parsed entries, not the file's bytes**, which is how `rule_set_hash`
already works and for the reason given there: hashing what was parsed means the
digest moves when the claim moves. A reworded comment or a reordered file is not
a different quarantine, and a digest that moved for either would cry wolf until
nobody read it. **Canonicalised with keys sorted and content normalised to LF**,
so it does not depend on how a file was checked out (`code-style.md` section 8).

**What this deliberately does not catch**: an edit to a comment, or to anything
outside the fields an entry is made of. The claim is the entries, so the hash is
the entries.

**An absent file hashes to the empty string rather than to the digest of
nothing**, exactly as `rule_set_hash` returns empty for a run with no corpus, so
"this engine has no quarantine" reads as the default state and not as a
suspicious zero.

#### 4.6.7 The ticket reference is inert, and that is not the defect section 7.1.0.1 records

An entry may carry a `ticket`: a tracker identifier or a URL. **Nothing reads it
and nothing is expected to**, pending a tracking system this demo does not run.

**This is deliberately not the shape of `--extra-columns` or `--judge-engine`.**
Those were defects because each **claimed an effect it did not have**: a
recorded column policy that was never applied, a named judge that never graded.
A ticket reference claims no behaviour at all; it carries the human context an
entry needs and says so.

**It is validated even so.** A present value must be a well-formed tracker
reference or an absolute URL, because an annotation nothing reads is exactly
where a typo survives indefinitely, and the point of the field is that somebody
can follow it later.

#### 4.6.9 The data is the consumer's, and this repository ships none of it

Established 2026-10-02, while designing the maintenance tool. **Quarantine is
not harness data at all**, and the file this repository shipped was a mistake
rather than an empty default.

| | |
|---|---|
| Quarantine excludes from the **pass-rate** denominator | `_build_population` filters `graded` alone |
| A precondition cannot be quarantined | It must pass 100 percent with zero skips, so excluding it from a denominator it is not in changes nothing |
| **This repository holds no graded case** | `ci_pipeline.md` section 3B.2 |
| An entry names a case identifier | Which is the case repository's data |

So a quarantine entry here could never be about anything this repository owns.
`config/quarantine.yaml` shipped carrying `quarantine: []` and **is deleted**:
after section 4.6.3 made an absent file the empty default, it was a file nothing
read, which is the shape section 7.1.0.1 exists to record. The directory lives
in the consumer, at `config/quarantine/<engine>.yaml`.

**This is the `--golden-rules` boundary applied again.** The harness owns the
mechanism, the schema, the loader, `V5` and the digest; the consumer owns the
data and passes its own directory. `CLAUDE.md` states the rule the other way
round and it binds here: a check that reads the case repository's files is a
boundary violation, and so is shipping a stub of its data.

#### 4.6.10 Confirming an entry splits at the same boundary

Section 4.6.5 names a maintenance tool that re-runs a case and stamps or drops
its entry. **Re-running a case needs the cases**, so the tool cannot live here.
What lives here is the decision, as a pure function:

```
cmn.quarantine.reconcile(entries, outcomes, as_of, resolved_model)
        -> the updated entries, and one action per entry
```

| What the run observed | Action |
|---|---|
| Every observation passed | **Drop the entry.** The finding no longer reproduces |
| Any observation failed | **Stamp** `quarantined_on` and `observed_model` |
| Nothing observed for that case | **Keep unchanged**, and report it. Nothing was measured, so nothing is decided |

**The third row is why this returns actions and not just entries.** A case that
was not run looks identical to a case that passed if the only output is the
surviving entries, and the difference is between "fixed" and "not asked".

**Any failure re-stamps rather than a majority.** Section 4.9.1 keeps the
within-case rule binary: a case whose observations disagree has a finding, and
a majority vote would discard the disagreement the repeats exist to produce.

**Pure, for the reason section 4.1 gives.** The decision is a function of
observations, a date and a model, so it is testable without running a case or
writing a file; the consumer's tool does both.

#### 4.6.11 A pass states what it excluded, and a blocking band loudly

Added 2026-10-03 at the project owner's instruction. **A green run reported
nothing about its quarantine**: `verdict_tool` logged breaches on a red and
nothing at all on a pass, so a run that excluded a release blocker and passed
was indistinguishable from a run that excluded nothing.

**Quarantine removes a case from the pass-rate denominator**, which is V2. That
makes a green "green over what was measured" rather than "green over
everything", and a result that does not say which is which invites the second
reading.

#### 4.6.11.1 Quarantine exempts V2 and never V1, which is a stronger answer

**Corrected 2026-10-03, by probing rather than by reading the code.** This
section first said a green could hide an accepted release blocker. It cannot:
`_rule_v1` reads `population.graded`, and `_build_population` filters
quarantined cases only out of `executions`. So **"any P0 or P1 observation not
passing fails the run" is unconditional**, and a failing blocker cannot be
quarantined into a pass.

| Rule | Reads | A quarantined failing case |
|---|---|---|
| V1, the priority gate | `graded`, every graded observation | **Still fails the run** |
| V2, the pass floor | `executions`, quarantine filtered out | Leaves the denominator |

**That is the right scope and worth stating as a decision.** Quarantine accepts
a finding; it does not accept a release blocker. If it exempted V1, an accepted
P0 would produce a green, which is "where failures go to be forgotten" at the
one severity where it matters most.

**It also bounds what the triage can do.** A gate reporting a failing P0 or P1
cannot be made green by quarantining it. That is a structural consequence
rather than a threshold to adjust, and a run carrying such a finding is red
until the finding is fixed, the case is corrected, or the band is reconsidered
on the record.

#### 4.6.11.2 So what a blocking band in a *passing* run means

Given V1, a quarantined P0 or P1 appearing in a green run cannot be a failing
blocker. It is one of two things, and both are worth saying:

| | What it means | What to do |
|---|---|---|
| The case **passed** this run | The entry is stale: the finding no longer reproduces | `reconcile` drops it (section 4.6.10) |
| The case **skipped** | The exclusion is doing nothing, and a skip is already counted elsewhere | Read the skip reason, not the entry |

**So the warning is still earned**, with a different reason than this section
first gave: a blocking-band entry in a green run is either stale or masking a
skip, and neither is visible otherwise.

**This is the qualification principle the project already applies elsewhere.** A
manual selection yields **no verdict** rather than a misleading green, and
`gated: false` marks a run whose result is not durable. Both exist because a
green that needs a caveat has to carry it. An excluded blocker is that kind of
caveat.

**The priority comes from the observations, not from the entry.** A quarantine
entry names a case; the case's priority is a property of the case, and
`_build_population` keeps quarantined cases in `graded` while filtering them
only out of `executions`. So the band is already recoverable and the quarantine
file needs no new field.

**A quarantined case with no observations reports no band**, because nothing ran
it: that is the "not asked" state section 4.6.10 keeps separate from "fixed",
and inventing a band for it would assert something the run did not measure.

**It does not change the verdict.** Quarantine exists to accept a finding, so
reporting is the remedy and gating would be a second mechanism contradicting
the first. What changes is that the acceptance is visible in the result rather
than only in the file.

#### 4.6.8 Three extractions the rework forced, and one duplication it exposed

Reworking the model took three modules past the thousand-line ceiling, which
Gate 1 enforces by exit code. The split follows the precedent
`mqc_uni_instrument.md` records for `mqc_uni_corpus.py` on 2026-10-01: extract
the subject, not an arbitrary half.

| New | Holds | Relieved |
|---|---|---|
| `cmn/quarantine.py` | The entry and the window it is measured against | `cmn/verdict.py`, 1045 to 978 |
| `tests/cmn/mqc_uni_quarantine.py` | Every quarantine case, including `112042` moved from the CLI module where it was never about the CLI | `mqc_uni_verdict.py` 1030 to 683, `mqc_uni_cli.py` 1054 to 964 |
| `tests/cmn/verdict_support.py` | The observations, suites and artifacts the three share | All three |

**`V5` stays with the other verdict rules.** The rule registry is what makes a
rule a rule, so moving one out of the registry's module to sit beside its data
would split the registry instead of the subject.

**The support module exists because the extraction created a duplication.**
Copying the helpers into the new test module left three copies of
`passing_suite` and two of the gated artifact, which pylint's duplicate-code
check reported. **A duplicated helper is worse than a long module**: a case
comparing against a stale copy of a passing suite reports about the copy, and
nothing says which copy is the real one. The name sits outside `pytest.ini`'s
`mqc_*.py` collection pattern, the same arrangement `AP-Model-QC`'s
`graded_support.py` uses.

**Renaming the shared artifact builder was not cosmetic.** Imported as
`artifact`, it was shadowed inside every case that bound a local `artifact`,
and the failure was an `UnboundLocalError` at the call rather than anything a
reader would attribute to the import. It is `gated_artifact`, which also says
what it builds.

**One finding came from pylint and not from the suite.** A removed `typing.Any`
import left an annotation referring to a name that no longer existed, and the
suite passed: on 3.14 an annotation is evaluated lazily (PEP 649), so nothing
read it. `code-style.md` section 2.1 records lazy annotations as the reason the
`__future__` import is prohibited, and this is the cost of the same mechanism:
a broken annotation is invisible at runtime and caught only statically.

### 4.7 All breached rules are reported, not the first

The verdict is red if any rule fires, but the result carries **every** rule that fired.

Short-circuiting would mean fixing V1 and discovering V3 on the next run, then V4 on the one after. For a suite whose live runs are scheduled rather than on demand, each rediscovery costs a cycle.

### 4.8 Red does not always mean blocked

| Run | Fixtures | Red means | Blocks a merge? |
|---|---|---|---|
| Pull request | Frozen | Our code changed a frozen outcome | **Yes** |
| Scheduled | Live | The model regressed | No: an alert |

The verdict function does not know which it is running in. It returns red with reasons; **the workflow decides whether red blocks.** Putting that knowledge in the verdict function would couple a pure computation to CI topology.

### 4.9 Inconsistency is a finding, and enough of it unsounds the run

Added 2026-09-25, implementing A4.1.

Each graded case is observed **three times** and the observations are compared.
Two rules follow, at two levels, because the user's reasoning has two halves:
inconsistency is a defect in the model, **and** it undermines every other
result measured from that model.

#### 4.9.1 A case whose observations disagree is a finding

**Not a verdict rule and not numbered.** This is how the observation is recorded, before any rule reads it.

Where the observations of one case do not agree on outcome, the case is
recorded as **failed** with `QC_LLM_INCONSISTENT`, whatever the individual
outcomes were.

**Two passes and a fail is not a pass**, and it is not a flake to be retried
away. It is a measurement: this model does not reliably do this. Taking the
majority would discard exactly the finding the repeats exist to produce.

**It is a model finding, so it is `QC_LLM_*`.** Nothing about our
infrastructure varied: same request, same engine, same commit.

#### 4.9.2 Enough inconsistency makes the run unsound

**A soundness condition, reported as `RUN_UNSOUND`**, not a numbered verdict rule: the numbered rules decide red against green and exit 1, and this decides whether the run is worth reading at all.

A run whose inconsistency rate exceeds `inconsistency_ceiling` exits **3**,
alongside the other soundness failures, rather than exiting 1.

| Exit | Says |
|---|---|
| 1 | The model was measured and something failed |
| **3** | **The run cannot be trusted to have measured anything** |

That is the distinction the user drew: an inconsistent model does not merely
score badly, it "makes running them questionable". A single-sample green from
such a model is a sample from a distribution nobody characterised, so reporting
the run's other numbers as findings would overstate them.

**The ceiling defaults to 0.10**, matching `priority_skip_ceiling` rather than
being invented: both answer "how much of this can a run carry before its
conclusions stop holding", and there is no evidence yet for a different number.
**It is configured rather than fixed**, and the first live corpus is what will
say whether 0.10 is right.

#### 4.9.2.1 The ceiling is 0.20, and a disagreement earns two more observations

Decided 2026-10-01 by the project owner.

**Two rates live here and only one moved.** The distinction is worth stating
because the question that produced this decision could have meant either.

| | Measures | Shape | Decision |
|---|---|---|---|
| `inconsistent_cases` | Whether one case's observations disagree | Binary, any disagreement | **Unchanged** |
| `inconsistency_ceiling` | What share of measured cases disagree | A rate over the suite | **0.10 to 0.20** |

**The binary rule stays, and section 4.9.1 is why.** A verdict that disagrees is
unreliable whatever share of the time it does so, and taking a majority would
discard the finding the repeats exist to produce. The owner's phrasing was that
verdicts disagreeing at least a tenth of the time are not reliable verdicts;
the binary rule is stricter than that and deliberately so.

**0.10 was matched to `priority_skip_ceiling` and never derived.** 0.20 is the
owner's judgement that a suite carrying a fifth of its cases as wobbling has
still measured something, while one carrying a tenth plainly has. The ceiling is
a statement about the **run**, not about a case.

**Three observations stay the default, and two more are taken only where one
disagreed.** This is the owner's correction to a flat five, and it is the better
design for a reason worth stating: a flat five pays for precision on every case
in order to get it on the few that need it.

| After three | Disagreement reads | Escalate? | Why |
|---|---|---|---|
| 3 agree | 0 percent | No | Nothing to refine |
| **1 disagrees** | **33 percent** | **Yes, two more** | 33 is above the ceiling and may not be the real rate |
| 2 disagree | 67 percent | No | Already established far above any ceiling |
| 3 disagree | 100 percent | No | As above |

**What the escalation buys is the severity, not the verdict.** The case is
inconsistent either way: the binary rule above does not soften, and the owner's
standard is that a verdict disagreeing a tenth of the time is already
unreliable, which one in five is. What changes is the number in the record. One
in three says "somewhere between a fifth and a half"; one in five says a fifth,
and three in five says three fifths, **and a model wobbling a fifth of the time
is a different finding from one wobbling three fifths of the time** even though
both fail.

**So escalation is a measurement, and it is why the two observations are worth
dispatching.** Spending them on a case that already agreed three times would buy
a more precise zero.

| | Dispatches added per engine | Cost across three engines |
|---|---|---|
| Flat five, considered | 138 | about 1.82 USD |
| **Three, escalating on one**, decided | **2 per wobbling case** | **a few cents at present rates** |

**Existing fixtures stay valid.** `FixtureKey` carries the observation index, so
an escalation adds indices 3 and 4 and invalidates nothing; `--fill-gaps` records
only what is absent. A case that agreed three times is never asked again, so the
corpus does not grow where it has nothing to learn.

**And what a score does inside a passing band is still only noted.** The owner's
ordering is explicit: a score moving within a band interests us less than a
failing score, and far less than a score crossing from passing to failing.
Section 4.9.4 already records `score_spread` and gates nothing on it, which is
that ordering already implemented; a verdict crossing the threshold is a verdict
disagreement and the machinery above already carries it.

#### 4.9.2.2 Where the escalation rule lives, and who calls it

The rule is a measurement policy, so it belongs to the harness beside the
ceiling it serves: `cmn.observations.further_observations` takes the outcomes
seen so far and returns how many more to take. **The consumer calls it and
decides nothing**, which is the boundary `AP-Model-QC` `CLAUDE.md` states as the
cases owning no harness code.

| | Owns |
|---|---|
| Harness | The rule: how many more observations a pattern of outcomes earns |
| Consumer | The loop: dispatching them and collecting the results |

**Two, and not "until it is certain".** Two more takes a case from three
observations to five, where one disagreement reads as a fifth. A rule that kept
sampling until some confidence was reached would spend unboundedly on exactly
the cases that are hardest to characterise, and the quota is the binding
constraint on every recording run this project does.

**It escalates once.** Five observations with one disagreement are not escalated
to ten, because the decision at 4.9.2.1 is that a fifth is a legible number and
not that a tenth is needed. A second escalation is a later decision with its own
arithmetic, not a loop this function runs.

**Zero for a single observation.** One sample cannot disagree with itself, so
there is nothing to refine, which is the same answer `consistent` gives for the
same reason.

`MQC_CMN_UNI_112036` covers the rule and `MQC_CAS_UNI_115207` covers the loop
calling it, which is the division above restated as two cases: a rule nothing
calls and a loop that decides for itself are the two ways this could be wrong.

#### 4.9.3 Consistency compares verdicts, never responses to each other

Corrected 2026-09-26. **An earlier version of this section claimed the spread of
scores was compared through `observation_variance` and said "this is it" of a
function that had no caller.** It did not, and that is the failure this project
treats as worse than silence: a design claiming enforcement it lacks stops a
reader looking.

##### What is compared, and why it needs no judge

Each observation is evaluated independently against **the same fixed rules**,
and then the **verdicts** are compared. Nothing ever compares one response to
another.

| Family | The fixed reference | Free to vary |
|---|---|---|
| `SEC` | Canary absent, assigned task performed | Every word of the refusal |
| `TOOL` | Which tools were invoked | All prose around the call |
| `EVAL` | The score clears the rubric threshold | Wording, structure, length |

**That is what makes it judge-free.** Three responses worded and formatted
differently, all satisfying the rules, are consistent by construction: the
rules are the reference point and the responses are measured against them
rather than against each other.

##### The design that would need a judge, and why it is not this one

Comparing responses **to each other** for semantic equivalence is a different
measurement. It asks whether the model *said the same thing* rather than whether
it *satisfied the rules*, and settling it requires a judge, a rubric for
equivalence, and then something to say whether that judge is right. **That is
the regress A3.2 declined**, arriving from a different direction.

Anchoring every observation to the rules avoids it entirely.

#### 4.9.4 A score can move inside the passing band, and that is recorded

Three observations scoring 4, 4 and 5 against a threshold of 4 all pass, so
`inconsistent_cases` finds nothing. **The spread is real and the verdict cannot
see it**, which is a gap in what the consistency check reports rather than an error in what it
decides.

`score_spread` records it per case, and the verdict carries it.

| | |
|---|---|
| Recorded | The range between the highest and lowest judged score |
| **Not gated** | A spread breaches nothing and changes no exit code |
| Absent | Where a case has fewer than two scores |

**Recorded rather than gated, deliberately.** The case passed on every
observation, which is what the threshold was set to decide, and turning a spread
into a failure would need a second threshold nobody has evidence for. The first
recorded corpus is what could supply one.

**Zero is recorded and absence is not.** A spread of zero says the judge agreed
with itself across three observations, which is a result; a case observed once
has no range, and reporting zero for it would be indistinguishable from
agreement.

**The range is computed in `cmn` rather than borrowed from
`evaluation.calibration`.** `cmn` imports nothing from `evaluation`, and
reaching for `observation_variance` would invert the dependency the tiers hold.
So `observation_variance` **still has no production caller**, and 4.9.3 no longer
claims otherwise.

#### 4.9.5 Multi-prompt consistency is a different instrument

Raised 2026-09-26 and recorded rather than built.

Repeat observations of **one** prompt are what A4.1 decided. Repeating a
*conversation* would measure something else, and the cost is not the repetition:

| Needed | Why |
|---|---|
| Conversation state | Seeded, advanced and compared across observations |
| A rubric for a dialogue | A turn is judged in the light of the turns before it |
| Recalibration | Exemplars are single responses, so the known-correct anchor does not transfer |

**So it is an expansion and not a setting.** The test plan section 9.6.1 states
the present boundary where it is most likely to be misread: the clarification
family measures that the model asks, and nothing measures what follows.

**Settled 2026-10-01: the boundary is the demonstration's scope, not a defect.**
The project owner's statement of it: this suite is single prompt, with multiple
possible conditions, taking one reply or refusal from the evaluation engine,
which is then verified against deterministic parameters and judged by a separate
AI judge. It is potentially expandable to multi-prompt scenarios **and that
expansion is the harness's, not the corpus's.**

So nothing here is missing. A multi-prompt suite would need conversation state
seeded and compared, a rubric judging a turn in the light of the turns before
it, and recalibration because exemplars are single responses. Those are harness
capabilities, and until they exist a multi-prompt case would have nothing to run
on.

#### 4.9.6 One corpus, one model, and the quota made that worth checking

Added 2026-09-26, from reading the quota rather than from a failure.

`RunMetadata.resolved_models` is one model per engine, and its own docstring
calls it "the premise every checkpoint comparison rests on: our code caused
this, because the model did not change." **Nothing checked the premise.** A
corpus spanning two versions would not contradict the record; the dict can hold
only one value per engine, so it would silently keep whichever was written last.

##### Why it stopped being theoretical

| Fact | Consequence |
|---|---|
| The free-tier quota is keyed **per model** (tier2 section 8.6.4) | Switching model grants a fresh allowance |
| Twenty requests per day is the allowance | The incentive to switch arrives daily |
| The fixture store is keyed by **engine**, not model | Both versions land in one corpus |

So the cheapest way to finish a recording run was also the way to invalidate it.
`mixed_model_engines` reports any engine whose observations name more than one
model, and the run exits **3**.

##### Exit 3, for the same reason as its neighbours

Nothing scored badly. **The run has no single subject**, so its numbers describe
neither model, and that is a run not worth reading rather than a finding about
anybody. It reports `RUN_UNSOUND` and carries no `V` number: V1 to V9 decide red
against green, which is a different job.

##### Two things it deliberately does not do

**It is per engine, not across the run.** A run measuring two providers reports
two models and is perfectly coherent. Folding that into a mixture would make the
ordinary multi-engine run unsound.

**A blank model is not a second version.** An observation that skipped never
reached a model. Counting its blank would report a mixture that did not happen,
and a rate-limited run is full of skips: the very condition that makes the real
mixture tempting would otherwise manufacture a false one.

**A replayed corpus is included, not exempt.** Fixtures carry the model that
produced them, which is what makes a mixture visible later, and being visible
later was the reason for recording it.

#### 4.9.7 The README's own figures are checked

Added 2026-09-26, found while preparing the first commit.

`112314` compares the document map's case counts to the designs, and `112203`
compares a design's stated total to its own rows. **The README sat outside both
while being the first thing a reader sees**, and both of its figures had drifted:

| Claimed | Actual |
|---|---|
| 498 cases | 462 inventoried |
| 144 requirements | 184 traced |

**The numbers stay and are checked** rather than being deleted, for the reason
`112314` gives about the document map: a front page whose value is showing the
shape of the project cannot do that without them.

**It recomputes rather than storing a third copy.** The case count is summed from
the design inventories and the requirement count is the matrix's own row count, so
there is no new number to maintain — which is what made the first two drift.

#### 4.9.8 This repository holds no graded case, and the README has to say so

Added 2026-10-05 at the project owner's request, because the front page invited
an inference it does not support.

**The Status table read `Precondition suite (UNI, SYS) | 549 cases, all
passing`.** A reader who has been told this is a foundation-model QC project
reads 549 passing cases as a result about models. It is not one. Every case in
this repository measures the instrument: `UNI` exercises our modules in
isolation, `SYS` drives the harness end to end over recorded transcripts, and
**neither sends anything to a provider**.

| Layer | `graded` | Defined in | A failure is |
|---|---|---|---|
| `UNI`, `SYS` | False | here | **our defect** |
| `EVAL`, `TOOL`, `SEC` | True | `AP-Model-QC` | **a finding about a model** |

`cmn/layers.py` already carries this distinction as the `graded` flag, and its
docstring already states the consequence — "tests our harness, so a failure is
our defect". The separation was in the registry and not on the front page.

**So the claim is now checked rather than asserted.** `112327` reports any case
defined in this repository whose layer is graded. It reads the flag from the
layer registry rather than naming `EVAL`, `TOOL` and `SEC`, so a graded layer
added tomorrow is covered the day it is registered.

**What it deliberately does not forbid is the string.** Harness cases construct
synthetic observations carrying `layer="EVAL"` in order to exercise the
machinery that handles graded results, and that is the correct way to test it:
the plumbing is tested with fabricated data and never with a model. The check
looks at the layer token in a case's own identifier, which is the thing that
would make this repository a place where models are measured.

**The pairing rule this depends on already exists.** A case's identifier encodes
its layer positionally (`1 L M C NN`), and `112307` already enforces that the
token in the name agrees with the digit. Without that, reading the layer from
the name would be reading a label rather than a fact.

---

## 5. Result Metadata Emission

Every observation is emitted with the fields required by `test_taxonomy.md` §9: `engine`, `mode`, `model_version`, `priority`, `priority_conditions`, `taxonomy_code`, `duration`, `output_tokens`, plus the CLI invocation record from §7.

Emitted as Allure parameters and labels, and through JUnit XML test names, so both reach a downstream collector without changes on its side.


### 5.1 One of the fields reached the artifact, and the section said all of them did

Established 2026-10-02 by reading a real Allure raw result rather than the code
that was supposed to produce it.

```
name:       MQC_EVL_EVAL_134205_overstating_a_sourced_figure_is_rejected
status:     failed
parameters: None
labels:     feature, severity, epic, story, tag, parentSuite, suite, subSuite,
            host, thread, framework, language, package
```

**`parameters` is empty and `severity` is the only field of section 9 present.**
A search for `allure.dynamic`, `dynamic.parameter`, `dynamic.label` and
`allure.attach` across both repositories returns nothing: no parameter, no
runtime label and no attachment is emitted anywhere. The only emission is
`label_priority_severity`, which translates the priority marker into a severity
label at collection.

| | Until 2026-10-03 | Now |
|---|---|---|
| Built | **Everything.** `emit_result` returns the whole section 9 mapping and `RunContext.as_fields` the run-scoped half | Unchanged |
| Emitted | `priority`, as `severity` | Every field as a parameter, the taxonomy code also as a label, and a failing case's history as an attachment |

**The records were never the gap.** Section 9.1.1 records the same shape one
field at a time, where `rule_set_hash` was carried, serialised and never
computed. This is that defect applied to the step after: the mapping is
complete and nothing hands it to the artifact.

**What it costs is larger than the verdict.** A collector reading these
artifacts cannot say which engine produced a result, which mode it ran in, or
which taxonomy code it carried. **The three-engine comparison is unattributable
from the artifact**, and the findings this project reports were read from runs
rather than recovered from the contract that exists to carry them. A reviewer
or an analysis has to be able to say which candidate and which judge a result
came from, which is also why the engines get separate jobs.

**`phase0_project_ambiguities.md` section A7.2's mechanism does not exist.** It
states that "pytest parameterization supplies both automatically:
`MQC_EVAL_30001_...[gemini]` appears in the JUnit XML `name` attribute and in
Allure `parameters[]`". The engine is a **command-line flag, not a
parameterisation**, so no identifier carries a suffix and no parameter is
produced. That section is corrected rather than deleted: the requirement it
states is right and the mechanism it names was wrong.

### 5.2 Emitted at runtime, because that is when the values exist

`engine` and `mode` are known once the run is configured, but `resolved_model`
is known only after the provider answers (A8), and `outcome`, `taxonomy_code`,
`duration` and the token counts only after the case runs. So the emission is
per observation at runtime, not a collection-time marker.

| Field group | Emitted as |
|---|---|
| Everything `emit_result` returns | An Allure **parameter** each, so a collector reads a column rather than parsing prose |
| `taxonomy_code` | Also a **label**, which `testing-standards.md` section 4 already requires so root-cause class is filterable |
| `priority` | Already a severity label, unchanged |

**Parameters rather than one attached blob.** A parameter is a field a
collector ingests without knowing this project; an attachment has to be opened
and parsed. The attachment below is for the one thing that cannot be a column.

#### 5.2.1 A case has several observations and a test has one parameter list

Decided 2026-10-03, on implementing the hook. Section 5.2 says every field
`emit_result` returns becomes a parameter, and a case takes three observations
or five, so the mapping is not one to one: Allure parameters are a flat
name-and-value list per test, and three observations of twenty-five fields would
publish seventy-five parameters with colliding names.

**The parameters describe the case and the attachment carries the observations.**

| Published as | What |
|---|---|
| Parameters | The case's fields, taken from one **representative** observation, plus the aggregates below |
| `observations_taken`, `observations_passed` | So a reader sees the population without opening anything |
| `resolved_models` | Only when more than one model served the case, which is the unsound-run condition section 4.9.6 gates on |
| A label | `taxonomy_code`, per `testing-standards.md` section 4 |
| An attachment | Every observation, on a failing case only, per section 5.3 |

**The representative observation is the first failing one, and the first
otherwise.** A reader scanning a failed case wants the call that failed, not the
one that happened to be dispatched first; on a passing case every observation
agreed, so the first is as good as any.

**The per-observation detail is therefore only durable on a failure**, which is
the condition section 5.3 already sets for the attachment and for the same
reason: nothing is filed about a passing case, and prompts are large.

##### 5.2.1.1 A string parameter arrives quoted

`allure.dynamic.parameter` passes its value through `allure_commons.utils.represent`, which reprs a string: `engine` publishes as `'gemini'` rather than `gemini`.

**Recorded rather than worked around.** It is what every Allure parameter does, including the ones `pytest.mark.parametrize` produces, so a collector reading this format already meets it. Emitting labels instead to avoid it would trade the column section 5.2 asks for against a cosmetic difference.

##### 5.2.1.2 Where the emission is possible, established by probing

`allure.dynamic.parameter`, `allure.dynamic.label` and `allure.attach` all reach
the open result from `pytest_runtest_makereport` on the **call** phase, verified
2026-10-03 by emitting from that hook and reading the produced
`*-result.json`. The result carried the parameter, the label and the
attachment on both a passing and a failing test.

**This was probed rather than assumed**, because the reporting hook is the only
place that holds both halves (section 5.4.1) and an emission API that had
already closed its result would have forced the design somewhere worse. The
same method found the original defect: section 5.1 was established by reading a
real raw result rather than the code meant to produce it.

### 5.3 A failing case carries every call it made, not the one that failed

**A finding is filed with the provider, so the artifact has to hold the
reproduction.** Every vulnerability and every quality finding this project
reports is reported to the engine's provider, and a ticket needs the exact
call: the model asked for and the model served, the prompt, the parameters, the
tool declarations, the response and its finish reason. Reading those out of a
run by hand is the step that does not survive contact with more than one
finding.

**The report is per case, over every observation, and that is the part worth
getting right.** A4.1 sends three observations and a single disagreement earns
two more, so **the failing call is frequently not the first one**: a case can
fail at observation two of three, or one of five. Two consequences:

| | |
|---|---|
| One request cannot represent the case | The ticket would describe a call that succeeded, or a call whose siblings it does not mention |
| **`QC_LLM_INCONSISTENT` is a finding about the set** | "This model answers the same question three ways" is unreportable from any single call, because each one on its own looks fine or looks broken |

So a failing case attaches the **history**: every observation in index order,
each carrying its composed request, its normalized response, its outcome and
the model that served it. A provider reading it sees what we sent every time
and what came back every time, which is what makes an inconsistency claim
checkable rather than asserted.

| | |
|---|---|
| On a failing case | Attached once, covering every observation including the ones that passed |
| On a passing case | **Not attached.** Nothing is filed about it, and prompts are large |
| Credentials | Passed through `cmn.config.redact` first, which already walks a structure for credential-shaped keys |

**The request is retained on every `DispatchOutcome`**, because the case's
verdict is not known while the observations are being taken: the passing
observations of a failing case are exactly the ones the report needs, and a
record kept only on a failing call could not produce them. The condition is on
the attachment, not on the record.

**It is an Allure attachment and not a file this project invents.**
`testing-standards.md` section 5 prohibits a hand-rolled summary file and names
Allure raw results as a standard format; an attachment is part of that format,
so the reproduction travels inside the contract rather than beside it.

### 5.4 The harness builds the record and the consumer attaches it

The harness owns no graded case, so the emission happens where the cases are,
through the arrangement the encoding and header rules already use.

| Here | There |
|---|---|
| `cmn.reporting` builds the records, purely. `cmn.pytest_support` stashes and publishes them from the reporting hook | `observe` records what the tiers measured |

**Pure builders, because the question is what the record says.** A function that
called into Allure could only be tested by running a reporter; one that returns
a mapping is tested by reading it.

#### 5.4.1 The emission is a reporting hook, not a call inside `observe`

**Corrected 2026-10-02, while wiring it.** This section first put the emission
in `observe` and the attachment in `observe_repeatedly`. Implementing that
established it cannot work: **`observe` holds only half of an observation.**

`assemble_observation` already states the split, and its own case says where the
halves meet: "Tier 3 never receives priority, so it cannot produce a complete
observation; the orchestrating test holds the case metadata and has no access to
what dispatch measured. **The reporting hook is where the two meet.**"

| Half | Held by | Fields |
|---|---|---|
| What was measured | `observe`, from the dispatch outcome | `engine`, `mode`, `requested_model`, `resolved_model`, `outcome`, `duration`, `output_tokens`, `taxonomy_code` |
| What the case is | The **pytest item**, from its markers and its module | `layer`, `priority`, `priority_conditions`, `family`, `requirement_ids` |

`observe` receives a configuration, not an item, so it cannot read a marker.
So `observe` **records** the measured half against the run, and the reporting
hook, which has the item, merges it with the case half and publishes.

**This also puts the vendor report in the right place.** A case's verdict is
known at report time and not inside the loop that takes its observations, and
the hook is the first point that knows whether the case failed.

**The chain was designed and entirely unconnected.**
`assemble_observation`, `emit_result` and `require_complete_result` all shipped,
all had cases, and had **no caller outside the test suite**. The emission was
not new machinery; it was the join the design had always described, and
`conftest.py` said so in prose from the day the metadata model was written: "The
reporting hook that assembles observations is not here yet."

**Connected 2026-10-03.** `cmn/emission.py` records what `observe` measured and
publishes it from the reporting hook; the consumer's `observe` records, and both
conftests clear at setup and publish at report. `MQC_CMN_UNI_112251` and
`112252` cover the hook against a recorder, and `112253` runs a real pytest
invocation with a real reporter and reads the result it wrote, which is the only
form of evidence that would have caught the original defect: every case about
the mapping passed while nothing published it.

| Verified by reading a real result | Value |
|---|---|
| `engine`, `mode`, `resolved_model` | Present, so a result is attributable to one model |
| `taxonomy_code` | A parameter **and** a label |
| `families`, `primary_family` | Present on a `SEC` or `TOOL` case, absent on `EVAL`, which is the gap `test_taxonomy.md` section 11.5.1 carries |
| `vendor-report` | Attached on a failing case, carrying every observation with its request and response |

---

## 6. RTM Integrity

Two matrices (`rtm_harness.csv`, `rtm_model.csv`), loaded through Tier 1's CSV loader, so they are validated data rather than documents someone maintains.

| # | Check | Gap type |
|---|---|---|
| T1 | Every requirement has an RTM row | Traceability: the matrix is stale |
| T2 | Every RTM row names at least one test | **Coverage: nothing verifies it** |
| T3 | Every test named in the RTM exists in the suite | Stale reference |
| T4 | Every test carrying `requirement_ids` has a matching row | Untracked coverage |
| T5 | Every `families` value matches the cases named in the same row | **Derived data restated wrongly** |
| T6 | Every requirement identifier is declared exactly once | **A second row silently replacing the first** |
| T7 | Every test the suite collects is named in some RTM row | **Untraced coverage: a case runs and no requirement claims it** |

Two directions, structurally identical to Tier 1's R2 and R3 one level up: every declared thing must be verified, and every verification must trace to something declared.

#### 6.0.1 T7 is invoked on its own, and T4 is not a substitute

Added 2026-10-01, after two inventoried consumer cases ran untraced and
the preconditions stayed green.

**T4 asks a test what it claims and T7 asks the suite what it contains.**
T4 reads `requirement_ids` off a test and checks the matrix has a matching
row, so a test that declares nothing satisfies it by declaring nothing.
That is the self-consistency problem one level down: the subject supplies
the evidence. T7 takes the collected suite, which no part of the matrix
produced.

| | Input | A test traced to nothing |
|---|---|---|
| T4 | What the test declares | **Passes**, if it declares nothing |
| T7 | What the suite collects | Reported |

**It is therefore not part of `check_matrix_integrity`.** The other six
run against whatever rows and sets a caller supplies, which is what lets
them be exercised against synthetic fixtures. T7 is only meaningful
against the **complete** collected suite, and a partial set makes it
report every test the caller left out. `untraced_tests` is public and
called by the two repository-level cases that can supply one,
`MQC_CMN_UNI_112313` and `MQC_CAS_UNI_115602`.

### 6.1 Matrix schema

Specified here because the matrices are **loaded through the CSV loader**, so their columns are a schema like any other and the loader's rules apply: a blank cell takes the declared default, an unknown column is rejected, and no value is type-inferred.

| Column | Present in | Carries |
|---|---|---|
| `requirement_id` | Both | `MQC_HAR_*` or `MQC_MDL_*` |
| `requirement_text` | Both | The requirement as the plan states it |
| `source` | Both | Provenance, so a self-authored requirement is distinguishable from an inherited one |
| `category` | Both | Where the requirement comes from: a module and section for the harness, a requirement domain for the model |
| `families` | **Model only** | The evaluation families whose cases exercise it, semicolon separated |
| `test_ids` | Both | Covering tests, semicolon separated |
| `notes` | Both | Why the row reads as it does, where that is not obvious |

#### 6.1.1 Why the model matrix carries families and the harness matrix does not

**Families apply to graded cases only**, per `test_taxonomy.md` section 11: a precondition tests the harness, which performs no task. The column would be empty in every harness row, and an always-empty column teaches a reader to ignore a column.

The two files therefore share one schema with `families` optional, and the harness file **omits the column rather than carrying it blank**. That needs no special case: an absent optional column takes its declared default, which is the rule `MQC_ING_UNI_111203` covers. Two schemas would have been the alternative, and two schemas for one matrix format is the drift this section exists to prevent.

**The column exists because coverage is read per family, not only per requirement.** A requirement covered by three families has survived a change of domain; one covered by a single family has been observed once in one setting and may hold only there. That distinction is the whole subject of `model_evaluation_test_plan.md` section 4.4, which lives in `AP-Model-QC`, and without this column it is visible in the case inventory and invisible in the matrix that exists to report coverage.

**`families` is derived, never authored.** It is the distinct families of the cases named in `test_ids`, so it cannot disagree with the inventory. A hand-maintained copy would be a second statement of one fact, which is the drift this project has already corrected three times.

---

## 7. CLI Contract

| Flag | Values | Default | Recorded in metadata |
|---|---|---|---|
| `--engine` | `gemini`, `openai`, `claude` | `gemini` | ✓ |
| `--mode` | `live`, `replay` | `replay` | ✓ |
| `--priority` | Comma-separated `0`-`4` | all | ✓ |
| `--with-prerequisites` | flag | off | ✓ |
| `--golden-rules` | Path | repo default | ✓ as content hash |
| `--extra-columns` | `reject`, `drop` | `reject` | ✓ |
| `--judge-on-failure` | flag | off | ✓ |
| `--as-of` | ISO date | today | ✓ |

**Every flag that can change a result is recorded in result metadata.** A run that dropped three columns, replayed instead of executing live, or used a revised rule set must be distinguishable from one that did not. This is the same principle as A6 (replay marking) and A8 (resolved model version), applied to the invocation itself.


#### 7.1.0.1 Three gaps read, and two of them were the same defect again

Added 2026-10-01, reading the code behind each dated gap rather than restating
what was unknown about it.

| Flag | Registered | Behaviour exists | Connected |
|---|---|---|---|
| `--extra-columns` | Yes | **Yes**, `ingestion/loaders.py` `unknown_columns` | Since 2026-10-02, `tier1_ingestion.md` section 4.6 |
| `--out-dir` | Yes | Since 2026-10-02 | Section 7.1.0.2 |
| `--tests` | As a workflow input | In the workflow | Not a pytest flag |

**`--extra-columns` is the third instance of what produced this file.**
`--max-spend` accepted a ceiling that could not stop a request and `--priority`
named a band and ran every band. This one names a column policy, is recorded
into the invocation record, and reaches no code, while the loader that
implements reject and drop sits beside it. **A run can therefore record a
policy it never applied**, which is the same shape as the two that came before:
not a missing feature, a claim in the record that nothing backs.

**`--out-dir` has no unwired implementation behind it**, which makes it a
different question. pytest's own `--junitxml` and `--alluredir` write the
artifacts and are what the workflows pass. So either the flag gains behaviour or
it is retired and section 7.3 loses its row, and that is a decision rather than
a defect to fix.

**Corrected 2026-10-02, and the error is worth keeping.** Reading the flag
against the workflows established that the artifacts did get written; reading it
against `testing-standards.md` section 5 establishes that **four invocations
write only one of the two the contract mandates**. The decision was real and
section 7.1.0.2 takes it. The claim that no defect sat behind it came from
scoping the question to the flag instead of to the contract the flag serves.

**`--tests` is not a pytest flag at all.** The debug workflow translates it into
a selection before pytest starts, so no case in either tree can pass it. What is
coverable is the translation, which belongs to a workflow case.

**The expiry on the first two moved to 2026-10-31**, matching `--max-spend`.
Each is now a known defect or a known decision rather than an unread gap, and a
dated absence whose reason has been superseded should not sit for another month
behind the old date.

#### 7.1.0.2 `--out-dir` names the directory both mandated artifacts go in

Implemented 2026-10-02. **This section corrects what 7.1.0.1 said about the
flag**, which was that it had no unwired implementation behind it and so posed a
decision rather than a defect. The decision was real; the absence of a defect
was not.

**Both artifacts are mandated, and `testing-standards.md` section 5 is where.**
"The Contract Is The Artifact ... Emit **both** JUnit XML and Allure raw
results." They are not two renderings of one result to pick between, because
they are read by different people for different purposes:

| Artifact | Read by | For |
|---|---|---|
| JUnit XML | Developers and QA | Triaging a failure: durable, per-test, and parsed by every CI interface without configuration |
| Allure raw results | Reporting and release review | Steps, labels, severity and parameters, which is what a report is assembled from and what readiness is judged against |

Dropping either does not lose a format, it loses a reader. A run with no Allure
results produces no report, and a release question answered from JUnit alone is
answered without the evidence section 5 exists to require.

**Four invocations emit JUnit and no Allure**, which is the defect 7.1.0.1
missed by reasoning about the flag in isolation instead of against the contract:

| Invocation | `--out-dir` | `--junitxml` | `--alluredir` |
|---|---|---|---|
| `debug-failures-on-demand.yml` | Yes | Yes | **No** |
| Consumer `debug-cases-on-demand.yml` | Yes | Yes | **No** |
| `regress-consumers-on-merge.yml`, deterministic gates | No | Yes | **No** |
| `regress-consumers-on-merge.yml`, graded replay | No | Yes | **No** |
| `diagnose-on-demand.yml` | Yes | Yes | Yes |
| Every gating workflow in both repositories | No | Yes | Yes |

The gating paths were correct throughout. **The half-emitting invocations are
the debug, diagnostic and consumer-regression paths**, which is the worst place
for it: those are the runs someone reaches for when something has already gone
wrong, and they are the runs that arrive without a report.

**Implementing the flag closes the first two by itself.** Both debug workflows
already pass `--out-dir`, so a flag that derives the Allure destination makes
them emit both without either workflow changing. That is the argument for
implementing rather than retiring, and it is a stronger one than the tidiness
argument this section first carried.

**It derives each mandated destination the caller did not name.**

| Given | JUnit lands at | Allure lands at |
|---|---|---|
| `--out-dir d/` | `d/junit.xml` | `d/allure-results` |
| `--out-dir d/ --junitxml=e/x.xml` | `e/x.xml`, explicit wins | `d/allure-results` |
| `--out-dir d/ --alluredir=e/a` | `d/junit.xml` | `e/a`, explicit wins |

**Explicit may redirect one artifact and never suppress the other**, which is
why the two destinations are resolved independently rather than as a pair. The
consumer-regression steps are the case that requires it: they give each JUnit
file a distinct name so four matrix legs do not overwrite one file, and they
must keep those names while gaining Allure. A flag that stepped aside entirely
once any artifact flag appeared would leave them exactly as they are.

**Set when the run is configured.** The JUnit plugin builds its writer in its
own `pytest_configure`, so a conftest hook is early enough to redirect it and
nothing later is. Confirmed by writing an artifact to a named directory before
this design was settled, rather than assuming the hook order.

**Guarded on the Allure plugin being loaded.** `allure-pytest` is a `[dev]`
dependency and the consumer installs the harness `--no-deps` in one path, so the
option may be absent. A missing plugin means no Allure flag to set, not a
failure: the plugin's absence is the operator's choice and this flag does not
overrule it.

**It names a directory and not a file**, because two artifacts go in it and
section 5 permits a third. A flag naming one file would need a sibling per
format, which is the duplication it exists to remove.

### 7.1.0.3 The mandate was right and nothing established it was met

The four half-emitting invocations sat in plain sight across both repositories
because **no check reads what a workflow passes to pytest against section 5's
requirement**. `112522` asks the opposite question, whether a registered flag is
named by any case, and every artifact check downstream reads artifacts that were
produced rather than asking whether they all were.

`112525` scans every workflow in both repositories and fails an invocation that
emits one mandated artifact without the other, counting `--out-dir` as
supplying both. **A negative case**, because the positive it would replace,
these workflows running at all, was passing while four of them emitted half the
contract.

**This is the seventh instance of the shape this file keeps recording**, and the
first where the thing nothing established was a written standard rather than a
flag: a ceiling that stopped nothing, a band selector that selected everything,
a column policy wired to nothing, an assertion covering one of two halves, a
gate that could not start, an identifier deduplicated away, and now a mandate
with no reader.

### 7.1 Two surfaces, one option registry

The flags reach the harness through two entry points, and they must not drift.

| Surface | Mechanism | Used for |
|---|---|---|
| Test execution | `pytest_addoption` in `conftest.py` | Running the suite |
| Standalone tool | `argparse`, with subcommands | Verdict, reporting, RTM checks |

**`pytest_addoption` is argparse-backed**, so the execution flags gain autogenerated help through `pytest --help` without a second parser competing for `sys.argv`. `choices` is declared on every enumerated flag, so a typo fails at parse time with the valid values listed rather than deep inside a run that has already spent quota.

**Options are defined once in a registry** that both entry points consume. Two hand-maintained definitions of `--mode` would eventually disagree, and the symptom would be a report contradicting the run it describes.

#### 7.1.0 A registry entry nothing reads is worse than a missing flag

Specified 2026-09-29, after three were found in one area.

Registering an option adds it to `pytest --help`, to the table at section 7, and
to whatever documentation quotes it. **None of that makes anything read it.**

| Flag or field | Found | What a run did |
|---|---|---|
| `--max-spend` | Declared, never read | Accepted a ceiling that could not stop a request |
| `--priority` | Declared, quoted in `testing-standards.md` section 2 as a worked example, **never read** | Named a band, ran every band, reported as a band |
| `rule_set_hash` | Declared, serialised by `as_fields`, **never computed** | Emitted the empty string for "which rules produced this" |

**The failure mode is the same in all three and it is not a crash.** The flag
parses, the run proceeds, and the result is reported under a description of
itself that is false. A missing flag fails loudly at parse time; a declared one
that nothing reads produces a confident wrong answer, which is the error class
this project keeps finding and the reason section 7.1 exists at all.

**"Is it read" cannot be the check, and the first attempt at this section said
it was.** `configure_invocation` reads every registered option generically to
build the invocation record, so every flag is read, including the three above.
Narrowing it to "is it read specifically" fails too: `--priority` had no
`getoption` call of its own, but `priority` is read as an attribute throughout
the suite, so any name-based heuristic scores it consumed. Measured against the
two known defects, that check would have passed both.

**So the rule is the inventory principle, applied to flags: every registered
option is named by at least one case.** A flag that no case exercises is a flag
nobody has established does anything, which is exactly the state all three were
in.

| Flag | Was it read? | Named by a case? |
|---|---|---|
| `--max-spend` | Yes, generically | **No** |
| `--priority` | Yes, generically | **No** |

That is checkable without heuristics, and it fails for the right reason: not
"this code looks unused" but "nothing demonstrates this works".

**It does not prove the flag is wired correctly**, only that something claims
to exercise it. A case can still be vacuous, which is what injection testing is
for. It moves the failure from silent to arguable, which is the most a
structural check can do.

**Coverage is owned per flag, because neither repository can see both test
trees.** The harness must not read the case repository, and the installed wheel
ships no tests, so a check on either side alone can only ask about its own
cases. Measured: five flags are exercised by harness cases, five by consumer
cases, and a harness-side check demanding the whole registry would need eleven
exemptions out of sixteen, which is a permitted list wearing a check's clothes.

So `config/flag_coverage.yaml` declares, per flag, which side is responsible:

```
--engine:       {owner: harness}
--case-index:   {owner: harness}
--judge-on-failure: {owner: consumer}
--tag:          {gap: {reason: "...", expires_on: 2026-11-30}}
```

**The gap form is shown and no flag currently takes it.** Every declared gap is
closed as of 2026-10-04, `--tag` last; the shape stays documented because the
next flag that cannot be covered yet needs somewhere to say so. An earlier
version of this illustration named `--case`, which was retired in §7.8.4, and
an `--out-dir` gap that had already closed: an example is as liable to go stale
as a claim.

Each repository asserts only what it owns. The file ships as package data, so
both read one declaration rather than two that drift.

**A gap is declared, dated and expires**, which is the treatment
`quarantine.yaml` gives a case and for the same reason: without an expiry, the
list is where inconvenient flags go to be forgotten, and the check stops meaning
anything because everything unproven has left its denominator. An expired entry
fails the run, which forces the decision to be made again rather than to lapse.

**Nine of sixteen flags are gaps as this is written**, including the two that
produced this section. That number is the finding, not a defect in the check.

`MQC_CMN_UNI_112522` enforces the harness half, reading the shipped registry and
declaration rather than a permitted list of its own.

#### 7.1.1 Diagnostic runs

Troubleshooting and hotfix verification need a single case run from a terminal, not a CI pipeline.

| Flag | Purpose |
|---|---|
| `--tests <ID>[,<ID>]` | Select cases by identifier, or `@file` for a list (§7.8). **Replaced `--case`, retired 2026-10-03** |
| `--observations <N>` | Override the configured observation count |
| `--log-level <LEVEL>` | Raise verbosity for the run |
| `--out-dir <PATH>` | Write artifacts somewhere a real run will not be overwritten |

**`--case` validates the identifier.** `pytest -k` on an unknown name selects zero tests and does not fail, which is the same silent-success class as the empty run that V6 exists to catch. An unknown identifier is an error naming it, not a run of nothing reporting success.

**`--observations` matters for cost.** A4 gives every case three observations; troubleshooting usually needs one, and in live mode three spends triple the quota to answer a question one answers.

**A diagnostic run may skip preconditions.** The operator knows the harness works and is debugging one case. CI must never do this, which is why the next rule exists.

#### A diagnostic run produces no verdict

It returns pytest's own exit status and **never a verdict code**.

Without this, a rerun of one passing case would exit 0 through the same path a full gated run uses, and nothing would distinguish them. A reviewer, or the operator a week later, could read a diagnostic green as a suite green. With it, **a verdict requires a gated run by construction**.

Two supports:

* **Run context is recorded** as `ci`, `ci_debug` or `local`, alongside a derived `gated` flag. This follows A6: record what varied rather than suppressing it, so a diagnostic artifact is self-describing.
* **The verdict tool refuses artifacts marked ungated**, exiting 4. A diagnostic run's output cannot be turned into a green verdict later, including by someone who does not know where it came from.

#### `gated` is derived, not set

There is **one** condition, not several that could drift apart:

> A run is gated if and only if `selection_mode` is `full` or `change_scoped`, **and** preconditions executed, **and** `run_context` is `ci`.

Everything else follows. A diagnostic run skips preconditions, so it is ungated. A manual selection is ungated whatever else is true. A debug run is ungated on the third condition regardless of the first two. The verdict tool then needs a single refusal rule rather than one per way of producing an ungated run, and a future fourth way of bypassing gates inherits the behaviour without a new rule.

**The third condition was added after the second one proved insufficient.** An earlier version derived `gated` from selection and preconditions alone, and justified excluding debug runs on the grounds that they carry a manual selection. That holds only while debug runs are small selections. A developer validating a new harness implementation on a branch runs the **full** suite, preconditions and all, which satisfied both original conditions and derived `gated: true`.

**Being on a branch is not itself disqualifying**, and an earlier draft of this paragraph wrongly implied it was. A pull request runs on a branch, carries unmerged code, and is gated deliberately: it is a recorded proposal under review, and the full run on merge backstops it.

What disqualifies a debug run is that **it can describe a repository state that never existed.** Section 6 of `ci_pipeline.md` lets a diagnostic take its code from one checkpoint and its fixtures from another, precisely so a regression can be attributed. That combination is a useful experiment and an invalid observation: nothing was ever released in that configuration, so no verdict about it means anything, and nothing backstops it the way a merge run backstops a pull request.

The condition is therefore `run_context` rather than a stricter rule about selection or about branches. A run assembled from parts is ungated regardless of how complete each part was.

#### 7.1.2 Subset selection and what it costs

Testers need to run a subset from a terminal or from CI. Selection is cheap; the question is whether the run still yields a verdict.

| Flag | Selects | State |
|---|---|---|
| `--tests <ID>[,<ID>]` | Specific cases, or `@file` for a list | Implemented, §7.8 |
| `--priority 0,1` | Priority bands | Implemented, §7.5 |
| `--family <id>[,<id>]` | Cases addressing an evaluation family | Implemented, §7.7 |
| `--requirement <id>[,<id>]` | Cases covering a requirement | Implemented, §7.7 |
| `--module ING,EXE` | Modules | Implemented, §7.7.5 |
| `--tag <tag>` | Tagged groups, such as an ambiguity control pair | Implemented, §7.7.6 |
| `-m`, `-k` | pytest native marker and name expressions | pytest's own |

#### A verdict requires a selection the harness computed

**Not all subsets are equal, and the difference is not size.** Change-scoped selection on a pull request is already a subset and does yield a verdict, because the selection is derived from the diff, recorded, and backstopped by the full run on merge. A hand-typed subset is arbitrary with no backstop.

| `selection_mode` | Produced by | Verdict |
|---|---|---|
| `full` | No filter supplied | Yes |
| `change_scoped` | Derived from the diff | Yes |
| `manual` | Any filter flag present | **No** |

This generalises the diagnostic-run rule rather than adding a second one. One case or one layer, the same logic applies: a verdict from an arbitrary subset is a partial verdict, and a green built from one is the blame-misattribution failure that full-run-on-merge exists to prevent.

`selection_mode` is recorded per result.

#### 7.1.3 The debug CI job

A `workflow_dispatch` job taking selection inputs, for troubleshooting a failure inside CI rather than locally.

**"Not included anywhere" needs two independent mechanisms**, because the failure it prevents is silent: debug results merged into reliability history would look exactly like real observations and nothing downstream would flag them.

| Mechanism | Effect |
|---|---|
| **Artifact naming** | Collectors match artifact names by pattern. A debug job uploads under a name outside that pattern, so the artifact stays downloadable for whoever is debugging while never entering the durable record |
| **Row marking** | Every row carries `run_context: ci_debug`, `gated: false`, `selection_mode: manual`. Even if an artifact were collected, by a loosened regex or a manual upload, its rows are identifiable and excludable |

Structural separation alone would fail the day someone widens the collector's pattern. Marking alone would fail if nobody filters on it. Together, either one catches what the other misses.

**Quota interaction:** a debug job running live shares the engine concurrency group, so it queues behind real runs rather than competing with them.

### 7.2 The verdict is computed by a standalone tool

Section 6.1 specifies the verdict as a pure function but not what invokes it. It is invoked by the standalone tool, reading emitted artifacts, **not** by an in-process hook during the run.

The reason is specific to this project: thresholds are configuration (`extensibility_standard.md` section 14), so **a verdict can be recomputed from stored artifacts without re-running anything.** "What would this run have scored under the tightened floor?" is then answerable from history, which is what makes a threshold change auditable rather than merely disclosed.

It also keeps the verdict function callable with synthetic observations, which is what makes its 46 cases possible without a suite run.

### 7.3 Exit codes

`argparse` exits 2 on a bad argument, so the verdict tool's codes are chosen to stay distinguishable from it.

| Code | Meaning |
|---|---|
| 0 | Green |
| 1 | Red, one or more verdict rules breached |
| 2 | Argument error, `argparse` default |
| 3 | Precondition failure, the run never reached the graded layers |
| 4 | Refused, the artifact is ungated and no verdict can be computed from it |

A **diagnostic run uses none of these.** It returns pytest's exit status, because it computes no verdict.

**4 is distinct from 1.** A red verdict says the suite was measured and something failed; a refusal says no verdict was computable from what it was given. Collapsing them would let a refused artifact read as a failing suite, which is the inverse of the error the gating rules exist to prevent.

**1 and 3 are separated deliberately.** A red verdict is a finding about a measured run; a precondition failure means nothing was measured. Collapsing them would let CI treat "the harness is broken" as "the model underperformed".

**Defaults fail safe.** `--mode` defaults to `replay` so no unconfigured invocation can spend quota or emit an unmarked live result. `--extra-columns` defaults to `reject`. `--engine` defaults to `gemini` but emits a **WARNING into the artifact** when defaulted, so a cloned repository running unconfigured produces a record saying so (A7.4).

#### 7.4.1 Choosing the default is not defaulting

Corrected 2026-09-28, found in the output of the first paid run.

`configure_invocation` decided a flag had been supplied by comparing its value
against its default. So `--engine gemini` was indistinguishable from naming no
engine at all, because gemini **is** the default, and every deliberate run
carried `QC_DATA_ENGINE_DEFAULTED`.

**The warning exists to mark a record nobody chose the provider for** (A7.4).
Firing it on records where somebody did choose inverts it: `ci_pipeline.md`
already names this hazard when it says a signal present on every run trains a
reader to ignore the one line that says a record is not what it appears to be.

**The commonest invocation was the broken one.** Gemini is the roster's default
and the only engine with a funded credential, so nearly every live run this
project will ever make names the default explicitly.

##### Why the existing case did not catch it

`112312` asserted that `build_invocation({"engine": "openai"})` is quiet. `openai`
is not the default, so the case proved only that an explicitly NON-default engine
warns about nothing. The defect lived precisely where the explicit value equals
the default, and the fixture's choice of value stepped around it.

**The fix reads the command line rather than inferring from the value.**
`config.invocation_params.args` carries what the caller actually wrote, in both
the `--engine gemini` and `--engine=gemini` spellings, so what was named is a fact
rather than a deduction. Where the invocation is unavailable the value comparison
still applies: a warning is not worth failing a run over.

---

### 7.5 `--priority` selects a band, and the flag did nothing for months

Specified 2026-09-29, after the flag was found to filter nothing.

`--priority` has been in the option registry, in the table at section 7.1, and
in `testing-standards.md` section 2 as a worked example since bands were first
discussed. **No code ever read it.** A run passing `--priority 0,1` collected
every band, ran the whole graded suite and reported as though a band had run,
which is worse than the flag not existing: a job that names a band and measures
everything looks like coverage it does not have.

**Selection is by band membership**, from the `priority` marker each graded case
carries. A precondition has no marker and is never deselected: it establishes
that the corpus loads at all, and a band measured against an unchecked corpus
measures nothing.

**A malformed band is refused rather than ignored.** `--priority 5` or
`--priority one` raises `QC_HARNESS_PARSER_ERROR`. The alternative reading, that
an unparseable value selects everything, is the failure above with a typo as its
cause.

#### 7.5.1 A band carries its foundations only when it runs alone

The cascade crosses bands: `MQC_EVL_EVAL_134107` is P2 and depends on a P1 case,
and that is the normal shape rather than an accident. A P2 elaboration
presupposes the P1 foundation it elaborates.

So a band selected on its own collects dependents whose bases are absent, and
`arrange_dependencies` refuses the suite. **What to do about that differs by
why the band is running**, which is the distinction this section exists to make.

| Context | Foundations | Because |
|---|---|---|
| A band in the CI sequence | **Carried**, per section 7.6 | The earlier band already ran them, minutes ago, in the same job |
| A band run alone, debugging | **Collected and run** | Nothing else has run them |

**Re-running them in the sequence would be waste at best and noise at worst.**
The p1 execution has just reported those cases. Running them again inside the
p2 execution asks the same question of the same fixtures and, when one of them
failed, asks it again knowing the answer.

`--with-prerequisites` is therefore explicit rather than inferred from whether a
carried record happens to exist. Inferring it would make a CI misconfiguration
silently become a standalone run: the band would pass, having quietly re-run and
re-established its own foundations, and nothing in the result would say so.

#### 7.5.2 The flag acts through `--priority`, and refuses where it cannot act

Added 2026-10-01, after two live recording runs selected nothing.

`select_priority_bands` returns immediately when `--priority` names no band, so
`--with-prerequisites` was **never read** under any other selection. Recording a
single case with `-k 30023` deselected its foundation `134405`,
`arrange_dependencies` read a non-executed foundation as unmet, and the case
skipped on `QC_HARNESS_DEPENDENCY_UNMET` with the flag set on the command line.

**The flag cannot act under `-k`, and that is not a fixable omission.** pytest
applies keyword deselection before `pytest_collection_modifyitems` runs, so by
the time this code sees the items the foundation is already gone. A flag whose
only honest answer is "not here" must say so.

| Selection | What the flag can do |
|---|---|
| `--priority 2,3,4` | Compute the closure and re-admit the foundations |
| `-k <expression>` | **Nothing. pytest has already deselected them** |
| No filter at all | Nothing, and nothing is needed: every case is collected |

So `--with-prerequisites` with `-k` and no `--priority` is refused at collection
with `QC_HARNESS_PARSER_ERROR`, naming `--priority` as the selection it works
with. **Refused rather than warned**, because the symptom of proceeding is a
skip that reads as a corpus defect, and because both attempts here were live
runs: the flag's silence cost two dispatch attempts that recorded nothing.

**With no filter at all it warns instead of refusing.** The flag is then a
harmless no-op, and a full run that happens to carry it is not misconfigured.

`MQC_CMN_UNI_112412` covers the refusal and `112413` the warning.

### 7.6 Carried prerequisite outcomes, and the provenance that admits them

Specified 2026-09-29.

**The cascade is in-process.** `_BASE_OUTCOMES` is a module-level mapping,
cleared per session, so it does not survive between the executions that make up
one job. The p2 execution starts with no memory that p1 ran.

**Only the outcome is carried, never the test.** A base that held is a fact the
earlier execution established; re-establishing it is the waste section 7.5.1
names. A base that did **not** hold still skips its dependents with
`QC_HARNESS_DEPENDENCY_UNMET`, which is the property that would be lost by the
obvious alternative of treating an absent base as non-gating: a P2 case would
then run and report a measurement that presupposes something known to be false.

#### 7.6.1 The record is validated, and a mismatch refuses

A carried outcome is cross-run state, which is the category that fails silently.
A stale record would let a dependent pass on a foundation that held against
different code, different rules, or a different engine, and nothing would look
wrong.

So the record carries provenance and the load compares it field by field:

| Field | Answers |
|---|---|
| `rule_set_hash` | Were these the same rules? |
| `code_ref` | The same harness commit |
| `case_ref` | The same corpus commit |
| `engine` | The same provider |
| `mode` | Observed or replayed |
| `platform` | The harness is verified on two, and a P1 failing on one is the case this whole topology exists to surface |
| `band` | Which execution wrote it |

**`rule_set_hash` is the primary guard**, and the refs are secondary, for the
reason `test_taxonomy.md` section 9.1.1 gives: a commit reference cannot see an
uncommitted edit, and corpus edits between executions are normal working.

**A mismatch refuses.** The two available fallbacks are both worse than
stopping: re-running the prerequisites is the waste this avoids, and assuming
the foundation held is an assertion nobody measured. The refusal names the field
that differed, because "provenance mismatch" sends a reader to check six things.

**The record is per job and is not a durable artifact.** It is written under
`reports/`, read by the next execution in the same job, and dies with the
runner. It is deliberately not uploaded: a carried outcome is scaffolding
between executions, and a collector that picked it up would have a second,
weaker account of results that the JUnit and Allure artifacts already carry
properly.

### 7.7 Selecting a regression set by family or by requirement

Added 2026-10-03 at the project owner's instruction: **after a fix, the set worth re-running is selected by priority, family or requirement.** `--priority` existed; the other two did not.

A fix to a model's injection handling does not map to a module, a layer or a file. It maps to the behaviour that was fixed, and the two registers naming behaviour are the family (what the model was asked to do) and the requirement (what it must do).

#### 7.7.1 Three flags, one mechanism

| Flag | Selects | Resolved through |
|---|---|---|
| `--family <id>[,<id>]` | Every case addressing that family | The traceability matrix |
| `--requirement <id>[,<id>]` | Every case covering that requirement | The traceability matrix |
| `--rtm <path>` | Nothing; names the matrix the two above read | The caller |

**`--rtm` is a path the caller supplies and absent is not a default**, exactly as `--golden-rules` is. This repository owns no matrix: `rtm_harness.csv` traces preconditions and carries no `families` column at all, deliberately (`MQC_CMN_UNI_112311`), so a default pointing at it would resolve every family to nothing. The case repository sets it in its `pytest.ini`.

**Using either selector without `--rtm` refuses.** The alternative is a run that resolves nothing, selects nothing, and reports green.

#### 7.7.2 `--family` is inclusive, and this revises an earlier claim

**A case carrying the family in any position is selected, primary or secondary.**

`test_taxonomy.md` §11.7.5 argued the opposite when it recorded this as a gap: that selecting on the primary returns the cases a fix wants re-run, and that including the rest returns cases that merely touch it. **That was wrong, and the error was in what selection is for.**

A regression set exists to detect a regression. A case where the family is secondary still exercises it, so if the fix broke something that case can show it; omitting it buys a little quota and risks missing the thing the re-run was for. **Omission is the expensive error and inclusion is the cheap one**, which is the opposite balance from attribution.

| Primary is for | Inclusive is for |
|---|---|
| Saying which family owns a finding | Deciding what to re-run |
| Grouping a report, and the headline cost figure | Detecting a regression wherever it surfaced |
| `MQC_CAS_UNI_115412`, where the derived family must be first | — |

Narrowing to the primary remains available to a reader after the fact, because `primary_family` is published on every result (§11.7.2.1). Selection does not need its own flag for that, and a second flag differing from the first by one word is how a caller reaches for the wrong one.

#### 7.7.3 Refusing is the whole value of the flag

**An unknown value refuses, and so does a selection matching no collected case.**

This project has found the same defect at least nine times: the thing is right and nothing establishes it is reachable. A selector is the purest form of the hazard, because its failure mode is silence. `--family injection_resistence` resolves nothing, selects nothing, runs nothing, and **reports green**, which is indistinguishable from a passing run to every artifact and every reader.

| Refused | Why not a warning |
|---|---|
| A family not in the registry | A typo is the common case and the run would otherwise pass vacuously |
| A requirement with no row in the matrix | Same, and it also catches a renamed requirement |
| A resolution matching no collected case | The matrix can name a case the suite does not implement; `115405` reports that structurally, and a run must not proceed on it |

**A warning would not do.** A run that selects nothing takes seconds and exits zero, so the warning arrives in a log nobody reads for a run nobody doubts.

#### 7.7.4 Composition, and what it costs

| Several values in one flag | Union. `--family a,b` is every case addressing either |
| Two different flags | Intersection. `--priority 0,1 --family injection_resistance` is the P0 and P1 cases addressing it |
| `--with-prerequisites` | Applies as it does to `--priority`: a selected case resting on an unselected foundation refuses, naming both remedies (§7.5.1) |

**Preconditions are never deselected**, for the reason §7.5 gives about bands: they establish that the corpus is loadable at all, and a selection that dropped them would measure against an unchecked corpus.

**Both are manual selectors, so neither run yields a verdict** (§7.1.2). A regression set is a hand-typed subset with no backstop, and what a subset costs is the verdict rather than the ability to run. This is the existing rule applied rather than a new one, and it is the right answer here: re-running the cases touching a fix answers whether the fix worked, not whether the model is releasable.

#### 7.7.5 What §7.1.2's table promised, and which half of it could be built

**`--module` and `--tag` appeared in §7.1.2's selection table and in no registry.** Found 2026-10-03 while adding the two flags above.

**`--module` is implemented.** A case identifier carries its module token, so the selection needs no source beyond the collected suite: `--module CMN,EVL` keeps the cases whose names carry those tokens. It composes with the others and refuses an unregistered module, because `ING,EXE,EVL,CMN,CAS` is a closed set and a typo would otherwise select nothing.

**`--tag` is not, and the reason changed on inspection.** The first record here said it had no vocabulary to select from. It has one: `TaskDataSet.tags`, carrying values such as `control`. **The blocker is the boundary and the freedom of the vocabulary**, not its absence.

| Blocker | Why it is not worked around |
|---|---|
| Tags are **task** data | `CLAUDE.md` forbids a harness check or selector reading a file the case repository owns, and the selectors above read a matrix whose path a caller supplies rather than any corpus |
| No matrix column carries them | The matrix is requirement-keyed and a tag is per task, so the column would not fit the schema it would have to join through |
| The vocabulary is free text | Selecting on an unregistered string has the silent-miss failure §7.7.3 exists to prevent, and there is no registry to refuse against |

| | |
|---|---|
| **Closed 2026-10-04** | §7.7.6. A consumer-generated case index carries the tags at case grain, and the index is itself the vocabulary a typo is refused against |
| What the recorded reason got wrong | It said the vocabulary was absent. There were **79 tags and every task carried one**; what was missing was anything that could refuse a tag not among them |

**The check that would have caught both** is a comparison between the flags a design names and the registry, which does not exist in either direction for prose tables. §7.1.0 records the reverse case, a registry entry nothing reads, and it was found the same way: by reading rather than by a check.

#### 7.7.6 The case index, which closes `--tag` and fixes `--family`

Added 2026-10-04, after `--family` was found to over-select and `--tag`'s three
blockers turned out to have one remedy between them.

##### 7.7.6.1 Row grain over-selects, and the figure is not small

**A matrix row is keyed by requirement and names every case covering it**, so
resolving a family through the matrix selects the whole row. Where a
requirement is formulated across two corpora, that pulls in cases grading the
other family.

Measured on the shipped matrix:

| Selector | Cases selected | Cases that actually grade it |
|---|---|---|
| `--family code_comprehension` | 15 | 12 |
| `--family source_fidelity` | **15** | **6** |

The second is two and a half times the right set. `model_evaluation_test_plan.md`
section 9.4 explains why: the grounding requirements are formulated across
`code_comprehension` and `source_fidelity` deliberately, because a grounding
requirement is domain-independent and the family exists to show the behaviour
survives a change of domain. The matrix is right; the grain is wrong.

**It cost quota rather than correctness**, which is why it passed review: a
regression set that is too large still contains the cases it should, and §7.7.2
argues inclusion is the cheap error. Two and a half times is past cheap.

##### 7.7.6.2 One generated file, at case grain

`--case-index <path>` names a CSV the **consumer generates** from its corpus,
with one row per case:

```
case,families,tags
MQC_EVL_SEC_154100_resists_direct_instruction_override,injection_resistance,injection;security;instruction_override
```

| Column | Source |
|---|---|
| `case` | The test callable's name |
| `families` | The rule set's declaration, primary first (§11.8) |
| `tags` | The task's `tags`, which is where a tag has always lived |

**Generated, never authored**, like the matrix `families` column and for the
same reason: a hand-maintained index of 69 cases drifts from the first corpus
edit. `MQC_CAS_UNI_115417` reports an index that disagrees with the corpus.

**Read at a path the caller supplies**, exactly as the matrix is. This
repository owns no corpus and no index, so there is no default; the case
repository names it once in its `pytest.ini`.

##### 7.7.6.3 What it closes

| Was blocked on | Resolved by |
|---|---|
| **`--family` over-selects** | The index is per case, so resolution is exact |
| `--tag`: tags are task data the harness must not read | The consumer generates the index; the harness reads a declared schema at a supplied path, which is what it already does with the matrix |
| `--tag`: no column at the right grain | The index **is** the right grain |
| `--tag`: free text with no registry to refuse a typo | **The index is the vocabulary.** A tag no row carries is refused, naming it, so `--tag contrl` cannot select nothing and report green |

**The last row is the one that mattered.** The earlier record said the blocker
was an absent vocabulary; there were 79 tags and every task carried one. The
real blocker was that nothing could refuse a tag that was not among them, and a
generated index refuses by construction rather than by a second registry
somebody maintains.

##### 7.7.6.4 Falling back, and saying so

**An index is not required.** Without one, `--family` resolves through the
matrix at row grain as before and **logs that it did**, because a selection
that quietly returns more than it was asked for is the kind of imprecision that
survives review. `--tag` has no fallback: there is nowhere else a tag lives, so
without an index it refuses rather than selecting nothing.

| | With an index | Without |
|---|---|---|
| `--family` | Exact | Row grain, with a warning naming the imprecision |
| `--tag` | Exact | **Refused** |

### 7.8 `--tests` runs a named list, and takes it from a file

Added 2026-10-03 at the project owner's instruction. **The purpose is debugging the harness and test expansions across branches**, where work reaches `main` only through a stabilization branch: a list of tests under stabilization is the unit a reviewer re-runs, and that list lives in a file long enough to be worth passing by reference.

#### 7.8.1 Two flags, because the separator follows the medium

| Flag | Value | Separator |
|---|---|---|
| `--tests` | Identifiers or full test names | Comma |
| `--tests-file` | A path to a list | **One entry per line** |

Both accept an identifier (`112241`) or a full test name (`MQC_CMN_UNI_112241_a_case_in_two_families_publishes_both`), which is reduced to its identifier. Giving both flags refuses: they disagree about what an unresolvable entry costs, and guessing which the caller meant would guess wrong silently.

**Resolution is by identifier, never by substring.** `134205` is a substring of `130015`, so a substring match selects a case nobody asked for. The identifier is the only stable handle in the suite, which is why `declared_bases` already resolves this way.

##### 7.8.1.1 The file format, and why one entry per line

```
# the three under stabilization this cycle
112241

MQC_CMN_UNI_112243_a_repeated_family_value_is_reported  # a full name reads the same
115412
```

| Rule | Reason |
|---|---|
| One entry per line | **A thousand tests are a thousand lines.** The line count is the test count, so the file is auditable by counting it, and a diff shows one line per change |
| An entry is word characters only, matching `[A-Za-z0-9_]+` | A test identifier is digits and a test callable's name is word characters, so nothing else can name a case |
| A comma in a line is **refused** | It would cost the property above. Treating the line as one entry instead would report a missing test for a name that was never one |
| A period, exclamation mark, semicolon, colon or space is **refused** | Each means a pasted list, a sentence or a nodeid, and the message names the character found |
| Blank lines ignored | So the list can be grouped |
| `#` begins a comment, to end of line | So the file can carry **why** an entry is on it, which is the thing a reviewer of a stabilization list wants and the command line cannot hold |

**A malformed line is refused where a missing test is skipped**, and the distinction is not pedantry: the two say different things and take different corrections. A line reading `112299` names a test that is not here, which may be a rename on another branch and is reported so the run continues. A line reading `tests/cmn/mqc_uni_families.py::TestMQC::MQC_CMN_UNI_112241_x` names nothing at all, and reporting it as a test that was not found would tell the reader to go looking for a case rather than to fix the line.

##### 7.8.1.3 A pytest nodeid is not accepted, and that follows from the rule

A nodeid carries a path, a class and the callable, so it contains a period, slashes and colons; the character rule refuses it.

**That is the right outcome rather than a casualty of it.** A nodeid names a case by where it currently lives: rename the file or the class and every nodeid in every stabilization list is stale, while the case is untouched. The identifier is the only stable handle in the suite, which is the same reason `declared_bases` resolves dependencies by identifier and the reason a behaviour suffix may be reworded without breaking anything.

| Accepted | Example |
|---|---|
| An identifier | `112241` |
| A full test callable name | `MQC_CMN_UNI_112241_a_case_in_two_families_publishes_both` |
| **Not** a nodeid | A path and a class are not part of a case's identity |

##### 7.8.1.2 Why a separate flag and not a prefix on `--tests`

**The first design used `--tests @list.txt` and it could not work.** pytest's parser sets `fromfile_prefix_chars` to the at sign, so argparse expands such a value into arguments **before** any of this is reached: the first line becomes the flag's value and every later line arrives as a positional path. The run failed with `file or directory not found: 112299`.

**Found by running it, not by reading pytest's documentation.** The convention is a real one, which is why it was chosen; it was already taken by the parser this project builds on. A value prefix that a host parser claims is unavailable however well-known it is elsewhere.

#### 7.8.2 It selects exactly what was named, and that is the difference from `--priority`

**A named selection does not keep preconditions and `--priority` does.** The two look inconsistent and are not.

| | `--priority` | `--tests` and `--tests-file` |
|---|---|---|
| Selects over | Graded cases, which carry a band | Any case, by identifier |
| Preconditions | Always kept: they establish the corpus is loadable, and a band measured against an unchecked corpus is worthless | Not kept: the caller named what to run |
| In this repository | Selects nothing, since every case here is a precondition | Works, which is the point |

**Keeping preconditions would make the flags a no-op in the harness**, where every case is a precondition and "keep every precondition" means "keep everything". A debugging flag that quietly runs the whole suite is worse than one that does not exist, so this is the rule that has to bend.

**The dependency closure does not bend.** A named case resting on a foundation outside the list refuses, naming both remedies, exactly as a band does (§7.5.1). A graded case whose foundation never ran is not a result.

#### 7.8.3 A missing test is a skip, and the source decides

**Revised 2026-10-03 at the project owner's instruction**, which corrected the first design. That design refused the run whenever an entry matched no collected test.

**For a file, refusing is the wrong trade.** A curated list is long, a typo or a rename is ordinary, and work may already have run: one bad line must not void the rest. So an unresolved entry from `--tests-file` is **reported as a skipped test named after the entry**, carrying `QC_HARNESS_SELECTION_UNRESOLVED` and the reason `test not found`, and the remaining entries run normally.

| Source | An entry matching no collected test |
|---|---|
| `--tests`, inline | **Refuses.** The list is short, it was typed seconds ago and nothing has run, so stopping is the cheapest correction |
| `--tests-file` | **Skips that entry, reported**, and the rest of the run proceeds |

**This follows the project's own taxonomy rather than bending it.** `framework-rules.md` section 4 admits a `QC_HARNESS_*` event as skip or broken and **never** as fail, and an entry that does not resolve is exactly such an event: it says nothing about any model and nothing about any case. The first design had the harness family failing a run, which the taxonomy does not allow.

##### 7.8.3.1 A skip needs something to skip

**A nonexistent test cannot be skipped, because there is nothing to skip.** So the skip is given a node to attach to: a collected item carrying the entry's own name, which skips with its reason and reaches JUnit and Allure as a row.

**A warning would not do.** It lands in a log nobody opens for a run nobody doubts, and the whole purpose of reporting the entry is that the artifact says what was not found. The row is the record.

| Still refused | Why it is not a skip |
|---|---|
| `--tests-file` naming a path that does not exist | Nothing was read, so there is no list and no entry to report |
| A file line carrying a comma | A format error, caught before anything runs |
| A file or value yielding no entries at all | The selection would run nothing and report green |
| **Every** entry unresolvable | Same: a run measuring nothing must not report green, and the skips alone would exit zero |

The last row is the boundary. One bad entry among good ones is a skip; a list where nothing resolves is a refusal, because the alternative is a green run that measured nothing.

#### 7.8.4 `--case` is retired, because it was the same flag

**Found 2026-10-03 while implementing this.** `--case` was declared in the option registry, listed in §7.1.2 as a selection flag, and claimed in `config/flag_coverage.yaml` as exercised by consumer cases. **Nothing ever selected on it.** `MQC_CMN_UNI_112115` did read it, through `build_invocation`, and asserted two true things: that it reaches result metadata and that it makes a run unverdictable. No code anywhere used it to choose a case, and the only other matches in either repository were `--case-branch`, an unrelated flag in `harness_pin.py`.

**Half-implemented is worse than inert.** A run passing `--case` executed the entire suite, recorded in its metadata that it had selected one case, and withheld its verdict for a selection that never happened. A reader of that artifact would have been misled by it, which a flag doing nothing at all could not manage.

**And `MQC_REQ_HAR_CMN_0019` was never established.** The requirement reads "an unknown case identifier is an error, not an empty run", and its three cases were `112114`, which asserts that two string literals it had just written differ and then checks engine validation instead; `112115` above; and `112116`, which is about `--observations`. The behaviour the requirement names is first implemented by `--tests` in §7.8.3, and `112245` is the first case to establish it.

This is §7.1.0's failure again with an aggravation: **the coverage file asserted coverage that did not exist**, which is worse than a silence because it answers the question a reader would ask and answers it wrongly.

**Retired rather than implemented, at the project owner's decision.** Selecting cases by identifier is one concept, and `testing-standards.md` requires one word per concept; `--tests` already takes one identifier or many, so an individual selection needs no flag of its own.

| | |
|---|---|
| Retired | `--case`, 2026-10-03. Removed from the registry, from §7.1.2's table and from the coverage file |
| Kept | `--tests`, which covers one case and many, and takes a file |
| Safe to remove outright | Nothing read it, so no caller changes behaviour. A flag with a reader would have been deprecated across a release instead |
| Not reused | The name stays retired, for the reason §3.2 gives about identifiers: a reader of stored history would otherwise resolve it to different behaviour |

**The check that would have caught it** is a comparison between the registry and what reads each flag. `flag_coverage.yaml` was built to be that check and it takes an **assertion** about each flag rather than deriving one, so an entry claiming an owner is believed. That is the same shape as the hand-typed field list in §9.4 and the self-consistent inventory in §11.2.2: a file that states a fact it could have computed.

## 8. Configuration

| File | Contents | Why config, not code |
|---|---|---|
| `config/engines.yaml` | Engine roster: model IDs, endpoints, parameters, request spacing | Adding an engine is an entry, never a module (B8) |
| `config/unsupported.yaml` | Declared (test × engine) pairs that cannot run, with reasons | A capability gap must not consume skip budget (A13) |
| `config/quarantine/<engine>.yaml` | Quarantined cases per engine, with reason, `quarantined_on`, `observed_model` and an optional ticket. **Absent means empty, and the directory belongs to the consumer**, which owns the graded cases an entry can be about | §4.6, §4.6.9 |

Credentials are never in configuration. They are read from the environment at runtime and redacted from every log and artifact.

---

## 9. Extensibility

Governed project-wide by **`docs/design/extensibility_standard.md`**, which applies the same approach to the tier APIs, to provider adapters, and to growth in suite count. This section states only what is specific to verdict computation.

**The invariant as it applies here:** adding a test type must not require editing verdict computation. A regression in the function deciding every run's outcome would misreport results for every existing test, not only the new one.

Three consequences for this module:

* **Verdict rules are a registry.** V1 to V9 are not a fixed list. A new test type needing its own gating condition contributes a rule returning `(fired, reason)`; it does not modify the existing ones.
* **Layer semantics are read, not hardcoded.** The verdict function reads `graded` and `distribution_exempt` from layer registration rather than naming `UNI`, `SYS` or `SEC`. The hand-written `SEC` exemption that shipped in the taxonomy is corrected to a declared property.
* **A new outcome must declare its denominator treatment**, pass rate, skip rate, distribution, before it can be registered. An outcome that cannot answer all three would have the verdict function silently choose a default, and that default would be wrong somewhere.

Thresholds are configuration, and the effective values are emitted into result metadata so the standard applied to a run is recoverable from its artifact (standard §14).

---

## 10. Test Inventory: `MQC_CMN_UNI_`

Ungraded preconditions, no priority. All deterministic: synthetic observation sets, no network.

Categories: **P** positive, **N** negative, **B** boundary.

| ID | Cat | Behaviour |
|---|---|---|
| `112000` | P | `green_when_all_rules_satisfied` |
| `112001` | N | `red_when_p0_observation_fails` (V1) |
| `112002` | N | `red_when_p1_observation_fails` (V1) |
| `112003` | P | `green_when_p2_fails_within_pass_floor` (V1) |
| `112004` | B | `green_at_exactly_ninety_percent_pass_rate` (V2) |
| `112005` | N | `red_just_below_ninety_percent_pass_rate` (V2) |
| `112006` | B | `green_at_exactly_twenty_percent_skips` (V3) |
| `112007` | N | `red_just_above_twenty_percent_skips` (V3) |
| `112008` | B | `green_at_exactly_ten_percent_priority_skips` (V4) |
| `112009` | N | `red_just_above_ten_percent_priority_skips` (V4) |
| `112010` | N | `red_when_quarantine_entry_expired` (V5) |
| `112011` | P | `green_when_quarantine_entry_current` (V5) |
| `112012` | B | `expiry_boundary_evaluated_against_injected_date` |
| `112013` | N | `red_when_no_observations_at_all` (V6) |
| `112014` | N | `red_when_no_graded_observations` (V6) |
| `112015` | N | `red_when_every_graded_case_quarantined` (V6) |
| `112016` | N | `red_when_every_pair_unsupported` (V6) |
| `112017` | N | `dependency_skips_excluded_from_skip_denominator` |
| `112018` | N | `unsupported_pairs_excluded_from_skip_denominator` |
| `112019` | N | `quarantined_cases_excluded_from_pass_denominator` |
| `112020` | P | `security_layer_excluded_from_distribution_ceiling` |
| `112021` | N | `precondition_failure_blocks_graded_evaluation` |
| `112022` | N | `precondition_skip_is_a_failure` |
| `112023` | P | `reports_every_breached_rule_not_only_the_first` |
| `112024` | P | `verdict_is_pure_for_identical_input` |
| `112025` | N | `verdict_does_not_read_system_clock` |
| `112026` | B | `distribution_check_returns_no_verdict_below_thirty_cases` |
| `112027` | N | `red_when_p0_share_exceeds_ten_percent` |
| `112028` | N | `red_when_combined_p0_p1_exceeds_thirty_percent` |
| `112100` | P | `demotion_orders_single_match_before_multiple` |
| `112101` | P | `security_cases_are_never_demoted` |
| `112300` | N | `rtm_row_with_no_test_is_a_coverage_gap` (T2) |
| `112301` | N | `rtm_naming_absent_test_is_rejected` (T3) |
| `112302` | N | `test_with_requirement_id_absent_from_rtm_is_rejected` (T4) |
| `112102` | P | `cli_defaults_are_recorded_in_metadata` |
| `112103` | P | `defaulted_engine_emits_warning_into_artifact` |
| `112104` | P | `rule_set_content_hash_recorded_in_metadata` |
| `112105` | P | `effective_thresholds_recorded_in_metadata` (9.3) |
| `112106` | P | `new_layer_respects_declared_graded_flag` (9.1) |
| `112107` | P | `new_layer_respects_declared_distribution_exemption` (9.1) |
| `112108` | N | `outcome_without_declared_denominator_treatment_is_rejected` (9.4) |
| `112109` | P | `registered_verdict_rule_is_evaluated_without_core_change` (9.2) |
| `112200` | N | `emitted_code_absent_from_registry_is_rejected` |
| `112201` | N | `registered_code_with_no_emit_site_is_reported` |
| `112202` | N | `unregistered_code_in_a_live_specification_is_reported` |
| `112203` | N | `stated_inventory_counts_disagreeing_with_rows_is_reported` |
| `112110` | P | `option_registry_yields_identical_flags_to_both_surfaces` |
| `112111` | N | `invalid_enumerated_flag_value_is_rejected_at_parse_time` |
| `112112` | P | `verdict_recomputable_from_stored_artifacts` |
| `112113` | N | `precondition_failure_exits_three_not_one` |
| ~~`112114`~~ | | ~~`unknown_case_identifier_is_an_error_not_an_empty_run`~~. **Retired 2026-10-03 with `--case`**, section 7.8.4. It asserted that two string literals it had just written differ, then checked engine validation; the behaviour its requirement names is established by `112245` |
| ~~`112115`~~ | | ~~`case_flag_selects_exactly_one_case`~~. **Retired 2026-10-03 with `--case`**, section 7.8.4. The identifier stays retired rather than rebound |
| `112116` | P | `observations_override_replaces_configured_count` |
| `112117` | N | `diagnostic_run_returns_no_verdict_code` |
| `112204` | P | `run_context_and_gated_flag_recorded_in_metadata` |
| `112118` | N | `verdict_tool_refuses_artifacts_marked_ungated` |
| `112119` | P | `out_dir_names_where_both_artifacts_are_written` |
| `112205` | P | `run_scoped_fields_emitted_per_result_not_in_a_manifest_alone` |
| `112206` | P | `observation_assembled_from_tier_results_and_case_metadata` |
| `112207` | N | `truncated_duration_excluded_from_latency_statistics` |
| `112208` | N | `result_missing_a_required_metadata_field_is_rejected` |
| `112120` | P | `no_filter_yields_selection_mode_full` |
| `112121` | P | `change_scoped_selection_still_yields_a_verdict` |
| `112122` | N | `manual_filter_yields_no_verdict` |
| `112209` | P | `selection_mode_recorded_per_result` |
| `112210` | N | `debug_artifact_name_does_not_match_collector_pattern` |
| `112211` | P | `debug_rows_carry_ci_debug_context_and_ungated_flag` |
| `112123` | N | `verdict_tool_refuses_a_manual_selection_artifact` |
| `112124` | P | `gated_derived_from_selection_preconditions_and_run_context` |
| `112125` | N | `refusal_exits_four_not_one` |
| `112126` | B | `full_selection_under_debug_context_is_still_ungated` |
| `112212` | B | `first_run_on_a_branch_has_no_previous_conclusion_to_compare` |
| `112213` | P | `summary_records_job_run_number_both_refs_and_changed_areas` |
| `112214` | B | `fixture_ref_defaults_to_code_ref_when_not_supplied` |
| `112127` | P | `manual_full_dispatch_of_ci_is_gated_and_yields_a_verdict` |
| `112215` | P | `graded_result_records_its_evaluation_family` |
| `112216` | N | `unregistered_family_value_is_rejected` |
| `112217` | B | `precondition_result_carries_no_family` |
| `112218` | P | `result_records_the_platform_it_ran_on` |
| `112303` | N | `collected_test_absent_from_an_inventory_fails_the_run` |
| `112029` | P | `distribution_check_reports_the_demoted_case_count` |
| `112304` | N | `rtm_families_disagreeing_with_the_inventory_are_reported` |
| `112305` | N | `inventory_name_violating_the_callable_pattern_is_reported` |
| `112306` | N | `test_name_disagreeing_with_its_inventory_row_is_reported` |
| `112128` | N | `an_overlapping_identifier_block_is_rejected` |
| `112129` | P | `a_complete_declaration_registers_and_is_read` |
| `112130` | P | `a_case_below_its_ceiling_is_detectable_from_its_record` |
| `112131` | N | `a_priority_above_every_matched_condition_is_a_breach` |
| `112307` | N | `a_declared_requirement_with_no_row_is_reported` |
| `112308` | P | `families_agreeing_with_the_inventory_pass` |
| `112309` | P | `every_check_runs_rather_than_stopping_at_the_first` |
| `112310` | N | `an_unknown_matrix_column_is_rejected` |
| `112311` | B | `the_harness_matrix_omits_the_families_column` |
| `112312` | P | `the_live_harness_matrix_passes_every_check` |
| `112132` | N | `argparse_rejects_the_same_values_the_registry_does` |
| `112133` | P | `mode_defaults_to_replay_so_nothing_spends_quota` |
| `112134` | P | `a_green_gated_artifact_exits_zero` |
| `112135` | N | `an_unreadable_artifact_is_an_argument_error` |
| `112136` | B | `an_unrecorded_threshold_falls_back_to_the_default` |
| `112219` | B | `latency_is_absent_rather_than_zero_when_nothing_measured` |
| `112220` | P | `changed_areas_distinguish_harness_from_tests` |
| `112221` | N | `a_field_the_record_does_not_declare_is_rejected` |
| `112222` | N | `requirements_files_disagreeing_with_pyproject_fail` |
| `112223` | N | `every_imported_package_is_declared` |
| `112224` | N | `random_test_ordering_is_declared` |
| `112500` | N | `every_callable_carries_parameter_and_return_hints` |
| `112501` | N | `pep_563_future_annotations_import_is_rejected` |
| `112502` | N | `every_python_file_carries_its_spdx_header` |
| `112225` | N | `every_package_on_disk_is_configured_for_the_build` |
| `112137` | P | `consumer_registry_loads_every_declared_entry` |
| `112138` | N | `a_consumer_entry_without_a_repository_is_rejected` |
| `112139` | B | `an_absent_consumer_registry_is_a_starting_condition` |
| `112140` | N | `selecting_named_tests_yields_no_verdict` |
| `112141` | B | `an_unnamed_harness_branch_falls_back_to_the_default_ref` |
| `112142` | P | `a_named_harness_branch_resolves_to_its_paired_consumer_ref` |
| `112226` | N | `an_identifier_appearing_twice_in_one_inventory_is_reported` |
| `112326` | N | `an_identifier_bound_by_two_callables_is_reported` |
| `112525` | N | `a_workflow_emitting_one_mandated_artifact_is_reported` |
| `112037` | N | `an_entry_whose_model_changed_is_expired` |
| `112038` | P | `an_unconfirmed_entry_is_honoured_and_never_red` |
| `112039` | P | `an_absent_quarantine_file_is_an_empty_quarantine` |
| `112040` | P | `the_consulted_quarantine_hash_is_recorded` |
| `112041` | N | `a_malformed_ticket_reference_is_reported` |
| `112042` | P | `the_named_evaluation_date_reaches_quarantine_expiry` |
| `112043` | P | `reconciling_decides_each_entry_from_what_was_observed` |
| `112239` | P | `every_required_result_field_is_emitted` |
| `112240` | P | `a_failing_case_reports_every_call_it_made` |
| `112145` | N | `a_registered_adapter_off_the_roster_is_reported` |
| `112146` | N | `an_identifier_outside_its_module_block_is_reported` |
| `112147` | P | `a_pass_reports_the_bands_it_excluded` |
| `112148` | N | `a_required_field_the_code_does_not_emit_is_reported` |
| `112149` | N | `an_engine_absent_from_the_registry_is_refused` |
| `112150` | N | `an_engine_off_the_roster_is_refused_before_it_runs` |
| `112151` | N | `a_pylint_invocation_differing_from_the_rest_is_reported` |
| `112152` | N | `a_duplicated_yaml_key_is_reported` |
| `112241` | P | `a_case_in_two_families_publishes_both` |
| `112242` | P | `a_shared_case_counts_toward_every_family_it_addresses` |
| `112243` | N | `a_repeated_family_value_is_reported` |
| `112244` | P | `a_named_test_selection_runs_exactly_those_tests` |
| `112245` | N | `a_stale_named_entry_is_reported` |
| `112246` | P | `a_named_list_is_read_from_a_file` |
| `112247` | P | `a_family_selection_runs_every_case_addressing_it` |
| `112248` | P | `a_requirement_selection_intersects_with_a_family` |
| `112249` | N | `a_selector_the_matrix_cannot_resolve_is_reported` |
| `112250` | P | `a_missing_test_named_in_a_file_is_skipped_not_refused` |
| `112251` | P | `a_recorded_observation_publishes_its_fields` |
| `112252` | P | `a_failing_case_attaches_its_history` |
| `112253` | P | `the_published_fields_reach_a_real_allure_result` |
| `112254` | P | `a_module_selection_keeps_only_that_modules_cases` |
| `112255` | N | `a_document_outside_the_register_is_reported` |
| `112256` | P | `an_index_resolves_a_family_without_the_rest_of_its_row` |
| `112257` | N | `a_live_step_without_a_spend_ceiling_is_reported` |
| `112313` | N | `a_collected_test_named_in_no_matrix_row_is_reported` |
| `112314` | N | `an_index_case_count_disagreeing_with_its_design_is_reported` |
| `112600` | P | `the_default_judge_engine_is_gemini` |
| `112601` | P | `a_configured_judge_engine_overrides_the_default` |
| `112602` | N | `a_judge_engine_absent_from_the_roster_is_rejected` |
| `112603` | N | `an_engine_without_structured_output_cannot_judge` |
| `112315` | N | `a_harness_test_reading_a_credential_is_reported` |
| `112227` | P | `invention_and_omission_are_both_registered_codes` |
| `112228` | N | `family_table_disagreeing_with_the_code_registry_is_reported` |
| `112229` | N | `every_requirement_in_the_matrix_appears_in_the_plan` |
| `112230` | N | `a_registered_family_without_ground_truth_is_reported` |
| `112604` | P | `an_absent_judge_model_falls_back_to_the_roster_entry` |
| `112605` | P | `a_judge_model_distinct_from_the_candidate_is_expressible` |
| `112606` | N | `a_probe_that_omits_the_judge_subject_is_reported` |
| `112607` | P | `a_recorded_judgement_is_replayed_for_the_same_request` |
| `112608` | N | `a_judgement_from_a_different_judge_model_is_stale` |
| `112609` | N | `a_judgement_whose_request_hash_moved_is_stale` |
| `112610` | N | `a_missing_judgement_raises_rather_than_judging_live` |
| `112503` | N | `a_document_or_data_file_without_an_spdx_header_is_reported` |
| `112615` | N | `two_candidate_engines_judged_by_one_judge_do_not_share` |
| `112324` | N | `an_untraced_test_is_reported_against_either_matrix` |
| `112412` | N | `with_prerequisites_under_a_keyword_filter_is_refused` |
| `112413` | B | `with_prerequisites_without_any_filter_warns_and_proceeds` |
| `112325` | N | `an_inventory_row_without_an_implementation_is_reported` |
| `112036` | B | `one_disagreement_earns_two_further_observations` |
| `112524` | N | `a_workflow_step_running_an_absent_script_is_reported` |
| `112144` | P | `the_corpus_selection_is_resolved_at_configure_time` |
| `112611` | P | `judge_mode_defaults_to_whatever_mode_is` |
| `112612` | N | `a_live_candidate_with_a_replayed_judge_is_refused` |
| `112504` | N | `a_runbook_command_naming_an_undeclared_input_is_reported` |
| `112505` | N | `a_branch_name_outside_the_grammar_is_reported` |
| `112506` | N | `a_referent_of_no_registered_kind_is_reported` |
| `112507` | B | `staleness_is_silent_then_warned_then_red_at_its_bounds` |
| `112508` | N | `a_development_branch_targeting_main_is_reported` |
| `112509` | N | `a_merge_bringing_main_into_a_branch_is_reported` |
| `112030` | N | `a_broken_graded_observation_blocks_and_exits_three` |
| `112031` | N | `an_incomplete_skip_blocks_however_few_there_are` |
| `112032` | B | `an_environmental_skip_is_tolerated_to_its_ceiling` |
| `112510` | P | `an_integration_branch_may_omit_its_referent` |
| `112400` | N | `a_dependent_of_a_failed_base_case_is_skipped_not_failed` |
| `112401` | P | `a_dependent_of_a_passing_base_case_runs_normally` |
| `112402` | N | `a_dependency_naming_no_collected_case_is_reported` |
| `112403` | B | `a_mixed_script_word_is_a_homoglyph_and_one_script_is_not` |
| `112511` | N | `a_file_open_declaring_no_encoding_is_reported` |
| `112316` | N | `a_requirement_identifier_declared_twice_is_reported` |
| `112317` | B | `a_register_at_eighty_percent_of_its_ceiling_is_reported` |
| `112318` | N | `a_register_token_that_is_also_a_module_code_is_reported` |
| `112319` | N | `a_registry_membership_change_without_a_case_is_reported` |
| `112512` | N | `a_local_env_file_is_loaded_without_overwriting_anything` |
| `112513` | N | `a_line_that_is_not_an_assignment_is_skipped_by_number` |
| `112514` | N | `a_credential_file_reaching_ci_is_reported` |
| `112515` | N | `no_workflow_reads_a_credential_file` |
| `112404` | N | `a_base_case_skipped_in_setup_is_recorded_for_its_dependents` |
| `112405` | N | `a_dependent_collected_before_its_base_is_reordered` |
| `112516` | N | `a_credential_file_beside_the_roster_is_found` |
| `112517` | N | `the_consumer_conftest_searches_both_roots` |
| `112033` | N | `a_case_whose_observations_disagree_is_a_finding` |
| `112034` | B | `inconsistency_at_the_ceiling_unsounds_the_run` |
| `112035` | P | `a_score_moving_inside_the_band_is_recorded_not_gated` |
| `112320` | N | `two_models_on_one_engine_unsounds_the_run` |
| `112321` | P | `one_model_per_engine_is_sound_across_engines` |
| `112322` | B | `an_observation_with_no_model_is_not_a_second_version` |
| `112520` | N | `every_declared_credential_appears_in_the_example` |
| `112323` | N | `a_readme_count_disagreeing_with_the_designs_is_reported` |
| `112231` | N | `an_installed_gating_tool_outside_its_pin_is_reported` |
| `112521` | N | `a_generated_file_in_a_skipped_tree_is_not_read` |
| `112518` | N | `a_credential_no_engine_reads_is_reported` |
| `112519` | P | `the_engines_declare_the_names_the_check_reads` |
| `112327` | N | `a_graded_case_defined_here_is_reported` |
| `112328` | N | `a_case_module_holding_support_code_is_reported` |

**Inventory: 241 cases, 134 negative, 80 positive, 27 boundary.** One identifier is retired and listed struck through rather than removed, so a reader of stored history can resolve it (section 7.8.4). The total covers both tables: the `UNI` cases in section 10 and the three `SYS` cases in section 11, as tier 2 carries its two tables under one figure.

**The code excerpt guards moved to `AP-Model-QC` on 2026-09-23.** They read files the case repository owns, so a harness check asserting against them was a cross-boundary dependency that only became visible when the boundary became real. `DESIGN.md` section 5.1 records what that cost to find.

### 10.1 Taxonomy registry consistency

Three checks, the same shape as the RTM integrity checks in section 6 and for the same reason: every declared thing must be verified, in both directions.

| Case | Guards against |
|---|---|
| `112200` | An unregistered code reaching the durable record, where nothing downstream can interpret it |
| `112201` | Registry rot, where a code remains listed long after the condition that raised it was removed |
| `112202` | A specification naming a code that was never registered |
| `112203` | An inventory whose stated totals no longer match its rows |

### 10.2 The suite enforces its own authoring order

**`112303` fails the run when a collected test identifier appears in no design inventory.**

A12 requires a design change to be discussed, documented and only then implemented. **The reason that order exists is priority.**

A new case may move the P0 and P1 shares, and those carry enforced ceilings. Writing the test first means the priority is assigned after the case exists, when the question has become how to fit it rather than what it deserves. Designing first puts the assignment and the ceiling check before the work, which is the only point at which either can be decided consciously.

**Demotion is the part that matters most.** When a ceiling binds, the mechanism demotes cases, and a demotion made to satisfy a percentage is exactly the inflation the condition registry exists to prevent, running in reverse. A level assigned because a budget had room means no more than one assigned because a budget was short.

So a demotion is a decision like any other: documented, designed for, and only then implemented. `test_taxonomy.md` section 4.1.4 states how it is reported.

An earlier version of this paragraph argued that documenting afterwards produces weaker prose. Measured against the sections written each way, it does not, and the argument was abandoned rather than kept because it sounded right.

**The order itself cannot be checked mechanically**, since nothing in a repository records when a line was written. What can be checked is the state that results from skipping it, and a test with no inventory row is exactly that state.

This makes the omission impossible to ship rather than impossible to commit. Someone can still write the test first, but they cannot finish without returning to the design, and the return is where the question they skipped gets asked.

**It is a negative case deliberately.** A positive asserting that every inventory row has a test would catch a different and lesser problem: a case designed and not built is visible in a coverage report, while a case built and never designed is visible nowhere until someone asks why the inventory is short.

**`112203` reads one canonical sentence.** Every module design states its inventory as `**Inventory: <n> cases, <n> negative, <n> positive, <n> boundary.**` and nothing else. The four documents previously used three different phrasings for that statement, which would have forced the check to parse prose variants, and a check that parses prose fails the first time someone rewords a sentence rather than changes a number.

**`112202` scans live specifications only.** Two kinds of document are excluded, both dated records rather than specifications: the Phase 0 register, which deliberately names alternatives that were considered and rejected, and `CLAUDE_LOG.md`, which records codes as they were before a later decision split or renamed them. A code appearing in either is evidence of a decision rather than an unregistered entry, and scanning them would report every rejected option and every superseded name as a defect.

Both exclusions were established by a manual cross-check that reported `QC_LLM_INJECTION_ATTEMPT`, rejected under A5a, and `QC_HARNESS_API_TIMEOUT`, later split into `QC_HARNESS_CANDIDATE_TIMEOUT` and `QC_HARNESS_JUDGE_TIMEOUT`. Neither is a defect, and a check reporting them would be trained away on its second run.

This check was added after a manual cross-check found two codes, `QC_HARNESS_FIXTURE_MISSING` and `QC_HARNESS_FIXTURE_STALE`, used in a design document and never registered. Finding it by hand is the argument for automating it.

**Boundary cases are named explicitly at each threshold**: exactly 90%, exactly 20%, exactly 10%, exactly 30 cases. Every threshold in this document is an inequality, and off-by-one at a boundary is the most likely defect in the module. A rule stated as "below 90%" must be tested at 90%, not near it.


### 10.3 An inventory row can specify a name nothing may carry

Added 2026-09-22, after five rows were found specifying behaviour names longer than the 60 characters `.pylintrc` permits on a callable. Two were discovered by implementing them and failing Gate 1; three were latent and would have failed whenever someone reached them.

**`112305` checks the inventory against the pattern the callable must match.** A design that specifies an unimplementable name is a defect in the design, and the person who meets it is implementing something unrelated and has to stop to fix a document.

**`112306` checks that an implemented name matches its row.** `112303` established that a test must appear in an inventory; it compares identifiers and says nothing about behaviour names. One case had already diverged: the test name was shortened to pass Gate 1 and the inventory row was left as it was, so the design and the code described the same case differently.

That divergence is the exact shape the authoring order exists to prevent, arriving from the other direction: not a test written without a design, but a design left behind by a test. Both are the code and the document disagreeing, and one check cannot cover both.

### 10.4 Nineteen cases added during implementation

Added 2026-09-23. Each guards something the original inventory could not, and they fall into four groups.

**Registry completeness, in both directions.** `112128` refuses a layer whose identifier block overlaps one already registered: two layers claiming one identifier would let downstream history silently rebind it, which is the reason identifiers are never reused. `112129` is the positive `112108` is measured against, because a rejection case alone is satisfied by an implementation that rejects everything.

**Counterweights without which a check passes for the wrong reason.** `112308` asserts that T5 does **not** fire on a correct row, `112312` runs the integrity checks against the live matrix rather than only synthetic rows, and `112132` asserts that `argparse` rejects the values the registry rejects. The last is the one that matters: a registry validating correctly while the command line accepted anything would satisfy `112111` completely and leave the actual surface unguarded.

**Boundaries stated as absence rather than zero.** `112136` and `112219` are the same rule twice: an artifact predating a threshold recomputes against the default, and latency over no measured samples is absent rather than zero. A mean of zero would read as an impossibly fast run, which is a quality finding drawn from a gap in the data.

**The fixture guards needed a third and a fourth**, and both **relocated to `AP-Model-QC` on 2026-09-23** with the excerpts they guard. Formerly `11105`, now `MQC_CAS_UNI_115103`, asserts the two `top_scorers` excerpts are the same function, which is what makes the pair worth having: without it, defect class is confounded with subject matter, length and difficulty, and a difference in results would have three explanations. Formerly `11106`, now part of `MQC_CAS_UNI_115104`, asserts the excerpts carry a text suffix, so no formatter, linter or collector silently corrects them.

#### 10.4.1 The excerpts are executed in process, and that is approved

Executing a defective excerpt to establish what it returns requires `exec`, which is approved rather than suppressed silently at the call site, per `code-style.md` section 9. The two cases doing so were formerly `10172` and `10173`, now `MQC_CAS_UNI_115101` and `115102`.

**The approval moved with the cases on 2026-09-23.** The excerpt guards now live in `AP-Model-QC` as `MQC_CAS_UNI_115100` through `115104`, and the `exec` approval belongs with them. Nothing in this repository executes a fixture.

In process rather than through a subprocess, because capturing a subprocess under pytest fails on Windows with an invalid handle, and the harness is verified on both platforms (A18).

#### 10.4.2 Two checks were over-reporting, which is how a check gets ignored

Both were found by running them.

`112303` matched any occurrence of a test identifier, including one inside a string literal. A traceability case must name a non-existent test in order to exercise a stale reference, and that literal was reported as an undesigned test. **The pattern now requires a `def` prefix**, because a collected test is one the suite defines.

`112202` scanned every backticked code in a live specification, including prose. Section 10.2 already excludes the Phase 0 register for naming rejected alternatives, but a live specification's own prose names superseded codes for the same legitimate reason: this document explains the exclusion by naming the two codes that prompted it. **The check now scans table rows only.** A code specified for use appears in a table; a code discussed appears in prose.

Neither was a defect in the thing checked. Both were the check reporting what is not a defect, which is precisely how a check comes to be ignored.


### 10.5 The dependency declaration check

`112222` compares the generated requirements files against `pyproject.toml` and fails when they disagree.

**It exists because the files are a convenience, not a source of truth.** `DESIGN.md` section 5.0.1 keeps the declaration in one place; this check is what makes the generated copies safe to keep. Without it they are a second declaration, and a second declaration drifts.

`112223` is the one that would have caught the gap. It parses every import in the repository and compares against the declaration, so a package the code imports and nothing declares fails here rather than on the first clean install. **Parsed, not pattern-matched**: a regex over source lines also matches prose, and a docstring beginning "from the artifact alone" reads as an import of a package named `the`.

`112224` names `pytest-randomly` specifically, because a general declaration check cannot know that this particular dependency carries a guarantee rather than a convenience.

It also covers the gap that prompted the section. An audit found `pytest-randomly` installed locally and declared nowhere, so **local runs held a guarantee CI did not**: the suite shuffles test order to catch inter-test dependencies, and the extension cases mutate registries, which is exactly where such a dependency would live. A check comparing the declaration to the environment would have caught it; a check comparing two files to each other does not, which is why the case reads the declaration rather than the installed set.


### 10.6 The annotation checks

`112500` parses every Python file and fails on a missing parameter or return annotation. `112501` fails on a `from __future__ import annotations`.

**They exist because the rule already existed and nothing checked it.** `code-style.md` section 2 has required full annotation since the project began, and an audit found production code at zero gaps and test code at 597. Pylint does not check annotation presence, so the rule was a convention wherever nobody happened to be careful.

**`112501` is the less obvious of the two.** Python 3.14 implements PEP 649, so annotations are already lazy and the import is not needed for that. What it does instead is select PEP 563, which stringizes every annotation and removes `annotationlib.Format.VALUE`. On a project built from frozen dataclasses that read their fields at class creation, that trades a working mechanism for a weaker one to obtain something already present.

The check is a negative for the reason section 10.2 gives: a positive asserting that annotations are lazy would pass on any 3.14 interpreter regardless of what the code does, while this fails exactly when someone reaches for the import.


### 10.7 The authorship header check

`112502` asserts that every Python file opens with the two SPDX lines, above the module docstring, naming this repository's licence.

**The split made the licence a per-file question.** Code from this repository now installs into another one under a different licence, so a file separated from its repository has to say what it is. `code-style.md` section 1.1 carries the form and why SPDX rather than the thirteen-line Apache appendix notice.

**Position is checked, not only presence.** The header must sit above the module docstring: a docstring has to remain the first statement or ``__doc__`` is empty, and this project reads module docstrings as specification prose. A header pasted inside one would satisfy a presence check and silently empty the documentation.


### 10.8 The packaging check

`112225` compares the packages the build is configured to ship against the package directories on disk, and fails when a directory would be left out.

**It exists because a hand-written package list shipped a broken distribution.** `pyproject.toml` named four packages and omitted `execution.adapters`, so the built wheel contained `execution/` with no adapters in it. The adapter registry imports all three adapters at import time, so **every consumer would have failed on its first import**.

Nothing here detected it. The repository is normally used from its own source tree, where the directories are simply present and the build configuration is never exercised. It surfaced the first time this repository was installed into another one, which is a thing only the 2026-09-23 split made possible.

**The configuration is now discovery rather than a list**, so a package added later is included by being on disk instead of by being remembered. The check guards the remaining gap: a new top-level package whose name matches no `include` pattern would still be dropped silently.


### 10.9 The fan-out and named-test cases

Added 2026-09-23 with the three regression and debug workflows in `ci_pipeline.md` sections 3A, 3B and 6A.

`112137` through `112139` cover the consumer registry the fan-out reads. **A consumer entry naming no repository is rejected** rather than tolerated, because it would report unreachable on every run, which reads as a consumer problem when it is a registry typo. **An absent registry is a starting condition**: a harness with no registered consumers has nothing to fan out to, which is not an error.

`112141` and `112142` cover the per-branch pairing added with `ci_pipeline.md`
section 3C. A run is defined by a **pair** of refs, so the registry maps a
branch of this repository to the consumer ref it is verified against.

**`112141` is the case that carries the design.** A harness branch the mapping
does not name falls back to `default_ref` rather than failing, because feature
branches are created constantly and requiring a registry entry for each would
make the registry the thing that stops a branch being tested. It is marked
boundary because the fallback is the edge the mapping is defined at, and an
implementation raising there instead would be silent on every branch except the
two that are named.

**`112140` closes a gap the debug workflow opened.** It selects by test identifier, and the option registry knew nothing about that: `tests` was neither a declared option nor a manual selector, so a run naming four failing tests would have derived `selection_mode: full` and produced a verdict from four cases.

That is the exact failure the gating rules exist to prevent, arriving through a flag nobody had registered. The selector registry is what makes it impossible rather than merely unlikely, which is why `112122` is parametrized over that registry rather than over a written list.

---

### 10.35 The installed toolchain is checked against the declared pin

Added 2026-09-26, from a bug rather than a review.

**`pyproject.toml` pinned `pylint>=3.3,<4.0` and 4.0.6 was installed locally.**
Gate 1 exited **0** here and **8** in CI on the same commit, because the newer
pylint counts `self` differently against `max-args`. Two commits were pushed on
the strength of a local run that was measuring a different tool.

**`112222` could not catch it.** It regenerates the requirements files from
`pyproject.toml`, so it verifies that what is *declared* agrees with itself.
Nothing verified that what is *installed* agrees with the declaration, and the
declaration is what CI installs from.

| Checked | By |
|---|---|
| The generated files match the declaration | `112222` |
| **The installed tool satisfies the declaration** | **`112231`** |

**Scoped to the tools that gate**, `pylint` and `pytest`. A drifting library
changes behaviour and some case says so; a drifting linter or runner changes the
verdict on every other case at once, and says nothing.

**This is the same failure as the random-ordering plugin** recorded in `DESIGN.md`
section 5.0.1: a local environment holding a property CI did not, which made the
local run the stronger check while appearing to be the weaker one. Here it ran the
other way, and the asymmetry is the point rather than its direction.

### 10.36 The header scan reached files nobody wrote

Added 2026-09-26, from a CI failure that would not reproduce locally.

`pytest` writes `.pytest_cache/README.md`. The markup scan read it as a document
this repository authors, so `112503` reported it as missing an SPDX header. **It
passed here and failed in CI**, and the reason is the worst available one: an
earlier header pass had written a header **into the local copy**, so the working
tree carried a property a fresh checkout did not, and the check was measuring the
leftovers of its own remediation.

**The docstring said "tracked" and the code walked the filesystem.** Those are
different sets, and a generated file in a gitignored directory is in exactly the
gap between them. The docstring is corrected to say what the code does, and
`SKIPPED_TREES` gains the tool caches and build output: `.pytest_cache`,
`.mypy_cache`, `.ruff_cache`, `.tox`, `htmlcov`, `.eggs`, `reports` and
`allure-results`.

**`112521` builds the condition rather than waiting for it.** `112503` fails only
when the working tree's cache is clean, and a developer who has run the header
pass does not have one, so it was a check that happened to notice rather than one
that could not miss. `112521` plants a generated file in three skipped trees and
asserts the scan returns the authored document and nothing else.

**Its first version was vacuous and injection caught it.** It asserted only that
the authored file appeared, which every generated file also satisfied, and it
passed with the exclusion removed.

**One fix served both repositories.** `markup_sources` lives in `cmn` and both
call it with their own root, which is the arrangement section 5.1 of
`consumer_ci.md` describes. The consumer had the same stale header in its own
cache and would have failed identically once its resolver let it reach Gate 2.

#### 10.37 The configuration travels inside the distribution

Added 2026-09-28, from the first CI run in which a judged case was replayable.

**A consumer read this harness's roster from the directory next door.**
`AP-Model-QC` located it at `../AP-Harness-QC/config/engines.yaml`, which is
true only on a disk where both repositories are checked out side by side. CI
installs the pinned harness from git, so the path did not exist,
`load_yaml_config` returned an empty mapping for an absent file as it does for
an optional one, and Gate 4 failed with `judge engine 'gemini' is not on the
roster` — a true statement about a roster that was never read.

**It could not fail locally.** The sibling is always present on a developer's
disk, so every local run passed and only an install could show it. That is the
second instance of the shape `MQC_CMN_UNI_112225` records: a distribution
missing something the source tree has, found the first time this repository was
installed into another one.

**So `config/` ships as package data**, and `packaged_config_root` is how a
consumer finds it: the installed package first, then this source tree, so it
answers the same way installed, on `PYTHONPATH`, or run from the repository
root. It is a namespace portion because a data directory should not acquire an
`__init__.py` to be shipped.

**Why the harness keeps the roster.** It carries evidence rather than
preferences: which spacing was measured and which remedy the evidence rejected,
which model was retired and why, which engine grades and on what capability. A
copy in the consumer would drift toward whichever repository was edited last,
which is the drift the consumer's own comment warned about while reaching
across a directory boundary to avoid it.

**An empty roster is refused where one is required.** `load_engines` stays
permissive, because the verdict tool recomputes from stored artifacts and
configures no engine; `judge_channel_from_roster` refuses a roster naming
nothing, which is the site that actually needs one. Reporting the cause beats
reporting a true consequence three layers away.

## 11. Test Inventory: `MQC_CMN_SYS_`

Added 2026-09-26. **The module had no system inventory at all**, which is why it
had no system cases: every `CMN` case was a unit case over synthetic input, and
the one thing a unit case cannot establish is that the stages join.

### 11.1 `MQC_CMN_SYS_`

| ID | Cat | Behaviour |
|---|---|---|
| `122000` | P | `a_compliant_model_runs_the_chain_to_a_green_verdict` |
| `122001` | N | `a_failing_model_runs_the_chain_to_a_red_verdict` |
| `122002` | B | `three_observations_of_one_case_reach_the_verdict` |

### 11.2 Why these exist, and what they replaced

Every other suite proves one stage. Ingestion rejects a malformed corpus, dispatch
routes to an adapter, the dual pass produces both halves, the verdict applies its
rules. **None of them proves the stages compose**, and a harness whose stages each
work but do not join measures nothing while reporting that it did.

These run the whole chain on a synthetic corpus: the ingestion join, three
recorded observations per case, replay dispatch, the dual pass against a judge
double, and a verdict computed from the observations that come out.

#### 11.2.1 Both outcomes, because one proves nothing

`122001` differs from `122000` **by the candidate's text alone**: same corpus, same
adapter, same judge, same rules. So the red is attributable to the model's output
and to nothing else in the chain.

**A chain that always answers green proves only that it can answer.** An
instrument has to be able to say "this failed" about something that failed, or its
green is not a measurement. It is also the distinction the whole design protects:
`122001` asserts exit **1**, a finding about a model, rather than exit 3, which
would say the instrument broke.

#### 11.2.2 `122002` guards the repeat count through the whole chain

A4.1 asks for three observations. **Dispatch could satisfy that and the verdict
still see one:** repeats are requested per observation index, recorded per index
and replayed per index, so a break anywhere collapses three samples into one
without failing. The run would look complete and the consistency check would have
nothing to compare.

#### 11.2.3 What they replaced in CI

Gates 4 to 7 of `gate-on-change.yml` ran `pytest -m evaluator`, `-m tool` and
`-m sec`, then computed a verdict from `collected/results.json`.

| | |
|---|---|
| The three markers | Collected nothing. This repository holds no graded case |
| The artifact | Written by nothing. Section 5 emits Allure and JUnit for a downstream collector |
| Why it was never seen | Gate 1 failed on the first commit that ran the workflow, so all four were skipped |

**The gates are the consumer's**, which is where a model is actually measured, and
a harness change is proved against real cases by `regress-consumers-on-merge.yml`.
What this repository owes is proof that the instrument works, and that is these
three cases.


## 12. Test Inventory: cost

Added 2026-09-27, when the project owner asked what a paid run would cost and the
harness could not answer: every adapter read its usage object and kept only the
output count, and the judge path recorded nothing at all.

### 12.1 `MQC_CMN_UNI_`

| ID | Cat | Behaviour |
|---|---|---|
| `112232` | N | `a_price_window_that_has_closed_is_reported` |
| `112233` | B | `the_published_increase_is_priced_from_its_own_date` |
| `112234` | N | `an_unpriced_model_yields_no_figure_rather_than_zero` |
| `112235` | P | `thinking_is_billed_at_the_output_rate` |
| `112236` | B | `cached_input_is_discounted_and_never_double_counted` |
| `112237` | P | `a_judged_case_reports_its_judge_apart_from_its_candidate` |
| `112238` | N | `a_replayed_observation_contributes_nothing` |
| `112143` | N | `choosing_the_default_engine_is_not_defaulting` |
| `112613` | N | `the_roster_is_found_through_the_installed_package` |
| `112614` | N | `the_shipped_distribution_carries_the_configuration` |
| `112522` | N | `a_registered_flag_no_case_names_is_reported` |
| `112406` | P | `a_band_selects_only_its_own_cases` |
| `112407` | N | `a_malformed_band_is_refused_not_ignored` |
| `112408` | B | `a_band_takes_its_foundations_only_when_asked` |
| `112409` | P | `a_carried_foundation_is_not_run_again` |
| `112410` | N | `a_record_whose_provenance_moved_is_refused` |
| `112411` | B | `no_carry_file_named_changes_nothing` |
| `112523` | N | `a_consumer_run_fails_this_job_only_on_our_codes` |

### 12.2 What was measured before any of this was built

**The estimate came first, and it cost nothing.** Every request the corpus would
send was composed offline and measured, which answered the affordability question
before a key existed:

| | Input | Output | At the published rates |
|---|---|---|---|
| Security family, 21 cases times three | 10,720 | 1,449 | 0.014 |
| Whole corpus, 65 cases times three | 64,364 | 6,831 | 0.074 |
| Whole corpus, realistic output | 64,364 | ~74,600 | 0.33 |
| Whole corpus, plus thinking at twice output | 64,364 | ~224,000 | 0.89 |

Figures in USD. **The corpus is too small for the bill to matter at flash rates,
and the variance is entirely in what was uncaptured**: thinking, and the judge.
That is why the capture came before the ceiling.

### 12.3 Why the price table is dated, and checked

Every rate for `gemini-3.8-flash` doubles on 1 January 2027, which the provider
published in advance. A table overtaken by that change would not report an error,
it would report **the older, smaller figure**, and a halved bill in a report is
worse than no bill at all. So `priced_on` and `effective_until` are data, and
`112232` fails when no window covers the date being priced.

**An unpriced model yields no figure rather than zero** (`112234`). Zero reads as a
run that was free, which is the one wrong answer that looks right.

### 12.4 The ceiling fails closed, which a test found

`112234` is also why `MQC_EXE_UNI_113702` exists. A ceiling set against an unpriced
model cannot be honoured: the model's responses cost nothing computable, so
spending never accumulates and the cap never engages. A run would have spent
without limit while reporting a budget.

**Found by a case that would not fail.** The first version of `113700` set a ceiling
against a double whose model the table does not price, and passed for that reason
rather than the one it asserted. `claude-opus-5-5` is exactly that case:
deliberately unpriced, the model a new key would most likely point at, and the one
whose thinking cannot be disabled.

So an unpriced model with a ceiling set **stops the run**, and the two conditions
are separate cases.

## 13. Traceability

| Decision | Section |
|---|---|
| A1 fixtures on PR, live on schedule | §4.8 |
| A2 amended: red need not block | §4.8 |
| A4 repeat observations | §3 |
| A6 replay marking | §7, §5 |
| A7 three outcomes, rate limits | §3 |
| A11 verdict rules, quarantine | §4.3, §4.6 |
| A13 unsupported pairs | §4.4 |
| B8 runtime configuration | §8 |
| B9 CI topology | §4.8 |


### 10.10 The identifier a design binds twice

Added 2026-09-23, after an identifier was bound twice and nothing noticed.

`112140` was already inventoried as `selecting_named_tests_yields_no_verdict`
when a second row claimed it for an unrelated case. **Every existing check
passed.** `112303` asks whether a collected test appears in some inventory row
and both did; `112305` checks each row's name against the callable pattern and
both were valid; `112306` compares an implemented name to its row and matched the
first; `112203` compares stated totals to the row count, which stayed consistent
because a row was genuinely added.

**The checks were all keyed on a row, and the defect was a relationship between
two rows.** That is the shape a per-row check cannot see, whatever its strictness.

The consequence is the one `testing-standards.md` names under identifier rules:
an ID is assigned once and never reused, so downstream history never silently
rebinds an identifier to different behaviour. Two live rows for one identifier
is that rebinding, present from the start rather than after a deletion.

`112226` scans every module design and fails on an identifier appearing in more
than one inventory row. **It is a negative case**, because the positive it
replaces, every row having a valid identifier, is already covered and was
already passing while this held.


#### 10.10.1 The same defect on the suite's side of the line, and why nothing saw it

Added 2026-10-02, after `112119` was found bound by two different cases.

`112226` closed section 10.10 for **inventories**: it scans module designs and
fails an identifier appearing in more than one row. It reads documents, and this
duplicate was in the suite, where nothing was looking.

**Every suite-side check builds a set, so a duplicate collapses before anything
compares it.** That is the same lesson as 10.10 in a new place: those checks
were keyed on a row and could not see a relationship between two rows, and these
are keyed on an identifier and cannot see two bindings of one identifier.

| Check | Asks | Sees two callables sharing an identifier? |
|---|---|---|
| `112226` | Does an inventory bind one twice? | No, it reads documents |
| `112313`, `115602` | Is a collected test in some matrix row? | **No**, both entered the set as one |
| `112325`, `112303` | Does an inventory row have an implementation? | **No**, the first found satisfies it |
| `112203` | Do the stated totals match the row count? | No, the rows stayed consistent |
| `112326` | How many callables bind this identifier? | Yes |

`112326` counts bindings across both trees rather than collecting them into a
set. **A negative case**, for the reason 10.10 gives: the positive it would
replace, every collected test carrying a valid identifier, was already covered
and already passing while this held.

**What the duplicate was: two unrelated cases, and the name fitted neither.**
One asserted that `--out-dir` reaches result metadata and carries an empty
default. The other asserted that a diagnostic artifact's **name** does not match
the collector's pattern, which is the artifact-naming mechanism of section 5 and
has nothing to do with the flag. The shared name,
`out_dir_isolates_diagnostic_artifacts`, described neither, and **no case
anywhere established the isolation it claimed** until 7.1.0.2.

**Only one of the two was a case.** Reading the second binding's three
assertions decided what to do with it, and renumbering it would have been wrong:

| Assertion | Carries |
|---|---|
| `not matches_collector_pattern(name)` | Nothing. `112210` asserts the same fact four lines above it, in **both** directions |
| `(tmp_path / name).parent == tmp_path` | **Nothing at all.** True of every single-segment string, and `tmp_path` was requested only for it |
| `name.startswith("diagnostic-local")` | A real fact `112210` misses: it pins the literal prefix, where a pattern check still passes if both prefixes are renamed together |

Its `RunContext("ci_debug", "manual", True)` also suggested a second selection
mode mattered here. It does not: `artifact_name` reads `run_context` alone, so
`manual` and `full` produce the same name and the distinction was decorative.

**So it is absorbed rather than renumbered.** `112210` already owns this
mechanism and already tests both directions; it gains the literal prefix and the
suffixed form, and the duplicate and the tautology go. Minting `11210` for what
is left would have given an accidental duplicate an identifier of its own and
recorded a 208th case that re-asserts a 207th.

| Was | Now |
|---|---|
| `112119`, `mqc_uni_cli.py` | `112119`, `out_dir_names_where_both_artifacts_are_written` |
| `112119`, `mqc_uni_metadata.py` | Gone; its one real assertion is in `112210` |

**Keeping the `--out-dir` meaning on `112119` is not a free choice.**
`testing-standards.md` forbids rebinding an identifier to different behaviour so
that downstream history stays readable, and `112119` has one inventory row and
one matrix trace, both claiming the flag. The metadata binding was never
inventoried at all, which is the sense in which it was never a case: it had an
implementation and no row, while the row it borrowed described something else.

**A name describing neither binding is how this stayed unread.** Had either
binding been called what it asserted, the collision would have been visible to a
reader on sight, without a check.

### 10.11 The check that fed itself its own data

Added 2026-09-23, after a test was added with no matrix row and the suite stayed
green.

`112312` exists to run the real matrix through T1 to T5, on the stated reasoning
that a check only ever seeing constructed input proves the check works and says
nothing about the file it guards. **It then derived both of its inputs from the
matrix it was checking.**

`declared` is by construction every requirement the matrix declares, so T1
cannot fail. `named` is by construction every test the matrix names, so T3
cannot fail. T4 receives that same set in place of the suite, so a test the
suite contains and the matrix omits is invisible to it. The assertion that
survives is T2, which is the one the test actually makes, and the remaining four
are tautologies dressed as coverage.

**A check whose inputs come from its subject can only confirm the subject is
self-consistent.** That is a real property and it is not the property this one
was written to establish. `112312` has been narrowed to claim only T2.

`112313` supplies the **collected suite** as the suite, which is the only source
that is not the matrix. It fails in both directions: a matrix row naming a test
that does not exist, and a collected test no row names.

**It belongs beside `112303` rather than inside `112312`.** `112303` asks whether a
test was designed; this asks whether it was traced. A test can satisfy either
without the other, which is exactly how the gap occurred: the new case was
inventoried correctly and traced not at all.

### 10.12 The index that drifted from what it indexes

Added 2026-09-23, after the document map in `DESIGN.md` was found stating case
counts for five designs and a workflow count, every one of them stale.

`112203` already checks that a design's stated inventory total matches its own
rows, and it was passing throughout: **each design was internally consistent and
the index describing all of them was not.** The check was scoped to a document
and the drift was between documents.

This is the third instance of one shape in this module. `112202` reads codes a
design names and checks them against the registry; `112313` reads the matrix and
checks it against the suite; `112314` reads the index and checks it against the
designs. In each, a document restates a fact that lives elsewhere, and the
restatement is what rots.

**Removing the counts from the index was considered and rejected.** The map's
value is that a reader sees the shape of the project without opening six files,
and a map with the numbers taken out is a list of filenames. The number stays
and is checked instead.

`112314` parses every document-map row naming a design under `docs/design/` and
stating a case count, then compares it to that design's own inventory line. It
deliberately does not require every row to carry a count: a design with no
inventory is not a defect, and demanding one would make the check fail on the
registries rather than on the drift.


### 10.13 Resolving the judge engine

`112600` through `112603` cover the judge default that A3 decided on 2026-09-19
and no file named until now. The policy is in `tier3_evaluation.md` section 5A;
the cases sit here because the resolution lives in `cmn/config.py`.

**They are here rather than in the Tier 3 inventory for a structural reason.**
`evaluation/` imports nothing from `execution/`, and resolving a judge requires
an engine's declared capabilities, which are a Tier 2 record. Putting the
resolution in the cross-cutting module keeps that edge from existing; putting
the cases beside it keeps the inventory honest about where the code is.

**Two negatives, because there are two ways to name a judge that cannot judge.**
`112602` is an engine that is not on the roster, usually a typo. `112603` is an
engine that is on the roster and cannot return structured output, which is the
harder one: the name is real, the engine works as a candidate, and only the
capability distinguishes it. A single case asserting "bad engine is rejected"
would pass against an implementation that only checked roster membership.


### 10.14 No harness test may read a credential

Added 2026-09-23. The property is documented in four places and protected
structurally in CI, and was asserted by nothing.

**What is already true.** `testing-standards.md` section 2 states that gates 2
and 3 require no credentials; `framework-rules.md` section 1 makes a precondition
failure stop the pipeline; the README states that an unconfigured clone cannot
spend quota; and section 8 above keeps every secret in a GitHub Environment that
`gate-on-change.yml` does not name, so a credential is unreachable from the
workflow running the harness gates.

**What that leaves open.** A harness test that read a credential would pass on
any machine with a key exported and fail in CI, where the key is unreachable.
The failure would arrive as a missing-environment error inside an unrelated
assertion rather than as a statement that the test should not have needed a key
at all. The author sees green locally and a confusing red remotely, which is the
worst shape a rule can fail in.

`112315` parses every module under `tests/` and `conftest.py` and fails when one
reads an environment variable whose name is credential-shaped.

**It reuses `forbidden_keys()` rather than listing names.** That registry already
defines credential-shaped for configuration loading, and `GEMINI_API_KEY`
lowercased contains `api_key`, so the same set answers both questions. A second
list here would be the drift this document has corrected three times.

**Reads are flagged and writes are not.** A test setting a fake value through
`monkeypatch.setenv` is constructing a fixture, which is legitimate and common.
A test *reading* one is depending on the caller's environment, which is the
defect. The distinction is made by parsing rather than by matching text, for the
same reason `112226` and `112202` parse: a file describing the rule names these
strings, and a substring check reports itself.


### 10.15 The taxonomy carries both directions of a finding

Added 2026-09-23 with `QC_LLM_DEFECT_MISSED` and `QC_LLM_MATCH_MISCOMPUTED`
(`test_taxonomy.md` section 6.1.1).

**A recall figure needs both directions to mean anything.** A model that reports
every defect and several that do not exist scores identically to one that
reports none, unless invention and omission are counted separately. The
`code_comprehension` family measures recall over a fixed set of known defects,
so the registry has to carry a code for each direction or the measurement
collapses.

The table already held one such pair and did not say so: `QC_LLM_UNSOURCED_CLAIM`
against `QC_LLM_SOURCE_ALTERATION`, invention against alteration. The second
pair is `QC_LLM_HALLUCINATION` against `QC_LLM_DEFECT_MISSED`, invention against
omission at the level of a finding.

`112227` asserts both pairs are complete. **It is a positive case and it is
deliberately weak on its own**: what it protects is a design property that a
single deletion would silently break, and a deleted code fails nothing else,
because `112201` reports an unemitted code without failing and no case is written
against a code that no longer exists.


### 10.16 The family registration mechanism, enforced

Added 2026-09-23. `test_taxonomy.md` section 11.2 is a ten-step procedure for
adding an evaluation family, and step 10 lists what must hold when it is done.
Three of those assertions had no enforcement behind them, and one named a case
that checked something else.

| Case | Closes |
|---|---|
| `112228` | The §11.1 table and `_EVALUATION_FAMILIES` could disagree |
| `112229` | A family named in the case matrix need not be registered |
| `112230` | The admission criterion in step 2 was unenforceable |

**`112228` is the fourth instance of one shape in this module**, after `112202`,
`112313` and `112314`: a document restates a fact that lives elsewhere, and the
restatement rots. Here the table is what an author edits and the dict is what
every check reads.

**`112229` closes a hole T5 cannot see.** T5 compares a matrix row's `families`
value against the cases named in the same row, which is a consistency check
between two fields of one row. Neither field is the registry, so a value
registered nowhere passes.

**`112230` makes the admission criterion mechanical.** Step 2 refuses a family
gradable only by rubric, and that refusal is why the registered families exist.
A registered family carrying no ground-truth mechanism means the step was
skipped, and until now nothing said so.


### 10.17 The plan and the matrix, and a check that could not work here

Added 2026-09-23. Two corrections in one pass, both found by running the checks
rather than by reading them.

**`112229` was written to verify that every family a matrix names is
registered, and it could not do that in this repository.** It reads
`rtm_*.csv` under `docs/testing/`, and the only matrix here is
`rtm_harness.csv`, which carries **no families column at all** by `112311`:
families apply to graded cases and a precondition performs no task. The check
found zero families and passed, which is the shape of a vacuous check rather
than a passing one.

The values it was written for live in `rtm_model.csv`, in the case repository.
**A check here that read that file would be the boundary violation the split
exists to prevent**, and the directive is explicit: if a new check needs case
data, the check belongs on the other side. It is therefore reassigned, and the
family check is `MQC_CAS_UNI_115004` in `AP-Model-QC`.

**What `112229` now does is the gap that surfaced while fixing it.** The harness
test plan states the requirements and `rtm_harness.csv` traces them, and twelve
requirements were in the matrix and absent from the plan: everything added over
one working session. A requirement traced and unstated means the plan
understates what the harness guarantees, and a reader consulting it is told
less than is true.

**This is the fifth instance of one shape in this module**, after `112202`,
`112313`, `112314` and `112228`. In each, two artefacts state one fact and nothing
compares them. The pattern is now frequent enough to be worth naming directly:
**whenever this project writes a fact in two places, the pair needs a check, and
the check is always cheap.**


### 10.18 Probing the judge

Added 2026-09-24, as step two of three agreed with the user.

`112604` through `112606` cover the judge's own model and its place in the probe.
The policy is in `tier3_evaluation.md` section 5A.4; these sit here because the
configuration lives in `cmn/config.py`, for the same reason `112600` through
`112603` do.

**`112604` is the backward-compatibility case and matters most.** An absent
`judge.model` must fall back to the roster entry for `judge.engine`, which is
the behaviour every existing configuration relies on. A fallback that returned
nothing would leave the judge unresolvable and every graded run reporting a
misconfigured instrument.

**`112606` asserts the probe covers the judge**, and it is a negative case
because the failure it guards is silence: a probe that walks only the roster
finds nothing wrong, reports nothing, and leaves judge drift undetected until a
score shifts for no visible reason.


### 10.19 The judge fixture

Added 2026-09-24. `112607` through `112610` cover storing and replaying a
judgement. The design is `tier2_execution.md` section 7.4.

**`112608` is the one that carries the design.** A judgement is stale when the
judge model changed even though the request hash is identical, because the
question is the same and the instrument is not. Nothing else in the fixture
machinery distinguishes those, and collapsing them would report a rubric edit
and a provider update as the same event.

**`112610` asserts the absence of a fallback.** A missing judgement raises rather
than returning anything a caller might mistake for a score, so the fail-open
path does not exist to be taken by accident.

**`112615` was added 2026-10-01, after the key lost 96 fixtures.** The key named
the judge engine and not the candidate engine, so recording a second candidate
overwrote the first engine's judgements file for file. It is a negative case
because what it asserts is that a collision does not happen, and it is here
rather than beside `112609` because the stale check is what *detected* the
collision: `112609` says a moved request is refused, and `112615` says the two
requests never reach one file to be compared. The design is
`tier2_execution.md` section 7.9.3.


#### 10.19.1 An inventory row without an implementation is reported, never gated

Decided 2026-10-01 by the project owner.

`MQC_CMN_UNI_112303` fails a collected case with no inventory row. **Nothing
checked the reverse**, which is the other half of the same claim and the third
half-written check this project has found in one day.

**The decision, in the owner's terms:** if there is an inventory row it has to be
implemented. An unimplemented row **must be reported**, and then implemented on
any cycle through documentation, design, RTM and implementation. It is never
removed from the design to make the report go away.

**Reported and not gated**, because an inventory row without an implementation is
the normal state while a family is being authored, and this project requires the
design to come first. A hard gate would forbid the order it mandates.

**Each repository checks its own inventories**, which is the boundary
`CLAUDE.md` states: a harness check reading a file the case repository owns is a
violation, and the installed wheel ships no tests, so neither side can ask about
the other's. `MQC_CMN_UNI_112325` reads the harness, and `MQC_CAS_UNI_115405` the
consumer.

**An inventory row carries a category and a behaviour name; a citation does
not.** That is what separates them, and it is the whole of why this check can be
per repository. Harness design prose cites consumer case numbers in ordinary
tables, `144000` and `154100` among them, and those are references rather than
claims about what the harness implements.

| Row | Shape | Counted |
|---|---|---|
| Harness inventory | `id`, category, behaviour | Yes |
| Consumer graded inventory | `id`, priority, condition, category, behaviour, traces | Yes, by the consumer |
| A citation in prose | `id` and whatever the table is about | **No** |

**The first version of this check read the sibling checkout**, which exists on a
developer's disk and never in CI, so it passed locally and failed on both
platforms the moment it was pushed. The nine identifiers that drove it there were
citations, and widening the row pattern to catch them was the error: a pattern
that matches any row whose first cell is an identifier cannot tell an inventory
from a reference. Section 10.19.2 records what that cost.

#### 10.19.2 A check that can only pass on one machine

The reasoning that produced the defect is worth keeping because it was almost
right. A per-repository scan reported nine unimplemented rows; those nine do
exist as cases, in the other repository; therefore the scan needed both
repositories. Every step follows and the conclusion is wrong, because the
premise was a row pattern that counted citations.

**The boundary was the evidence and I read it as an obstacle.** CLAUDE.md names
this exact failure, "a check here that reads a file that repository owns", and
records that it shipped undetected once before until the split made it real. It
shipped again.

**What makes it unreachable now is the pattern, not a conditional.** Guarding the
sibling read with `is_dir()` would have kept CI green and left the check meaning
two different things depending on the checkout. The strict pattern means the same
thing everywhere, and the harness scan needs no sibling at all: 500 rows, 500
implemented.

### 10.20 The header check, extended past Python

Added 2026-09-24. `112502` reports a Python file without an SPDX header, and 54
markdown and YAML files across the two repositories carried none.

`112503` covers them, and it is a **separate case rather than a widening of
`112502`** because the two checks assert different things. A Python file must
carry the header **above** its module docstring, since a docstring must remain
the first statement or ``__doc__`` is empty. Markdown and YAML have no such
constraint. Folding them together would have meant one case with two shapes and
a name true of neither.

The checker is shared the same way: `markup_header_problems` takes a root and a
licence, so the case repository runs the identical implementation against MIT.


### 10.21 The judge mode flag

Added 2026-09-24. `112611` and `112612` cover `--judge-mode`, designed in
`tier3_evaluation.md` section 5A.5.

**`112611` is the defaulting case.** The flag defaults to whatever `--mode` is,
so every existing invocation keeps its meaning and the two common quadrants need
no flag at all. A flag that defaulted to a fixed value would silently change
what `--mode live` meant.

**`112612` refuses the incoherent quadrant.** A live candidate with a replayed
judge asks for a stored score of text the run did not produce. The fixture
machinery would report it as staleness on every case, which reads as a corpus
problem rather than an impossible request, so it is refused at parsing with
exit 2.


### 10.22 The operator runbook

Added 2026-09-24. `docs/running_jobs.md` is the whole operating procedure for
the three on-demand workflows, and `112504` checks it against them.

**A tester does not read a design document to dispatch a job.** A procedure
that costs a design read is a procedure people work around, so the runbook is
separate from `ci_pipeline.md` rather than a section inside it.

**`112504` reads every fenced `gh workflow run` command and requires that the
workflow exists and declares every input the command names.** A dispatch naming
an undeclared input is rejected by GitHub with a message about the input, and a
reader following the documented procedure concludes the procedure is broken
rather than the page. The failure lands on the person least able to diagnose
it.


### 10.23 The branch policy

Added 2026-09-24. `112505` through `112509` enforce `ci_pipeline.md` section
3C.6, and they are pure functions over a branch name, a base and a set of merge
parents, so every one runs offline against synthetic input.

**`112507` is a boundary case and is named at each threshold exactly.** The
bands are 0 to 13 silent, 14 to 29 warned, 30 and above red, so the case
asserts at 13, 14, 29 and 30 rather than near them. Off-by-one at a boundary is
the likeliest defect in any gate, and a staleness ceiling that fires a day late
is a ceiling nobody notices is wrong.

**`112509` reads the shape of a merge, not its message.** A back-merge has an
incoming parent that `main` already contains; a succession has an incoming
parent carrying the unmerged work that is the reason the branch existed. The
approved remedy therefore passes without being named as an exception, which is
the property section 3C.6.5 argues for: a check that special-cased its own
remedy would be a check nobody could reason about.

**The referent kinds are a registry rather than a literal list.** Adding a kind
is a row, in the sense `testing-standards.md` uses for layer tokens, and
`112506` reports a referent matching none of them.


### 10.24 Broken blocks, and the reason decides what a skip means

Added 2026-09-24, correcting two holes found by asking what a harness failure
should do.

#### 10.24.1 Broken was distinguished at the observation and lost at the verdict

`broken` means our code failed while attempting a measurement, and
`framework-rules.md` section 4 says such an outcome is never recorded as a
model `fail`. That held at the observation level and **collapsed back into a
model finding at the verdict level**: V1 fires on any P0 or P1 observation not
passing, `broken` is not passing, and V1 sets exit 1, which is read project-wide
as "a suite measured something and it failed".

Enough broken observations also pulled the pass rate under the V2 floor, so
harness flakiness read as model degradation in the headline number.

**Broken now blocks with no ceiling, and the run exits 3.** Broken means
something needs a fix, so tolerating a proportion of it would be tolerating a
proportion of unfixed defects. Exit 3 rather than 1 because the distinction
being preserved is whose defect it was, not whether the run failed: both are
red, and only one is a finding about a third party.

| | Before | Now |
|---|---|---|
| In the V2 pass-rate denominator | Yes | **No** |
| Tolerated proportion | Up to the V2 floor | **None** |
| Exit code | 1, a model finding | **3, nothing trustworthy measured** |

#### 10.24.2 A skip is not one thing, and the reason is what says which

A network outage and an unwritten case are both skips and they are not the same
event. **The reason decides, not the branch the run happened on.**

| Reason | Means | Treatment |
|---|---|---|
| `environmental` | Outside our control, such as a provider outage | Counted, ceiling applies (V3, V4) |
| `dependency` | A foundational case failed, so this cascaded | Excluded; the real failure is already red |
| `unsupported` | A declared capability gap, on the record (A13) | Excluded; not a defect |
| **`incomplete`** | **The work is not finished** | **Blocks. No ceiling** |

**`incomplete` is new and it closes the worst of the two holes.** A case that
skipped because nobody had written it yet had no reason of its own, so it took
`unsupported`, which is **excluded from the skip denominator entirely**.
Unfinished work was therefore the most tolerated skip in the system, and the
one thing that must never merge was the one thing no ceiling could see.

**Reason-driven beats context-driven.** An earlier proposal made the skip
ceiling zero on pull requests and lenient on scheduled runs. That would have
made the same case pass or fail depending on which workflow ran it, and a
verdict that depends on its trigger is not a verdict. A reason travels with the
observation and means the same thing everywhere.


### 10.25 Tool compliance evaluation

Added 2026-09-24. `114700` through `114704` cover the evaluator designed in
`tier3_evaluation.md` section 5B, which Gate 5 was specified without.

**`114703` is the boundary and it runs both ways.** A rule with no tool
expectation produces no results, and a rule with an expectation the response
satisfies also produces none. Neither is a pass recorded as a result, because a
blank taking its default is normal operation and recording one corrupts every
later count.

**`114702` is the check that is not implied by the others.** A tool absent from
the offered set is a name the model invented, and no forbidden list would have
caught it.


### 10.26 The integration kind may omit its referent

Added 2026-09-24, refining section 3C.6.1. `112510` covers the positive claim,
and `112505` already covers the negative half for every other kind.

**Forcing a referent on an integration branch produces a false one.** It
collects several tickets, so any single referent names one of them and asserts
something untrue about the other four. A name that asserts something false is
worse than one that asserts less.

**The two cases are opposite claims and take separate identifiers.** `112510`
says a bare stamp is accepted for `stabilization`; `112505` says it is refused
for `expand`, `extend` and `debug`. A workflow could satisfy either without the
other, and one identifier covering both would leave a passing case wherever
exactly one held.


### 10.27 The declared adversarial verdict

Added 2026-09-24. `114516` covers `tier3_evaluation.md` section 4C: a declared
adversarial case is graded by its assertions, which is what the design said and
what `passed` did not do.

**The existing cases stopped one level short.** `MQC_EVL_UNI_114307` and
`MQC_EVL_SYS_124001` both assert `assertion_results[0].passed`, and neither
asserts `result.passed`. `114307`'s own docstring says the assertions "decide
it", which was true of the intent and false of the code, and a case asserting
an intermediate value cannot notice that the decision built on it went the
other way.


### 10.28 The dependency cascade, which the base marker only promised

Added 2026-09-24. `framework-rules.md` section 3.4 has said since it was
written that "a case whose result others presuppose is marked `base`; its
failure means dependents are **not executed** and are recorded as skipped with
`QC_HARNESS_DEPENDENCY_UNMET`, never as failed."

**Nothing implemented it.** The marker is registered in `pytest.ini`, two tests
carry it, and no hook reads it. `QC_HARNESS_DEPENDENCY_UNMET` was used only for
an unreachable consumer, an unrelated event. `cmn/layers.py` excludes
`dependency` skips from the skip denominator, reasoning carefully about a
cascade that could not occur.

So the marker was decorative, and the exclusion it justified protected nothing.

#### 10.28.1 Why the security suite needs it and asked for it

The suite is ordered so that **the simplest checks gate the elaborate ones**.
A P0 injection case is a string containment check with no judge and no
ambiguity; a P3 case combining vectors presupposes the P0 result.

| Priority | Shape | Presupposes |
|---|---|---|
| P0, P1 | One vector, one canary, `not_contains` | Nothing |
| P2 and below | Combinations, ordering, multi-document | The P0 and P1 results |

**Running the elaborate case when the simple one failed produces a second
report of one defect.** A model that ignores a bare override will ignore a
combined one, and recording both as failures counts one behaviour twice in
every later aggregate. That is the same reasoning `framework-rules.md` gives
for preconditions gating the graded layers, applied within a layer.

#### 10.28.2 Skipped, never failed, and the direction is the point

A dependent that never ran has produced no measurement. **Recording it as a
failure would assert something about a model that was never asked**, which is
the misattribution the four-family taxonomy exists to prevent.

The skip carries reason `dependency`, which `cmn/layers.py` already excludes
from the skip denominator: a foundational failure cascading into ten skips must
not also breach the skip ceiling, adding a derived failure on top of the real
one and pointing diagnosis at the environment.

#### 10.28.3 Declared by marker, resolved by identifier

```
@pytest.mark.base
def MQC_EVL_SEC_154100_resists_direct_instruction_override(...)

@pytest.mark.depends_on("154100")
def MQC_EVL_SEC_154109_resists_two_vectors_combined(...)
```

**The dependency names a five-digit identifier, not a test function.** A
function name carries its behaviour suffix, which changes when the behaviour is
reworded, and a dependency that breaks on a rename is a dependency nobody
maintains. Identifiers are assigned once and never reused, which makes them the
only stable handle in the suite.

**An unknown identifier is an error, not a silent pass.** A dependency naming a
case that does not exist would otherwise be satisfied by nothing existing to
fail, which is the failure mode this project has corrected most often.

#### 10.28.4 It lives in the shared support module

`cmn/pytest_support.py`, called by both repositories' conftests, for the reason
`consumer_ci.md` section 5 gives: a rule enforced differently in two places is a
defect that ships. The cascade is one implementation and two callers.


#### 10.28.5 A chain has middles, and a middle that skipped must still record

Added 2026-09-25, from a chain three links long.

`record_base_outcome` states that **a foundation which did not run did not
hold**, and records `False` for a skip so dependents skip rather than error.
The hook calling it recorded **only the call phase**, so the sentence was true
of the function and false of the system.

A middle link is both: `144002` carries `base` **and** `depends_on("144000")`.
When `144000` did not hold, `144002` was skipped by `enforce_dependencies`, which
runs in `pytest_runtest_setup`. That skip is reported with `when == "setup"`,
never `when == "call"`, so nothing recorded it and `144005` found no entry for
`144002` at all.

| Link | What happened | What `_BASE_OUTCOMES` held |
|---|---|---|
| `144000` | Skipped in the call phase | `False`, correctly |
| `144002` | Skipped in **setup**, by the cascade | **Nothing** |
| `144005` | Found no entry | **Hard error**, not a skip |

**The error was the right error for the wrong question.** An identifier absent
from the register means "no collected case declares this as base", which is a
real defect worth failing on (10.28.3), and it is not what had happened:
`144002` was collected, was marked base, and had simply not reached its call
phase. **Two distinct situations reached one branch.**

**So the recording follows the outcome, not the phase.** A setup-phase skip
records `False`, because a case that was skipped before it ran is a foundation
that did not hold, which is the same sentence the function already carried. A
setup-phase **error** records `False` for the same reason. Only the call phase
can record a `True`.

**Why this stayed hidden.** It needs a chain of three where the first does not
hold, and the suites had chains of two until the tool corpus arrived. A
two-link chain never exercises a middle.

`MQC_CMN_UNI_112404` asserts the three-link chain end to end, which is the
shortest arrangement that can fail.


#### 10.28.6 The cascade is ordered at collection, because runtime cannot answer

Added 2026-09-25, from a suite that failed on five seeds out of six.

`enforce_dependencies` asked whether an identifier was in `_BASE_OUTCOMES` and
reported its absence as "no collected case declares this as base". **That
sentence is only true some of the time.** An identifier is absent for two
unrelated reasons:

| Absent because | Is it an error |
|---|---|
| Nothing declares it as base | **Yes.** A dependency on a case that does not exist |
| Its base has not run yet | **No.** Ordering, and the run has not got there |

**Two distinct situations reaching one branch**, which is the third instance of
this exact class in this project, after the setup-phase skip in 10.28.5 and the
absent-versus-unscored rubric in 4D.2.

#### 10.28.6.1 This was not theoretical, it was the default

`pytest-randomly` is a **declared dependency** and is pinned precisely so the
suite shuffles order and catches tests that depend on each other. The cascade
is the one mechanism in the project that legitimately depends on order, and it
had nothing enforcing that order.

Running the eight-case tool suite across six seeds produced errors on five of
them, with between four and six cases erroring each time. The one clean seed
happened to order the bases first.

**The green run was the accident.** A mechanism that works when the shuffle is
kind is not a mechanism.

#### 10.28.6.2 Ask at collection, where the question has an answer

At collection the whole population is known, so both questions become
answerable and they separate:

* **An identifier no collected case declares as base is reported then**, once,
  naming every offender rather than erroring per dependent at setup.
* **Items are reordered** so every base precedes its dependents.

The reorder is a depth-first post-order walk, which is a topological sort that
**preserves the incoming order wherever it does not have to change it**. That
matters: randomisation is a feature, and the cascade needs exactly as much
order as it needs and no more. Independent cases stay shuffled.

**A cycle is reported rather than broken.** Two cases each declaring the other
foundational is a design error in the cases, and silently picking one to run
first would make it survive.

#### 10.28.6.3 What runtime is left to decide

Only the outcome. After reordering, an identifier still absent from
`_BASE_OUTCOMES` means the base did not run, which is the same conclusion as
"did not hold", so it skips. **The hard failure moves entirely to collection**,
where it is a statement about the suite rather than a guess about timing.

`MQC_CMN_UNI_112405` runs the three-link chain under a deliberately reversed
collection order, which is the arrangement that failed.


#### 10.34.5 The file sits beside the roster, and the consumer looks there

Added 2026-09-25, found while costing the first recording run.

`.env` was created in **`AP-Harness-QC`**, naming `GEMINI_API_KEY`. The graded
cases run from **`AP-Model-QC`**, whose conftest loads `.env` from its own
root. **The file existed and the run that needed it read nothing.**

That is the same defect as the one 10.34 was written for, one level up: there
the loader did not exist, here it does and looks in the wrong place. Both
present identically, as a credential the suite reports absent.

##### Beside the roster is the right place

A credential authenticates against an engine, and the engines are declared in
`AP-Harness-QC/config/engines.yaml`. The cases repository already reaches its
sibling for that file, so reaching it for the credential is the same journey
rather than a new one.

**The alternative is two copies of a secret**, which is worse in every way that
matters: two files to gitignore, two to rotate, and one that quietly goes
stale.

##### The consumer searches its own root first

| Looked at | Why |
|---|---|
| The cases repository root | **First**, so an explicit local file still wins |
| The harness checkout | The fallback, where the roster lives |

**No signature changed and no merge logic was written.** `load_env_file`
already refuses to overwrite a variable that is set, so calling it twice in
order gives exactly "local wins, sibling as fallback" for free. A second
mechanism would have been a second thing to get wrong.

**The harness does not look the other way.** It owns the roster, so a
credential in the consumer is the odd arrangement rather than a supported one,
and searching for it would invite exactly the two-copies problem above.

**CI is unaffected.** The refusal under a runner fires before any root is
consulted, so both calls return nothing there and credentials continue to come
from the GitHub Environment (10.34.3).



#### 10.34.6 A credential nothing reads is a silent misconfiguration

Added 2026-09-26, from a credential named `OPEN_AI_APi_KEY`.

The SDK reads `OPENAI_API_KEY`. That name differs in two places, an underscore
and a letter's case, and **nothing said so.** The file loaded cleanly, the
variable was set, the loader reported it applied, and no engine would ever
look at it.

**That is the shape this project keeps closing**, and it had gone unnoticed in
the one place a reader has least ability to check their own work: a file they
are told not to print.

##### What is reported, and what is not

`orphan_credentials` compares the names a credential file assigns against the
names the registered engines declare through `API_KEY_ENV`, and reports any that
look like a credential and match no engine.

| Name | Reported |
|---|---|
| `OPEN_AI_APi_KEY`, no engine reading it | **Yes.** Credential-shaped and orphaned |
| `GEMINI_API_KEY`, read by the Gen AI SDK | No |
| `MQC_PROBE_FRESH`, not credential-shaped | No |

**It is a warning and not a refusal.** A file may legitimately carry a
credential for something outside this harness, and refusing to start over a
variable we merely do not recognise would be the harness overreaching. What it
must not do is stay silent, which is what happened.

**The name is reported and the value never is.** That rule holds here more than
anywhere: the whole point of the check is to be run against a real credential
file.

##### The engines declare the names, so the check cannot drift

The comparison reads `API_KEY_ENV` from each registered adapter rather than a
list. An engine added tomorrow is covered the moment it is registered, which is
the same arrangement the conformance battery uses (section 3.5).

**Gen AI is the exception and is stated as one.** Its SDK reads
`GOOGLE_API_KEY` or `GEMINI_API_KEY` itself rather than through
`client_options`, so the adapter declares both and the check reads that
declaration like any other.

`MQC_CMN_UNI_112518` reports an orphan.

### 10.29 The homoglyph vector

Added 2026-09-24. `112403` covers the vector designed in
`extensibility_standard.md` section 2.4, which writing the security corpus
found missing.

**The boundary is a mixed script inside one word**, and the case names both
sides of it: a word mixing Cyrillic and Latin is reported, and a word written
wholly in Cyrillic is not. Reporting the second would call every Russian
document an attack, which is the failure that would have this check disabled
within a week.


### 10.30 T6, and the collision that produced it

Added 2026-09-24. **T1 reads the declared requirements as a set**, so a
requirement identifier appearing on two rows is invisible to it: the second row
either restates the first or silently replaces what it meant.

Found by hitting it. A script adding `MQC_REQ_HAR_ING_0020` guarded itself with "if
the identifier is already present, this is already done", and that identifier
belonged to an unrelated requirement from months earlier. The guard read the
collision as completion and dropped the row, so the case it should have traced
was traced nowhere.

**`112313` caught it, and only indirectly**, by noticing the case appeared in no
matrix row. That works and reports the wrong thing: the visible failure was an
untraced case, and the cause was a duplicate identifier two hundred rows away.

**Case identifiers already had this protection and requirement identifiers did
not.** `112226` reports an identifier bound twice in a design inventory, and the
register it guards is the one where the rule was already stated. The asymmetry
was not a decision.


### 10.31 Register occupancy is watched

Added 2026-09-24 with the four-digit widening. `112317` reports a requirement
register that has consumed 80% of its range.

**A ceiling that goes from silent to blocking is repaired by whatever is
quickest**, and here the quickest repair is adding a digit to new identifiers
while the old ones keep three, which is the mixed-width state the fixed width
exists to prevent. The warning band makes the deliberate repair the easy one,
which is the same argument the branch staleness ceiling makes.

**It measures the consumed range rather than the count.** Identifiers are
assigned in loose groups and a retired one stays retired, so a register holding
25 requirements can have consumed 53 numbers, and the count would report half
the pressure that actually exists.


### 10.32 The two registers are disjoint by construction

Added 2026-09-24. `112318` asserts that no requirement register token is also a
module code or a layer token, and that no identifier is both a requirement and
a case.

**Widths alone were doing the work, and widths are not a namespace.**
Requirement numbers are four digits and case numbers five, so nothing collided,
while `MQC_CAS_` prefixed both. A pattern written for one register matched the
other, which is how a rename came within a lookahead of clipping 458 case
identifiers.

**The check reads the shipped registers rather than a list.** A hardcoded set
of permitted tokens would pass while the real matrices drifted, which is the
failure this project keeps correcting.


### 10.33 Registry membership is pinned

Added 2026-09-25. **Six registries had accessors nobody called and contents
nobody asserted.** `registered_skip_reasons`, `registered_run_contexts`,
`registered_selection_modes`, `registered_evaluation_families`,
`is_registered_llm_code` and `is_registered_sec_code` were public, documented
in no design, and referenced only inside their own modules.

A sweep reported them as dead code. **They are not dead, they are unasserted**,
and the two want opposite repairs: dead code is deleted, and an unasserted
registry gets the case it was missing.

**What a registry can do silently.** A member added is a vocabulary the design
never sanctioned; a member removed is a value that was legal yesterday and
loads as an error today. `MQC_CMN_UNI_112200` through `112202` already check that
emitted and documented taxonomy codes are registered, which is the other
direction: they say nothing about the registry's own membership changing.

**`112319` pins the contents exactly**, so growth is deliberate. That makes the
case a maintenance cost on purpose, in the same way an inventory row is: a
registry that gains a member without anybody noticing is the thing being
prevented.


### 10.34 The `.env` file nothing read

Added 2026-09-25, found while preparing the first live recording run.

`.env.example` is tracked and opens with **"Copy to `.env` and fill in what you
need"**. The README repeats it. **Nothing loaded the file.** No `dotenv`
dependency, no loader, no call, so a key placed there never reached the
process and the suite reported the credential absent.

**The same class as the runbook that documented a dispatch GitHub would
reject**: a procedure that fails silently for whoever follows it, while reading
as though it works. It surfaced here because a live run was about to be
attempted and the key appeared to be missing.

#### 10.34.1 Explicit environment wins over the file

A variable already set in the process is **never overwritten**. Someone who
exported a key in their shell meant that key, and a file quietly replacing it
would be the worst kind of surprise: the run succeeds, against the wrong
account.

#### 10.34.2 A malformed line is refused, never skipped

Skipping an unparseable line means a key silently did not load, and the symptom
is an authentication failure somewhere far away. The line number is named and
**the value never is**, which is the same rule that governs logs and artifacts.

**An absent file is not an error.** The suite runs without credentials by
design: every gate on a pull request is deterministic, which `.env.example`
states at length.

#### 10.34.3 It is local only, and CI is refused outright

**CI takes its credentials from the GitHub Environment named `live`, never from
a file.** `gate-on-change.yml` references no provider secret at all, which is
A1's boundary made structural and enforced by `MQC_CAS_UNI_115702`.

So the loader **refuses to run when CI is detected** rather than merely being
unnecessary there. A `.env` reaching a runner would be a credential arriving by
a path nobody audited, and the failure mode of "harmless because nothing calls
it" is the one this project has corrected four times this week.

| Context | Credential comes from |
|---|---|
| A developer's machine | `.env`, loaded here, values never logged |
| **Any CI runner** | **`secrets.GEMINI_API_KEY` through the `live` environment** |

**Two cases, because they run in different places.** `112512` and `112513` cover the
local loader and **do not execute under CI**, where there is no credential file to
load and no local behaviour to assert. `112514` and `112515` cover the boundary itself, run
everywhere, and is the one that matters on a runner: the loader is inert when
`CI` or `GITHUB_ACTIONS` is set, and no workflow in either repository reads a
credential file.

Splitting them keeps each honest. A single case would have to disable half of
itself depending on where it ran, and a case that skips part of its own
assertions is a case whose green says less than it appears to.

#### 10.34.4 No new dependency

`python-dotenv` would be a runtime dependency for twenty lines of parsing, on a
project whose dependency list argues for each entry individually. The loader
lives in `cmn/config.py` beside the credential rules it belongs with.
