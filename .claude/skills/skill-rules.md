<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# AI Skill & Process Governance

## 1. Audit & Logging Standard

Two logs, split by audience. Writing to the wrong one is a process error.

| File | Tracked | Contents |
|---|---|---|
| `CLAUDE_LOG.md` (repo root) | **Yes** | Decisions, trade-offs, Pylint scores, variable audits, phase outcomes. Written for a reader who was not present. |
| `.claude/logs/PROMPT_LOG.md` | **No** | Verbatim prompts, phrasings, reprompt history. Working notes, not project output. |

* **Log Entry Required**: an entry MUST be written to `CLAUDE_LOG.md` upon completion of every phase, including phases that produce no code.
* **No Raw Prompts In The Tracked Log**: summarize intent in `CLAUDE_LOG.md`; the verbatim text goes to `PROMPT_LOG.md` only.
* **No Credentials In Either**: API keys and `.env` values are redacted in both, without exception.
* **No Self-Referential Or Audience-Facing Framing In The Tracked Log**: `CLAUDE_LOG.md` is publicly visible. It records decisions and their reasoning, never commentary on how the work should be perceived, who might read it, or what it demonstrates about its author. Such notes belong in `.claude/logs/PROMPT_LOG.md`, which is not tracked.
* **Write For An External Reader**: `CLAUDE_LOG.md` entries record what was decided, what was rejected, and why, for someone evaluating the work who was not present. The record demonstrates the reasoning on its own; it does not need to point at itself.

* **Digressions Are Recorded With Their Fix**: an entry whose work departed from the design, the rules or the documented order carries a section headed **"Digressions the user spotted, and the fix"**. Each item names the departure, where it was (the document, rule or code segment), who or what caught it, and the fix applied. Added 2026-10-16 at the project owner's instruction, replacing the unwritten habit of a "Where I Was Wrong" heading, which named no subject and recorded a confession rather than a departure and its remedy. Earlier entries keep the heading they were written with.

### 1.1 A test report in session separates the harness from the model

Added 2026-10-16 at the project owner's instruction.

**A result reported in a working session states the harness and the model on separate lines**, never one merged count. A harness failure implicates the instrument and a model failure implicates a vendor's model (`framework-rules.md` section 3.1), and a merged line hides which of the two a reader is looking at.

| Line | Carries |
|---|---|
| `Harness:` | `AP-Harness-QC` preconditions, unit and system, and pylint |
| `Model:` | `AP-Model-QC` preconditions and pylint |
| One line per engine beneath `Model:` | The graded bands or cases run against that engine, and the mode, replay or live |

Each line carries total, executed, passed, failed and skipped in that order, and the exit code, which is the vocabulary `code-style.md` section 7.1 sets for a measured run. A line for something that was not run says so rather than being left out.

## 2. Feature Development Lifecycle

### Phase 0: Ambiguity Resolution & Clarification
* Identify every ambiguity, unstated assumption, and open decision **before** any discussion of approach.
* Record each as a numbered item in an ambiguity register at `docs/design/phase0_<feature_name>_ambiguities.md`, with: the question, why it blocks work, the options, and a recommendation.
* Distinguish **blocking** items (work cannot proceed or would be wasted) from **deferrable** items (an assumption can be stated and revisited).
* Phase 0 closes only when every blocking item has a recorded user decision. Deferrable items close with a stated assumption.
* **STRICT RULE**: zero code generation and zero design commitment during Phase 0.

### Phase 1: Clarification & Discussion
* Discuss architectural intent, requirements, and edge cases, informed by the Phase 0 decisions.
* Clarify API contracts, type signatures, and dataclass boundaries.
* **STRICT RULE**: Zero code generation during Phase 1.

#### When Phase 0 discharges Phase 1

Phase 1 is required where a module carries **fresh ambiguity**, or where it forces decisions the project-level Phase 0 did not already settle.

Where it carries neither, the project-level Phase 0 discharges it, and the module proceeds directly to Phase 2. Running a discussion phase with nothing left to discuss produces a document recording that there was nothing to record.

The discharge is **stated in the design document**, so a reader can tell a phase deliberately discharged from one overlooked.

### Phase 2: Design Document Creation
* Create a dedicated Markdown design document in `docs/design/<feature_name>.md`.
* Define system context, class signatures, variable naming choices, Pylint requirements, and data flows.
* Record the Phase 0 decisions that shaped the design, so a later reader sees what was chosen and what was rejected.
* Requires user review and approval before proceeding to Phase 3.

### Phase 3: Code Implementation & Quality Audit
* Generate production code implementing the approved design document.
* Enforce `.claude/rules/code-style.md` and `.claude/rules/framework-rules.md`.
* Verify **10.00/10 Pylint score** and **zero single-character variables** (minimum length of 3 characters). Log results in `CLAUDE_LOG.md`.

#### The design is amended, not worked around

Where implementation finds a better structure than the design specifies, **the design is amended**. That is a design change, and it must cover the new implementation.

A design document is a **living specification, not a frozen contract**. Its purpose is that a reader of the documentation sees the system as it is, so documentation that has fallen behind the code is worse than none: it reads as verified and is not.

Three rules follow:

* **Discuss, document, then implement.** A design change re-enters the discussion and design steps before any code is written against it. Implementation stops at the point the better structure is found; it does not proceed and document afterwards.
* **The amendment is recorded in `CLAUDE_LOG.md`** with the reason implementation improved on the design. A specification that changes silently cannot be reviewed.
* **Specified test cases are revisable on the same terms**, through the same sequence. A case encoding a structure that implementation improves upon is amended rather than treated as a constraint to argue against.

**Documentation is a standard and a compass**, not a record written after the fact. Coding first and documenting after inverts that, and produces a design that describes what was built rather than what was decided. The structure is the point.

Once versioning begins, `CHANGELOG.md` records this evolution release to release, and the design documents continue to describe only the current state.

## 3. Test Engineering Lifecycle

### Phase 0: Test Ambiguity Resolution
* Resolve what "correct" means for a non-deterministic system before designing assertions: tolerance, retry policy, and what distinguishes a genuine failure from model variance.
* Register open items in `docs/testing/phase0_<feature_name>_ambiguities.md`.

### Phase 1: Test Strategy Discussion
* Define coverage targets, failure scenarios, and error taxonomy mappings.

### Phase 2: Test Design Document Creation
* Generate a structured test plan in `docs/testing/<feature_name>_test_plan.md`.
* Document test IDs in the format `MQC_<MODULE>_<LAYER>_<6DIGIT_ID>_<behavior>`, with modules and layers as registered in `../rules/testing-standards.md` section 1, and with inputs, expected outputs, and variable checks.
* Assign a priority to every case with its **matched qualifying condition** named, per `docs/design/harness_test_taxonomy.md` section 4.1. A priority without a named condition is not assignable.
* Assign IDs from the registered layer's block; never reuse a retired ID.

### Phase 3: Test Implementation
* Generate test implementations matching `.claude/rules/testing-standards.md` with 10.00/10 Pylint score compliance and descriptive variable names.

### Phase 3 Is A Loop, Not A Finish Line

Implementation routinely discovers something Phase 2 did not anticipate. **The
design is corrected before the code is**, and then the code is written against
the corrected design. Normative statement and rationale in
`.claude/rules/testing-standards.md`, Authoring Order.

| Discovered while building | Wrong response | Right response |
|---|---|---|
| A case the design did not inventory | Write the test, document it later | Add the inventory row, then write the test |
| A behaviour the design got wrong | Change the code to what works | Correct the design, then change the code |
| A new case the work revealed is needed | Add it and move on | Inventory it, trace it, then add it |

**A surprise found while building is evidence the design was wrong**, not
licence to leave it wrong. Returning to Phase 2 mid-Phase-3 is the expected
path, and re-entering it costs minutes against a documentation set that would
otherwise describe a system nobody built.

## 4. Design Document vs Test Plan

The two Phase 2 artefacts have different subjects, and the division follows the layer taxonomy rather than being an arbitrary split of one document.

| | Design document | Test plan |
|---|---|---|
| Path | `docs/design/<feature>.md` | `docs/testing/<feature>_test_plan.md` |
| Subject | **The harness** | **The agent / model under evaluation** |
| Layers | `UNI`, `SYS` | `EVAL`, `TOOL`, `SEC` |
| Assumes | Nothing | That the harness is complete |
| Contains | Tiers, schemas, loaders, validation, test categories, priority assignment mechanics and examples | Test categories mapped to a requirements traceability matrix |
| Released to a customer | **No**, test infrastructure | **Yes**, the model and agent are the product |

**Why the split matters.** Without a working harness QA cannot test, but the harness is not the deliverable. For an end-product release it is the tests evaluating the agent and model that matter. Harness tests may appear in the test plan as a stated **precondition**; they are never its content.

This also retro-justifies making the `UNI` and `SYS` layers ungraded preconditions: they do not measure the product, so they do not belong in the product's quality budget.

### 4.1 Requirements traceability

Where evaluation requirements exist as business requirements, the test plan maps them in a traceability matrix. An RTM answers two questions, and the second is the one that earns its keep:

1. Which tests cover a given requirement?
2. **Which requirements have no test at all?**

Coverage gaps are the real output. This is referential integrity check 3, *every constraint sent must be checked*, applied one level up: **every requirement stated must be tested.**

`requirement_ids` is carried on `GoldenRuleSet` and emitted into result metadata, so **the matrix is derived from the record rather than maintained by hand**. A hand-maintained matrix goes stale the moment a test is renamed; a derived one cannot. Because the downstream collector retains history, the matrix answers "has this requirement ever failed" and not merely "is it passing now".

## 5. Document Tracking
* `docs/design/**` and `docs/testing/**` are **tracked project output**. They demonstrate the engineering process and are written to be read by someone outside the project.
* Ambiguity registers are tracked alongside the designs they precede. A resolved question is evidence of process, not scratch work.

## 6. Version Control Safeguards
* **NO DIRECT COMMITS**: Never execute `git commit`, `git push`, or alter branches directly.

### 6.1 A commit note is written in past tense, labelled by kind, and every label carries its reason

Added 2026-10-02 as the tense rule and extended 2026-10-28 at the project
owner's instruction to the structure: "report what was changed fixed (why)
added (why) and use past tense".

**Past tense, not the imperative mood the git convention teaches.** The note
records a change that has already been made and the reason it was made;
"Implement `--out-dir`" reads as an instruction to somebody, which is not what
a commit note is for here. The subject line and every body paragraph open with
a past tense verb.

**One paragraph per item, opening with its label**, then what it was, then why
it was needed:

```
Reported a publisher that read conclusions, and moved the Ubuntu pin to 26.04

Fixed: <what was wrong, and what it cost>
Added: <what is new, and why the gap mattered>
Changed: <what moved, and what decided it>
```

| Label | Holds |
|---|---|
| `Fixed:` | A defect, and the behaviour it produced |
| `Added:` | Something new, and the gap it closes |
| `Changed:` | Something that moved, and what decided the move |
| `Removed:` | Something withdrawn, and why it was buying nothing |
| `Verified:` | The injection or the run that proves the above, where it is not obvious |

**The label is what makes the note readable to somebody bisecting.** A
narrative paragraph mixing three changes hides which reason belongs to which,
and the reason is the part a reader arriving at the commit cannot reconstruct
from the diff.

**This is `code-style.md` section 7.4.1 applied to a different artefact, and
the division of labour is the same.** The changelog states the purpose and then
the change and never who made it; the commit note does the same for one commit,
and authorship is recorded by the commit itself. Who asked, in what words, goes
to `CLAUDE_LOG.md` and `.claude/logs/PROMPT_LOG.md`.
