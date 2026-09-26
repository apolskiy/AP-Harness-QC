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

Last reviewed 2026-09-26, after the panel withdrawal.

---

## 1. Blocked on credentials, not on code

Recording is the only thing standing between the corpus and a first real
measurement, and both engines are stopped for different environmental reasons
(`tier2_execution.md` section 8.6).

| Engine | State | What clears it |
|---|---|---|
| `gemini` | Daily plan quota spent | Waiting for the reset, or a paid tier |
| `openai` | **Authenticates, no credit** | Adding credit at `platform.openai.com/settings/organization/billing` |
| `claude`, `grok` | No credential | A key, then `ANTHROPIC_API_KEY` or `XAI_API_KEY` |

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

### 2.3 ~~Where should a judge panel's divergence be published?~~

**Answered and withdrawn 2026-09-26.** A judge panel is out of scope: divergence
between judges is a finding about judges, and acting on it needs a judge over the
judges (A3.2). The feature is removed rather than deferred, and calibration
against authored exemplars is what checks the judge.

### 2.4 ~~Should invalid-coupon abuse be logged, and is that assertable?~~

**Answered 2026-09-26: assertable, by asking directly.** The difficulty was that
"list every defect" leaves a mention of abuse to chance, so a regex over the
response measures luck as much as understanding. **A separate prompt against the
same excerpt, asking explicitly about the negative business impact of the
implementation, makes it a direct question** — and a direct question has a
checkable answer.

**Not yet built, and deliberately so.** Section 7.3.6 of
`tier1_ingestion.md` records the ordering rule this runs into: a case combining
concerns is only interpretable once each is measured alone. The single concerns
here are the cause (`30038`) and the remedy (`30039`), both new and both
unrecorded against any model. **A business-impact case belongs after them, not
beside them.**

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

### 2.5 ~~Should the `screen_evasion` exemption be capped?~~

`MQC_CAS_UNI_10446` permits a payload to declare that it evades the vector
screen, and polices the declaration in both directions. **What it does not do is
make the exemption scarce.**

| | |
|---|---|
| Declared payloads | 20 |
| Matching a vector | 18 |
| Tagged exempt | **2** |
| The floor of 6 would permit | **14** |

**The residual risk is a lazy tag, not a stale one.** Rule 2 stops the tag
outliving its truth; nothing stops somebody reaching for it instead of asking
whether the *pattern* is wrong. That is how the two genuine gaps found on
2026-09-26 came to exist: `50004` and `50008` looked covered for as long as they
did because they matched incidentally.

**Settled 2026-09-26: capped at 15% of payloads**, a share rather than a number
so it scales with the corpus. A fourth exemption is not forbidden; the design has
to change to permit it, which is the point. `tier1_ingestion.md` section 7.3.5
carries the reasoning and `MQC_CAS_UNI_10446` enforces it.

**A note on wording.** An earlier version of this said a fourth exemption
"forces a conversation", meaning one among the people writing cases. Read against
a project whose subject is model dialogue that is ambiguous, and it should not
be: nothing here evaluates a conversation, and section 9.6.1 of the test plan
now says so where the clarification family is specified.

---

### 2.6 Recording the corpus takes about ten days on the free tier. Pay, or wait?

**Measured 2026-09-26, not estimated.** Asked directly, Gemini named the quota
that stalled the security recording run at nineteen fixtures:

```
quotaId    : GenerateRequestsPerDayPerProjectPerModel-FreeTier
quotaValue : 20
```

**Twenty requests per day, per model.** A4.1 asks for three observations per
case, so:

| | Requests | Days at 20/day |
|---|---|---|
| Security, 21 cases | 63 | 4 |
| Every family currently authored | ~200 | 10 |

**Nothing is broken and no code change helps.** The earlier `spacing_sec`
experiment (4.0s to 6.0s) failed for exactly this reason: pacing is a remedy at
the run level for a limit at the environmental level. `--fill-gaps` already makes
the run resumable, so waiting works; it just takes the days above.

**The options, and what each costs:**

| | Cost | Effect |
|---|---|---|
| Wait | Nothing but time | ~10 days of daily runs to a full corpus |
| Pay for the Gemini API | Per token | The cap goes away |
| Switch model to win a fresh allowance | Nothing | **Invalidates the corpus** — see below |

**The third is not an option and is now blocked in code.** The quota is keyed
per model, so switching model does grant another twenty requests, and the fixture
store is keyed by engine rather than by model, so both versions would land in one
corpus. `mixed_model_engines` now exits 3 on that (`cmn_verdict_and_cli.md`
section 4.9.6). I mention it because it is the cheapest-looking way out and the
one that silently destroys the result.

**My recommendation:** wait, and record security first. It is the family that
needs no judge, so it is the one that makes progress on candidate quota alone.
Paying becomes worth it when the evaluator family starts, because that spends
quota on the judge as well as the candidate.


## 3. Things I changed that deserve a second opinion

Each of these is implemented, tested and reversible. I believe each is right and
none is the kind of call I would want made only once.

| Change | Why it might warrant review |
|---|---|
| `screen_evasion` exemption (`tier1_ingestion.md` 7.3.4) | It relaxes a security check. The exemption is policed in both directions, but it is still a relaxation |
| Vector patterns widened, two vectors added (7.3.1, 7.3.2) | A screen that fires wrongly is worse than one that misses. Verified against 42 ordinary tasks and 8 ordinary phrases, and that is a sample, not a proof |
| `spacing_sec` reverted to 4.0 | Widening it to 6.0 produced zero additional observations, so the value is **unvalidated rather than validated**: the plan quota is reached first and masks any per-minute ceiling |
| `gemini-3.8-flash` pinned (A3.1) | Chosen because the provider's 404 named it. A different model is a different instrument and every recorded score is against this one |
| `score_spread` recorded but not gated (4.9.4) | Information nothing consumes is information nothing protects. It is in the verdict and no rule reads it, which is deliberate and worth revisiting once a corpus exists |

---

## 4. Known-good state, for comparison after any change

| | |
|---|---|
| Harness | 574 unit, 20 system, pylint 10.00/10 |
| Cases | 47 unit, 69 graded, pylint 10.00/10 |
| Graded inventory | 69 inventoried, 69 collected |
| Recorded | 9 observations, all at index 0, security family only |
| Documentation audit | Clean on duplicate sections, dangling references, unregistered codes |
