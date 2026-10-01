<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# Testing Standards & Reporting Rules

## 1. Test Naming

### The Project Prefix Is Mandatory
`MQC` is the project prefix, shared by **AP-Harness-QC** and **AP-Model-QC**, and it is required on **every** test artifact without exception. It is not a property of a particular layer, and it does not vary by test type. Anything the suite collects carries it:

| Artifact | Required form | Enforced by |
|---|---|---|
| Test module | `mqc_<layer>_<component>.py` | `pytest.ini` `python_files`, `.pylintrc` `module-rgx` |
| Test class | `TestMQC<Component>` | `pytest.ini` `python_classes`, `.pylintrc` `class-rgx` |
| Test callable | `MQC_<MODULE>_<LAYER>_<5DIGIT_ID>_<behavior>` | `pytest.ini` `python_functions`, `.pylintrc` `function-rgx` / `method-rgx` |

**The layer appears in the test module name** because nothing else carries it: the directory gives the module and the path gives nothing else. `mqc_uni_schemas.py` holds harness preconditions; `mqc_eval_grounding.py` holds model gradings. One layer per file, which subsumes the one-layer-per-class rule below. The full rule, including why harness modules take no prefix, is normative in `docs/design/test_taxonomy.md` section 2.1.

The `test_` prefix is prohibited at every level: module, class, and function. Names built for pytest's defaults are a lint failure, not a style preference: `pytest.ini` would not collect them, so such a test lints clean, reports nothing, and never runs.

### The Layer Token Is An Extensible Registry
`<LAYER>` is an uppercase token of 3-5 characters identifying the test type. It is **secondary to the prefix**: adding a new layer never relaxes the `MQC_` requirement, and `.pylintrc` deliberately matches `MQC_[A-Z]{3,5}_` rather than an enumerated list so that registering a new layer is not a lint failure on a correctly named test.

Currently registered layers:

| Layer | Marker | ID Block | Scope |
|---|---|---|---|
| `MQC_UNI_` | `unit` | 10001-19999 | Parsers, validators, helpers. No network. **Ungraded precondition: 100% pass, zero skips.** |
| `MQC_SYS_` | `system` | 20001-29999 | Dispatch, adapter normalization, pipeline wiring. **Ungraded precondition, replay mode: 100% pass.** |
| `MQC_EVAL_` | `evaluator` | 30001-39999 | LLM-as-a-Judge rubric scoring and golden-rule enforcement. |
| `MQC_TOOL_` | `tool` | 40001-49999 | Tool-use compliance: required tools invoked, forbidden tools avoided. |
| `MQC_SEC_` | `sec` | 50001-59999 | Model security behaviour: injection resistance, prompt leakage, tool coercion. **Own suite; exempt from priority distribution ceilings.** |

`<MODULE>` is `ING`, `EXE`, `EVL` or `CMN`. Meanings, module and priority definitions, the outcome model and the failure taxonomy are normative in `docs/design/test_taxonomy.md`. This file holds the machine-enforced patterns only.

**Preconditions before graded layers.** `MQC_UNI_` and `MQC_SYS_` carry no priority and must pass 100%. If either fails, the graded layers (`MQC_EVAL_`, `MQC_TOOL_`) do not execute: a harness whose own tests are failing produces results that are suspect anyway, and running them spends provider quota to generate noise.

**Registering a new layer** requires all three of: a row in this table with its own ID block, a marker entry in `pytest.ini`, and a `-m <marker>` gate step in the CI sequence below. No code change to `.pylintrc` is needed or permitted for this.

### Inventory Principle

**Prefer including a check to omitting one.** Justifying why a case exists is easier than justifying why one is absent, and an absent case is rarely a decision. It is usually an oversight nobody notices until the thing it would have caught has already happened.

Where a check is **cheap and deterministic**, it is written. Cost is the only argument for omission that carries weight, and it applies to cases consuming provider quota or wall-clock, not to unit cases that run in milliseconds against synthetic input.

A case deliberately **not** written is recorded as a known gap with its reason, so the omission is a decision on the record rather than a silence.

### Authoring Order Is Documentation, Traceability, Then Code

**Nothing is implemented before it is documented and traced.** The order is
fixed and it is not a formality:

1. **Document it.** The case, the data file or the behaviour gets an inventory
   row in the design or test plan that owns it, with its category, and prose
   saying what it establishes and why.
2. **Trace it.** A row in the matrix naming the requirement it satisfies.
3. **Implement it.**
4. **Reconcile.** Where implementation meets something the design did not
   anticipate, **or the design turns out to be wrong**, the design is corrected
   first, the correction is entered in the RTM, and only then are tests or
   functionality written against it. The change is logged.

**The hole can be in any of the three.** A gap in the tests, a gap in the
implementation, and a gap in the design are all entered the same way, because
until the design says what should be true there is nothing for a test to be
written against. The most common case in this project has been the third, and
the least expected:

| Where the hole was | Example |
|---|---|
| Tests | An identifier bound twice and every per-row check passing |
| Implementation | A resolver exiting 1 where only 4 is permissible |
| **Design** | A step naming a verification that did not exist |

**A design that claims enforcement it does not have is worse than one that
claims none**, because a reader stops looking. Two instances in one session:
`10197` stated it ran the real matrix through five checks and fed itself its own
data, and step 10 of the family procedure named one case against an assertion
that case never made. Both read as stronger than silence would have.

**Why the order and not the reverse.** Writing code first and documenting after
produces documentation that describes what was built rather than what was
intended, and the difference between those two is where every gap hides. A
design written afterwards cannot disagree with the code, so it can never reveal
that the code is wrong.

**The loop is the point.** Step 4 is not failure, it is the normal case: the
instruction-following corpus forced a constraint-kind promotion, and the
consumer green-gate forced a new failure code. Both were design changes
discovered by building, and both were written down before the fix was. Going
back to adjust the documentation to reality and then implementing against the
adjusted documentation is cheaper than either half alone, and it keeps the
record honest about what was learned when.

**This also protects the priority budget.** A case that arrives as code and is
documented later has already chosen its priority, and the distribution ceilings
in this document are only enforceable where the assignment is a decision on the
record before the test exists.

`MQC_CMN_UNI_10183` enforces step 1 mechanically: a collected test with no
inventory row fails the run. `11122` enforces step 2 in both directions. **The
order itself cannot be checked**, since nothing records when a line was written;
what can be checked is the state that results from skipping it.


### Every Bug Is Matched By A Case, And The Case Comes First

Added 2026-09-24.

**A bug is not fixed until a case exists that fails without the fix.** Finding
one is the same event as finding a hole in the design, and it enters the same
way:

1. **Design it.** The case gets an inventory row in the document that owns it,
   with its category and what it establishes.
2. **Trace it.** A row in the matrix naming the requirement it satisfies. Where
   the bug revealed that no requirement covered the behaviour, the requirement
   is written first, because a case tracing to nothing is a case nobody can
   argue with.
3. **Implement it**, then fix the bug.

**This applies to a bug found while building, not only to one reported.** Those
are the same defect discovered at different times, and the later discovery is
the one that already cost somebody something. A defect found and quietly
corrected mid-change leaves no record that it was ever possible, so the next
person writes it again.

**Where the case goes decides nothing about whether it is written.** A bug in
the harness takes a harness case; a bug in a corpus file takes a case in the
case repository. If the bug is in a place that has no case yet, that absence
is the finding.

#### The case must fail before the fix, and it is checked that way

**Writing the case after the fix proves nothing.** A case written against
already-correct code passes on its first run whether or not it tests anything,
and the project has shipped exactly that: `10197` fed itself its own data and
every one of its five checks passed against a matrix it had constructed.

The verification is mechanical and cheap. **Inject the defect the case guards,
confirm the case reports it, restore.** In this project that has caught two
kinds of problem worth separating:

| What the injection revealed | Example from this project |
|---|---|
| The case was vacuous | A regex that lost an escape, passing and reporting nothing |
| **The injected defect was not one** | Dropping a `needs:` that another job still supplied |

The second is not a failure of the exercise, it is the exercise working. A
defect that turns out to be permitted means the rule was narrower than it
looked, and that is worth knowing before somebody relies on it.

#### What cannot be enforced mechanically, and what can

Nothing records that a case was written before a fix, in the same way nothing
records that a design was written before code. **What can be checked is the
state that results from skipping the step**, which is the same answer the
authoring-order rule gives.

| Enforced | By |
|---|---|
| Every collected case has an inventory row | `MQC_CMN_UNI_10183` |
| Every case is traced, both directions | `MQC_CMN_UNI_11122` |
| An identifier is not bound twice | `MQC_CMN_UNI_11121` |
| **The case would have caught the bug** | **Nothing. It is verified by injection and recorded in the log** |

The last row is the one that depends on discipline rather than machinery, which
is why the injection result belongs in `CLAUDE_LOG.md` alongside the fix: a
claim that a case was verified is worth what the record of the verification is
worth.

### Every Authored Anchor Carries An Exemplar

Added 2026-09-23.

**An anchor states what a level means; an exemplar shows it.** Authoring both is
one task, and a rubric carrying descriptions without exemplars is a scale nobody
can check.

**The exemplar is the judge's ground truth.** Calibration sends each exemplar
through the judge and compares the returned score against the level the exemplar
was written for. That comparison is the only thing in the system that can say
**which** judge is right when two judges disagree: a fixture comparison says a
score changed, and an exemplar comparison says the judge no longer means what the
anchors say.

| Without exemplars | With exemplars |
|---|---|
| Judge drift is detectable only as a score that moved | Drift is measurable against a known intended level |
| A harsher judge and a worse model look identical | They separate: exemplars move, or they do not |
| Recalibration has no target | The intended levels are the target |

**Three per criterion, at levels 1, 3 and 5**, matching the anchors invariant G3
requires. An exemplar is short, two sentences at most: it demonstrates a level
rather than exhausting it.

**A rubric authored without exemplars is uncalibrated**, and an uncalibrated
rubric silently accepts whatever the judge does. `MQC_CAS_UNI_10431` reports one.

### One Word Per Concept, And A Second One Is Drift

Added 2026-09-24.

**A concept gets one word, and that word is whatever the code already uses.**
Prose, identifiers and directories name the same thing the same way, or a reader
has to learn that three words are synonyms before they can read anything.

The instance that produced this rule: the evaluation data was called `corpus` in
shipped harness code and design, `data/` on disk, and `DAT` in requirement
identifiers. The third was introduced later and retired in favour of `COR`.

**Check the existing vocabulary before coining a word, including the parts you
did not write.** `corpus` was established in `ingestion/screening.py` and
`tier1_ingestion.md` before the repository split, and the newer prefix was added
without looking.

**A synonym that collides is worse than the word it replaces.** Two candidates
were rejected on that ground rather than on taste: `dataset` collides with
`TaskDataSet`, which is a **single** task record used across twelve modules, and
`collection` collides with pytest's test collection, which this project
discusses constantly. A word is only a better name if it is unambiguous in the
place it will be read.


### Requirements And Test Cases Are Two Registers, Marked Apart

Added 2026-09-25.

**An identifier says which register it belongs to, before anything else.**
Requirements carry `MQC_REQ_`; test cases never do.

```
MQC_REQ_<SCOPE>_<AREA>_<NNNN>     a requirement
MQC_<MODULE>_<LAYER>_<NNNNN>_<behaviour>     a test case
```

| | Requirement | Test case |
|---|---|---|
| Marker | `MQC_REQ_` | None |
| Second token | `HAR`, `CAS`, `MDL`, the scope | The module: `ING`, `EXE`, `EVL`, `CMN`, `CAS` |
| Digits | **Four**, zero padded | **Five** |
| Behaviour suffix | None | Required, lowercase, three characters or more |
| Example | `MQC_REQ_CAS_CI_0019` | `MQC_CAS_UNI_10428_an_inlined_excerpt_differing_from_its_fixture_is_reported` |

#### Why the marker rather than disjoint vocabularies

**The relationship is many to many**, with a strong pull in one direction. A
requirement is normally satisfied by several cases; a case frequently serves
several requirements, because a new requirement is often partly covered by
cases that already exist. In the shipped matrices: 122 requirements are
satisfied by more than one case, one by thirteen, and eighteen cases each serve
several requirements, one serving eight.

So the two registers are read together constantly, in the same tables, the same
prose and the same tooling. **An identifier that needs context to classify is an
identifier that will be classified wrongly.**

The first attempt made the token sets disjoint, which is true and insufficient:
it works only for a reader who has memorised both sets, and it has to be
re-established every time a register or a module is added. `MQC_REQ_` is
self-describing, and no case can carry it.

#### What went wrong without it

`MQC_CAS_` prefixed **both** registers: `MQC_CAS_CI_019` was a requirement and
`MQC_CAS_UNI_10428` a case. Nothing ever collided, because the widths differ.

**The hazard was the pattern, not the values.** A rename widening three-digit
requirement numbers matched the leading three digits of every case identifier,
and a lookahead added late was the only thing that stopped it rewriting 461 of
them. A near miss of that shape is a design defect, not a lucky escape.

**Widths remain as the second mechanism**, deliberately. Four digits against
five means a number alone cannot be misread even where a marker is stripped,
which is the same two-independent-mechanisms pattern the debug-artifact
exclusion uses.

`MQC_CMN_UNI_11160` enforces the separation, reading the shipped registers
rather than a permitted list.

### Identifier Rules
* **ID Blocks**: IDs are assigned once and never reused, including after a test is deleted. A retired ID stays retired so downstream history never silently rebinds an identifier to different behavior.
* **Behavior Suffix**: lowercase `snake_case` describing the asserted behavior, minimum 3 characters (`MQC_UNI_10001_rejects_missing_rubric_key`).
* **One Layer Per Class**: a test class carries exactly one layer marker and exactly one priority. `pytest` propagates class-level markers to every method, so a class mixing layers causes both tests to be collected by the wrong gate and neither to be gated correctly. Verified by collection probe 2026-09-19.
* **Priority Required On Graded Tests**: every **graded** test carries `@pytest.mark.priority(N)`, N in 0..4, assigned in the test design document. Definitions are normative in `docs/design/test_taxonomy.md`.

  **A precondition carries no priority marker because it is above the scale, not below it.** Saying it carries none invites the reading that it matters less, and the opposite is true: a P0 graded failure fails the run, while a precondition failure means the graded layers **never execute at all**, the run exits 3 rather than 1, and nothing is measured. That is a stronger consequence than any level inside the scale can express.

  The marker is a **budget** device and a budget only exists where claims compete. Preconditions do not compete: all are mandatory. Marking them P0 would also put 235 cases into a distribution denominator measured over 45 graded cases, turning a 10% ceiling into an arithmetic impossibility.

  An earlier wording said every test carries a priority, which contradicted the paragraph above and would have done exactly that.
* **Priority Distribution**: suite-wide ceilings of **10% P0**, **20% P1**, and **30% combined**. Checked programmatically once the suite reaches 20 cases; below that the check reports counts without a verdict. Breaching a ceiling is a finding, because an inflated P0/P1 population turns the 100%-must-pass gate into a hair-trigger that people resolve by demoting tests.

## 2. Test Execution Commands & CI Static Analysis

### CI Verification Sequence
```bash
# Gate 1: Pylint Static Analysis (must achieve 10.00/10; naming rules enforced by .pylintrc)
pylint ingestion/ execution/ evaluation/ tests/ --rcfile=.pylintrc

# Gate 2: Unit Precondition - 100% pass, zero skips. Blocks everything below.
pytest -m unit --junitxml=reports/junit_mqc_unit.xml --alluredir=reports/allure-results

# Gate 3: System Precondition - replay mode, 100% pass. Blocks the graded layers.
pytest -m system --mode replay --junitxml=reports/junit_mqc_system.xml --alluredir=reports/allure-results

# Gate 4: Evaluator Agent Run (graded)
pytest -m evaluator --engine gemini --junitxml=reports/junit_mqc_eval.xml --alluredir=reports/allure-results

# Gate 5: Tool-Use Compliance Run (graded)
pytest -m tool --engine gemini --junitxml=reports/junit_mqc_tool.xml --alluredir=reports/allure-results

# Gate 6: Model Security Suite (graded, exempt from distribution ceilings)
pytest -m sec --engine gemini --junitxml=reports/junit_mqc_sec.xml --alluredir=reports/allure-results
```

Gates run in order and each blocks the next. Gates 2 and 3 are deterministic and require no credentials, so they run identically on pull requests and on the schedule.

**These lines run unchanged in `bash` and in PowerShell**, which is a requirement rather than a coincidence: the harness is verified on Ubuntu and Windows (A18), and `code-style.md` section 8 requires every documented command to work on both. Paths use forward slashes, which Python accepts on Windows.

**The engine is written literally here and substituted by the workflow in CI.** An earlier version used a `bash` variable expansion, which PowerShell does not expand, so the documented command was silently wrong on one of the two supported platforms. In the workflow the value comes from `${{ matrix.engine }}`, which GitHub Actions resolves **before** any shell sees the line, making the substitution shell-agnostic by construction rather than by choosing a syntax both shells happen to share.

A shell-specific form anywhere in a tracked document is a defect, because the reader on the other platform has no way to tell that the line was never meant for them.

**Serialization, not separation, resolves the quota conflict.** Priority bands share a provider quota, so running them concurrently multiplies requests against one free-tier ceiling and defeats the request spacing in `test_taxonomy.md`. Running them **one at a time** removes that objection entirely.

| Requirement | Mechanism |
|---|---|
| Bands execute one at a time within a run | `strategy: max-parallel: 1` |
| Two workflow runs do not hit one engine at once | `concurrency: group: <engine>-<mode>` |
| `UNI` or `SYS` failure stops everything downstream | `needs:`, dependent jobs skip rather than run |

**`concurrency` is a mutex, not a queue.** A concurrency group holds exactly **one** pending job: with one running and one queued, a third arrival cancels the queued job and replaces it. Bands placed in a concurrency group therefore contend for a single waiting slot and the losers surface as cancelled, which reads as failure. `max-parallel` is the correct primitive for ordering within a run; `concurrency` is correct only for preventing overlap *between* runs.

**Only live-mode jobs need serialization.** Replay jobs consume no *candidate* quota and are pure CPU for the dispatch half, so the concurrency group is keyed on engine **and mode**, leaving replay legs fully parallel.

**The judge is not replayed, and this is where that shows.** `FixtureKey` is `(case_id, engine, observation_index)` and keys the candidate only, so a bound judge is a live call whatever the mode. A replay job therefore consumes no quota **because the gate does not judge a failed case**, not because replay makes judging free. A debug run passing `--judge-on-failure` in replay mode does spend quota, deliberately and against a named subset; `AP-Model-QC` `consumer_ci.md` section 6.4 carries the full table and records replaying the judge as an open question.

**Default topology, revised 2026-10-01.** The harness runs `UNI` and `SYS`, which is all it has: it owns no corpus, so it has no graded cases and no bands. **A consumer runs its preconditions in one job and each priority band in a job of its own**, specified in `AP-Model-QC` `consumer_ci.md` section 3.12.

**The earlier wording put bands inside one graded job**, on the ground that separate jobs multiply checkout and dependency-install overhead beyond the test runtime. That arithmetic is correct and was the wrong thing to weigh. Measured: a graded replay takes about 1.4 seconds against roughly 70 seconds of install per job, and the jobs run in parallel on free runners, so the cost is wall-clock rather than anything scarce.

**What it bought is the diagnosis.** One job running Gate 2 and the graded layers together means a red says either "our harness or corpus is broken and nothing was measured" or "the model underperformed", which are the two categories section 3.1 of `framework-rules.md` exists to separate and the verdict keeps apart as exit 3 against exit 1. Reading such a red meant finding the failing case, opening the test plan and looking up its priority before knowing which kind of problem it was. The band in the job name answers that before anything is opened, and the remedy differs at every level: P0 and P1 are release blockers, and a band below P1 is a bug to open and quarantine while review sets the date.

**A band is runnable alone**, which is what the debug workflow needs, and `--with-prerequisites` is how it collects the foundations it rests on. Inside a sequence the foundations are not re-run: the outcome travels instead, per harness `cmn_verdict_and_cli.md` sections 7.5.1 and 7.6.

```bash
# One band, alone, with the foundations it rests on
pytest -m "evaluator or tool" --priority 2,3,4 --with-prerequisites --engine gemini

# One band in a sequence, taking what the band before it established
pytest -m "evaluator or tool" --priority 2,3,4 --carry-outcomes reports/carry.json --engine gemini
```

**Every gate runs on every supported platform, and alternating between them is prohibited.** Platforms are separate jobs with `fail-fast: false`, so one platform's failure neither cancels nor masks the other. A run that covers only one platform yields no verdict for the same reason a manual selection does not: it cannot establish what the gate exists to establish. Supported platforms are listed in `DESIGN.md` section 5.0 and the preclusion is normative in `docs/design/extensibility_standard.md` section 7.

The live suite is the one exception and it is a narrowing, not an alternation: it runs on one platform because platform coverage tests the harness rather than the model, and the replay legs have already covered both.

Gate 1 is blocking for every later gate. A naming violation is a build failure, not a warning.

## 3. Change-Scoped Selection

Pull request runs execute only what the change can affect. Merge and scheduled runs execute everything.

### 3.1 Scope by path, never by priority

Priority is a **gating** dimension, not an **impact** dimension. Tests of several priorities routinely cover the same production code, so selecting "only P1" because a P1 test prompted the change would skip P2 and P3 tests exercising the same lines.

| Changed | Selected |
|---|---|
| A test module | That module's tests |
| A production module (`ingestion/`, `execution/`, `evaluation/`) | **All** tests covering it, every priority |
| Anything in the always-full list below | Everything |

Priority enters selection only when the changed paths happen to be priority-banded test files.

### 3.2 `MQC_UNI_` always runs

Unit tests are fast, need no network and consume no quota. They are also the precondition guaranteeing the harness is sound, which is why graded results mean anything at all. Skipping them saves seconds and risks running graded tests against a broken harness.

Scoping unit tests down to affected modules is permitted for a module-local change; skipping them wholesale is not. **The savings worth pursuing are in the graded live layers**, which cost quota and wall-clock.

### 3.3 A verdict requires a harness-computed selection

Testers may run any subset from a terminal or from CI. What a subset costs is the verdict, not the ability to run.

| `selection_mode` | Produced by | Verdict |
|---|---|---|
| `full` | No filter supplied | Yes |
| `change_scoped` | Derived from the diff | Yes |
| `manual` | Any filter flag present | **No** |

**Not all subsets are equal, and the difference is not size.** Change-scoped selection yields a verdict because it is derived from the diff, recorded, and backstopped by the full run on merge. A hand-typed subset is arbitrary with no backstop, and a verdict from one is a partial verdict.

A debug CI job is excluded from the durable record by **two independent mechanisms**: an artifact name the collector's pattern does not match, and row marking carrying `run_context: ci_debug` with `gated: false`. Structural separation alone fails the day someone widens the collector pattern; marking alone fails if nobody filters on it.

### 3.4 Full run on merge

| Trigger | Scope |
|---|---|
| Pull request | Scoped |
| **Merge to default branch** | **Full** |
| Scheduled | Full, live |

A partial run cannot establish that the default branch is green. If a skipped test is failing, it stays hidden until the next full run and then attaches to **whoever triggered that run** rather than to the change responsible, producing blame misattribution days after the fact. A full run on merge is inexpensive here: unit and system layers are free, and graded layers run in replay. Only the scheduled run spends quota.

### 3.5 Changes forcing a full run

* `conftest.py`, `pytest.ini`, `.pylintrc`, `pyproject.toml`, dependency pins
* CI workflow definitions
* `cmn/`: cross-cutting by definition
* **Golden rule and task data files**: changing the dataset changes every evaluation result
* **Replay fixtures**: changing a recorded response changes every replay outcome

The last two are easily overlooked and would silently invalidate a scoped run.

### 3.6 Documentation-only changes run no tests

A change touching **only** documentation triggers no test execution:

* `docs/**`, `README.md`, `CHANGELOG.md`, `CLAUDE.md`, `CLAUDE_LOG.md`
* `.claude/**`: governance prose, which documents behaviour rather than producing it

This is a **documentation-only** rule, not a documentation-exempt one: any non-documentation path in the same change selects normally. A design document revised alongside the code it specifies runs that code's tests.

`.pylintrc` and `pytest.ini` are **not** documentation. They are behavioural and appear in the always-full list at section 3.4.

**Branch-protection hazard.** Skipping a workflow through `paths-ignore` means its status check never reports. If that check is marked required in branch protection, a documentation-only pull request can never merge, because the required check is permanently pending rather than passing. The check must either not be required, or the workflow must always run and report success quickly when it selects nothing.

### 3.7 Failing safe

Changed files are resolved with `git diff --name-only origin/<default>...HEAD`, which requires `fetch-depth: 0` on checkout. GitHub Actions clones at depth 1 by default, where that diff fails or returns nothing, and an empty result is indistinguishable from "nothing changed", which would select **no tests at all**.

**An empty or failed diff falls back to a full run.** Selection logic defaults to running more, never less.

---

## 4. Allure Annotation Requirements

Allure labels are the grouping dimension downstream collection reads, so they are mandatory rather than decorative:

* `@allure.epic("AP-Harness-QC")` on every test class. The case repository uses its own epic, so a collector reading both can tell which produced a result.
* `@allure.feature(...)` naming the tier under test (`Ingestion`, `Execution`, `Evaluation`).
* `@allure.story(...)` naming the scenario.
* `@pytest.mark.priority(N)` on every **graded** test, translated by a `conftest.py` hook into the matching `@allure.severity(...)` label. A precondition carries no priority and therefore no severity label; the hook leaves it unset rather than inventing a default, because a default would make preconditions sortable by a severity nobody assigned. P0 maps to `blocker` through P4 to `trivial`; definitions are normative in `docs/design/test_taxonomy.md`. The run-verdict gate reads the marker and downstream analysis reads the label, from one source of truth.
* `allure.step` blocks around each distinct action. Steps are the only per-action record that survives into durable history.
* **Failure Taxonomy Tag**: every deliberate failure assertion attaches its `QC_LLM_*` or `QC_HARNESS_*` code from `framework-rules.md` via `allure.dynamic.label` or the assertion message, so root-cause class is recoverable from the artifact alone.

## 5. Downstream Artifact Contract

Test results are published as **standard CI artifacts** for read-only downstream consumption. This repository **names no consumer**, because the integration contract is a set of formats rather than an interface to a particular tool, and the tool may change.

* **No Reverse Dependency**: this repository MUST NOT import from, write into, or block on any consumer. There is no "publish metrics to a collector" step in its CI.
* **No Bespoke Telemetry File**: collectors parse standard formats, JUnit XML, Allure raw results (`*-result.json`) and Allure generated reports (`data/test-cases/*.json`). A hand-rolled summary file would be parsed by nothing and is prohibited.
* **The Contract Is The Artifact**: integration means uploading named GitHub Actions artifacts. Emit both JUnit XML (durable, per-test) and Allure raw results (carrying steps and labels).
* **Retention**: artifacts inherit GitHub's 90-day maximum for public repositories, so durable history depends on something outside this repository collecting them. This repository does not attempt its own history store.
* **Artifact Naming**: names must be stable and pattern-matchable across runs. Renaming a published artifact silently breaks downstream history for this repository.
* **Onboarding Is Not This Repository's Concern**: a consumer registers this repository on its own side. That is never a code change here.
