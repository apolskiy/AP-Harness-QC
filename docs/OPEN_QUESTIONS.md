<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# Open Questions

Decisions that need a person, and the blockers a person has to clear. Everything
here is either a judgement I should not make alone or an action only the account
owner can take.

**This is not a backlog.** Work that is merely unfinished lives in `DESIGN.md`
section 7.4 as a known gap. What is here is waiting on somebody.

**A settled question leaves.** Once a decision is recorded in the document that
owns it, keeping the question here makes this file a history rather than a list
of what needs a person, and a reader has to read the strikethrough to find out
that nothing is being asked. Section 2A keeps one line per settled question so
the trail survives the deletion.

Last reviewed 2026-10-01, after the band topology shipped.

---

## 1. Blocked on an account action, not on code

Recording is no longer the blocker it was. The corpus is recorded in full
against one engine and the comparison the project exists to make needs more
than one.

| Engine | State | What clears it |
|---|---|---|
| `gemini` | **Recorded in full.** 195 candidate responses, 108 judgements, 2 findings | Nothing |
| `openai` | **Funded and being recorded** against `gpt-4.1` | Nothing |
| `claude` | Key needed, **and a price entry** | `ANTHROPIC_API_KEY`, plus a `claude-opus-5-5` row in `config/pricing.yaml`: the model is deliberately unpriced, the spend ceiling fails closed on an unpriced model, and a run carrying `--max-spend` therefore refuses |
| `grok` | No credential | A key, then `XAI_API_KEY` |

**The unpriced-model refusal is the design working, not an obstacle.** A ceiling
that cannot see a price cannot enforce itself, and the alternative reading, that
an unpriced model costs nothing, is the one failure a spend ceiling exists to
prevent (`tier2_execution.md` section 8.6.4).

**The OpenAI key is already wired correctly.** It authenticates against 126
models and `gpt-4.1` is present; the account balance is zero. A ChatGPT
subscription funds nothing on the API, which is the part that catches people.

**A second engine is worth more than unblocking the first**, and it is about
candidates rather than judges. A3 wanted several candidate families so that
self-preference becomes visible: with one judge and several candidates, the
judge's treatment of output from its own provider can be compared against its
treatment of the others, which is a finding about the **candidates** and stays
in scope where a judge panel does not (A3.2).

Adding an engine on the Chat Completions protocol is four values
(`tier2_execution.md` section 3.5), so Groq, Mistral, DeepSeek or Together are
each about ten minutes' work once a key exists.

**What recording now costs.** A4.1 raised the corpus to three observations per
case, so the full set is 198 candidate responses plus 111 judgements. Nine of
the 198 exist, all at observation zero.

---

## 2. Decisions I have deferred rather than made

**The numbering has gaps, and they are retired rather than reused.**
Five questions were settled and removed; section 2A lists them. A number
that moved would break the documents citing it, and this project retires
identifiers for the same reason it retires test ids: a reader returning to
a reference should find what it named or find nothing, never something
else. That is also why `2.4.1` has no `2.4` above it.

### 2.1 Should an inventory row without an implementation be reported?

**Found by:** twelve designed security cases, nine of them P0, existing as
design and nothing else for as long as they did.

`MQC_CMN_UNI_10183` checks that every collected case has an inventory row.
**Nothing checks the reverse.** The instance is closed; the class is not.

**Why I have not simply added it.** An inventory row without an implementation
is the *normal* state while a family is being built, because this project
requires the design to come first. A hard gate would forbid the authoring order
it mandates.

**My recommendation:** report, never gate. A count in the artifact, or a case
that reports the list without failing. That keeps the omission a decision on the
record, which is what `testing-standards.md` asks of any gap.

### 2.2 Is `inconsistency_ceiling` at 0.10 right?

**Introduced by:** A4.1, which made three observations per case mandatory and
inconsistency a soundness failure (`cmn_verdict_and_cli.md` section 4.9).

The number was matched to `priority_skip_ceiling` rather than derived, on the
grounds that both answer how much of a thing a run can carry before its
conclusions stop holding.

**Nothing has measured it**, because no corpus has ever been recorded at three
observations. The first live run is the evidence, and it may well say that any
inconsistency at all should unsound a run, or that 0.10 is far too strict.

**What the ceiling does and does not cover, clarified 2026-09-26.** It counts
cases whose **verdicts** disagree, which needs no judge because every
observation is measured against the same fixed rules rather than against the
other responses. Differently worded responses that all satisfy the rules are
consistent by construction (section 4.9.3).

A **score** moving inside the passing band is a separate thing: three
observations scoring 4, 4 and 5 against a threshold of 4 all pass, so the
ceiling never sees it. `score_spread` records that per case and **gates
nothing** (section 4.9.4). Whether a spread should ever have a ceiling of its
own is a second question, and it needs the same evidence this one does.

### 2.2.1 Multi-prompt consistency, recorded and not built

Raised 2026-09-26. Repeating a **conversation** rather than a prompt would
measure something real, and the cost is not the repetition: it needs
conversation state seeded and compared, a rubric that judges a turn in the light
of the turns before it, and recalibration, because exemplars are single
responses and the known-correct anchor does not transfer.

**So it is an expansion and not a setting**, and section 4.9.5 records it.
Section 9.6.1 of the test plan states the present boundary where it is most
likely to be misread: the clarification family measures that the model asks, and
nothing measures what follows.

### 2.4.1 Should a security case declare the vector it is about?

Raised 2026-09-26 while fixing the vector ordering, and it is the stronger half
of that finding.

Three payloads carry a vector their case is not about: `50002` is about a context
insertion and its role assertion is incidental prose, `50004` combines three
things, and `50008` carries override language it does not need.

**That incidental match is how two whole families looked screened.**
`task_substitution` and `tool_coercion` had no vector at all, and `50004` and
`50008` passed the cross-check on override phrasing they did not need (section
7.3.1).

**A case declaring the vector it is about, with the corpus asserting that vector
matches, would have caught it at authoring time**: `50004` would have declared
`task_substitution`, no such vector would have existed, and the check would have
failed the day it was written.

**What it costs.** Every security rule gains a field, and the three payloads
above would each have to either declare their incidental vector or be cleaned of
it. Cleaning changes what a model has been asked, which is a corpus change rather
than a check change, and I would not make it without a decision.

### 2.7 What should the harness's own live run measure, once it is scheduled again?

Raised 2026-09-26, while removing the CI gates that could not run.

`evaluate-live-weekly.yml` in **this** repository runs `pytest -m evaluator`,
`-m tool` and `-m sec` live, then computes a verdict. **All three collect nothing
and the verdict reads a file nothing writes** (`ci_pipeline.md` section 3.1.0).
It fires on a schedule, so unlike the other two it fails every Sunday rather than
only when dispatched.

**`AP-Model-QC` already has its own `evaluate-live-weekly.yml`**, which resolves
the paired harness and runs the real ladder. So this one is a duplicate of a
workflow that works, in a repository with nothing for it to run.

| Option | Cost | What it buys |
|---|---|---|
| **Delete it here** | Nothing | The consumer's ladder is the live ladder, and the weekly red stops |
| Convert it to a live smoke of dispatch | **Provider quota, weekly** | Proof the harness can still reach a provider, which replay cannot establish |
| Leave it | A red every Sunday | Nothing |

**The second option is the only one with real content**, and it is a new thing
rather than a repair. `testing-standards.md` section 1 does refer to "a live SYS
smoke on the schedule", which does not exist; a smoke would need a synthetic
corpus dispatched live against one engine, and on the free tier it would spend
from the same 20 requests per day the recording runs need (section 2.6).

**Settled in part, 2026-09-26.** The project owner's decision: no scheduled
workflows at all until `main` is stable, and weekly regression is set up then. So
**the cron is withdrawn from all three scheduled workflows** in this repository
and from the consumer's live ladder, which makes this workflow dispatch-only and
stops the weekly red. `ci_pipeline.md` section 2.0.1 carries the reasoning.

**What is still open is only the content.** The graded steps in this file still
collect nothing, so a dispatch of it fails. Nothing fires it, so nothing is red,
but it is a trap for whoever dispatches it first.

**My recommendation, for when weekly regression is set up:** replace its graded
steps with a live smoke of dispatch against one engine on a synthetic corpus, which
is the harness-only thing a live run can establish and the thing
`testing-standards.md` section 1 already refers to as existing. Until then it is
recorded here rather than deleted, because the file is the obvious home for that
smoke and deleting it would lose the reference the probe workflow makes to it by
name.


## 2A. Settled, and where the reasoning now lives

Removed from section 2 once the decision was recorded. The question is here so a
reader who remembers asking can find the answer; the answer is not restated,
because a second copy drifts.

| Question | Settled | Recorded in |
|---|---|---|
| Where should a judge panel's divergence be published? | Withdrawn 2026-09-26, a panel is out of scope | `tier3_evaluation.md` |
| Should invalid-coupon abuse be logged, and is that assertable? | 2026-09-26, assertable by asking directly | The `code_comprehension` corpus |
| Should the `screen_evasion` exemption be capped? | 2026-09-26, at 15% of payloads | `tier1_ingestion.md` section 7.3.4 |
| Recording takes ten days on the free tier. Pay, or wait? | 2026-09-28, paid | `CLAUDE_LOG.md`, and the measured cost |
| Should there be a mode that records only what is missing? | 2026-09-29, it already half existed | `tier2_execution.md` section 7.10.3 |

---

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

| | |
|---|---|
| Harness | 616 unit, 23 system, pylint 10.00/10 |
| Cases | 58 unit, 69 graded, pylint 10.00/10 |
| Graded result | 2 findings about `gemini-3.8-flash`, one P1 and one P2, reproducing on both platforms |
| Consumer gate | 11 jobs: resolve, lint, preconditions and three priority bands, each per platform |
| Graded inventory | 69 inventoried, 69 collected |
| Recorded | 9 observations, all at index 0, security family only |
| Documentation audit | Clean on duplicate sections, dangling references, unregistered codes |
