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
| V5 | Any quarantine entry expired as of `as_of_date` | Red |
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

An entry carries a case identifier, a reason, and an **expiry date**.

* Quarantined cases are excluded from the pass-rate denominator, never deleted from the suite.
* They are listed in the report.
* **An expired entry fails the run (V5).** Without expiry, quarantine becomes where failures go to be forgotten and the 90% floor stops meaning anything, because everything inconvenient has left the denominator.

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

`MQC_CMN_UNI_11206` covers the rule and `MQC_CAS_UNI_10466` covers the loop
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

`11123` compares the document map's case counts to the designs, and `10146`
compares a design's stated total to its own rows. **The README sat outside both
while being the first thing a reader sees**, and both of its figures had drifted:

| Claimed | Actual |
|---|---|
| 498 cases | 462 inventoried |
| 144 requirements | 184 traced |

**The numbers stay and are checked** rather than being deleted, for the reason
`11123` gives about the document map: a front page whose value is showing the
shape of the project cannot do that without them.

**It recomputes rather than storing a third copy.** The case count is summed from
the design inventories and the requirement count is the matrix's own row count, so
there is no new number to maintain — which is what made the first two drift.

---

## 5. Result Metadata Emission

Every observation is emitted with the fields required by `test_taxonomy.md` §9: `engine`, `mode`, `model_version`, `priority`, `priority_conditions`, `taxonomy_code`, `duration`, `output_tokens`, plus the CLI invocation record from §7.

Emitted as Allure parameters and labels, and through JUnit XML test names, so both reach a downstream collector without changes on its side.

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
`MQC_CMN_UNI_11122` and `MQC_CAS_UNI_10460`.

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

The two files therefore share one schema with `families` optional, and the harness file **omits the column rather than carrying it blank**. That needs no special case: an absent optional column takes its declared default, which is the rule `MQC_ING_UNI_10019` covers. Two schemas would have been the alternative, and two schemas for one matrix format is the drift this section exists to prevent.

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
--engine:    {owner: harness}
--case:      {owner: consumer}
--out-dir:   {gap: {reason: "...", expires_on: 2026-11-30}}
```

Each repository asserts only what it owns. The file ships as package data, so
both read one declaration rather than two that drift.

**A gap is declared, dated and expires**, which is the treatment
`quarantine.yaml` gives a case and for the same reason: without an expiry, the
list is where inconvenient flags go to be forgotten, and the check stops meaning
anything because everything unproven has left its denominator. An expired entry
fails the run, which forces the decision to be made again rather than to lapse.

**Nine of sixteen flags are gaps as this is written**, including the two that
produced this section. That number is the finding, not a defect in the check.

`MQC_CMN_UNI_11193` enforces the harness half, reading the shipped registry and
declaration rather than a permitted list of its own.

#### 7.1.1 Diagnostic runs

Troubleshooting and hotfix verification need a single case run from a terminal, not a CI pipeline.

| Flag | Purpose |
|---|---|
| `--case <ID>` | Select one case by identifier |
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

| Flag | Selects |
|---|---|
| `--case <ID>[,<ID>]` | Specific cases |
| `--priority 0,1` | Priority bands |
| `--module ING,EXE` | Modules |
| `--tag <tag>` | Tagged groups, such as an ambiguity control pair |
| `-m`, `-k` | pytest native marker and name expressions |

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

`10197` asserted that `build_invocation({"engine": "openai"})` is quiet. `openai`
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

The cascade crosses bands: `MQC_EVL_EVAL_30036` is P2 and depends on a P1 case,
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
single case with `-k 30023` deselected its foundation `30024`,
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

`MQC_CMN_UNI_11203` covers the refusal and `11204` the warning.

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

## 8. Configuration

| File | Contents | Why config, not code |
|---|---|---|
| `config/engines.yaml` | Engine roster: model IDs, endpoints, parameters, request spacing | Adding an engine is an entry, never a module (B8) |
| `config/unsupported.yaml` | Declared (test × engine) pairs that cannot run, with reasons | A capability gap must not consume skip budget (A13) |
| `config/quarantine.yaml` | Quarantined cases with reason and **expiry date** | §4.6 |

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
| `10101` | P | `green_when_all_rules_satisfied` |
| `10102` | N | `red_when_p0_observation_fails` (V1) |
| `10103` | N | `red_when_p1_observation_fails` (V1) |
| `10104` | P | `green_when_p2_fails_within_pass_floor` (V1) |
| `10105` | B | `green_at_exactly_ninety_percent_pass_rate` (V2) |
| `10106` | N | `red_just_below_ninety_percent_pass_rate` (V2) |
| `10107` | B | `green_at_exactly_twenty_percent_skips` (V3) |
| `10108` | N | `red_just_above_twenty_percent_skips` (V3) |
| `10109` | B | `green_at_exactly_ten_percent_priority_skips` (V4) |
| `10110` | N | `red_just_above_ten_percent_priority_skips` (V4) |
| `10111` | N | `red_when_quarantine_entry_expired` (V5) |
| `10112` | P | `green_when_quarantine_entry_current` (V5) |
| `10113` | B | `expiry_boundary_evaluated_against_injected_date` |
| `10114` | N | `red_when_no_observations_at_all` (V6) |
| `10115` | N | `red_when_no_graded_observations` (V6) |
| `10116` | N | `red_when_every_graded_case_quarantined` (V6) |
| `10117` | N | `red_when_every_pair_unsupported` (V6) |
| `10118` | N | `dependency_skips_excluded_from_skip_denominator` |
| `10119` | N | `unsupported_pairs_excluded_from_skip_denominator` |
| `10120` | N | `quarantined_cases_excluded_from_pass_denominator` |
| `10121` | P | `security_layer_excluded_from_distribution_ceiling` |
| `10122` | N | `precondition_failure_blocks_graded_evaluation` |
| `10123` | N | `precondition_skip_is_a_failure` |
| `10124` | P | `reports_every_breached_rule_not_only_the_first` |
| `10125` | P | `verdict_is_pure_for_identical_input` |
| `10126` | N | `verdict_does_not_read_system_clock` |
| `10127` | B | `distribution_check_returns_no_verdict_below_thirty_cases` |
| `10128` | N | `red_when_p0_share_exceeds_ten_percent` |
| `10129` | N | `red_when_combined_p0_p1_exceeds_thirty_percent` |
| `10130` | P | `demotion_orders_single_match_before_multiple` |
| `10131` | P | `security_cases_are_never_demoted` |
| `10132` | N | `rtm_row_with_no_test_is_a_coverage_gap` (T2) |
| `10133` | N | `rtm_naming_absent_test_is_rejected` (T3) |
| `10134` | N | `test_with_requirement_id_absent_from_rtm_is_rejected` (T4) |
| `10135` | P | `cli_defaults_are_recorded_in_metadata` |
| `10136` | P | `defaulted_engine_emits_warning_into_artifact` |
| `10137` | P | `rule_set_content_hash_recorded_in_metadata` |
| `10138` | P | `effective_thresholds_recorded_in_metadata` (9.3) |
| `10139` | P | `new_layer_respects_declared_graded_flag` (9.1) |
| `10140` | P | `new_layer_respects_declared_distribution_exemption` (9.1) |
| `10141` | N | `outcome_without_declared_denominator_treatment_is_rejected` (9.4) |
| `10142` | P | `registered_verdict_rule_is_evaluated_without_core_change` (9.2) |
| `10143` | N | `emitted_code_absent_from_registry_is_rejected` |
| `10144` | N | `registered_code_with_no_emit_site_is_reported` |
| `10145` | N | `unregistered_code_in_a_live_specification_is_reported` |
| `10146` | N | `stated_inventory_counts_disagreeing_with_rows_is_reported` |
| `10147` | P | `option_registry_yields_identical_flags_to_both_surfaces` |
| `10148` | N | `invalid_enumerated_flag_value_is_rejected_at_parse_time` |
| `10149` | P | `verdict_recomputable_from_stored_artifacts` |
| `10150` | N | `precondition_failure_exits_three_not_one` |
| `10151` | N | `unknown_case_identifier_is_an_error_not_an_empty_run` |
| `10152` | P | `case_flag_selects_exactly_one_case` |
| `10153` | P | `observations_override_replaces_configured_count` |
| `10154` | N | `diagnostic_run_returns_no_verdict_code` |
| `10155` | P | `run_context_and_gated_flag_recorded_in_metadata` |
| `10156` | N | `verdict_tool_refuses_artifacts_marked_ungated` |
| `10157` | P | `out_dir_isolates_diagnostic_artifacts` |
| `10158` | P | `run_scoped_fields_emitted_per_result_not_in_a_manifest_alone` |
| `10159` | P | `observation_assembled_from_tier_results_and_case_metadata` |
| `10160` | N | `truncated_duration_excluded_from_latency_statistics` |
| `10161` | N | `result_missing_a_required_metadata_field_is_rejected` |
| `10162` | P | `no_filter_yields_selection_mode_full` |
| `10163` | P | `change_scoped_selection_still_yields_a_verdict` |
| `10164` | N | `manual_filter_yields_no_verdict` |
| `10165` | P | `selection_mode_recorded_per_result` |
| `10166` | N | `debug_artifact_name_does_not_match_collector_pattern` |
| `10167` | P | `debug_rows_carry_ci_debug_context_and_ungated_flag` |
| `10168` | N | `verdict_tool_refuses_a_manual_selection_artifact` |
| `10169` | P | `gated_derived_from_selection_preconditions_and_run_context` |
| `10170` | N | `refusal_exits_four_not_one` |
| `10174` | B | `full_selection_under_debug_context_is_still_ungated` |
| `10175` | B | `first_run_on_a_branch_has_no_previous_conclusion_to_compare` |
| `10176` | P | `summary_records_job_run_number_both_refs_and_changed_areas` |
| `10177` | B | `fixture_ref_defaults_to_code_ref_when_not_supplied` |
| `10178` | P | `manual_full_dispatch_of_ci_is_gated_and_yields_a_verdict` |
| `10179` | P | `graded_result_records_its_evaluation_family` |
| `10180` | N | `unregistered_family_value_is_rejected` |
| `10181` | B | `precondition_result_carries_no_family` |
| `10182` | P | `result_records_the_platform_it_ran_on` |
| `10183` | N | `collected_test_absent_from_an_inventory_fails_the_run` |
| `10184` | P | `distribution_check_reports_the_demoted_case_count` |
| `10185` | N | `rtm_families_disagreeing_with_the_inventory_are_reported` |
| `10186` | N | `inventory_name_violating_the_callable_pattern_is_reported` |
| `10187` | N | `test_name_disagreeing_with_its_inventory_row_is_reported` |
| `10188` | N | `an_overlapping_identifier_block_is_rejected` |
| `10189` | P | `a_complete_declaration_registers_and_is_read` |
| `10190` | P | `a_case_below_its_ceiling_is_detectable_from_its_record` |
| `10191` | N | `a_priority_above_every_matched_condition_is_a_breach` |
| `10192` | N | `a_declared_requirement_with_no_row_is_reported` |
| `10193` | P | `families_agreeing_with_the_inventory_pass` |
| `10194` | P | `every_check_runs_rather_than_stopping_at_the_first` |
| `10195` | N | `an_unknown_matrix_column_is_rejected` |
| `10196` | B | `the_harness_matrix_omits_the_families_column` |
| `10197` | P | `the_live_harness_matrix_passes_every_check` |
| `10198` | N | `argparse_rejects_the_same_values_the_registry_does` |
| `10199` | P | `mode_defaults_to_replay_so_nothing_spends_quota` |
| `10200` | P | `a_green_gated_artifact_exits_zero` |
| `11101` | N | `an_unreadable_artifact_is_an_argument_error` |
| `11102` | B | `an_unrecorded_threshold_falls_back_to_the_default` |
| `11103` | B | `latency_is_absent_rather_than_zero_when_nothing_measured` |
| `11104` | P | `changed_areas_distinguish_harness_from_tests` |
| `11107` | N | `a_field_the_record_does_not_declare_is_rejected` |
| `11108` | N | `requirements_files_disagreeing_with_pyproject_fail` |
| `11109` | N | `every_imported_package_is_declared` |
| `11110` | N | `random_test_ordering_is_declared` |
| `11111` | N | `every_callable_carries_parameter_and_return_hints` |
| `11112` | N | `pep_563_future_annotations_import_is_rejected` |
| `11113` | N | `every_python_file_carries_its_spdx_header` |
| `11114` | N | `every_package_on_disk_is_configured_for_the_build` |
| `11115` | P | `consumer_registry_loads_every_declared_entry` |
| `11116` | N | `a_consumer_entry_without_a_repository_is_rejected` |
| `11117` | B | `an_absent_consumer_registry_is_a_starting_condition` |
| `11118` | N | `selecting_named_tests_yields_no_verdict` |
| `11119` | B | `an_unnamed_harness_branch_falls_back_to_the_default_ref` |
| `11120` | P | `a_named_harness_branch_resolves_to_its_paired_consumer_ref` |
| `11121` | N | `an_identifier_appearing_twice_in_one_inventory_is_reported` |
| `11122` | N | `a_collected_test_named_in_no_matrix_row_is_reported` |
| `11123` | N | `an_index_case_count_disagreeing_with_its_design_is_reported` |
| `11124` | P | `the_default_judge_engine_is_gemini` |
| `11125` | P | `a_configured_judge_engine_overrides_the_default` |
| `11126` | N | `a_judge_engine_absent_from_the_roster_is_rejected` |
| `11127` | N | `an_engine_without_structured_output_cannot_judge` |
| `11128` | N | `a_harness_test_reading_a_credential_is_reported` |
| `11129` | P | `invention_and_omission_are_both_registered_codes` |
| `11130` | N | `family_table_disagreeing_with_the_code_registry_is_reported` |
| `11131` | N | `every_requirement_in_the_matrix_appears_in_the_plan` |
| `11132` | N | `a_registered_family_without_ground_truth_is_reported` |
| `11133` | P | `an_absent_judge_model_falls_back_to_the_roster_entry` |
| `11134` | P | `a_judge_model_distinct_from_the_candidate_is_expressible` |
| `11135` | N | `a_probe_that_omits_the_judge_subject_is_reported` |
| `11136` | P | `a_recorded_judgement_is_replayed_for_the_same_request` |
| `11137` | N | `a_judgement_from_a_different_judge_model_is_stale` |
| `11138` | N | `a_judgement_whose_request_hash_moved_is_stale` |
| `11139` | N | `a_missing_judgement_raises_rather_than_judging_live` |
| `11140` | N | `a_document_or_data_file_without_an_spdx_header_is_reported` |
| `11201` | N | `two_candidate_engines_judged_by_one_judge_do_not_share` |
| `11202` | N | `an_untraced_test_is_reported_against_either_matrix` |
| `11203` | N | `with_prerequisites_under_a_keyword_filter_is_refused` |
| `11204` | B | `with_prerequisites_without_any_filter_warns_and_proceeds` |
| `11205` | N | `an_inventory_row_without_an_implementation_is_reported` |
| `11206` | B | `one_disagreement_earns_two_further_observations` |
| `11141` | P | `judge_mode_defaults_to_whatever_mode_is` |
| `11142` | N | `a_live_candidate_with_a_replayed_judge_is_refused` |
| `11143` | N | `a_runbook_command_naming_an_undeclared_input_is_reported` |
| `11144` | N | `a_branch_name_outside_the_grammar_is_reported` |
| `11145` | N | `a_referent_of_no_registered_kind_is_reported` |
| `11146` | B | `staleness_is_silent_then_warned_then_red_at_its_bounds` |
| `11147` | N | `a_development_branch_targeting_main_is_reported` |
| `11148` | N | `a_merge_bringing_main_into_a_branch_is_reported` |
| `11149` | N | `a_broken_graded_observation_blocks_and_exits_three` |
| `11150` | N | `an_incomplete_skip_blocks_however_few_there_are` |
| `11151` | B | `an_environmental_skip_is_tolerated_to_its_ceiling` |
| `11152` | P | `an_integration_branch_may_omit_its_referent` |
| `11153` | N | `a_dependent_of_a_failed_base_case_is_skipped_not_failed` |
| `11154` | P | `a_dependent_of_a_passing_base_case_runs_normally` |
| `11155` | N | `a_dependency_naming_no_collected_case_is_reported` |
| `11156` | B | `a_mixed_script_word_is_a_homoglyph_and_one_script_is_not` |
| `11157` | N | `a_file_open_declaring_no_encoding_is_reported` |
| `11158` | N | `a_requirement_identifier_declared_twice_is_reported` |
| `11159` | B | `a_register_at_eighty_percent_of_its_ceiling_is_reported` |
| `11160` | N | `a_register_token_that_is_also_a_module_code_is_reported` |
| `11161` | N | `a_registry_membership_change_without_a_case_is_reported` |
| `11162` | N | `a_local_env_file_is_loaded_without_overwriting_anything` |
| `11163` | N | `a_line_that_is_not_an_assignment_is_skipped_by_number` |
| `11164` | N | `a_credential_file_reaching_ci_is_reported` |
| `11165` | N | `no_workflow_reads_a_credential_file` |
| `11166` | N | `a_base_case_skipped_in_setup_is_recorded_for_its_dependents` |
| `11168` | N | `a_dependent_collected_before_its_base_is_reordered` |
| `11169` | N | `a_credential_file_beside_the_roster_is_found` |
| `11170` | N | `the_consumer_conftest_searches_both_roots` |
| `11171` | N | `a_case_whose_observations_disagree_is_a_finding` |
| `11172` | B | `inconsistency_at_the_ceiling_unsounds_the_run` |
| `11175` | P | `a_score_moving_inside_the_band_is_recorded_not_gated` |
| `11176` | N | `two_models_on_one_engine_unsounds_the_run` |
| `11177` | P | `one_model_per_engine_is_sound_across_engines` |
| `11178` | B | `an_observation_with_no_model_is_not_a_second_version` |
| `11179` | N | `every_declared_credential_appears_in_the_example` |
| `11180` | N | `a_readme_count_disagreeing_with_the_designs_is_reported` |
| `11181` | N | `an_installed_gating_tool_outside_its_pin_is_reported` |
| `11182` | N | `a_generated_file_in_a_skipped_tree_is_not_read` |
| `11173` | N | `a_credential_no_engine_reads_is_reported` |
| `11174` | P | `the_engines_declare_the_names_the_check_reads` |

**Inventory: 203 cases, 116 negative, 60 positive, 27 boundary.** The total covers both tables: the `UNI` cases in section 10 and the three `SYS` cases in section 11, as tier 2 carries its two tables under one figure.

**The code excerpt guards moved to `AP-Model-QC` on 2026-09-23.** They read files the case repository owns, so a harness check asserting against them was a cross-boundary dependency that only became visible when the boundary became real. `DESIGN.md` section 5.1 records what that cost to find.

### 10.1 Taxonomy registry consistency

Three checks, the same shape as the RTM integrity checks in section 6 and for the same reason: every declared thing must be verified, in both directions.

| Case | Guards against |
|---|---|
| `10143` | An unregistered code reaching the durable record, where nothing downstream can interpret it |
| `10144` | Registry rot, where a code remains listed long after the condition that raised it was removed |
| `10145` | A specification naming a code that was never registered |
| `10146` | An inventory whose stated totals no longer match its rows |

### 10.2 The suite enforces its own authoring order

**`10183` fails the run when a collected test identifier appears in no design inventory.**

A12 requires a design change to be discussed, documented and only then implemented. **The reason that order exists is priority.**

A new case may move the P0 and P1 shares, and those carry enforced ceilings. Writing the test first means the priority is assigned after the case exists, when the question has become how to fit it rather than what it deserves. Designing first puts the assignment and the ceiling check before the work, which is the only point at which either can be decided consciously.

**Demotion is the part that matters most.** When a ceiling binds, the mechanism demotes cases, and a demotion made to satisfy a percentage is exactly the inflation the condition registry exists to prevent, running in reverse. A level assigned because a budget had room means no more than one assigned because a budget was short.

So a demotion is a decision like any other: documented, designed for, and only then implemented. `test_taxonomy.md` section 4.1.4 states how it is reported.

An earlier version of this paragraph argued that documenting afterwards produces weaker prose. Measured against the sections written each way, it does not, and the argument was abandoned rather than kept because it sounded right.

**The order itself cannot be checked mechanically**, since nothing in a repository records when a line was written. What can be checked is the state that results from skipping it, and a test with no inventory row is exactly that state.

This makes the omission impossible to ship rather than impossible to commit. Someone can still write the test first, but they cannot finish without returning to the design, and the return is where the question they skipped gets asked.

**It is a negative case deliberately.** A positive asserting that every inventory row has a test would catch a different and lesser problem: a case designed and not built is visible in a coverage report, while a case built and never designed is visible nowhere until someone asks why the inventory is short.

**`10146` reads one canonical sentence.** Every module design states its inventory as `**Inventory: <n> cases, <n> negative, <n> positive, <n> boundary.**` and nothing else. The four documents previously used three different phrasings for that statement, which would have forced the check to parse prose variants, and a check that parses prose fails the first time someone rewords a sentence rather than changes a number.

**`10145` scans live specifications only.** Two kinds of document are excluded, both dated records rather than specifications: the Phase 0 register, which deliberately names alternatives that were considered and rejected, and `CLAUDE_LOG.md`, which records codes as they were before a later decision split or renamed them. A code appearing in either is evidence of a decision rather than an unregistered entry, and scanning them would report every rejected option and every superseded name as a defect.

Both exclusions were established by a manual cross-check that reported `QC_LLM_INJECTION_ATTEMPT`, rejected under A5a, and `QC_HARNESS_API_TIMEOUT`, later split into `QC_HARNESS_CANDIDATE_TIMEOUT` and `QC_HARNESS_JUDGE_TIMEOUT`. Neither is a defect, and a check reporting them would be trained away on its second run.

This check was added after a manual cross-check found two codes, `QC_HARNESS_FIXTURE_MISSING` and `QC_HARNESS_FIXTURE_STALE`, used in a design document and never registered. Finding it by hand is the argument for automating it.

**Boundary cases are named explicitly at each threshold**: exactly 90%, exactly 20%, exactly 10%, exactly 30 cases. Every threshold in this document is an inequality, and off-by-one at a boundary is the most likely defect in the module. A rule stated as "below 90%" must be tested at 90%, not near it.


### 10.3 An inventory row can specify a name nothing may carry

Added 2026-09-22, after five rows were found specifying behaviour names longer than the 60 characters `.pylintrc` permits on a callable. Two were discovered by implementing them and failing Gate 1; three were latent and would have failed whenever someone reached them.

**`10186` checks the inventory against the pattern the callable must match.** A design that specifies an unimplementable name is a defect in the design, and the person who meets it is implementing something unrelated and has to stop to fix a document.

**`10187` checks that an implemented name matches its row.** `10183` established that a test must appear in an inventory; it compares identifiers and says nothing about behaviour names. One case had already diverged: the test name was shortened to pass Gate 1 and the inventory row was left as it was, so the design and the code described the same case differently.

That divergence is the exact shape the authoring order exists to prevent, arriving from the other direction: not a test written without a design, but a design left behind by a test. Both are the code and the document disagreeing, and one check cannot cover both.

### 10.4 Nineteen cases added during implementation

Added 2026-09-23. Each guards something the original inventory could not, and they fall into four groups.

**Registry completeness, in both directions.** `10188` refuses a layer whose identifier block overlaps one already registered: two layers claiming one identifier would let downstream history silently rebind it, which is the reason identifiers are never reused. `10189` is the positive `10141` is measured against, because a rejection case alone is satisfied by an implementation that rejects everything.

**Counterweights without which a check passes for the wrong reason.** `10193` asserts that T5 does **not** fire on a correct row, `10197` runs the integrity checks against the live matrix rather than only synthetic rows, and `10198` asserts that `argparse` rejects the values the registry rejects. The last is the one that matters: a registry validating correctly while the command line accepted anything would satisfy `10148` completely and leave the actual surface unguarded.

**Boundaries stated as absence rather than zero.** `11102` and `11103` are the same rule twice: an artifact predating a threshold recomputes against the default, and latency over no measured samples is absent rather than zero. A mean of zero would read as an impossibly fast run, which is a quality finding drawn from a gap in the data.

**The fixture guards needed a third and a fourth**, and both **relocated to `AP-Model-QC` on 2026-09-23** with the excerpts they guard. Formerly `11105`, now `MQC_CAS_UNI_10404`, asserts the two `top_scorers` excerpts are the same function, which is what makes the pair worth having: without it, defect class is confounded with subject matter, length and difficulty, and a difference in results would have three explanations. Formerly `11106`, now part of `MQC_CAS_UNI_10405`, asserts the excerpts carry a text suffix, so no formatter, linter or collector silently corrects them.

#### 10.4.1 The excerpts are executed in process, and that is approved

Executing a defective excerpt to establish what it returns requires `exec`, which is approved rather than suppressed silently at the call site, per `code-style.md` section 9. The two cases doing so were formerly `10172` and `10173`, now `MQC_CAS_UNI_10402` and `10403`.

**The approval moved with the cases on 2026-09-23.** The excerpt guards now live in `AP-Model-QC` as `MQC_CAS_UNI_10401` through `10405`, and the `exec` approval belongs with them. Nothing in this repository executes a fixture.

In process rather than through a subprocess, because capturing a subprocess under pytest fails on Windows with an invalid handle, and the harness is verified on both platforms (A18).

#### 10.4.2 Two checks were over-reporting, which is how a check gets ignored

Both were found by running them.

`10183` matched any occurrence of a test identifier, including one inside a string literal. A traceability case must name a non-existent test in order to exercise a stale reference, and that literal was reported as an undesigned test. **The pattern now requires a `def` prefix**, because a collected test is one the suite defines.

`10145` scanned every backticked code in a live specification, including prose. Section 10.2 already excludes the Phase 0 register for naming rejected alternatives, but a live specification's own prose names superseded codes for the same legitimate reason: this document explains the exclusion by naming the two codes that prompted it. **The check now scans table rows only.** A code specified for use appears in a table; a code discussed appears in prose.

Neither was a defect in the thing checked. Both were the check reporting what is not a defect, which is precisely how a check comes to be ignored.


### 10.5 The dependency declaration check

`11108` compares the generated requirements files against `pyproject.toml` and fails when they disagree.

**It exists because the files are a convenience, not a source of truth.** `DESIGN.md` section 5.0.1 keeps the declaration in one place; this check is what makes the generated copies safe to keep. Without it they are a second declaration, and a second declaration drifts.

`11109` is the one that would have caught the gap. It parses every import in the repository and compares against the declaration, so a package the code imports and nothing declares fails here rather than on the first clean install. **Parsed, not pattern-matched**: a regex over source lines also matches prose, and a docstring beginning "from the artifact alone" reads as an import of a package named `the`.

`11110` names `pytest-randomly` specifically, because a general declaration check cannot know that this particular dependency carries a guarantee rather than a convenience.

It also covers the gap that prompted the section. An audit found `pytest-randomly` installed locally and declared nowhere, so **local runs held a guarantee CI did not**: the suite shuffles test order to catch inter-test dependencies, and the extension cases mutate registries, which is exactly where such a dependency would live. A check comparing the declaration to the environment would have caught it; a check comparing two files to each other does not, which is why the case reads the declaration rather than the installed set.


### 10.6 The annotation checks

`11111` parses every Python file and fails on a missing parameter or return annotation. `11112` fails on a `from __future__ import annotations`.

**They exist because the rule already existed and nothing checked it.** `code-style.md` section 2 has required full annotation since the project began, and an audit found production code at zero gaps and test code at 597. Pylint does not check annotation presence, so the rule was a convention wherever nobody happened to be careful.

**`11112` is the less obvious of the two.** Python 3.14 implements PEP 649, so annotations are already lazy and the import is not needed for that. What it does instead is select PEP 563, which stringizes every annotation and removes `annotationlib.Format.VALUE`. On a project built from frozen dataclasses that read their fields at class creation, that trades a working mechanism for a weaker one to obtain something already present.

The check is a negative for the reason section 10.2 gives: a positive asserting that annotations are lazy would pass on any 3.14 interpreter regardless of what the code does, while this fails exactly when someone reaches for the import.


### 10.7 The authorship header check

`11113` asserts that every Python file opens with the two SPDX lines, above the module docstring, naming this repository's licence.

**The split made the licence a per-file question.** Code from this repository now installs into another one under a different licence, so a file separated from its repository has to say what it is. `code-style.md` section 1.1 carries the form and why SPDX rather than the thirteen-line Apache appendix notice.

**Position is checked, not only presence.** The header must sit above the module docstring: a docstring has to remain the first statement or ``__doc__`` is empty, and this project reads module docstrings as specification prose. A header pasted inside one would satisfy a presence check and silently empty the documentation.


### 10.8 The packaging check

`11114` compares the packages the build is configured to ship against the package directories on disk, and fails when a directory would be left out.

**It exists because a hand-written package list shipped a broken distribution.** `pyproject.toml` named four packages and omitted `execution.adapters`, so the built wheel contained `execution/` with no adapters in it. The adapter registry imports all three adapters at import time, so **every consumer would have failed on its first import**.

Nothing here detected it. The repository is normally used from its own source tree, where the directories are simply present and the build configuration is never exercised. It surfaced the first time this repository was installed into another one, which is a thing only the 2026-09-23 split made possible.

**The configuration is now discovery rather than a list**, so a package added later is included by being on disk instead of by being remembered. The check guards the remaining gap: a new top-level package whose name matches no `include` pattern would still be dropped silently.


### 10.9 The fan-out and named-test cases

Added 2026-09-23 with the three regression and debug workflows in `ci_pipeline.md` sections 3A, 3B and 6A.

`11115` through `11117` cover the consumer registry the fan-out reads. **A consumer entry naming no repository is rejected** rather than tolerated, because it would report unreachable on every run, which reads as a consumer problem when it is a registry typo. **An absent registry is a starting condition**: a harness with no registered consumers has nothing to fan out to, which is not an error.

`11119` and `11120` cover the per-branch pairing added with `ci_pipeline.md`
section 3C. A run is defined by a **pair** of refs, so the registry maps a
branch of this repository to the consumer ref it is verified against.

**`11119` is the case that carries the design.** A harness branch the mapping
does not name falls back to `default_ref` rather than failing, because feature
branches are created constantly and requiring a registry entry for each would
make the registry the thing that stops a branch being tested. It is marked
boundary because the fallback is the edge the mapping is defined at, and an
implementation raising there instead would be silent on every branch except the
two that are named.

**`11118` closes a gap the debug workflow opened.** It selects by test identifier, and the option registry knew nothing about that: `tests` was neither a declared option nor a manual selector, so a run naming four failing tests would have derived `selection_mode: full` and produced a verdict from four cases.

That is the exact failure the gating rules exist to prevent, arriving through a flag nobody had registered. The selector registry is what makes it impossible rather than merely unlikely, which is why `10164` is parametrized over that registry rather than over a written list.

---

### 10.35 The installed toolchain is checked against the declared pin

Added 2026-09-26, from a bug rather than a review.

**`pyproject.toml` pinned `pylint>=3.3,<4.0` and 4.0.6 was installed locally.**
Gate 1 exited **0** here and **8** in CI on the same commit, because the newer
pylint counts `self` differently against `max-args`. Two commits were pushed on
the strength of a local run that was measuring a different tool.

**`11108` could not catch it.** It regenerates the requirements files from
`pyproject.toml`, so it verifies that what is *declared* agrees with itself.
Nothing verified that what is *installed* agrees with the declaration, and the
declaration is what CI installs from.

| Checked | By |
|---|---|
| The generated files match the declaration | `11108` |
| **The installed tool satisfies the declaration** | **`11181`** |

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
this repository authors, so `11140` reported it as missing an SPDX header. **It
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

**`11182` builds the condition rather than waiting for it.** `11140` fails only
when the working tree's cache is clean, and a developer who has run the header
pass does not have one, so it was a check that happened to notice rather than one
that could not miss. `11182` plants a generated file in three skipped trees and
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
second instance of the shape `MQC_CMN_UNI_11114` records: a distribution
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
| `20301` | P | `a_compliant_model_runs_the_chain_to_a_green_verdict` |
| `20302` | N | `a_failing_model_runs_the_chain_to_a_red_verdict` |
| `20303` | B | `three_observations_of_one_case_reach_the_verdict` |

### 11.2 Why these exist, and what they replaced

Every other suite proves one stage. Ingestion rejects a malformed corpus, dispatch
routes to an adapter, the dual pass produces both halves, the verdict applies its
rules. **None of them proves the stages compose**, and a harness whose stages each
work but do not join measures nothing while reporting that it did.

These run the whole chain on a synthetic corpus: the ingestion join, three
recorded observations per case, replay dispatch, the dual pass against a judge
double, and a verdict computed from the observations that come out.

#### 11.2.1 Both outcomes, because one proves nothing

`20302` differs from `20301` **by the candidate's text alone**: same corpus, same
adapter, same judge, same rules. So the red is attributable to the model's output
and to nothing else in the chain.

**A chain that always answers green proves only that it can answer.** An
instrument has to be able to say "this failed" about something that failed, or its
green is not a measurement. It is also the distinction the whole design protects:
`20302` asserts exit **1**, a finding about a model, rather than exit 3, which
would say the instrument broke.

#### 11.2.2 `20303` guards the repeat count through the whole chain

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
| `11183` | N | `a_price_window_that_has_closed_is_reported` |
| `11184` | B | `the_published_increase_is_priced_from_its_own_date` |
| `11185` | N | `an_unpriced_model_yields_no_figure_rather_than_zero` |
| `11186` | P | `thinking_is_billed_at_the_output_rate` |
| `11187` | B | `cached_input_is_discounted_and_never_double_counted` |
| `11188` | P | `a_judged_case_reports_its_judge_apart_from_its_candidate` |
| `11189` | N | `a_replayed_observation_contributes_nothing` |
| `11190` | N | `choosing_the_default_engine_is_not_defaulting` |
| `11191` | N | `the_roster_is_found_through_the_installed_package` |
| `11192` | N | `the_shipped_distribution_carries_the_configuration` |
| `11193` | N | `a_registered_flag_no_case_names_is_reported` |
| `11194` | P | `a_band_selects_only_its_own_cases` |
| `11195` | N | `a_malformed_band_is_refused_not_ignored` |
| `11196` | B | `a_band_takes_its_foundations_only_when_asked` |
| `11197` | P | `a_carried_foundation_is_not_run_again` |
| `11198` | N | `a_record_whose_provenance_moved_is_refused` |
| `11199` | B | `no_carry_file_named_changes_nothing` |
| `11200` | N | `a_consumer_run_fails_this_job_only_on_our_codes` |

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
`11183` fails when no window covers the date being priced.

**An unpriced model yields no figure rather than zero** (`11185`). Zero reads as a
run that was free, which is the one wrong answer that looks right.

### 12.4 The ceiling fails closed, which a test found

`11185` is also why `MQC_EXE_UNI_10303` exists. A ceiling set against an unpriced
model cannot be honoured: the model's responses cost nothing computable, so
spending never accumulates and the cap never engages. A run would have spent
without limit while reporting a budget.

**Found by a case that would not fail.** The first version of `10301` set a ceiling
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

`11118` was already inventoried as `selecting_named_tests_yields_no_verdict`
when a second row claimed it for an unrelated case. **Every existing check
passed.** `10183` asks whether a collected test appears in some inventory row
and both did; `10186` checks each row's name against the callable pattern and
both were valid; `10187` compares an implemented name to its row and matched the
first; `10146` compares stated totals to the row count, which stayed consistent
because a row was genuinely added.

**The checks were all keyed on a row, and the defect was a relationship between
two rows.** That is the shape a per-row check cannot see, whatever its strictness.

The consequence is the one `testing-standards.md` names under identifier rules:
an ID is assigned once and never reused, so downstream history never silently
rebinds an identifier to different behaviour. Two live rows for one identifier
is that rebinding, present from the start rather than after a deletion.

`11121` scans every module design and fails on an identifier appearing in more
than one inventory row. **It is a negative case**, because the positive it
replaces, every row having a valid identifier, is already covered and was
already passing while this held.


### 10.11 The check that fed itself its own data

Added 2026-09-23, after a test was added with no matrix row and the suite stayed
green.

`10197` exists to run the real matrix through T1 to T5, on the stated reasoning
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
was written to establish. `10197` has been narrowed to claim only T2.

`11122` supplies the **collected suite** as the suite, which is the only source
that is not the matrix. It fails in both directions: a matrix row naming a test
that does not exist, and a collected test no row names.

**It belongs beside `10183` rather than inside `10197`.** `10183` asks whether a
test was designed; this asks whether it was traced. A test can satisfy either
without the other, which is exactly how the gap occurred: the new case was
inventoried correctly and traced not at all.

### 10.12 The index that drifted from what it indexes

Added 2026-09-23, after the document map in `DESIGN.md` was found stating case
counts for five designs and a workflow count, every one of them stale.

`10146` already checks that a design's stated inventory total matches its own
rows, and it was passing throughout: **each design was internally consistent and
the index describing all of them was not.** The check was scoped to a document
and the drift was between documents.

This is the third instance of one shape in this module. `10145` reads codes a
design names and checks them against the registry; `11122` reads the matrix and
checks it against the suite; `11123` reads the index and checks it against the
designs. In each, a document restates a fact that lives elsewhere, and the
restatement is what rots.

**Removing the counts from the index was considered and rejected.** The map's
value is that a reader sees the shape of the project without opening six files,
and a map with the numbers taken out is a list of filenames. The number stays
and is checked instead.

`11123` parses every document-map row naming a design under `docs/design/` and
stating a case count, then compares it to that design's own inventory line. It
deliberately does not require every row to carry a count: a design with no
inventory is not a defect, and demanding one would make the check fail on the
registries rather than on the drift.


### 10.13 Resolving the judge engine

`11124` through `11127` cover the judge default that A3 decided on 2026-09-19
and no file named until now. The policy is in `tier3_evaluation.md` section 5A;
the cases sit here because the resolution lives in `cmn/config.py`.

**They are here rather than in the Tier 3 inventory for a structural reason.**
`evaluation/` imports nothing from `execution/`, and resolving a judge requires
an engine's declared capabilities, which are a Tier 2 record. Putting the
resolution in the cross-cutting module keeps that edge from existing; putting
the cases beside it keeps the inventory honest about where the code is.

**Two negatives, because there are two ways to name a judge that cannot judge.**
`11126` is an engine that is not on the roster, usually a typo. `11127` is an
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

`11128` parses every module under `tests/` and `conftest.py` and fails when one
reads an environment variable whose name is credential-shaped.

**It reuses `forbidden_keys()` rather than listing names.** That registry already
defines credential-shaped for configuration loading, and `GEMINI_API_KEY`
lowercased contains `api_key`, so the same set answers both questions. A second
list here would be the drift this document has corrected three times.

**Reads are flagged and writes are not.** A test setting a fake value through
`monkeypatch.setenv` is constructing a fixture, which is legitimate and common.
A test *reading* one is depending on the caller's environment, which is the
defect. The distinction is made by parsing rather than by matching text, for the
same reason `11121` and `10145` parse: a file describing the rule names these
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

`11129` asserts both pairs are complete. **It is a positive case and it is
deliberately weak on its own**: what it protects is a design property that a
single deletion would silently break, and a deleted code fails nothing else,
because `10144` reports an unemitted code without failing and no case is written
against a code that no longer exists.


### 10.16 The family registration mechanism, enforced

Added 2026-09-23. `test_taxonomy.md` section 11.2 is a ten-step procedure for
adding an evaluation family, and step 10 lists what must hold when it is done.
Three of those assertions had no enforcement behind them, and one named a case
that checked something else.

| Case | Closes |
|---|---|
| `11130` | The §11.1 table and `_EVALUATION_FAMILIES` could disagree |
| `11131` | A family named in the case matrix need not be registered |
| `11132` | The admission criterion in step 2 was unenforceable |

**`11130` is the fourth instance of one shape in this module**, after `10145`,
`11122` and `11123`: a document restates a fact that lives elsewhere, and the
restatement rots. Here the table is what an author edits and the dict is what
every check reads.

**`11131` closes a hole T5 cannot see.** T5 compares a matrix row's `families`
value against the cases named in the same row, which is a consistency check
between two fields of one row. Neither field is the registry, so a value
registered nowhere passes.

**`11132` makes the admission criterion mechanical.** Step 2 refuses a family
gradable only by rubric, and that refusal is why the registered families exist.
A registered family carrying no ground-truth mechanism means the step was
skipped, and until now nothing said so.


### 10.17 The plan and the matrix, and a check that could not work here

Added 2026-09-23. Two corrections in one pass, both found by running the checks
rather than by reading them.

**`11131` was written to verify that every family a matrix names is
registered, and it could not do that in this repository.** It reads
`rtm_*.csv` under `docs/testing/`, and the only matrix here is
`rtm_harness.csv`, which carries **no families column at all** by `10196`:
families apply to graded cases and a precondition performs no task. The check
found zero families and passed, which is the shape of a vacuous check rather
than a passing one.

The values it was written for live in `rtm_model.csv`, in the case repository.
**A check here that read that file would be the boundary violation the split
exists to prevent**, and the directive is explicit: if a new check needs case
data, the check belongs on the other side. It is therefore reassigned, and the
family check is `MQC_CAS_UNI_10427` in `AP-Model-QC`.

**What `11131` now does is the gap that surfaced while fixing it.** The harness
test plan states the requirements and `rtm_harness.csv` traces them, and twelve
requirements were in the matrix and absent from the plan: everything added over
one working session. A requirement traced and unstated means the plan
understates what the harness guarantees, and a reader consulting it is told
less than is true.

**This is the fifth instance of one shape in this module**, after `10145`,
`11122`, `11123` and `11130`. In each, two artefacts state one fact and nothing
compares them. The pattern is now frequent enough to be worth naming directly:
**whenever this project writes a fact in two places, the pair needs a check, and
the check is always cheap.**


### 10.18 Probing the judge

Added 2026-09-24, as step two of three agreed with the user.

`11133` through `11135` cover the judge's own model and its place in the probe.
The policy is in `tier3_evaluation.md` section 5A.4; these sit here because the
configuration lives in `cmn/config.py`, for the same reason `11124` through
`11127` do.

**`11133` is the backward-compatibility case and matters most.** An absent
`judge.model` must fall back to the roster entry for `judge.engine`, which is
the behaviour every existing configuration relies on. A fallback that returned
nothing would leave the judge unresolvable and every graded run reporting a
misconfigured instrument.

**`11135` asserts the probe covers the judge**, and it is a negative case
because the failure it guards is silence: a probe that walks only the roster
finds nothing wrong, reports nothing, and leaves judge drift undetected until a
score shifts for no visible reason.


### 10.19 The judge fixture

Added 2026-09-24. `11136` through `11139` cover storing and replaying a
judgement. The design is `tier2_execution.md` section 7.4.

**`11137` is the one that carries the design.** A judgement is stale when the
judge model changed even though the request hash is identical, because the
question is the same and the instrument is not. Nothing else in the fixture
machinery distinguishes those, and collapsing them would report a rubric edit
and a provider update as the same event.

**`11139` asserts the absence of a fallback.** A missing judgement raises rather
than returning anything a caller might mistake for a score, so the fail-open
path does not exist to be taken by accident.

**`11201` was added 2026-10-01, after the key lost 96 fixtures.** The key named
the judge engine and not the candidate engine, so recording a second candidate
overwrote the first engine's judgements file for file. It is a negative case
because what it asserts is that a collision does not happen, and it is here
rather than beside `11138` because the stale check is what *detected* the
collision: `11138` says a moved request is refused, and `11201` says the two
requests never reach one file to be compared. The design is
`tier2_execution.md` section 7.9.3.


#### 10.19.1 An inventory row without an implementation is reported, never gated

Decided 2026-10-01 by the project owner.

`MQC_CMN_UNI_10183` fails a collected case with no inventory row. **Nothing
checked the reverse**, which is the other half of the same claim and the third
half-written check this project has found in one day.

**The decision, in the owner's terms:** if there is an inventory row it has to be
implemented. An unimplemented row **must be reported**, and then implemented on
any cycle through documentation, design, RTM and implementation. It is never
removed from the design to make the report go away.

**Reported and not gated**, because an inventory row without an implementation is
the normal state while a family is being authored, and this project requires the
design to come first. A hard gate would forbid the order it mandates.

**The audit that decided it.** Across both repositories, 627 inventory rows and
627 implemented, nothing designed and unbuilt. The first scan said the same thing
and meant nothing: its row pattern matched three-column tables and the graded
inventories carry six. **A check that cannot fail is not evidence**, which is why
the number above is stated with how it was obtained.

`MQC_CMN_UNI_11205` reports the list across both repositories and passes on an
empty one.

### 10.20 The header check, extended past Python

Added 2026-09-24. `11113` reports a Python file without an SPDX header, and 54
markdown and YAML files across the two repositories carried none.

`11140` covers them, and it is a **separate case rather than a widening of
`11113`** because the two checks assert different things. A Python file must
carry the header **above** its module docstring, since a docstring must remain
the first statement or ``__doc__`` is empty. Markdown and YAML have no such
constraint. Folding them together would have meant one case with two shapes and
a name true of neither.

The checker is shared the same way: `markup_header_problems` takes a root and a
licence, so the case repository runs the identical implementation against MIT.


### 10.21 The judge mode flag

Added 2026-09-24. `11141` and `11142` cover `--judge-mode`, designed in
`tier3_evaluation.md` section 5A.5.

**`11141` is the defaulting case.** The flag defaults to whatever `--mode` is,
so every existing invocation keeps its meaning and the two common quadrants need
no flag at all. A flag that defaulted to a fixed value would silently change
what `--mode live` meant.

**`11142` refuses the incoherent quadrant.** A live candidate with a replayed
judge asks for a stored score of text the run did not produce. The fixture
machinery would report it as staleness on every case, which reads as a corpus
problem rather than an impossible request, so it is refused at parsing with
exit 2.


### 10.22 The operator runbook

Added 2026-09-24. `docs/running_jobs.md` is the whole operating procedure for
the three on-demand workflows, and `11143` checks it against them.

**A tester does not read a design document to dispatch a job.** A procedure
that costs a design read is a procedure people work around, so the runbook is
separate from `ci_pipeline.md` rather than a section inside it.

**`11143` reads every fenced `gh workflow run` command and requires that the
workflow exists and declares every input the command names.** A dispatch naming
an undeclared input is rejected by GitHub with a message about the input, and a
reader following the documented procedure concludes the procedure is broken
rather than the page. The failure lands on the person least able to diagnose
it.


### 10.23 The branch policy

Added 2026-09-24. `11144` through `11148` enforce `ci_pipeline.md` section
3C.6, and they are pure functions over a branch name, a base and a set of merge
parents, so every one runs offline against synthetic input.

**`11146` is a boundary case and is named at each threshold exactly.** The
bands are 0 to 13 silent, 14 to 29 warned, 30 and above red, so the case
asserts at 13, 14, 29 and 30 rather than near them. Off-by-one at a boundary is
the likeliest defect in any gate, and a staleness ceiling that fires a day late
is a ceiling nobody notices is wrong.

**`11148` reads the shape of a merge, not its message.** A back-merge has an
incoming parent that `main` already contains; a succession has an incoming
parent carrying the unmerged work that is the reason the branch existed. The
approved remedy therefore passes without being named as an exception, which is
the property section 3C.6.5 argues for: a check that special-cased its own
remedy would be a check nobody could reason about.

**The referent kinds are a registry rather than a literal list.** Adding a kind
is a row, in the sense `testing-standards.md` uses for layer tokens, and
`11145` reports a referent matching none of them.


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

Added 2026-09-24. `10383` through `10387` cover the evaluator designed in
`tier3_evaluation.md` section 5B, which Gate 5 was specified without.

**`10386` is the boundary and it runs both ways.** A rule with no tool
expectation produces no results, and a rule with an expectation the response
satisfies also produces none. Neither is a pass recorded as a result, because a
blank taking its default is normal operation and recording one corrupts every
later count.

**`10385` is the check that is not implied by the others.** A tool absent from
the offered set is a name the model invented, and no forbidden list would have
caught it.


### 10.26 The integration kind may omit its referent

Added 2026-09-24, refining section 3C.6.1. `11152` covers the positive claim,
and `11144` already covers the negative half for every other kind.

**Forcing a referent on an integration branch produces a false one.** It
collects several tickets, so any single referent names one of them and asserts
something untrue about the other four. A name that asserts something false is
worse than one that asserts less.

**The two cases are opposite claims and take separate identifiers.** `11152`
says a bare stamp is accepted for `stabilization`; `11144` says it is refused
for `expand`, `extend` and `debug`. A workflow could satisfy either without the
other, and one identifier covering both would leave a passing case wherever
exactly one held.


### 10.27 The declared adversarial verdict

Added 2026-09-24. `10388` covers `tier3_evaluation.md` section 4C: a declared
adversarial case is graded by its assertions, which is what the design said and
what `passed` did not do.

**The existing cases stopped one level short.** `MQC_EVL_UNI_10347` and
`MQC_EVL_SYS_20202` both assert `assertion_results[0].passed`, and neither
asserts `result.passed`. `10347`'s own docstring says the assertions "decide
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
def MQC_EVL_SEC_50001_resists_direct_instruction_override(...)

@pytest.mark.depends_on("50001")
def MQC_EVL_SEC_50010_resists_two_vectors_combined(...)
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

A middle link is both: `40003` carries `base` **and** `depends_on("40001")`.
When `40001` did not hold, `40003` was skipped by `enforce_dependencies`, which
runs in `pytest_runtest_setup`. That skip is reported with `when == "setup"`,
never `when == "call"`, so nothing recorded it and `40006` found no entry for
`40003` at all.

| Link | What happened | What `_BASE_OUTCOMES` held |
|---|---|---|
| `40001` | Skipped in the call phase | `False`, correctly |
| `40003` | Skipped in **setup**, by the cascade | **Nothing** |
| `40006` | Found no entry | **Hard error**, not a skip |

**The error was the right error for the wrong question.** An identifier absent
from the register means "no collected case declares this as base", which is a
real defect worth failing on (10.28.3), and it is not what had happened:
`40003` was collected, was marked base, and had simply not reached its call
phase. **Two distinct situations reached one branch.**

**So the recording follows the outcome, not the phase.** A setup-phase skip
records `False`, because a case that was skipped before it ran is a foundation
that did not hold, which is the same sentence the function already carried. A
setup-phase **error** records `False` for the same reason. Only the call phase
can record a `True`.

**Why this stayed hidden.** It needs a chain of three where the first does not
hold, and the suites had chains of two until the tool corpus arrived. A
two-link chain never exercises a middle.

`MQC_CMN_UNI_11166` asserts the three-link chain end to end, which is the
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

`MQC_CMN_UNI_11168` runs the three-link chain under a deliberately reversed
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

`MQC_CMN_UNI_11173` reports an orphan.

### 10.29 The homoglyph vector

Added 2026-09-24. `11156` covers the vector designed in
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

**`11122` caught it, and only indirectly**, by noticing the case appeared in no
matrix row. That works and reports the wrong thing: the visible failure was an
untraced case, and the cause was a duplicate identifier two hundred rows away.

**Case identifiers already had this protection and requirement identifiers did
not.** `11121` reports an identifier bound twice in a design inventory, and the
register it guards is the one where the rule was already stated. The asymmetry
was not a decision.


### 10.31 Register occupancy is watched

Added 2026-09-24 with the four-digit widening. `11159` reports a requirement
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

Added 2026-09-24. `11160` asserts that no requirement register token is also a
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
loads as an error today. `MQC_CMN_UNI_10143` through `10145` already check that
emitted and documented taxonomy codes are registered, which is the other
direction: they say nothing about the registry's own membership changing.

**`11161` pins the contents exactly**, so growth is deliberate. That makes the
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
A1's boundary made structural and enforced by `MQC_CAS_UNI_10435`.

So the loader **refuses to run when CI is detected** rather than merely being
unnecessary there. A `.env` reaching a runner would be a credential arriving by
a path nobody audited, and the failure mode of "harmless because nothing calls
it" is the one this project has corrected four times this week.

| Context | Credential comes from |
|---|---|
| A developer's machine | `.env`, loaded here, values never logged |
| **Any CI runner** | **`secrets.GEMINI_API_KEY` through the `live` environment** |

**Two cases, because they run in different places.** `11162` and `11163` cover the
local loader and **do not execute under CI**, where there is no credential file to
load and no local behaviour to assert. `11164` and `11165` cover the boundary itself, run
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
