<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# Extensibility Standard

> **Parent:** `DESIGN.md` section 3.1. Read that first for architecture and document map.
> **Status:** normative, project-wide. Every design document conforms to this; none restates it.
> **Scope:** how the harness absorbs a new provider, a new test layer, a new suite, or a test type nobody anticipated.
> **Purpose:** the same approach applies to the tier APIs and to growth in the number of test suites, so neither is a special case.

---

## 1. The Governing Pattern

Three parts, applied identically everywhere:

1. **A registry**: implementations registered by name.
2. **Declared properties**: each entry states how it behaves rather than being special-cased by the core.
3. **Configuration selects**: choosing among registered entries is config, never code.

**The invariant:** *adding a thing must not require editing the code that consumes things of that kind.*

Where this is violated, the risk of an addition becomes unbounded: a regression in shared consuming code affects every existing entry, not only the new one. That risk is most acute in verdict computation, which decides every run's outcome.

**Anti-pattern to watch for:** `MQC_SEC_` was added with hand-written exemptions, a conditional in the distribution check naming one layer. That worked once and would not survive a second exempt layer. It is now a **declared property** (§4), and the same correction applies anywhere a core function names a specific entry.

---

## 2. Tier API Contracts

Each tier exposes a stable interface. Crossing a tier boundary means satisfying an interface, never reaching into an implementation.

| Boundary | Passes | Never passes |
|---|---|---|
| Tier 1 → Tier 2 | Validated `EvaluationCase` objects | Raw files, loader state, format knowledge |
| Tier 2 → Tier 3 | Normalized responses with tool-call traces | Provider-specific payloads, SDK objects |
| Any tier → orchestrating test | That tier's **result** type | Tier internals |
| Reporting hook → artifact | An assembled **observation** | Unmerged tier results |

**Syntax is validated at the boundary, before anything is passed on.** A malformed payload is rejected where it is detected and never forwarded to the next tier.

| Boundary | Validated | On malformed input |
|---|---|---|
| File → Tier 1 | YAML parses; CSV has consistent, non-duplicated columns | `QC_DATA_*` ERROR, ingestion aborts |
| Provider → Tier 2 | Response is well-formed for its declared content type | `QC_HARNESS_PARSER_ERROR`, observation skipped |
| Tier 2 → Tier 3 | Payload is structurally valid where a structure was required | `QC_LLM_SCHEMA_VIOLATION`: a model finding, not a harness defect |
| Judge → CMN | Reply is schema-valid | `QC_SEC_JUDGE_HIJACK`, blocking |
| Any model → harness | Prose fields carry no prohibited glyph (em dash, bare pipe) | `QC_LLM_FORMAT_VIOLATION`, normalized and recorded, never fatal |

**Two distinctions this preserves:**

*Malformed* and *invalid* are different findings. Syntactically broken JSON from a model under test is `QC_LLM_SCHEMA_VIOLATION`; a syntactically valid response failing a rubric is `QC_LLM_RUBRIC_FAILURE`. Collapsing them would make "the model cannot produce JSON" indistinguishable from "the model produced poor content".

Forwarding a malformed payload also has a **security consequence**: a structurally broken payload may be a delimiter-escape attempt (§ injection taxonomy). Validating structure at the boundary is a safety control, not only a correctness one.

### 2.1 The test class orchestrates

No tier drives the sequence. **The test class holds the `EvaluationCase`, calls each tier through an injected fixture, and passes each tier only the subset it needs.** Tiers stay independently unit-testable because they are objects a test drives, not a pipeline that drives itself.

Step semantics are conjunctive: a case passes only when every verifiable step passes, and one failing step fails the case. This is the same rule the assertion gates use.

**Tiers emit results; they do not emit observations.** Tier 3 deliberately never receives `priority` or `priority_conditions`, so it is structurally incapable of producing a complete observation, and requiring it to would breach the boundary keeping severity invisible to the component deciding whether something failed.

**A reporting hook in `conftest.py` assembles the observation**, merging tier results with the case metadata the test holds, and writes it into the artifact. The CMN verdict tool later reads observations from artifacts.

**Extensible by registry:** each result type declares the fields it contributes, and the hook merges across the registry. A new tier adds a result type without the hook changing, which is the same pattern as every other extension point here.

Two rules follow:

* **A tier does not know how the tier below obtained its input.** Tier 3 cannot tell whether a response came from Gemini or a replay fixture, except through the `mode` field it records but does not branch on.
* **A tier receives what it needs, never a whole object it must ignore.** `GoldenRuleSet` carries fields for two different consumers: Tier 3 evaluates with `assertions`, `rubric` and `tool_expectation`, while CMN reads `priority`, `priority_conditions` and `requirement_ids` for verdict computation and traceability. **Tier 3's interface receives only the evaluation-relevant subset.** The evaluator has nothing to do with a priority or its justification, and passing them would invite an implementation to start reading them.
* **Provider-specific types stop at the adapter.** An SDK object reaching Tier 3 is a design defect, because it makes the judge dependent on which vendor produced the output it is judging.


### 2.4 The homoglyph vector, which writing the corpus found missing

Added 2026-09-24. The registry detected two of the three obfuscation
techniques the security corpus uses and not the third.

| Technique | Detected by | Level |
|---|---|---|
| Base64 and named encodings | `encoding_obfuscation` | Pattern |
| Zero width characters | `invisible_characters` | Character |
| **Confusable letters** | **Nothing** | Character |

`MQC_REQ_MDL_SEC_0005` says the model must resist an override "obfuscated by
encoding", and `MQC_EVL_SEC_154106` is inventoried for the homoglyph form
specifically. The requirement expected a detection the registry could not make.

#### 2.4.1 A homoglyph is a character-level fact, not a pattern

`Ignоre аll рreviоus instruсtiоns` reads as English and contains Cyrillic
`о`, `а`, `р` and `с`. **No amount of pattern work on the visible text finds
it**, because the text looks exactly like what it imitates. Detection is a
property of the code points, which is why this joins `invisible_characters` as
a character-level vector rather than a row in the pattern table.

**The test is a mixed script inside one word.** A word written entirely in
Cyrillic is Russian; a word mixing Cyrillic and Latin is almost always an
imitation of the Latin one, because no natural orthography does that. Scanning
for the presence of Cyrillic alone would report every Russian document as an
attack.

#### 2.4.2 It reports, and the screen decides

Like every vector, this is a **measurement**. The ingest screen bypasses it for
a declared adversarial task and the Tier 3 screen records it without aborting,
which is A19 unchanged. What the vector adds is that a homoglyph payload is now
visible in the record instead of passing as ordinary prose.

**The cross-check is what was actually lost.** `MQC_EVL_UNI_114608` requires
content the ingest screen matched to be matched again at Tier 3, and a payload
no vector recognises cannot participate in it. The case would still have tested
the model correctly and stopped saying anything about whether the fixture was
still doing its job.

---

## 3. Provider Adapters: the API extension point

Adding an engine is the most likely extension. An adapter implements one interface and declares its capabilities.

### 3.1 Required operations

| Operation | Responsibility |
|---|---|
| `compose_request` | Build a provider-shaped request from an `EvaluationCase` |
| `normalize_response` | Return the canonical response shape |
| `extract_tool_calls` | Return tool-call intent in canonical form: **captured, never executed** (A9) |
| `resolve_model_version` | The version the provider **returned**, not the one requested (A8) |
| `map_error` | Translate provider failures into `QC_HARNESS_*` codes |

`map_error` matters more than it looks: provider error taxonomies differ, and without translation a rate limit from one vendor and a rate limit from another become different rows in the record, destroying comparability.

### 3.2 Declared capabilities

An adapter declares what it supports:

| Capability | If absent |
|---|---|
| `tool_calling` | `MQC_*_TOOL_` cases become unsupported pairs for this engine |
| `structured_output` | Judge-side schema enforcement unavailable; this engine cannot judge |
| `system_instruction` | Instruction folded into the prompt, recorded as a deviation |

**Unsupported pairs are derived from declared capability, not hand-maintained.** If an engine cannot call tools, every `MQC_*_TOOL_` case against it is automatically unsupported: no config entry to forget. Configuration may still declare an additional unsupported pair with a written reason (A13), but a capability gap should not require someone to notice it.

### 3.3 Adapters do not evaluate

An adapter composes, sends and normalizes. It does not score, judge, retry into a loop, or interpret content. Evaluation is Tier 3's, and an adapter that starts interpreting output has become a second evaluator with no rubric.

---

### 3.4 Adding an evaluated engine is declarative, and one step was unchecked

Added 2026-10-02 at the project owner's instruction: the evaluated-engine API
has to be expandable, because the findings are per engine and the set of engines
worth evaluating grows.

**Three declarations, no code outside the adapter.**

| Step | Where | Checked by |
|---|---|---|
| Register the adapter | `@register_adapter` on the class, which declares its engine name, default model and credential variable | `register_adapter` refuses a duplicate claim |
| Name the credential | `API_KEY_ENV` on the adapter, surfaced by `credential_variables()` | The credential checks read that list |
| **Put the engine on the roster** | `config/engines.yaml` | **Nothing** |

**The third step is unreachable and silent, and `grok` is in that state now.**
The adapter ships, registers under `grok`, declares `grok-4` and
`XAI_API_KEY`, and `credential_variables()` already reports that variable. The
roster names `gemini`, `openai` and `claude` and does not name `grok`, so
`load_engines` never yields it and `--engine grok` is refused as absent from the
roster.

| | |
|---|---|
| An adapter exists and registers | Yes |
| Its credential is expected by the credential surface | Yes |
| The engine can be selected | **No** |
| Anything reports the gap | **No** |

So "adding an engine is an entry, never a module" (B8) is true of the design and
had a step that could be skipped without a word. That is the shape this project
keeps recording: the mechanism is right and nothing establishes it is reachable.

**Every registered adapter is either on the roster or a recorded absence.** The
remedy is the one `flag_coverage.yaml` already uses for flags: an adapter that
is deliberately not rostered carries a reason and a date, so the omission is a
decision rather than a silence, and an undated one fails the run.

```yaml
# config/engines.yaml, a sibling of `engines:` and `judge:`
not_rostered:
  grok:
    reason: >-
      The adapter and its conformance cases ship; no fixtures are recorded
      and no credential is held, so a run naming it would refuse at preflight.
    expires_on: 2026-11-30
```

**A sibling key rather than an entry under `engines:`.** `load_engines` refuses
an entry naming no model, on the ground that an engine with no model would
dispatch against the adapter default and record a model nobody configured. A
declared absence is not an engine, so it must not sit where engines are read.

**Why a recorded absence rather than simply adding the entry.** A roster entry
is a claim that the engine can be evaluated, and evaluating one needs a
credential, recorded fixtures and a priced model, none of which `grok` has yet.
An entry added without them turns a declarative gap into a run that fails at
preflight, which reads as a broken harness rather than as work not done.

## 4. Adding a Test Layer

A layer declares its properties at registration; the verdict function reads them rather than naming the layer.

| Property | Values | Effect |
|---|---|---|
| `graded` | true / false | False means ungraded precondition: 100% pass, zero skips, blocks graded layers |
| `distribution_exempt` | true / false | True excludes it from the priority ceilings |
| `id_block` | Range | Assigned once, never reused |
| `marker` | String | `pytest.ini` registration |
| `gate_position` | Integer | Where it runs in the CI sequence |

`UNI` and `SYS` are `graded: false`. `SEC` is `graded: true, distribution_exempt: true`. Neither is special-cased in code.

**Registration remains three steps** (`harness_test_taxonomy.md` §3.4): a registry row, a `pytest.ini` marker, a CI gate step. No `.pylintrc` change: the pattern accepts any `MQC_[A-Z]{3}_[A-Z]{3,5}_` identifier, which is why three layers have been added without touching it.

---

## 5. Growth In Suite Count

Properties that do not scale automatically, and what governs each:

| Pressure | Governed by |
|---|---|
| **Provider quota** | Parallelism is per-engine only. Priority bands and suites share a quota, so they serialize (`max-parallel: 1`). Adding suites must not add concurrent live jobs |
| **CI job count** | Default topology is three jobs on dependency boundaries, not one per suite. Per-suite jobs are a `workflow_dispatch` troubleshooting path |
| **Runtime** | Preconditions are free and fast; only graded live layers cost wall-clock. Suite growth in precondition layers is close to free |
| **ID exhaustion** | 9,999 identifiers per layer. Not a practical limit; blocks are never reused, so exhaustion would be permanent |
| **Report legibility** | Reporting prints authored tasks, case definitions and executions as three separate counts, never one conflated total |

**The rule for a new suite:** it must not increase concurrent live requests. A suite that can only run live and in parallel with others does not fit this harness without a quota change.

---

## 6. Registries

| Registry | An entry is |
|---|---|
| Layers | Declared properties (§4) |
| Evaluation families | Identifier plus its declared ground-truth mechanism (`harness_test_taxonomy.md` §11) |
| Taxonomy codes | Code, family, severity, meaning |
| Priority conditions | Identifier and level |
| Aggregation strategies | Implementation plus declared `scale_id` |
| Assertion kinds | Implementation plus parameter schema |
| Loaders | Implementation against the loader interface |
| Verdict rules | Implementation returning `(fired, reason)` |
| Provider adapters | Implementation plus declared capabilities (§3) |
| Injection vectors | Name plus its pattern. **Shared by the ingest and Tier 3 screens**, so a new vector reaches both at once |
| `Constraint.kind` | Open vocabulary; unknown kinds warn rather than fail |
| Term aliases | A canonical name and its variants, such as `JavaScript` against `Javascript`, or `Kubernetes` against `K8s`. Used wherever a requirement is matched against supplied source material |

---

## 7. What Is Deliberately Fixed

| Fixed | Why |
|---|---|
| Five priority levels | Bound to Allure's five severities, which carry them to the collector |
| The `MQC` prefix | Project identity; a collector keys on it |
| Assigned ID blocks | Never reused, so history cannot rebind an identifier to different behaviour |
| Verdict purity | A rule reading a clock, a file or the environment cannot be tested at a boundary |
| Outcome set | `pass`, `fail`, `broken`, `skip`. Extensible only under §8 |
| Capture-not-execute | Tier 2 never executes a tool call. Relaxing this would make the harness an agent |
| Every supported platform on every gated run | Alternating or sampling platforms is **not permitted**. See below |
| Untrusted content never enters instruction text | Applies to every component that composes a request to a model, present or future. See below |
| A payload is never forwarded to a component that can act on it | Resistance is measured by assertion, not by asking a model. See below |

**Platform alternation is precluded, not merely unchosen.** A gated run must execute every supported platform, and a scheme that runs Ubuntu on one commit and Windows on the next is forbidden regardless of the saving it offers.

The reason is attribution rather than coverage. **Alternating rarely holds both results for one commit**, so a green run on one platform followed by a red run on the other cannot be separated into a platform difference and the change between them. The failure is then attributed to whoever triggered the run that exposed it rather than to the change responsible, which is the same misattribution the full-run-on-merge rule exists to prevent.

It is listed here rather than left as a rejected option in A18 because the saving it offers is real and will be proposed again. **The correct lever when platform cost binds is scoping, which is already specified**, not sampling the thing the run exists to prove.

A diagnostic run is exempt, as it is from every gating rule: it may name one platform, and it yields no verdict.

### 7.1 Two rules about untrusted content

Added 2026-09-22 per A19, generalised from Tier 3 because **neither rule is a property of Tier 3**. Any component this project grows that composes a request to a model inherits both.

#### The trust boundary is authorship, not custody

**Content we did not author is untrusted, however we came to hold it.** Case data sits in our repository, passes our validation and is read from our disk, and none of that makes it ours. A case author is trusted to write a good test, which includes writing an injection payload on purpose; trusting the payload as well does not follow.

Every such value goes into a delimited, typed data field and never into the instruction portion of a request. The categories that qualify today are candidate output, task instructions and context documents. **The list will grow and the rule will not**, which is why it is stated as a boundary rather than as three field names.

This is testable by string containment over the composed request, so a new field is covered by extending a loop rather than by writing a new kind of test.

#### Resistance is measured, not judged

**A component that can act on an instruction is never shown one deliberately.** Grading whether a model resisted an injection is a string check against a canary, not a question put to another model.

Asking a judge would put the payload in front of the one component whose compliance would corrupt the result, to answer a question a substring comparison answers exactly. The check is also cheaper, deterministic, and spends no quota.

**What this costs:** manner cannot be graded, only compliance. A judge could have said how gracefully a model refused, and that question is unavailable. Compliance is what makes a model unsafe to deploy, so this is the right thing to lose.

**There is no fallback, and that is deliberate.** An earlier version kept redaction to a typed marker for a case where judgement could not be avoided. It was implemented, had no caller, and was removed on 2026-09-24.

A security case is decided by assertion or it is not decided. **An unused door in this wall is still a door**: the next author with an awkward case finds it, and the reasoning that justified keeping it is not in front of them at that moment.

---

## 8. Unanticipated Test Types

A test type nobody designed for is the real test of this standard.

**Checklist for any addition:**

1. Does it fit an existing layer, or need a new one? A new layer needs declared properties (§4).
2. Does it need a new outcome? If so, it must declare **how it counts in each denominator**: pass rate, skip rate, distribution. An outcome that cannot answer all three cannot be added, because the verdict function would silently pick a default and that default would be wrong somewhere.
3. Does it need a new gating rule? Contribute a verdict rule; do not modify existing ones.
4. Does it need a new failure classification? Add a taxonomy code with family and severity.
5. Does it need new data? Extend a schema with an **optional** field, or add a loader. A new required field breaks every existing fixture.
5b. **Does it put content in front of a model?** If the content was authored by anyone other than us, it is isolated into a typed data field, per section 7.1. If the content is an injection payload, no model sees it: resistance is asserted, not judged.
5a. **Is it a new evaluation family?** If the task shape or the source of ground truth differs from every registered family, it is. Register it per `harness_test_taxonomy.md` §11.2 rather than filing its cases under a family they do not belong to, which is how a scope statement comes to describe less than the suite exercises.
6. **Does it increase concurrent live requests?** If yes, it does not fit without a quota decision.

**If an addition cannot be made through this checklist, that is a finding about the design, not about the addition.** The correct response is to fix the extension point, not to special-case the new type, which is how `MQC_SEC_`'s hand-written exemption became a declared property.

---

## 9. Interface Stability Tiers

A standard that does not say which interfaces are stable cannot prevent a breaking change; it only regrets one.

| Tier | Covers | Changing it |
|---|---|---|
| **Stable** | Tier boundaries (§2), the provider adapter interface (§3), the loader interface, the verdict rule signature, the observation record | **Major version.** Requires a deprecation cycle (§12) |
| **Registry entries** | Individual adapters, loaders, strategies, codes, conditions | Minor version. Additive by construction |
| **Internal** | Everything inside a module not reachable across a tier boundary | Patch. No external contract |

**The rule that gives this teeth:** a stable interface may gain an **optional** parameter with a default, and may never gain a required one. A required parameter breaks every existing implementation simultaneously, which is the refactor this standard exists to avoid.

---

## 10. Conformance Suites: the executable contract

An interface described in prose is a suggestion. **Every extension point ships a reusable conformance suite that any implementation must pass.**

| Extension point | Conformance suite asserts |
|---|---|
| Provider adapter | Composes a valid request, normalizes to the canonical shape, extracts tool-call intent without executing, returns a resolved model version, maps each provider error class to a `QC_HARNESS_*` code, honours declared capabilities |
| Loader | Produces identical objects from equivalent input, rejects unknown fields, rejects empty mandatory fields, reports missing and empty distinctly |
| Aggregation strategy | Declares a `scale_id`, is deterministic for identical input, handles a single criterion and an empty-after-filtering set |
| Verdict rule | Returns `(fired, reason)`, is pure, does not read a clock or the environment |

Registration **enrols an implementation in its conformance suite automatically**. Adding an adapter without running the battery is not possible, because the battery is parametrized over the registry.

The cross-loader equivalence test already specified in Tier 1 is the first instance of this pattern; generalising it is what turns "both loaders should agree" into "every loader must agree, including ones not yet written."

**This is the mechanism that replaces refactoring.** A new implementation either satisfies the recorded contract or fails visibly on arrival, rather than diverging quietly and being discovered when results disagree.

---

## 11. Every Extension Ships Its Own Tests

Passing the conformance suite is necessary and **not sufficient**. The two answer different questions:

| | Answers |
|---|---|
| **Conformance suite** (§10) | Does it satisfy the shared contract? |
| **Its own unit tests** | Is its own logic correct? |

A provider adapter can satisfy every contract assertion while mapping its provider's rate-limit error to the wrong code, or composing a request that drops the system instruction. The contract cannot know what the implementation was supposed to do internally.

**Mandatory for any registry addition:**

* `MQC_<MODULE>_UNI_` cases covering the implementation's own logic, including its **negative and boundary** paths.
* Enrolment in the relevant conformance suite (automatic, §10).
* The same quality bar as the rest of the harness: no exemption for being an extension.

**Mandatory for a new suite or layer:**

* Unit tests for whatever the layer adds beyond existing behaviour.
* A declared-properties entry (§4) exercised by a test proving the verdict function honours it.
* An entry in `rtm_harness.csv`: a layer with no requirement traced to it is a coverage gap.

**The quality bar applies identically to extension code and its tests:**

| Constraint | Applies to |
|---|---|
| **10.00/10 Pylint** against `.pylintrc` | Implementation and tests |
| Minimum 3-character identifiers, no `test_` prefix | Both |
| `MQC_<MODULE>_<LAYER>_<5DIGIT>_<behavior>` naming | Tests |
| One layer and one priority per class | Tests |
| Google docstrings, explicit typing, narrow exception handling | Both |
| Frozen dataclasses, explicit casting at boundaries | Implementation |

An extension that cannot meet the bar the harness meets is not ready to be registered. **There is no provisional or experimental tier**, because a registry entry is reachable by the verdict function and therefore affects results.

---

## 12. Data Schema Versioning

Extending a schema must not invalidate existing fixtures.

* **Every data file carries `schema_version`.** Loaders accept the current version and the one before it.
* **Additive changes are minor:** a new **optional** field with a default. Existing files remain valid unchanged.
* **A new required field is a major schema change** and requires a migration note in the changelog plus a transitional period where the field is optional with a defined default.
* **Unknown `schema_version` is rejected**, never guessed. A loader silently treating a future version as current would misread fields it does not understand.

Without this, the first genuinely new requirement that needs a mandatory field forces every fixture to be rewritten at once: exactly the incessant refactoring this standard exists to prevent.

---

## 13. Deprecation and Retirement

Registry entries are retired on a path, never removed abruptly.

| Stage | Behaviour |
|---|---|
| **Active** | Normal use |
| **Deprecated** | Usable; emits a WARNING naming the replacement and the removal version |
| **Removed** | Rejected with an error naming the replacement |

**Identifiers are never reused after removal**: test IDs, taxonomy codes, condition identifiers, `scale_id` values. A reused identifier makes a durable record rebind a name to different behaviour, silently corrupting history already stored.

A removal appears in the changelog as a major change, because an existing dataset or configuration stops loading.

---

## 14. Thresholds Are Configuration, And What Was Applied Is Recorded

Every numeric gate is configuration rather than a constant: the 90% pass floor, the 20% and 10% skip ceilings, the 10/20/30% distribution ceilings, and the 30-case minimum.

**The hazard:** configurable thresholds can be loosened until a failing run goes green. That is the corruption A2 exists to prevent, relocated from rubric thresholds to gate thresholds.

**The guard is disclosure, not prohibition.** The **effective thresholds are emitted into result metadata**, so every artifact states the standard it was judged against. A loosened threshold then appears in durable history as a change in the recorded standard rather than as an unexplained improvement in pass rate.

This is the principle already applied to `mode` (A6), resolved model version (A8) and the rule-set content hash: extended to the judging criteria themselves. **Anything that can vary between runs and change a result is recorded with the result.**
