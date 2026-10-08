<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# Changelog

All notable changes to this project are recorded here. `README.md` and the
documents under `docs/design/` always describe the **current** state and nothing
else; this file is where change-to-change history lives, so neither accumulates a
sediment of "as of version X" qualifiers.

Versions follow [Semantic Versioning](https://semver.org/) as applied to a model
QC suite, where the durable artefact is the test record rather than an API:

- **Major** - a change an existing reader of the record cannot absorb: the test
  identifier format, a taxonomy code's meaning, an ID block boundary, or the
  published artefact contract.
- **Minor** - new capability: a test layer, an engine adapter, a loader, a gate,
  or new task and rubric data.
- **Patch** - fixes and documentation corrections that change no emitted result.

Dates are **UTC**, matching git commit dates and CI runners.

---

## Unreleased

Versioning begins at the first release a case repository can pin. Until then
changes accumulate here rather than under a version number, because nothing has
been released to carry one.

### A skip is counted by its cause, and the skip ceilings are retired, 2026-10-08

**A case that skipped did not pass, and the pass rate now says so.** A skip
entered neither the pass-rate numerator nor its denominator, so a rate was
stated over whatever happened to run. It now enters the denominator and never
the numerator, which makes it read as the failure it is.

**Whether it counts as a failure is decided by the reason it carries.** A skip
caused by a harness bug, a flaky test or a provider nobody could reach is not
the model's failure, and charging it to the model is the misattribution the four
taxonomy families exist to prevent.

| Reason | In the pass rate |
|---|---|
| `quarantined`, `dependency`, `incomplete`, or unstated | **Counted as a failure** |
| `environmental`, `unsupported` | Excluded |

**`quarantined` is a new skip reason.** A quarantined case skips before dispatch
to save the run's cost, and it had been arriving unattributed. An unattributed
skip is counted, so the answer was right by accident; it is now right by
declaration.

**Quarantine no longer leaves the pass-rate denominator.** It saves the cost of
asking again about a known failure and does not stop it being one. The one thing
that releases a quarantined skip is `release_accepted_in`, the tracker reference
in which product management announced that releasing with the finding is
acceptable, and an unconfirmed entry cannot carry one.

**V3 and V4 are retired.** A 20% total skip ceiling and a 90% pass floor cannot
both hold once a skip counts in the denominator: a run sitting exactly where V3
tolerated it breached V2 automatically. V4 capped the blocking-band skip rate at
10%, and V1 already fails a run on a single blocking-band observation that does
not pass, so a ceiling that can fire only after something stricter has fired
decided nothing. Both rule names stay retired rather than reused, and both
thresholds stay loadable so a stored verdict remains recomputable.

**A skipped case records its own observation, which nothing did before.**
`pytest.skip` raised before anything was recorded, so the accounting specified
since A13 had no skips to count. The three in-case skip sites now record one
each, carrying the reason, and a judgement the replay store did not hold records
`environmental` where it used to record a model **failure**.

**A band line names each kind of skip by the remedy it takes**: behind a higher
band failure, as a known failure in quarantine, or for a reason of ours. A
quarantined skip had been reading as our infrastructure wobbling.

**Replay on both sides is recorded as measuring no model.** Both halves are
recordings, so such a run establishes only that our pipeline still reads its own
fixtures the same way. It is the pull-request gate and a precondition, and a
finding filed against a vendor cites a live candidate.

**Recording a skip exposed one more thing the artifact was doing.** A skipped
report is not a passing one, so the attachment condition read `passed` alone and
began filing a vendor report for every quarantined case the moment a skip
recorded an observation. Nothing is filed about a skip: it holds no response for
a provider to read. The observation is still published, which is what gives the
rate a skip to count.

**The blocking-band floor honours the dispensation it was documented to honour.**
It read the field nowhere. It now loads the entries for the engine, releases a
skipped case the reference names, and names the case and the reference in the
line. A dispensation recorded against another case releases nothing.

Retired with the rules: `112006` through `112009`, `112019` and `112032`, each
listed struck through rather than removed. Added: `112044` through `112050`,
`112341` and `112342` in the harness, `115717` in the case repository, with
`MQC_REQ_HAR_CMN_0142` and `0143` and `MQC_REQ_CAS_CI_0042`. Designs:
`test_taxonomy.md` sections 7.4.1, 7.4.1.0, 7.4.1.2, 7.4.1.3 and 7.4.2;
`cmn_verdict_and_cli.md` sections 4.3, 4.4, 4.6.13, 5.3, 7.11 and 10.24.2;
`consumer_ci.md` sections 3.12.3 and 6.4.1.

### Claude candidate moved to Claude Opus 5.5, 2026-09-23

**The model identifier changed and the adapter did not.** Of the four breaking
changes the newer model introduces, this adapter was exposed to none: it sent no
`thinking` field, forced no tool call, replayed no conversation turn, and
declared no computer-use tool. "One request per case, no loop" was adopted so
tool-call intent stays unexecuted, and it independently removed an entire class
of migration work.

**One behavioural change was designed for rather than absorbed.** The newer
model defaults its effort level one step lower, so the adapter now states the
value (`_DEFAULT_EFFORT`) instead of inheriting it. The setting enters the
request hash, so moving it reports a stale fixture rather than silently
changing how much the model thinks. `tier2_execution.md` section 5A.1 carries
the reasoning; `MQC_EXE_UNI_113011` and `113012` enforce it.

**No recurring cost changes.** A3 Option 1 stands: the judge is Gemini on the
free tier and Claude remains a replay-only candidate, so the lower price
becomes relevant only if a key is provisioned.

### Repository split, 2026-09-23

**This repository became the harness alone.** The evaluation cases moved to
`AP-Model-QC`, which now consumes this one as a pinned dependency. Closes A17;
`DESIGN.md` section 5.1 carries the boundary and the capability table.

This is a **major** change under the versioning policy above, because it changes
what a version means: a commit here is now a version of the harness rather than
of the harness and the cases together. Nothing downstream has consumed a version
yet, so it costs no migration.

- **Moved out**: the graded layers, task data, golden rules, replay fixtures,
  the code excerpts, `model_evaluation_test_plan.md` and `rtm_model.csv`.
- **Removed**: `MQC_CMN_UNI_10171` through `10173`, `11105` and `11106`, with
  `MQC_REQ_HAR_CMN_0027`. They read case-side data, which the split revealed as a
  boundary violation. Re-homed as `MQC_CAS_UNI_115100` through `115104`.
- **Added**: `CAS` as a registered module with its own identifier block, which
  spans repositories because the durable record does.
- **Licensed**: Apache 2.0 with a `NOTICE`, and an SPDX header on every Python
  file, enforced by `MQC_CMN_UNI_112502`.

### Implementation, Phase 3

All four modules implemented, with 357 precondition cases and 107 traced
requirements. Four CI workflows written and linted. The 3-phase workflow in
`.claude/skills/skill-rules.md` was observed throughout: every case was
inventoried in a design document before it was built, which
`MQC_CMN_UNI_112303`, `112305` and `112306` now enforce mechanically.

### Added

- **`CLAUDE.md`** as the directive router, and the rule set beneath `.claude/`
  covering code style, framework architecture, testing standards and worktree
  isolation.

- **`.pylintrc`**, which moves the project's naming rules from prose into
  mechanical enforcement. `variable-rgx`, `argument-rgx`, `attr-rgx` and
  `inlinevar-rgx` enforce the three-character minimum; `function-rgx`,
  `method-rgx`, `class-rgx` and `module-rgx` enforce the `MQC` prefix and
  reject `test_`-prefixed names.

  `inlinevar-rgx` is set deliberately. It governs comprehension targets, which
  pylint's defaults permit to be single letters, so without it `[row for r in
  rows]` scores 10.00/10 while violating the rule it is meant to satisfy.

- **`docs/design/phase0_project_ambiguities.md`** - a register of 13 blocking
  items, 10 deferrable assumptions and 3 governance ambiguities, each with a
  recorded decision. The governance layer specified *how* to build but never
  *what*; this closed that gap before any design commitment.

- **`docs/design/test_taxonomy.md`** - the normative reference for what every
  identifier means: module and layer registries, priority definitions with
  worked examples and distribution ceilings, the outcome model, and four failure
  taxonomy families (`QC_LLM_*`, `QC_HARNESS_*`, `QC_DATA_*`, `QC_SEC_*`).

- **`CLAUDE_LOG.md`** - tracked decision and progress record. Raw prompts are
  deliberately excluded and kept in an untracked prompt log, so this file holds
  outcomes rather than phrasing.

### Changed

- **The test identifier format is `MQC_<MODULE>_<LAYER>_<5DIGIT>_<behavior>`**,
  extended from an earlier three-segment form. Identifiers now read outward-in:
  project identifier, module, test type, instance. The old format is rejected
  by `.pylintrc` rather than tolerated alongside the new one, because two valid
  formats at once is how a naming standard stops being one.

- **Gate 4 no longer exports a bespoke telemetry file.** The prior rule required
  writing a bespoke `reports/mqc_test_insights.json` for a downstream collector
  to consume. Collectors parse standard formats, JUnit XML and Allure output,
  so the rule would have produced a file nothing could read. It also encoded a
  reverse dependency on a consumer, which the architecture exists to avoid.

- **`MQC_UNI_` and `MQC_SYS_` became ungraded preconditions** rather than graded
  layers. Both require 100% pass and block the graded layers on failure, on the
  grounds that a harness failing its own tests produces results that are suspect
  anyway. `MQC_SYS_` runs in replay mode as the precondition: a gate that can
  flake on a rate limit cannot distinguish a broken pipeline from a busy
  provider, and so is not a gate.

### Fixed

- **A silent-skip hole in the lint gate.** The `MQC` naming pattern accepted
  `test_`-prefixed callables through its ordinary snake_case branch. Such a test
  scored 10.00/10 at Gate 1 while `pytest.ini` never collected it, so it linted
  clean, reported nothing and never ran. Closed with negative lookaheads on the
  function, method, module and class patterns. A suite reporting green for a
  test that does not exist is worse than one reporting red.

- **Marker propagation across test layers.** A class-level `@pytest.mark` applies
  to every method in the class, so a class mixing an `MQC_TOOL_` and an
  `MQC_EVAL_` method under one marker caused both to be collected by the wrong
  gate and neither to be gated correctly. One layer and one priority per class
  is now a rule in both the taxonomy and the testing standards.

- **Three rule files that could not be complied with as written.** Both skill
  templates targeted a different repository and demonstrated `test_` prefixes
  and single-character exception bindings, which this project prohibits;
  `testing-standards.md` was truncated mid-code-fence at 13 lines; and
  `worktree-rules.md` carried leftover markdown fences from a paste.

### Notes

- **Zero recurring cost is a deliberate scoping decision, not a budget
  constraint.** Gemini's free tier judges and runs live; OpenAI and Claude are
  exercised from recorded fixtures. The funded multi-provider configuration was
  bypassed for this demonstration project. The architecture is already legible
  in the codebase, making the ongoing monthly cost unjustifiable. The paid path
  is documented in the design as a costed alternative.

- **Every enforcement rule in this release was verified by adversarial probe
  rather than by reading configuration.** Probes confirmed that single-character
  comprehension targets and exception bindings are rejected, that `test_` names
  are rejected, that an unregistered layer token passes, that the old identifier
  format is rejected, and that marker filters select correctly once one layer
  per class is observed. Probe files were removed after verification.
