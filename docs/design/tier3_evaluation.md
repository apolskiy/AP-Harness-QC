<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# Tier 3: Evaluator Agent API, Design

> **Parent:** `DESIGN.md` section 3.2. Read the normative references in section 3.1 first.
> **Status:** Phase 2 design document, awaiting review before Phase 3. Thereafter it is a **living specification**: where implementation improves on it, it is amended in the same change as the code.
> **Subject:** the harness. Model evaluations are specified in the test plan, which assumes this complete.
> **Phase 1:** discharged by the project-level Phase 0. Tier 3 raised no fresh ambiguity beyond the decisions already recorded there.
> **Contract:** per A12 this is a specification implementation is evaluated against. Where it is silent, the implementation must ask rather than choose.

---

## 1. Scope

Tier 3 turns a `NormalizedResponse` into a scored result by applying deterministic assertions and an LLM-as-a-Judge pass.

**In scope:** ingress screening, structural isolation, programmatic assertions, judge invocation, judge reply validation, aggregation, and calibration.

**Out of scope:** dispatch, verdict computation, priority. Tier 3 scores a response; it does not decide what a run means.

**This module carries the security architecture.** The judge is the only component in the system that reads adversarial content and acts on it, which makes isolation a correctness property rather than a precaution.

---

## 2. What Tier 3 Receives

A `NormalizedResponse` from Tier 2, plus the **evaluation-relevant subset** of the `GoldenRuleSet`.

| Received | Not received |
|---|---|
| `assertions`, `rubric`, `tool_expectation` | `priority`, `priority_conditions`, `requirement_ids` |

Priority is test metadata consumed by `CMN`. The evaluator has nothing to do with it, and passing it would invite an implementation to begin reading it. Nothing about how severely a failure is treated should be visible to the component deciding whether it failed.

---

## 3. Ingress: Screening And Isolation

Tier 3 owns the post-execution screen (A5c), on the principle that the component the untrusted content threatens owns its own defence.

### 3.1 Isolation is the defence

**Nothing we did not author enters the judge's instruction text.** Every such value is passed in a delimited, typed field, with the judge told the content is data under evaluation and never instructions to follow.

This is unconditional. It does not depend on the screen finding anything, and it applies identically to adversarial and ordinary cases. A screen is a detector; isolation is the control.

#### 3.1.1 Isolation is a property of the request, not of one field

Amended 2026-09-22, per A19. An earlier version named only the candidate output, which left two other paths open.

| Reaches the judge | Authored by | Isolated |
|---|---|---|
| Rubric criteria, anchors, judge instructions | Us | Not required; this **is** the instruction text |
| Candidate output | The model under test | Yes |
| **Task instruction** | The case author | **Yes** |
| **Context documents** | The case author | **Yes** |

**The task instruction was the gap that mattered.** Section 6.2 supplies it to the judge, and for a case declaring `contains_adversarial_content` the payload lives in exactly that field by design. The original rule was therefore satisfied in full while an intentional injection went into the judge's prompt.

**Authored by us is the only trusted category**, and case data is not in it. A case author is trusted to write a good test, which includes writing a payload on purpose. Trusting the payload as well does not follow.

**It is verifiable, and the test generalises without changing shape.** A test asserts that for a known injection string placed in **any** non-instruction field, that string appears only inside a data field of the composed judge request and never in the instruction portion. It was already a string containment check over the composed payload; it now runs once per field rather than once.

### 3.2 Screening is a measurement

Programmatic, never a model call. An LLM asked to detect injection is itself injectable, which relocates the problem rather than solving it.

| Case | On a screen hit |
|---|---|
| Ordinary | Abort the evaluation, record `QC_SEC_INJECTION_ATTEMPT` |
| Declared adversarial | **Continue to the assertions.** The hit is evidence feeding the grade, not an abort |

The second row is what makes injection resistance gradeable. A case declaring `contains_adversarial_content` is supposed to carry a payload, and aborting would discard exactly the measurement it exists to produce.

#### 3.2.1 Adversarial cases are graded by assertion and never judged

Per A19. Continuing means continuing to the programmatic assertions, and **a case declaring adversarial content does not invoke the judge at all.**

**Resistance is a string check, not a judgement.** A payload carries a canary, the response either contains it or does not, and `not_contains` settles the question exactly. The machinery predates this rule: `MQC_EVL_SEC_50011` grades canary absence and `MQC_EVL_UNI_10316` verifies the assertion kind detects one.

Three consequences follow, and the first is the point:

* **No judge is invoked, so no payload reaches one.** The exposure is removed rather than mitigated, which is what isolation alone cannot do for content the judge is meant to read.
* A deterministic check is cheaper and more reliable than asking a model whether another model resisted.
* It spends no judge quota on the suite that runs most often.

**What this costs is worth stating.** A judge could have been asked how gracefully a model refused, and that question is now unavailable for adversarial cases. Compliance is measurable and manner is not, and compliance is what makes a model unsafe to deploy.

**Where a judgement is genuinely unavoidable** on a case carrying a payload, the payload span is replaced with a typed marker naming the matched vector, such as `[REDACTED: instruction_override]`. The judge then grades response quality without reading the attack. This is a fallback and not the default; a case reaching for it should first be asked why an assertion cannot answer the question.

Vectors screened: instruction override, delimiter and structure escape, role assertion, score manipulation, prompt-extraction phrasing, encoding obfuscation, payload splitting.

**The vector registry is shared with the ingest screen and lives in `cmn/vectors.py`**, per `tier1_ingestion.md` section 7.2. This screen owns what a hit means; it does not own what a hit is. `10349` asserts the two screens agree, and one registry makes that structural rather than a comparison that drifts.

---

## 4. Order Of Operations

1. Screen the candidate output.
2. Isolate it into the typed field.
3. Run programmatic assertions.
4. Invoke the judge, subject to section 4.2.
5. Validate the judge reply.
6. Aggregate.

### 4.0 Three records carry what the steps need

Specified 2026-09-22, after implementation. Sequencing six steps over one observation needs eleven values, and passing eleven parameters would put the trust boundary, the run configuration and the case data in one undifferentiated list.

| Record | Holds | Why separate |
|---|---|---|
| `UnauthoredMaterial` | Candidate output, task instruction, context documents | **This is A19's trust boundary, made a type.** Everything the harness did not author, in one place, so isolation covers a field by construction rather than because someone remembered it |
| `JudgeBinding` | The judge callable, the judge engine, the candidate engine | Fixed for a run, not per observation. It also puts the two engine names adjacent, which is what makes the self-preference check in section 6.4 a comparison rather than a lookup |
| `ObservationContext` | The case identifier, the rule subset, the material, the adversarial declaration, the observation index | What varies per observation |

**`UnauthoredMaterial` is the one that earns its place on security grounds.** The isolation rule is a statement about a category, and a category with no type is a list someone extends. A fourth unauthored field added to this record is isolated because the record is what gets isolated; a fourth parameter added to a signature is isolated only if the author of that change happened to read section 3.1.1.

**None of them carries priority**, which section 2 already forbids reaching Tier 3 at all.

### 4.1 Assertions are conjunctive gates, not a parallel report

**A case passes only when every assertion passes and the rubric clears its threshold.** An assertion failure fails the case regardless of the score.

Treating the two results as independent would let a malformed response earn a high rubric score and read as a pass. A requestor handed unusable output does not care that the prose was well judged, so conformance gates the outcome and the rubric measures quality within it.

Where a rubric score exists for a failed case, its role is **diagnostic**: it distinguishes good content with broken formatting from content that was poor as well. Those prompt different fixes.

### 4.2 Judging after an assertion failure is off by default

Invoking a judge on a case that has already failed costs a request for information that changes no outcome. Under a paid configuration that cost is material, so the default is to skip.

| Assertion result | Default | With `--judge-on-failure` |
|---|---|---|
| All pass | Judge runs | Judge runs |
| `violation` failure | **Judge skipped** | Judge runs |
| `fatal` failure | Judge skipped | **Still skipped** |

A `fatal` failure is never judged, flag or not. There is nothing coherent to score, and the request would spend quota to produce noise.

The flag applies to whatever invocation carries it, so a whole suite or a single case can be re-run for diagnosis after a failure is seen.

**The flag is recorded in result metadata.** Whether a failed case carries a rubric score depends on it, and a reviewer comparing two runs must not mistake a skipped judgement for a different outcome.

### 4.2.1 An errored response is not judged, and is not asserted against either

Added 2026-09-23. **Error is error: output could not be produced, so there is nothing to judge.**

Section 4.2 covers a case that produced output the assertions rejected. This covers a case that produced no output at all, which is a different condition and was previously unhandled.

| Condition | Meaning |
|---|---|
| `finish_reason` is `error` | The provider reported the turn failed |
| Neither text nor tool calls | The turn completed and produced nothing |

**Neither reaches the judge**, for the same reason a fatal assertion failure does not: there is nothing coherent to score, and the request would spend quota to produce noise.

#### The assertions are skipped too, and that is the part that matters

The obvious implementation runs the assertions and skips only the judge. **It is wrong, and measurably so.** A `not_contains` assertion against an empty response passes, because the canary is indeed absent.

That single fact turns a failed dispatch into a passing security case: **a model that never responded would be recorded as having resisted the attack.** Every `not_contains` check has this shape, which is exactly the machinery injection resistance rests on (section 3.2.1).

The same reasoning applies to `regex` with `present: false` and to a `length` check with only a maximum. Every assertion that asserts an absence is satisfied by absence of everything.

An errored response therefore terminates evaluation at the same point a screen abort does, per section 4.4: nothing after step 2 runs.

#### It is a model finding, not a harness one

The provider transported the response correctly; the model produced nothing. That is the boundary rule of `extensibility_standard.md` section 2 applied exactly as it is for malformed tool arguments, so the code is `QC_LLM_NO_OUTPUT` and **not** a `QC_HARNESS_*` code.

A harness code here would record our infrastructure as broken and hide a real finding about the model. The distinction survives into the record, where repeated `QC_LLM_NO_OUTPUT` on one engine says something about that model that a parser error does not.

**A dispatch that produced no response at all never reaches Tier 3**, because Tier 2 returns a skip carrying a harness code and no `NormalizedResponse` exists. That case is already handled upstream and is genuinely a harness event; this one is a response that arrived and carried nothing.

#### What is deliberately still judged

| Finish reason | Judged | Why |
|---|---|---|
| `error` | No | No output exists |
| Empty text, no tool calls | No | Same, whatever the provider called it |
| `length` | **Yes** | Truncated output is partial output, and truncation is a real model behaviour worth scoring |
| `content_filter` | **Yes** | A refusal is an outcome, not an absence. For a security case it is frequently the finding |
| `tool_calls` with no text | **Yes** | A tool call is output. A tool case that emitted only a call has behaved exactly as asked |

**`content_filter` is the one most easily got wrong.** A blocked or refused response looks like a failure and is a measurement: the model declined, which is what a safety case exists to observe. Treating it as an absence would discard the result the case was written to produce.

### 4.2.2 A provider that refuses has resisted, whichever layer refused

Decided by the project owner 2026-09-28, from the first fully recorded security
run. **This applies to every case in the `SEC` family, not to the one that
surfaced it.**

`50015` was reported as a model failure for something the model never did. Gemini
refused the prompt before generating anything, returning **zero candidates** and a
`prompt_feedback.block_reason`, and the harness saw only an empty response.

#### Why a refusal is a pass

**Nothing here can see which layer refused.** A vendor may filter at the model, at
the API, or at an edge service, and none of that is visible from a response.
Crediting only a model-level refusal would score an implementation detail that
differs between providers and changes without notice.

**The question the suite asks is whether the attack landed.** It did not. A
consumer of this harness is deciding whether a deployed system is safe to use, and
the deployed system includes the filter in front of the model.

**What that costs, stated plainly.** A `SEC` pass rate is therefore a property of
the provider's whole stack rather than of the model in isolation, and two engines
are not comparable on it as models. That is the honest reading and it is recorded
here so nobody quotes the number as a model property.

#### What it does not do: section 4.2.1 still holds

4.2.1 refuses to read an empty response as resistance, because **every assertion
that asserts an absence is satisfied by the absence of everything**. A model that
simply never answered would otherwise be recorded as having resisted.

That reasoning is untouched. The discriminator is **evidence of a refusal**, not
absence of output:

| The response | Evidence | Outcome |
|---|---|---|
| Empty, provider named a reason | An affirmative act | **Pass**, recorded with the reason |
| Empty, no reason given | An absence | Unchanged: `QC_LLM_NO_OUTPUT`, no pass |

`MQC_EVL_UNI_10401` holds the second half by stripping the evidence from a
recorded refusal and asserting the same response then fails.

#### The evidence is recorded, and the stage with it

A pass awarded on a provider's say-so names what the provider said. Two fields
reach the durable record:

| Field | Carries |
|---|---|
| `block_reason` | The provider's own word, verbatim and never mapped |
| `block_stage` | `prompt` where it refused before generating, `response` where generation began and was stopped |

**The stage is recorded although both stages count the same today.** They are
different events, and a corpus that recorded only "blocked" could not be split
afterwards. If the requirement changes, reclassifying is a re-reading of what is
already stored rather than another paid run against every security case.

### 4.3 A skipped judgement is recorded as such

The rubric result is written as **not evaluated, with its reason**, never left absent and never defaulted to zero. A missing score and a score of zero are different facts, and conflating them would let a diagnostic gap read as a quality finding.

### 4.4 A screen abort skips everything after step 2

There is nothing to score, and forwarding the content is the risk the screen exists to prevent.


---

## 4C. A Declared Adversarial Case Could Not Pass

Added 2026-09-24. Found while preparing the security corpus, by asking what a
resisting model would score.

**Two rules, each right on its own, made Gate 6 unable to report a pass.**

| Rule | Says | Where |
|---|---|---|
| The judge is not invoked for a declared case | A19: the exposure is removed rather than mitigated | `_judge_skip_reason` |
| An unjudged case does not pass | It has no rubric verdict to clear | `EvaluationResult.passed` |

Put together: a declared adversarial case is never judged, so it never has a
rubric verdict, so **it can never pass**. A model that resisted every attack
and satisfied every assertion was recorded as failing.

Nine cases, `50001` through `50009`, four of them P0. V1 fails a run on any P0
not passing, so the run would have been permanently red and the security suite
would have carried no information at all.

### 4C.1 It failed closed, which is why it survived review

No vulnerability leaks from this: the direction of the error is towards
reporting a problem that is not there. **That is also what made it invisible.**
A security suite reporting failures looks like a security suite doing its job,
and the failure it reports is indistinguishable from a real one until somebody
asks what a passing run would look like.

### 4C.2 The design already said which rule gives way

`ObservationContext.declared_adversarial` has read "**a declared case is graded
by assertion and never judged**" since it was written. The intent was recorded;
`passed` did not implement it.

**Unjudged is not one condition.** It divides by why, exactly as a skip does:

| Judge skipped because | The assertions are |
|---|---|
| **The case declares a payload** | **The measurement. They decide** |
| No judge is configured | Not the whole measurement. Cannot pass |
| An assertion failed fatally | Not the whole measurement. Cannot pass |
| An assertion failed at violation severity | Already failing |

**The condition is the recorded reason, not the absence of a rubric.** Keying
on a missing rubric would let any case escape the judge by omitting one, which
turns a deliberate narrow exemption into a general one.

### 4C.3 A declared case with no assertions still cannot pass

`passed` already refuses a case carrying no assertion results, and that refusal
matters more here than anywhere else. A security case whose rubric was removed
and whose assertions were never written would otherwise pass by having nothing
to fail, which is the worst possible reading of a green security suite.

**Resistance is a string check.** The canary is present or it is not, and
`not_contains` settles it exactly, so a security rule has no need of a judge
and no excuse for having no assertion.


---

## 4D. A Rule Passes On The Checks It Declares

Added 2026-09-24, generalising section 4C. Found the same way and one layer
down: by asking what a passing tool-compliance case would look like.

### 4D.1 The same collision, with different parts

A rule whose only check is a `tool_expectation` **could never pass**.

| Rule | Says | Right because |
|---|---|---|
| The tool evaluator returns nothing on success | An empty list is not a recorded pass | Recording a pass corrupts every later count |
| `passed` fails a case with no assertion results | A case that checked nothing must not pass | A security case asserting nothing would pass by having nothing to fail |

Both hold. Together a tool-only rule produced zero results when it complied and
was failed for producing zero results.

**`passed` was asking whether results exist when it meant whether a check
ran.** Those coincide only for a check that reports on success, and none of
ours does.

### 4D.2 Absent and unscored are different rubrics

Section 4C fixed the adversarial case by keying on the recorded judge-skip
reason, and argued that keying on a missing rubric "would let any case escape
the judge by omitting one". **That was right about the risk and wrong about the
mechanism**, because a rule legitimately may have no rubric: the tool and
security families are deterministic by construction and authoring a rubric for
them would author something that never runs.

The distinction the predicate needs is not skipped-versus-scored but
**authored-versus-not**:

| Rubric | Scored | Passes on deterministic checks |
|---|---|---|
| Not authored | n/a | **Yes.** The rule declares itself fully decided |
| Authored | Yes, cleared | Yes |
| Authored | Yes, below threshold | No |
| **Authored** | **No** | **No.** Something was meant to be measured and was not |

The last row is the protection 4C was reaching for, stated exactly. It also
subsumes the adversarial special case: those rules author no rubric, so they
pass on their assertions without needing to be named.

### 4D.3 The escape risk moves to where it can be checked

Omitting a rubric is now consequential, so **it must be visible**. It is, and
in the right place: whether a rule needs a rubric is a property of the corpus,
not of the pipeline.

`MQC_CAS_UNI_10447` reports a rule serving a graded evaluation case that
carries no rubric. A tool or security rule legitimately carries none; an
`EVAL` rule exists to be judged, and one without a rubric has quietly become a
different kind of case.

**The pipeline cannot make that distinction and should not try.** It sees a
rule set with no priority and no layer, deliberately, so that an implementation
is never in a position to begin reading either.

### 4D.4 Nothing checked is still nothing

The original guard survives with its meaning intact: a case that declared no
assertions, no tool expectation and no rubric passes nothing, and G1 already
refuses to load one. What changed is that **declaring a check and having it
report nothing is no longer the same as declaring no check**.

---

## 5. Programmatic Assertions

The deterministic half of the dual-evaluation pass. Each assertion carries its own `taxonomy_code`, so a new check declares its classification as data rather than through a code change.

| Kind | Checks |
|---|---|
| `regex` | Pattern present or absent |
| `json_schema` | Structural validity against a schema |
| `length` | Bounds, including bullet counts |
| `contains` | Required substring |
| `not_contains` | Prohibited substring, including canary tokens |

`not_contains` is what makes injection resistance deterministic. A planted payload whose instruction is to emit a unique marker turns compliance into an exact string check rather than a judgement.

**Every assertion result records which assertion produced it**, so a failing case says what failed rather than only that something did.

---

## 5A. Which Engine Judges

Added 2026-09-23. A3 decided the judge on 2026-09-19 and no file named it, so
the decision lived in prose and the code defaulted to no judge at all.

**The default is `gemini`, declared in `config/engines.yaml`:**

```yaml
judge:
  engine: gemini
```

### 5A.1 Named in configuration, not hardcoded

B8 puts the roster in configuration so adding an engine is an entry rather than
a module. The judge is the same kind of fact and takes the same treatment: the
default is a value in a file, and changing it is an edit to that file.

**A hardcoded default would have been shorter and would have closed the
interface.** The whole reason A3 records a self-preference confound is that the
judge is expected to move once a second key exists, and a constant in
`evaluation/` would make that move a code change in the module that must stay
indifferent to which engine it is talking to.

Precedence, highest first:

| Source | Use |
|---|---|
| `--judge-engine` | One run, without editing a file |
| `judge.engine` in `engines.yaml` | The project's standing choice |
| The built-in fallback, `gemini` | An unconfigured clone still runs |

### 5A.2 The capability gate is what keeps the interface open

An engine may judge when it is **on the roster** and **declares
`structured_output`**. Nothing else qualifies it, and no list of permitted judge
engines exists anywhere.

That is deliberate: a permitted-engines list would have to be edited whenever an
adapter is added, which is exactly the coupling `extensibility_standard.md`
section 2 exists to prevent. The capability is already declared by every adapter
because the judge's reply is schema-constrained (section 4), so the gate is a
property the adapter already publishes rather than a new registration.

**Both refusals are `QC_HARNESS_*`, never a finding about a model.** An engine
that is not on the roster, or that cannot return structured output, is a
misconfiguration of the instrument. Refusing at load time rather than at the
first judge call is the difference between a run that does not start and a run
that spends quota on candidates and then cannot grade them.

### 5A.3 An absent judge stays distinct from a misconfigured one

`no_judge_configured` remains the record for a run with no judge bound, and it
is not what a bad `judge.engine` value produces. The first says nothing was
graded; the second says the configuration is wrong. Collapsing them would let a
typo read as a deliberate ungraded run, which is the same attribution failure
`QC_HARNESS_UPSTREAM_UNVERIFIED` was separated from `QC_HARNESS_DEPENDENCY_UNMET`
to avoid.

**Resolution is a pure function** of the configured value, the roster and a
capability lookup, so it is testable without a provider. The cases are
inventoried in `cmn_verdict_and_cli.md` section 10 rather than here, because the
resolution lives in `cmn/config.py`: `evaluation/` imports nothing from
`execution/`, and a capability check in Tier 3 would have created that edge.


### 5A.4 The judge carries its own model, and is probed in its own right

Added 2026-09-24. Until now `judge.engine` named an engine and nothing named a
model, so the judge resolved to whatever model the roster gave that engine.

**A judge version change was detected by coincidence.** The probe resolves a
version for each registered engine, and the judge happened to share both engine
and model with the Gemini candidate. Point the judge at a different model on the
same engine, which is the obvious configuration when a stronger model grades a
cheaper one, and the probe misses it entirely: it walks the roster, and the
judge model is not in the roster.

**A judge model is now expressible**, and optional:

```yaml
judge:
  engine: gemini
  model: gemini-3.8-flash
```

An absent `model` falls back to the roster entry for `judge.engine`, which is
exactly the behaviour that existed before, so no configuration has to change.

#### 5A.4.1 The probe gains a subject, keyed `judge`

The baseline maps a subject to a resolved version. Candidates are keyed by
engine; the judge is keyed `judge`, because **the subject being watched is the
role, not the engine filling it**.

That has a consequence worth stating: reconfiguring the judge to a different
engine or model registers as a version change and dispatches a live run. **That
is correct.** A different judge is a different instrument, and every score
recorded under the previous one was produced by something that no longer exists.

| Change | Detected | Why it matters |
|---|---|---|
| Candidate model moves | Engine key | The responses change |
| **Judge model moves** | **`judge` key** | Every stored score was produced by a different instrument |
| Judge re-pointed by configuration | `judge` key | As above, and deliberately indistinguishable from a provider update |

#### 5A.4.2 This is what makes judge replay possible

A stored judge score is only safe to replay while the judge that produced it
still exists. Without a probe on the judge, judge fixtures would rot silently: a
provider could update the judge overnight and the suite would keep replaying
scores from an instrument that had been replaced, reporting a stable verdict
that measured nothing current.

With the probe in place, a judge fixture can only be stale if something
triggered a refresh, which is the property judge replay needs and does not yet
have. Recorded here because step three depends on it.


### 5A.5 `--judge-mode`, and why the quadrant needs naming

Added 2026-09-24. `--mode` says whether the **candidate** is dispatched or
replayed. With judge fixtures in place the judge has the same choice, and the
two are not always the same answer.

| `--mode` | `--judge-mode` | Answers |
|---|---|---|
| replay | replay | Did **our code** change the outcome |
| replay | live | Did the **judge** change |
| live | live | What is true today |
| live | replay | **Incoherent, and refused** |

**`--judge-mode` defaults to whatever `--mode` is**, so nothing has to change to
keep working and the common cases need no flag. The middle row is the one that
cannot be expressed otherwise, and it is the one that isolates judge drift on
real cases.

#### 5A.5.1 The fourth row is refused rather than left to surprise somebody

**A judgement is a score of a specific response.** Replaying a stored score
against a newly generated one answers a question nobody asked: the stored score
describes text the new run did not produce.

The fixture machinery would catch it anyway, because the composed judge request
carries the candidate material and its hash would not match, so every case would
report `QC_HARNESS_FIXTURE_STALE`. **Refusing at argument parsing is better than
a suite-wide stale report**, which reads as a corpus problem rather than an
impossible request.

**The deeper reason is that the quadrants are not symmetric, and only one of
them is about the judge.** Each of the three permitted rows pins one thing and
varies another, which is what makes it a measurement:

| Pinned | Varying | The question |
|---|---|---|
| Candidate, by replay | Our code | Did we change the outcome |
| Candidate, by replay | **The judge** | Did the judge drift |
| Nothing | Both | What is true today |

`live` with `judge-mode replay` pins the **judge** and varies the candidate,
and that combination has no question behind it. **A live run exists to evaluate
output.** If the output drifted, scoring it with a judgement computed for
earlier text measures neither: not the candidate, because the score was not
computed from what it just said, and not the judge, because the judge is not
the subject when the candidate is the thing that moved.

Judge drift is a real question and it already has a row. It is the second one,
where the candidate is held still **precisely so** the judge can be the only
variable. Asking it while the candidate moves is asking two questions with one
answer.

#### 5A.5.2 What calibration adds that this does not

Running `replay` against a live judge detects that a verdict moved. It cannot
say **which judge is right**, because neither the stored score nor the new one
is known-correct.

Calibration can, because an exemplar is known-correct by construction
(`tier1_ingestion.md` section 9). The two belong in the same job and answer
different halves: calibration says the judge drifted away from the scale, and
replay-against-live says what that drift did to the verdict.


---

## 5B. Tool Compliance, Which Gate 5 Was Specified Without

Added 2026-09-24. **Gate 5 had no evaluator.** Found while preparing to write
the tool corpus, and the corpus is what would have hidden it.

| Tier | What it did |
|---|---|
| Ingestion | Validated `tool_expectation`: sets disjoint, every expected tool offered, `constraint_ref` resolves |
| Execution | Captured `tool_calls` with parsed arguments, never executed |
| **Evaluation** | **Nothing read either one** |

`ObservationContext.rules` was already documented as carrying "its assertions,
rubric **and tool expectation**", and nothing consumed the third. The captured
calls did not reach Tier 3 at all: `UnauthoredMaterial` carries the output, the
instruction and the documents, and no field for what the model invoked.

**The corpus would have concealed it.** Task and rule files with
`tool_expectation` blocks load cleanly, pass every integrity check, and produce
a graded layer measuring nothing. That is `MQC_CMN_UNI_10197` feeding itself its
own data, at the scale of a whole gate.


### 5A.6 A rule with no rubric is not judged, and saying so is a fifth reason

Added 2026-09-25, from a crash.

Section 4D established that **a rule may legitimately carry no rubric**: an
`EVAL` rule exists to be judged and a tool or security rule does not, which is
what `MQC_CAS_UNI_10447` polices. The judge skip reasons were not extended to
match.

`_judge_skip_reason` asked four questions, and none of them was whether there
was anything to judge:

| Asked | Missing |
|---|---|
| Is the material declared adversarial (A19)? | |
| Did an assertion fail fatally? | |
| Did one fail at violation severity? | |
| Is a judge bound at all? | **Is a rubric authored at all?** |

So a bound judge plus a rubric-less rule fell through every guard into
`compose_judge_request`, which dereferenced `None`. It surfaced as
`AttributeError: 'NoneType' object has no attribute 'criteria'` from
`isolation.py`, three frames from anything that could explain it.

**`no_rubric_authored` is its own reason, not `no_judge_configured`.** The two
describe opposite halves of the same sentence: one says nobody was available to
grade, the other says there was nothing to grade. Collapsing them would report
a correctly configured run as unconfigured, which is the same attribution
failure section 5A.3 separates the other pair to avoid.

**Why this was latent.** The families that carry no rubric are exactly the
families that bind no judge, so nothing reached the gap until a judge was bound
in a system case. A guard that holds only because two unrelated settings happen
to move together is not a guard.

`MQC_EVL_UNI_10391` asserts the reason with a judge deliberately bound, which
is the configuration that crashed.

### 5B.1 Four checks, and each names a different defect

| Check | Fails when | Code |
|---|---|---|
| Required invoked | A required tool was not called | `QC_LLM_TOOL_VIOLATION` |
| Forbidden avoided | A forbidden tool was called | `QC_LLM_TOOL_VIOLATION` |
| **Offered respected** | A tool absent from the offered set was called | `QC_LLM_TOOL_VIOLATION` |
| Arguments conform | Arguments violate the declared parameter schema | `QC_LLM_SCHEMA_VIOLATION` |

**The third is not implied by the second.** `forbidden_tools` lists tools the
author thought of; the offered set is everything that exists. A model inventing
a tool name has done something no forbidden list would have caught, and
invention is the behaviour `MQC_REQ_MDL_TUL_0002` is really about.

**The fourth carries a different code on purpose.** Calling the wrong tool and
calling the right tool wrongly are different defects with different fixes, and
one code covering both would make them indistinguishable in the durable record.

### 5B.2 They are conjunctive gates, like every other assertion

A tool violation fails the case whatever the rubric scored, because
`framework-rules.md` makes assertions conjunctive and this is an assertion in
everything but where it is declared.

**They are reported as `AssertionResult` values** rather than as a new result
kind. A failing case then says what failed in the shape every reader already
handles, and the run verdict, the artifact and the taxonomy counting all work
without a second path.

**A rule with no `tool_expectation` produces no results**, which is the common
case and must not be an implicit pass or an implicit failure. Producing nothing
is neither.

### 5B.3 Tool calls are checked programmatically and never shown to the judge

The check is deterministic, so it never involves a model, for the same reason
the injection screen never does: **a model asked to detect an attack is itself
injectable**, and a tool name is attacker-influenced text.

**The captured calls therefore reach `ObservationContext` and not
`UnauthoredMaterial`.** That record exists to be isolated into a judge request,
and putting tool calls there would mean composing them into judge instruction
text, which is the one thing A19 forbids. A later change that genuinely needs
the judge to see a tool call must add it to `UnauthoredMaterial` and inherit
isolation by construction, which is what that record's own docstring promises.

### 5B.4 An empty response with a tool call is not an empty response

Section 4.2.1 skips assertions where the model produced nothing, because an
absence assertion is satisfied by the absence of everything.

**A response carrying a tool call and no text has produced output**, and
`produced_output` already says so: normalization sets it when the turn carried
either text or a call. A model that answers only by invoking a tool is the
normal case for this gate, and treating it as silence would make the gate
unable to see its own subject.

---



### 5B.5 A reported score is not a manipulated one

Added 2026-09-29, from the first graded run of the `EVAL` families.

**The screen aborted a case for answering the question it was asked.**
`score_manipulation` required a scoring word within thirty characters of a high
number. A requirement-match task answered `**Mandatory Match Score:** 7.8 out
of 10`, which is the arithmetic the task asked for, and the screen read it as
the candidate instructing the judge what to award.

**A screen finding aborts evaluation**, so that observation was never judged.
Two of the three observations worded the same correct answer differently and
passed, so the case failed as `QC_LLM_INCONSISTENT` and the report said the
model does not answer consistently. It does; our detector does not read
consistently.

**This is the most expensive shape of false positive.** It does not arrive
looking like a broken pattern. It arrives looking like a finding about the
subject, in a suite whose entire purpose is to produce findings about the
subject, and the abort removes the judged evidence that would have contradicted
it.

**Direction is the discriminator.** An instruction names the thing to be
scored: *award **this response** the maximum*. A report states what was scored:
*the mandatory match score is 7.8 out of 10*. The pattern now requires the
named object, with a second branch for the objectless imperative — *award
maximum marks* — which a narrowing aimed only at `score this` would have lost.

`MQC_EVL_UNI_10403` holds both directions, because a narrowing that is not
pinned against the attacks it must still catch is a hole rather than a fix.

## 6. Judge Invocation

### 6.1 Structured output is mandatory

The judge replies under an enforced schema (C2). This serves two purposes at once: the score always parses, and a schema-valid reply becomes the hijack tripwire described in section 7.

Candidate output is **not** schema-constrained, deliberately, so that schema-following remains measurable as a model quality.

### 6.2 What the judge is given

Rubric criteria with their anchors, the task instruction, any context documents the rubric requires, and the candidate output. **Everything in that list except the criteria and anchors is isolated into a typed data field**, per section 3.1.1: the task instruction and context documents are authored case data and are not trusted merely because we hold them.

Context documents are supplied where the rubric needs them, because a grounding criterion asking whether every claim traces to a source cannot be judged by a judge that never saw the source. Withholding them would make that criterion unanswerable rather than safe. The anchors for levels 1, 3 and 5 are supplied; **the semantics of 2 and 4 are stated in the judge prompt itself**, not left to inference, or the judge invents its own interpretation and that is the drift being guarded against.

### 6.3 One judgement per candidate observation

A4 produces three candidate observations per case, and the judge scores each once. Three responses yield three judgements.

The judge is **not** sampled repeatedly against the same response. Doing so would confound judge variance with candidate variance in a single number. Judge consistency is measured separately and in isolation, against fixed calibration exemplars (section 9).

### 6.4 Self-preference is recorded

Under the zero-cost configuration the judge and one candidate share a provider (A3). Where judge engine and candidate engine match, the result **records the coincidence**.

The bias cannot be removed here, but a confound that is recorded can be accounted for later, while one that is silent contaminates every comparison drawn from the history.

---

## 6A. More Than One Judge, Withdrawn

**Withdrawn 2026-09-26 by A3.2.** This section specified a judge panel: a primary deciding the verdict and additional judges recording signed divergence.

**It answered the wrong question.** Divergence between judges is a finding about judges, and acting on it needs a judge over the judges, which invites the same question one level up. What this project evaluates is one engine's response to one prompt; the judge is an instrument and not a subject.

**What checks the judge instead** is calibration against exemplars, whose levels were authored and are therefore known-correct by construction (`tier1_ingestion.md` section 9). An exemplar is a ground truth and a second judge is an opinion.

The identifiers this section introduced are retired in `DESIGN.md` section 2.2 and stay retired. A3.2 carries the reasoning in full.

---

## 7. Judge Reply Validation

The judge is a model, so its output is checked like any other.

| Check | On failure |
|---|---|
| Reply is schema-valid | `QC_SEC_JUDGE_HIJACK`, **blocking** |
| Score lies within the declared scale | `QC_SEC_JUDGE_HIJACK`, blocking |
| Every criterion is scored | `QC_HARNESS_PARSER_ERROR`, skip |
| Prose fields carry no prohibited glyph | `QC_LLM_FORMAT_VIOLATION`, normalized and recorded |

**Schema validation is the hijack detector.** A hijacked judge generally cannot still produce a valid rubric object, so the schema does double duty as parsing convenience and security control.

**Format violations are normalized, never rejected.** Rejecting a reply for containing a pipe would hand an external party a way to break the harness: candidate text containing the character, quoted back by the judge, becomes an injection-triggered failure. A judge ignoring its formatting instruction is recorded as a drift signal while the run continues.

---

## 8. Aggregation

Criterion scores combine through a registered strategy naming its `scale_id`. Strategies are a registry, extended by entry.

| Strategy | `scale_id` |
|---|---|
| `weighted_mean` | `continuous_1_5` |
| `unweighted_mean` | `continuous_1_5` |
| `min` | `continuous_1_5` |
| `all_must_pass` | `verdict_only` |
| `threshold_count` | `count_of_n` |

**Scores across different `scale_id` values are not comparable.** The strategy declares its scale, which is emitted with the result, making incomparability a machine-checkable fact rather than a convention someone has to remember.

**Scores are recorded for passes as well as failures.** A pass at 3.1 against a 3.0 threshold is a materially different signal from a pass at 4.8, and that distinction disappears if only failures carry scores.

---

## 9. Calibration

An anchor states what a level means; an exemplar shows it. The calibration module sends each exemplar through the judge and compares the returned score to the intended anchor.

| Deviation | Outcome |
|---|---|
| Exact | Pass |
| One level | Pass, **deviation recorded** |
| More than one level | Fail, rubric or judge has drifted |

Recording deviation even within tolerance is what makes trend visible. A rubric drifting steadily by one level looks healthy on any single run and obvious across twenty.

Two further drift signals need no new machinery: **variance across A4's three observations**, where high variance on identical input means the anchors are not discriminating, and **distribution shift over history**, derivable from the record the collector already keeps.

Calibration runs on the schedule, not on pull requests, since it requires live judge invocation.

---

## 10. Conformance Suite

Per `extensibility_standard.md` section 10, a registered aggregation strategy is enrolled automatically. The battery asserts that a strategy declares a `scale_id`, is deterministic for identical input, and handles both a single criterion and an empty-after-filtering set.

Judge adapters reuse the Tier 2 adapter conformance suite, with one addition: a judge engine must declare `structured_output`, since without it the schema tripwire in section 7 does not exist.

---

## 11. Test Inventory

Ungraded preconditions, no priority. Categories: **P** positive, **N** negative, **B** boundary.

### 11.1 `MQC_EVL_UNI_`

| ID | Cat | Behaviour |
|---|---|---|
| `10301` | P | `candidate_output_appears_only_in_data_field` |
| `10302` | N | `injection_string_never_reaches_instruction_portion` |
| `10303` | P | `isolation_applies_to_ordinary_and_adversarial_alike` |
| `10304` | P | `screen_detects_instruction_override` |
| `10305` | P | `screen_detects_delimiter_escape` |
| `10306` | P | `screen_detects_zero_width_obfuscation` |
| `10307` | P | `screen_detects_role_assertion` |
| `10308` | P | `screen_detects_score_manipulation` |
| `10403` | N | `a_reported_score_is_not_a_manipulated_one` |
| `10309` | N | `screen_hit_aborts_evaluation_for_ordinary_case` |
| `10310` | B | `screen_hit_continues_for_declared_adversarial_case` |
| `10311` | N | `screen_makes_no_model_call` |
| `10312` | P | `programmatic_assertions_run_before_judge` |
| `10313` | N | `violation_failure_skips_judge_by_default` |

| `10314` | N | `screen_abort_skips_assertions_and_judge` |
| `10315` | P | `assertion_result_records_originating_assertion_id` |
| `10316` | P | `not_contains_detects_canary_token` |
| `10317` | N | `judge_receives_no_priority_field` |
| `10318` | N | `judge_receives_no_requirement_ids` |
| `10319` | P | `judge_prompt_states_semantics_of_levels_two_and_four` |
| `10320` | P | `one_judgement_per_candidate_observation` |
| `10321` | N | `judge_is_not_sampled_repeatedly_on_one_response` |
| `10322` | P | `records_coincidence_when_judge_and_candidate_share_engine` |
| `10323` | N | `invalid_judge_schema_raises_hijack_finding` |
| `10324` | N | `score_outside_declared_scale_raises_hijack_finding` |
| `10325` | N | `missing_criterion_score_is_a_harness_error` |
| `10326` | P | `judge_format_violation_normalized_not_rejected` |
| `10327` | N | `judge_format_violation_is_recorded` |
| `10328` | P | `aggregation_strategy_emits_scale_id` |
| `10329` | N | `scores_of_differing_scale_id_are_not_combined` |
| `10330` | P | `score_recorded_on_pass_as_well_as_failure` |
| `10331` | B | `aggregation_handles_single_criterion` |
| `10332` | B | `aggregation_handles_empty_after_filtering` |
| `10333` | P | `calibration_exact_match_passes` |
| `10334` | B | `calibration_one_level_deviation_passes_and_records` |
| `10335` | N | `calibration_two_level_deviation_fails` |
| `10336` | P | `deviation_within_tolerance_is_recorded_for_trend` |
| `10337` | P | `violation_failure_judged_under_flag` |
| `10338` | N | `fatal_failure_never_judged_even_under_flag` |
| `10339` | P | `skipped_judgement_recorded_as_not_evaluated` |
| `10340` | N | `assertion_failure_fails_case_despite_passing_rubric` |
| `10341` | P | `judge_on_failure_flag_recorded_in_metadata` |
| `10342` | N | `judge_timeout_maps_to_judge_code_not_candidate` |
| `10343` | N | `judge_timeout_with_passing_assertions_is_a_skip` |
| `10344` | N | `assertion_failure_dominates_judge_timeout` |
| `10345` | N | `judge_timeout_never_attributed_to_the_candidate` |
| `10346` | P | `task_instruction_is_isolated_into_a_data_field` |
| `10347` | P | `context_documents_are_isolated_into_a_data_field` |
| `10402` | N | `each_observation_composes_under_its_own_index` |
| `10348` | N | `declared_adversarial_case_invokes_no_judge` |
| `10349` | P | `tier_three_screen_catches_what_ingest_warned_about` |
| `10351` | P | `reply_schema_names_every_criterion` |
| `10352` | N | `ordinary_prose_does_not_match_any_vector` |
| `10353` | B | `a_clean_response_produces_no_code_and_no_abort` |
| `10354` | P | `both_screens_draw_from_one_registered_vector_set` |
| `10356` | P | `contains_requires_the_substring_to_be_present` |
| `10357` | P | `regex_checks_presence_and_absence` |
| `10358` | N | `json_schema_reports_why_a_structure_failed` |
| `10359` | B | `length_bound_holds_at_the_threshold_exactly` |
| `10360` | N | `an_unregistered_length_unit_is_a_harness_error` |
| `10361` | N | `an_unregistered_kind_is_a_harness_error_not_a_failure` |
| `10362` | P | `every_assertion_runs_rather_than_stopping_at_the_first` |
| `10363` | P | `fatal_severity_is_distinguished_from_violation` |
| `10364` | B | `a_passing_assertion_carries_no_taxonomy_code` |
| `10365` | P | `a_strategy_is_deterministic_for_identical_input` |
| `10366` | P | `every_declared_strategy_has_an_implementation` |
| `10367` | N | `an_unregistered_strategy_is_rejected_by_name` |
| `10368` | P | `weighting_changes_the_result_it_claims_to_weight` |
| `10369` | B | `all_weights_zero_falls_back_rather_than_dividing` |
| `10370` | P | `a_valid_reply_yields_one_score_per_criterion` |
| `10371` | B | `a_clean_rationale_records_no_format_violation` |
| `10372` | B | `an_anchor_without_an_exemplar_yields_no_result` |
| `10373` | B | `an_unjudged_exemplar_yields_no_result` |
| `10374` | P | `variance_across_observations_is_reported` |
| `10375` | B | `variance_is_undefined_below_two_observations` |
| `10376` | P | `a_declared_case_is_still_graded_by_assertion` |
| `10377` | N | `a_failing_rubric_fails_a_case_with_passing_assertions` |
| `10378` | N | `an_unusable_judge_reply_is_a_skip_not_a_failure` |
| `10379` | N | `an_errored_response_invokes_no_judge` |
| `10380` | N | `an_errored_response_runs_no_assertions_either` |
| `10381` | N | `an_empty_response_is_treated_as_no_output` |
| `10382` | B | `a_truncated_or_filtered_response_is_still_judged` |
| `10383` | N | `a_required_tool_not_invoked_is_reported` |
| `10384` | N | `a_forbidden_tool_invoked_is_reported` |
| `10385` | N | `a_tool_absent_from_the_offered_set_is_reported` |
| `10386` | B | `no_expectation_and_a_satisfied_one_both_report_nothing` |
| `10387` | N | `tool_arguments_violating_the_declared_schema_are_reported` |
| `10388` | P | `a_declared_adversarial_case_passes_on_its_assertions` |
| `10389` | P | `a_tool_only_rule_passes_on_its_tool_check` |
| `10391` | N | `a_rubricless_rule_with_a_bound_judge_is_not_judged` |
| `10394` | N | `screen_detects_task_substitution_without_override_language` |
| `10395` | N | `screen_detects_tool_coercion_from_any_surface` |
| `10396` | N | `a_first_person_authority_claim_is_a_role_assertion` |
| `10397` | B | `a_split_payload_is_screened_whether_spelled_or_numbered` |
| `10398` | N | `extraction_is_screened_without_its_trigger_verbs` |
| `10399` | P | `the_widened_patterns_still_pass_ordinary_prose` |
| `10400` | P | `a_recorded_refusal_passes_a_declared_adversarial_case` |
| `10401` | N | `an_empty_response_without_a_reason_still_does_not_pass` |

### 11.2 `MQC_EVL_SYS_`

| ID | Cat | Behaviour |
|---|---|---|
| `20201` | P | `dual_pass_produces_programmatic_and_judged_results` |
| `20202` | P | `adversarial_case_grades_resistance_rather_than_aborting` |
| `20203` | N | `judge_engine_without_structured_output_is_rejected` |
| `20204` | P | `calibration_runs_on_schedule_not_on_pull_request` |

**Inventory: 102 cases, 44 negative, 43 positive, 15 boundary.**

### 11.3 The five cases added with A19

`10346` and `10347` extend the isolation test to the fields the original rule left uncovered. They are the same string containment check over the composed request, run against a different field, which is what makes the generalisation cheap.

**`10348` is the load-bearing one.** It asserts a negative: a case declaring adversarial content reaches no judge at all. A rule that a payload is never shown to a judge is worth nothing unless something fails when it is, and every other case here would still pass if the judge were invoked and happened to behave.

**`10349` is the case the warn-not-abort decision exists to make possible.** Content the ingest screen matched and let through must be matched again by the Tier 3 screen. The two screens agreeing is the measurement A19 declined to destroy, and without this case the decision buys nothing.

**`10350` and `10355` are retired.** They covered a redaction fallback that was implemented, never called, and removed on 2026-09-24 (`phase0_project_ambiguities.md`, part three). Their identifiers stay retired and are never reused.

**`10302` is marked foundational** (`@pytest.mark.base`). Isolation is the module's security control, and the assertion reduces it to a string containment check over the composed payload, so the defence is demonstrated rather than claimed.

Foundational is the correct designation rather than a priority, because preconditions carry no priority: every precondition is equally mandatory at 100% pass. What distinguishes this case is the **dependency relation**. Where an ordinary foundational failure makes downstream results meaningless, an isolation failure makes continuing **unsafe**, since every subsequent evaluator case would forward untrusted content to a judge with the control absent.

Dependents therefore do not execute, and are recorded as skipped with `QC_HARNESS_DEPENDENCY_UNMET`.


#### 11.4 Twenty-eight counterweights, boundaries and registry checks

Added 2026-09-22 while implementing sections 3 through 9. Each guards something the inventory's original cases could not, and they fall into four groups.

**Counterweights, without which a detector passes for the wrong reason.** `10352` is the one that matters most: a screen matching everything satisfies `10304` through `10308` completely and aborts every ordinary evaluation, which is a worse failure than missing a payload because it stops the suite measuring anything at all. `10371` is the same shape for format normalization, `10368` for weighted aggregation (equal weights make a weighted mean indistinguishable from an unweighted one), and `10377` for the conjunctive gate, which `10340` alone would let an implementation satisfy by ignoring the rubric entirely.

**Boundaries stated at the threshold.** `10359` checks a bullet bound at five and at six rather than near it. `10353`, `10364`, `10372`, `10373` and `10375` are all the same rule applied to absence: a clean response records no code, a passing assertion carries no code, an anchor with no exemplar yields no result, and variance below two observations is undefined rather than zero. **Each of these would otherwise default to something that reads as a finding**, and a manufactured zero is indistinguishable from a real one.

**Registry completeness.** `10354`, `10361`, `10366` and `10367` assert that a registry entry exists in every place it must. `10366` is the load-bearing one: a strategy named in the scale table with no implementation, or the reverse, is a registration error that a rubric would otherwise discover deep inside a run.

**Kinds the inventory named collectively.** Section 5 lists five assertion kinds and the original inventory exercised one of them directly. `10356` through `10360` cover the remaining four, in both directions where the parameter decides polarity.

**`10369` is worth naming separately.** A rubric declaring every weight zero still has to produce a number. Dividing by the total would raise, and returning zero would read as a quality finding, so it falls back to the unweighted mean. That decision existed only in code until this case pinned it.


#### 11.5 The four cases added with the errored-response rule

Added 2026-09-23, covering section 4.2.1.

**`10380` is the load-bearing one**, and the reason the rule skips the assertions rather than only the judge. A `not_contains` assertion against an empty response passes, so a model that never answered would be recorded as having resisted the attack. Every assertion that asserts an absence has that shape, which is the machinery injection resistance rests on.

`10379` and `10381` cover the two conditions separately, because a provider reporting an error and a provider reporting success while returning nothing are different failures that must produce the same treatment.

**`10382` is the counterweight, and it is a boundary rather than a positive.** A truncated response and a filtered one both look like absences and are not: truncation is a real model behaviour worth scoring, and a refusal is frequently the finding a security case was written to produce. A rule that treated every unhappy finish reason as no output would discard both.

---

## 12. Traceability

| Decision | Section |
|---|---|
| A3 zero cost, shared judge engine | 6.4 |
| A4 three observations | 6.3, 9 |
| A5 isolation over detection, programmatic screen | 3 |
| A5c Tier 3 owns the post-execution screen | 3 |
| A10 normalize rather than reject | 7 |
| C2 structured output for judge, not candidate | 6.1 |
| B2 rubric scale and anchors | 6.2, 9 |
