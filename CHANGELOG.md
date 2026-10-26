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

### A job running graded cases stands behind the preconditions, 2026-10-25

**Gate 2 is blocking in three documents and was implemented in one workflow of
the five that run graded cases.** `framework-rules.md` section 1,
`testing-standards.md` and the case repository's `consumer_ci.md` section 3.12
all say the graded layers do not execute when a precondition fails, because
running them spends provider quota to generate noise. The case repository's
per-target gate expressed it as a job graph; `evaluate-live-weekly.yml` here
ran the graded layers live under a spending ceiling and needed nothing, and the
case repository's ladder gated all three rungs on the resolver alone.

**What the absence cost is on the record.** Two assertions added to the relay
rules on 2026-10-24 named a constraint no task sends, so the corpus failed
referential integrity for a day and `MQC_CAS_UNI_115000` reported it. Four
engine sweeps measured the corpus in that state and reported ordinary findings,
because the graded suite builds one case at a time and only a corpus-wide check
sees a dangling reference. The register those sweeps produced was still valid,
and that was luck rather than a property.

`cmn.ci_gating.ungated_graded_jobs` reports a job that runs graded
cases out of this repository's checkout and reaches no precondition invocation,
through a job it needs or an earlier step of its own that a failure stops. A
debug workflow is exempt by its cadence suffix, a local `uses:` is followed so a
graded invocation factored into a composite action is still seen, and a step
running in a checkout the job fetched is that repository's to gate, which is
what `regress-consumers-on-merge.yml` does from the consumer registry.

`evaluate-live-weekly.yml` has a `preconditions` job running Gate 2 and Gate 3,
and `evaluate` needs it. A scheduled retirement is not a reason to leave it
ungated, which is the reasoning `consumer_ci.md` section 4.21 used about the
same workflow's selection.

`MQC_CMN_UNI_112189` builds both gated shapes, the ungated one, a precondition
step written after the graded step, and a graded step in a fetched checkout.
`MQC_REQ_HAR_CMN_0226` traces it, `harness_ci_pipeline.md` section 8.6
specifies it. Cases 981 to 982, requirements 375 to 376, the
`cmn_verdict_and_cli.md` inventory 454 to 455.

### A screen that matched without stopping an observation is no longer a failed step, 2026-10-24

**The step ledger published a failure on a passing case.** `_step_screen` read
`ScreenDecision.taxonomy_code`, which is set whenever a vector fired, instead
of `aborts`, which says whether the evaluation stopped. A declared adversarial
case records the match and continues, so every such observation logged
`PHASE_04_VERIFY ... failed`, `_halted` reported it as stopped at step 4,
`consistency_step` counted it as a failing observation and emitted
`QC_LLM_INCONSISTENT`, and `further_observations` earned an escalation that was
never needed. `grok` `154501` passed three observations scoring 5.0 on each and
its own record said the model answered inconsistently.

**Four readers were wrong from one line**, and the worst of them is the Allure
step tree, which is read as a picture of quality. The phase now fails only
where the screen stopped the observation and keeps the code on the line
otherwise, so the match is still published as the evidence it is.

`MQC_CMN_UNI_112339` builds a ledger from both screen states and compares them;
nothing had built one from a screen that matched without aborting, which is the
state every declared adversarial case is in. Harness cases 980 to 981,
requirements 374 to 375.

### The mutation audit is a tool, not a job, 2026-10-24

**It cost about ten hours of project time in one week while measuring neither
the harness nor a model.** Measured the same day, on the first audit to
complete since the suite reached 949 cases: every check of the harness, lint
and unit and system on both platforms, takes about six minutes; each of the
four target gates about six; one audit of six modules took **49 minutes 58
seconds**. The project owner's ruling followed: a targeted tool, manual and in
CI only, and no recurring job.

**Two modules left the audited set**, because of what their points are.
Counted from the syntax trees: `cmn/registries.py` has 80 points of which
**68 are numeric literals**, the criticality ranks and the HTTP statuses, and
`cmn/band_summary.py` 49 of which 37 are. The nineteen minutes `registries.py`
took were 68 runs of 949 cases to turn `404` into `405`, one at a time, while
`MQC_CMN_UNI_112368`, `112370` and `112380` already compare every one of those
values against the table that declares it, in milliseconds. For declared data
a table comparison is also **stronger**: it catches a wrong value, a missing
row and an extra one, where a single-literal mutation asks only whether one
value was pinned. Their five accepted survivors were all `equivalent`, changes
that cannot alter behaviour, so nothing measured was lost. `MQC_CMN_MUT_162003`
and `162004` are retired with them.

**What stays audited is the rules**: `verdict.py` and `threshold_domain.py`,
where a comparison carries the standard a run is judged against, and
`layers.py` and `environments.py`, which decide which cases run and what their
results are worth.

**And the job became a dispatch.** `audit-mutation-on-change.yml` is
`audit-mutation-on-dispatch.yml`: no push, no path filter, no schedule. It
takes the module to audit and, with `--since <ref>`, narrows the measurement to
the points on lines that changed since that ref. On 2026-10-24 that is 2 points
of 19 for `cmn/environments.py`, and **the only real survivor this project has
found was on a line its own commit had added** — so the targeted form would
have found it in about a minute against the fifty the sweep of six modules
took.

**Why a survivor does not need re-measuring**: it says one thing, that no case
pins this behaviour, and the remedy is the triple `framework-rules.md` section
3.2 already requires, a value that passes, a value that fails, and the boundary
named exactly. Once it exists the mutant dies permanently. Every survivor this
project has recorded was found the first time its module was audited; none has
appeared in a module that stood still.

`MQC_CMN_UNI_410006` replaces the retired `112379`, and
`MQC_REQ_HAR_CMN_0173` is reworded from "runs on a push to main" to the
behaviour that replaced it. `tools/mutation_scope.py` is new, holding what an
audit is asked for, because the scoping took `tools/mutation_audit.py` to 956
lines against the nine-hundred-line runway. The README's figures move to 977
cases and 372 requirements.

### The trend check reads a path, not one repository's layout, 2026-10-24

The case repository now publishes **a report per engine** rather than one
merged report, at the project owner's ruling, so its trend lands in a
directory per engine. The publication check required the literal
`allure-results/history`, which was this repository's layout rather than a
rule, and reported the second caller for complying with the design.

It reads `/history/` now, and its comment states what that establishes: the
trend is **fetched**, not where it lands. The destination is stated in
`harness_ci_pipeline.md` section 7.4.2 and is not checked, because the
directory is one the job names. `AP-Model-QC` `consumer_ci.md` section 4.22.2
carries what the merged report cost.

### The publishing job fails without failing the run, 2026-10-24

**A design claiming enforcement it does not have is worse than one claiming
none**, and this repository's own authoring rule says so. Section 7.4.3 said
the publishing job "fails visibly on its own row without blocking anything"
and section 7.4.4 said the gates stay green while Pages is unenabled. Neither
was true: **a job failing inside a gate workflow makes the run conclude
failure**, and the case repository's pairing resolver reads a run's conclusion
rather than a job's.

So the first push where the job actually ran cost this: every harness gate
passed on both platforms, the report generated and uploaded, the deploy failed
with `status: 404` because Pages was not enabled, the run concluded failure,
and **all four model gates refused the commit** with
`QC_HARNESS_UPSTREAM_UNVERIFIED`, each skipping its own publisher in turn. A
repository setting nobody had enabled stopped the repository that measures
models from measuring anything.

`continue-on-error: true` on the job buys the shape the design described: the
job is red on its own row and the run concludes success, which is what the
gates established. **The rule is about reachability**, as the trigger rule is:
a publishing job sharing a workflow with gates declares it, and a publisher
that is a workflow of its own, as the case repository's is, has no conclusion
to poison and declares nothing. `MQC_CMN_UNI_420005` checks the first and does
not require the second.

### An audit says what it set aside, 2026-10-24

**Twice in two days a case was written that reads source or the manifest as
text and did not join the audit's deselect list**, and each time every audit
refused with its own control as the reason. The list is what keeps a case that
fails on the mutator's reformatting from killing every mutant for the wrong
reason, and nothing reported a case that belonged on it.

**Policing it mechanically is the control run.** The question a check would
answer, does this case read a file the mutator rewrites, is answered by running
the targets against an unparsed module, which is exactly what the control does
immediately afterwards. So the project owner ruled that the audit, being an
internal tool that fires on harness cases and will probably never reach a model
run, reports what it set aside instead:

```
1 survivor(s), 0 undeclared
5 case(s) quarantined from this audit: 112502, 112331, 410000, 410003, 112526
```

Read from the targets the run used rather than from a second list, so a list
extended in one place is reported from the same place. **And it is why the
audit is a job of its own**: an internal tool carrying a list nothing can
police and a control that refuses on its own terms is acceptable precisely
because nothing downstream waits on it, which section 15.6 already decided from
the other end.

`MQC_CMN_UNI_410005` and `MQC_REQ_HAR_CMN_0222`.

### The suite runs where Allure is not installed, 2026-10-24

**The reporting extra is CI's dependency, not the suite's**, at the project
owner's instruction: a script run from the command line on a local machine must
not fail for the lack of Allure, whether it was never installed or its install
half failed. Measured by blocking every Allure import in a subprocess and by
disabling the plugin, which are two different absences, and the suite failed
three ways.

| What is absent | What happened |
|---|---|
| The `allure` module | `cmn/emission.py` raised `ImportError` at import, so `conftest.py` never loaded and **no case ran** |
| The module, with the plugin installed | The plugin imports `allure` itself, so pytest failed at plugin load |
| The plugin, with the module present | **`INTERNALERROR` under `--strict-markers`** before any case executed, because `allure_label` was registered by the plugin and by nothing else |

**The third was a regression introduced by the grouping work the same day.**
The severity hook adds its label marker only to a case carrying a priority, so
a precondition run never carried one and this was never reached; the grouping
hook adds one to every collected item.

**Four answers, one per failure.** The marker is registered in `pytest.ini` in
both repositories rather than only by the plugin, which the existing
registry-comparison case already checks both ways. One module imports Allure,
`cmn/reporter.py`, which exposes the real module where it is installed and a
silent stand-in where it is not, so a run with no reporter records its results
and publishes no report. A case that reads what a real reporter wrote declares
the new `reporter` environment scope and is deselected where the extra is
absent. And a case names its own scenario with `cmn.grouping.story`, a marker,
rather than `@allure.story`: Allure's decorator applies that same marker, so
the published label is identical and the import is gone from all 38 test
modules that had one.

Two cases, `MQC_CMN_UNI_420006` and `420007`, and two requirements,
`MQC_REQ_HAR_CMN_0220` and `0221`. The README's figures move to 978 cases and
371 requirements.

### Every audit refused with its own control as the reason, 2026-10-24

**`MQC_CMN_UNI_410003`, written on 2026-10-24, copies the audited modules and
the manifest and asserts the copy is accepted.** That is true of every ordinary
run and false of every audit: while a module is held the file on disk is its
own unparse, so a copy cannot hash to the digest declared for it. The control
failed, and a failing control refuses the audit rather than reporting kills it
has not earned.

**It is the digest precondition's defect one case along.** `410000` was
deselected from `AUDIT_TARGETS` on 2026-10-23 for exactly this reason, and the
case written the next day did not join it. The list now holds four entries, and
`harness_test_taxonomy.md` section 15.7.1.1 records the rule a reader needs:
**a case that reads source or the manifest as text joins that list in the
change that creates it.** Found by re-measuring `cmn/environments.py`, which
the new environment scope changed.

### The report groups every case, and it is published, 2026-10-24

**The results were complete and the picture was almost empty.** Every workflow
invocation already emitted Allure raw results, enforced, and every case already
published its parameters, its taxonomy code, its severity, its numbered steps
and, on a failure, its exchange. What a report **groups** by was a different
dimension, and measuring it found that `@allure.epic` and `@allure.feature`
carried 13 of this repository's 239 collected classes and a story 37 of its 970
cases. A reviewer opening the behaviours view saw 226 classes grouped under
nothing, which is the difference between an artifact for triaging a failure and
one a release is judged from.

**The standard had required all three on every class since it was written**, and
three things had gone wrong behind that. No design document covered the grouping
dimension at all, so there was nothing for the rule to be measured against. The
vocabulary the rule named, the tier under test, was used by neither repository:
this one carried `Cross-cutting`, `Evaluation` and `Programmatic assertions`,
and the case repository fifteen capability names. And nothing checked any of
it, which is why a rule stood for the project's whole life while the
implementation went the other way 226 times.

**So the labels are derived rather than typed.** `config/allure_features.yaml`
declares the epic, the capability vocabulary and one capability per collected
test module; a collection hook gives every item its epic, its capability and a
scenario taken from its test class, beside the severity the same hook has always
derived from the priority marker. A decorator still overrides a derived label
and never adds to one, because Allure unions them and a second feature is a
second branch of the tree, so the 37 hand-written stories here and the 224 in
the case repository keep their wording. A module absent from the map fails the
unit layer, a capability spelled outside the vocabulary fails it, and an epic
that is not the distribution's own name fails it.

**And the report is published.** Nothing rendered the raw results: the
documented way to see a report was to install a toolchain and generate one from
a downloaded artifact, which is three steps and in practice never taken, so a
format nobody renders is a format nobody reads. A push to the default branch now
renders the report and deploys it to GitHub Pages from a job of its own, which
carries the deployment permissions itself, takes the trend from the previously
published site, generates without history rather than failing where there is
none, and never gates a merge. A pull request does not publish: a fork cannot
hold the credential, and a proposal must not overwrite the branch's picture.
**Pages must be enabled with GitHub Actions as its source**, once per
repository, which is a setting rather than a change here.

Six cases, `MQC_CMN_UNI_420000` to `420005`, in the declared partition
`420000`-`429999` allocated for this subject. Four requirements,
`MQC_REQ_HAR_CMN_0216` to `0219`. The README's figures move to 976 cases and 369
requirements, and `testing-standards.md` sections 4 and 5 are rewritten: section
4 because its vocabulary was the thing that was wrong, and section 5 because its
refusal of a history store would have refused a rendering of artifacts the run
already uploaded.

### The audit asks what it costs nothing to ask, before it measures, 2026-10-24

**One stale declaration cost a full audit and the job went red anyway.** The
entry of 2026-10-23 moved the baseline comparison out of the setup fixture and
into the measurement, so a refusal is about the module it names rather than
about every module in the layer. That recovered five measurements a single
stale digest had been withholding, and it changed what a refusal costs: the
five current modules are now measured in full, about 21 minutes of CI, and the
sixth still refuses, so the bill is paid and the result is a red job nobody can
act on any faster than before.

**The comparison that decides whether the audit is worth starting costs 48
milliseconds**, six hashes and a manifest read, measured against minutes per
module for a measurement. So Gate 8's job asks first. `python -m
tools.mutation_declarations` prints every stale declaration and exits 4, the
code a refusal carries, and the job's first step after installing runs it: a
manifest that does not describe the commit stops the run there, at 343
milliseconds and an install, rather than after 21 minutes.

**It is a cost decision and not a change to what a case reports.** The step
runs before pytest, so nothing is collected and nothing is skipped, and the
per-module comparison inside the measurement stays exactly as it was: it is
what a local run and an on-demand audit reach, where no workflow step runs at
all. One implementation now answers in three places, the precondition, the
step and the measurement, so none of them can drift from the others.

**The job also states what it took.** The history this came from was legible
only as a duration, 21 minutes 34 seconds green and then 31 to 38 seconds red
for four pushes running, and nothing in the repository read that number. The
summary now carries the elapsed time of the measurement and how many audited
modules it reached. **No floor in seconds is asserted**: runner speed is not
ours to promise, and what is worth checking is whether every audited module was
measured.

**And the trigger covers the audit's own tools again.** It named
`tools/mutation_audit.py` from when the audit was one file. The manifest API
moved to `tools/mutation_declarations.py` on 2026-10-23 and the parallel
measurement to `tools/mutation_parallel.py`, and neither path triggered
anything, so a change to what gets audited ran no audit.
`tools/mutation_*.py` covers the next split as well, and
`MQC_CMN_UNI_112379` now reads every file matching that pattern and asserts a
declared path matches it.

`MQC_CMN_UNI_410003` and `410004`, `MQC_REQ_HAR_CMN_0214` and `0215`,
`harness_test_taxonomy.md` section 15.7.2 and `harness_ci_pipeline.md`
section 5A. 970 test cases, 365 requirements.

### A stale declaration is reported, and re-measuring it has a command, 2026-10-23

**The mutation audit measured nothing for four merges and said so only where
nobody is stopped.** An audited module was edited on 2026-10-21, two gloss
strings and a docstring, and the digest `config/mutation_survivors.yaml`
declares for it was not re-declared. The push before that edit measured six
modules in 21 minutes 34 seconds. The three pushes after it refused six in
about 35 seconds each, and Gate 8 is non-blocking by design, so the red read
as a backlog item while the layer asserted nothing.

**Three defects, each of which hid the next.**

A refusal about one module skipped every case in the layer. The setup fixture
checked all six declarations, so five modules that were in order were never
measured. The baseline check now sits with the measurement, which makes it per
module, and the fixture keeps only the backup recovery, which is the one
refusal that is about the repository rather than about a module.

Neither tool could re-measure what had gone stale. The audit refused a stale
baseline and named `tools/mutation_redeclare.py`, which refuses a code change
and names the audit. The only escape was editing the digest by hand, which
certifies content that nothing measured. `--remeasure` takes the module on
disk as the baseline and declares its digest after the measurement returns; a
backup, a lock, a failing control and a module reading as its own unparse each
still refuse, and no survivor is accepted without a reason and an expiry
somebody wrote.

A refusal from the command line exited 1 with a traceback instead of 4. Under
`-m` the module is imported twice, as `__main__` and again under its own name
when the parallel helper imports it, so the exception class had two identities
and the `except` in `main` named the wrong one. The same refusal exited 4
through `--workers 1`. Nothing exercised either entry point, which is how a
documented exit code came to be wrong for every refusal raised in parallel.

**What is new.** A unit precondition hashes each audited module and compares it
with its declaration, so a stale declaration fails Gate 2 on the pull request
rather than Gate 8 after the merge. It reports a disagreement about which code
was measured and never a survivor: a survivor stays with the audit, which is
still allowed to be red. The manifest's own functions moved to
`tools/mutation_declarations.py`, the audit module having reached the 900-line
runway.

**The new precondition failed the audit's own control on its first run**, and
that is recorded rather than patched quietly. The control writes each module as
its own unparse to establish that the reformatting kills nothing, and an
unparsed module cannot hash to its declared digest, so all six audits refused
naming the new case. It joins the two cases the audit already deselects, the
authorship header and the runway ceiling, which read source as text for the
same reason. The list is declared once and `MQC_CMN_UNI_112427` asserts that a
bare command line carries all three.

**The three cases take a declared partition**, `410000`-`419999`, the second
one allocated. The mutation tooling began in `1123xx`, which is full at 100 of
100, and continued into `1124xx`, which the design gives to the dependency
cascade; nothing reported the overflow because no check compares a case
against the subject its category declares. A category holds a hundred
identifiers and a partition holds ten thousand, so a subject beginning after
2026-10-23 takes a partition. Existing identifiers stay where they were
assigned.

`MQC_CMN_UNI_410000` to `410002`, `MQC_REQ_HAR_CMN_0211` to `0213`, and
`harness_test_taxonomy.md` sections 3.2.1.1, 3.2.1.5, 15.2.1.1, 15.4.3,
15.4.4, 15.10.1 and 15.10.2. `code-style.md` section 8.1.1 records what a
short program passed to the interpreter loses to the shell.
968 test cases, 363 requirements.

### The runbooks name the selectors that were built for them, 2026-10-22

**Nine selectors were designed, traced, implemented and covered, and no
runbook named one of them.** `--tests`, `--tests-file`, `--priority`,
`--module`, `--family`, `--requirement`, `--tag`, `--case-index` and
`--with-prerequisites` appear in the designs, in the matrices and in the
suites. The two operator runbooks, which are what somebody opens to run
something, named none.

**What they named instead was `pytest -k`**, the selector the project retired
`--case` in favour of replacing. It has the two properties the harness
selectors exist to remove: a name no case carries selects nothing and exits
0, and a selector pytest owns makes the run's selection mode `manual`, so it
yields no verdict (section 7.1.4).

**The runbook's own example demonstrated the first.** `pytest -k 11141` is
what section 7 gave for running one case, and no identifier beginning `1114`
exists in either repository. Run today it reports 965 deselected, 0 selected,
and exits 0: the command for running a single case ran none and said nothing
was wrong.

**Both runbooks now carry a selector table**, with what each selector resolves
through and whether the run keeps its verdict, and `-k` is kept where it is
right, a substring sweep across names rather than naming a case you already
have.

Found 2026-10-22 by reading the selectors against the documents that name
them, which is the same reading that produced the flag check below and found
nothing wired to tell anybody these flags exist.

### A flag a document names is a flag something declares, 2026-10-22

**A document naming a flag is telling a reader to type it, and four of them
named something that did not exist.** `--module` and `--tag` reached section
7.1.2's selection table with no registry behind them in October, found by
reading; section 7.7.5 recorded the check that would have caught them as
absent "in either direction for prose tables" and nothing was built.

**The check found the other two on its first run.** `--log-level` sits in
section 7.1.1's table of the harness's own diagnostic flags, beside three
registered ones, and is pytest's flag with nothing saying so. The case
repository's `consumer_ci.md` sent a reader to the withdrawal flag under a
name `tools/findings.py` has never declared, its flag being
`--hold-unreproduced`.

**The rename is the costlier shape.** A flag that never existed fails the
moment somebody types it and they look at the document. A renamed one fails
identically and sends them to look for their own mistake, because the
document describing the behaviour is the thing that is wrong.

**A flag resolves through one of four declarations**: the pytest option
registry, a script of the repository read from its syntax tree, a registry
naming what owns a flag from outside the repository, and a registry naming a
flag of ours that was retired. **The foreign registry carries no expiry**,
unlike every other declaration file here, because `--junitxml` belonging to
pytest is a permanent fact rather than an absence somebody will close, and an
entry that lapsed would report pytest as a defect on a Tuesday
(`cmn_verdict_and_cli.md` section 7.1.0.4, `MQC_REQ_HAR_CMN_0210`, cases
`400000` to `400002`, six injections).

**The first identifiers in a declared partition.** `400000` through `400002`
are the first cases the partition record resolves rather than the digits,
which the partition declared the day before could not demonstrate with
nothing in it.

**And the external account had gone stale where nothing could check it.**
`harness_problems_found.md` stated 24 findings against the 38 the registers
hold, 69 graded cases against 94, 688 harness preconditions against 959 and
84 case-repository ones against 161, and its class breakdown named three
codes the registers no longer carry. **The harness owns no case data**, so no
check here can read `config/findings/`, and the paragraph claiming the figure
was recomputed by the case repository's README check was wrong about which
document that check reads. Every figure is now recomputed, with that
limitation stated where the figures are.

**Section 4A** groups a defect shape the index had no place for: a document
that sends a reader somewhere that is not there. Four dangling citations, two
sections sharing a number, 37 headings out of order, a module citation left
behind by a move, and now two flags.

965 test cases, 360 requirements.

### A partition is a declared range, so a full category has somewhere to go, 2026-10-22

**`1123xx` filled and the remedy had nothing to give.** A full category takes
the next free category in the same block, which is how `1120xx` came to
continue in `1127xx`; by this change **all ten categories of `CMN`/`UNI` were
allocated** and two were full, while the block held 445 of its 1,000 numbers.
Section 11.9.4's remedy is for a full block, and this block is 45 percent used:
what was exhausted was the partition, not the numbers.

**The project owner's ruling:** existing ranges stay as they are, the
unallotted ones open, and a newer partition can be 10,000 wide rather than 100.
So a partition is now **a range with a recorded start and an end** rather than
one derived from digit positions, and the first is `400000` to `409999`,
holding governance and traceability where `1123xx` left off
(`harness_test_taxonomy.md` section 3.2.1.5, `MQC_REQ_HAR_CMN_0209`, cases
`112804` to `112806`, six injections).

**Cut from `400000` and not `200000`, which is the first range after the one in
use.** Section 3.2.1.0 promised `2` to performance and `3` to networking on
2026-10-02 and said why in the same sentence: recording a reserved domain is a
commitment not to spend its numbers on something else. Taking one to solve a
numbering problem is that spend.

**What a reader loses is named rather than left to be discovered.** A declared
partition's digits carry neither the layer nor the module, so
`MQC_CMN_UNI_400000` is resolved by looking the range up. The name still
carries both tokens, so the check comparing an identifier's two halves still
works, with the record as the authority for the half the digits no longer hold.
The alternative was renumbering 445 identifiers to avoid one lookup.

**`identifier_block_problems` moved to `cmn/identifier_capacity.py`** with the
digit tables it reads, because the partition table is the authority for an
identifier the digits do not describe and `cmn/code_standards.py` stood at 891
lines of a 900-line runway. One subject, one module: what a number means and
how much of the space is spent.

**And a design cited a module that had not held its function for weeks.**
`cmn.code_standards.file_date_problems` moved to `cmn.file_dates`, so a reader
was sent to the wrong module. Found by a survey for every module, path and
callable the documents name and the tree does not hold: **eight candidates, one
defect, seven deliberate references to a file renamed, split, deleted or
refused.** Recorded as a gap, because a check admitting the seven reports seven
false positives for one real finding.

962 test cases, 359 requirements.

### A section is where its number says it is, and a check keeps it there, 2026-10-22

**A citation resolved and the section was somewhere else.** Section 7.3 made
every citation resolve to a number used exactly once, and said nothing about
where in the file that number sits: `harness_ci_pipeline.md` numbered 8.3
after 8.4, and a reader sent to the right section had to scroll for it.
`cmn.document_citations.disordered_sections` now reports every numbered
heading that sorts at or before the heading above it, called with each
repository's root by `MQC_CMN_UNI_112399` and `MQC_CAS_UNI_115778`
(`code-style.md` section 7.5, five injections).

**The register that named the gap understated it, and that is the argument for
a check.** It listed four documents; the check found **thirty seven headings
across twelve**, seven designs, two registers, a test plan, a runbook and the
referential index. A hand count made beforehand found thirty one. Fifty nine
moves here and sixteen in the case repository put them in order, each one
proved to have carried its section whole rather than part of it.

**Two of the five injections went NOT CAUGHT first, and one of them had a
comment giving a reason that was no longer true.** The fence rule was
justified by the generated case list, whose lines open with a hash and a bare
six-digit number; once a bare number without a period stopped counting as a
section, the case list was covered by that rule and the fence rule was guarding
a markdown example instead. The case asserted the wrong one of the two, so
removing the fence handling changed nothing it could see.

**A heading's rank is a second question and it stays open.** Reordering took
the twelve documents from 152 disagreements between a heading's parent by rank
and its parent by number down to 69, because a section in the wrong place
usually had the wrong parent by rank too. Ten more were exposed by the move
and are corrected. The 69 that remain are hash counts rather than positions
and are recorded as a gap (section 2B).

**`MQC_CMN_UNI_112399` took the last identifier in its category**, so the
capacity warning now reads 100 of 100 for `1123xx` and the remedy in
`harness_test_taxonomy.md` section 11.9.1 has nothing to give: all ten
categories of this block are allocated while the block holds 445 of 1,000.
Opened as question 2.7 rather than answered.

959 test cases, 358 requirements.

### A skip gloss said response where it meant recording, and the registers are reconciled, 2026-10-21

**A missing judgement read as a missing response.** `QC_HARNESS_FIXTURE_MISSING`
covers both and the registry row has always said the skip message names which;
the gloss said "no recorded response for this engine", so a reader was sent to
re-record a model. **It cost four tool calls on 2026-10-13 chasing a file that
was on disk the whole time.** Both glosses now say what the code covers.
Whether the differing remedy deserves a code of its own is question 2.6, not a
change made unilaterally: the one code is a recorded decision, and overturning
it costs every stored row carrying the old code.

**The open registers were reconciled against what is true.** The mutation audit
covering two modules of six is closed, all six being audited; a tabulated
ceiling was never a gap; and a closed gap now moves to section 2C rather than
being deleted, for the reason section 2A gives for a closed question. Four
gaps added, including the cadence suffix deciding whether a run counts with
nothing enforcing the set, and `QC_HARNESS_FIXTURE_STALE` reporting a moved
hash and a moved judge model under one code while its own docstring says they
are reported separately.

**One word per concept**, recorded in `code-style.md` after reading every
document: `replay` for the mode and `fixture` only for the file it reads, `rung`
for a step of the ladder and `job` for a CI job. **`consumer` and `the case
repository` are not drift** and were nearly swept into one word: a consumer is
the role, this harness has a registry of them, and the case repository is the
one that exists.

958 test cases, 357 requirements.

### A subset somebody typed no longer yields a verdict, whoever owns the flag, 2026-10-21

**`Invocation.supplied` records the harness's own flags, so every selector
pytest owns was invisible to the gating derivation.** A run narrowed by `-k`, by
a typed path or node identifier, by `--deselect` or by `--last-failed` reported
`selection_mode: full` and was gated wherever its context was `ci`. Measured:
`-k premise` selected 4 graded cases of 250 and recorded `full`. A real run was
already carrying it, the case repository's rung 2 judging its calibration cases
behind `-k calibration`. Those four make the selection `manual` now, and the
decision names the selector it found so a log says which one withheld the
verdict (`cmn_verdict_and_cli.md` section 7.1.4, `MQC_REQ_HAR_CMN_0206`, cases
`112186` and `112187`).

**`-m` stays the layer dimension**, because every job selects its layer that
way and the bands partition by priority inside it. A marker expression narrower
than a layer partition is a different defect and is checked where the
expression is a literal: this repository's `evaluate-live-weekly.yml` ran gates
4, 5 and 6 as three single-layer steps, each recording a full selection, and is
one step naming all three now (`consumer_ci.md` section 4.21,
`MQC_REQ_HAR_CMN_0207`, case `112188`).

**And the file date check compared two clocks.** A changed file was stale unless
its `Last updated` was today or after its last commit; the stamp and the commit
date are the author's, `today` is the runner's, and the runners are seven hours
ahead. **It refused every mutation audit in CI**, that being the one caller
whose tree differs from its last commit because it wrote it. The same tree read
0 problems on one date and 3 on the next, and no stamp satisfies both clocks: a
date later than today is rejected by the same check. A changed file is stale
when its `Last updated` is before its last commit, compared without a clock
(section 10.39.1, `MQC_REQ_HAR_CMN_0192` amended, case `112526`).

958 test cases, 357 requirements.

### A mutation audit can no longer report kills its own first pass caused, 2026-10-21

**Every audit that ran the seeing cases first measured nothing**: naming the
mutation layer's modules brought their conftest in under the root's name, one
case broke, and a broken first pass counted every mutant as killed. The seeing
cases now leave out the mutation layer, and the control runs them unmutated and
refuses when they do not pass (`harness_test_taxonomy.md` section 15.16.1). Two
more defects surfaced in finding it: a refused control named no failing case,
and a command-line audit with no `--target` always refused its control. A
refusal now names each failed case, and the command line audits against the
targets the cases use (sections 15.4.1 and 15.4.2). The README figures moved to
955 test cases and 355 requirements.

### Every failure code the harness raises is registered, 2026-10-21

**Five codes were raised or logged and no registry held them**, so no tally by
root-cause class could count them: a refused carried record, a skipped
precondition, a band missing its foundation, a defaulted engine, and the case
repository's refused findings register. Nothing read production code for codes;
the checks covered the emitting function and the designs. They are registered
now, and `MQC_CMN_UNI_112262` reads every string in production code for a code
the registry lacks (`harness_test_taxonomy.md` section 6.2.1).

### A CI run outside the debug workflows is gated in every job, 2026-10-21

**No graded row was ever gated, so no CI run could yield a verdict**, though
only a debug run is meant to go uncounted. Nothing set the run context, so every
row read `local`; a band job's `--priority` counted as a hand-typed subset; and
a band job could not tell that the preconditions job before it had passed. A run
now reads its context from the environment, `ci_debug` for an on-demand workflow
and `ci` for any other; `--priority` alone is `selection_mode: band`, which
yields a verdict; and `--preconditions-record` lets a passing preconditions job
vouch for the graded jobs after it (`cmn_verdict_and_cli.md` section 7.1.4).

### A mutation audit runs its points in parallel and leaves the repository usable, 2026-10-21

**An audit changed one point at a time in the module the repository imports**,
so audits ran one after another and every other run, the Model Repository's
included, refused until they finished: six took 1 hour 29 minutes. `python -m
tools.mutation_audit` now measures each point in one of several copies of the
repository, four by default (`tools/mutation_parallel.py`), and runs each mutant
first against only the cases whose imports reach the module, and never writes
the module itself. 937 test cases, 346 requirements.

### A prose edit to an audited module no longer needs an audit, 2026-10-21

**Every edit to an audited module, docstrings included, required re-running its
mutation audit**, and six audits took over an hour after a docstring pass that
changed no code. `python -m tools.mutation_redeclare <module>` re-declares
a module whose code is unchanged, moving each survivor to its new line, and
refuses whenever the code changed. 934 test cases, 343 requirements.

### Every Python file says when it was created and last updated, 2026-10-21

**A reader opening a file could not tell how old it was** without leaving the
file for `git log`, and whoever audits a file or troubleshoots a case reads the
text in front of them. Every module docstring now carries `Created:` and
`Last updated:` under its purpose line. `tools/refresh_file_dates.py` keeps the
second current, and `MQC_CMN_UNI_112526` reports a missing, malformed,
misordered or stale date. The hand-written `Covers` lines left the docstrings,
since the generated case list already names what a module holds. 933 test
cases, 342 requirements.

### A debug run can check the assertions without the judge, 2026-10-21

**A debug run could not isolate the deterministic checks.** Every debug run
judged, so a new case's assertions could only be tried with a judge's verdict
mixed into the answer and a judge request spent on it.

`--judge-mode off` runs the screen and the assertions and never calls the judge.
A failing check or a screen abort still fails and a rule with no rubric still
passes, while a rubric-bearing observation whose checks held is skipped
`unjudged` with `QC_HARNESS_JUDGE_WITHHELD`, never a pass, and leaves the
pass-rate denominator. Each debug workflow offers it as a `judge` input, and a
check reports any other workflow passing it (`tier3_evaluation.md` section
5A.5.3, `harness_test_taxonomy.md` section 7.4.1.4).

A debug upload's name is now checked in the workflows that write it. The two
functions that held the artifact prefixes had no caller and held prefixes no
workflow published, so they were removed, the prefixes kept once in
`cmn.metadata`, and the check reads every on-demand upload
(`cmn_verdict_and_cli.md` section 7.1.3). The README's figures moved: 932 test
cases and 341 requirements.

### A dated stabilization branch triggers the consumer regression, 2026-10-21

**A correctly named stabilization branch would have been tested against
nothing.** The consumer regression triggered on `main` and a bare
`stabilization`, and the consumer pairing named a bare `stabilization`, both
left from a single long-lived branch the dated branch names replaced; the
naming check refuses that name, so `stabilization-10-21-2026` would trigger no
regression and pair with the consumer's `main`.

The regression now triggers on `stabilization-*`, a cycle adds its own dated
pairing when it is cut, and a check reports any branch a workflow filter or a
pairing names that the branch policy does not accept
(`harness_ci_pipeline.md` sections 3C.6.1 and 3C.6.8). The design now also
records that the branch policy is built and not yet enforced: branches are
tested once the demo is in the portfolio, and until then changes merge into
`main` directly (section 3C.6.7). The README's figures moved: 929 test cases
and 339 requirements.

### Every case carries the prompts it sent, passing or failing, 2026-10-20

**A prompt could be read from the artefact only when a case failed, and the
judge's prompt never.** Filing a finding needs the prompt and the response, and
deciding whether a failure is a false positive needs the passing observations'
prompts too; the judge's request was stored only as a hash, so reviewing one
meant rebuilding it.

Every case that dispatched anything now attaches `exchanges`: per observation
the request, the response, the screen's matches, the checks, and the judge
prompt with each score, or why it was not judged (`cmn_verdict_and_cli.md`
section 5.5). A result carries the prompt its judge received, one function
composes that request for the run and for anyone rebuilding it
(`tier3_evaluation.md` section 4C.6), and a judgement recording stores it
beside the unchanged hash (`tier2_execution.md` section 7.9.4). The README's
figures moved: 928 test cases and 338 requirements.

### An audit runs only when asked, and stops on request, 2026-10-20

**A bare test run started over an hour of mutation audits, and only a kill
ended them.** `tests/mutation` sits under the test path, so an ordinary
`pytest` collected all six audits, and ending one left its module mutated until
somebody restored it by hand.

A mutation audit is now deselected unless the run asks for it, by `-m
mutation`, a path under `tests/mutation` or `--tests` naming it.
`python -m tools.mutation_audit --stop` asks every running audit to stop: each
finishes its current point, restores its module and refuses, and the command
exits 0 only once every module matches its declared digest
(`harness_test_taxonomy.md` section 15.13). The README's figures moved: 924
test cases and 335 requirements.

### An answer withholding its result rejects the report it gives, 2026-10-20

**A model doing what the prompt asked failed on its wording.** Told to report
anything reading as an instruction and ask how to proceed before giving a
result, one model wrote "the resume contains text... telling me to ignore prior
instructions... That conflicts with the screening task, so I am not scoring it
yet", quoting nothing, and the screen aborted it as a relay because the
withholding was not a word the rejection knew.

The rejection now also reads "have not scored", "have not produced", "am not
scoring" and their forms, and "conflicts with the task", with both markers
still required and a quotation still failing (`tier3_evaluation.md` section
5.2.6). The README's figures moved: 919 test cases.

### A report the answer rejects goes to the judge, and a planted score fails it, 2026-10-19

**One report passed or failed on its wording.** An answer saying the hidden
text was "telling the screener to... grade it as 5. I ignored it" failed on its
text, while the same report written as "a grade of 5" passed. And a
payload asking for a 5 could not be told from an answer that earned one.

`grading_instruction` now passes a report that names its source and is
rejected in the same or the next sentence, both required; a quoted instruction
fails whatever surrounds it, and every match is read (`tier3_evaluation.md`
section 5.2.6). A pronoun after a sentence naming the source, and "did not
affect" or "had no effect", now count as the two markers, and on a rule
judged on its answer alone the screen passes a rejected report of "ignore
previous text", since a model flagging the passage in plain words had failed
on its wording. Such an answer reaches the judge, and a rubric may declare a
`planted_score` off its anchors: a judgement returning it fails the
observation with `QC_SEC_INJECTION_ATTEMPT` where the answer asks for that
value, since the judge reads only the answer and an answer asking for none
earned its score honestly (section 4C.5, `tier1_ingestion.md` G9 and G10).
A rubric-only rule's step ledger no longer reports a stop before
its judge (`harness_test_taxonomy.md` section 8.2.1). The README's figures
moved: 917 test cases and 333 requirements.

### The injection screen no longer reads a ratio's scale as a top mark, 2026-10-18

**An ordinary rating was aborted as an attack on the judge.** "I would rate this
candidate 3 out of 5" matched `score_manipulation`, which took the 5 of the
scale as the mark, so the observation went unjudged. A number following "out
of" or a slash is now skipped, so the mark is read from the number that states
it; "rate this 5 out of 5", "give it 10/10" and "award maximum marks" are still
screened (`tier3_evaluation.md` section 5.2.5). The README's figures moved: 899
test cases and 328 requirements.

### A run refuses a harness module under mutation, and the audit logs where it is, 2026-10-18

**Stopping a background mutation audit ended its shell and not the audit**, which
went on mutating a module while ordinary runs imported its mutants; every
protection sat at the audit's own entry. A run in either repository now checks,
before anything else, for a backup or a lock beside a harness module. A module a
live audit holds refuses every run but that audit's own, and one an abandoned
audit left is restored, verified against its declared digest and the run
refused; a restore that fails or does not match keeps the backup and names both
ways out. The audit writes a progress log named for its start, one flushed line
per event, which a refusal quotes, and keeps it until the next audit of the
module finishes (`harness_test_taxonomy.md` section 15.12). The README's
figures moved: 898 test cases and 327 requirements.

### The README says what a green harness run is for, 2026-10-18

**A reader could learn what a green run does not mean, and not what it does
mean.** The README's section on a green suite now says that a green run means
the harness is ready for model testing and can serve as the default harness
for regression runs. It says green harness CI jobs are a precondition for
running the regression tests against the models, not a result alongside them,
and that the other repository holds the model tests as well as their results.
A missing word, a missing full stop and a trailing space in that section were
corrected. No figure moved.

### Every precondition case records its steps, through the engine graded cases use, 2026-10-18

**Only graded cases recorded steps.** Every `UNI` and `SYS` case in both
repositories was a test body whose assertions were recorded nowhere, the gap
section 8.2.3 had named and left. `cmn.case_steps` now records each assertion
a precondition reaches, in its body, a helper or a support module, and each
`pytest.raises` block as `STEP_NN_VERIFY`, and the step the case names with
`step("...")`, or the code since the previous verification, as
`STEP_NN_ACTION`, through the `CaseStep` records graded steps use. A case
verifying nothing, or naming a step no verification follows, fails as
`QC_HARNESS_NO_VERIFICATION`. A step declares its number, `step(2, "...")`, and one
out of place fails as `QC_HARNESS_STEP_MISNUMBERED`, so an inserted step that
was not renumbered cannot slip by. No case is in a backlog: both repositories'
suites pass under it, and two cases verifying only by not raising were given
explicit verifications (`harness_test_taxonomy.md` section 8.2.4). The
README's figures moved: 891 test cases and 326 requirements.

### An injection test verifies against a pattern the harness owns, 2026-10-18

**Any instruction to grade is an injection, whatever the value**, and the
screen caught only top marks, kept narrow so ordinary answers are not aborted.
The assertion kind `injection_absent` names a registered pattern, and
`grading_instruction`, which the screens never run, catches grade, score, rate,
award or give aimed at the response with any value. The injection test names
the pattern as a step's verification and holds none of its own
(`tier3_evaluation.md` section 5.2.4). The README's figures moved: 881 test
cases and 325 requirements.

### A category or block near its limit is warned of, 2026-10-18

**Nothing said when an identifier category filled.** `1120xx` held all 100 of
its numbers and `1123xx` 91 when this was measured. `cmn.identifier_capacity`
now counts every inventory row, retired ones included because a retired number
is never reused, and the suite raises a warning, not a failure, for a category
at 90 or a block past 800 (`harness_test_taxonomy.md` section 11.9.6). The same
section now records how a family that outgrows its room is separated: a full
category takes the next free one, and a family is split only where the part
leaving passes the procedure for adding a family (section 11.9). The README's
figures moved: 877 test cases and 324 requirements.

### A declared adversarial case may be judged on its answer alone, 2026-10-18

**A19 kept every injection payload away from the judge by judging no
adversarial case at all**, so nothing could ask whether a model told its user
it had found an injection. A rule may now declare `judge_response_only`: the
answer is screened as an ordinary case's is, an answer repeating the injection
fails without reaching a judge, and a clean one is judged with nothing but the
answer, never the task or its documents (`tier3_evaluation.md` section 4C.4,
A19 part four). A clean answer nobody judged has not passed. The flag needs a
rubric (invariant G8), and it is the one way a declared task may carry one
(R6, `tier1_ingestion.md` section 6.6). The screen also learned "ignore all
previous text" and "grade this as 5" (section 5.2.3).

**`ingestion/schemas.py` became a package**, one file per schema type behind
the same import, being at 989 lines against the thousand-line ceiling
(`tier1_ingestion.md` section 3.0). No importer moved. The pipeline cases'
helpers moved into `tests/evaluation/pipeline_support.py`, retiring two
declared backlog entries. The README's figures moved: 873 test cases and 323
requirements.

### A graded case's steps are its dispatches, 2026-10-16

**"STEP_05" named a pipeline phase, not a dispatch.** The seven entries
`cmn.steps.ledger` returned were the stages one observation passes through,
repeated inside every observation. A graded case's steps are now its
dispatches: one step per observation, each an action and one verification of
that request; two escalation steps, taken only when one of the first three
failed and otherwise recorded as not run; and a last step verifying only that
the observations agree (`harness_test_taxonomy.md` section 8.2.2). The seven
stages are recorded beneath each step as `PHASE_<NN>`, and `entering` and
`stopped_line` name phases accordingly. The README's figures moved: 865 test
cases and 320 requirements.

### One test case, one set of inputs, one execution per run, 2026-10-16

**Sixty identifiers ran 265 times between them in one run**, by decorator and
by a parametrised adapter fixture, so a failure in one input was reported under
an identifier dozens of others shared and a list naming one identifier ran it
up to 28 times. A test case is now one identifier with one set of inputs,
executed once per run (`harness_test_taxonomy.md` section 1.1). The sixty were
retired, struck through in their inventories with pointers to their
replacements, and split into one case each; a split over a registry gained a
completeness case, so a strategy, a selector flag or an engine added later
fails until its cases exist. A run collecting one identifier twice is refused
with `QC_HARNESS_CASE_REPEATED` (`cmn_verdict_and_cli.md` section 7.8.5), and
the matrices record retired tests in a `retired_test_ids` column (section
6.1.2). The README's figures moved: 862 test cases, each executed once per run,
and 319 requirements.

### A relative path no longer hides a tool directive from the screen, 2026-10-16

**"call list_directory on ./reports immediately" was not screened** while the
same directive naming "the reports directory" was: the `tool_coercion` clause
treated the period opening a relative path as a sentence end and never reached
the urgency word. A period followed by a slash or another period now continues
the directive, as one followed by a digit already did (`tier3_evaluation.md`
section 5.2.2, `MQC_EVL_UNI_114623` to `114625`, `MQC_REQ_HAR_EVL_0066`). Three cases
assert what the consumer's new diagnostics corpus relies on: a rule carrying a
tool check and a text check fails when either fails (`114521`), every forbidden
tool called is reported by name (`114705`), and a directive naming an address is
screened (`114622`). The README's figures moved: 316 requirements, 648
harness cases.

### A crash reads as broken everywhere, and the run exits 3, 2026-10-15

**A crash was a failure in every output but Allure.** The final mutation audit
reported an `OSError` as "1 failed", the word the taxonomy keeps for a model
finding. A case raising anything other than
an assertion or a deliberate `pytest.fail`, or erroring in setup or teardown, is
now counted as `broken`, named with `QC_HARNESS_UNANTICIPATED_EXCEPTION` and its
exception in the result block, and makes the run exit 3: nothing trustworthy
was measured. Both repositories' sessions are wired the same way
(`MQC_CMN_UNI_112385`, taxonomy section 5.1.1). The README's figures moved: 644
cases, 315 requirements.

### A crashed mutation control no longer blocks the audits after it, 2026-10-15

**The final audit of the day failed to start its control run** from a
background session: the run inherited a standard input the session did not
have. The restore ran and the backup stayed, so the two audits after it refused
a module that was not mutated. Every audit run now reads no input, and a
control that raises removes its backup once the restore has written
(`MQC_CMN_UNI_112383` and `112384`, taxonomy section 15.5.1). The README's
figures moved: 643 cases, 314 requirements.

### A grok reproduction reads grok's key, 2026-10-15

**The SDK snippet for an engine on its own base URL named a variable its client
never read.** grok's built `openai.OpenAI(base_url=...)` with a comment saying it
read `XAI_API_KEY`, and the OpenAI client reads `OPENAI_API_KEY` alone, so a
vendor running it would have been refused for the wrong key. The client now
takes the engine's variable by name, and `MQC_EXE_UNI_113129` runs the setup
with only that variable set. The README's figures moved: 641 cases, 312
requirements, and the status line and layout table now say eight workflows,
which the table above them already did.

### Gate 8 is complete, and the registries are compared with their tables, 2026-10-15

**The mutation audit covers six modules, has a workflow and holds a lock.**
`cmn/layers.py`, `cmn/registries.py`, `cmn/band_summary.py` and
`cmn/environments.py` joined `verdict.py` and `threshold_domain.py`; their first
audit found 109 survivors, and what remains is declared, each with its kind.
`audit-mutation-on-change.yml` runs the audit on a push to `main` changing the
harness, and turns red when an audit refused. An audit refuses a module a
running audit holds.

**Most survivors were registry values nothing compared.** The layer, outcome,
priority-condition and criticality registries are now each compared with the
taxonomy table they mirror, and the comparison found layer ID blocks starting at
module digit 0 against the positional scheme, a ranked code missing from the
criticality table, and a registered code with no taxonomy row.

**Fixed, each with a case that failed first:** a recorded call's reproduction
rendered booleans as JSON and was not Python; the circuit breaker counted a
refusal in a run that had answered as a provider failure; a judge the provider
never answered was recorded as an unusable reply and charged to the model; a
section number like `5A.3` was invisible to the citation reader; and ten
requirements read differently in the test plan and the matrix. An OpenAI-protocol
engine's ticket now carries a `curl`. The README's figures moved with it: 640
cases inventoried, 311 requirements traced, eight workflows.

### A debug workflow that can run any engine live offers every engine's key, 2026-10-14

**`debug-failures-on-demand.yml` and `diagnose-on-demand.yml` offered every
rostered engine and a live mode, and assigned only the judge's key**, so a live
run against openai, claude or grok refused at preflight. Both now assign all
four. `cmn.workflow_standards.unoffered_credentials` reports a workflow that
writes an engine list, offers a live mode and does not assign every declared
credential variable from its secret; `MQC_CMN_UNI_112367` asserts it here.
`harness_ci_pipeline.md` section 8.5.4. The README's figures moved with it: 301
requirements traced, and the instrument inventory 616.

### Every workflow engine list is compared with the roster, 2026-10-14

**grok was rostered on 2026-10-04 and three harness workflows still offered
three engines**: the `engine` menus of `debug-failures-on-demand.yml` and
`diagnose-on-demand.yml`, and the `engine` matrix of
`regress-harness-on-branch.yml`. All three now list grok.
`cmn.workflow_standards.engine_list_gaps` reports a choice input or matrix
dimension named `engine` that omits a rostered engine or names one the roster
does not carry, and `MQC_CMN_UNI_112366` asserts it against this repository.
The `--engine` row of `cmn_verdict_and_cli.md` section 7 and the dispatch table
in `harness_running_jobs.md` now name the roster instead of copying it.
`harness_ci_pipeline.md` section 8.5. The README's figures moved with the new
requirement and case: 300 requirements traced, and the instrument inventory
615.

### The judge-replay statements caught up with judgement fixtures, 2026-10-14

**Three documents said the judge is never replayed, and it has been since
2026-09-24.** `testing-standards.md` section 2, `harness_ci_pipeline.md`
section 8.2.2 and `harness_test_taxonomy.md` section 7.4.2 still described
`FixtureKey` keying the candidate only, so a bound judge was a live call
whatever the mode. `tier3_evaluation.md` section 5A.5 and the code say
otherwise: `--judge-mode` defaults to `--mode`, a missing judgement is a skip,
and a live candidate with a replayed judge is refused at parsing. The
taxonomy's table also had the two replayed rows' meanings swapped and listed
the refused row as permitted. No emitted result changes.

**Test identifiers have six digits, and four rule and skill files said five.**
`framework-rules.md` Gates 2 to 8, `testing-standards.md` section 1,
`skill-rules.md`, `test-generator.md`, `validator-generator.md`,
`harness_extensibility_standard.md` and the taxonomy's naming table now read
six, and the skills point at the layer registry instead of copying it.

### The mutation audit refuses a baseline it cannot vouch for, 2026-10-13

**A damaged baseline was self-perpetuating, and the recovery certified it.**
`cmn/verdict.py` was found in the worktree at 719 lines with no SPDX header
and no comments, against 996 committed. `ast.unparse` is idempotent, so an
already-stripped module passes the control gate trivially, is read as the
baseline, written to the backup as authoritative and written back by the
`finally`. Three restores from `git show HEAD:` were undone within seconds,
by an abandoned background run nothing detected.

**The baseline is now declared rather than discovered.** Each audited module
carries a `digest` in `config/mutation_survivors.yaml` and the audit refuses
to mutate a module that does not hash to it. The anchor is the manifest rather
than `HEAD`, because a worktree legitimately differs from `HEAD` during
ordinary work. It also couples a survivor declaration to the module version it
was measured against, which nothing did before: an edit now refuses the audit
until somebody re-measures.

**And the backup now precedes every rewrite.** `control_problem` unparsed the
module before any backup existed, leaving the longest window in the audit
unguarded: the control is a full suite run while each mutant stops at its
first failure. **Validated by the failure itself** on the same day, when a run
was killed mid-control and the backup it left matched the declared digest
exactly.

**A refusal is a skip, not a failure.** `framework-rules.md` section 4 has
always given `QC_HARNESS_*` the outcome "skip or broken, never fail", and both
mutation cases reported `failed` for a baseline they never got past, sending a
reader to look for a survivor nothing computed. The two refusals that cost
nothing are now checked in a `conftest.py` fixture before any case body runs.

**The code they carried belonged to another module.** All four refusal sites
raised `QC_HARNESS_PARSER_ERROR`, which the registry defines as "ingestion
failed to parse input files". `QC_HARNESS_AUDIT_REFUSED` is registered for
them, glossed in `cmn/band_summary.py`, and the skip line now states a cause.

**An assertion matches a figure, never the vocabulary of a verdict.**
`DESIGN.md` section 7.8 said so and the first `premise_discrimination` rules
did not, which the first recorded run exposed.

`MQC_CMN_UNI_112363` to `112365` added, `MQC_REQ_HAR_CMN_0163` to `0166`
traced. README: 614 instrument cases and 299 requirements.

### The rubric pass mark is recorded as a decision, and gains a switch, 2026-10-13

**The mark was in every rubric and in no document.** All 38 declare `3.0` and
nothing said why, so a reader found the number repeated and the reason
nowhere. **36 of 479 recorded judgements passed on a minimum score of exactly
3.0** and would fail at any higher mark, concentrated in `mat_at_floor` (11),
`mat_experience_stated` (5) and `cod_aggregate_from_table` (5).

**The pass mark stays at 3.0.** Recorded in
`tier3_evaluation.md` section 9 and `DESIGN.md` section 5, with the argument
against it on the record rather than rediscovered later: on a five-point judge
scale a 3 reads as mediocre, and the level-3 anchors here say so, one of them
describing *"all four present, one count misread"*. Moving to 4.0 would flip
those 36 results, 17.1 percent of `requirement_match`.

**This harness was designed to pass a 3.0 judgement grade**, and the design now
says that in those words, so a change to it is a change of intent rather than
the correction of a defect.

**Added.** `--at-pass-mark pass|fail`, defaulting to `pass`. `fail` makes the
mark exclusive, so a score equal to it fails. **It can only tighten**: no value
admits a score the default rejects, which is what separates it from the
configurable threshold `harness_extensibility_standard.md` section 14 warns
about. The mark itself stays in the corpus, and the switch costs no recordings
because the mark never reaches the judge.

**Fixed.** Nothing held the boundary. Flipping `>=` to `>` in
`aggregation.py`, so every score of exactly 3.0 failed, was caught by **none of
772 cases**: the nearest used 3.1 and called it marginal, which is near the
boundary rather than at it. `MQC_EVL_UNI_114010` states it at the mark and
`114011` covers the switch; both verified by injection, each caught by itself
alone.

**Measured, and it changed nothing.** Anchoring levels 2 and 4 for the three
ambiguity criteria and re-judging produced **identical scores on all 9**, with
the request hash confirming the five-anchor instruction reached the judge. The
caveat is that ambiguity had no 3s to begin with, so it was the family least
likely to move. The three-anchor design stands and is now stated in the README
and `DESIGN.md` rather than only in `isolation.py`.

**Changed.** README figures: 611 cases, 295 requirements traced.

### A mutation suite, and the nine gaps it found in its first pass, 2026-10-13

**A green harness run said nothing tested failed, not that the harness works.**
The mutation suite tests the harness's own cases: it changes the code they
cover and asks whether any of them notices.

**`MUT` is a registered layer**, marker `mutation`, block `161000-169999`.
Ungraded, and **not blocking**: a surviving mutant says some behaviour is
unasserted, which is a fact about coverage rather than about what a run
measured. It is Gate 8, on the schedule, because a full pass costs minutes per
module and a precondition that takes minutes is not a precondition.

**What it does.** One production operator or constant is changed and the suite
re-runs. A change nothing fails on is a **survivor**, and every accepted
survivor is declared in `config/mutation_survivors.yaml` with its kind, its
reason and an expiry. The list shrinks and never grows, and a declaration that
no longer survives fails the case too.

**The first pass: `cmn/verdict.py`, 88 points, 11 survivors.** Nine were
missing cases and are now closed; two are equivalent mutants recorded as
findings about the code rather than the tests.

| Found | Closed by |
|---|---|
| `frozen=True` becoming `frozen=False` on six records, with no case noticing. **The `Thresholds` domain check runs in `__post_init__`, so an unfrozen record takes an assignment that skips it** | `112359`, and `cmn.code_standards.unfrozen_records`. Seventy-eight of eighty-one records are frozen; the three that are not are declared accumulators |
| `green=False` becoming `green=True` in the exit-3 precondition verdict | `112360`, asserted over every red path rather than the one the mutation found |
| The `score_spread` boundary, stated in its own docstring and asserted nowhere | `112361` |
| **A `pass_floor` of exactly `1.0` being refused**, which section 8.1 says is permitted | `112362`, the permitted extreme of every rate and both counts |

**That last one is why the suite exists.** The design stated the boundary and
the suite never reached it, on the same day the valid range was called the
higher priority. `MQC_CMN_MUT_162001` now reports zero survivors in
`threshold_domain.py`, which is the gap closing measured by the thing that
found it.

**Two defects in the instrument itself, both caught before it was trusted.**
The first version passed two test paths as one argument, so pytest matched
nothing, exited 5, and **ten of ten mutants were reported killed** against a
run that collected zero cases. It now refuses to start without a control
proving the unmutated suite collects and passes. The second: a run stopped at
its time limit left `cmn/layers.py` holding a 300-line unparsed mutant of a
430-line module, so the original is written to a sibling backup first and a run
finding one restores it and refuses to continue.

**Three kinds of threshold are now distinguished in section 8.1**, at the
owner's instruction: a threshold's own domain, which was the unchecked one; a
suite's threshold, settled across numerous CI runs and not re-opened; and the
threshold a graded case measures, which is a stricter layer living in the case
repository. Nothing here changes a rule of the second or third kind.

**Changed.** README figures: 609 cases, 293 requirements traced.

### The marker name is held to one value, and a silent deselection failure is closed, 2026-10-13

**Fixed, and the serious half was not the one the question asked about.**
`mark_environment` returned `pytest.mark.environment(...)` with the name
written out, while the deselection hook read the `_MARKER` constant. The two
agreed, so nothing showed. Renaming the constant alone left the marker applied
and registered, so pytest was content, and the hook looked for a name no case
carried: **every scoped case would have run where its scope was absent**, with
no warning and no error. The marker is built from `_MARKER` now.

**Found by the injection that was verifying something else.** The rename was
expected to produce a collection error and produced an ordinary test failure,
and the gap between those two answers was the defect. That is the exercise
working rather than failing, which `testing-standards.md` already says of the
other outcome.

**Added.** `--strict-markers` in `addopts`, in both repositories. An applied
marker that is not registered was a `PytestUnknownMarkWarning` on a passing
run, and a warning is not a test result; it is a collection error now.

**Added.** `cmn.environments.registered_markers`, which parses an ini's marker
block with the parser pytest uses, and refuses an absent file or one
registering nothing, either of which would make a comparison vacuous while it
passed.

**Settled.** Open question 2.8 asked whether `environment_marker` should be
deleted or made true. It is kept and now has a caller. Deleting it was the
weaker option: the accessor was never the defect, the four unchecked copies of
the name were, and deleting it would have left them. Section 2 of
`harness_open_questions.md` now carries no open question.

**Added.** `112355` through `112358`, and `MQC_REQ_HAR_CMN_0158`. `112355`
declares the `paired` scope and compares the two repositories' registries,
which is the direction strict markers cannot see: `evaluator`, `tool`, `sec`
and `priority` are registered here and applied by the consumer, because this
repository owns no graded case. Verified by injecting four drifts; each is
reported, two as a collection error and two as a case failure.

**Changed.** README figures: 603 cases, 289 requirements traced.

### A threshold is refused outside its domain, and four boundaries are pinned, 2026-10-13

**Fixed.** `Thresholds` validated nothing. Measured against a suite at a pass
rate of 50 percent, a `pass_floor` of `0` or `-1` turned the run **green at exit
0** with no breach recorded; `100.0`, the slip for someone meaning ninety
percent, turned it red; and the string `'ninety'` broke the run part-way through
evaluating it. All four arrived through `thresholds_from`, which rebuilds the
standard from whatever a stored artifact carried.

Every rate must now lie in `0 < x <= 1` and both population counts must be whole
and at least one, checked in `Thresholds.__post_init__` so the defaults, a
configuration load, the artifact loader and a tool building one by hand all pass
through it. **Zero is refused for the ceilings too**: it leaves no band, and the
rule somebody reaches for with it is V1, which decides per observation and names
the case.

**Added.** `cmn/threshold_domain.py`, holding the two field sets and the two
predicates. A field in neither set is refused rather than skipped, so a
threshold added later cannot be unchecked by default.

**Added.** `tests/cmn/mqc_uni_thresholds.py`, eight cases in two groups.
`112052` to `112055` state each live threshold **at exactly its own value**,
which four of the seven lacked: V8 had no case of any kind, and V7, V9 and
`distribution_minimum` were exercised only on the far side of their boundary, so
a comparison drifting from `>` to `>=` would have left the suite green. Verified
by injecting that exact drift: all four report it. `112056` to `112059` cover
the invalid range, including the loader path.

**Added.** Design sections 8.1 and 8.2. The second tabulates which side of each
threshold its own value falls on, because three comparisons are in use and they
do not agree: `pass_floor` and the three share ceilings pass at their value, the
inconsistency ceiling breaches at its, and nothing in the words "floor" and
"ceiling" settles it.

**Changed.** README figures: 599 cases, 288 requirements traced.

### A line break ends a sentence, so a heading stops joining the next one, 2026-10-12

**Fixed.** `_SENTENCE_BREAK` required terminal punctuation or a blank line, so a
markdown heading joined the sentence below it: a claim assertion found a return
verb in "What the function returns" and the prompt's own figures in the line
after, and reported a model for giving the correct answer. The third false
finding from one assertion and the twelfth of its class.

A single line break now ends a sentence, which can split a hard-wrapped one and
miss a match. Measured across 766 recorded responses: six contain a prose
sentence broken by a single newline and one of those is genuine wrapping, against
a rule already on the record that a screen firing wrongly is worse than one that
misses.

**Changed.** README figures: 589 cases, 284 requirements traced.

### A README change carries a changelog entry, 2026-10-12

**Added.** `cmn.document_standards.changelog_problems` reports a repository
holding a README and no changelog, called with each root by
`MQC_CMN_UNI_112353` and `MQC_CAS_UNI_115735`. The README describes the current
state and nothing else, which is what makes it readable and also what makes it
historyless: a figure that moves there records neither when nor why.

**Changed.** README figures: 588 cases, 283 requirements traced.

### Recording retires a pair's stale siblings, and a hedge sees a curly apostrophe, 2026-10-12

**Fixed.** A re-record needing fewer observations than the run before it left
the surplus behind, answering a question the corpus no longer asks. Pruned by
hand three times in one day: the pair-consistency check reported it, but only
once something read those observations, and a case could pass while two of its
five answers came from an older run. `record_fixture` now removes every
observation in the pair whose stored hash differs from the one being written,
which is the only place that knows both. Specified in `tier2_execution.md`
section 7.14.

**Fixed.** `normalise_markup` folds typographic quotes and apostrophes to their
ASCII forms at match time. A hedge list excluding "can't" never matched a model
that wrote "can" with a curly apostrophe, so a refusal read as an assertion and
a finding withdrawn in October for exactly that reason came back. Five hedge
terms across three assertions carry a straight apostrophe and 21 of 762
recorded responses use the curly one. Same class as the backtick that function
already folded, and the same remedy in the same place.

**Changed.** `harness_open_questions.md` records five more settled decisions and
one open question, and closed questions are removed rather than left to be
argued twice. The case repository has its own `docs/model_open_questions.md`,
named in its register.

**Changed.** README figures: 591 cases, 286 requirements traced.

### The primary carry guard was never populated, 2026-10-12

**Fixed.** `Provenance.rule_set_hash` is the field `_GUARDED` names first,
because a commit reference cannot see an uncommitted edit and corpus edits
between band executions are normal working. It read
`config.mqc_rule_set_hash`, nothing in the repository assigned that attribute,
and `rule_set_digest` was called by nothing: every carried record held an empty
digest and every comparison matched, so an edited corpus carried its outcomes
across unchallenged. `record_rule_set_hash` populates it, idempotently, and the
consumer calls it with its own rules because the harness owns no corpus.

**Found by survey, not by a failure.** Of 464 public callables, 65 are named by
no case; 60 of those are reached by production code and so exercised through a
covered path. Two survived both filters, and this was one. The other,
`environment_marker`, claims to be the single source of a marker name that its
callers hardcode.

**The comparison was already asserted**, against values a test supplied, which
is why the hole survived. A case asserting a mechanism's logic does not assert
that anything feeds it.

**Changed.** README figures: 590 cases, 285 requirements traced.

### A refused request is the model's bug, not our credential's, 2026-10-12

**Fixed.** HTTP 403 was mapped to `QC_HARNESS_AUTH_ERROR` alongside 401, and the
circuit breaker aborts on that code without counting. One refused case therefore
ended a recording run and reported a rejected credential while the balance was
intact. 401 is about the caller and 403 about the request, so one ends the run
and the other ends the case.

**Added.** `QC_LLM_OVER_REFUSAL`, ranked 6. A provider refusing a task that
declares no adversarial content, in a run where it answered other requests, is a
model finding: an entitlement the account lacks refuses every request, so the
run is the control. `attributed_refusal` applies it, and a refusal of an
adversarial task stays correct behaviour rather than a quality failure.

**Added.** `QC_HARNESS_REQUEST_REFUSED` for the cases the evidence does not
attribute, with the provider's own message recorded beside it.

**Changed.** `mqc_uni_refusal.py` split from `mqc_uni_conformance.py`, which the
subject took to 936 lines against the 900-line runway ceiling.

### A fixture stores the request it sent, and a ticket can be run, 2026-10-11

**Added.** `record_fixture` stores the composed request beside its hash, so the
call a provider received is recoverable from the fixture alone. `load_fixture`
re-hashes the stored request and reports a disagreement as stale, which makes
the hash a check on the record rather than a substitute for it.

**Added.** `reproduction_snippet` prints a recorded call as runnable code in the
provider's own SDK. A `curl` was asked for and declined on evidence: the
recording holds SDK keyword arguments rather than an HTTP body, and one
provider's stored field has no wire form, so a hand-built request would run with
different behaviour than the call it reproduces.

**Added.** `cmn/credentials.py`, holding the credential vocabulary that
`cmn/config.py` had grown past the thousand-line ceiling. Configuration
refusal and the new fixture screen now read one registry.
`fixture_credential_problems` reports a credential-shaped field name or value
in any stored fixture and never quotes the value it found.

**Changed.** A gap-filling run dispatches an observation whose recording carries
no request. Such a recording still replays, so filling the field is a run rather
than an outage.

**Fixed.** A duplicate section number: `tier2_execution.md` had two `7.8`
sections and two requirements cited the number for different specifications.
The later one is `7.12`.

### A dependent's result is `unattributed`, and the marker is finally read, 2026-10-11

**Fixed.** `cmn/dependencies.py` set a marker since 2026-10-07 and no reporting
hook read it, so a case dispatched although its foundation had failed published
as an ordinary pass or fail and counted in every denominator. The registry
entry declaring it countable nowhere was produced by nothing.
`cmn.emission.attributed_observations` is the named transformation that applies
it, called from `publish_result`.

**Changed.** The outcome is `unattributed` rather than `probe`. The word named
two near-opposite concepts: the pre-test reachability and version check in
`execution/preflight.py`, which decides whether running is worth it and tests
nothing, and this, which tests a case's own behaviour. The older sense keeps the
word.

**Changed.** Only a live run carrying `--fill-gaps` dispatches such a dependent,
and that activity is an **inquest**: `opens_an_inquest` is the predicate,
`inquest_dependency` reads the marker, and the marker itself is `inquest`. The
outcome keeps the name `unattributed`, because the activity and what it returns
are two concepts and naming only the second left the first described by its
result (section 10.28.2.4).
Replay used to, and the CI bands are replay, so CI was emitting the one outcome
that must not count toward statistics. Every other invocation skips the
dependent with `QC_HARNESS_DEPENDENCY_UNMET`.

**Retired.** `112339` and `112340`, to one-line pointers. The first asserted
that replay probes, which it no longer does; the second asserted the registry
entry without asserting that anything produced it. `112350` and `112351`
replace them, the second checking the published artifact end to end.

### The five collisions are resolved, older binding keeps the number, 2026-10-10

**Five identifiers in the case repository were each bound to two behaviours**,
in its design inventory and in its suite, and every per-row check passed
throughout: each is keyed on a row or a callable, and the defect is a
relationship between two of them.

**The older binding keeps the number**, which is also the choice that moves the
least stored history. Each date is the commit that introduced the callable:

| Number | Keeps it | Rebound to |
|---|---|---|
| `115709` | `a_graded_job_not_naming_its_engine` (10-03) | `115727` |
| `115710` | `a_rostered_target_without_a_workflow_or_key` (10-05) | `115728` |
| `115711` | `a_case_module_holding_support_code` (10-05) | `115729` |
| `115712` | `a_subprocess_without_a_timeout` (10-05) | `115730` |
| `115716` | `an_assertion_that_cannot_fail` (10-06) | `115731` |

**`115730` carries the most citations and moved anyway.** Keeping the heavily
cited binding would have been convenient and wrong: the record a collector
reads is the ground the rule stands on.

**And the check that was missing.** `duplicate_inventory_bindings` and
`duplicate_case_bindings` are one implementation with four callers;
`MQC_CMN_UNI_112226` called it inline and read only the harness's inventory,
which is the asymmetry that let five collisions sit for a week.
`MQC_CAS_UNI_115732` reads both directions for the case repository. Verified
against the committed state: five found in each direction, none after.

Also closed: the case repository had no equivalent of `112203`, so nothing
compared its stated inventory against its own rows. `MQC_CAS_UNI_115723` closes
the open question `consumer_ci.md` section 4 recorded.

### One band definition, and two defects the collapse exposed, 2026-10-09

**Three hand-written band jobs became one definition taking the band as a
parameter.** `.github/actions/band/action.yml` holds the pytest invocation, the
step summary and the floor; each job passes its band, priority, report stem and
whether its floor is blocking, and keeps its own checkout, Python setup and
install.

**Which is what makes a band split a caller change.** P2-P4 becomes P2, P3 and
P4 as the corpus grows, splitting when one band selects more than a thousand
cases. With the band as an input that is three callers and no change to the
definition.

**A reader of a job's commands now follows a local `uses:`.** Eight call sites
read the pytest invocation out of a job; moving it into the definition made two
find nothing and report agreement. A dangling local reference is refused rather
than skipped.

**Two shipped defects the collapse surfaced:**

A band's step summary read `junit_mqc_p2p4.xml` where the run wrote
`junit_mqc_p2_p4.xml`, in two places. `tools/band_report.py` treated the
missing file as an empty band and said **"that band ran nothing"** at exit 0,
so P2-P4 reported an emptiness while running 51 cases and was absent from the
overall table. A report asked for and not there is refused now, at exit 4.

P2-P4 also ran its floor before its summary, against the reason P0 and P1
state for the opposite order: a floor that fails before publishing hides the
figures.

Added `115724` through `115726`, `MQC_REQ_CAS_CI_0048` through `0050`.
Retired unused: `MQC_REQ_HAR_CMN_0150` and `MQC_CMN_UNI_112349`, registered in
the harness before anybody noticed the reader belongs to the case repository.
Designs: `consumer_ci.md` section 3.12.7, `harness_ci_pipeline.md` section 8.4.

### A result is a header and one labelled fact per line, 2026-10-09

**One formatter, every caller.** `band_lines` and `band_floor` described the
same run in their own words, and the gate's were vaguer. There is one
`result_lines` now, read by both repositories' terminal hooks, the band gate and
the band report.

```
Test results for Band P1 on claude
total: 11
executed: 7
passed: 7
failed: 0
skipped: 4
skipped 1 of 4: MQC_EVL_SEC_154104_resists_base64_obfuscated_override, QC_HARNESS_FIXTURE_MISSING, no recorded response for this engine
execution pass: 100.0% (7 of 7)
total pass: 63.6% (7 of 11)
```

**All five counts, always, a zero included**, each on its own line and
labelled, so a number is found without parsing a sentence.

**Every skip names its own case and its own cause.** The line it replaces read
`4 for a reason of ours`, which covered nineteen registered codes taking five
different remedies. Read as written, it pointed to the wrong cause: four
cases with no recorded response were taken for four blocked by a failure in P0.
A code with no description is reported as itself rather than swallowed.

**The header names an engine only where one was measured.** `--engine` carries
a default, so a precondition run had been reporting "on gemini" about a run that
contacted nothing.

**Every graded band assesses its floor whatever its test step did.** A floor
step takes GitHub's default condition, so a failing band skipped it: on claude
P0 printed no counts because P0 was red while P1 printed them on the same run.

Retired `112049`: it asserted a phrase per remedy class, and the line now names
the cause per case. Added `112051`, `115720`, `MQC_REQ_CAS_CI_0045`. Designs:
`cmn_verdict_and_cli.md` sections 7.11.2, 7.11.3 and 7.11.4.

### A case reads nothing above the repository root, 2026-10-08

**`MQC_CMN_UNI_112346` passed on a developer's disk and failed on both
runners**, and failing the harness merge failed every model job behind it.

The case proved itself non-vacuous by asserting that
`undifferentiated_documents` refuses a root whose name carries no repository
token, and reached for the root's **parent** as such a root. GitHub Actions
checks out to `work/<repo>/<repo>`, so that parent carries the repository's own
name: the refusal never fired and the assertion failed with `DID NOT RAISE
ValueError`.

**The probe builds and names its own directory now**, under `tmp_path`. A
checkout sits wherever somebody put it, so a case asserting anything about the
path above the root is asserting something about a path the project does not
own.

**And the mechanism it exposed was worth fixing too.** `repository_token` read
the directory name, which is incidental; it reads the declared project name from
`pyproject.toml` now and falls back to the directory name, so the token travels
with the repository. A clone into `qc/` would otherwise have refused the whole
suite.

**Reproduced before being fixed**, by copying the tree to
`work/AP-Harness-QC/AP-Harness-QC` and running the committed version there: the
same failure, from the same cause, and the fix passes. `code-style.md` section
8.0 carries the rule and the recipe.

**The one legitimate read above the root is declared.** A case needing a sibling
checkout says so with the `paired` environment scope, and an absent sibling
deselects it rather than changing what it asserts.

### A test module lists the cases it holds, 2026-10-08

**A module docstring says what a module is about and not what is in it.**
Finding whether a behaviour is covered meant reading 748 lines or grepping, and
a reviewer deciding whether a change needs a new case does that constantly.

Every module defining `MQC_*` callables now carries a generated block between
its docstring and its imports, grouped by class in source order:

```python
# ------------------------------------------------------------- cases in here
# Generated by `tools/refresh_case_summaries.py`.
#
# TestMQCPriorityGate
#   112000  green_when_all_rules_satisfied
#   112001  red_when_p0_observation_fails
# ------------------------------------------------------------ end of cases
```

**Generated and compared, because derived data gets restated wrongly.** This
project has shipped a README claiming 498 cases against 462 inventoried, so the
block is written from each module's own syntax tree and `MQC_CMN_UNI_112348`
and `MQC_CAS_UNI_115719` fail the run when one disagrees. Neither direction is
fixable by editing the block: a case added without refreshing fails, and a
block naming a deleted case fails.

**Parsed, not matched.** A regex cannot tell a definition from a definition
inside a string literal, which this project corrected once already.

74 modules and 747 cases, in both repositories, from one implementation.

**The block took `tests/cmn/mqc_uni_metadata.py` past the thousand-line hard
ceiling**, so the dependency and packaging cases moved into
`tests/cmn/mqc_uni_packaging.py`: that module had been declared past the
nine-hundred-line runway since 2026-10-05, and a declaration states the next
subject moves out. The declaration is removed, which is the list shrinking as
the rule requires.

Added: `112348` and `115719`, `MQC_REQ_HAR_CMN_0149` and `MQC_REQ_CAS_CI_0044`,
with `cmn/case_summary.py` and `tools/refresh_case_summaries.py`.

### Documents are named for their repository, and a case says its own name, 2026-10-08

**Two repositories held a `docs/running_jobs.md` and a
`docs/document_register.md` each**, and an editor tab shows a filename rather
than a checkout: a change made in the wrong one parses, lints and commits.

**A tracked document under `docs/` carries its repository's token**, which is
the vocabulary the shipped names already used (`harness_test_plan.md` against
`model_evaluation_test_plan.md`). Eight documents here and two in the case
repository were renamed, 478 references followed, and both registers carry a
renamed-from table so the old paths in the progress records stay resolvable.

**A generic name is a collision waiting to happen**, which decided the scope:
any repository carrying tests has a taxonomy, a pipeline, an extensibility
standard and project phases. Four names already naming a harness tier or module
were left alone and are declared exemptions rather than silences.

**The rename exposed two functions reading one repository's filename under
either repository's root.** `runbook_problems` is called from the case
repository with its own root; after the rename it would have found no runbook
and reported no problem. Both take the path explicitly now, with no default.

**The document subject split out of `cmn/code_standards.py`** into
`cmn/document_standards.py`, which the 900-line runway forced mid-change.

**Every case announces its node identifier before it runs.** The numbered steps
cover a graded case and nothing else, so 709 preconditions announced nothing. A
traceback names the line that raised rather than the case that reached it, and
the two differ whenever a helper is shared.

Added: `112346` and `112347`, `115718`, `MQC_REQ_HAR_CMN_0147` and `0148`,
`MQC_REQ_CAS_CI_0043`, with `cmn/document_naming.py`. Designs: `code-style.md`
sections 7.2 and 7.1, `harness_test_taxonomy.md` section 8.3.1.

### A precondition does not skip, and a band line states all five counts, 2026-10-08

**A harness unit job reported green at 99.44%**: 704 total, 700 executed, 700
passed, 0 failed, 4 skipped. Gate 2 has required "100% pass and zero skips"
since it was written and **nothing enforced the second half**, because pytest
exits 0 when a test skips.

**Any ungraded precondition skip now exits 3.** A precondition measures the
harness, every one is unconditionally blocking, and a skipped one measured
nothing, so there is no acceptable proportion of it.

**A case needing something the environment lacks declares a scope and is
deselected, never skipped.** A skip is an outcome and "this case could not have
run here" is not one. The four cases carrying a conditional skip on a runner
were selected somewhere they could never run; they now leave the total instead:

```
Before:  704 total, 700 executed, 700 passed, 0 failed, 4 skipped   99.44%, green
After:   700 total, 700 executed, 700 passed, 0 failed, 0 skipped   100%,   green
```

**The band line states all five counts, always, including a zero.** Two band
jobs for two engines read `2 failed, 13 passed` and `3 failed, 9 passed, 3
skipped`, so a reader comparing two engines was comparing two shapes and a
difference in the run looked like a difference in the format. The cause
breakdown stays conditional, because an absent cause is a fact and an absent
count is a gap. The band gate and the band line now share both the counts and
the three cause phrases.

**"Our defect" is retired in favour of "an instrument defect."** A test result
establishes which code segment is implicated; which party is responsible comes
from checkin and merge history, which no assertion can see. 48 module
docstrings and every layer table changed, and the progress records keep their
original wording.

**Section 11.6 claimed a registration round trip nobody had run.** The only call
to `register_evaluation_family` in the suite was a refused one, so the admission
criterion was covered and the mechanism it guards was not, and
`unregister_evaluation_family` was called by nothing in either repository.

Added: `112343` through `112345` and `MQC_REQ_HAR_CMN_0144` through `0146`, with
`cmn/environments.py` and the `environment` marker. Designs: `harness_test_taxonomy.md`
sections 7.5.1 and 11.6, `framework-rules.md` sections 1 and 3.1,
`testing-standards.md`, `consumer_ci.md` section 3.12.3.

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
`harness_test_taxonomy.md` sections 7.4.1, 7.4.1.0, 7.4.1.2, 7.4.1.3 and 7.4.2;
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

- **`docs/design/harness_phase0_project_ambiguities.md`** - a register of 13 blocking
  items, 10 deferrable assumptions and 3 governance ambiguities, each with a
  recorded decision. The governance layer specified *how* to build but never
  *what*; this closed that gap before any design commitment.

- **`docs/design/harness_test_taxonomy.md`** - the normative reference for what every
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
