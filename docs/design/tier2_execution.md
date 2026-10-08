<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# Tier 2: Execution API, Design

> **Parent:** `DESIGN.md` section 3.2. Read the normative references in section 3.1 first.
> **Status:** Phase 2 design document, awaiting review before Phase 3. Thereafter it is a **living specification**: where implementation improves on it, it is amended in the same change as the code.
> **Subject:** the harness. Model evaluations are specified in the test plan, which assumes this complete.
> **Phase 1:** discharged by the project-level Phase 0. Tier 2 raised no fresh ambiguity beyond the decisions already recorded there.
> **Contract:** per A12 this is a specification implementation is evaluated against. Where it is silent, the implementation must ask rather than choose.

---

## 1. Scope

Tier 2 turns an `EvaluationCase` into a normalized response by dispatching it to one provider endpoint.

**In scope:** request composition, dispatch, response normalization, tool-call capture, resolved model version, provider error translation, rate limiting, and replay.

**Out of scope:** scoring, judging, injection screening, verdict computation. Tier 2 does not interpret content. An adapter that begins interpreting output has become a second evaluator with no rubric.

**One request per case. No loop, no retry into an agentic cycle, no tool execution** (A9). The model's tool-call *intent* is the recorded artifact.

---

## 2. What Crosses The Boundaries

| Direction | Passes | Never passes |
|---|---|---|
| Tier 1 to Tier 2 | `EvaluationCase`, minus the evaluation-only fields Tier 3 owns | Raw files, loader state, format knowledge |
| Tier 2 to Tier 3 | `NormalizedResponse` | Provider payloads, SDK objects, vendor error types |

A vendor SDK object reaching Tier 3 is a design defect, because it would make the judge dependent on which provider produced the output it is judging.

**Tier 2 does not screen for injection.** The post-execution screen belongs to Tier 3 ingress, on the principle that the component the untrusted content threatens owns its own defence (A5c). Tier 2 normalizes and hands over.

---

## 3. The Adapter Interface

One interface, implemented per provider. This is a **stable interface** under `harness_extensibility_standard.md` section 9, so it may gain an optional parameter with a default and may never gain a required one.

| Operation | Returns | Responsibility |
|---|---|---|
| `compose_request` | Provider-shaped request | Build from an `EvaluationCase` |
| `dispatch` | Provider-shaped response | One call. No loop |
| `normalize_response` | `NormalizedResponse` | Canonical shape |
| `extract_tool_calls` | `list[ToolCall]` | Intent only, never executed |
| `resolve_model_version` | `str` | The version the provider **returned** (A8) |
| `map_error` | `QC_HARNESS_*` code | Translate provider failures |
| `declare_capabilities` | `Capabilities` | See section 6 |

### 3.1 `map_error` carries more weight than it appears to

Provider error taxonomies differ in naming, in HTTP status usage, and in what they consider retryable. Without translation, a rate limit from one vendor and a rate limit from another become different rows in the durable record, and cross-engine comparison of harness reliability becomes impossible.

Every adapter maps to the same closed set: `QC_HARNESS_CANDIDATE_TIMEOUT`, `QC_HARNESS_RATE_LIMIT`, `QC_HARNESS_AUTH_ERROR`, `QC_HARNESS_PARSER_ERROR`, `QC_HARNESS_VERSION_UNAVAILABLE`.

An unrecognised provider error maps to `QC_HARNESS_PARSER_ERROR` and **records the original**, so an unmapped case is visible rather than silently absorbed into a neighbouring category.

### 3.2 The adapter registry

`harness_extensibility_standard.md` section 10 requires that registration enrol an adapter in its conformance battery automatically. That requires a registry, and this is where it lives: `execution/adapters/registry.py`, mapping an engine name to the adapter class serving it.

| Rule | Why |
|---|---|
| The engine name is the **only** key | It is already the value used in CLI selection, result metadata and fixture paths, and those three must agree |
| One name maps to exactly one adapter | Two adapters under one name would make `--engine gemini` mean whichever registered last, and a fixture recorded by one would replay through the other |
| Registering a duplicate name **fails at import** | A run that started before the collision was noticed would produce results attributed to the wrong provider |
| An unregistered name is rejected by name, listing what is registered | A typo and an unimplemented provider are different problems, and the message should let the reader tell which they have |
| The battery is parametrized over the registry, never over a list | A list is a second place to forget, which is the failure mode the standard's automatic enrolment exists to remove |

The registry holds classes rather than instances, because a model identifier is supplied at execution time per B8 and an instance would have to be constructed with one before the run knew which one.

### 3.2.1 A shared base holds construction and identity

The three adapters were written independently and converged on identical code for three things: storing a requested model, reporting an engine name, and populating the eleven canonical fields. That is not a coincidence to be tolerated; it is the interface's own shape showing through.

`ConfiguredAdapter` sits between the interface and each adapter, supplying construction, the two identity properties, and one helper that assembles a `NormalizedResponse`. An adapter declares its engine name and default model as class attributes and implements only what is genuinely provider-specific.

**This does not weaken section 9's stability guarantee.** `ProviderAdapter` remains the interface, and an adapter may still implement it directly. The base is a convenience beneath the contract, not a new requirement above it.

**What each adapter extracts is named:** `ProviderFacts` carries the six values an adapter pulls out of its provider's response, and the base turns those into the canonical record. Without it every adapter repeats the same eleven-field constructor call, and a field added to the record has to be found in three places instead of one.

| Belongs in the base | Belongs in the adapter |
|---|---|
| Storing the requested model | Composing the request |
| Reporting the engine name | Reading the provider's text, tool calls and usage |
| Assembling the canonical record from `ProviderFacts` | Mapping the provider's finish reasons and error classes |
| | Declaring capabilities |

### 3.3 Provider-side agentic features are disabled explicitly

A9 forbids a loop, an agentic cycle and tool execution. One provider SDK offers automatic function calling **enabled by default**, which executes the model's tool calls locally and returns the result of a multi-turn exchange in place of the first response.

Relying on not passing tools is not sufficient, because a tool case passes tools by definition. The adapter therefore switches the behaviour off explicitly, and a case asserts that it did.

**Why this is a design statement rather than an implementation detail:** if it ever silently re-enabled, the harness would execute a tool the model chose, on the machine running the suite, and record a multi-turn transcript as a single response. Tool-use compliance would then be measured against output the harness itself had participated in producing.

### 3.4 Official SDKs, and all three are required

Each adapter calls its provider through that provider's **official SDK** rather than through raw HTTP.

| Option | Cost |
|---|---|
| **Official SDK** | A pinned dependency per provider |
| Raw HTTP | We reimplement authentication, retry semantics, error classes and response parsing for three providers, and maintain them against three changing APIs |

Raw HTTP would also make the error-mapping in section 3.1 our own invention rather than a translation of something the provider defined, which is exactly the coupling that makes a taxonomy drift.

**All three are required dependencies, not optional extras.** The registry imports every registered adapter so the battery can be parametrized over it, and an optional SDK would let the battery cover two providers on a machine missing the third while still reporting green. That is the failure automatic enrolment exists to prevent, arriving by a different route.

`httpx` is a **direct** dependency, not a transitive one. One provider's SDK raises no timeout class of its own, so the adapter catches `httpx`'s. Depending on a library without declaring it means a transitive upgrade can break us with no record of why.

### 3.5 A wire protocol is not a vendor

Added 2026-09-25, extending the adapter registry so that a fourth engine costs
four values rather than a module.

**The registry was already extensible and the adapters were not.** Registration
enrols an engine in the conformance battery automatically (section 10 of
`harness_extensibility_standard.md`), so adding one was never a wiring problem. It was
a **duplication** problem: every new engine reimplemented request composition,
normalization, tool-call capture, version resolution and error mapping, none of
which is actually vendor-specific.

**Most vendors do not have a protocol.** They serve somebody else's.

| Protocol | Module | Engines |
|---|---|---|
| Chat Completions | `openai_protocol.py` | `openai`, `grok`, and any of DeepSeek, Mistral, Groq, Together, OpenRouter, Ollama |
| Google Gen AI | `gemini.py` | `gemini` |
| Anthropic Messages | `claude.py` | `claude` |

#### 3.5.1 What adding an engine costs

`grok.py` is the evidence, and it is deliberately the whole file:

```
class GrokAdapter(OpenAICompatibleAdapter):
    ENGINE_NAME = "grok"
    DEFAULT_MODEL = "grok-4"
    BASE_URL = "https://api.x.ai/v1"
    API_KEY_ENV = "XAI_API_KEY"
```

No request composition, no normalization, no error mapping, **and no judging**:
`compose_judgement` and `parse_judgement` are protocol properties, so an engine
on a served protocol can judge the day it is registered. The conformance
battery covers it without a line added, and its response doubles are the
protocol's.

**`BASE_URL` is the only field that routes a request.** An engine that omits it
reaches OpenAI holding another vendor's key, which surfaces as an
authentication failure naming the wrong vendor. `MQC_EXE_UNI_113014` reports it.

#### 3.5.2 The credential is a variable name, never a value

`API_KEY_ENV` names the environment variable and nothing reads it until a
client is constructed. **Two engines on one protocol therefore never share a
credential**, which is what keeps `grok` from spending an OpenAI key, and it
holds without any configuration file learning a secret.


#### 3.5.1 The roster is the list, and it gates the run

Added 2026-10-04, after rostering a fourth engine found two defects one after
the other.

**Adding a provider is an entry in `config/engines.yaml`.** On the list it runs;
off the list it refuses, naming what is on it. That is the whole of the rule and
it is what makes the engine set expandable without touching code.

##### 3.5.1.1 Two lists, and the weaker one was doing the gating

| List | Says | Lives in |
|---|---|---|
| The adapter registry | Code exists for this provider | `execution/adapters/registry.py` |
| **The roster** | A model, an observation count and a request spacing are configured | `config/engines.yaml` |

**An engine with an adapter and no roster entry ran.** `dispatch_plan` resolves
`model=roster[engine].model if engine in roster else None`, and a plan carrying
no model dispatches against the **adapter's own default**. For grok that default
was `grok-4`, which the provider does not serve, so `--engine grok` before
rostering would have produced a 404 on every case.

| | |
|---|---|
| What it looked like | A broken harness, or a provider outage: a 404 per case, 69 times |
| What it was | Configuration not yet done |
| What it cost to tell apart | Reading `dispatch_plan`, because nothing said so |

**Refusing once is the whole difference.** `require_rostered_engine` raises
`QC_HARNESS_PREFLIGHT_FAILURE` when the run is configured, before anything is
collected, and names every rostered engine plus both remedies: add an entry, or
declare the absence under `not_rostered`.

**A preflight code rather than a parser one**, deliberately. The flag's value is
well formed; what is missing is configuration for it, which is an environment
fact rather than a typo.

##### 3.5.1.2 The flag stopped enumerating, which is what exposed this

`--engine` carried `choices=("gemini", "openai", "claude")` until the same day,
so rostering a fourth engine made the flag refuse one the roster named:
`invalid choice: 'grok'` against a configuration that listed it.

**The argument against enumerating was already written one flag away.**
`--judge-engine` carries it: "NO choices TUPLE, deliberately. An enumerated list
here would have to be edited whenever an adapter is added, which is the coupling
the capability gate exists to avoid." Nobody had applied it to `--engine`.

**Removing the tuple revealed the real gap rather than creating it.** With the
enumeration gone, an engine off the roster reached `dispatch_plan` for the first
time, and `dispatch_plan` had always been willing to run it. The enumeration had
been hiding a missing gate by refusing three engines' worth of values for the
wrong reason.

### 3.6 A role is derived, never listed

Added 2026-09-25, alongside section 3.3.

An engine can be a **candidate** (something under test) or a **judge**
(something that grades), and most engines are both. **Neither is a list.**

| Role | Qualification |
|---|---|
| Candidate | Registered. Every adapter can be dispatched against |
| Judge | Registered **and** declares `structured_output` |

This is the arrangement `config/engines.yaml` already describes in prose: "any
engine in the roster that declares the structured_output capability may judge;
there is deliberately no list of permitted judge engines to keep in step with
the adapters." `engines_for_role` makes it queryable rather than only stated,
so a caller asking which engines may judge gets an answer derived from the
registry instead of maintaining a second copy.

**Adding Grok added a candidate and a judge in one line**, because the
capability came with the protocol. That is the property worth having: a new
engine arrives in both roles or in neither, and never in one because somebody
remembered to add it to one list.

---

## 4. Canonical Shapes

### 4.1 `NormalizedResponse`

| Field | Type | Notes |
|---|---|---|
| `case_id` | `str` | Identity |
| `engine` | `str` | Which adapter produced it |
| `mode` | `str` | `live` or `replay` (A6) |
| `requested_model` | `str` | What we asked for |
| `resolved_model` | `str` | What the provider returned (A8) |
| `text` | `str` | Primary output |
| `tool_calls` | `list[ToolCall]` | Empty when none |
| `output_tokens` | `int` | Recorded alongside duration (A7.2) |
| `duration_ms` | `int` | Normalized downstream, not here |
| `finish_reason` | `str` | Normalized across providers |
| `raw_reference` | `str` | Pointer to the stored original, never the object itself |

`raw_reference` is a pointer rather than an embedded payload. Carrying the vendor object forward would defeat section 2, but discarding it entirely would make a normalization defect undiagnosable.

### 4.2 `ToolCall`

| Field | Type | Notes |
|---|---|---|
| `tool_name` | `str` | Canonical name |
| `arguments` | `dict[str, Any]` | **Parsed**, never a JSON string |
| `call_id` | `Optional[str]` | Absent where a provider supplies none |
| `sequence` | `int` | Order within the response |

**Arguments are always a parsed mapping.** Providers differ here: some return arguments as a structured object, others as a JSON string that must be parsed. Leaving that difference visible to Tier 3 would mean the judge handling two shapes for the same fact.

**A parse failure on tool arguments is a model finding, not a harness defect.** The provider transported the response correctly; the model emitted malformed JSON. It maps to `QC_LLM_SCHEMA_VIOLATION`, not `QC_HARNESS_PARSER_ERROR`. This is the boundary rule from `harness_extensibility_standard.md` section 2, applied to the one place it is easiest to get backwards.

### 4.3 The finish reason is reconciled, not transcribed

Each provider spells the same outcome differently, and one of the three does not report a tool-calling turn in the finish reason at all: it ends such a turn with the ordinary stop reason and carries the calls in the content parts, while the other two name it explicitly.

Transcribing each provider's value would make a cross-engine comparison of tool-use rates a comparison of vendor conventions, which is the same defect section 3.1 describes for error codes.

**Where a provider is silent, the normalized value is derived from what the response contains.** An adapter reporting an ordinary stop while carrying captured tool calls normalizes to the tool-calling reason.

**The derivation is deliberately narrow.** It applies only where the provider said the turn stopped normally. A truncated or filtered turn keeps its own reason even when calls were captured, because truncation is the more important fact about that response and a derived value must never overwrite a reported one.

Three refusal-shaped provider reasons collapse into one canonical value. The canonical question is whether content was withheld; **why** the provider withheld it belongs in the record rather than in the vocabulary, or the vocabulary grows with every provider's policy taxonomy.

#### 4.3.1 An adapter that normalises a refusal records the provider's word for it

Added 2026-10-01, after the first Claude recording.

Section 4.3 settles that the canonical value answers **whether** content was
withheld and that **why** belongs in the record. An adapter can satisfy the
first and not the second, and one did: Anthropic returns
`stop_reason="refusal"`, the Claude adapter mapped it to the canonical
`content_filter`, and left `block_reason` empty.

**Nothing downstream reads the canonical value to decide a refusal.**
`tier3_evaluation.md` section 4.2.2 and `AP-Model-QC` `model_evaluation_test_plan.md`
section 9.12 both turn on `blocked_by`, which is `block_reason`. So the
provider refused, the adapter knew, and the case was reported as a model
failure on all three observations.

| | `finish_reason` | `block_reason` | What section 9.12 concludes |
|---|---|---|---|
| gemini refusal | `content_filter` | `SAFETY` or `OTHER` | Resistance, a pass |
| Claude refusal, before | `content_filter` | **empty** | **A model failure** |
| Claude refusal, after | `content_filter` | `refusal` | Resistance, a pass |

**This is the second time.** `MQC_EXE_UNI_113509` records a gemini double of the
wrong shape that reported `154002` as a model failure for three recorded runs.
That was corrected in the gemini adapter rather than stated as an obligation on
adapters, so the next adapter written reproduced it. **A fix applied to one
implementation of an interface is not a fix to the interface.**

**Derived from the one mapping rather than listed twice.** A stop reason is a
block exactly when `_FINISH_REASONS` sends it to the canonical refusal value, so
registering a new refusal-shaped vocabulary word extends both at once. The
alternative is two lists that eventually disagree about what a refusal is.

**The stage is `response`.** Anthropic refuses while generating, so nothing was
withheld before the prompt was read. Section 4.3's own reasoning applies: both
stages count the same today and a corpus storing only "blocked" could not be
split later.

`MQC_EXE_UNI_113022` covers the adapter. `MQC_CAS_UNI_115402` covers the corpus,
and it is the one that would have caught this: it reads the recorded fixtures and
reports any response that withheld content without saying why, whichever adapter
produced it.

### 4.4 Duration is measured by the dispatcher, not by the adapter

An adapter builds a `NormalizedResponse` from a response object it did not time, so it sets `duration_ms` to zero and the dispatcher stamps the measured value.

**The measurement has to be taken in one place** or the three adapters would each decide what the interval covers. The dispatcher's interval is the one that matters, because it is the only one that can exclude configured request spacing: spacing is our pacing decision and counting it as model latency would make a free-tier run look like a slow model.

---

## 5. Model Version Resolution

Captured in preflight and attached per result (A8). **The resolved identifier, not the requested one:** aliases float, and recording only the request hides precisely the event that makes a score change uninterpretable.

| Situation | Behaviour |
|---|---|
| Provider returns a version | Record it |
| Provider returns nothing usable | `QC_HARNESS_VERSION_UNAVAILABLE`, preflight fails, run aborts |
| Resolved differs from requested | Record both. Not an error; it is the signal |

Preflight failure aborts before any case runs, per `cmn_verdict_and_cli.md` section 4.2. A run whose model identity is unknown produces scores nobody can interpret later.

---

## 5A. The Anthropic Request States What It Depends On

Added 2026-09-23 with the migration from `claude-opus-5` to `claude-opus-5-5`.

**The model moved and nothing in the adapter had to change**, which is the
result section 3 was designed for rather than a coincidence. Of the four
breaking changes the newer model introduces, this adapter was exposed to none:

| Breaking change | Why it does not reach here |
|---|---|
| Thinking cannot be disabled | The adapter never sent a `thinking` field |
| Forced `tool_choice` is rejected | Tool use is **behaviour under test**, so the adapter never forces a call |
| Thinking blocks bind to model and conversation | One request per case, so no turn replays a block |
| Computer use only through the toolset | Not declared, and would be tool execution rather than capture |

The third row is the interesting one. **"One request per case, no loop" was
adopted to keep tool-call intent unexecuted**, and it independently removed an
entire class of migration work: an adapter that replayed conversation turns
would have had to audit every one of them against the new binding rules.

### 5A.1 Effort is stated, never inherited

The newer model defaults `output_config.effort` to `medium` where its
predecessor defaulted to `high`. An adapter sending no `output_config` would
therefore have changed how much the model thinks **without any line of this
repository changing**, and the resulting observations would have been recorded
as though nothing had moved.

The adapter now names the value:

```
_DEFAULT_EFFORT: Final[str] = "medium"
```

**This is the same rule as `py-version` in `.pylintrc` and the explicit
`--engine` in CI.** Each states a value the tool would otherwise infer, and each
exists because the inferred value can move underneath a run that is claiming to
be reproducible. B8 puts the roster in configuration for the same reason; a
request parameter that changes results belongs in the request.

**It enters the request hash, which is the point.** `hash_request` serializes
the whole composed request, so the effort level is part of what a replay fixture
was recorded against. Changing it makes every affected fixture report
`QC_HARNESS_FIXTURE_STALE` rather than replaying a response produced under a
setting that no longer applies. A value left to an API default could not be
detected that way, because nothing local would have changed.

`medium` is the value chosen, not merely the value inherited: Anthropic reports
the newer model at `medium` exceeding its predecessor at `high` on coding and
knowledge work, and this project's graded cases are code comprehension. The
level is a constant so that moving it is a diff, a stale fixture and a recorded
decision rather than an invisible drift.

### 5A.2 Thinking is now always on, and the normalizer already handled it

The newer model cannot disable thinking, so every response carries `thinking`
blocks, and text the model writes between tool calls can arrive as a
progress-update `thinking` block rather than a `text` block.

**`normalize_response` selects `type == "text"` and was already correct.** It
was written that way to ignore block types this project does not consume, and
that decision absorbed a response-shape change made two model generations later.
A normalizer that had concatenated every block, or read `content[0]`, would now
be emitting reasoning text into the candidate answer under evaluation.

`113012` holds the four breaking changes as a standing check on the composed
request, so a later edit cannot reintroduce one and discover it as a 400 during
a live run.

---

#### 5A.7 The judgement schema is translated for the wire

Added 2026-09-28, from the first live judged run.

**No judgement had ever reached Gen AI.** Every one returned `400
INVALID_ARGUMENT` naming `additional_properties` as a field it cannot find:
`response_schema` takes a restricted OpenAPI subset, not JSON Schema. The whole
`EVAL` family was unjudgeable live, and the `SEC` family did not reveal it
because those rules carry no rubric.

**The composed schema is right and is unchanged.** `additionalProperties: false`
is what makes the reply validation strict, and `_require_schema_valid` reads the
same object: a judge returning a criterion nobody asked for must fail. Weakening
the schema to satisfy one provider would weaken it for every provider.

**So the adapter translates.** A provider's constraints stop at the adapter, the
same rule that keeps vendor types out of Tier 3, and `_wire_schema` copies the
schema without the keywords this provider rejects.

**The rejected list is evidence-driven and short.** `additionalProperties` is
there because a request carrying it was refused, not because a list somewhere
says so. An entry is added when a request fails for it, which keeps the file from
claiming knowledge nobody verified.

#### 5A.8 A judgement is recorded per observation

Added 2026-09-28, from the first replay of a judged family.

**Three observations kept one judgement.** `JudgeRequest` carried no
`observation_index`, and the channel read one through
`getattr(request, "observation_index", 0)`. The default was always taken, so
every observation of every case composed its key at index zero: observation 1
overwrote 0, observation 2 overwrote 1, and the surviving file held the hash of
whichever observation was judged last.

**Replay then failed as staleness.** Observation 0 recomputed its hash over its
own candidate text, met the hash of observation 2, and raised
`QC_HARNESS_FIXTURE_STALE` — which reads as a corpus problem and is not one.
The `amb` family recorded live and would not replay.

**Every layer but one was already built for it.** `ObservationContext`,
`JudgementKey` and the fixture path all carry the index; `compose_judge_request`
did not take it and so could not pass it on. The `getattr` default is what made
the gap silent, and direct attribute access replaces it: a request without the
field is now loud.

**The index is routing, not content.** It names the fixture and never reaches
the provider, so `rendered()` does not read it and two observations of identical
material compose identical payloads.

## 6. Declared Capabilities

An adapter declares what its provider supports. Unsupported pairs are then **derived rather than hand-maintained**.

| Capability | When absent |
|---|---|
| `tool_calling` | Every `MQC_*_TOOL_` case for this engine becomes an unsupported pair |
| `structured_output` | This engine cannot serve as judge |
| `system_instruction` | Instruction folded into the prompt, and the deviation recorded |

Configuration may still declare an additional unsupported pair with a written reason (A13), but a capability gap should not depend on someone noticing it.

---

## 7. Replay

Replay is the default mode (A6) and covers most engines under the zero-cost configuration (A3).

### 7.1 Fixtures store every observation

A4 specifies three observations per case. A live recording captures three genuinely different responses, and **replay reproduces all three**.

Replaying one response three times would show zero variance and falsely imply the model is deterministic, destroying the same-commit reliability signal that repeat observation exists to produce.

### 7.2 Staleness is detected, not silently tolerated

A fixture is located by `(case_id, engine, observation_index)` and **stores a hash of the request that produced it**. Before replay the composed request is hashed and compared.

#### 7.2.1 The key is a tuple; the path splits it

Amended 2026-09-22, after the first Windows run refused to create the directory.

**A `case_id` cannot be a path segment.** Section 3.11 of `tier1_ingestion.md` defines it as `<task_id>::<rule_id>`, and a colon is the drive separator on Windows, so the operating system rejects the name outright. The two sections were written apart and are incompatible on one of the two supported platforms.

The fix keeps both. The **key** stays the tuple, because that is the identity a record carries. The **path** splits it into its two halves, which are already validated identifiers:

```
tests/fixtures/replay/<engine>/<task_id>/<rule_id>/<observation_index>.json
```

**Encoding the colon was rejected.** Any substitution has to survive a task identifier that already contains the replacement, and `MQC_TASK_a__b::MQC_RULE_c` and `MQC_TASK_a::MQC_RULE_b__c` would collide under a `__` substitution. Hashing was rejected for a different reason: section 7.2 values fixtures being findable, and a directory named by digest is findable only by a tool.

Splitting needs no encoding at all, because both halves are identifiers this harness already screens for reserved device names and case collisions (A18).

**This was a design conflict rather than an implementation defect**, and it surfaced only because the harness runs on both platforms. On Linux the illegal name would have been created without complaint, and the incompatibility would have shipped.

| Condition | Behaviour |
|---|---|
| Hash matches | Replay the stored response |
| Hash differs | `QC_HARNESS_FIXTURE_STALE`, skip, naming the case |
| No fixture found | `QC_HARNESS_FIXTURE_MISSING`, skip, naming the case |

Locating by identity keeps fixtures findable; verifying by hash keeps them honest. Without the hash, changing prompt composition would silently replay a recorded answer to a **different question**, which is the same class of corruption as an unmarked replay (A6) and harder to notice.

### 7.3 Recording

Recording happens only in `live` mode and writes fixtures with the request hash, the response, and the resolved model version. A recorded fixture therefore carries the model identity it came from, so replaying against a later model version is visible in the record rather than assumed away.

**The stored response is the normalized record, not the provider payload.** Replay rebuilds a `NormalizedResponse` from it directly and no adapter takes part.

| Storing | Consequence |
|---|---|
| **The normalized record** | A fixture is provider-agnostic and survives an SDK shape change. Replay exercises no normalization |
| The provider payload | Replay would re-run normalization, and every fixture would break whenever a vendor changed a field name |

The second option buys one thing: normalization defects would surface during replay. That is not worth the cost, because normalization is already covered directly by the conformance battery (section 9), by the per-adapter cases (section 10.1.3), and by `123001` asserting that three adapters produce one shape. Paying for it a fourth time with fixtures that rot on a vendor's schedule is a bad trade.

The record therefore serializes to and from a plain mapping, and **deserialization goes back through the record's own constructor**, so a hand-edited fixture carrying an unregistered mode or finish reason is rejected on read rather than replayed.

---

### 7.4 The judge is replayed too, and Tier 3 never learns of it

Added 2026-09-24. Until now `FixtureKey` keyed the candidate only, so a replay
run replayed the response and called the judge **live**. A replay was therefore
neither free nor deterministic: two runs of one commit could produce different
verdicts, which contradicts the verdict being recomputable from stored
artifacts.

#### 7.4.1 The architecture already allowed it

`harness_extensibility_standard.md` section 2 states that a tier does not know how the
tier below obtained its input, and that Tier 3 cannot tell whether a response
came from a provider or a fixture. **That principle extends to the judge without
amendment**, because `JudgeBinding.invoke` is an injected callable: a replaying
judge is a different callable, bound by the caller.

So `evaluation/` changes not at all. It still imports nothing from
`execution/`, it still cannot tell, and the machinery lives here with the rest
of replay.

#### 7.4.2 What locates and what invalidates a judgement

| | Candidate | Judgement |
|---|---|---|
| Key | `case_id`, `engine`, `observation_index` | `case_id`, **`judge_engine`**, `observation_index` |
| Hash over | The composed request | The composed **judge** request |
| Also stale when | | **The judge model differs** |

The composed judge request already carries the case, the rubric and the
candidate material, so hashing it covers every input except one: **who judged**.
A rubric edit, a different candidate response and a reworded prompt all change
the hash. A judge model change does not, because the model is not part of the
request, so it is stored alongside and compared separately.

**Two stale reasons are reported separately** because the operator response
differs. A hash mismatch means the question changed and the score answers a
different one. A model mismatch means the question is the same and the
instrument is not.

#### 7.4.3 A missing judgement is a skip, never a live call

A replay run that cannot find a judgement records
`QC_HARNESS_FIXTURE_MISSING` and skips, **excluded from the skip-rate
denominator**, on the same reasoning as a dependency skip: nothing was measured
about the model, so it must not count against a threshold.

**It never falls back to a live call.** That fallback would restore both the
drift and the quota spend silently, under exactly the load that would hide it,
and it is the fail-open pattern this project refuses everywhere else.

The consequence is accepted and stated: **a new graded case is unjudged in
replay until a live run records its judgement.** That is the honest result. It
reports that nothing was measured rather than guessing, and the live schedule is
what fills it in.

#### 7.4.4 Why this is safe now and was not before

A stored judgement is trustworthy only while the judge that produced it still
exists. Section 5A.4 of `tier3_evaluation.md` made the judge a probe subject in
its own right, so a judge model change is detected and dispatches a live run.

Without that, judgements would rot silently: a provider could update the judge
overnight and the suite would keep replaying scores from an instrument that had
been replaced, reporting a stable verdict that measured nothing current. **The
probe is what makes replay safe, and it had to come first.**



### 7.6 The replay skip that never happened

Added 2026-09-25, found by writing the first graded case that reads a fixture.

`_replay_case` is documented as returning "a skip when the fixture is missing
or stale. **Both are reported, never silently replayed**". It caught
`FileNotFoundError` and `ValueError`.

**The replay store raises neither.** `FixtureMissing` and `FixtureStale`
inherit from `Exception` alone, so the handler never fired and a missing
fixture propagated out of dispatch as an unhandled exception.

| Promised | Actual |
|---|---|
| `QC_HARNESS_FIXTURE_MISSING`, recorded as a skip | The exception escapes dispatch |
| `QC_HARNESS_FIXTURE_STALE`, recorded as a skip | The exception escapes dispatch |

**A harness event surfaced as a test error**, which `framework-rules.md`
section 4 forbids: a `QC_HARNESS_*` code is a skip or broken and never a
failure, because a red suite reads as a finding about the model.

#### 7.6.1 Why it stayed invisible

`MQC_EXE_UNI_113003` and its neighbours assert that **the store** raises, which
it does. Nothing asserted that **dispatch converts** what the store raises into
a skip, and the two are different claims about different modules.

`_fixture_error_code` reads the code out of the message and was written for
exactly these exceptions, so the intent was never in doubt. Only the `except`
clause disagreed with it.

**It could not surface before a graded case existed.** Every replay path in
the suite until now supplied a fixture, because a case that needs one was
written alongside it. `MQC_EXE_UNI_113611` asserts the conversion directly, so
it no longer depends on somebody running a graded case with an empty store.



### 7.7 A connection belongs to one case

Added 2026-09-25. **`dispatch_case` already builds a fresh adapter per call**
(line 311), and `ConfiguredAdapter` constructs its client lazily on first
dispatch. So a run already opens one connection per case. It simply never
released any of them, which is the worst of both arrangements: the setup cost
of isolation without the isolation, and a pool per case accumulating for the
length of the run.

#### 7.7.1 Isolation is the reason, and it is worth its cost

The obvious argument for closing is that there is nothing to carry: A19 issues
one request per case with no loop, no follow-up turn and no clarification
exchange. **That is true and it is the weaker argument.**

**The real reason is that a connection is a shared mutable thing, and sharing
it across cases couples their outcomes.** A socket that wedges, a provider-side
session that starts misbehaving, or a client whose internal state goes strange
would otherwise be inherited by every case that followed. One connection per
case means such an event reports as **one** `QC_HARNESS_*` skip against the
case that met it, which is exactly the attribution the taxonomy is for. Shared,
the same event produces a cascade of failures attributable to nothing.

**The cost is real and it is small here.** A fresh connection means a TLS
handshake per case, on the order of a hundred milliseconds.

| | Per case |
|---|---|
| Handshake | roughly 0.1s |
| Deliberate pacing, `gemini` | **4.0s** (`config/engines.yaml`) |

The pacing exists because the free tier demands it, and it dwarfs the
handshake by a factor of forty. **A run is waiting anyway.** Paying under three
percent of an interval we are already spending on purpose, in exchange for
per-case fault isolation, is not a close call. It would be a different
calculation against an unpaced provider or a suite of thousands, which is
what the flag below is for.

#### 7.7.2 Released by default, kept only when asked

`--keep-connection` is a flag, absent by default, and **the default is the safe
one** in the sense `cmn_verdict_and_cli.md` section 7 means: an unconfigured
invocation releases what it opened, and isolation is not something a run has to
ask for.

| Invocation | After a response |
|---|---|
| Default | The client is released |
| `--keep-connection` | The client is retained for reuse |

**The flag exists because the tradeoff above has inputs that can change.** If
this grows into continuous evaluation, or runs against a provider needing no
pacing where the handshake stops being noise, reuse becomes the right answer.
The option is the seam for that, and it is opt-in because the case for reuse
has to be made by whoever knows their run, not assumed by this one.

#### 7.7.3 The judge never borrows the candidate's connection

The judge is a separate engine selection with its own model, and it is
frequently the **same provider** as the candidate, which is what makes sharing
tempting and wrong.

**Two reasons, and the second is the one that bites.** A shared client blurs
which call spent which part of a shared free-tier quota, and it makes the
judge's request physically adjacent to the candidate's in a way A19 spends
considerable effort making logically impossible. Isolation that holds in the
composed request and not in the transport is isolation on paper.

The isolation argument in 7.7.1 applies here at full strength rather than
partially: a candidate connection that has just carried adversarial content is
the **last** thing that should also carry the judgement of it.

So the judge dispatches through a `JudgeChannel`, which **constructs its own
adapter** rather than accepting one, paces itself, and releases on the same
rule. `MQC_EXE_UNI_113212` asserts that a channel built for the candidate's own
engine still holds a different adapter instance.

##### Why the channel lives in Tier 2 and hands out a callable

`JudgeBinding.invoke` is `Optional[Callable]` and Tier 3 knows nothing else
about it. **That is the seam, and it was already there**: neither tier imports
the other today, in either direction, and a factory returning a `JudgeBinding`
would have been the first breach.

| | Owns | Knows about the other |
|---|---|---|
| `execution.judge_channel` | The adapter, the pacing, the release | Nothing. It returns a callable |
| `evaluation.judge` | What a reply must satisfy | Nothing. It calls a callable |

The composition happens where both are already in scope, which is the runner.
**A tier boundary that survives because nobody needed to cross it is luck; one
that survives a feature that wanted to cross it is a boundary.**

##### The judge is paced on its own budget

The channel carries its own `DispatchSession`. Judge calls were previously
unpaced, so a judged run issued the candidate request against a 4.0s interval
and the judge request against nothing, **into the same free-tier quota**. That
is a rate limit waiting for the first run long enough to reach it, and it is
why this is a precondition for any live recording rather than a refinement.

### 7.8 The adapter dispatches a judgement, because nothing else could

Added 2026-09-25, wiring the first production judge.

`JudgeBinding.invoke` is called with a `JudgeRequest` and its result goes
straight to `validate_judge_reply`, which expects **a mapping**. Every test
double returned one directly. **No adapter could produce one**: `compose_request`
takes an `EvaluationCase`, and a judge request is not a case.

So the judge worked in every test and could not have worked once.

#### 7.8.1 Every adapter declared it could judge

`declare_capabilities().structured_output` is what qualifies an engine to judge
(C2), and there is deliberately no list of permitted judge engines to keep in
step. All three adapters declared `structured_output=True`.

**None of them implemented it.** The capability was a label rather than an
obligation, which is the same failure mode as a rule nothing checks: the
declaration was read by `resolve_judge_engine` and satisfied by nothing.

#### 7.8.2 Two methods, added without breaking an implementation

Section 9 of `harness_extensibility_standard.md` permits a stable interface to gain an
**optional** parameter and never a required one. A new **abstract** method is
worse than a required parameter: it breaks every implementation at import.

So both arrive as **concrete** methods on `ProviderAdapter` with a default
body, which is additive by construction:

| Method | Default body |
|---|---|
| `compose_judgement(prompt, reply_schema)` | Refuses with `QC_HARNESS_PREFLIGHT_FAILURE` |
| `parse_judgement(response)` | Refuses the same way |

**The default refuses rather than approximating.** A plausible fallback
suggests itself: ask for JSON in plain text and parse whatever comes back. It
is rejected because C2 makes structured output mandatory for the judge
precisely so that **schema validation doubles as the hijack detector**. A text
fallback would satisfy the call and quietly remove the security control, which
is the worse outcome of the two by a wide margin.

#### 7.8.3 The declaration becomes an obligation the conformance suite enforces

The refusal above is only visible if something looks for it. The conformance
suite is parametrized over the registry, so it already enrols every adapter
automatically:

> An adapter declaring `structured_output` must compose a judgement carrying
> its reply schema, and must parse a provider reply into a mapping.

`MQC_EXE_UNI_113116` asserts it. **An adapter may still decline to judge** by
declaring `structured_output=False`, which costs it only the judge role and
excludes it from the check. What it may no longer do is claim the capability
and not have it.

#### 7.8.4 The binding is composed at the runner, not in a tier

`evaluation/` and `execution/` import each other in neither direction (section
7.7.3), so neither can hold a factory returning a `JudgeBinding`. Tier 2
supplies `judge_channel_from_roster`, which reads the roster, resolves the
judge engine through the existing `cmn/config.py` path and returns a
`JudgeChannel`. Binding it is one line where both are already in scope:

```
JudgeBinding(invoke=channel.invoke, judge_engine=channel.engine,
             candidate_engine=engine)
```

**The candidate engine is passed in rather than inferred**, because it is what
makes `shares_provider` a comparison rather than a guess, and under the
zero-cost configuration the two are routinely equal (A3).


### 7.9 The channel honours `--judge-mode`, or replay spends judge quota

Added 2026-09-25, wiring the channel to the machinery that was waiting for it.

`JudgementKey`, `load_judgement` and `record_judgement` have existed since the
judge fixtures were specified, and `resolve_judge_mode` has defaulted
`--judge-mode` to `--mode` since section 5A.5. **Nothing joined them to a
channel**, so `JudgeChannel.invoke` dispatched live whatever the run asked for.

**That is not a missing feature, it is a quota leak.** `FixtureKey` keys the
candidate only, so a bound judge is a live call whatever `--mode` says. A
replay run that judged would spend provider quota on every pull request, which
is precisely the hazard `consumer_ci.md` section 6.4 records as open.

| `--mode` | `--judge-mode` | The channel |
|---|---|---|
| replay | replay | Loads a stored judgement. **Never dispatches** |
| replay | live | Dispatches, and may record |
| live | live | Dispatches, and records when asked |
| live | replay | Refused at argument parsing (5A.5.1) |

#### 7.9.1 A missing judgement is a skip, never a live call

`load_judgement` raises rather than returning anything a caller could mistake
for a score, and the channel does not catch it to fall back. **The fail-open
path does not exist to be taken by accident**: a replay run missing a
judgement reports `QC_HARNESS_FIXTURE_MISSING` and records a skip, which is
cheap and visible, where a silent live call is expensive and is not.

#### 7.9.2 The hash covers the composed request, which carries the candidate

Hashing the composed provider request rather than the rubric means a stored
judgement is bound to **the exact text it scored**. A judgement is a score of a
specific response, and replaying one against different candidate output answers
a question nobody asked.

`MQC_EXE_UNI_113300` asserts that a replay channel never reaches the adapter,
and `MQC_EXE_UNI_113301` that a live one records what it obtained.


#### 7.9.3 The key separates candidate engines, because the hash only detects that it did not

Added 2026-10-01, after recording a second candidate engine destroyed the first
one's stored judgements.

`JudgementKey` was `(case_id, judge_engine, observation_index)`, and its
docstring argued the judge engine belongs in the key because a judgement is a
measurement and which instrument made it is part of its identity. That is true
and it is half the identity. **A judgement is a measurement of something**, and
what was measured is the other half: one judge scoring two candidates produces
two judgements, exactly as two judges scoring one candidate do.

Candidate fixtures were already separated, `replay/<engine>/<task>/...` per
engine. Judgements were not, so `replay/judgements/gemini/<task>/<rule>/0.json`
named a file both the gemini run and the openai run wrote.

| | Candidate fixture | Judgement fixture, before | Judgement fixture, after |
|---|---|---|---|
| Candidate engine in the path | Yes | **No** | Yes |
| Judge engine in the path | Not applicable | Yes | Yes |
| Recording a second engine | Writes beside the first | **Overwrites it** | Writes beside it |

**What it cost.** Recording `gpt-4.1` replaced 96 gemini judgements in place.
The gemini replay then reported ten failures where it had reported two, and
thirty dependent cases skipped on `QC_HARNESS_DEPENDENCY_UNMET` behind stale
foundations. Nine of the ten failures were `QC_HARNESS_FIXTURE_STALE`, which is
the correct code: the stored judgement answered a different question.

**The hash is the second mechanism and it held.** Section 7.9.2 binds a stored
judgement to the exact text it scored, so the overwritten files were refused
rather than read as scores for the wrong response. That is the difference
between losing data and publishing a wrong result, and it is why the failure
was loud. It is not a substitute for the key: a guard that detects a collision
after it has destroyed the data it was guarding has prevented the wrong answer
and not the loss.

**Why the collision was invisible until a second engine existed.** Under the
zero-cost configuration the candidate and the judge are routinely the same
engine (A3), so `judgements/gemini/` held gemini-judged gemini output and the
missing dimension was constant. The project ran one candidate engine for its
whole life until this session. A key that is correct for every value a field has
so far taken is not a correct key, and nothing distinguishes the two states from
inside a single-engine run.

**The path gains one level**, candidate engine above judge engine:

```
replay/judgements/<candidate_engine>/<judge_engine>/<task>/<rule>/<index>.json
```

Candidate first, because that is the order the rest of the tree already reads:
`replay/<candidate_engine>/...` for candidates, so a reader looking for
everything one engine produced finds it under one name in both subtrees.

`MQC_CMN_UNI_112615` asserts that two candidate engines judged by one judge
occupy two files. It fails against the old key by reading back the first
judgement and finding the second, which is the shape the defect had.


### 7.10 A recording run that repeats itself does not converge

Added 2026-09-26, building the first corpus under a rate limit.

`--mode live` dispatches every observation and records every response, which is
right for the question it answers: what is true today. **It is wrong for
building a corpus**, and under a rate limit it actively fights it.

A4.1 raised the security corpus to 27 observations. One run recorded nine and
was rate limited out of the rest. **Running it again would dispatch all 27**,
spending the scarce quota re-recording nine observations that already existed,
and replacing good samples with equivalent ones.

| | Requests | Outcome |
|---|---|---|
| Re-running `--mode live` | 27 | Nine spent replacing what was already there |
| `--mode live --fill-gaps` | **18** | Only what is missing |

**It converges either way**, because a fixture once written is only ever
replaced and never deleted, so the set of recorded observations grows. What
`--fill-gaps` changes is how much quota the convergence costs, and quota is the
binding constraint on every recording run this project will do.

#### 7.10.1 Why it is a flag and not the default

`--mode live` means call the provider, and a run asking what a model says today
should not silently answer from a file recorded last week. **The two intents are
different questions**, and conflating them would make the mode that spends
money the mode that sometimes does not.

| Invocation | Asks |
|---|---|
| `--mode live` | What does the model say now |
| `--mode live --fill-gaps` | Complete the corpus, and spend nothing on what is done |
| `--mode replay` | What did it say when recorded |

#### 7.10.2 A gap is an absent or stale fixture, not merely an absent file

`--fill-gaps` replays an observation whose fixture loads **and matches the
request hash and model**. A stale fixture is a gap: the question or the
instrument moved, so what is stored answers something else and dispatching is
exactly right.

That reuses `load_judgement`'s own distinction rather than restating it, so a
gap means the same thing here as everywhere else.

`MQC_EXE_UNI_113213` asserts that a recorded observation is not dispatched again
and a stale one is.


#### 7.10.3 The judge half, added 2026-09-29

**`--fill-gaps` reached the candidate and stopped there.** `DispatchPlan` has
carried it since section 7.10 was written; `JudgementPlan` did not, so
judgements stayed all or nothing.

**What that cost.** Correcting eight corpus assertions unblocked observations
that a false positive had aborted before the judge ran, which left two
judgements missing. Obtaining them meant `--judge-mode live` over all
ninety-two, because narrowing the selection with `-k` breaks the dependency
graph and collects nothing. Two judgements, twice, for roughly 0.90 USD against
about 0.01 of actual work.

**The rule is the candidate's, unchanged.** A judgement that loads cleanly is
returned; a stale one is a gap, because the rubric or the response moved and
what is stored answers a different question. `MQC_EXE_UNI_113305` holds both
halves, including the stale case, since a fill that reused a judgement recorded
against another rubric would be worse than no fill at all.

**It does not weaken section 7.9.1.** That rule is about `--mode replay`, which
a pull request runs and which still refuses with nothing to replay from. This
branch is reachable only when a live judge was asked for explicitly, which is
the same condition under which the candidate path already fills.

**Why this shape recurs.** A corpus gains gaps in normal use, not only in
disaster: a corrected assertion, a new rule, a rubric gaining a criterion, or a
foundational case that starts passing and reveals dependents that were never
recorded because they were skipped. Each of those is a handful of fixtures
against a corpus of hundreds.

### 7.11 A retry gets its own connection

Added 2026-09-26. Section 7.7 gave each **case** its own connection, on the
grounds that a shared one couples outcomes. The retry loop inside a case kept
reusing one.

**A failed attempt can leave the connection worse than it found it.** A
half-open socket, a stuck HTTP/2 stream, or a pool entry pinned to a backend
instance that just returned 503 is a state every subsequent attempt on that
connection inherits. Retrying on it asks the same unhealthy path the same
question.

So the adapter is released between attempts, and each attempt dispatches on a
connection it opened itself. This is the argument of section 7.7 applied one
level down: **isolation between cases and isolation between attempts are the
same property at two scales.**

#### 7.11.1 What it does and does not fix

**This acts at the connection level and therefore fixes connection-level
failures.** Section 8.6 names the levels, and the classification answers the
question by construction rather than failure by failure:

| Level | Does a new connection help |
|---|---|
| Connection: a wedged socket or stuck stream | **Yes.** That is the state being discarded |
| Path: a gateway | **Plausibly.** A new connection may be routed elsewhere |
| Service: one unhealthy instance | **Plausibly.** An instance is not the fleet |
| **Environmental: a rate limit** | **No.** A quota is keyed to the account, and a new socket presents the same credential |

**A rate limit is a different diagnosis at a different level, so it has a
different remedy and its own documented failure.** This change was not adopted
to fix it and does not: it is neutral there, and correct at the level it acts
on. A change that helps at its own level and is harmless elsewhere does not need
to claim more.

#### 7.11.2 The cost is inside the backoff it already waits out

A handshake is roughly 0.1s, and it happens after `backoff_sec * 2 ** (attempt
- 1)`, which starts at the configured base and doubles. **The attempt is
already waiting**, so the connection is rebuilt during time the run was
spending anyway.

`MQC_EXE_UNI_113214` asserts the release happens between attempts and not only
at the end of the case.


---

## 8. Rate Limiting

The objective is evaluation, never load-testing a provider. On a free tier, pacing decides whether a run completes at all (A7.3).

| Control | Behaviour |
|---|---|
| Request spacing | Per engine, from `config/engines.yaml` |
| Retry | Bounded backoff on `QC_HARNESS_CANDIDATE_TIMEOUT`, and on `QC_HARNESS_RATE_LIMIT` **unless the provider named an exhausted quota period** (section 8.6.4) |
| Exhausted backoff | Skip the case, attach the code, continue |
| Circuit breaker | N consecutive failures, or any auth error, aborts the run |
| Diagnostics | Rate-limit encounters counted and reported, never absorbed silently by retry |

**Interaction with A4:** three observations per case triples request volume against the same ceiling. Spacing and observation count are configured together, not independently.

**Replay mode applies no spacing** and consumes no quota, which is why the deterministic gates run identically on a pull request and on a schedule.


#### 7.8 The outcome carries the call that produced it

Added 2026-10-02. `_CaseContext.request` is the composed request, hashed for the
fixture store and discarded with the context.

`DispatchOutcome` now carries it, because **a finding is filed with the
provider** and a ticket needs the exact call rather than a description of it
(`cmn_verdict_and_cli.md` section 5.3).

**Retained on every outcome, attached only for a failing case.** A case's
verdict is not known while its observations are being taken, and the passing
observations of a failing case are exactly the ones its report needs, so a
record kept only on a failing call could not produce them. The request is
already in memory and the field is a reference, so retaining it costs nothing;
what costs artifact size is the attachment.

**It is serializable by construction.** `hash_request` already refuses a
request carrying a provider object, with the reasoning that such an object
should have stopped at the adapter, so what reaches this field is a structure a
report can carry.


### 8.1 What a dispatch returns

A dispatch produces an outcome rather than a response, because a skipped case is a result the run has to carry forward and an exception is not.

| Field | Type | Notes |
|---|---|---|
| `case_id` | `str` | Which case |
| `engine` | `str` | Which adapter |
| `mode` | `str` | `live` or `replay` |
| `response` | `Optional[NormalizedResponse]` | Absent exactly when the case was skipped |
| `taxonomy_code` | `Optional[str]` | The `QC_HARNESS_*` code, present exactly when `response` is absent |
| `duration_ms` | `int` | Measured by the dispatcher, per section 4.4 |
| `duration_kind` | `str` | `measured` or `truncated`, per `harness_test_taxonomy.md` section 9.3 |
| `attempts` | `int` | How many requests were issued, so a retried case is visible |
| `rate_limit_encounters` | `int` | Counted per case and summed per run (section 8) |

**`response` and `taxonomy_code` are mutually exclusive, and one is always present.** A record carrying both would leave downstream code to decide which it believed; a record carrying neither would be a case that neither produced a measurement nor said why.

**On a timeout the duration is `truncated`.** It records how long the harness waited, not how long the model took, and the two must not be averaged together (`harness_test_taxonomy.md` section 9.3).

**A run carries two records, not one.** `DispatchPlan` is fixed for the run: mode, fixture root, model and whether to record. `DispatchSession` is consumed by it: the clock, the spacing interval, the failure streak and the counters. Holding both in one mutable record would put the mode next to a counter that changes on every case, and a caller wanting to know how a run was configured would have to read a record that had been mutated since.

### 8.2 The clock and the delay are injected

The dispatcher takes its monotonic clock and its sleep as parameters with real defaults.

Without that, asserting that spacing is honoured at its configured interval means a test that actually waits, and asserting a bounded backoff means a test that waits repeatedly. A precondition suite that sleeps is a precondition suite people start skipping.

This is the same argument that makes the verdict a pure function of an injected date (`cmn_verdict_and_cli.md` section 2): **the behaviour under test is the decision, and the decision is separable from the waiting.**

### 8.3 The circuit breaker counts consecutively, and an auth error ignores the count

| Trigger | Behaviour |
|---|---|
| N **consecutive** case failures | Abort the run |
| Any `QC_HARNESS_AUTH_ERROR` | Abort immediately, whatever the count |

**Consecutive rather than cumulative**, because a long run against a flaky provider legitimately accumulates scattered failures while still producing a usable measurement. A consecutive streak means the provider stopped answering, and every further request spends quota to confirm it.

**An auth error is categorically different from a failed request.** It will not resolve by waiting, every subsequent case will fail identically, and the run cannot produce a measurement. Waiting for a streak to accumulate would issue N requests that were all going to fail.

---

### 8.5 A busy provider is not a parser error

Added 2026-09-25, found by the first live run the project ever made. Nothing
short of a real provider would have produced it.

Three of nine security cases came back with:

```
503 UNAVAILABLE. This model is currently experiencing high demand.
Spikes in demand are usually temporary. Please try again later.
```

**The status map covered 401, 403, 404 and 429 and nothing in the 5xx family**,
so a 503 fell through to `QC_HARNESS_PARSER_ERROR`, which is the code for a
failure nobody anticipated. Two things followed, and the second is the
expensive one:

| Consequence | Why it matters |
|---|---|
| The artifact said the response could not be parsed | It parsed fine. There was no response |
| **It was not retried** | `QC_HARNESS_PARSER_ERROR` is not retryable, and correctly so |

The provider said the condition was temporary and the harness had backoff
machinery ready, and the two never met.

#### 8.5.1 It is its own code, not a rate limit

`QC_HARNESS_RATE_LIMIT` is the tempting reuse and it is wrong.
`rate_limit_encounters` is **counted and reported across the run**, and the two
conditions call for different responses from whoever reads that number:

| | Says | Operator response |
|---|---|---|
| `QC_HARNESS_RATE_LIMIT` | You asked too often, **or your allowance for the period is spent** | Widen `spacing_sec`, or wait for the reset (section 8.6.4 separates them) |
| `QC_HARNESS_PROVIDER_UNAVAILABLE` | The provider is busy | Wait, and nothing on our side changes |

Folding one into the other would make a provider's bad afternoon look like a
pacing defect, and the obvious fix, pacing the run more slowly, would not help.

#### 8.5.2 The whole transient family, not one status

`500`, `502`, `503` and `504` all map to it. Mapping only the status that
happened to occur would leave the next one to be discovered the same way, on a
run that spends quota to find it.

**They are retryable**, joining rate limits and timeouts as the third member of
that set: all three are conditions where the same request later plausibly
succeeds, which is the only thing that makes a retry worth its quota.

`MQC_EXE_UNI_113118` asserts the mapping across every registered adapter, and
`113119` that the code is retried rather than reported once.


#### 8.5.3 The status says whose defect it is, and what to do about it

Extended 2026-09-25. Section 8.5 closed the 5xx family; the 4xx family needed
the same treatment, and **400 was the one still falling through**.

Every status is mapped to the operator response it calls for, because that is
the only thing the reader of an artifact actually needs from it:

| Status | Code | Whose defect | Retry | What to do |
|---|---|---|---|---|
| `400` | `QC_HARNESS_REQUEST_REJECTED` | **Ours** | No | Fix how the request is composed |
| `401` | `QC_HARNESS_AUTH_ERROR` | Ours | No | Fix the credential |
| `402` | `QC_HARNESS_CREDIT_EXHAUSTED` | **Environmental** | No | Add credit. **The credential is valid**, which is why this is not the auth code |
| `403` | `QC_HARNESS_AUTH_ERROR` | Ours | No | Fix the credential or its grants |
| `404` | `QC_HARNESS_VERSION_UNAVAILABLE` | Ours | No | Fix the model name (A3.1) |
| `429` | `QC_HARNESS_RATE_LIMIT` | **Neither** | **Conditional** | Widen `spacing_sec` for a per-minute rate; wait for the reset where the period is spent (section 8.6.4) |
| `5xx` | `QC_HARNESS_PROVIDER_UNAVAILABLE` | **Theirs** | Yes | Wait |

**400 gets its own code rather than the catch-all.** Mapping it to
`QC_HARNESS_PARSER_ERROR` would have been one line and would have destroyed
the property that code exists for: it means *nobody anticipated this*, and an
artifact carrying it should send a reader looking for something new. A
malformed request is anticipated, diagnosable and entirely ours, so folding it
in would make every genuinely unknown failure harder to find.

**It is not retryable**, for the reason the retry set already gives: the same
malformed request gets the same answer, and spending quota to confirm that is
the definition of a wasted retry.

##### 429 is the one that is nobody's defect, and it has a sharp edge

A rate limit means the request was well formed, authorised and addressed to a
model that exists. Nothing is wrong; we simply asked too often. That is why it
is retryable and why `rate_limit_encounters` is **counted and reported rather
than absorbed**: a run that completes after twelve rate limits is telling the
operator to widen `spacing_sec` before the next one.

**The edge: a provider may return 429 for a per-minute rate and for an
exhausted daily quota, and they are the same status.** Retrying a per-minute
limit works, and retrying an exhausted daily quota cannot: no backoff inside a
run reaches tomorrow.

The harness is **bounded rather than clever** here. Each case exhausts
`max_attempts` with backoff, every attempt increments the counter, and the
circuit breaker trips on the consecutive-failure streak, so an exhausted daily
quota costs a bounded number of futile requests and then stops the run.
Distinguishing the two would mean parsing a provider's prose, which changes
without notice and differs per vendor, and guessing wrong in the optimistic
direction would burn the next day's quota as well.

**What makes that acceptable is the counter.** A run that trips the breaker
with a high `rate_limit_encounters` and no successes reads unmistakably as
quota exhaustion rather than as a model problem.


#### 8.5.4 A gateway failure is not the provider saying it is busy

Extended 2026-09-25. Section 8.5 folded the whole 5xx family into one code,
and two of those statuses do not mean what the code says.

**`502` and `504` come from a gateway**, which may be a load balancer, a CDN,
a corporate proxy or a VPN egress, and need not be the provider at all. The
tell is in the payload: **the body of a 502 is the intermediary's, not the
provider's**, so a diagnostic read out of it describes something other than the
service we called.

| Status | Who said it | What it means |
|---|---|---|
| `500` | The service | It failed while handling the request |
| `503` | The service | It is overloaded or down, deliberately |
| **`502`** | **A gateway** | It could not reach, or got a bad answer from, whatever is behind it |
| **`504`** | **A gateway** | Whatever is behind it did not answer in time |

##### The operator response differs, which is the whole test

`QC_HARNESS_PROVIDER_UNAVAILABLE` tells a reader to wait, and that is right
when the provider said so. **Told the same thing about a 502 from a misbehaving
corporate proxy, a reader waits for a condition that will never clear**, when
they should be looking at the path: the proxy, the egress rules, the DNS, the
VPN.

That is the same test section 8.5.1 applied to separate a rate limit from a
busy provider, and it gives the same answer here.

##### Both stay retryable, and for different reasons

A gateway failure is frequently momentary, so a retry is worth its quota. What
changes is what an operator does when the retries are exhausted, which is
exactly what a taxonomy code is for.

##### The status is read from the exception, which every SDK exposes

`502` and `504` are indistinguishable by exception class: the OpenAI and
Anthropic SDKs raise `InternalServerError` for everything at or above 500, and
carry the number in `status_code`. The Gen AI SDK carries it in `code`.

So the shared lookup consults a **status table first and a class table
second**, the status being the more specific of the two. Gemini, which always
mapped by status, and the SDK protocols, which mapped by class, now express the
same thing through one mechanism rather than two.

`MQC_EXE_UNI_113121` asserts the split across every registered adapter.


#### 8.5.5 A redirect means we are not talking to the engine we addressed

Extended 2026-09-25. **No 3xx status was mapped at all**, so a redirect landed
on the code reserved for failures nobody anticipated.

A redirect reaching an adapter as an error is neither a model finding nor a
judge finding. **It says the engine was not where we addressed it**, and the
client did not follow the hop.

| Status | Says |
|---|---|
| `300` | Several representations, and the request did not choose |
| `301`, `308` | The endpoint moved permanently |
| `302`, `303`, `307` | The endpoint is elsewhere for now |
| `305` | Go through a proxy |
| `306` | Reserved, and should not be emitted at all |

**The common cause is not the provider.** A corporate proxy, a captive portal
or an SSO gateway answering `302` with a login page is the ordinary way this
happens, and the body is then HTML. **Following such a hop blindly is how a
login page gets scored as a model response**, which is the outcome this code
exists to make impossible to mistake for anything else.

##### A connection failure is the same condition, and one was mis-filed

`APIConnectionError` was mapped to `QC_HARNESS_PROVIDER_UNAVAILABLE` when the
transient family was added, which says **the provider reported itself busy**.
It reported nothing; we never reached it. That is the same error 8.5.4
corrected for `502`, made in the same change, and it is corrected here.

##### Not retryable, and the reason differs per cause

| Cause | Why a retry is waste |
|---|---|
| A redirect | Deterministic. The same request gets the same hop |
| A connection failure | **Both SDKs retry internally** before surfacing one, so what reaches us has already been retried |

#### 8.5.6 One status table, several interfaces

**What an HTTP status means is a property of HTTP, not of a vendor.** A `302`
says the same thing whoever returned it, so the mapping is one table in
`cmn/registries.py`, reached through `taxonomy_for_status`, and every interface
that needs it calls that one function.

This replaced three copies. The first implementation put a status table in each
adapter, which was three places for one fact and the exact shape
`consumer_ci.md` section 5 calls a defect that ships: **a rule enforced
differently in two places**.

| Owns | What |
|---|---|
| The shared table | What a status number means |
| An adapter | Which attribute carries the status, and which exception class its SDK raises for a **non-HTTP** failure such as a timeout |

An adapter no longer states that `404` means an unavailable version. It states
only what is genuinely its own, which for the Gen AI SDK is a `httpx` timeout
and a connect error, and for the SDK protocols is their typed exception
classes.

**`None` rather than a default for an unmapped status**, so an unrecognised
number falls through to the caller's unanticipated-failure path and stays
visible, which is the property `QC_HARNESS_PARSER_ERROR` exists to preserve.

#### 8.5.7 The judge reaches the same table, and could not report anything

`JudgeChannel.invoke` called the adapter and mapped nothing, and the pipeline
caught only `JudgeHijackSuspected` and `ValueError`. **Every provider failure
during judging escaped as a raw SDK exception**, so a busy provider that the
candidate path handles as a retryable skip crashed a judged case outright.

The channel now maps through `map_error`, which is the same method and
therefore the same table the candidate path uses, and raises a `ValueError`
carrying the code. The pipeline already records that as `judge_reply_unusable`,
so a harness event on the judge path is a skip with a code, as it is
everywhere else.

**The hijack exception is deliberately not named there.** It is raised by
`validate_judge_reply` in Tier 3 after the channel returns, and naming it would
make `execution/` import `evaluation/`, which neither tier does in either
direction (section 7.7.3).


### 8.6 Every failure has a level, and the level decides the remedy

Added 2026-09-26. The codes accumulated one at a time, each from a real
failure, and the set was documented as a flat list of statuses. **The list has
an organising principle and stating it makes the set predictable rather than
merely complete.**

A failure lives at exactly one level, and the level is what a remedy acts on:

| Level | Codes | What a remedy changes | Retry |
|---|---|---|---|
| **Ours** | `QC_HARNESS_REQUEST_REJECTED` | The request we compose | No |
| **Connection** | (transport failures, before a status) | The socket. **Reconnect** | Per attempt |
| **Path** | `QC_HARNESS_GATEWAY_FAILURE`, `QC_HARNESS_ENGINE_UNREACHABLE` | Proxy, DNS, egress, endpoint | Gateway yes, redirect no |
| **Service** | `QC_HARNESS_PROVIDER_UNAVAILABLE` | Nothing on our side. Wait | Yes |
| **Environmental** | `QC_HARNESS_RATE_LIMIT`, `QC_HARNESS_AUTH_ERROR`, `QC_HARNESS_VERSION_UNAVAILABLE` | The account, the credential, the configuration | Rate limit **only where the period is not spent** (section 8.6.4), the others no |

#### 8.6.1 The level is why reconnecting is not a general remedy

Section 7.11 opens a fresh connection per retry attempt. **That acts at the
connection level and therefore fixes connection-level failures**, and asking
whether it helps a `429` is asking whether a new socket changes an account's
quota. It does not, and the question answers itself once the level is named.

The earlier version of 7.11.1 reasoned failure by failure about whether a new
connection would help, which reached the right answers by inspection.
**Naming the level reaches them by construction**, which is what makes the next
code's classification obvious instead of a judgement call.


##### The two remedies inside the environmental level

A `429` is environmental, and **the level names what to change, not which
change.** Within it, two conditions share the status and differ in remedy:

| Condition | Provider says | Remedy |
|---|---|---|
| A per-minute rate | Usually names the rate or the metric | Widen `spacing_sec` |
| A plan quota | "exceeded your current quota, check your plan and billing" | Wait for the reset, or raise the tier |
| **No credit** | "you have no credits remaining", `insufficient_quota` | **Add credit.** Nothing else reaches it |

The third was found the same day as the other two, on a second provider: a
credential that authenticated against 126 models and could call none of them.
**An authenticated key is not a funded one**, and a subscription to a vendor's
consumer product funds nothing on its API.

**Pacing does not touch the second, and a run proves it in one attempt.** This
project widened `spacing_sec` from 4.0 to 6.0 against observed 429s and recorded
**zero** additional observations, because the message was the second kind. The
value was reverted.

**Read the message before choosing the remedy.** The level narrows the search to
the environment; the provider's own words pick the action within it.

#### 8.6.2 A level is a different diagnosis, so it is a different documented failure

Two failures at different levels are not two flavours of one problem. A `429`
and a wedged socket both stop a request and have nothing else in common: one is
answered by waiting or by raising a tier, the other by discarding a socket, and
**a reader told the wrong one acts on the wrong thing.**

This is the same reasoning that split `502` from `503` in section 8.5.4 and a
rate limit from a busy provider in 8.5.1, applied to the set as a whole rather
than to one pair at a time.

#### 8.6.3 Where the remedies are written down

The codes are registered in `harness_test_taxonomy.md` section 6 and the operator
response for each is in `harness_running_jobs.md` section 6.1, which this section
organises rather than restates. **`QC_HARNESS_*` remains a skip at every
level**: a harness event says our infrastructure produced no measurement, and
no level of it is a finding about a model.


#### 8.6.4 A rate limit carries a period, and the period decides whether to retry

Added 2026-09-26 from a measurement, after a recording run stalled at nineteen
fixtures and three further runs added none.

Section 8.5 listed `QC_HARNESS_RATE_LIMIT` as retryable, which is right for one
of the three conditions a 429 carries and wrong for the other two. **The status
does not say which condition it is; the provider's body does.**

##### What the provider actually said

Asked directly, Gemini named the quota:

| Field | Value |
|---|---|
| `quotaId` | `GenerateRequestsPerDayPerProjectPerModel-FreeTier` |
| `quotaValue` | `20` |
| `retryDelay` | `52s` |

**Twenty requests per day, per model.** Nineteen fixtures was not a symptom of
pacing; it was the allowance, spent. The `spacing_sec` experiment recorded in
section 8.4 failed for exactly this reason: it was a remedy at the run level for
a failure at the environmental level.

##### The provider's own retry hint is wrong here

`retryDelay` says 52 seconds beside a quota that resets once a day. **Anything
honouring that hint retries until the day turns.** Nothing in this harness reads
it, and `period_quota_exhausted` is documented so that nothing starts.

##### Which level, and therefore which remedy

| Condition | Level | Remedy | Retry? |
|---|---|---|---|
| Per-minute rate | Run | Widen `spacing_sec` | **Yes** — it clears on its own |
| Per-day or per-month allowance | Environmental | Wait for the reset, or raise the tier | **No** |
| No credit on the account | Environmental | Add credit | **No** |

So the retry survives for the condition it was written for and is abandoned for
the two it never addressed. `_AttemptTally.period_exhausted` records which one
happened, because three rate limits look identical in a count whether the
allowance returns in seconds or at midnight.

##### The shared status, the vendor-specific condition

This follows the split section 8.5.6 already holds. **What a 429 means is a
property of HTTP**, so it is read from one table. **Which quota was exceeded is
a property of the vendor**, so the shared code asks
`period_quota_exhausted` and each adapter answers from its own body shape.

**It fails open, deliberately.** An adapter that cannot tell returns `False` and
keeps the retry. Unknown must not become "give up": that would trade away the
recoverable condition in order to handle the unrecoverable one.

##### What this costs the recording plan

Twenty requests per day per model is the constraint, and A4.1 asks for three
observations per case:

| | Requests | Days at 20/day |
|---|---|---|
| Security family, 21 cases | 63 | 4 |
| Every family currently authored | ~200 | 10 |

**This is a planning fact, not a defect**, and it is recorded here because the
alternative is rediscovering it as a run that appears to hang. A paid tier
removes it; until then live recording is a multi-day activity and `--fill-gaps`
is what makes it resumable.

#### 8.6.5 402 is the balance, not the credential

Added 2026-09-28, the day the project first held prepaid credit.

**Until there was money, this status could not occur.** A free-tier key returns
429 when its allowance is spent; a paid key with an empty balance returns **402**,
and Gemini stops every key on the billing account at once when prepay credit
reaches zero.

It fell through to `QC_HARNESS_PARSER_ERROR`, the catch-all. So at the moment the
true cause was "the balance is empty", a run would have reported that it could not
parse something.

| | 401 | 402 |
|---|---|---|
| The credential | Rejected | **Valid** |
| The remedy | A new key | **Money** |
| Level | Ours | Environmental |
| Retryable | No | No |

**Not folded into the auth code**, because the remedies do not overlap and the
wrong one wastes the most time: rotating a working key while the account is empty
changes nothing and looks like it should. `.env.example` already draws the same
distinction in prose, and this makes it a code.

**Environmental, like the no-credit variant of 429** (section 8.6), so nothing
retries it: no wait a run can afford produces funds.


#### 8.6.5 The session reports the models it served

Added 2026-10-02. The resolved model reached `record_spend`, was priced with and
dropped; `unpriced` kept only the ones it could not price.

`served` records every model the session saw, which answers "what did this run
run against" without a caller re-deriving it from observations. The quarantine
tool needs it to stamp an entry with the model a re-observation measured
(`cmn_verdict_and_cli.md` section 4.6.10), and the question is general enough
that the session is the right place for it.

**Recorded in `note_outcome`, not in `record_spend`.** The first attempt hooked
spending, and a replayed response never reaches it: the tool then stamped an
empty model from a replay while the fixture it replayed names one. Every
outcome reaches `note_outcome` in either mode, which is what this needs.

**A replay is included, not exempt**, which is the rule `mixed_model_engines`
already states for the same reason: fixtures carry the model that produced them,
so a replay does answer what it ran against.

**It is a set, so two entries mean a mixed corpus**, the same condition
`mixed_model_engines` reports from the other direction.


## 9. Conformance Suite

Per `harness_extensibility_standard.md` section 10, registration enrols an adapter automatically. The battery asserts:

1. `compose_request` produces a valid request from a minimal case.
2. `normalize_response` returns the canonical shape with every required field populated.
3. `extract_tool_calls` returns parsed argument mappings, never JSON strings.
4. A tool call is captured and **not executed**.
5. `resolve_model_version` returns the provider's value, not the request's.
6. Each provider error class maps to its `QC_HARNESS_*` code.
7. An unrecognised error maps to `QC_HARNESS_PARSER_ERROR` and preserves the original.
8. Declared capabilities match observed behaviour.
9. No vendor type appears in the normalized output.

Passing this is **necessary and not sufficient** (standard section 11). Each adapter additionally ships its own unit tests covering its provider's specific quirks.

### 9.1 The battery asserts over the registry, which is a different claim

Four of the nine assertions restate a property already inventoried against the canonical record: arguments are parsed (`113401`, `113402`), the resolved version is recorded (`113406`), and no vendor type survives (`113408`). Those cases construct the record directly and prove the record is well formed.

**The battery proves something the record-level cases cannot:** that every registered adapter produces such a record. A record-level case passes while an adapter that never builds one correctly sits in the registry untested, which is precisely the gap automatic enrolment exists to close.

They are therefore separate inventory rows rather than a reuse of the same identifier. An identifier names one behaviour, and "the canonical record rejects a JSON string" and "no registered adapter emits one" are two. Reusing the identifier would also make a parametrized battery report N results under a row the inventory counts once.

| §9 assertion | Inventory row |
|---|---|
| 1. Composes a valid request | `113100`, `113101` |
| 2. Normalizes to the canonical shape | `113102` |
| 3. Arguments are mappings, never JSON strings | `113110` |
| 4. A tool call is captured, not executed | `113103` |
| 5. The version comes from the response | `113111` |
| 6. Each provider error class maps to its code | `113104`, `113105`, `113106` |
| 7. An unrecognised error is preserved | `113107` |
| 8. Declared capabilities match behaviour | `113108`, `113109` |
| 9. No vendor type survives normalization | `113112` |

---

## 10. Test Inventory

Ungraded preconditions, no priority. Categories: **P** positive, **N** negative, **B** boundary.

### 10.1 `MQC_EXE_UNI_`

| ID | Cat | Behaviour |
|---|---|---|
| `113100` | P | `composes_request_from_minimal_case` |
| `113101` | P | `composes_request_carrying_constraints_and_context` |
| `113102` | P | `normalizes_response_to_canonical_shape` |
| `113400` | N | `rejects_response_missing_required_canonical_field` |
| `113401` | P | `parses_tool_arguments_supplied_as_json_string` |
| `113402` | P | `parses_tool_arguments_supplied_as_object` |
| `113403` | N | `malformed_tool_arguments_map_to_model_finding_not_harness` |
| `113103` | P | `captures_tool_call_without_executing_it` |
| `113404` | B | `returns_empty_tool_call_list_when_none_present` |
| `113405` | P | `preserves_tool_call_sequence_order` |
| `113406` | P | `records_resolved_model_version_not_requested` |
| `113500` | N | `absent_model_version_fails_preflight` |
| `113407` | P | `records_both_when_resolved_differs_from_requested` |
| `113104` | P | `maps_rate_limit_error_to_harness_code` |
| `113105` | P | `maps_timeout_error_to_harness_code` |
| `113106` | P | `maps_auth_error_to_harness_code` |
| `113107` | N | `unrecognised_error_preserves_original_text` |
| `113408` | N | `no_vendor_type_appears_in_normalized_output` |
| `113108` | P | `declared_capabilities_derive_unsupported_pairs` |
| `113109` | N | `tool_case_against_engine_without_tool_calling_is_unsupported` |
| `113600` | P | `replay_reproduces_all_three_recorded_observations` |
| `113601` | N | `replay_of_single_response_thrice_is_rejected` |
| `113602` | N | `changed_request_hash_reports_fixture_stale` |
| `113603` | N | `absent_fixture_reports_fixture_missing` |
| `113604` | P | `recorded_fixture_carries_resolved_model_version` |
| `113200` | P | `replay_mode_applies_no_request_spacing` |
| `113201` | B | `request_spacing_honoured_at_configured_interval` |
| `113202` | N | `exhausted_backoff_skips_case_with_rate_limit_code` |
| `113203` | N | `circuit_breaker_aborts_after_consecutive_failures` |
| `113204` | N | `auth_error_aborts_immediately` |
| `113205` | P | `rate_limit_encounters_are_counted_and_reported` |
| `113206` | N | `adapter_performs_no_scoring_or_interpretation` |
| `113207` | N | `candidate_timeout_maps_to_candidate_code_not_generic` |
| `113208` | P | `timeout_records_duration_kind_truncated` |
| `113501` | P | `unchanged_model_version_yields_no_dispatch` |
| `113502` | P | `changed_model_version_dispatches_only_the_changed_engine` |
| `113503` | B | `absent_baseline_is_recorded_rather_than_treated_as_a_change` |
| `113504` | N | `probe_failure_records_a_harness_event_and_does_not_dispatch` |
| `113605` | B | `divergent_refs_report_staleness_as_a_finding` |
| `113606` | P | `request_hash_is_identical_across_line_ending_conventions` |
| `113607` | N | `a_fixture_path_never_contains_the_case_id_separator` |
| `113409` | P | `call_id_is_optional_because_providers_differ` |
| `113410` | N | `mode_outside_the_registered_set_is_rejected` |
| `113411` | N | `finish_reason_outside_the_registered_set_is_rejected` |
| `113412` | P | `raw_reference_is_a_pointer_not_a_payload` |
| `113608` | P | `different_requests_hash_differently` |
| `113609` | N | `an_unserializable_request_names_the_boundary_it_crossed` |
| `113610` | N | `an_unreadable_fixture_reports_missing_not_stale` |
| `113505` | P | `a_resolved_version_is_returned_stripped` |
| `113506` | P | `a_change_dispatches_once_not_on_every_later_run` |
| `113507` | P | `a_failed_probe_leaves_its_baseline_untouched` |
| `113508` | N | `an_unreadable_baseline_is_reported_not_ignored` |
| `113509` | P | `probe_outcomes_are_returned_in_a_reproducible_order` |
| `113110` | P | `every_adapter_returns_tool_arguments_as_a_mapping` |
| `113111` | P | `every_adapter_reads_the_version_from_the_response` |
| `113112` | N | `no_vendor_type_survives_any_adapter_normalization` |
| `113113` | N | `registering_two_adapters_under_one_engine_name_fails` |
| `113114` | P | `the_registry_enrols_every_adapter_in_the_battery` |
| `113000` | P | `claude_maps_refusal_stop_reason_to_content_filter` |
| `113001` | P | `claude_concatenates_every_text_block_in_order` |
| `113002` | P | `openai_maps_the_superseded_tool_call_finish_reason` |
| `113003` | B | `openai_absent_tool_calls_field_yields_an_empty_list` |
| `113004` | P | `gemini_reads_the_resolved_version_from_its_own_field` |
| `113005` | P | `gemini_reconciles_a_stop_reason_carrying_captured_calls` |
| `113006` | N | `gemini_a_blocked_candidate_yields_empty_text_not_an_error` |
| `113007` | P | `gemini_disables_provider_side_automatic_function_calling` |
| `113008` | P | `gemini_maps_each_error_status_to_its_harness_code` |
| `113115` | N | `an_unregistered_engine_name_names_what_is_registered` |
| `113009` | P | `claude_sends_the_system_instruction_as_its_own_field` |
| `113010` | P | `openai_sends_the_system_instruction_as_a_message_role` |
| `113011` | P | `composed_request_states_effort_rather_than_inheriting_it` |
| `113012` | N | `composed_request_carries_no_field_the_model_rejects` |
| `113611` | N | `a_missing_fixture_becomes_a_skip_rather_than_an_error` |
| `113210` | N | `a_connection_left_open_after_a_response_is_reported` |
| `113211` | B | `keeping_the_connection_is_opt_in_and_recorded` |
| `113212` | N | `a_judge_sharing_the_candidate_adapter_is_reported` |
| `113116` | N | `a_declared_capability_that_cannot_judge_is_reported` |
| `113117` | P | `a_judgement_round_trips_through_the_adapter_to_a_mapping` |
| `113013` | P | `an_engine_on_a_shared_protocol_inherits_it_entire` |
| `113014` | N | `two_engines_on_one_protocol_do_not_share_a_credential` |
| `113015` | P | `a_role_is_derived_from_the_registry_not_a_list` |
| `113300` | N | `a_replay_judgement_never_reaches_the_provider` |
| `113301` | P | `a_live_judgement_is_recorded_for_later_replay` |
| `113118` | N | `a_transient_provider_failure_is_not_a_parser_error` |
| `113119` | P | `a_transient_provider_failure_is_retried` |
| `113120` | N | `a_rejected_request_is_not_an_unanticipated_failure` |
| `113121` | N | `a_gateway_failure_is_not_the_provider_being_busy` |
| `113122` | N | `a_redirect_or_connection_failure_is_unreachability` |
| `113123` | P | `every_interface_maps_a_status_through_one_table` |
| `113302` | N | `a_provider_failure_while_judging_is_contained` |
| `113303` | N | `the_judge_channel_imports_no_evaluation_module` |
| `113213` | P | `filling_gaps_dispatches_only_what_is_missing` |
| `113214` | P | `a_retry_attempt_opens_its_own_connection` |
| `113215` | N | `a_spent_quota_period_abandons_its_remaining_attempts` |
| `113216` | B | `a_rate_limit_of_unknown_period_keeps_its_retries` |
| `113016` | P | `gemini_reads_the_spent_period_from_the_quota_id` |
| `113017` | P | `every_adapter_reports_the_four_token_counts` |
| `113018` | B | `thinking_is_counted_only_where_reported_separately` |
| `113019` | B | `a_response_carrying_no_usage_reports_zero_not_an_error` |
| `113700` | N | `a_run_at_its_spend_ceiling_dispatches_nothing_further` |
| `113701` | P | `a_run_with_no_ceiling_is_unchanged` |
| `113702` | N | `a_ceiling_against_an_unpriced_model_stops_the_run` |
| `113703` | N | `an_empty_balance_is_its_own_code_not_an_auth_failure` |
| `113020` | P | `a_refused_prompt_is_recorded_with_its_reason_and_stage` |
| `113021` | N | `the_judgement_schema_drops_keywords_the_provider_rejects` |
| `113304` | N | `each_observation_records_its_own_judgement` |
| `113305` | N | `fill_gaps_judges_only_what_is_not_recorded` |
| `113022` | P | `a_claude_refusal_is_recorded_as_a_block` |
| `113217` | P | `an_outcome_carries_the_request_that_produced_it` |
| `113209` | N | `an_unregistered_mode_is_rejected_before_any_adapter` |

### 10.2 `MQC_EXE_SYS_`

| ID | Cat | Behaviour |
|---|---|---|
| `123000` | P | `dispatches_one_request_per_case_with_no_loop` |
| `123001` | P | `every_adapter_produces_identical_canonical_shape` |
| `123002` | P | `engine_selection_routes_to_declared_adapter` |
| `123003` | N | `unknown_engine_name_is_rejected` |
| `123004` | P | `mode_flag_selects_live_or_replay_independently_of_engine` |

**`123001` is marked foundational** (`@pytest.mark.base`). A provider-agnostic interface carrying only plain text proves nothing; one normalising three genuinely different tool-call and error shapes is a real abstraction, and this is where that claim is tested.

Its failure means the canonical shape does not hold across adapters, so every downstream evaluator result would be comparing responses that were never made comparable. Dependents do not execute.

**Inventory: 115 cases, 47 negative, 59 positive, 9 boundary.** Positive cases outnumber negative here, unlike Tier 1, because most of this module's work is transformation rather than rejection. The rejections that matter are concentrated in replay integrity and error mapping.

#### 10.1.1 The version probe

`113501` through `113504` cover the nightly probe specified in `harness_ci_pipeline.md` section 4. The probe resolves each engine's model version and decides whether a live run is warranted, which is decision logic and therefore testable rather than configuration.

**`113503` is the boundary that matters.** On a first run no baseline exists, and an absent baseline is not a change. Treating it as one would dispatch a live run for every engine the first time the probe executes, and again after any baseline reset, spending quota to discover nothing. The case is stated at the exact condition, per the boundary rule.

#### 10.1.2 Twelve counterweights and boundaries

`113409` through `113509` were designed after the first Tier 2 test run, and each guards a case the inventory's positives could not.

**`113608` is the counterweight `113606` needs.** A hash that ignored line endings by ignoring content would satisfy `113606` completely and be worthless. A normalization case without its counterweight asserts that two things are equal and never that anything is different.

**`113609` and `113508` are the same shape:** a value that cannot be read must be reported rather than absorbed. A corrupt version baseline silently read as empty is the worst outcome available, because the probe would then report every night that nothing changed while holding no record of what anything was.

**`113507` states what a failed probe must not do.** Overwriting a baseline with nothing would fake a change on the following run, turning one broken night into a spurious live run the next.

**`113506` closes the loop `113502` opens.** Detecting a change is useless if it dispatches again every night afterwards, and nothing in the positive case for detection says the baseline moves with it.

**`113606` makes the request hash independent of how a file was checked out.** Content is normalized to LF before hashing, so a task document or code excerpt of more than one line produces the same hash on Windows and on Linux. Without it, every replay fixture reports stale on whichever platform did not record it, `MQC_REQ_HAR_EXE_0009` fires correctly, and the diagnosis is wrong.

`.gitattributes` also pins line endings. **Both exist because either alone is a single point of failure**: the attributes file can be edited or absent in a copy of the repository, and normalization in code cannot repair a fixture that was recorded from already-rewritten content.

**`113605` is the one place a stale fixture is not a problem.** `MQC_REQ_HAR_EXE_0009` requires staleness to be reported rather than silently replayed, because replaying a recorded answer to a different question corrupts the result. Under the divergent refs of `harness_ci_pipeline.md` section 6.4, a changed request hash is the answer the diagnostic was asking: it says the request composition changed between the two checkpoints. The run reports it per fixture and continues.

**`113504` keeps a broken detector from reading as a model finding.** A probe failure means our code or the provider's metadata endpoint failed, so it records a `QC_HARNESS_*` event and dispatches nothing. The unconditional weekly run covers the period regardless, which is why the probe is allowed to fail without escalating.

#### 10.1.3 Five battery cases and nine provider quirks

`113110` through `113114` are the conformance battery's own rows, explained in section 9.1: they assert over the registry rather than over a constructed record. `113113` and `113115` guard the registry itself, one against a name claimed twice and one against a name claimed by nothing.

`113000` through `113008`, with `113009` and `113010`, are the per-adapter cases section 9 requires and `harness_extensibility_standard.md` section 11 makes mandatory for any registry addition. Each names a **real difference between the three providers**, not a restatement of the shared contract:

| Provider behaviour | Case | What goes wrong without it |
|---|---|---|
| Tool arguments arrive parsed on two providers and as a JSON string on the third | `113110` with `113401` | One provider's tool cases fail on a shape the others never produce |
| A policy refusal is a distinct stop reason on one provider only | `113000` | A refusal reads as an ordinary completion and is scored as one |
| Text arrives as several blocks rather than one field | `113001` | Output is silently truncated to its first block |
| A superseded finish-reason spelling is still emitted by older deployments | `113002` | A successful tool call records as an unknown outcome |
| The tool-call field is omitted entirely rather than sent empty | `113003` | Normalization fails on the ordinary no-tool response |
| The resolved version field is named differently on each provider | `113111`, `113004` | Preflight aborts the run for a provider that answered correctly |
| A tool-calling turn reports the ordinary stop reason | `113005` | Tool-use rates compare vendor conventions, per section 4.3 |
| A blocked candidate carries no content at all, not empty content | `113006` | A model behaviour worth recording becomes a harness failure recording nothing |
| Automatic function calling is on by default | `113007` | The harness executes a tool the model chose, per section 3.3 |
| One error class carries every client failure, distinguished by status | `113008` | Every provider failure records as a parser error |
| A system instruction is a request field on one provider and a message role on another | `113009`, `113010` | The instruction is folded into the prompt, where models follow it at a different rate |

**`113003` is a boundary rather than a positive** because the absent field is the ordinary case, not the exceptional one. Most responses contain no tool call, so the shape the inventory is likeliest to leave untested is the one that occurs most often.

**`113209` belongs with the registry cases rather than with the pacing ones.** Mode selection is independent of engine selection, so an unregistered mode is rejected on the plan before an adapter is chosen. Rejecting it later would make the error depend on which engine happened to be selected, and a mode nobody supports would produce three different messages.

**`113112` is stated negatively on purpose.** Asserting that each adapter emits the right types would pass on an adapter that emits a vendor object in a field nobody enumerated. The case walks the record's fields and rejects any type outside the permitted set, so a field added later is covered without anyone remembering to cover it.

---

## 11. Traceability

| Decision | Section |
|---|---|
| A3 zero cost, most engines replayed | 7 |
| A5c Tier 3 owns the post-execution screen | 2 |
| A6 mode recorded, replay default | 4.1, 7 |
| A7.2 output tokens with duration | 4.1 |
| A7.3 spacing, retry, circuit breaker | 8 |
| A8 resolved model version | 5 |
| A9 no loop, no tool execution | 3.3 |
| A9 capture not execute, one request per case | 1, 4.2 |
| A13 unsupported pairs derived | 6 |
| B8 engine roster in configuration | 6, 8 |
