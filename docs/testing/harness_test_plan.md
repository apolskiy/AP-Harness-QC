<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# Harness Test Plan

> **Parent:** `DESIGN.md` section 3.3.
> **Status:** Implemented, and traced both ways in `rtm_harness.csv`.
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
| `MQC_REQ_HAR_ING_0013` | Every constraint sent is referenced by at least one check among the rules the task names | R3 |
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
| `MQC_REQ_HAR_EXE_0021` | Each adapter absorbs its provider response conventions so the canonical shape is identical across providers, and an adapter normalising a refusal records the provider's own word for it | Tier 2 section 10.1.3 |
| `MQC_REQ_HAR_EXE_0022` | Provider-side agentic execution is disabled explicitly, not left to a default | Tier 2 section 3.3 |
| `MQC_REQ_HAR_EXE_0043` | The Anthropic request states its effort level rather than inheriting an API default, so a provider-side default change cannot move a recorded observation | tier2_execution.md section 5A.1 |
| `MQC_REQ_HAR_EXE_0044` | The composed Anthropic request carries no field the model rejects: no disabled or budgeted thinking, no forced tool choice, no computer use tool and no sampling parameters | tier2_execution.md section 5A |
| `MQC_REQ_HAR_EXE_0053` | A judgement is stored and replayed like a candidate observation, keyed by candidate engine and judge engine together, stale when the request or the judge model moved, and never falling back to a live call when absent | tier2_execution.md section 7.4 |

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
| `MQC_REQ_HAR_CMN_0019` | An unknown named test is an error rather than an empty run, established by `--tests` since 2026-10-03; `--case` is retired and its two cases with it | CMN section 7.1.1 |
| `MQC_REQ_HAR_CMN_0020` | A verdict is recomputable from stored artifacts | CMN section 7.2 |
| `MQC_REQ_HAR_CMN_0021` | Each verdict rule produces the correct outcome at its threshold and on either side of it | CMN section 4.3 |
| `MQC_REQ_HAR_CMN_0022` | Demotion follows match count, is reported, and security cases are never demoted | Taxonomy section 4.1.4 |
| `MQC_REQ_HAR_CMN_0023` | The distribution check abstains below the minimum sample rather than publishing a verdict | Taxonomy section 4.2.3 |
| `MQC_REQ_HAR_CMN_0024` | Options are declared once and yield identical flags to both surfaces, with an invalid value rejected at parse time | CMN section 7.1 |
| `MQC_REQ_HAR_CMN_0025` | An observation is assembled from tier results and case metadata | CMN section 3 |
| `MQC_REQ_HAR_CMN_0026` | A truncated duration is excluded from latency statistics | Taxonomy section 9.3 |
| `MQC_REQ_HAR_CMN_0028` | A debug run is ungated whatever its selection, and notifies without emitting a status check | CI pipeline section 6 |
| `MQC_REQ_HAR_CMN_0029` | A diagnostic summary identifies the run, both refs, the changed areas and the resolved model version | CI pipeline section 6.5 |
| `MQC_REQ_HAR_CMN_0030` | Every graded result carries its registered evaluation families, each value checked individually because the relation is many to many, and preconditions carry none | Taxonomy section 11 |
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
| `MQC_REQ_HAR_CMN_0049` | The taxonomy carries a code for each direction of a finding, so a recall figure counts invention and omission separately | harness_test_taxonomy.md section 6.1.1 |
| `MQC_REQ_HAR_CMN_0050` | The evaluation family registration procedure is enforced: the design table agrees with the code registry, every family a matrix names is registered, and every registered family declares a ground-truth mechanism | harness_test_taxonomy.md section 11.2.2 |
| `MQC_REQ_HAR_CMN_0051` | Every requirement the traceability matrix carries is stated in the harness test plan, so the plan never understates what is guaranteed | cmn_verdict_and_cli.md section 10.17 |
| `MQC_REQ_HAR_CMN_0052` | The judge carries its own model and is probed as its own subject, so a judge version change is detected rather than coincidental | tier3_evaluation.md section 5A.4 |
| `MQC_REQ_HAR_CMN_0054` | Every tracked document and data file carries an SPDX header in its own comment syntax, so a file separated from its repository still states its licence | code-style.md section 1.2 |
| `MQC_REQ_HAR_CMN_0055` | The judge mode is selectable and defaults to the candidate mode, and a live candidate with a replayed judge is refused at parsing | tier3_evaluation.md section 5A.5 |
| `MQC_REQ_HAR_CMN_0056` | The operator runbook names only workflows that exist and inputs they declare, so a documented dispatch is one that works | cmn_verdict_and_cli.md section 10.22 |
| `MQC_REQ_HAR_CMN_0057` | A working branch is named for the day it was cut from main and for the work it carries, and the referent is registered | harness_ci_pipeline.md sections 3C.6 and 3C.6.1 |
| `MQC_REQ_HAR_CMN_0058` | A branch that has not been succeeded goes silent, then warned, then red, so the date is a ceiling rather than a label | harness_ci_pipeline.md section 3C.6.3 |
| `MQC_REQ_HAR_CMN_0059` | Everything reaches main through a stabilization branch, and main is merged into nothing | harness_ci_pipeline.md sections 3C.6.2 and 3C.6.5 |
| `MQC_REQ_HAR_CMN_0060` | A broken observation blocks the run with no tolerated proportion, and the run exits 3 rather than reporting a model | cmn_verdict_and_cli.md section 10.24.1 |
| `MQC_REQ_HAR_CMN_0061` | A skip is treated by its reason: unfinished work blocks the run, a cause of ours or the network's leaves the pass rate, and everything else is counted as the failure it is | cmn_verdict_and_cli.md section 10.24.2 |
| `MQC_REQ_HAR_EVL_0030` | Tier 3 checks captured tool calls against the rule set's tool expectation and the offered set, as conjunctive gates | tier3_evaluation.md section 5B |
| `MQC_REQ_HAR_CMN_0062` | An integration branch may name its cycle with a bare stamp, and every working branch must still name the work it holds | harness_ci_pipeline.md section 3C.6.1 |
| `MQC_REQ_HAR_EVL_0031` | A declared adversarial case is graded by its assertions, which decide the verdict because no judge is invoked for one | tier3_evaluation.md section 4C |
| `MQC_REQ_HAR_CMN_0063` | A failing foundational case makes its dependents skip with QC_HARNESS_DEPENDENCY_UNMET rather than fail, and a dependency naming no collected case is reported | cmn_verdict_and_cli.md section 10.28 |
| `MQC_REQ_HAR_CMN_0064` | The vector registry detects confusable letters, so a homoglyph payload is visible in the record rather than passing as prose | harness_extensibility_standard.md section 2.4 |
| `MQC_REQ_HAR_CMN_0065` | Every file read and write declares an encoding, so the same commit cannot produce different values on Windows and Linux | code-style.md section 8.2 |
| `MQC_REQ_HAR_EVL_0032` | A rule passes on the checks it declares, so a tool-only rule that complied is not failed for reporting nothing | tier3_evaluation.md section 4D |
| `MQC_REQ_HAR_ING_0048` | A task declaring adversarial content pairs with no rubric, because a declared case reaches no judge and the rubric could never be scored | tier1_ingestion.md section 6.6 |
| `MQC_REQ_HAR_CMN_0066` | Every requirement identifier is declared exactly once, so a second row cannot silently replace what the first one meant | cmn_verdict_and_cli.md section 10.30 |
| `MQC_REQ_HAR_CMN_0067` | A requirement register that has consumed 80 percent of its range is reported, so widening is decided with notice | harness_test_plan.md section 2.1 |
| `MQC_REQ_HAR_CMN_0068` | No requirement register token is also a module code or layer token, and no identifier is both a requirement and a case | harness_test_plan.md section 2.2 |
| `MQC_REQ_HAR_CMN_0069` | Every registry's membership is asserted, so a member added or removed is a deliberate change rather than a silent one | cmn_verdict_and_cli.md section 10.33 |
| `MQC_REQ_HAR_CMN_0070` | A local .env is loaded without overwriting what is already set, and a line that is not an assignment is skipped with its number named | cmn_verdict_and_cli.md section 10.34 |
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
| `MQC_REQ_HAR_EVL_0041` | An assertion may ask whether a sentence asserts a pattern rather than whether the pattern appears, so a hedged or negated mention of a forbidden claim is not counted as making it | tier3_evaluation.md section 5.3 |
| `MQC_REQ_HAR_EVL_0042` | A forbidding claim assertion declaring no exclusions is refused as a configuration error, and an asserting one declaring exclusions likewise, so the kind cannot silently behave as a plain pattern match | tier3_evaluation.md section 5.3 |
| `MQC_REQ_HAR_EVL_0043` | A judgement the replay store cannot supply is recorded as a skip carrying the store's own harness code, with the observation's assertion results intact, so a recording gap is never reported as a model finding | tier3_evaluation.md section 6.5 |
| `MQC_REQ_HAR_EVL_0044` | A coercion screen counts a modal instruction to use something only where its subject is tool shaped, so ordinary prose saying a figure or a code should be used does not abort the observation | tier3_evaluation.md section 5.2.1 |
| `MQC_REQ_HAR_EVL_0045` | A claim assertion is scoped to one sentence and a single line break ends one, so a markdown heading does not join the line below it | tier3_evaluation.md section 5.3.1 |
| `MQC_REQ_HAR_EXE_0082` | A live judged run with --fill-gaps replays a judgement that loads cleanly and asks the judge only where none is recorded or the stored one is stale | tier2_execution.md section 7.10.3 |
| `MQC_REQ_HAR_EXE_0083` | A dispatch outcome carries the composed request that produced it, so the exact call is recoverable after the fact | tier2_execution.md section 7.12 |
| `MQC_REQ_HAR_EXE_0127` | A recorded fixture stores the composed request that produced the response, so the exact call a provider received is recoverable from the fixture alone | tier2_execution.md section 7.13 |
| `MQC_REQ_HAR_EXE_0128` | A stored request re-hashes to the hash recorded beside it, and a disagreement is reported as a stale fixture rather than replayed | tier2_execution.md section 7.13.1 |
| `MQC_REQ_HAR_EXE_0129` | No stored fixture carries a credential-shaped value, so storing the composed request cannot expose one | tier2_execution.md section 7.13.3 |
| `MQC_REQ_HAR_EXE_0130` | A gap-filling run dispatches an observation whose recording carries no request and replays one that does, so the field is filled without making an existing recording unreplayable | tier2_execution.md section 7.13.2 |
| `MQC_REQ_HAR_EXE_0131` | Every registered adapter declares how a recorded call is re-issued, the shared protocol declares it once for the engines speaking it, and an adapter declaring none emits no reproduction rather than a wrong one | consumer_ci.md section 9.5.3.1 |
| `MQC_REQ_HAR_EXE_0132` | HTTP 403 is reported as a refused request rather than an authentication failure and ends the case rather than the run, because 401 is about the caller and 403 about the request | tier2_execution.md section 8.6.7 |
| `MQC_REQ_HAR_EXE_0133` | A provider refusing a task that declares no adversarial content, in a run where it answered other requests, is recorded as a model over-refusal rather than as our own infrastructure failure | tier2_execution.md section 8.6.7 |
| `MQC_REQ_HAR_EXE_0134` | Recording an observation removes every observation in that pair whose stored hash differs, so a re-record needing fewer observations than the run before it cannot leave answers to a superseded request behind | tier2_execution.md section 7.14 |
| `MQC_REQ_HAR_EXE_0135` | A recorded call's reproduction is Python whose call arguments evaluate to the recorded request, so a ticket's snippet runs and re-issues the call that was made | consumer_ci.md section 9.5.3.1 |
| `MQC_REQ_HAR_EXE_0136` | An engine whose recorded request is the wire body also reproduces as a curl posting it unchanged to the engine's own endpoint, in a quoted heredoc naming the credential variable, and an engine whose recording is not the wire body offers none | consumer_ci.md section 9.5.3.1 |
| `MQC_REQ_HAR_EXE_0137` | An OpenAI-protocol engine on its own base URL reproduces with a client that takes that URL and the engine's credential variable by name, so the snippet runs with only that variable set | consumer_ci.md section 9.5.3.1 |
| `MQC_REQ_HAR_EXE_0138` | Every registered adapter reports what its provider declares about the requested model, read without sending a prompt, asked about the model the run requested and reduced to a mapping whose keys are sorted and which carries neither a null value nor a private field; an adapter whose provider declared nothing usable returns an empty mapping rather than raising | tier2_execution.md section 5.2 |
| `MQC_REQ_HAR_EXE_0139` | Preflight is invocable from a command line: it declares an entry point taking the baseline to compare against, where to write the changed engines and which roster to walk, and a run given no baseline exits 2 naming it rather than exiting 0 having done nothing | tier2_execution.md section 5.3 |
| `MQC_REQ_HAR_CMN_0092` | Every registered execution flag is named by at least one case, or is a declared coverage gap carrying a reason and an expiry that fails the run once it lapses | cmn_verdict_and_cli.md section 7.1.0 |
| `MQC_REQ_HAR_CMN_0093` | A run selects the priority bands named by --priority and no others, refuses a malformed band rather than selecting everything, and carries the foundations a band rests on only when --with-prerequisites asks for them, and refuses --with-prerequisites under a selection it cannot widen | cmn_verdict_and_cli.md sections 7.5 and 7.5.1 |
| `MQC_REQ_HAR_CMN_0094` | Base outcomes established by one band execution are carried to the next without re-running the cases, so a dependent resolves against a foundation it did not collect and still skips when that foundation did not hold | cmn_verdict_and_cli.md section 7.6 |
| `MQC_REQ_HAR_CMN_0095` | A carried outcome record is admitted only when the rules, harness commit, corpus commit, engine, mode and platform match the current run, and a mismatch refuses naming the field that moved | cmn_verdict_and_cli.md section 7.6.1 |
| `MQC_REQ_HAR_CMN_0096` | The consumer regression replays the consumer's graded layers and fails only on harness-attributable outcomes, so a finding about the model under test does not turn a harness regression red, and every script a workflow step runs resolves in the layout that step executes in | harness_ci_pipeline.md sections 3B.3 and 3B.3.1 |
| `MQC_REQ_HAR_CMN_0097` | Every inventory row in a design document names a case the suite implements, reported so an unbuilt design is visible rather than forgotten | cmn_verdict_and_cli.md section 10.19.1 |
| `MQC_REQ_HAR_CMN_0098` | A case whose first observations include any failure earns two further observations, so a reported failure rate rests on five observations rather than three and reads as a fifth rather than a third | cmn_verdict_and_cli.md sections 4.9.2.1 and 4.9.2.2 |
| `MQC_REQ_HAR_CMN_0099` | A run given an output directory writes both mandated artifacts there, deriving each destination the caller did not name, so an explicit pytest flag redirects one artifact without suppressing the other | cmn_verdict_and_cli.md section 7.1.0.2 |
| `MQC_REQ_HAR_CMN_0100` | A five-digit case identifier is bound by exactly one test callable across the suite, so an accidental duplicate is reported rather than collapsing into a set | cmn_verdict_and_cli.md section 10.10.1 |
| `MQC_REQ_HAR_CMN_0227` | A graded case whose outcome a rubric threshold can decide is reported where it claims P0 or P1, so a run never blocks on a number a judge produced, and a case priced at P2 carrying its severity condition alongside the rubric condition is accepted as a recorded demotion | harness_test_taxonomy.md section 4.1.2.1 |
| `MQC_REQ_HAR_CMN_0101` | Every workflow invocation emits both JUnit XML and Allure raw results, so a diagnostic or regression run produces the reporting evidence the downstream artifact contract requires and not half of it | cmn_verdict_and_cli.md section 7.1.0.3 |
| `MQC_REQ_HAR_CMN_0102` | A quarantine entry expires when the run's resolved model differs from the model it was observed against, or when the injected evaluation date reaches 21 days past the date it was quarantined, so an accepted finding cannot outlive the model it was accepted about | cmn_verdict_and_cli.md section 4.6.2 |
| `MQC_REQ_HAR_CMN_0103` | A quarantine entry missing the date or the model it was observed against is reported as a harness condition and still excludes its case, so a defect in our bookkeeping neither fails the run nor silently reinstates an accepted failure | cmn_verdict_and_cli.md section 4.6.4 |
| `MQC_REQ_HAR_CMN_0104` | Quarantine is read per engine and an absent file is an empty quarantine, so the default state needs no file and a run whose engine has none does no expiry work | cmn_verdict_and_cli.md section 4.6.3 |
| `MQC_REQ_HAR_CMN_0105` | The quarantine entries a run consulted are recorded in its metadata by hash, so a stored pass rate can be read against the exclusions that produced it | cmn_verdict_and_cli.md section 4.6.6 |
| `MQC_REQ_HAR_CMN_0106` | Re-observing a quarantined case decides its entry as a pure function of what was observed: a case that passed throughout loses its entry, one that failed is re-stamped with the date and model, and one that was not observed is left alone and reported | cmn_verdict_and_cli.md section 4.6.10 |
| `MQC_REQ_HAR_CMN_0108` | A failing case attaches every call it made in observation order, each with its request, response, outcome and served model, credential redacted, so a finding is filed with the provider from the artifact rather than from a run somebody watched | cmn_verdict_and_cli.md section 5.3 |
| `MQC_REQ_HAR_CMN_0109` | Every registered provider adapter is either named on the engine roster or carries a dated, reasoned absence, so an adapter cannot ship unselectable without a word | harness_extensibility_standard.md section 3.4 |
| `MQC_REQ_HAR_CMN_0110` | Every collected case identifier carries six digits whose layer and module positions agree with its tokens, so a module cannot occupy another's block without being reported | harness_test_taxonomy.md section 3.2.1.4 |
| `MQC_REQ_HAR_CMN_0111` | A run that passes reports every case its quarantine excluded and the priority band of each, with a blocking band raised as a warning, so a green cannot read as green over everything when a release blocker is open and accepted | cmn_verdict_and_cli.md section 4.6.11 |
| `MQC_REQ_HAR_CMN_0112` | The field list section 9 declares and the fields the code emits agree in both directions, so the normative list cannot fall behind the code and the code cannot emit a field the standard never declared | harness_test_taxonomy.md section 9.5 |
| `MQC_REQ_HAR_CMN_0113` | A case belonging to several families publishes all of them, and per-family cost totals attribute a shared case to each family it addresses, so the totals overlap and answer what a family costs to run rather than how the bill divides | harness_test_taxonomy.md section 11.7 |
| `MQC_REQ_HAR_CMN_0114` | A run selects the cases a fix wants re-run by evaluation family or by requirement, resolved through the traceability matrix the caller names, inclusive of a secondary family, and neither selection yields a verdict | cmn_verdict_and_cli.md section 7.7 |
| `MQC_REQ_HAR_CMN_0115` | A selection that cannot be resolved refuses the run rather than selecting nothing, and names what it could not resolve | cmn_verdict_and_cli.md section 7.7.3 |
| `MQC_REQ_HAR_CMN_0116` | A named test list is taken from a file holding one entry per line, and an entry in it matching no collected test is reported as a skip while the rest of the run proceeds | cmn_verdict_and_cli.md sections 7.8.1 and 7.8.3 |
| `MQC_REQ_HAR_CMN_0117` | Overriding the observation count is recorded in result metadata and makes the run unverdictable, so a run that measured a different population is distinguishable from one that did not | cmn_verdict_and_cli.md section 7.1.1 |
| `MQC_REQ_HAR_CMN_0118` | Every observation a run takes is published to the artifact as Allure parameters and a taxonomy label, so a collector can say which engine, mode and model produced a result without reading a log | cmn_verdict_and_cli.md sections 5.2 and 5.2.1 |
| `MQC_REQ_HAR_CMN_0119` | A failing case attaches every observation it took, each with its request, its response and the model that served it, credential-redacted, so a provider ticket is written from the artifact rather than from a run | cmn_verdict_and_cli.md section 5.3 |
| `MQC_REQ_HAR_CMN_0120` | A run selects the cases of named modules, refusing a module outside the registered set so a typo cannot select nothing and report green | cmn_verdict_and_cli.md section 7.7.5 |
| `MQC_REQ_HAR_CMN_0121` | Every tracked document is named in the document register and every path the register names resolves, so a documentation review reaches every document and a citation cannot dangle | harness_test_taxonomy.md section 12 |
| `MQC_REQ_HAR_ING_0122` | A rule set declares the evaluation families it grades, ordered with the primary first, every value registered and none repeated, so a graded result is attributable to a task and the primary is unambiguous | harness_test_taxonomy.md section 11.8 |
| `MQC_REQ_HAR_ING_0123` | A rule declaring a response-only judgement carries a rubric, and only such a rule may author a rubric on a declared adversarial task | tier1_ingestion.md sections 3.5 and 6.6 |
| `MQC_REQ_HAR_ING_0124` | A rubric's planted score is an integer from 1 to 5 that no criterion anchors, declared only on a rule judged on its answer alone | tier1_ingestion.md sections 3.5 and 3.6 |
| `MQC_REQ_HAR_ING_0125` | A rubric's planted score falls below the rubric's threshold, so a judgement returning it is one the rubric already fails and the fingerprint names the cause rather than being the only thing that fails it | tier1_ingestion.md section 3.6 |
| `MQC_REQ_HAR_CMN_0123` | A family or a tag selection resolves through the per-case index, so it returns the cases carrying that value and not the whole requirement row, and a value no case carries is refused by name | cmn_verdict_and_cli.md section 7.7.6 |
| `MQC_REQ_HAR_CMN_0124` | Every workflow step that can dispatch to a provider names a spend ceiling, so a live run cannot spend without a bound against an account with a monthly limit | harness_ci_pipeline.md section 8.2 |
| `MQC_REQ_HAR_EXE_0125` | An engine the adapter registry does not know is refused, naming what is registered, so the engine vocabulary is the roster rather than a list in the option registry | tier2_execution.md section 3.5 |
| `MQC_REQ_HAR_EXE_0126` | An engine that is not on the roster is refused when the run is configured, naming the rostered engines and both remedies, so a run cannot dispatch against an adapter default nobody configured | tier2_execution.md section 3.5.3 |
| `MQC_REQ_HAR_CMN_0127` | Pylint is run over the same paths wherever the command is written, in the workflows and in the documents a contributor copies, so a file cannot pass one gate and fail another | harness_ci_pipeline.md section 8.3.1 |
| `MQC_REQ_HAR_CMN_0128` | A tracked YAML file carrying a duplicated mapping key is reported, because a parse resolves it last-wins and discards the first silently while a schema validator rejects the file outright | harness_ci_pipeline.md section 8.3.2 |
| `MQC_REQ_HAR_CMN_0129` | No case defined in this repository belongs to a graded layer, the graded layers being read from the layer registry rather than named, so the suite here cannot come to hold a claim about a model and a green run here is a statement about the instrument alone | cmn_verdict_and_cli.md section 4.9.8 |
| `MQC_REQ_HAR_CMN_0130` | A collected test module defines no module-level function or non-test class, the supporting code living in a sibling module collection does not reach, so a case file reads as a list of claims and a helper is owned by an interface rather than privately re-derived per module | harness_test_taxonomy.md section 13 |
| `MQC_REQ_HAR_CMN_0131` | Every subprocess invocation carries a timeout, so a child that stalls fails the case with a named harness code rather than blocking until a runner cancels the job and reports a failure with no failing step | harness_test_taxonomy.md section 14 |
| `MQC_REQ_HAR_CMN_0132` | The overall report states each band's result and marks the total as deciding nothing, naming any failure in a release blocking band, so a healthy aggregate cannot stand in for a band that failed | cmn_verdict_and_cli.md section 7.11.1 |
| `MQC_REQ_HAR_CMN_0133` | A model name carrying a trailing ISO date prices at the rates of the base model it names, where the table carries that base, so a provider pinning a dated snapshot does not silently make a priced model unpriced | cmn_verdict_and_cli.md section 12.5 |
| `MQC_REQ_HAR_CMN_0134` | Every recording a case holds answers the same request, so a store refreshed in part is reported rather than discovered when an escalation first draws the observation that was left behind | cmn_verdict_and_cli.md section 12.4.1 |
| `MQC_REQ_HAR_CMN_0135` | An observation records every numbered step as a verifiable action and a verification, each carrying its outcome, so a failure names the step and the phase it stopped at and the steps that never ran are visible | harness_test_taxonomy.md section 8 |
| `MQC_REQ_HAR_CMN_0136` | A rule authoring no rubric reports its judge steps as not applicable rather than as an early stop, so a suite decided by its assertions is not read as having halted short | harness_test_taxonomy.md section 8 |
| `MQC_REQ_HAR_CMN_0137` | A quarantined case is skipped before a request is formed, so a case already known to fail spends no provider quota while it is being fixed | cmn_verdict_and_cli.md section 4.6.12 |
| `MQC_REQ_HAR_CMN_0138` | Superseded by MQC_REQ_HAR_CMN_0151 on 2026-10-11. It required a dependent of a failed foundation to be executed in replay and skipped live, and replay is where CI runs, so it required CI to produce a result that counts in no denominator | cmn_verdict_and_cli.md section 10.28.2.1 |
| `MQC_REQ_HAR_CMN_0139` | An unattributed observation is counted in no pass rate, skip rate, distribution or verdict, so an inquest cannot report one behaviour twice | cmn_verdict_and_cli.md section 10.28.2.1 |
| `MQC_REQ_HAR_CMN_0140` | A skipped case records its own observation and enters the pass-rate denominator without entering the numerator, so a rate is stated over what was selected rather than over whatever happened to run | cmn_verdict_and_cli.md section 4.6.13 |
| `MQC_REQ_HAR_CMN_0141` | A release blocking band passes a failing case only where the quarantine entry records the tracker reference in which product management announced the decision, and the pass names the case, the band and the reference | cmn_verdict_and_cli.md section 4.6.13 |
| `MQC_REQ_HAR_CMN_0142` | A skip is counted as a failure in the pass rate unless its cause was ours, the network's or a declared capability gap; an unattributed skip is counted, and a recorded release dispensation is the one thing that excuses one | harness_test_taxonomy.md section 7.4.1 |
| `MQC_REQ_HAR_CMN_0143` | The total and blocking-band skip ceilings are retired and fire for no population, and a configuration naming either still loads | harness_test_taxonomy.md section 7.4.1.0 |
| `MQC_REQ_HAR_CMN_0144` | A family registered at runtime is admitted, readable from the registry, and removable, leaving the registry exactly as it was found | harness_test_taxonomy.md section 11.6 |
| `MQC_REQ_HAR_CMN_0145` | An ungraded precondition that skipped fails the run with exit 3, whatever the reason it carried | harness_test_taxonomy.md section 7.5.1 |
| `MQC_REQ_HAR_CMN_0146` | A case declaring an environment scope this environment does not satisfy is deselected before it runs, leaving the run's total rather than reporting a skip inside it, and an unregistered scope is refused | harness_test_taxonomy.md section 7.5.1 |
| `MQC_REQ_HAR_CMN_0147` | Every tracked document under docs carries its repository's token in its filename, or a stated exemption, so an open editor tab says which checkout the file belongs to | code-style.md section 7.2 |
| `MQC_REQ_HAR_CMN_0148` | Every case announces its node identifier before it runs, so a crash between setup and a response leaves the module, the class and the case behind | harness_test_taxonomy.md section 8.3.1 |
| `MQC_REQ_HAR_CMN_0149` | Every test module carries a generated block naming the cases it holds, grouped by class in source order, and a block disagreeing with its module in either direction fails the run | testing-standards.md, A Test Module Lists The Cases It Holds |
| `MQC_REQ_HAR_CMN_0151` | A dependent whose foundation did not hold is skipped in every run but a gap-filling one, so CI reports pass, fail and skip and nothing else | cmn_verdict_and_cli.md section 10.28.2.3 |
| `MQC_REQ_HAR_CMN_0152` | A gap-filling live run dispatches a dependent whose foundation did not hold, records its response, and records the observation as unattributed | cmn_verdict_and_cli.md section 10.28.2.3 |
| `MQC_REQ_HAR_CMN_0153` | Every citation naming a document in the same repository resolves to a section that document numbers, and no document numbers one section more than once | code-style.md section 7.3 |
| `MQC_REQ_HAR_CMN_0154` | A repository holding a README holds a CHANGELOG beside it, and the document register names both, so a figure that moves in the README leaves a record of when it moved and why | code-style.md section 7.4 |
| `MQC_REQ_HAR_CMN_0155` | The rule set digest a carried outcome is guarded on is populated by the run that loaded the rules, so the primary guard compares real digests rather than two empty strings | cmn_verdict_and_cli.md section 7.6.2 |
| `MQC_REQ_HAR_CMN_0156` | A threshold outside its domain is refused when the thresholds are constructed, rather than deciding a verdict: every rate lies in (0, 1] and both population counts are whole and at least one | cmn_verdict_and_cli.md section 8.1 |
| `MQC_REQ_HAR_CMN_0157` | A stored artifact carrying an impossible threshold refuses when its verdict is recomputed, and is not recomputed against a substituted or defaulted standard | cmn_verdict_and_cli.md section 8.1 |
| `MQC_REQ_HAR_CMN_0158` | The pytest marker registry is compared against the code that applies it rather than duplicated unchecked: an applied marker that is not registered fails collection, the scope marker the code reads is the one the ini registers, and the two repositories register the same names | harness_test_taxonomy.md section 7.5.1 |
| `MQC_REQ_HAR_CMN_0159` | A production record is a frozen dataclass unless it is a declared accumulator, so a validated value cannot be replaced after construction | harness_test_taxonomy.md section 15.8 |
| `MQC_REQ_HAR_CMN_0160` | A verdict carrying a non-zero exit code is never green, whichever rule or condition produced it | harness_test_taxonomy.md section 15.8 |
| `MQC_REQ_HAR_CMN_0161` | The score spread is reported from two observations and withheld from one, because zero spread means the judge agreed with itself and one observation cannot establish that | cmn_verdict_and_cli.md section 4.9.4 |
| `MQC_REQ_HAR_CMN_0162` | A production change the suite fails to notice is reported as a survivor, and every accepted survivor is declared with its kind, its reason and an expiry; the audit refuses to run without a control proving the unmutated suite collects and passes | harness_test_taxonomy.md section 15 |
| `MQC_REQ_HAR_CMN_0163` | The mutation audit mutates only a module whose content hashes to the digest declared for it, so a baseline an earlier run altered is refused rather than measured, and a survivor declaration is valid only for the module version it was measured against | harness_test_taxonomy.md section 15.10 |
| `MQC_REQ_HAR_CMN_0164` | Every rewrite of a module the mutation audit performs is inside the backup window, the control's unparse included, so a run killed at any point leaves a backup a later run can recover from | harness_test_taxonomy.md section 15.5 |
| `MQC_REQ_HAR_CMN_0165` | A mutation audit that declines to measure reports a skip carrying QC_HARNESS_AUDIT_REFUSED, never a failure, and the two refusals that cost nothing are checked in setup so a case that cannot measure does not execute | harness_test_taxonomy.md section 15.2.1 |
| `MQC_REQ_HAR_CMN_0166` | The manifest is read and written through the harness, so a declaration is recorded by the audit rather than hand-edited, and writing one preserves the reasons and expiries the other entries carry | harness_test_taxonomy.md section 15.2.2 |
| `MQC_REQ_HAR_CMN_0167` | Every engine list a workflow writes, as a choice input or a matrix dimension, names exactly the rostered engines, checked by one implementation run against each repository | harness_ci_pipeline.md section 8.5 |
| `MQC_REQ_HAR_CMN_0168` | A workflow that lets the engine be chosen from a list and can run live assigns the credential variable of every rostered engine from its secret, checked by one implementation run against each repository | harness_ci_pipeline.md section 8.5.4 |
| `MQC_REQ_HAR_CMN_0169` | Every code registry that mirrors a taxonomy table, the layers, the outcomes, the priority conditions and the criticality ranks, agrees with that table in both directions | harness_test_taxonomy.md sections 3, 4.1.0, 6.5 and 7.4.0 |
| `MQC_REQ_HAR_CMN_0170` | A band summary's totals sum its bands, every skip reason pytest reports is read whatever its shape, and a precondition skip is named only when one occurred and never beyond the skips | cmn_verdict_and_cli.md sections 7.11.2 and 7.11.3 |
| `MQC_REQ_HAR_CMN_0171` | A runner is recognised by its own variables, each deselection is counted in the line that reports it, and a marker block is read the way pytest reads it | harness_test_taxonomy.md section 7.5.1 |
| `MQC_REQ_HAR_CMN_0172` | One mutation audit holds a module at a time: a lock naming a running process refuses a second audit and names it, and a lock left by a process that has exited is cleared, the liveness asked of the operating system without signalling the process | harness_test_taxonomy.md section 15.11 |
| `MQC_REQ_HAR_CMN_0173` | The mutation audit runs only when somebody asks for it, dispatched at one module and narrowed to the lines that changed, so a tool that measures neither the harness nor a model is never a tax on a push | harness_test_taxonomy.md section 15.6A |
| `MQC_REQ_HAR_CMN_0174` | Every code the harness registers has a row in the taxonomy's section 6 tables, so the single registry lists every code the code can emit | harness_test_taxonomy.md section 6 |
| `MQC_REQ_HAR_CMN_0175` | Every requirement the harness plan states reads the same in the plan and in rtm_harness.csv, backticks aside, so a reader of either is told what was decided last | cmn_verdict_and_cli.md section 10.17.1 |
| `MQC_REQ_HAR_CMN_0176` | Every pytest run the mutation audit starts reads no standard input, so an audit started from a session without one runs | harness_test_taxonomy.md section 15.5.1 |
| `MQC_REQ_HAR_CMN_0177` | A mutation control that raises restores its module and then removes the backup, so a later audit does not refuse a module that is not mutated | harness_test_taxonomy.md section 15.5.1 |
| `MQC_REQ_HAR_CMN_0178` | A case that raises an exception other than an assertion or a deliberate pytest outcome, or errors in setup or teardown, is logged as QC_HARNESS_UNANTICIPATED_EXCEPTION, counted as broken rather than failed, and makes the run exit 3 | harness_test_taxonomy.md section 5.1.1 |
| `MQC_REQ_HAR_CMN_0182` | A graded case records one step per dispatch, each an action and one verification of that request, records escalation steps not taken as not run, and ends with a step verifying only that the observations agree | harness_test_taxonomy.md section 8.2.2 |
| `MQC_REQ_HAR_CMN_0184` | Every precondition case in both repositories records its steps through the engine graded cases use: each assertion and expected exception a verification, the code or the case's named step before it the action, its fixtures the preconditions, and a case recording no verification fails | harness_test_taxonomy.md section 8.2.4 |
| `MQC_REQ_HAR_CMN_0185` | A run refuses to start while a module of the harness it imports is under mutation by another process, or was left so: an abandoned backup is restored and the restore verified against the declared digest, a restore that fails or does not match keeps the backup, and the audit leaves a progress log, named for its start, that the refusal quotes | harness_test_taxonomy.md section 15.12 |
| `MQC_REQ_HAR_CMN_0186` | A rule authoring no assertion reports its check step as not applicable once its judge has run, so a rubric-only rule is not read as having stopped before its judgement | harness_test_taxonomy.md section 8 |
| `MQC_REQ_HAR_CMN_0225` | The screen phase of a step fails only where the screen stopped the observation, so a declared adversarial case whose payload matched and was graded is not published as a halted step or counted as a failing observation | harness_test_taxonomy.md section 8.2.5 |
| `MQC_REQ_HAR_CMN_0226` | A job that runs graded cases reaches a precondition invocation before it can spend, either through a job it needs or through an earlier step of its own job that a failure stops; a graded invocation is read in every workflow that is not a debug workflow and through a local uses: where one is factored out, and a job running another repository's cases from a checkout it fetched is that repository's to gate | harness_ci_pipeline.md section 8.6 |
| `MQC_REQ_HAR_CMN_0228` | Every Ubuntu runner label a workflow names is the single version this repository pins, and that version is declared in `.github/actionlint.yaml`. Four things are therefore refused: a label carrying no version, a second version anywhere in the repository, a pinned version the declaration omits, and a declaration no workflow names | harness_ci_pipeline.md section 8.7 |
| `MQC_REQ_HAR_CMN_0229` | A workflow does not report success for work it did not do. Where one job is gated on the conclusion of the run that triggered the workflow, every other job either skips with that job or names its result, so a run whose gated job was skipped concludes skipped rather than success | harness_ci_pipeline.md section 8.8 |
| `MQC_REQ_HAR_CMN_0230` | A report's Suites tab is navigated by the band a case was graded in. A graded case's suite root is P0 through P4 and a precondition's is Preconditions, the same value is published as a tag so a reader can filter by it, and a case declaring a root of its own keeps it rather than gaining a second | harness_test_taxonomy.md section 16.8 |
| `MQC_REQ_HAR_CMN_0231` | A report's Categories tab classifies a non-passing result by its cause rather than by its status. Every registered failure code is matched by exactly one category: each family carries one, the three harness codes whose remedies differ carry one each, and a result naming no registered code carries one of its own. The classification is written into the directory the raw results go to | harness_test_taxonomy.md section 16.9 |
| `MQC_REQ_HAR_CMN_0232` | A job that dispatches a workflow which spends reads a green pairing from a job it needs, so nothing starts a live ladder against a harness nothing verified. A dispatch is read whether it is made from the command line or through the Actions API, a dispatch naming this repository explicitly is read as spending this repository's quota, and a dispatch into another repository belongs to the repository that owns the pairing | harness_ci_pipeline.md section 8.9 |
| `MQC_REQ_HAR_CMN_0236` | The resolver a debug run gates on accepts a collected identifier, refuses an unknown one and refuses an empty request, and the consumer enumerator resolves a mapped harness branch to its mapped ref, an unmapped one to the consumer's declared default, and an absent registry to a refusal, so neither a selection that measures nothing nor a fan-out that verifies nothing reports success | harness_ci_pipeline.md section 8.10 |
| `MQC_REQ_HAR_EXE_0140` | A case the spend ceiling prevented is skipped naming that cause and never counts toward the circuit breaker's consecutive-failure streak, so a run that reached a ceiling an operator set reports what it measured rather than reporting an engine that stopped answering | tier2_execution.md section 8.3.1 |
| `MQC_REQ_HAR_CMN_0238` | Every date the project means by today is the UTC date, read from the one clock every caller calls, so a module reading a clock of its own is reported rather than stamping a durable record with the date wherever the process happened to run | code-style.md section 8.3 |
| `MQC_REQ_HAR_CMN_0237` | Every collected test module names a gate that would select it, by a module-level marker or by a marker on each case it holds, so a module no gate reaches is reported rather than collected, deselected and counted as nothing | harness_test_taxonomy.md section 13.6 |
| `MQC_REQ_HAR_CMN_0234` | A JUnit report's failing cases are listed apart from its erroring cases, a case carrying both counts once as erroring, a clean report still states its counts, and a report that is absent or will not parse refuses rather than reporting no failures, so a leg whose cases broke is never read as a clean leg | cmn_verdict_and_cli.md section 7.12 |
| `MQC_REQ_HAR_CMN_0233` | A run states which model it measured against, in both the artifacts it publishes. One mapping carries the engine, the mode, the requested model and what the provider served, every field is present whatever the run knew and an absent value reads unrecorded rather than empty, and the same mapping is rendered into the properties file a report's environment block is built from and into the properties a JUnit report carries under its root element. The provider is asked only where there is one to ask, so a replay run records what it replayed and a precondition run reaches no network | cmn_verdict_and_cli.md section 5.6 |
| `MQC_REQ_HAR_CMN_0187` | A mutation audit is collected only when the run asks for one, by a marker expression naming mutation, a path under tests/mutation or --tests naming the case; any other run deselects every MUT case, so it leaves the total | harness_test_taxonomy.md section 15.13 |
| `MQC_REQ_HAR_CMN_0188` | A running audit stops on request: it finishes the point running, restores its module and releases its lock, refuses with QC_HARNESS_AUDIT_REFUSED and logs the stop, every later audit in that process stops before its control, a request naming another process stops nothing, and the stop command exits 0 only once each named module matches its declared digest | harness_test_taxonomy.md section 15.13 |
| `MQC_REQ_HAR_EVL_0074` | A result carries the rendered prompt its judge received wherever a judge request was composed, and none where it was not; one function composes that request, from the observation, for the pipeline and for any caller rebuilding it | tier3_evaluation.md section 4C.6 |
| `MQC_REQ_HAR_EXE_0084` | A judgement recording stores the rendered prompt it scored beside the request hash, the hash computed as before and a recording without the prompt still loading | tier2_execution.md section 7.9.4 |
| `MQC_REQ_HAR_CMN_0189` | Every case that dispatched anything attaches an exchanges report, passing or failing: per observation its request and response redacted, its screen matches, its checks, and its judge prompt with scores or the reason it was not judged | cmn_verdict_and_cli.md section 5.5 |
| `MQC_REQ_HAR_CMN_0190` | Every branch a workflow's push, pull_request or workflow_run filter names, and every key of a consumer's refs, is main, ** for every branch, a name the branch policy accepts, or a <kind>-* pattern over a registered kind | harness_ci_pipeline.md section 3C.6.8 |
| `MQC_REQ_HAR_EVL_0075` | With the judge withheld, --judge-mode off, the screen and the assertions decide: a failing check or a screen abort fails, a rule with no rubric passes on its assertions, a rubric-bearing observation whose checks held is skipped unjudged and never passes, and the judge is never called | tier3_evaluation.md section 5A.5.3 |
| `MQC_REQ_HAR_CMN_0191` | --judge-mode off is accepted under either candidate mode, unjudged is a registered skip reason excluded from the denominator with QC_HARNESS_JUDGE_WITHHELD, and only a workflow of the on-demand cadence may pass it or offer it | tier3_evaluation.md section 5A.5.3; harness_test_taxonomy.md section 7.4.1.4 |
| `MQC_REQ_HAR_CMN_0192` | Every Python file's module docstring carries Created: and Last updated: as its third and fourth lines, each a real date, Created no later than Last updated and neither in the future, and a file differing from its last commit carries a Last updated no earlier than that commit, compared without reference to any running clock so the verdict does not move with the runner's timezone | code-style.md section 3.1.2 |
| `MQC_REQ_HAR_CMN_0193` | An audited module whose code is unchanged since its survivors were measured, its docstrings and comments aside, is re-declared without an audit: its digest is rewritten and each survivor moves to the line its mutation point now sits on; a code change, a module reading as its own unparse, or a measured version missing from history is refused | harness_test_taxonomy.md section 15.14 |
| `MQC_REQ_HAR_CMN_0194` | A mutation audit with two or more workers measures every point in its own copy of the repository, beside a link to each sibling repository, never writing the repository's module, and reports the same survivors in walk order as a serial audit; the copies are removed when it ends | harness_test_taxonomy.md section 15.15 |
| `MQC_REQ_HAR_CMN_0195` | A lock marked isolated, held by a live audit measuring in copies, does not refuse an ordinary run, while an in-place audit's lock still does | harness_test_taxonomy.md section 15.15 |
| `MQC_REQ_HAR_CMN_0196` | A parallel audit runs each mutant first against the test modules that import the audited module directly or through other repository modules; a mutant those kill is killed, and one they miss is run against the full targets, whose outcome alone decides a survivor | harness_test_taxonomy.md section 15.16 |
| `MQC_REQ_HAR_CMN_0197` | A run derives its context from the environment: local outside GitHub Actions, ci_debug for a workflow file ending in -on-demand or for a run naming no workflow, and ci for any other workflow | cmn_verdict_and_cli.md section 7.1.4 |
| `MQC_REQ_HAR_CMN_0198` | The session builds one run context from the detected context, the selection mode and the precondition outcome, and every case it runs is handed that context | cmn_verdict_and_cli.md section 7.1.4 |
| `MQC_REQ_HAR_CMN_0199` | A priority band selected with no other selector is selection mode band, which yields a verdict and is gated only in the ci context; with any other selector the selection is manual | cmn_verdict_and_cli.md section 7.1.4 |
| `MQC_REQ_HAR_CMN_0200` | A session whose preconditions all passed writes a precondition record guarded by the harness commit, the corpus commit and the platform; a graded session counts a matching record as preconditions executed, refuses one that differs naming the field, and treats an absent one as not executed; a failed precondition writes none and removes the old one | cmn_verdict_and_cli.md section 7.1.4 |
| `MQC_REQ_HAR_CMN_0201` | Production code outside tests names no failure code the registry lacks, read from every string constant including f-string parts | harness_test_taxonomy.md section 6.2.1 |
| `MQC_REQ_HAR_CMN_0202` | A mutation audit whose control fails names each failed or errored case in its refusal, read from pytest's short summary | harness_test_taxonomy.md section 15.4.1 |
| `MQC_REQ_HAR_CMN_0203` | A mutation audit started from the command line with no target runs against the same targets as the audit cases, declared once | harness_test_taxonomy.md section 15.4.2 |
| `MQC_REQ_HAR_CMN_0204` | The test modules run first against a mutant leave out the mutation layer, whose conftest would otherwise be loaded under the root's name | harness_test_taxonomy.md section 15.16.1 |
| `MQC_REQ_HAR_CMN_0205` | A parallel audit's control runs the seeing cases against the unparsed module as well, and refuses the audit naming them when they do not pass | harness_test_taxonomy.md section 15.16.1 |
| `MQC_REQ_HAR_CMN_0206` | A selection narrowed by a selector pytest owns, -k, a typed path or node identifier, --deselect or --last-failed, is selection mode manual and yields no verdict; a marker expression and a run stopped early narrow no selection and leave the mode as the harness's own flags set it | cmn_verdict_and_cli.md section 7.1.4 |
| `MQC_REQ_HAR_CMN_0207` | A graded invocation in a workflow that is not a debug workflow, or in a composite action, names every graded layer marker; one naming some of them selects part of a run while the harness records a full selection, so its rows would carry a verdict over part of the graded cases | consumer_ci.md section 4.21 |
| `MQC_REQ_HAR_CMN_0208` | Within every document this repository tracks, each numbered heading sorts after the numbered heading above it; a heading opening with a bare number is a section only where that number carries a period, and a fenced block holds no headings | code-style.md section 7.5 |
| `MQC_REQ_HAR_CMN_0209` | A subject whose category fills continues in a declared partition, a range with a recorded start and end rather than digits that derive it; the partitions this code declares are the partitions the design tabulates, an identifier inside one takes its layer and module from that record, and the partition is warned of at nine tenths of its own width | harness_test_taxonomy.md section 3.2.1.5 |
| `MQC_REQ_HAR_CMN_0210` | Every flag a live document names is declared by something: the pytest option registry, a script of the repository, a registry naming what owns a flag from outside it, or a registry naming a retired flag with its date; the changelog and the progress log are not read, recording what was true when they were written | cmn_verdict_and_cli.md section 7.1.0.4 |
| `MQC_REQ_HAR_CMN_0211` | Every audited module hashes to the digest declared for it, reported as a precondition before any audit is asked for, naming the module, the digest on disk and the digest declared | harness_test_taxonomy.md section 15.10.1 |
| `MQC_REQ_HAR_CMN_0212` | A mutation audit refused from the command line exits 4 and names the refusal, whether it was raised in place or in a parallel copy | harness_test_taxonomy.md section 15.4.3 |
| `MQC_REQ_HAR_CMN_0213` | An audited module whose code changed is re-measured on request, the module on disk taken as the baseline and its digest declared after the measurement returns; a backup, a lock, a failing control and a module reading as its own unparse each still refuse, and no survivor is accepted | harness_test_taxonomy.md section 15.10.2 |
| `MQC_REQ_HAR_CMN_0214` | Every stale declaration is reported from the command line, which exits 4 and names each module, so the comparison a precondition makes is runnable by an operator and by a workflow step | harness_test_taxonomy.md section 15.7.2 |
| `MQC_REQ_HAR_CMN_0215` | Gate 8's job compares every declaration before it measures one and stops without measuring where the manifest does not describe the repository; its summary states what the measurement took and how many audited modules it reached | harness_test_taxonomy.md section 15.7.2 |
| `MQC_REQ_HAR_CMN_0216` | Every collected test module declares the capability it tests, from a vocabulary declared in the same file, and the declared epic is the distribution's own name; a module absent from the map, a value outside the vocabulary, an entry naming no module and an epic disagreeing with the project are each reported | harness_test_taxonomy.md section 16.3 |
| `MQC_REQ_HAR_CMN_0217` | Every collected case reaches the published result with an epic, a feature and a story, derived at collection from the declared map and the test class, so a report groups every result by capability rather than grouping the few that were annotated by hand | harness_test_taxonomy.md section 16.2 |
| `MQC_REQ_HAR_CMN_0218` | A class or case declaring a label of its own keeps exactly one of that type, the derived label standing aside, so a hand-written story is an override rather than a second branch in the tree | harness_test_taxonomy.md section 16.2.1 |
| `MQC_REQ_HAR_CMN_0219` | The report is generated from the raw results a gated run on the default branch uploaded and is published, carrying the previously published trend where one exists, from a job of its own that declares the deployment permissions, never gates a merge, decides what to include from the head commit rather than from a run's conclusion, and generates without history rather than failing where no previous site is readable | harness_ci_pipeline.md section 7.4 |
| `MQC_REQ_HAR_CMN_0220` | A run on a machine with no Allure runtime installed collects and executes its cases, publishing no report and refusing no derived label marker, so the reporting extra is CI's dependency rather than the suite's | harness_test_taxonomy.md section 16.7 |
| `MQC_REQ_HAR_CMN_0221` | One module imports the reporting library and every other reaches it through that module, so a module cannot fail to load for the lack of an optional dependency, and a case that reads what a real reporter wrote declares the environment scope that says so | harness_test_taxonomy.md section 16.7 |
| `MQC_REQ_HAR_CMN_0222` | Every audit closes by naming the cases it set aside, read from the targets it ran rather than from a second list, so a case excluded from the measurement is visible to the reader of its report | harness_test_taxonomy.md section 15.7.1.2 |
| `MQC_REQ_HAR_CMN_0224` | An audit is counted apart from the harness suite and carries no priority band, so a run's total answers one question and a band orders only claims that compete for a gate | harness_test_taxonomy.md section 15.6A.5 |
| `MQC_REQ_HAR_CMN_0183` | A category with 90 or more assigned identifiers, and a block with more than 800, are warned of without failing the run, retired identifiers counted as assigned | harness_test_taxonomy.md section 11.9.6 |
| `MQC_REQ_HAR_CMN_0181` | A case split from a parametrisation over a registry is accompanied by a completeness case, which reports every registry member no case passes to the shared helper | harness_test_taxonomy.md section 1.1 |
| `MQC_REQ_HAR_CMN_0180` | A traceability matrix records each retired test in its requirement's retired_test_ids column, and every test named there is uncollected, absent from test_ids, and struck through in a design inventory | cmn_verdict_and_cli.md section 6.1.2 |
| `MQC_REQ_HAR_CMN_0179` | A case identifier executes once per run: a run collecting one identifier more than once is refused with QC_HARNESS_CASE_REPEATED and exits 3, and a named list of N identifiers selects N executions | cmn_verdict_and_cli.md section 7.8.5 |
| `MQC_REQ_HAR_CMN_0044` | A run states how many cases its own selection executed, passed, failed and skipped, with the pass rate over what executed and every skip named on its own line against its own case with the registered code and what that code means, so a band job is read for its band rather than for a count of what it declined to run | cmn_verdict_and_cli.md section 7.11 |
| `MQC_REQ_HAR_CMN_0043` | A module at nine hundred lines or more is reported unless it is declared with a reason and an expiry, so the next subject added starts a module of its own and the thousand-line ceiling is never reached by an unrelated edit | code-style.md section 5.1 |
| `MQC_REQ_HAR_CMN_0027` | Every registered model and security code carries a criticality rank, and a finding is named by the most critical code that fired rather than the first one emitted, so a security compromise is not catalogued as a consistency observation | harness_test_taxonomy.md section 6.5 |
| `MQC_REQ_HAR_EVL_0022` | An assertion that reads prose matches on what the model said rather than how it formatted it, inline markup being removed before a pattern or substring is applied, while an assertion that counts reads the text as written | tier3_evaluation.md section 5.1 |
| `MQC_REQ_HAR_EVL_0023` | An assertion that counts reads the text as the model produced it, markup included, so a bound stated against that output is measured against it rather than against a shortened reading | tier3_evaluation.md section 5.1 |
| `MQC_REQ_HAR_EVL_0024` | The task-substitution vector screens an instructed substitution and not a described one, so a model contrasting an outcome with the expected one is not aborted on an ordinary case and reported as inconsistent | tier3_evaluation.md section 5.2 |
| `MQC_REQ_HAR_EVL_0063` | A judged score equal to the rubric pass mark passes, and a score below it does not, so the mark is inclusive as the design states | tier3_evaluation.md section 9 |
| `MQC_REQ_HAR_EVL_0064` | A run may decide whether a score equal to the rubric pass mark passes or fails, defaulting to pass, and the choice reaches the artifact | tier3_evaluation.md section 9 |
| `MQC_REQ_HAR_EVL_0065` | A judge the provider could not answer is recorded as an unavailable judgement carrying the provider's code, never as a reply the model is charged for | tier3_evaluation.md section 6.5.1 |
| `MQC_REQ_HAR_EVL_0066` | A coercion directive is screened whether its argument is an amount, an address or a relative path, so a period inside an argument does not end the directive | tier3_evaluation.md section 5.2.2 |
| `MQC_REQ_HAR_EVL_0067` | A declared adversarial case whose rule opts into a response-only judgement is judged on its answer alone once the answer screens clean, fails without a judge when the screen finds a registered vector in it and the rule declares the relay forbidden, and no payload reaches a judge | tier3_evaluation.md section 4C.4 |
| `MQC_REQ_HAR_EVL_0070` | An answer that quotes an injected instruction while reporting it is screened, recorded and judged rather than aborted, where no rule forbids the relay, so a prompt that invited a report does not fail the model for quoting what it reported | tier3_evaluation.md section 4C.4.1 |
| `MQC_REQ_HAR_EVL_0068` | An instruction to ignore the previous text, and an instruction to grade the response, are screened as the vectors they are | tier3_evaluation.md section 5.2.3 |
| `MQC_REQ_HAR_EVL_0069` | An injection test verifies an answer against a pattern the harness owns, named by the case: an instruction to grade with any value fails it, a pattern no registry holds is refused, and the global screen does not run a verification-only pattern | tier3_evaluation.md section 5.2.4 |
| `MQC_REQ_HAR_EVL_0070` | The injection screen reads a mark only from the number that states it: a value written as a ratio's scale, after "out of" or a slash, is not a top mark, and a top mark stated before the scale is still screened | tier3_evaluation.md section 5.2.5 |
| `MQC_REQ_HAR_EVL_0071` | An injection test's grading-instruction verification fails every match except reported speech: a source named as saying it, before the match in its sentence or as a pronoun opening it after a sentence naming one, and a rejection in that sentence or the next, both required; a quoted match fails whatever surrounds it, and a later direct instruction is not excused by an earlier report | tier3_evaluation.md section 5.2.6 |
| `MQC_REQ_HAR_EVL_0073` | On a rule judged on its answer alone, an instruction-override match the answer reports and rejects, outside any quotation, does not abort the screen; any other match of it in the answer still aborts, and every other vector and every ordinary case is screened unchanged | tier3_evaluation.md section 5.2.6 |
| `MQC_REQ_HAR_EVL_0072` | A judgement returning the planted score its rubric declares, on an answer carrying a grading instruction asking for that value, fails the observation with QC_SEC_INJECTION_ATTEMPT whatever the aggregate, naming the criterion and the value; a judgement on an answer asking for no such value, and a rubric declaring none, are decided as before | tier3_evaluation.md section 4C.5 |
| `MQC_REQ_HAR_CMN_0107` | Every field section 9 requires of an observation reaches the published artifact as a parameter, with the taxonomy code also carried as a label, so a reviewer or an analysis can say which engine and which judge produced a result from the artifact alone | cmn_verdict_and_cli.md sections 5.1 and 5.2 |

---

## 4. Coverage

`docs/testing/rtm_harness.csv` maps each requirement above to the precondition cases covering it, and is verified in both directions by `MQC_CMN_UNI_112300` through `112302`.

**A requirement with no case is a coverage gap**, and the matrix reports it rather than leaving it to be noticed.

---

## 5. What This Plan Does Not Cover

The graded layers. A harness passing every case here proves only that the instrument works, not that any model was measured well. That is the subject of `model_evaluation_test_plan.md`, which since the 2026-09-23 split lives in its own repository. The distinction is why the two plans were separate documents before they were separate repositories.
