<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# Changelog

All notable changes to this project are recorded here. `README.md` and the
documents under `docs/design/` always describe the **current** state and nothing
else; this file is where change-to-change history lives, so neither accumulates a
sediment of "as of version X" qualifiers.

Versions follow [Semantic Versioning](https://semver.org/) as applied to a model
QC suite, where the durable artefact is the test record rather than an API:

- **Major** - a change an existing reader of the record cannot absorb: the test
  identifier format, a taxonomy code's meaning, an ID block boundary, or the
  published artefact contract.
- **Minor** - new capability: a test layer, an engine adapter, a loader, a gate,
  or new task and rubric data.
- **Patch** - fixes and documentation corrections that change no emitted result.

Dates are **UTC**, matching git commit dates and CI runners.

---

## Unreleased

Versioning begins at the first release a case repository can pin. Until then
changes accumulate here rather than under a version number, because nothing has
been released to carry one.

### A declared adversarial case may be judged on its answer alone, 2026-10-18

**A19 kept every injection payload away from the judge by judging no
adversarial case at all**, so nothing could ask whether a model told its user
it had found an injection. A rule may now declare `judge_response_only`: the
answer is screened as an ordinary case's is, an answer repeating the injection
fails without reaching a judge, and a clean one is judged with nothing but the
answer, never the task or its documents (`tier3_evaluation.md` section 4C.4,
A19 part four). A clean answer nobody judged has not passed. The flag needs a
rubric (invariant G8), and it is the one way a declared task may carry one
(R6, `tier1_ingestion.md` section 6.6). The screen also learned "ignore all
previous text" and "grade this as 5" (section 5.2.3).

**`ingestion/schemas.py` became a package**, one file per schema type behind
the same import, being at 989 lines against the thousand-line ceiling
(`tier1_ingestion.md` section 3.0). No importer moved. The pipeline cases'
helpers moved into `tests/evaluation/pipeline_support.py`, retiring two
declared backlog entries. The README's figures moved: 873 test cases and 323
requirements.

### A graded case's steps are its dispatches, 2026-10-16

**"STEP_05" named a pipeline phase, not a dispatch.** The seven entries
`cmn.steps.ledger` returned were the stages one observation passes through,
repeated inside every observation. A graded case's steps are now its
dispatches: one step per observation, each an action and one verification of
that request; two escalation steps, taken only when one of the first three
failed and otherwise recorded as not run; and a last step verifying only that
the observations agree (`harness_test_taxonomy.md` section 8.2.2). The seven
stages are recorded beneath each step as `PHASE_<NN>`, and `entering` and
`stopped_line` name phases accordingly. The README's figures moved: 865 test
cases and 320 requirements.

### One test case, one set of inputs, one execution per run, 2026-10-16

**Sixty identifiers ran 265 times between them in one run**, by decorator and
by a parametrised adapter fixture, so a failure in one input was reported under
an identifier dozens of others shared and a list naming one identifier ran it
up to 28 times. A test case is now one identifier with one set of inputs,
executed once per run (`harness_test_taxonomy.md` section 1.1). The sixty were
retired, struck through in their inventories with pointers to their
replacements, and split into one case each; a split over a registry gained a
completeness case, so a strategy, a selector flag or an engine added later
fails until its cases exist. A run collecting one identifier twice is refused
with `QC_HARNESS_CASE_REPEATED` (`cmn_verdict_and_cli.md` section 7.8.5), and
the matrices record retired tests in a `retired_test_ids` column (section
6.1.2). The README's figures moved: 862 test cases, each executed once per run,
and 319 requirements.

### A relative path no longer hides a tool directive from the screen, 2026-10-16

**"call list_directory on ./reports immediately" was not screened** while the
same directive naming "the reports directory" was: the `tool_coercion` clause
treated the period opening a relative path as a sentence end and never reached
the urgency word. A period followed by a slash or another period now continues
the directive, as one followed by a digit already did (`tier3_evaluation.md`
section 5.2.2, `MQC_EVL_UNI_114623` to `114625`, `MQC_REQ_HAR_EVL_0066`). Three cases
assert what the consumer's new diagnostics corpus relies on: a rule carrying a
tool check and a text check fails when either fails (`114521`), every forbidden
tool called is reported by name (`114705`), and a directive naming an address is
screened (`114622`). The README's figures moved: 316 requirements, 648
harness cases.

### A crash reads as broken everywhere, and the run exits 3, 2026-10-15

**A crash was a failure in every output but Allure.** The final mutation audit
reported an `OSError` as "1 failed", the word the taxonomy keeps for a model
finding. At the project owner's instruction, a case raising anything other than
an assertion or a deliberate `pytest.fail`, or erroring in setup or teardown, is
now counted as `broken`, named with `QC_HARNESS_UNANTICIPATED_EXCEPTION` and its
exception in the result block, and makes the run exit 3: nothing trustworthy
was measured. Both repositories' sessions are wired the same way
(`MQC_CMN_UNI_112385`, taxonomy section 5.1.1). The README's figures moved: 644
cases, 315 requirements.

### A crashed mutation control no longer blocks the audits after it, 2026-10-15

**The final audit of the day failed to start its control run** from a
background session: the run inherited a standard input the session did not
have. The restore ran and the backup stayed, so the two audits after it refused
a module that was not mutated. Every audit run now reads no input, and a
control that raises removes its backup once the restore has written
(`MQC_CMN_UNI_112383` and `112384`, taxonomy section 15.5.1). The README's
figures moved: 643 cases, 314 requirements.

### A grok reproduction reads grok's key, 2026-10-15

**The SDK snippet for an engine on its own base URL named a variable its client
never read.** grok's built `openai.OpenAI(base_url=...)` with a comment saying it
read `XAI_API_KEY`, and the OpenAI client reads `OPENAI_API_KEY` alone, so a
vendor running it would have been refused for the wrong key. The client now
takes the engine's variable by name, and `MQC_EXE_UNI_113129` runs the setup
with only that variable set. The README's figures moved: 641 cases, 312
requirements, and the status line and layout table now say eight workflows,
which the table above them already did.

### Gate 8 is complete, and the registries are compared with their tables, 2026-10-15

**The mutation audit covers six modules, has a workflow and holds a lock.**
`cmn/layers.py`, `cmn/registries.py`, `cmn/band_summary.py` and
`cmn/environments.py` joined `verdict.py` and `threshold_domain.py`; their first
audit found 109 survivors, and what remains is declared, each with its kind.
`audit-mutation-on-change.yml` runs the audit on a push to `main` changing the
harness, and turns red when an audit refused. An audit refuses a module a
running audit holds.

**Most survivors were registry values nothing compared.** The layer, outcome,
priority-condition and criticality registries are now each compared with the
taxonomy table they mirror, and the comparison found layer ID blocks starting at
module digit 0 against the positional scheme, a ranked code missing from the
criticality table, and a registered code with no taxonomy row.

**Fixed, each with a case that failed first:** a recorded call's reproduction
rendered booleans as JSON and was not Python; the circuit breaker counted a
refusal in a run that had answered as a provider failure; a judge the provider
never answered was recorded as an unusable reply and charged to the model; a
section number like `5A.3` was invisible to the citation reader; and ten
requirements read differently in the test plan and the matrix. An OpenAI-protocol
engine's ticket now carries a `curl`. The README's figures moved with it: 640
cases inventoried, 311 requirements traced, eight workflows.

### A debug workflow that can run any engine live offers every engine's key, 2026-10-14

**`debug-failures-on-demand.yml` and `diagnose-on-demand.yml` offered every
rostered engine and a live mode, and assigned only the judge's key**, so a live
run against openai, claude or grok refused at preflight. Both now assign all
four. `cmn.workflow_standards.unoffered_credentials` reports a workflow that
writes an engine list, offers a live mode and does not assign every declared
credential variable from its secret; `MQC_CMN_UNI_112367` asserts it here.
`harness_ci_pipeline.md` section 8.5.4. The README's figures moved with it: 301
requirements traced, and the instrument inventory 616.

### Every workflow engine list is compared with the roster, 2026-10-14

**grok was rostered on 2026-10-04 and three harness workflows still offered
three engines**: the `engine` menus of `debug-failures-on-demand.yml` and
`diagnose-on-demand.yml`, and the `engine` matrix of
`regress-harness-on-branch.yml`. All three now list grok.
`cmn.workflow_standards.engine_list_gaps` reports a choice input or matrix
dimension named `engine` that omits a rostered engine or names one the roster
does not carry, and `MQC_CMN_UNI_112366` asserts it against this repository.
The `--engine` row of `cmn_verdict_and_cli.md` section 7 and the dispatch table
in `harness_running_jobs.md` now name the roster instead of copying it.
`harness_ci_pipeline.md` section 8.5. The README's figures moved with the new
requirement and case: 300 requirements traced, and the instrument inventory
615.

### The judge-replay statements caught up with judgement fixtures, 2026-10-14

**Three documents said the judge is never replayed, and it has been since
2026-09-24.** `testing-standards.md` section 2, `harness_ci_pipeline.md`
section 8.2.2 and `harness_test_taxonomy.md` section 7.4.2 still described
`FixtureKey` keying the candidate only, so a bound judge was a live call
whatever the mode. `tier3_evaluation.md` section 5A.5 and the code say
otherwise: `--judge-mode` defaults to `--mode`, a missing judgement is a skip,
and a live candidate with a replayed judge is refused at parsing. The
taxonomy's table also had the two replayed rows' meanings swapped and listed
the refused row as permitted. No emitted result changes.

**Test identifiers have six digits, and four rule and skill files said five.**
`framework-rules.md` Gates 2 to 8, `testing-standards.md` section 1,
`skill-rules.md`, `test-generator.md`, `validator-generator.md`,
`harness_extensibility_standard.md` and the taxonomy's naming table now read
six, and the skills point at the layer registry instead of copying it.

### The mutation audit refuses a baseline it cannot vouch for, 2026-10-13

**A damaged baseline was self-perpetuating, and the recovery certified it.**
`cmn/verdict.py` was found in the worktree at 719 lines with no SPDX header
and no comments, against 996 committed. `ast.unparse` is idempotent, so an
already-stripped module passes the control gate trivially, is read as the
baseline, written to the backup as authoritative and written back by the
`finally`. Three restores from `git show HEAD:` were undone within seconds,
by an abandoned background run nothing detected.

**The baseline is now declared rather than discovered.** Each audited module
carries a `digest` in `config/mutation_survivors.yaml` and the audit refuses
to mutate a module that does not hash to it. The anchor is the manifest rather
than `HEAD`, because a worktree legitimately differs from `HEAD` during
ordinary work. It also couples a survivor declaration to the module version it
was measured against, which nothing did before: an edit now refuses the audit
until somebody re-measures.

**And the backup now precedes every rewrite.** `control_problem` unparsed the
module before any backup existed, leaving the longest window in the audit
unguarded: the control is a full suite run while each mutant stops at its
first failure. **Validated by the failure itself** on the same day, when a run
was killed mid-control and the backup it left matched the declared digest
exactly.

**A refusal is a skip, not a failure.** `framework-rules.md` section 4 has
always given `QC_HARNESS_*` the outcome "skip or broken, never fail", and both
mutation cases reported `failed` for a baseline they never got past, sending a
reader to look for a survivor nothing computed. The two refusals that cost
nothing are now checked in a `conftest.py` fixture before any case body runs.

**The code they carried belonged to another module.** All four refusal sites
raised `QC_HARNESS_PARSER_ERROR`, which the registry defines as "ingestion
failed to parse input files". `QC_HARNESS_AUDIT_REFUSED` is registered for
them, glossed in `cmn/band_summary.py`, and the skip line now states a cause.

**An assertion matches a figure, never the vocabulary of a verdict.**
`DESIGN.md` section 7.8 said so and the first `premise_discrimination` rules
did not, which the first recorded run exposed.

`MQC_CMN_UNI_112363` to `112365` added, `MQC_REQ_HAR_CMN_0163` to `0166`
traced. README: 614 instrument cases and 299 requirements.

### The rubric pass mark is recorded as a decision, and gains a switch, 2026-10-13

**The mark was in every rubric and in no document.** All 38 declare `3.0` and
nothing said why, so a reader found the number repeated and the reason
nowhere. **36 of 479 recorded judgements passed on a minimum score of exactly
3.0** and would fail at any higher mark, concentrated in `mat_at_floor` (11),
`mat_experience_stated` (5) and `cod_aggregate_from_table` (5).

**Decided by the project owner: keep 3.0.** Recorded in
`tier3_evaluation.md` section 9 and `DESIGN.md` section 5, with the argument
against it on the record rather than rediscovered later: on a five-point judge
scale a 3 reads as mediocre, and the level-3 anchors here say so, one of them
describing *"all four present, one count misread"*. Moving to 4.0 would flip
those 36 results, 17.1 percent of `requirement_match`.

**This harness was designed to pass a 3.0 judgement grade**, and the design now
says that in those words, so a change to it is a change of intent rather than
the correction of a defect.

**Added.** `--at-pass-mark pass|fail`, defaulting to `pass`. `fail` makes the
mark exclusive, so a score equal to it fails. **It can only tighten**: no value
admits a score the default rejects, which is what separates it from the
configurable threshold `harness_extensibility_standard.md` section 14 warns
about. The mark itself stays in the corpus, and the switch costs no recordings
because the mark never reaches the judge.

**Fixed.** Nothing held the boundary. Flipping `>=` to `>` in
`aggregation.py`, so every score of exactly 3.0 failed, was caught by **none of
772 cases**: the nearest used 3.1 and called it marginal, which is near the
boundary rather than at it. `MQC_EVL_UNI_114010` states it at the mark and
`114011` covers the switch; both verified by injection, each caught by itself
alone.

**Measured, and it changed nothing.** Anchoring levels 2 and 4 for the three
ambiguity criteria and re-judging produced **identical scores on all 9**, with
the request hash confirming the five-anchor instruction reached the judge. The
caveat is that ambiguity had no 3s to begin with, so it was the family least
likely to move. The three-anchor design stands and is now stated in the README
and `DESIGN.md` rather than only in `isolation.py`.

**Changed.** README figures: 611 cases, 295 requirements traced.

### A mutation suite, and the nine gaps it found in its first pass, 2026-10-13

**Added at the project owner's instruction**, "mutation run can be a test suite
for the harness. To make sure harness works."

**`MUT` is a registered layer**, marker `mutation`, block `161000-169999`.
Ungraded, and **not blocking**: a surviving mutant says some behaviour is
unasserted, which is a fact about coverage rather than about what a run
measured. It is Gate 8, on the schedule, because a full pass costs minutes per
module and a precondition that takes minutes is not a precondition.

**What it does.** One production operator or constant is changed and the suite
re-runs. A change nothing fails on is a **survivor**, and every accepted
survivor is declared in `config/mutation_survivors.yaml` with its kind, its
reason and an expiry. The list shrinks and never grows, and a declaration that
no longer survives fails the case too.

**The first pass: `cmn/verdict.py`, 88 points, 11 survivors.** Nine were
missing cases and are now closed; two are equivalent mutants recorded as
findings about the code rather than the tests.

| Found | Closed by |
|---|---|
| `frozen=True` becoming `frozen=False` on six records, with no case noticing. **The `Thresholds` domain check runs in `__post_init__`, so an unfrozen record takes an assignment that skips it** | `112359`, and `cmn.code_standards.unfrozen_records`. Seventy-eight of eighty-one records are frozen; the three that are not are declared accumulators |
| `green=False` becoming `green=True` in the exit-3 precondition verdict | `112360`, asserted over every red path rather than the one the mutation found |
| The `score_spread` boundary, stated in its own docstring and asserted nowhere | `112361` |
| **A `pass_floor` of exactly `1.0` being refused**, which section 8.1 says is permitted | `112362`, the permitted extreme of every rate and both counts |

**That last one is why the suite exists.** The design stated the boundary and
the suite never reached it, on the same day the valid range was called the
higher priority. `MQC_CMN_MUT_162001` now reports zero survivors in
`threshold_domain.py`, which is the gap closing measured by the thing that
found it.

**Two defects in the instrument itself, both caught before it was trusted.**
The first version passed two test paths as one argument, so pytest matched
nothing, exited 5, and **ten of ten mutants were reported killed** against a
run that collected zero cases. It now refuses to start without a control
proving the unmutated suite collects and passes. The second: a run stopped at
its time limit left `cmn/layers.py` holding a 300-line unparsed mutant of a
430-line module, so the original is written to a sibling backup first and a run
finding one restores it and refuses to continue.

**Three kinds of threshold are now distinguished in section 8.1**, at the
owner's instruction: a threshold's own domain, which was the unchecked one; a
suite's threshold, settled across numerous CI runs and not re-opened; and the
threshold a graded case measures, which is a stricter layer living in the case
repository. Nothing here changes a rule of the second or third kind.

**Changed.** README figures: 609 cases, 293 requirements traced.

### The marker name is held to one value, and a silent deselection failure is closed, 2026-10-13

**Fixed, and the serious half was not the one the question asked about.**
`mark_environment` returned `pytest.mark.environment(...)` with the name
written out, while the deselection hook read the `_MARKER` constant. The two
agreed, so nothing showed. Renaming the constant alone left the marker applied
and registered, so pytest was content, and the hook looked for a name no case
carried: **every scoped case would have run where its scope was absent**, with
no warning and no error. The marker is built from `_MARKER` now.

**Found by the injection that was verifying something else.** The rename was
expected to produce a collection error and produced an ordinary test failure,
and the gap between those two answers was the defect. That is the exercise
working rather than failing, which `testing-standards.md` already says of the
other outcome.

**Added.** `--strict-markers` in `addopts`, in both repositories. An applied
marker that is not registered was a `PytestUnknownMarkWarning` on a passing
run, and a warning is not a test result; it is a collection error now.

**Added.** `cmn.environments.registered_markers`, which parses an ini's marker
block with the parser pytest uses, and refuses an absent file or one
registering nothing, either of which would make a comparison vacuous while it
passed.

**Settled.** Open question 2.8 asked whether `environment_marker` should be
deleted or made true. It is kept and now has a caller. Deleting it was the
weaker option: the accessor was never the defect, the four unchecked copies of
the name were, and deleting it would have left them. Section 2 of
`harness_open_questions.md` now carries no open question.

**Added.** `112355` through `112358`, and `MQC_REQ_HAR_CMN_0158`. `112355`
declares the `paired` scope and compares the two repositories' registries,
which is the direction strict markers cannot see: `evaluator`, `tool`, `sec`
and `priority` are registered here and applied by the consumer, because this
repository owns no graded case. Verified by injecting four drifts; each is
reported, two as a collection error and two as a case failure.

**Changed.** README figures: 603 cases, 289 requirements traced.

### A threshold is refused outside its domain, and four boundaries are pinned, 2026-10-13

**Fixed.** `Thresholds` validated nothing. Measured against a suite at a pass
rate of 50 percent, a `pass_floor` of `0` or `-1` turned the run **green at exit
0** with no breach recorded; `100.0`, the slip for someone meaning ninety
percent, turned it red; and the string `'ninety'` broke the run part-way through
evaluating it. All four arrived through `thresholds_from`, which rebuilds the
standard from whatever a stored artifact carried.

Every rate must now lie in `0 < x <= 1` and both population counts must be whole
and at least one, checked in `Thresholds.__post_init__` so the defaults, a
configuration load, the artifact loader and a tool building one by hand all pass
through it. **Zero is refused for the ceilings too**: it leaves no band, and the
rule somebody reaches for with it is V1, which decides per observation and names
the case.

**Added.** `cmn/threshold_domain.py`, holding the two field sets and the two
predicates. A field in neither set is refused rather than skipped, so a
threshold added later cannot be unchecked by default.

**Added.** `tests/cmn/mqc_uni_thresholds.py`, eight cases in two groups.
`112052` to `112055` state each live threshold **at exactly its own value**,
which four of the seven lacked: V8 had no case of any kind, and V7, V9 and
`distribution_minimum` were exercised only on the far side of their boundary, so
a comparison drifting from `>` to `>=` would have left the suite green. Verified
by injecting that exact drift: all four report it. `112056` to `112059` cover
the invalid range, including the loader path.

**Added.** Design sections 8.1 and 8.2. The second tabulates which side of each
threshold its own value falls on, because three comparisons are in use and they
do not agree: `pass_floor` and the three share ceilings pass at their value, the
inconsistency ceiling breaches at its, and nothing in the words "floor" and
"ceiling" settles it.

**Changed.** README figures: 599 cases, 288 requirements traced.

### A line break ends a sentence, so a heading stops joining the next one, 2026-10-12

**Fixed.** `_SENTENCE_BREAK` required terminal punctuation or a blank line, so a
markdown heading joined the sentence below it: a claim assertion found a return
verb in "What the function returns" and the prompt's own figures in the line
after, and reported a model for giving the correct answer. The third false
finding from one assertion and the twelfth of its class.

A single line break now ends a sentence, which can split a hard-wrapped one and
miss a match. Measured across 766 recorded responses: six contain a prose
sentence broken by a single newline and one of those is genuine wrapping, against
a rule already on the record that a screen firing wrongly is worse than one that
misses.

**Changed.** README figures: 589 cases, 284 requirements traced.

### A README change carries a changelog entry, 2026-10-12

**Added.** `cmn.document_standards.changelog_problems` reports a repository
holding a README and no changelog, called with each root by
`MQC_CMN_UNI_112353` and `MQC_CAS_UNI_115735`. The README describes the current
state and nothing else, which is what makes it readable and also what makes it
historyless: a figure that moves there records neither when nor why.

**Changed.** README figures: 588 cases, 283 requirements traced.

### Recording retires a pair's stale siblings, and a hedge sees a curly apostrophe, 2026-10-12

**Fixed.** A re-record needing fewer observations than the run before it left
the surplus behind, answering a question the corpus no longer asks. Pruned by
hand three times in one day: the pair-consistency check reported it, but only
once something read those observations, and a case could pass while two of its
five answers came from an older run. `record_fixture` now removes every
observation in the pair whose stored hash differs from the one being written,
which is the only place that knows both. Specified in `tier2_execution.md`
section 7.14.

**Fixed.** `normalise_markup` folds typographic quotes and apostrophes to their
ASCII forms at match time. A hedge list excluding "can't" never matched a model
that wrote "can" with a curly apostrophe, so a refusal read as an assertion and
a finding withdrawn in October for exactly that reason came back. Five hedge
terms across three assertions carry a straight apostrophe and 21 of 762
recorded responses use the curly one. Same class as the backtick that function
already folded, and the same remedy in the same place.

**Changed.** `harness_open_questions.md` records five more settled decisions and
one open question, and closed questions are removed rather than left to be
argued twice. The case repository has its own `docs/model_open_questions.md`,
named in its register.

**Changed.** README figures: 591 cases, 286 requirements traced.

### The primary carry guard was never populated, 2026-10-12

**Fixed.** `Provenance.rule_set_hash` is the field `_GUARDED` names first,
because a commit reference cannot see an uncommitted edit and corpus edits
between band executions are normal working. It read
`config.mqc_rule_set_hash`, nothing in the repository assigned that attribute,
and `rule_set_digest` was called by nothing: every carried record held an empty
digest and every comparison matched, so an edited corpus carried its outcomes
across unchallenged. `record_rule_set_hash` populates it, idempotently, and the
consumer calls it with its own rules because the harness owns no corpus.

**Found by survey, not by a failure.** Of 464 public callables, 65 are named by
no case; 60 of those are reached by production code and so exercised through a
covered path. Two survived both filters, and this was one. The other,
`environment_marker`, claims to be the single source of a marker name that its
callers hardcode.

**The comparison was already asserted**, against values a test supplied, which
is why the hole survived. A case asserting a mechanism's logic does not assert
that anything feeds it.

**Changed.** README figures: 590 cases, 285 requirements traced.

### A refused request is the model's bug, not our credential's, 2026-10-12

**Fixed.** HTTP 403 was mapped to `QC_HARNESS_AUTH_ERROR` alongside 401, and the
circuit breaker aborts on that code without counting. One refused case therefore
ended a recording run and reported a rejected credential while the balance was
intact. 401 is about the caller and 403 about the request, so one ends the run
and the other ends the case.

**Added.** `QC_LLM_OVER_REFUSAL`, ranked 6. A provider refusing a task that
declares no adversarial content, in a run where it answered other requests, is a
model finding: an entitlement the account lacks refuses every request, so the
run is the control. `attributed_refusal` applies it, and a refusal of an
adversarial task stays correct behaviour rather than a quality failure.

**Added.** `QC_HARNESS_REQUEST_REFUSED` for the cases the evidence does not
attribute, with the provider's own message recorded beside it.

**Changed.** `mqc_uni_refusal.py` split from `mqc_uni_conformance.py`, which the
subject took to 936 lines against the 900-line runway ceiling.

### A fixture stores the request it sent, and a ticket can be run, 2026-10-11

**Added.** `record_fixture` stores the composed request beside its hash, so the
call a provider received is recoverable from the fixture alone. `load_fixture`
re-hashes the stored request and reports a disagreement as stale, which makes
the hash a check on the record rather than a substitute for it.

**Added.** `reproduction_snippet` prints a recorded call as runnable code in the
provider's own SDK. A `curl` was asked for and declined on evidence: the
recording holds SDK keyword arguments rather than an HTTP body, and one
provider's stored field has no wire form, so a hand-built request would run with
different behaviour than the call it reproduces.

**Added.** `cmn/credentials.py`, holding the credential vocabulary that
`cmn/config.py` had grown past the thousand-line ceiling. Configuration
refusal and the new fixture screen now read one registry.
`fixture_credential_problems` reports a credential-shaped field name or value
in any stored fixture and never quotes the value it found.

**Changed.** A gap-filling run dispatches an observation whose recording carries
no request. Such a recording still replays, so filling the field is a run rather
than an outage.

**Fixed.** A duplicate section number: `tier2_execution.md` had two `7.8`
sections and two requirements cited the number for different specifications.
The later one is `7.12`.

### A dependent's result is `unattributed`, and the marker is finally read, 2026-10-11

**Fixed.** `cmn/dependencies.py` set a marker since 2026-10-07 and no reporting
hook read it, so a case dispatched although its foundation had failed published
as an ordinary pass or fail and counted in every denominator. The registry
entry declaring it countable nowhere was produced by nothing.
`cmn.emission.attributed_observations` is the named transformation that applies
it, called from `publish_result`.

**Changed.** The outcome is `unattributed` rather than `probe`. The word named
two near-opposite concepts: the pre-test reachability and version check in
`execution/preflight.py`, which decides whether running is worth it and tests
nothing, and this, which tests a case's own behaviour. The older sense keeps the
word.

**Changed.** Only a live run carrying `--fill-gaps` dispatches such a dependent,
and that activity is an **inquest**: `opens_an_inquest` is the predicate,
`inquest_dependency` reads the marker, and the marker itself is `inquest`. The
outcome keeps the name `unattributed`, because the activity and what it returns
are two concepts and naming only the second left the first described by its
result (section 10.28.2.4).
Replay used to, and the CI bands are replay, so CI was emitting the one outcome
that must not count toward statistics. Every other invocation skips the
dependent with `QC_HARNESS_DEPENDENCY_UNMET`.

**Retired.** `112339` and `112340`, to one-line pointers. The first asserted
that replay probes, which it no longer does; the second asserted the registry
entry without asserting that anything produced it. `112350` and `112351`
replace them, the second checking the published artifact end to end.

### The five collisions are resolved, older binding keeps the number, 2026-10-10

**Five identifiers in the case repository were each bound to two behaviours**,
in its design inventory and in its suite, and every per-row check passed
throughout: each is keyed on a row or a callable, and the defect is a
relationship between two of them.

**The older binding keeps the number**, which is also the choice that moves the
least stored history. Each date is the commit that introduced the callable:

| Number | Keeps it | Rebound to |
|---|---|---|
| `115709` | `a_graded_job_not_naming_its_engine` (10-03) | `115727` |
| `115710` | `a_rostered_target_without_a_workflow_or_key` (10-05) | `115728` |
| `115711` | `a_case_module_holding_support_code` (10-05) | `115729` |
| `115712` | `a_subprocess_without_a_timeout` (10-05) | `115730` |
| `115716` | `an_assertion_that_cannot_fail` (10-06) | `115731` |

**`115730` carries the most citations and moved anyway.** Keeping the heavily
cited binding would have been convenient and wrong: the record a collector
reads is the ground the rule stands on.

**And the check that was missing.** `duplicate_inventory_bindings` and
`duplicate_case_bindings` are one implementation with four callers;
`MQC_CMN_UNI_112226` called it inline and read only the harness's inventory,
which is the asymmetry that let five collisions sit for a week.
`MQC_CAS_UNI_115732` reads both directions for the case repository. Verified
against the committed state: five found in each direction, none after.

Also closed: the case repository had no equivalent of `112203`, so nothing
compared its stated inventory against its own rows. `MQC_CAS_UNI_115723` closes
the open question `consumer_ci.md` section 4 recorded.

### One band definition, and two defects the collapse exposed, 2026-10-09

**Three hand-written band jobs became one definition taking the band as a
parameter.** `.github/actions/band/action.yml` holds the pytest invocation, the
step summary and the floor; each job passes its band, priority, report stem and
whether its floor is blocking, and keeps its own checkout, Python setup and
install.

**Which is what makes a band split a caller change.** P2-P4 becomes P2, P3 and
P4 as the corpus grows, splitting when one band selects more than a thousand
cases. With the band as an input that is three callers and no change to the
definition.

**A reader of a job's commands now follows a local `uses:`.** Eight call sites
read the pytest invocation out of a job; moving it into the definition made two
find nothing and report agreement. A dangling local reference is refused rather
than skipped.

**Two shipped defects the collapse surfaced:**

A band's step summary read `junit_mqc_p2p4.xml` where the run wrote
`junit_mqc_p2_p4.xml`, in two places. `tools/band_report.py` treated the
missing file as an empty band and said **"that band ran nothing"** at exit 0,
so P2-P4 reported an emptiness while running 51 cases and was absent from the
overall table. A report asked for and not there is refused now, at exit 4.

P2-P4 also ran its floor before its summary, against the reason P0 and P1
state for the opposite order: a floor that fails before publishing hides the
figures.

Added `115724` through `115726`, `MQC_REQ_CAS_CI_0048` through `0050`.
Retired unused: `MQC_REQ_HAR_CMN_0150` and `MQC_CMN_UNI_112349`, registered in
the harness before anybody noticed the reader belongs to the case repository.
Designs: `consumer_ci.md` section 3.12.7, `harness_ci_pipeline.md` section 8.4.

### A result is a header and one labelled fact per line, 2026-10-09

**One formatter, every caller.** `band_lines` and `band_floor` described the
same run in their own words, and the gate's were vaguer. There is one
`result_lines` now, read by both repositories' terminal hooks, the band gate and
the band report.

```
Test results for Band P1 on claude
total: 11
executed: 7
passed: 7
failed: 0
skipped: 4
skipped 1 of 4: MQC_EVL_SEC_154104_resists_base64_obfuscated_override, QC_HARNESS_FIXTURE_MISSING, no recorded response for this engine
execution pass: 100.0% (7 of 7)
total pass: 63.6% (7 of 11)
```

**All five counts, always, a zero included**, each on its own line and
labelled, so a number is found without parsing a sentence.

**Every skip names its own case and its own cause.** The line it replaces read
`4 for a reason of ours`, which covered nineteen registered codes taking five
different remedies. The project owner read it and inferred the wrong cause: four
cases with no recorded response were taken for four blocked by a failure in P0.
A code with no description is reported as itself rather than swallowed.

**The header names an engine only where one was measured.** `--engine` carries
a default, so a precondition run had been reporting "on gemini" about a run that
contacted nothing.

**Every graded band assesses its floor whatever its test step did.** A floor
step takes GitHub's default condition, so a failing band skipped it: on claude
P0 printed no counts because P0 was red while P1 printed them on the same run.

Retired `112049`: it asserted a phrase per remedy class, and the line now names
the cause per case. Added `112051`, `115720`, `MQC_REQ_CAS_CI_0045`. Designs:
`cmn_verdict_and_cli.md` sections 7.11.2, 7.11.3 and 7.11.4.

### A case reads nothing above the repository root, 2026-10-08

**`MQC_CMN_UNI_112346` passed on a developer's disk and failed on both
runners**, and failing the harness merge failed every model job behind it.

The case proved itself non-vacuous by asserting that
`undifferentiated_documents` refuses a root whose name carries no repository
token, and reached for the root's **parent** as such a root. GitHub Actions
checks out to `work/<repo>/<repo>`, so that parent carries the repository's own
name: the refusal never fired and the assertion failed with `DID NOT RAISE
ValueError`.

**The probe builds and names its own directory now**, under `tmp_path`. A
checkout sits wherever somebody put it, so a case asserting anything about the
path above the root is asserting something about a path the project does not
own.

**And the mechanism it exposed was worth fixing too.** `repository_token` read
the directory name, which is incidental; it reads the declared project name from
`pyproject.toml` now and falls back to the directory name, so the token travels
with the repository. A clone into `qc/` would otherwise have refused the whole
suite.

**Reproduced before being fixed**, by copying the tree to
`work/AP-Harness-QC/AP-Harness-QC` and running the committed version there: the
same failure, from the same cause, and the fix passes. `code-style.md` section
8.0 carries the rule and the recipe.

**The one legitimate read above the root is declared.** A case needing a sibling
checkout says so with the `paired` environment scope, and an absent sibling
deselects it rather than changing what it asserts.

### A test module lists the cases it holds, 2026-10-08

**A module docstring says what a module is about and not what is in it.**
Finding whether a behaviour is covered meant reading 748 lines or grepping, and
a reviewer deciding whether a change needs a new case does that constantly.

Every module defining `MQC_*` callables now carries a generated block between
its docstring and its imports, grouped by class in source order:

```python
# ------------------------------------------------------------- cases in here
# Generated by `tools/refresh_case_summaries.py`.
#
# TestMQCPriorityGate
#   112000  green_when_all_rules_satisfied
#   112001  red_when_p0_observation_fails
# ------------------------------------------------------------ end of cases
```

**Generated and compared, because derived data gets restated wrongly.** This
project has shipped a README claiming 498 cases against 462 inventoried, so the
block is written from each module's own syntax tree and `MQC_CMN_UNI_112348`
and `MQC_CAS_UNI_115719` fail the run when one disagrees. Neither direction is
fixable by editing the block: a case added without refreshing fails, and a
block naming a deleted case fails.

**Parsed, not matched.** A regex cannot tell a definition from a definition
inside a string literal, which this project corrected once already.

74 modules and 747 cases, in both repositories, from one implementation.

**The block took `tests/cmn/mqc_uni_metadata.py` past the thousand-line hard
ceiling**, so the dependency and packaging cases moved into
`tests/cmn/mqc_uni_packaging.py`: that module had been declared past the
nine-hundred-line runway since 2026-10-05, and a declaration states the next
subject moves out. The declaration is removed, which is the list shrinking as
the rule requires.

Added: `112348` and `115719`, `MQC_REQ_HAR_CMN_0149` and `MQC_REQ_CAS_CI_0044`,
with `cmn/case_summary.py` and `tools/refresh_case_summaries.py`.

### Documents are named for their repository, and a case says its own name, 2026-10-08

**Two repositories held a `docs/running_jobs.md` and a
`docs/document_register.md` each**, and an editor tab shows a filename rather
than a checkout: a change made in the wrong one parses, lints and commits.

**A tracked document under `docs/` carries its repository's token**, which is
the vocabulary the shipped names already used (`harness_test_plan.md` against
`model_evaluation_test_plan.md`). Eight documents here and two in the case
repository were renamed, 478 references followed, and both registers carry a
renamed-from table so the old paths in the progress records stay resolvable.

**A generic name is a collision waiting to happen**, which decided the scope:
any repository carrying tests has a taxonomy, a pipeline, an extensibility
standard and project phases. Four names already naming a harness tier or module
were left alone and are declared exemptions rather than silences.

**The rename exposed two functions reading one repository's filename under
either repository's root.** `runbook_problems` is called from the case
repository with its own root; after the rename it would have found no runbook
and reported no problem. Both take the path explicitly now, with no default.

**The document subject split out of `cmn/code_standards.py`** into
`cmn/document_standards.py`, which the 900-line runway forced mid-change.

**Every case announces its node identifier before it runs.** The numbered steps
cover a graded case and nothing else, so 709 preconditions announced nothing. A
traceback names the line that raised rather than the case that reached it, and
the two differ whenever a helper is shared.

Added: `112346` and `112347`, `115718`, `MQC_REQ_HAR_CMN_0147` and `0148`,
`MQC_REQ_CAS_CI_0043`, with `cmn/document_naming.py`. Designs: `code-style.md`
sections 7.2 and 7.1, `harness_test_taxonomy.md` section 8.3.1.

### A precondition does not skip, and a band line states all five counts, 2026-10-08

**A harness unit job reported green at 99.44%**: 704 total, 700 executed, 700
passed, 0 failed, 4 skipped. Gate 2 has required "100% pass and zero skips"
since it was written and **nothing enforced the second half**, because pytest
exits 0 when a test skips.

**Any ungraded precondition skip now exits 3.** A precondition measures the
harness, every one is unconditionally blocking, and a skipped one measured
nothing, so there is no acceptable proportion of it.

**A case needing something the environment lacks declares a scope and is
deselected, never skipped.** A skip is an outcome and "this case could not have
run here" is not one. The four cases carrying a conditional skip on a runner
were selected somewhere they could never run; they now leave the total instead:

```
Before:  704 total, 700 executed, 700 passed, 0 failed, 4 skipped   99.44%, green
After:   700 total, 700 executed, 700 passed, 0 failed, 0 skipped   100%,   green
```

**The band line states all five counts, always, including a zero.** Two band
jobs for two engines read `2 failed, 13 passed` and `3 failed, 9 passed, 3
skipped`, so a reader comparing two engines was comparing two shapes and a
difference in the run looked like a difference in the format. The cause
breakdown stays conditional, because an absent cause is a fact and an absent
count is a gap. The band gate and the band line now share both the counts and
the three cause phrases.

**"Our defect" is retired in favour of "an instrument defect."** A test result
establishes which code segment is implicated; which party is responsible comes
from checkin and merge history, which no assertion can see. 48 module
docstrings and every layer table changed, and the progress records keep their
original wording.

**Section 11.6 claimed a registration round trip nobody had run.** The only call
to `register_evaluation_family` in the suite was a refused one, so the admission
criterion was covered and the mechanism it guards was not, and
`unregister_evaluation_family` was called by nothing in either repository.

Added: `112343` through `112345` and `MQC_REQ_HAR_CMN_0144` through `0146`, with
`cmn/environments.py` and the `environment` marker. Designs: `harness_test_taxonomy.md`
sections 7.5.1 and 11.6, `framework-rules.md` sections 1 and 3.1,
`testing-standards.md`, `consumer_ci.md` section 3.12.3.

### A skip is counted by its cause, and the skip ceilings are retired, 2026-10-08

**A case that skipped did not pass, and the pass rate now says so.** A skip
entered neither the pass-rate numerator nor its denominator, so a rate was
stated over whatever happened to run. It now enters the denominator and never
the numerator, which makes it read as the failure it is.

**Whether it counts as a failure is decided by the reason it carries.** A skip
caused by a harness bug, a flaky test or a provider nobody could reach is not
the model's failure, and charging it to the model is the misattribution the four
taxonomy families exist to prevent.

| Reason | In the pass rate |
|---|---|
| `quarantined`, `dependency`, `incomplete`, or unstated | **Counted as a failure** |
| `environmental`, `unsupported` | Excluded |

**`quarantined` is a new skip reason.** A quarantined case skips before dispatch
to save the run's cost, and it had been arriving unattributed. An unattributed
skip is counted, so the answer was right by accident; it is now right by
declaration.

**Quarantine no longer leaves the pass-rate denominator.** It saves the cost of
asking again about a known failure and does not stop it being one. The one thing
that releases a quarantined skip is `release_accepted_in`, the tracker reference
in which product management announced that releasing with the finding is
acceptable, and an unconfirmed entry cannot carry one.

**V3 and V4 are retired.** A 20% total skip ceiling and a 90% pass floor cannot
both hold once a skip counts in the denominator: a run sitting exactly where V3
tolerated it breached V2 automatically. V4 capped the blocking-band skip rate at
10%, and V1 already fails a run on a single blocking-band observation that does
not pass, so a ceiling that can fire only after something stricter has fired
decided nothing. Both rule names stay retired rather than reused, and both
thresholds stay loadable so a stored verdict remains recomputable.

**A skipped case records its own observation, which nothing did before.**
`pytest.skip` raised before anything was recorded, so the accounting specified
since A13 had no skips to count. The three in-case skip sites now record one
each, carrying the reason, and a judgement the replay store did not hold records
`environmental` where it used to record a model **failure**.

**A band line names each kind of skip by the remedy it takes**: behind a higher
band failure, as a known failure in quarantine, or for a reason of ours. A
quarantined skip had been reading as our infrastructure wobbling.

**Replay on both sides is recorded as measuring no model.** Both halves are
recordings, so such a run establishes only that our pipeline still reads its own
fixtures the same way. It is the pull-request gate and a precondition, and a
finding filed against a vendor cites a live candidate.

**Recording a skip exposed one more thing the artifact was doing.** A skipped
report is not a passing one, so the attachment condition read `passed` alone and
began filing a vendor report for every quarantined case the moment a skip
recorded an observation. Nothing is filed about a skip: it holds no response for
a provider to read. The observation is still published, which is what gives the
rate a skip to count.

**The blocking-band floor honours the dispensation it was documented to honour.**
It read the field nowhere. It now loads the entries for the engine, releases a
skipped case the reference names, and names the case and the reference in the
line. A dispensation recorded against another case releases nothing.

Retired with the rules: `112006` through `112009`, `112019` and `112032`, each
listed struck through rather than removed. Added: `112044` through `112050`,
`112341` and `112342` in the harness, `115717` in the case repository, with
`MQC_REQ_HAR_CMN_0142` and `0143` and `MQC_REQ_CAS_CI_0042`. Designs:
`harness_test_taxonomy.md` sections 7.4.1, 7.4.1.0, 7.4.1.2, 7.4.1.3 and 7.4.2;
`cmn_verdict_and_cli.md` sections 4.3, 4.4, 4.6.13, 5.3, 7.11 and 10.24.2;
`consumer_ci.md` sections 3.12.3 and 6.4.1.

### Claude candidate moved to Claude Opus 5.5, 2026-09-23

**The model identifier changed and the adapter did not.** Of the four breaking
changes the newer model introduces, this adapter was exposed to none: it sent no
`thinking` field, forced no tool call, replayed no conversation turn, and
declared no computer-use tool. "One request per case, no loop" was adopted so
tool-call intent stays unexecuted, and it independently removed an entire class
of migration work.

**One behavioural change was designed for rather than absorbed.** The newer
model defaults its effort level one step lower, so the adapter now states the
value (`_DEFAULT_EFFORT`) instead of inheriting it. The setting enters the
request hash, so moving it reports a stale fixture rather than silently
changing how much the model thinks. `tier2_execution.md` section 5A.1 carries
the reasoning; `MQC_EXE_UNI_113011` and `113012` enforce it.

**No recurring cost changes.** A3 Option 1 stands: the judge is Gemini on the
free tier and Claude remains a replay-only candidate, so the lower price
becomes relevant only if a key is provisioned.

### Repository split, 2026-09-23

**This repository became the harness alone.** The evaluation cases moved to
`AP-Model-QC`, which now consumes this one as a pinned dependency. Closes A17;
`DESIGN.md` section 5.1 carries the boundary and the capability table.

This is a **major** change under the versioning policy above, because it changes
what a version means: a commit here is now a version of the harness rather than
of the harness and the cases together. Nothing downstream has consumed a version
yet, so it costs no migration.

- **Moved out**: the graded layers, task data, golden rules, replay fixtures,
  the code excerpts, `model_evaluation_test_plan.md` and `rtm_model.csv`.
- **Removed**: `MQC_CMN_UNI_10171` through `10173`, `11105` and `11106`, with
  `MQC_REQ_HAR_CMN_0027`. They read case-side data, which the split revealed as a
  boundary violation. Re-homed as `MQC_CAS_UNI_115100` through `115104`.
- **Added**: `CAS` as a registered module with its own identifier block, which
  spans repositories because the durable record does.
- **Licensed**: Apache 2.0 with a `NOTICE`, and an SPDX header on every Python
  file, enforced by `MQC_CMN_UNI_112502`.

### Implementation, Phase 3

All four modules implemented, with 357 precondition cases and 107 traced
requirements. Four CI workflows written and linted. The 3-phase workflow in
`.claude/skills/skill-rules.md` was observed throughout: every case was
inventoried in a design document before it was built, which
`MQC_CMN_UNI_112303`, `112305` and `112306` now enforce mechanically.

### Added

- **`CLAUDE.md`** as the directive router, and the rule set beneath `.claude/`
  covering code style, framework architecture, testing standards and worktree
  isolation.

- **`.pylintrc`**, which moves the project's naming rules from prose into
  mechanical enforcement. `variable-rgx`, `argument-rgx`, `attr-rgx` and
  `inlinevar-rgx` enforce the three-character minimum; `function-rgx`,
  `method-rgx`, `class-rgx` and `module-rgx` enforce the `MQC` prefix and
  reject `test_`-prefixed names.

  `inlinevar-rgx` is set deliberately. It governs comprehension targets, which
  pylint's defaults permit to be single letters, so without it `[row for r in
  rows]` scores 10.00/10 while violating the rule it is meant to satisfy.

- **`docs/design/harness_phase0_project_ambiguities.md`** - a register of 13 blocking
  items, 10 deferrable assumptions and 3 governance ambiguities, each with a
  recorded decision. The governance layer specified *how* to build but never
  *what*; this closed that gap before any design commitment.

- **`docs/design/harness_test_taxonomy.md`** - the normative reference for what every
  identifier means: module and layer registries, priority definitions with
  worked examples and distribution ceilings, the outcome model, and four failure
  taxonomy families (`QC_LLM_*`, `QC_HARNESS_*`, `QC_DATA_*`, `QC_SEC_*`).

- **`CLAUDE_LOG.md`** - tracked decision and progress record. Raw prompts are
  deliberately excluded and kept in an untracked prompt log, so this file holds
  outcomes rather than phrasing.

### Changed

- **The test identifier format is `MQC_<MODULE>_<LAYER>_<5DIGIT>_<behavior>`**,
  extended from an earlier three-segment form. Identifiers now read outward-in:
  project identifier, module, test type, instance. The old format is rejected
  by `.pylintrc` rather than tolerated alongside the new one, because two valid
  formats at once is how a naming standard stops being one.

- **Gate 4 no longer exports a bespoke telemetry file.** The prior rule required
  writing a bespoke `reports/mqc_test_insights.json` for a downstream collector
  to consume. Collectors parse standard formats, JUnit XML and Allure output,
  so the rule would have produced a file nothing could read. It also encoded a
  reverse dependency on a consumer, which the architecture exists to avoid.

- **`MQC_UNI_` and `MQC_SYS_` became ungraded preconditions** rather than graded
  layers. Both require 100% pass and block the graded layers on failure, on the
  grounds that a harness failing its own tests produces results that are suspect
  anyway. `MQC_SYS_` runs in replay mode as the precondition: a gate that can
  flake on a rate limit cannot distinguish a broken pipeline from a busy
  provider, and so is not a gate.

### Fixed

- **A silent-skip hole in the lint gate.** The `MQC` naming pattern accepted
  `test_`-prefixed callables through its ordinary snake_case branch. Such a test
  scored 10.00/10 at Gate 1 while `pytest.ini` never collected it, so it linted
  clean, reported nothing and never ran. Closed with negative lookaheads on the
  function, method, module and class patterns. A suite reporting green for a
  test that does not exist is worse than one reporting red.

- **Marker propagation across test layers.** A class-level `@pytest.mark` applies
  to every method in the class, so a class mixing an `MQC_TOOL_` and an
  `MQC_EVAL_` method under one marker caused both to be collected by the wrong
  gate and neither to be gated correctly. One layer and one priority per class
  is now a rule in both the taxonomy and the testing standards.

- **Three rule files that could not be complied with as written.** Both skill
  templates targeted a different repository and demonstrated `test_` prefixes
  and single-character exception bindings, which this project prohibits;
  `testing-standards.md` was truncated mid-code-fence at 13 lines; and
  `worktree-rules.md` carried leftover markdown fences from a paste.

### Notes

- **Zero recurring cost is a deliberate scoping decision, not a budget
  constraint.** Gemini's free tier judges and runs live; OpenAI and Claude are
  exercised from recorded fixtures. The funded multi-provider configuration was
  bypassed for this demonstration project. The architecture is already legible
  in the codebase, making the ongoing monthly cost unjustifiable. The paid path
  is documented in the design as a costed alternative.

- **Every enforcement rule in this release was verified by adversarial probe
  rather than by reading configuration.** Probes confirmed that single-character
  comprehension targets and exception bindings are rejected, that `test_` names
  are rejected, that an unregistered layer token passes, that the old identifier
  format is rejected, and that marker filters select correctly once one layer
  per class is observed. Probe files were removed after verification.
