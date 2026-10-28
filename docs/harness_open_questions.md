<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# Open Questions

Decisions that need a person, and the blockers a person has to clear. Everything
here is either a judgement I should not make alone or an action only the account
owner can take.

**This is not a backlog.** Work that is merely unfinished lives in `DESIGN.md`
section 7.8 as a known gap. What is here is waiting on somebody.

**A settled question leaves.** Once a decision is recorded in the document that
owns it, keeping the question here makes this file a history rather than a list
of what needs a person, and a reader has to read the strikethrough to find out
that nothing is being asked. Section 2A keeps one line per settled question so
the trail survives the deletion.

Last reviewed 2026-10-01, after the band topology shipped.

---

## 1. Standing constraints, which are facts rather than questions

**The account limits**, recorded 2026-10-04 from the account owner, because a
spend ceiling has to be set against something:

| Provider | Total credit | Monthly limit |
|---|---|---|
| Gemini | $60 | **$20** |
| OpenAI | $60 | **$20** |
| Anthropic | $20 | $20 |
| xAI | $20 | $20 |

**The measured cost makes this comfortable rather than tight.** The `SEC` family
recorded for **six cents** and a full graded recording run for one engine is
cents rather than dollars. Every leg that can dispatch carries a `max_spend`
input, wired 2026-10-04, and `--max-spend` fails closed on a model it cannot
price.

**Nothing in this section is blocked.** All four engines are recorded, every
provider is wired, and what used to be sections 1 and 1.2 is listed as settled
in section 2A.

**This document does not say where any credential is held.** A tracked document
should not map the credential surface, and the properties that matter are
asserted by code rather than described here: `cmn/config.py` refuses a
configuration file carrying a credential-shaped key, `MQC_CMN_UNI_112520`
requires every variable a registered adapter reads to be settable in
`.env.example`, and `MQC_CAS_UNI_115710` requires the live workflow to offer one
per rostered engine.

**The one structural fact worth keeping**: a gate names no environment and
references no provider secret, so a pull request from a fork has no path to a
credential at all.

---

## 2. Decisions I have deferred rather than made

### 2.5 Should a claude-judged rung 3 run at all?

Opened 2026-10-21. A second judge was added so that gemini does not score its
own engine unchecked, and **the comparison only works at rung 2**: the
responses are a recording, so a difference between two judges is the judge.
Rung 3 draws its candidates live, so a claude-judged rung 3 and a gemini-judged
one score different responses and nothing in the result separates a judge
difference from a response difference.

The project owner named rung 1 as the one rung not to repeat for a second
judge, so rung 3 runs as instructed and this is the question rather than a
change. **What keeps it genuinely open:** a finding filed against a vendor must
cite a live candidate, so a finding only claude's judging produces cannot be
filed from rung 2 alone. Recorded in `consumer_ci.md` section 7.7.2 with the
table.

**Previously, and still true of the rest:** section 2A says where every settled
answer now lives, and a closed question is removed from here rather than left
to be argued again.

**An empty section is the honest state and is kept rather than deleted.**
Deleting it would say this project never defers a decision, which is false and
is the opposite of what this document is for: the next open question gets a
number here, continuing the sequence rather than restarting it.

**The numbering has gaps, and they are retired rather than reused.**
Ten questions were settled and removed; section 2A lists them. A number
that moved would break the documents citing it, and this project retires
identifiers for the same reason it retires test ids: a reader returning to
a reference should find what it named or find nothing, never something
else. That is also why `2.4.1` has no `2.4` above it.

### 2.6 Does a differing remedy require a code of its own?

Opened 2026-10-21. `QC_HARNESS_FIXTURE_MISSING` covers an absent candidate and
an absent judgement, and `harness_test_taxonomy.md` section 6 records that as a
decision: **one code, and the skip message names which, "because the remedy
differs: re-record the model, or re-record the judge."** The same row is the
argument against itself. Elsewhere this project has twice split a code on
exactly that ground, `QC_HARNESS_AUDIT_REFUSED` out of
`QC_HARNESS_PARSER_ERROR` and the five codes registered on 2026-10-21, and the
reason given each time was that a code exists so a tally by root-cause class
can count it. A message cannot be counted.

**What it cost while nobody decided:** the gloss asserted the candidate, so a
missing judgement read as a missing response and sent me to re-record a model;
four tool calls chasing a file that was on disk the whole time, 2026-10-13. The
gloss is fixed and the question is not: whether `QC_HARNESS_JUDGEMENT_MISSING`
and `QC_HARNESS_JUDGEMENT_STALE` should exist, and whether
`QC_HARNESS_FIXTURE_STALE` should further split by hash against judge model.

**Not decided unilaterally**, because the existing arrangement is a recorded
decision rather than an omission, and overturning one costs every stored row
that carries the old code.

## 2A. Settled, and where the reasoning now lives

Removed from section 2 once the decision was recorded. The question is here so a
reader who remembers asking can find the answer; the answer is not restated,
because a second copy drifts.

| Question | Settled | Recorded in |
|---|---|---|
| Where does the next governance case get its number? | Settled 2026-10-22, in a declared partition at `400000` | `harness_test_taxonomy.md` section 3.2.1.5. The owner's ruling: existing ranges stay, the unallotted ones open, and a newer partition can be 10,000 wide. `200000` and `300000` stay reserved for the two recorded domains |
| `CMN`/`UNI` category 4 holds three subjects against a table naming one. Partition, or a corrected table? | Settled 2026-10-23, a declared partition at `410000` | `harness_test_taxonomy.md` section 3.2.1.5, which now records the direction as well as the range. The owner's ruling: "use declared partition. at the end of the day we will need to use declared partitions. 100 test cases per partition is just not enough." So a partition is what a new subject takes, and the sixteen mutation cases already in `1123xx` and `1124xx` stay where they were assigned |
| Where should a judge panel's divergence be published? | Withdrawn 2026-09-26, a panel is out of scope | `tier3_evaluation.md` |
| Should invalid-coupon abuse be logged, and is that assertable? | 2026-09-26, assertable by asking directly | The `code_comprehension` corpus |
| Should the `screen_evasion` exemption be capped? | 2026-09-26, at 15% of payloads | `tier1_ingestion.md` section 7.3.4 |
| Recording takes ten days on the free tier. Pay, or wait? | 2026-09-28, paid | `CLAUDE_LOG.md`, and the measured cost |
| Should there be a mode that records only what is missing? | 2026-09-29, it already half existed | `tier2_execution.md` section 7.10.3 |
| Should an inventory row without an implementation be reported? | 2026-10-01, reported and never gated | `cmn_verdict_and_cli.md` section 10.19.1 |
| Is `inconsistency_ceiling` at 0.10 right? | 2026-10-01, 0.20, with three observations escalating to five on a single disagreement | `cmn_verdict_and_cli.md` section 4.9.2.1 |
| Should multi-prompt consistency be built? | 2026-10-01, out of scope and a harness expansion | `cmn_verdict_and_cli.md` section 4.9.5 |
| Should a security case declare the vector it is about? | 2026-10-01, all of them, with a primary | `model_evaluation_test_plan.md` section 9.10.3.1 |
| What should the harness's own live run measure? | 2026-10-01, the same ladder, fired weekly or on a version change | `harness_ci_pipeline.md` section 2.0.2 |
| Which engines are recorded, and what clears the rest? | 2026-10-04 and 2026-10-05, all four | `config/findings/`, and `CLAUDE_LOG.md` for each recording |
| Where do the credentials live, and which secret is where? | 2026-10-05, **deliberately not recorded in a tracked document** | Nowhere. The properties are asserted by code, per section 1 |
| Is `--max-spend` wired into anything? | 2026-10-04, into every leg that can dispatch | `harness_ci_pipeline.md`, and the `max_spend` input on each |
| What is the known-good state to compare against? | 2026-10-05, the README figures, which are recomputed and checked | `README.md`, by `MQC_CMN_UNI_112323` |
| What is the activity that measures a dependent of a failed foundation called? | 2026-10-11, an inquest, and `unattributed` is what it returns | `cmn_verdict_and_cli.md` section 10.28.2.4 |
| Should a fixture store the request or only its hash? | 2026-10-11, store it; re-record rather than derive | `tier2_execution.md` sections 7.13 and 7.13.2 |
| Is a `curl` the right reproduction for a recorded call? | 2026-10-12, no: the recording holds SDK arguments, and one provider's stored field has no wire form | `consumer_ci.md` section 9.5.3.1 |
| Is a provider refusing a benign request our failure or the model's? | 2026-10-12, the model's, when the run answered other requests | `tier2_execution.md` section 8.6.7 |
| Does a README change require a changelog entry? | 2026-10-12, yes, in the same change | `code-style.md` section 7.4 |
| Should a threshold outside its domain be clamped, defaulted or refused? | 2026-10-13, refused at construction, because a run reporting a result against a substituted standard is the worse failure | `cmn_verdict_and_cli.md` section 8.1 |
| Is zero an acceptable ceiling? | 2026-10-13, no: it leaves no band, and the rule it reaches for is V1 | `cmn_verdict_and_cli.md` section 8.1 |
| Delete `environment_marker`, or make its claim true? | 2026-10-13, keep it and compare: strict markers for an applied marker, a case for the registry the consumer copies | `harness_test_taxonomy.md` section 7.5.1 |

---

## 2B. Known gaps, which are work rather than questions

Recorded so the absence is on the record. None needs a decision.

| Gap | Where it bites |
|---|---|
| Two equivalent mutants in `cmn/verdict.py` are findings about the code | One branch is unreachable given its predecessors and one adds a rule to a breach list nobody reads. Declared with expiries rather than fixed |
| `QC_HARNESS_FIXTURE_STALE` says a hash moved and a judge model moved under one code | `execution/replay.py` raises both, and its own docstring says they are "reported separately **because** the operator response differs": re-record against the new request, against recalibrating a judge. **Only the message differs**, so no tally by root-cause class can separate them. Found 2026-10-21 beside the gloss defect below, and left as the narrower half of question 2.6 |
| The cadence suffix in a workflow filename decides whether a run counts, and nothing enforces the set | `harness_ci_pipeline.md` section 2.1 lists `on-change`, `nightly`, `weekly` and `on-demand`; `on-branch`, `on-merge` and `on-dispatch` are also in use, `gate-<engine>.yml` and the two reusable workflows carry none, and `regress-harness-on-branch.yml` names a scope where the rule asks for a trigger. **`on-demand` reads as `ci_debug` and yields no verdict** (`cmn_verdict_and_cli.md` section 7.1.4), so `on-demand` and `on-dispatch` differ by one word and by whether the run is counted |
| A re-record needing fewer observations than the previous run leaves the surplus behind | Pruned by hand three times on 2026-10-12. Nothing prunes at the point of recording |
| Nothing checks that an assertion matches a figure the fixture declares rather than a verdict's vocabulary | `DESIGN.md` section 7.8. Three assertions in `premise_discrimination` shipped as synonym lists and produced a false positive on the first recorded run. The rule is written and **review is the only thing enforcing it**: a pattern carrying no digit is not reliably wrong, so the obvious check would refuse legitimate assertions |
| A heading's rank disagrees with the depth of its number in 69 places | A heading's parent by rank is the nearest heading above it with fewer hashes, and its parent by number is the longest prefix of its number the document also numbers. Where they disagree a section renders under its neighbour: a fourth-level 9.12 under a third-level 9.11, now corrected. **Reordering took the twelve documents from 152 to 69**, because a section in the wrong place usually had the wrong parent by rank as well, and the 69 that remain are hash counts rather than positions. Changing them is a decision about rendering, so it is recorded rather than swept (`code-style.md` section 7.5.2) |
| Nothing checks that a module, path or callable a document names is one that exists | A survey on 2026-10-22 read every backticked `module.callable` and every backticked path in both repositories' documents and found **eight the tree does not hold, of which one was a defect**: a design cited `cmn.code_standards.file_date_problems` after the function moved to `cmn.file_dates`, so a reader was sent to the wrong module. **The other seven are deliberate**, naming a file that was renamed, split, deleted or refused, and a check admitting them reports seven false positives for one real one. Section 7.3's lesson applies: a pattern burying its signal trains a reader to ignore it. **The missing half is the one the citation checker has**, a way to mark a reference as historical |
| A composite graded case depends on its control and not on its single-axis siblings | Every hidden-passage case declares `depends_on` the control `154500` alone, so a four-axis case reports a finding although the one-axis case beneath it already failed, and the composite result is attributed to interaction when the cause is the component. That is the duplicate-reporting `harness_test_taxonomy.md` section 4.1.3 exists to prevent, unwired for this family. Found 2026-10-28 while pricing the measurement ceiling, where the project owner's axis-count proposal named the composite problem correctly and attached it to priority rather than to the dependency relation (section 4.1.2.2). **Wiring it changes which cases run**, so it is a rerun decision rather than an edit |
| `evaluate-live-weekly.yml` runs no case, and the probe dispatches it | It runs the graded markers in this repository, which owns no graded case, and `probe-model-version-nightly.yml` dispatches it on a version change rather than the case repository's run against the green harness. `harness_ci_pipeline.md` section 2.0.1 records the first half. Both are retired at the probe move, which is the next step of the probe and calibration plan. **Its three single-layer steps became one on 2026-10-21**, which was a separate defect: each recorded a full selection while measuring a third of the graded layers |

## 2C. Gaps since closed, and where the closure is recorded

A closed gap moves here rather than being deleted, for the reason section 2A
gives for a closed question: a reader who remembers it should find where the
answer is, and the answer is not restated.

| Gap | Closed | Recorded in |
|---|---|---|
| The mutation audit covered two modules of six | 2026-10-21, all six audited | `config/mutation_survivors.yaml`, `MQC_CMN_MUT_162000` to `162005`, and the parallel audit in `harness_test_taxonomy.md` section 15.15 |
| A ceiling meant `>` in one place and `>=` in another with nothing saying so | 2026-10-13, both tabulated | `cmn_verdict_and_cli.md` section 8.2. It was a documentation gap and the table closed it |
| The skip gloss for a missing or stale fixture asserted the candidate, so a missing **judgement** read as a missing response | 2026-10-21 | `cmn/band_summary.py`, and `cmn_verdict_and_cli.md` section 7.11's table. The code's own registry row always said the message names which; the gloss did not. **Whether the two deserve separate codes is question 2.6**, which is a decision rather than this gap |
| Section headings sat out of numeric order, in twelve documents rather than the four this row named | 2026-10-22, the check and the reordering together | `cmn.document_citations.disordered_sections`, `MQC_CMN_UNI_112399`, `MQC_CAS_UNI_115778`, and `code-style.md` section 7.5. **Thirty seven headings, not the thirty one a hand count found**, and the documents the row named were six of twelve. Fifty nine moves in this repository and sixteen in the case repository, each proved to carry its section whole |
| The Allure grouping tree was mandatory, had no design, and carried 13 classes of 239 | 2026-10-24, the design, the vocabulary and the derivation together | `harness_test_taxonomy.md` section 16, `config/allure_features.yaml`, `cmn/grouping.py`, `MQC_CMN_UNI_420000` to `420005`, and `testing-standards.md` sections 4 and 5. **It was a decision and not the sweep this row first called it**: the vocabulary section 4 named was used by neither repository, so the rule was the thing that was wrong. The labels are derived in the collection hook that already derives severity, which is the one label that was never missing. The report is published as well, which `harness_ci_pipeline.md` section 7.4 carries |
| A case belonging in the audit's deselect list left the audit silently | 2026-10-24, reported rather than policed | `tools.mutation_audit.quarantine_report`, `MQC_CMN_UNI_410005`, and `harness_test_taxonomy.md` section 15.7.1.2. **The project owner's ruling**: the audit is an internal tool, it will fire on harness cases and probably never reach a model run, and all that can be done is to report what was set aside at the end of the run. Deciding membership mechanically means running the targets against an unparsed module, which **is** the control run, so the check would answer a question the control answers one step later. The list was also re-measured the same day and is five and complete |

## 3. Things I changed that deserve a second opinion

Each of these is implemented, tested and reversible. I believe each is right and
none is the kind of call I would want made only once.

| Change | Why it might warrant review |
|---|---|
| `screen_evasion` exemption (`tier1_ingestion.md` 7.3.4) | It relaxes a security check. The exemption is policed in both directions, but it is still a relaxation |
| Vector patterns widened, two vectors added (7.3.1, 7.3.2) | A screen that fires wrongly is worse than one that misses. Verified against 42 ordinary tasks and 8 ordinary phrases, and that is a sample, not a proof |
| `spacing_sec` reverted to 4.0 | Widening it to 6.0 produced zero additional observations, so the value is **unvalidated rather than validated**: the plan quota is reached first and masks any per-minute ceiling |
| `gemini-3.8-flash` pinned (A3.1) | Chosen because the provider's 404 named it. A different model is a different instrument and every recorded score is against this one |
| `score_spread` recorded but not gated (4.9.4) | Information nothing consumes is information nothing protects. It is in the verdict and no rule reads it. **The corpus it was waiting for now exists**, so the condition for revisiting this has been met |

---

## 4. Known-good state, for comparison after any change

**Removed 2026-10-05. It was a second copy of figures that are checked
elsewhere, and it had drifted on every one of them**: 687 passing against 711,
83 preconditions against 91, 24 findings against 23, and "9 observations,
security family only" against 815 across four engines.

**The README carries these and `MQC_CMN_UNI_112323` checks them**, recomputing
each from the designs, the matrix and the corpus rather than restating it. A
hand-kept snapshot in a second document is the defect this project has
corrected four times; keeping one here while a checked copy exists was the same
mistake in the document that catalogues mistakes.

| Where to look | For |
|---|---|
| `README.md` | Case counts, requirement counts, corpora, recordings, findings |
| `config/findings/` | Every open finding, per engine, with its reproduction |
| `CLAUDE_LOG.md` | What changed when, and what it cost |

## The one warning every run carries, and the version it becomes an error

**Added 2026-10-05**, after the project owner asked whether we should stop using
`_UnionGenericAlias` before Python does.

**We never used it.** It is inside `google/genai/types.py` line 42, and it
appears nowhere in either repository:

```
DeprecationWarning: '_UnionGenericAlias' is deprecated and slated for
removal in Python 3.17
```

**Upgrading does not help, which was checked rather than assumed.** The
installed version was 2.25.0 and the latest is 2.28.0; the warning is present in
both. The declared pin is `google-genai>=2.25,<3.0`, so **CI has been installing
2.28.0 all along** and the local environment was the thing that was behind. The
generated `requirements.txt` carries the range rather than an exact version, so
no requirement changed when the local install caught up.

### Why it is recorded rather than silenced

| | |
|---|---|
| Can we fix it | **No.** It is a third party's use of a private typing alias |
| Can we silence it | Yes, with a `filterwarnings` entry |
| Should we | **No.** It stops being a warning at Python 3.17 and starts being an import error |

**A silenced warning is a removed reminder.** This project targets 3.14 and the
alias is removed in 3.17, so the warning is the only thing currently announcing
a future hard break in a dependency we cannot patch.

### The trigger

**Whichever comes first:** `google-genai` releases a version without it, which
is checked by the warning disappearing, or Python 3.17 approaches and the
dependency has not moved. The second case is a dependency decision rather than a
code change: the provider's own SDK would no longer import on a supported
interpreter.

**It is one warning, not noise.** Every suite run reports exactly one, which is
why it is legible: a second would be worth the same treatment, and a filter
entry now would hide both.
