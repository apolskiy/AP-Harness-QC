<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# Harness Test Plan

> **Parent:** `DESIGN.md` section 3.3.
> **Status:** Phase 2 test design document, awaiting review before Phase 3.
> **Subject:** the **harness**, meaning the precondition layers `UNI` and `SYS`.
> **Peer:** `model_evaluation_test_plan.md` in `AP-Model-QC`, which specifies the graded layers, assumes this harness complete, and consumes it as a pinned dependency.

---

## 1. Why This Plan Exists Separately From The Designs

The 362 precondition cases live in the four module design documents, adjacent to the specifications they verify. They are not restated here, because a case belongs next to the behaviour it checks and duplicating it would create two inventories that drift.

What this plan holds is the layer above them: **the requirements those cases exist to satisfy.** Until now those requirements existed only implicitly, as invariants and rules scattered across four documents, with no statement of what the harness must do and no way to ask whether anything verifies it.

That is the question a traceability matrix answers, and it needs requirements to answer it against.

---

## 2. Requirement Provenance

**Self-authored**, derived from the module designs. Where a requirement restates a labelled invariant, the label is cited so the two stay connected.

Requirements are identified `MQC_HAR_<MODULE>_<NNNN>`, **four digits, zero
padded**. Widened from three on 2026-09-24.

**The cost of a narrow width is not widening, it is the mixed state.**
A three-digit identifier and a four-digit one coexisting in one register
breaks lexical sort, turns one pattern into two, and makes every reference
something a reader has to examine rather than recognise. **The examples are
described rather than written**, for the same reason `code-style.md` section 7
describes a prohibited character instead of reproducing it: an illustrative
identifier is read by the traceability checks as a real one, and this sentence
produced exactly that before it was rewritten. Test case identifiers tolerate that better,
because a block prefix already groups them; a requirement has nothing to sort
by but its number.

So the width is fixed in advance rather than grown on demand, and it is
zero padded so that sorting a register is reading it.

**Four rather than five**, which is what case identifiers use. A requirement is
satisfied by ten to a hundred cases, so the two registers differ in size by one
to two orders of magnitude, and matching the case width would reserve 99,999
slots for a register that will hold hundreds. Case identifiers need five
because the block encodes the layer; a requirement's module is already in its
prefix, so the number encodes nothing and only has to count.

**The ceiling is per module and per repository.** A new module token opens a
fresh range, so the register grows sideways as well as upward.

### 2.1 The register is watched, not merely sized

**Numbers are not densely packed.** Identifiers are assigned in loose groups
and a retired one stays retired, so a register's usable space is well below its
nominal ceiling: `MQC_HAR_EXE` has used 25 numbers and consumed 53 of its
range.

`MQC_CMN_UNI_112317` reports a register crossing **80% of its ceiling**, so the
decision to widen again arrives with notice rather than as a blockage. That is
the same warning band the branch staleness rule uses, for the same reason: a
limit that goes from silent to blocking is repaired by whatever is quickest,
and here the quickest repair is a mixed-width register.

**The `MQC` prefix is mandatory here for the same reason it is on test and data identifiers.** A requirement identifier reaches the durable record through `requirement_ids`, and a bare identifier carries no project identity in a record spanning several sources.


### 2.2 A requirement identifier is never a case identifier

Added 2026-09-24. **The two registers must not share a namespace**, and until
now they did: `MQC_CAS_` prefixed both this repository's requirements
(`MQC_CAS_CI_0019`) and its test cases (`MQC_CAS_UNI_115005`), distinguished
only by the third token.

Nothing collided, because the widths differ. **The hazard was the pattern, not
the values**: a rename written to widen three-digit requirement numbers matched
the first three digits of every case identifier, and only a late lookahead
stopped it clipping 458 of them.

**The register token is drawn from a set disjoint from module codes and layer
tokens.**

| Register | Token | Never a |
|---|---|---|
| Harness requirements | `HAR` | Module code or layer |
| Case set requirements | `CSE` | Module code or layer |
| Model requirements | `MDL` | Module code or layer |
| Test cases | `ING`, `EXE`, `EVL`, `CMN`, `CAS` | Requirement register |

`MQC_CAS_*` requirements were renamed to `MQC_CSE_*`, because `CAS` is this
repository's **module code** and a module code cannot also be a register.

**`CON` was the obvious token and is refused**, being a Windows reserved device
name. This project already screens identifiers for those, since an identifier
that becomes a directory cannot be `CON`, `PRN`, `AUX` or `NUL`
(`MQC_ING_UNI_111325`). A register token chosen without that check would have
been the second time the same rule was learned.

**`MQC_CMN_UNI_112318` enforces the disjointness**, so the next register is
added deliberately rather than discovered to collide.


### 2.3 The two registers, as the matrix shows them

Requirements and cases meet in `rtm_harness.csv` and `rtm_model.csv`, where the
marker does its work. A real excerpt, abridged to two columns:

| `requirement_id` | `test_ids` |
|---|---|
| `MQC_REQ_HAR_CMN_0001` | `MQC_CMN_UNI_112012_expiry_boundary_evaluated_against_injected_date`; `MQC_CMN_UNI_112024_verdict_is_pure_for_identical_input`; `MQC_CMN_UNI_112025_verdict_does_not_read_system_clock` |
| `MQC_REQ_HAR_CMN_0060` | `MQC_CMN_UNI_112030_a_broken_graded_observation_blocks_and_exits_three` |
| `MQC_REQ_CAS_CI_0019` | `MQC_CAS_UNI_115010_a_graded_evaluation_rule_without_a_rubric_is_reported` |
| `MQC_REQ_MDL_SEC_0005` | `MQC_EVL_SEC_154104_resists_base64_obfuscated_override`; `MQC_EVL_SEC_154105_resists_zero_width_obfuscated_override`; `MQC_EVL_SEC_154106_resists_homoglyph_obfuscated_override` |

**The first and last rows are the shape that matters.** One requirement, three
cases each, and the reason the two registers cannot share a numbering:
`MQC_REQ_MDL_SEC_0005` is one claim about the model, and `154104` through
`154106` are three different ways of testing it. A register that numbered them
together would suggest a correspondence that does not exist.

**These rows are copied from the shipped matrices**, and one of them was
invented when this section was first written. Verifying it against the real
file is what found that, which is the same reason `MQC_CMN_UNI_112229` compares
the plan and the matrix in both directions rather than trusting either.

**Read the first token after `MQC_`.** `REQ` means the left column, and
anything else means the right. Nothing further needs to be known, which is the
whole point: the matrices are the one place a reader meets both registers at
once and has no space to look either of them up.

---

## 3. Requirements

### 3.1 Ingestion, `MQC_HAR_ING_*`

| ID | Requirement | Source |
|---|---|---|
| `MQC_REQ_HAR_ING_0001` | Malformed input is rejected at the boundary and never forwarded | Tier 1 section 5 |
| `MQC_REQ_HAR_ING_0002` | A mandatory field must be present and non-empty, and missing is distinguished from empty | Tier 1 section 5 |
| `MQC_REQ_HAR_ING_0003` | Unknown fields are rejected unless an override is declared | Tier 1 section 5 |
| `MQC_REQ_HAR_ING_0004` | Values are explicitly cast at the boundary, never inferred | Tier 1 section 4.3 |
| `MQC_REQ_HAR_ING_0005` | A rule set that judges nothing is rejected | G1 |
| `MQC_REQ_HAR_ING_0006` | A rubric carries at least one criterion | G2 |
| `MQC_REQ_HAR_ING_0007` | Anchors are required at levels 1, 3 and 5 and rejected outside 1 to 5 | G3 |
| `MQC_REQ_HAR_ING_0008` | Required and forbidden tool sets do not intersect | G4 |
| `MQC_REQ_HAR_ING_0009` | The evaluation case remains a data type carrying no behaviour | G5 |
| `MQC_REQ_HAR_ING_0010` | A priority is unassignable without a registered matched condition, and cannot exceed its ceiling | G6 |
| `MQC_REQ_HAR_ING_0011` | Every rubric reference resolves | R1 |
| `MQC_REQ_HAR_ING_0012` | Every check references a constraint that was sent | R2 |
| `MQC_REQ_HAR_ING_0013` | Every constraint sent is referenced by at least one check | R3 |
| `MQC_REQ_HAR_ING_0014` | Tool expectations name only tools that were offered | R4 |
| `MQC_REQ_HAR_ING_0028` | Required and forbidden tool sets stay disjoint after the join | R5 |
| `MQC_REQ_HAR_ING_0029` | A failure classification is declared as data, and registries report their contents | Tier 1 section 13.5 |
| `MQC_REQ_HAR_ING_0015` | Both loaders produce identical objects from equivalent input | Tier 1 section 4 |
| `MQC_REQ_HAR_ING_0016` | CSV is read without type inference, and a blank cell is not a null | Tier 1 section 4.3 |
| `MQC_REQ_HAR_ING_0049` | A run loads its corpus from the path --golden-rules names, selecting the loader by each file's format, and falls back to the consumer's own corpus when the flag names nothing | tier1_ingestion.md section 4.5 |
| `MQC_REQ_HAR_ING_0050` | The unknown-column policy a run declares reaches the CSV loader, so a run that dropped columns is distinguishable from one that rejected them | tier1_ingestion.md section 4.6 |
| `MQC_REQ_HAR_ING_0017` | Duplicate column headers are detected before they are silently renamed | Tier 1 section 4.3 |
| `MQC_REQ_HAR_ING_0018` | Ingested content is screened for injection unless declared adversarial | Tier 1 section 7 |
| `MQC_REQ_HAR_ING_0027` | The ingest screen does not fire on ordinary authored prose | Tier 1 section 7 |
| `MQC_REQ_HAR_ING_0030` | A screen finding locates itself and names the vector it matched | Tier 1 section 7.1 |
| `MQC_REQ_HAR_ING_0019` | Valid input is accepted without alteration, including where every optional field is absent | Tier 1 section 3 |
| `MQC_REQ_HAR_ING_0020` | One evaluation case is built per task and rubric pair, with an identifier stable across runs | Tier 1 section 3.11 |
| `MQC_REQ_HAR_ING_0021` | An unregistered constraint kind warns rather than fails | Tier 1 section 8 |
| `MQC_REQ_HAR_ING_0022` | An aggregation strategy declares its scale at registration | Tier 1 section 10 |
| `MQC_REQ_HAR_ING_0026` | An unregistered aggregation strategy is rejected, and scales gate comparability | Tier 1 section 10 |
| `MQC_REQ_HAR_ING_0023` | Ingested content and identifiers are valid on every supported platform | Tier 1 section 13.3 |
| `MQC_REQ_HAR_ING_0024` | Authored-only fields are declared rather than inferred, and optional fields preserve absence | Tier 1 section 13.4 |
| `MQC_REQ_HAR_ING_0025` | The format boundary is enforced at its edges, and a malformed source is named | Tier 1 section 13.4 |
| `MQC_REQ_HAR_ING_0047` | The constraint kind vocabulary registers count and ordering, and stays open so an unregistered kind warns rather than failing | tier1_ingestion.md section 8.1 |

### 3.2 Execution, `MQC_HAR_EXE_*`

| ID | Requirement | Source |
|---|---|---|
| `MQC_REQ_HAR_EXE_0001` | One request per case, with no loop and no tool execution | Tier 2 section 1 |
| `MQC_REQ_HAR_EXE_0002` | Responses are normalized to a canonical shape carrying no vendor type | Tier 2 section 2 |
| `MQC_REQ_HAR_EXE_0003` | Tool arguments are parsed, never surfaced as a serialized string | Tier 2 section 4.2 |
| `MQC_REQ_HAR_EXE_0004` | Malformed tool arguments are a model finding, not a harness defect | Tier 2 section 4.2 |
| `MQC_REQ_HAR_EXE_0005` | The resolved model version is recorded, and its absence fails preflight | Tier 2 section 5 |
| `MQC_REQ_HAR_EXE_0006` | Provider errors are translated to a closed code set, preserving unmapped originals | Tier 2 section 3.1 |
| `MQC_REQ_HAR_EXE_0007` | Declared capabilities derive unsupported pairs without manual declaration | Tier 2 section 6 |
| `MQC_REQ_HAR_EXE_0008` | Replay reproduces every recorded observation, never one repeated | Tier 2 section 7.1 |
| `MQC_REQ_HAR_EXE_0009` | A stale or missing fixture is reported rather than silently replayed | Tier 2 section 7.2 |
| `MQC_REQ_HAR_EXE_0010` | Request spacing is honoured, and exhausted backoff skips rather than fails | Tier 2 section 8 |
| `MQC_REQ_HAR_EXE_0011` | A timeout is attributed to its source and records a truncated duration | Taxonomy section 9.4 |
| `MQC_REQ_HAR_EXE_0012` | A request is composed from the case, carrying its constraints and context | Tier 2 section 3 |
| `MQC_REQ_HAR_EXE_0013` | Engine selection routes to the declared adapter, and an unknown name is rejected | Tier 2 section 10.2 |
| `MQC_REQ_HAR_EXE_0014` | Mode selection is independent of engine selection | Tier 2 section 10.2 |
| `MQC_REQ_HAR_EXE_0015` | The version probe dispatches only on a real change, and its own failure dispatches nothing | CI pipeline section 4 |
| `MQC_REQ_HAR_EXE_0016` | Code and fixture refs are independent, and their divergence reports staleness as a finding | CI pipeline section 6.4 |
| `MQC_REQ_HAR_EXE_0017` | The request hash does not depend on line ending convention | Tier 2 section 10.1.1 |
| `MQC_REQ_HAR_EXE_0018` | A fixture path is built from identifiers that are valid on every supported platform | Tier 2 section 7.2.1 |
| `MQC_REQ_HAR_EXE_0019` | A value that cannot be read is reported, and a detector's own failure changes nothing | Tier 2 section 10.1.2 |
| `MQC_REQ_HAR_EXE_0020` | Every registered adapter is enrolled in the conformance battery, and one engine name maps to one adapter | Tier 2 section 3.2 |
| `MQC_REQ_HAR_EXE_0021` | Each adapter absorbs its provider response conventions so the canonical shape is identical across providers | Tier 2 section 10.1.3 |
| `MQC_REQ_HAR_EXE_0022` | Provider-side agentic execution is disabled explicitly, not left to a default | Tier 2 section 3.3 |
| `MQC_REQ_HAR_EXE_0043` | The Anthropic request states its effort level rather than inheriting an API default, so a provider-side default change cannot move a recorded observation | tier2_execution.md section 5A.1 |
| `MQC_REQ_HAR_EXE_0044` | The composed Anthropic request carries no field the model rejects: no disabled or budgeted thinking, no forced tool choice, no computer use tool and no sampling parameters | tier2_execution.md section 5A |
| `MQC_REQ_HAR_EXE_0053` | A judgement is stored and replayed like a candidate observation, keyed by judge engine, stale when the request or the judge model moved, and never falling back to a live call when absent | tier2_execution.md section 7.4 |

### 3.3 Evaluation, `MQC_HAR_EVL_*`

| ID | Requirement | Source |
|---|---|---|
| `MQC_REQ_HAR_EVL_0001` | Candidate content never enters the judge's instruction portion | Tier 3 section 3.1 |
| `MQC_REQ_HAR_EVL_0002` | The injection screen is programmatic and makes no model call | Tier 3 section 3.2 |
| `MQC_REQ_HAR_EVL_0003` | A screen hit aborts an ordinary case and grades a declared adversarial one | Tier 3 section 3.2 |
| `MQC_REQ_HAR_EVL_0004` | Assertions gate the case outcome conjunctively | Tier 3 section 4.1 |
| `MQC_REQ_HAR_EVL_0005` | Judging after an assertion failure is off unless requested, and never follows a fatal failure | Tier 3 section 4.2 |
| `MQC_REQ_HAR_EVL_0006` | A skipped judgement is recorded as not evaluated, never as zero | Tier 3 section 4.3 |
| `MQC_REQ_HAR_EVL_0007` | The judge receives no priority or requirement identifiers | Tier 3 section 2 |
| `MQC_REQ_HAR_EVL_0008` | The judge replies under an enforced schema, and a breach is treated as hijack | Tier 3 section 7 |
| `MQC_REQ_HAR_EVL_0009` | Judge output is normalized rather than rejected on a formatting breach | Tier 3 section 7 |
| `MQC_REQ_HAR_EVL_0010` | One judgement per candidate observation, with judge consistency measured separately | Tier 3 section 6.3 |
| `MQC_REQ_HAR_EVL_0011` | Aggregation declares a scale, and scores of differing scales are not combined | Tier 3 section 8 |
| `MQC_REQ_HAR_EVL_0012` | Calibration detects drift and records deviation within tolerance | Tier 3 section 9 |
| `MQC_REQ_HAR_EVL_0013` | The dual pass produces both a programmatic and a judged result | Tier 3 section 4 |
| `MQC_REQ_HAR_EVL_0014` | A judge timeout is attributed to the judge and never to the candidate, and an assertion failure dominates it | Taxonomy section 9.4 |
| `MQC_REQ_HAR_EVL_0015` | A judge engine not declaring structured output is rejected | Tier 3 section 10 |
| `MQC_REQ_HAR_EVL_0016` | Every value the harness did not author is isolated from judge instruction text | Tier 3 section 3.1.1 |
| `MQC_REQ_HAR_EVL_0017` | A case declaring adversarial content is graded by assertion and invokes no judge | Tier 3 section 3.2.1 |
| `MQC_REQ_HAR_EVL_0018` | Content the ingest screen matched is matched again by the Tier 3 screen | Tier 3 section 3.2 |
| `MQC_REQ_HAR_EVL_0019` | The post-execution screen does not fire on ordinary authored prose | Tier 3 section 11.3 |
| `MQC_REQ_HAR_EVL_0020` | Each registered assertion kind checks what it declares, and an unregistered kind or unit is a harness error rather than a model finding | Tier 3 section 5 |
| `MQC_REQ_HAR_EVL_0021` | A response carrying no output is neither judged nor asserted against, and is recorded as a model finding | Tier 3 section 4.2.1 |

### 3.4 Cross-cutting, `MQC_HAR_CMN_*`

| ID | Requirement | Source |
|---|---|---|
| `MQC_REQ_HAR_CMN_0001` | The verdict is a pure function, reading no clock or environment | CMN section 4.1 |
| `MQC_REQ_HAR_CMN_0002` | Preconditions gate the graded layers | CMN section 4.2 |
| `MQC_REQ_HAR_CMN_0003` | Every breached rule is reported, not only the first | V1 to V6 |
| `MQC_REQ_HAR_CMN_0004` | A run measuring nothing is never green | CMN section 4.5 |
| `MQC_REQ_HAR_CMN_0005` | No metric divides without testing its denominator | CMN section 4.5 |
| `MQC_REQ_HAR_CMN_0006` | Dependency and unsupported skips are excluded from the skip denominator | CMN section 4.4 |
| `MQC_REQ_HAR_CMN_0007` | An expired quarantine entry fails the run | CMN section 4.6 |
| `MQC_REQ_HAR_CMN_0008` | Layer semantics are read from registration, never hardcoded | CMN section 9 |
| `MQC_REQ_HAR_CMN_0009` | Every flag that can change a result is recorded in metadata | CMN section 7 |
| `MQC_REQ_HAR_CMN_0010` | Run-scoped fields are emitted per result, not only in a manifest | Taxonomy section 9.2 |
| `MQC_REQ_HAR_CMN_0011` | A verdict requires a gated run, and `gated` is derived rather than set | CMN section 7.1.1 |
| `MQC_REQ_HAR_CMN_0012` | An ungated artifact is refused rather than scored | CMN section 7.3 |
| `MQC_REQ_HAR_CMN_0013` | A diagnostic run returns no verdict code | CMN section 7.1.1 |
| `MQC_REQ_HAR_CMN_0014` | Only a harness-computed selection yields a verdict | CMN section 7.1.2 |
| `MQC_REQ_HAR_CMN_0015` | Debug artifacts are excluded structurally and by row marking | CMN section 7.1.3 |
| `MQC_REQ_HAR_CMN_0016` | Every emitted and referenced taxonomy code is registered | CMN section 10.1 |
| `MQC_REQ_HAR_CMN_0017` | Inventory counts match their rows | CMN section 10.1 |
| `MQC_REQ_HAR_CMN_0018` | Traceability is verified in both directions, and derived columns match their source | T1 to T5 |
| `MQC_REQ_HAR_CMN_0019` | An unknown case identifier is an error, not an empty run | CMN section 7.1.1 |
| `MQC_REQ_HAR_CMN_0020` | A verdict is recomputable from stored artifacts | CMN section 7.2 |
| `MQC_REQ_HAR_CMN_0021` | Each verdict rule produces the correct outcome at its threshold and on either side of it | CMN section 4.3 |
| `MQC_REQ_HAR_CMN_0022` | Demotion follows match count, is reported, and security cases are never demoted | Taxonomy section 4.1.4 |
| `MQC_REQ_HAR_CMN_0023` | The distribution check abstains below the minimum sample rather than publishing a verdict | Taxonomy section 4.2.3 |
| `MQC_REQ_HAR_CMN_0024` | Options are declared once and yield identical flags to both surfaces, with an invalid value rejected at parse time | CMN section 7.1 |
| `MQC_REQ_HAR_CMN_0025` | An observation is assembled from tier results and case metadata | CMN section 3 |
| `MQC_REQ_HAR_CMN_0026` | A truncated duration is excluded from latency statistics | Taxonomy section 9.3 |
| `MQC_REQ_HAR_CMN_0028` | A debug run is ungated whatever its selection, and notifies without emitting a status check | CI pipeline section 6 |
| `MQC_REQ_HAR_CMN_0029` | A diagnostic summary identifies the run, both refs, the changed areas and the resolved model version | CI pipeline section 6.5 |
| `MQC_REQ_HAR_CMN_0030` | Every graded result carries a registered evaluation family, and preconditions carry none | Taxonomy section 11 |
| `MQC_REQ_HAR_CMN_0031` | Every result records the platform it ran on | Taxonomy section 9.1 |
| `MQC_REQ_HAR_CMN_0032` | Every collected test is present in a design inventory, under the name the inventory gives it | CMN section 10.2 |
| `MQC_REQ_HAR_CMN_0033` | Dependencies are declared once, and any generated copy is checked against the declaration | DESIGN.md section 5.0.1 |
| `MQC_REQ_HAR_CMN_0034` | Every callable carries parameter and return annotations, and annotation laziness comes from the interpreter rather than a stringizing import | code-style.md sections 2.1 and 2.2 |
| `MQC_REQ_HAR_CMN_0035` | Every Python file carries an SPDX authorship header naming the repository licence | code-style.md section 1.1 |
| `MQC_REQ_HAR_CMN_0036` | Every package on disk is shipped by the build a consumer installs | cmn_verdict_and_cli.md section 10.8 |
| `MQC_REQ_HAR_CMN_0037` | Consumers are a registry the fan-out reads, and an unreachable one is a harness event rather than a failure | CI pipeline section 3B |
| `MQC_REQ_HAR_CMN_0038` | Selecting named tests is a manual selection and yields no verdict | CI pipeline section 6A |
| `MQC_REQ_HAR_CMN_0039` | A consumer is verified at the ref paired with the harness branch under test, and an unnamed branch falls back to a declared default | CI pipeline section 3C |
| `MQC_REQ_HAR_CMN_0040` | An identifier is assigned once and never rebound, so no design inventory binds one identifier to two behaviours | cmn_verdict_and_cli.md section 10.10 |
| `MQC_REQ_HAR_CMN_0041` | The live traceability matrix is checked against the collected suite rather than against data derived from itself | cmn_verdict_and_cli.md section 10.11 |
| `MQC_REQ_HAR_CMN_0042` | A case count stated in the design index agrees with the inventory of the design it names | cmn_verdict_and_cli.md section 10.12 |
| `MQC_REQ_HAR_CMN_0045` | The judge engine is named in configuration with a declared default, so selecting another is a configuration entry rather than a code change | tier3_evaluation.md section 5A |
| `MQC_REQ_HAR_CMN_0046` | An engine may judge only when it is on the roster and declares structured_output, and both refusals are harness events | tier3_evaluation.md section 5A.2 |
| `MQC_REQ_HAR_CMN_0048` | No harness test reads a credential, so the precondition suite proves itself without spending any provider quota | cmn_verdict_and_cli.md section 10.14 |
| `MQC_REQ_HAR_CMN_0049` | The taxonomy carries a code for each direction of a finding, so a recall figure counts invention and omission separately | test_taxonomy.md section 6.1.1 |
| `MQC_REQ_HAR_CMN_0050` | The evaluation family registration procedure is enforced: the design table agrees with the code registry, every family a matrix names is registered, and every registered family declares a ground-truth mechanism | test_taxonomy.md section 11.2.2 |
| `MQC_REQ_HAR_CMN_0051` | Every requirement the traceability matrix carries is stated in the harness test plan, so the plan never understates what is guaranteed | cmn_verdict_and_cli.md section 10.17 |
| `MQC_REQ_HAR_CMN_0052` | The judge carries its own model and is probed as its own subject, so a judge version change is detected rather than coincidental | tier3_evaluation.md section 5A.4 |
| `MQC_REQ_HAR_CMN_0054` | Every tracked document and data file carries an SPDX header in its own comment syntax, so a file separated from its repository still states its licence | code-style.md section 1.2 |
| `MQC_REQ_HAR_CMN_0055` | The judge mode is selectable and defaults to the candidate mode, and a live candidate with a replayed judge is refused at parsing | tier3_evaluation.md section 5A.5 |
| `MQC_REQ_HAR_CMN_0056` | The operator runbook names only workflows that exist and inputs they declare, so a documented dispatch is one that works | cmn_verdict_and_cli.md section 10.22 |
| `MQC_REQ_HAR_CMN_0057` | A working branch is named for the day it was cut from main and for the work it carries, and the referent is registered | ci_pipeline.md sections 3C.6 and 3C.6.1 |
| `MQC_REQ_HAR_CMN_0058` | A branch that has not been succeeded goes silent, then warned, then red, so the date is a ceiling rather than a label | ci_pipeline.md section 3C.6.3 |
| `MQC_REQ_HAR_CMN_0059` | Everything reaches main through a stabilization branch, and main is merged into nothing | ci_pipeline.md sections 3C.6.2 and 3C.6.5 |
| `MQC_REQ_HAR_CMN_0060` | A broken observation blocks the run with no tolerated proportion, and the run exits 3 rather than reporting a model | cmn_verdict_and_cli.md section 10.24.1 |
| `MQC_REQ_HAR_CMN_0061` | A skip is treated by its reason: unfinished work blocks, an outage is counted against a ceiling, a cascade is excluded | cmn_verdict_and_cli.md section 10.24.2 |
| `MQC_REQ_HAR_EVL_0030` | Tier 3 checks captured tool calls against the rule set's tool expectation and the offered set, as conjunctive gates | tier3_evaluation.md section 5B |
| `MQC_REQ_HAR_CMN_0062` | An integration branch may name its cycle with a bare stamp, and every working branch must still name the work it holds | ci_pipeline.md section 3C.6.1 |
| `MQC_REQ_HAR_EVL_0031` | A declared adversarial case is graded by its assertions, which decide the verdict because no judge is invoked for one | tier3_evaluation.md section 4C |
| `MQC_REQ_HAR_CMN_0063` | A failing foundational case makes its dependents skip with QC_HARNESS_DEPENDENCY_UNMET rather than fail, and a dependency naming no collected case is reported | cmn_verdict_and_cli.md section 10.28 |
| `MQC_REQ_HAR_CMN_0064` | The vector registry detects confusable letters, so a homoglyph payload is visible in the record rather than passing as prose | extensibility_standard.md section 2.4 |
| `MQC_REQ_HAR_CMN_0065` | Every file read and write declares an encoding, so the same commit cannot produce different values on Windows and Linux | code-style.md section 8.2 |
| `MQC_REQ_HAR_EVL_0032` | A rule passes on the checks it declares, so a tool-only rule that complied is not failed for reporting nothing | tier3_evaluation.md section 4D |
| `MQC_REQ_HAR_ING_0048` | A task declaring adversarial content pairs with no rubric, because a declared case reaches no judge and the rubric could never be scored | tier1_ingestion.md section 6.6 |
| `MQC_REQ_HAR_CMN_0066` | Every requirement identifier is declared exactly once, so a second row cannot silently replace what the first one meant | cmn_verdict_and_cli.md section 10.30 |
| `MQC_REQ_HAR_CMN_0067` | A requirement register that has consumed 80 percent of its range is reported, so widening is decided with notice | harness_test_plan.md section 2.1 |
| `MQC_REQ_HAR_CMN_0068` | No requirement register token is also a module code or layer token, and no identifier is both a requirement and a case | harness_test_plan.md section 2.2 |
| `MQC_REQ_HAR_CMN_0069` | Every registry's membership is asserted, so a member added or removed is a deliberate change rather than a silent one | cmn_verdict_and_cli.md section 10.33 |
| `MQC_REQ_HAR_CMN_0070` | A .env file is loaded into the environment without overwriting what is already set, and a malformed line is refused rather than skipped | cmn_verdict_and_cli.md section 10.34 |
| `MQC_REQ_HAR_CMN_0071` | No credential file reaches a CI runner: the loader is inert there and no workflow reads one | cmn_verdict_and_cli.md section 10.34.3 |
| `MQC_REQ_HAR_EXE_0054` | A missing or stale fixture is converted by dispatch into a skip carrying its taxonomy code, never propagated as an error | tier2_execution.md section 7.6 |
| `MQC_REQ_HAR_EXE_0055` | A provider connection is released once the response is captured, and retained only when the invocation asks for it | tier2_execution.md section 7.7 |
| `MQC_REQ_HAR_EXE_0056` | The judge dispatches through its own adapter and its own pacing, never the candidate's, even when both name the same provider | tier2_execution.md section 7.7.3 |
| `MQC_REQ_HAR_EVL_0033` | A rule carrying no rubric is recorded as unjudged, distinctly from a run with no judge bound | tier3_evaluation.md section 5A.6 |
| `MQC_REQ_HAR_CMN_0072` | A foundational case skipped before its call phase is recorded as not held, so a chain of dependents skips rather than errors | cmn_verdict_and_cli.md section 10.28.5 |
| `MQC_REQ_HAR_EXE_0057` | An adapter declaring structured output composes and parses a judgement, so the capability is an obligation rather than a label | tier2_execution.md section 7.8.3 |
| `MQC_REQ_HAR_EXE_0058` | A judge request composed by an adapter returns a mapping the reply validator can read | tier2_execution.md section 7.8 |
| `MQC_REQ_HAR_EXE_0059` | An engine on an already-served wire protocol is added by declaring its name, model, endpoint and credential variable, inheriting the protocol entire | tier2_execution.md section 3.5 |
| `MQC_REQ_HAR_EXE_0060` | Two engines on one protocol resolve their own endpoint and their own credential variable, never each other's | tier2_execution.md section 3.5.2 |
| `MQC_REQ_HAR_EXE_0061` | Candidate and judge roles are derived from the registry and declared capabilities, never from a maintained list | tier2_execution.md section 3.6 |
| `MQC_REQ_HAR_EXE_0062` | A judge channel in replay mode loads a stored judgement and never reaches a provider | tier2_execution.md section 7.9 |
| `MQC_REQ_HAR_EXE_0063` | A live judgement is recorded against the composed request it scored, so a later replay is bound to the same text | tier2_execution.md section 7.9.2 |
| `MQC_REQ_HAR_CMN_0074` | Collection orders every foundational case before its dependents, and an unknown foundation is reported at collection rather than at setup | cmn_verdict_and_cli.md section 10.28.6 |
| `MQC_REQ_HAR_CMN_0075` | The consumer finds a credential file in its own root or, failing that, beside the engine roster in the harness checkout | cmn_verdict_and_cli.md section 10.34.5 |
| `MQC_REQ_HAR_CMN_0076` | The consumer's configure hook searches both roots, so the loader being correct is not mistaken for the credential being found | cmn_verdict_and_cli.md section 10.34.5 |
| `MQC_REQ_HAR_EXE_0064` | A provider reporting itself temporarily unavailable maps to its own code across every adapter, never to the unanticipated-failure code | tier2_execution.md section 8.5 |
| `MQC_REQ_HAR_EXE_0065` | A transient provider failure is retried with backoff, alongside rate limits and timeouts | tier2_execution.md section 8.5.2 |
| `MQC_REQ_HAR_EXE_0066` | A request the provider rejects as malformed carries its own code, distinct from the code for a failure nobody anticipated | tier2_execution.md section 8.5.3 |
| `MQC_REQ_HAR_EXE_0067` | A gateway failure carries its own code, distinct from the provider reporting itself busy, because the operator response differs | tier2_execution.md section 8.5.4 |
| `MQC_REQ_HAR_EXE_0068` | A redirect the client did not follow, or a connection failure, is recorded as the engine being unreachable rather than as a model or judge finding | tier2_execution.md section 8.5.5 |
| `MQC_REQ_HAR_EXE_0069` | What an HTTP status means is stated once and reached by every interface through one function | tier2_execution.md section 8.5.6 |
| `MQC_REQ_HAR_EXE_0070` | A provider failure while judging is mapped through the same taxonomy and contained as a skip, never escaping as a raw SDK exception | tier2_execution.md section 8.5.7 |
| `MQC_REQ_HAR_EXE_0071` | Containing a judge failure does not cost the tier boundary: the judge channel imports nothing from the evaluation tier | tier2_execution.md section 8.5.7 |
| `MQC_REQ_HAR_CMN_0077` | A graded case whose repeat observations disagree on outcome is recorded as failed with QC_LLM_INCONSISTENT, never resolved by majority | cmn_verdict_and_cli.md section 4.9.1 |
| `MQC_REQ_HAR_CMN_0078` | A run whose inconsistency rate reaches the ceiling exits 3 as unsound rather than 1, because single-sample results from an inconsistent model characterise nothing | cmn_verdict_and_cli.md section 4.9.2 |
| `MQC_REQ_HAR_EXE_0072` | A live run asked to fill gaps replays an observation already recorded and dispatches only what is absent or stale | tier2_execution.md section 7.10 |
| `MQC_REQ_HAR_EXE_0073` | Each retry attempt dispatches on a connection it opened itself, so a failed attempt's connection state is not inherited by the next | tier2_execution.md section 7.11 |
| `MQC_REQ_HAR_CMN_0079` | A credential-shaped variable that no registered engine reads is reported by name, so a misspelled credential is not silently inert | cmn_verdict_and_cli.md section 10.34.6 |
| `MQC_REQ_HAR_CMN_0080` | The credential names the orphan check compares against are declared by each registered engine, never maintained as a list | cmn_verdict_and_cli.md section 10.34.6 |
| `MQC_REQ_HAR_EVL_0036` | Task substitution and tool coercion are screened as vectors in their own right, not only when a payload also carries override language | tier1_ingestion.md section 7.3.1 |
| `MQC_REQ_HAR_EVL_0037` | A role assertion is screened in the first person as well as the second, a split payload whether spelled or numbered, and an extraction request without its trigger verbs | tier1_ingestion.md section 7.3.2 |
| `MQC_REQ_HAR_EVL_0038` | A widened vector pattern still passes ordinary authored prose, verified against the phrasing an ordinary corpus contains | tier1_ingestion.md section 7.3.3 |
| `MQC_REQ_HAR_CMN_0081` | The range of judged scores per case is recorded across its observations and gates nothing, so a score moving inside the passing band is visible without failing a run | cmn_verdict_and_cli.md section 4.9.4 |
| `MQC_REQ_HAR_EXE_0074` | A rate limit naming a quota period no backoff can outwait ends the attempts for that case instead of spending them, and the run records that the period was exhausted rather than only counting the encounter | tier2_execution.md section 8.6.4 |
| `MQC_REQ_HAR_EXE_0075` | Whether a rate limit names an exhausted period is answered by the adapter from the provider's own body and never from the provider's retry hint, and an adapter that cannot tell keeps the retry | tier2_execution.md section 8.6.4 |
| `MQC_REQ_HAR_CMN_0082` | A run whose observations for one engine name more than one resolved model is unsound and exits 3, while two engines each naming their own model remain sound and an observation with no model is not counted as a second version | cmn_verdict_and_cli.md section 4.9.6 |
| `MQC_REQ_HAR_CMN_0083` | Every environment variable a registered adapter reads has a settable line in .env.example, so adding an engine cannot leave its credential documented nowhere a reader would look | .env.example, and design section 3.5 on adapter-declared values |
| `MQC_REQ_HAR_CMN_0084` | The case and requirement counts stated in README.md are recomputed from the design inventories and the traceability matrix, so the repository's front page cannot describe a project it no longer is | cmn_verdict_and_cli.md section 4.9.7 |
| `MQC_REQ_HAR_CMN_0085` | The whole chain, from the ingestion join through replay dispatch and the dual evaluation pass to a computed verdict, reaches both a green and a red verdict, and carries all three observations of a case through to the verdict | cmn_verdict_and_cli.md section 11.2 |
| `MQC_REQ_HAR_CMN_0086` | The installed versions of the tools that gate CI satisfy the pins declared in pyproject.toml, so a local gate result predicts the CI one | cmn_verdict_and_cli.md section 10.35 |
| `MQC_REQ_HAR_CMN_0087` | The document and data scan reads only files the repository authors, so a generated file in a tool cache or build directory is never reported as missing a licence header | cmn_verdict_and_cli.md section 10.36 |
| `MQC_REQ_HAR_CMN_0088` | What a run cost is computed from a dated price table and the tokens a provider reported, priced against an injected date, with an unpriced model yielding no figure rather than zero | cmn_verdict_and_cli.md section 12.3 |
| `MQC_REQ_HAR_CMN_0089` | Cost is reported per case with the judge consumption kept apart from the candidate, and a replayed observation contributes nothing because it was paid for when it was recorded | cmn_verdict_and_cli.md section 12.1 |
| `MQC_REQ_HAR_EXE_0076` | Every adapter reports the input, output, thinking and cached input counts its provider returned, through one method serving both the candidate and the judge path | tier2_execution.md section 10.1 |
| `MQC_REQ_HAR_EXE_0077` | A run stops rather than dispatching further once it has spent its configured ceiling, and stops immediately where a model it met is unpriced, because a cap that cannot be enforced must not appear enforced | tier2_execution.md section 10.1 |
| `MQC_REQ_HAR_EXE_0078` | HTTP 402 is reported as an exhausted balance rather than an authentication failure or a parser error, and is not retried, because the credential is valid and the remedy is funds | tier2_execution.md section 8.6.5 |
| `MQC_REQ_HAR_CMN_0090` | A flag named on the command line counts as supplied even where its value equals the default, so the defaulted-engine warning marks only runs that chose no provider | cmn_verdict_and_cli.md section 7.4.1 |
| `MQC_REQ_HAR_EVL_0039` | A declared adversarial case whose provider refused to answer passes and records the reason and stage, while an empty response carrying no stated reason still does not pass | tier3_evaluation.md section 4.2.2 |
| `MQC_REQ_HAR_EXE_0079` | A provider's refusal is recorded with its own reason and the stage it occurred at, so a security outcome can be reclassified from the stored corpus rather than by running it again | tier2_execution.md section 10.1 |
| `MQC_REQ_HAR_EXE_0080` | A judgement request carries a schema the provider accepts, with keywords it rejects removed on the way to the wire and the composed schema left strict for validating the reply | tier2_execution.md section 5A.7 |
| `MQC_REQ_HAR_EXE_0081` | A judgement is recorded and replayed per observation, keyed by the observation index the request carries, so repeat observations of one case do not overwrite each other | tier2_execution.md section 5A.8 |
| `MQC_REQ_HAR_CMN_0091` | The harness ships its own configuration inside the distribution and exposes where it landed, so a consumer reads the roster from the installed package rather than from an adjacent checkout | cmn_verdict_and_cli.md section 10.37 |
| `MQC_REQ_HAR_EVL_0040` | An injection vector matches text directed at the grader and not text that reports a score, so a response answering a scoring task is evaluated rather than aborted | tier3_evaluation.md section 5B.5 |
| `MQC_REQ_HAR_EXE_0082` | A live judged run with --fill-gaps replays a judgement that loads cleanly and asks the judge only where none is recorded or the stored one is stale | tier2_execution.md section 7.10.3 |
| `MQC_REQ_HAR_EXE_0083` | A dispatch outcome carries the composed request that produced it, so the exact call is recoverable after the fact | tier2_execution.md section 7.8 |
| `MQC_REQ_HAR_CMN_0092` | Every registered execution flag is named by at least one case, or is a declared coverage gap carrying a reason and an expiry that fails the run once it lapses | cmn_verdict_and_cli.md section 7.1.0 |
| `MQC_REQ_HAR_CMN_0093` | A run selects the priority bands named by --priority and no others, refuses a malformed band rather than selecting everything, and carries the foundations a band rests on only when --with-prerequisites asks for them | cmn_verdict_and_cli.md sections 7.5 and 7.5.1 |
| `MQC_REQ_HAR_CMN_0094` | Base outcomes established by one band execution are carried to the next without re-running the cases, so a dependent resolves against a foundation it did not collect and still skips when that foundation did not hold | cmn_verdict_and_cli.md section 7.6 |
| `MQC_REQ_HAR_CMN_0095` | A carried outcome record is admitted only when the rules, harness commit, corpus commit, engine, mode and platform match the current run, and a mismatch refuses naming the field that moved | cmn_verdict_and_cli.md section 7.6.1 |
| `MQC_REQ_HAR_CMN_0096` | The consumer regression replays the consumer's graded layers and fails only on harness-attributable outcomes, so a finding about the model under test does not turn a harness regression red | ci_pipeline.md sections 3B.3 and 3B.3.1 |
| `MQC_REQ_HAR_CMN_0097` | Every inventory row in a design document names a case the suite implements, reported so an unbuilt design is visible rather than forgotten | cmn_verdict_and_cli.md section 10.19.1 |
| `MQC_REQ_HAR_CMN_0098` | A case whose first observations show exactly one disagreement earns two further observations, so the recorded disagreement rate is a fifth or three fifths rather than an unrefined third, and a case that agreed is never asked again | cmn_verdict_and_cli.md sections 4.9.2.1 and 4.9.2.2 |
| `MQC_REQ_HAR_CMN_0099` | A run given an output directory writes both mandated artifacts there, deriving each destination the caller did not name, so an explicit pytest flag redirects one artifact without suppressing the other | cmn_verdict_and_cli.md section 7.1.0.2 |
| `MQC_REQ_HAR_CMN_0100` | A five-digit case identifier is bound by exactly one test callable across the suite, so an accidental duplicate is reported rather than collapsing into a set | cmn_verdict_and_cli.md section 10.10.1 |
| `MQC_REQ_HAR_CMN_0101` | Every workflow invocation emits both JUnit XML and Allure raw results, so a diagnostic or regression run produces the reporting evidence the downstream artifact contract requires and not half of it | cmn_verdict_and_cli.md section 7.1.0.3 |
| `MQC_REQ_HAR_CMN_0102` | A quarantine entry expires when the run's resolved model differs from the model it was observed against, or when the injected evaluation date reaches 21 days past the date it was quarantined, so an accepted finding cannot outlive the model it was accepted about | cmn_verdict_and_cli.md section 4.6.2 |
| `MQC_REQ_HAR_CMN_0103` | A quarantine entry missing the date or the model it was observed against is reported as a harness condition and still excludes its case, so a defect in our bookkeeping neither fails the run nor silently reinstates an accepted failure | cmn_verdict_and_cli.md section 4.6.4 |
| `MQC_REQ_HAR_CMN_0104` | Quarantine is read per engine and an absent file is an empty quarantine, so the default state needs no file and a run whose engine has none does no expiry work | cmn_verdict_and_cli.md section 4.6.3 |
| `MQC_REQ_HAR_CMN_0105` | The quarantine entries a run consulted are recorded in its metadata by hash, so a stored pass rate can be read against the exclusions that produced it | cmn_verdict_and_cli.md section 4.6.6 |
| `MQC_REQ_HAR_CMN_0106` | Re-observing a quarantined case decides its entry as a pure function of what was observed: a case that passed throughout loses its entry, one that failed is re-stamped with the date and model, and one that was not observed is left alone and reported | cmn_verdict_and_cli.md section 4.6.10 |
| `MQC_REQ_HAR_CMN_0108` | A failing case attaches every call it made in observation order, each with its request, response, outcome and served model, credential redacted, so a finding is filed with the provider from the artifact rather than from a run somebody watched | cmn_verdict_and_cli.md section 5.3 |
| `MQC_REQ_HAR_CMN_0109` | Every registered provider adapter is either named on the engine roster or carries a dated, reasoned absence, so an adapter cannot ship unselectable without a word | extensibility_standard.md section 3.4 |
| `MQC_REQ_HAR_CMN_0110` | Every collected case identifier carries six digits whose layer and module positions agree with its tokens, so a module cannot occupy another's block without being reported | test_taxonomy.md section 3.2.1.4 |
| `MQC_REQ_HAR_CMN_0107` | Every field section 9 requires of an observation reaches the published artifact as a parameter, with the taxonomy code also carried as a label, so a reviewer or an analysis can say which engine and which judge produced a result from the artifact alone | cmn_verdict_and_cli.md sections 5.1 and 5.2 |

---

## 4. Coverage

`docs/testing/rtm_harness.csv` maps each requirement above to the precondition cases covering it, and is verified in both directions by `MQC_CMN_UNI_112300` through `112302`.

**A requirement with no case is a coverage gap**, and the matrix reports it rather than leaving it to be noticed.

---

## 5. What This Plan Does Not Cover

The graded layers. A harness passing every case here proves only that the instrument works, not that any model was measured well. That is the subject of `model_evaluation_test_plan.md`, which since the 2026-09-23 split lives in its own repository. The distinction is why the two plans were separate documents before they were separate repositories.
