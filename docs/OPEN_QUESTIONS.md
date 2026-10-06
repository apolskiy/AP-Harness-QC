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

## 1. Blocked on an account action, not on code

Recording is no longer the blocker it was. The corpus is recorded in full
against one engine and the comparison the project exists to make needs more
than one.

**Updated 2026-10-04.** Three of the four rows below had gone stale: every key
now exists, `claude-opus-5-5` is priced, and the comparison the project exists
to make is recorded against three engines.

| Engine | State | What clears it |
|---|---|---|
| `gemini` | **Recorded and reported.** 2 findings in `config/findings/gemini.yaml` | Nothing |
| `openai` | **Recorded and reported** against `gpt-4.1-2025-04-14`. 8 findings | Nothing |
| `claude` | **Recorded and reported** against `claude-opus-5-5`, which is now priced. 10 findings | Nothing |
| `grok` | **Recorded and reported** against `grok-4.7`, 2026-10-04. 4 findings | Nothing |

**All four engines are now recorded**, which is what A3 wanted: several
candidate families against one judge, so that the judge's treatment of output
from its own provider is comparable with its treatment of the others.

**The grok recording took 25 minutes live and replays in 2 seconds.** 64 task
directories and 102 judgements written; 4 findings, the fewest of the four. The
run cost well under the $2.00 ceiling it carried.

**The model it defaulted to does not exist.** A models call with the funded key
returns 14 models and `grok-4` is not among them, so the adapter default was a
404 nobody had reached. `grok-4.7` is pinned instead, chosen by the account
owner as the latest. This is the second time a pinned model was settled by
asking the provider rather than by reading a document, the first being
`gemini-3.8-flash` under A3.1.

**Recording it costs about what the others did.** At $2.00 and $6.00 per million
against a measured six cents for the `SEC` family, a full recording run for grok
is cents, and the $2.00 per-run ceiling now wired into every spending leg bounds
it.

### 1.1 What the account caps are, and what the project does about them

Recorded 2026-10-04 from the account owner.

| Provider | Total credit | Monthly limit |
|---|---|---|
| Gemini | $60 | **$20** |
| OpenAI | $60 | **$20** |
| Anthropic | $20 | $20 |
| xAI | $20 | $20 |

**The measured cost makes this comfortable rather than tight.** The `SEC` family
recorded on 2026-09-28 for **six cents**, so a full graded recording run for one
engine is cents rather than dollars, against a monthly limit of $20.

**What is not yet true is that anything enforces it.** `--max-spend` is
implemented, covered by `MQC_CAS_UNI_115208` and `MQC_CAS_UNI_115409`, and
**no workflow passes it**, so a live run currently has no ceiling at all. That
is the next thing to close and it is tracked below rather than left to this
paragraph.

| | |
|---|---|
| Implemented | `--max-spend`, which aborts before a request would take total spend past a figure, and fails closed on an unpriced model |
| Not wired | No workflow passes it. The flag reaches the dispatch session and nothing sets a value |
| Why it matters now | Before 2026-10-04 no key was in Actions, so a CI run could not spend. Now three are |

### 1.2 Where the credentials live

| | |
|---|---|
| Locally | `.env` at each repository root, gitignored and untracked, holding all four keys |
| In Actions | A GitHub **Environment** named `live` in each repository, created 2026-10-04 |
| Protection | **A required reviewer**, the account owner, on every run that names the environment |
| Branch policy | None. A `workflow_dispatch` cannot be fired from a fork or by a pull request, and the approval covers the rest |
| What the gates hold | **Nothing.** `gate-target.yml` names no environment and references no provider secret, so a fork pull request has no path to a key |

**Only what a workflow references is set.** The harness `live` environment holds
`GEMINI_API_KEY` alone, because that is the only secret any harness workflow
names; the consumer's holds the keys its live and judged legs name.

**`XAI_API_KEY` is in Actions as of 2026-10-05, and nothing is outstanding.**
It was held locally and deliberately absent while nothing named it; grok was
rostered on 2026-10-04, `evaluate-engine.yml` names the variable, and the
project owner added it to the case repository's `live` environment the same
day. **All four providers' keys are now wired**, so a live ladder is
dispatchable for every rostered engine.

| | |
|---|---|
| Until it is added | A dispatched grok ladder refuses at preflight with an absent credential, which `consumer_ci.md` section 4.17.2 reports as our configuration rather than as a finding |
| What is unaffected | Every gate. `gate-grok.yml` is replay-only and names no secret, so the fourth target gates on a push exactly as the other three do |
| What asserts the wiring | `MQC_CAS_UNI_115710`, which requires a line per rostered engine and would have caught the omission at the time grok was rostered |

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

**Empty as of 2026-10-01.** The project owner settled the last five in one pass,
and section 2A says where each answer now lives. The heading stays because the
next deferral belongs here and a reader looking for one should find the place
it goes, not its absence.

**The numbering has gaps, and they are retired rather than reused.**
Ten questions were settled and removed; section 2A lists them. A number
that moved would break the documents citing it, and this project retires
identifiers for the same reason it retires test ids: a reader returning to
a reference should find what it named or find nothing, never something
else. That is also why `2.4.1` has no `2.4` above it.

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
| Should an inventory row without an implementation be reported? | 2026-10-01, reported and never gated | `cmn_verdict_and_cli.md` section 10.19.1 |
| Is `inconsistency_ceiling` at 0.10 right? | 2026-10-01, 0.20, with three observations escalating to five on a single disagreement | `cmn_verdict_and_cli.md` section 4.9.2.1 |
| Should multi-prompt consistency be built? | 2026-10-01, out of scope and a harness expansion | `cmn_verdict_and_cli.md` section 4.9.5 |
| Should a security case declare the vector it is about? | 2026-10-01, all of them, with a primary | `model_evaluation_test_plan.md` section 9.10.3.1 |
| What should the harness's own live run measure? | 2026-10-01, the same ladder, fired weekly or on a version change | `ci_pipeline.md` section 2.0.2 |

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
| Harness | 687 passing, pylint 10.00/10 |
| Cases | 83 preconditions, 69 graded, pylint 10.00/10 |
| Findings | 24 open: gemini 2, grok 4, openai 8, claude 10, all `QC_LLM_*` or `QC_SEC_*` |
| Graded result | 2 findings about `gemini-3.8-flash`, one P1 and one P2, reproducing on both platforms |
| Consumer gate | 11 jobs: resolve, lint, preconditions and three priority bands, each per platform |
| Graded inventory | 69 inventoried, 69 collected |
| Recorded | 9 observations, all at index 0, security family only |
| Documentation audit | Clean on duplicate sections, dangling references, unregistered codes |
