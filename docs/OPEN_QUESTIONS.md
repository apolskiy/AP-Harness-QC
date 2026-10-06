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
| Which engines are recorded, and what clears the rest? | 2026-10-04 and 2026-10-05, all four | `config/findings/`, and `CLAUDE_LOG.md` for each recording |
| Where do the credentials live, and which secret is where? | 2026-10-05, **deliberately not recorded in a tracked document** | Nowhere. The properties are asserted by code, per section 1 |
| Is `--max-spend` wired into anything? | 2026-10-04, into every leg that can dispatch | `ci_pipeline.md`, and the `max_spend` input on each |
| What is the known-good state to compare against? | 2026-10-05, the README figures, which are recomputed and checked | `README.md`, by `MQC_CMN_UNI_112323` |

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
