<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# Open Questions

Decisions that need a person, and the blockers a person has to clear. Everything
here is either a judgement I should not make alone or an action only the account
owner can take.

**This is not a backlog.** Work that is merely unfinished lives in `DESIGN.md`
section 7.6 as a known gap. What is here is waiting on somebody.

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
| Harness | 616 unit, 23 system, pylint 10.00/10 |
| Cases | 58 unit, 69 graded, pylint 10.00/10 |
| Graded result | 2 findings about `gemini-3.8-flash`, one P1 and one P2, reproducing on both platforms |
| Consumer gate | 11 jobs: resolve, lint, preconditions and three priority bands, each per platform |
| Graded inventory | 69 inventoried, 69 collected |
| Recorded | 9 observations, all at index 0, security family only |
| Documentation audit | Clean on duplicate sections, dangling references, unregistered codes |
