<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->

# Problems Found

**What this project has found, grouped by the shape of the defect rather than by
the date.** Assembled 2026-10-04 for an external account of the work.

`CLAUDE_LOG.md` is the primary record and carries each item in full with its
evidence; this is the index over it. Where a figure appears here it was measured
rather than estimated, and the log entry says how.

**Two things are deliberately separate.** Findings about the models under test
are the project's output. Everything else is a defect in the instrument, the
documentation, or the tooling, and those were found *by* building the
instrument. A reader interested in whether the method works should care more
about the second list than the first.

---

## 1. Findings about the models under test

24 open, every one a `QC_LLM_*` or `QC_SEC_*` event. Recorded per engine in
`config/findings/<engine>.yaml` in the case repository, each with the model it
was observed against, what was expected, what happened, and the command that
reproduces it.

| Engine | Model | Findings |
|---|---|---|
| gemini | `gemini-3.8-flash` | 2 |
| openai | `gpt-4.1-2025-04-14` | 8 |
| claude | `claude-opus-5-5` | 10 |
| grok | `grok-4.7` | 4 |

**Four engines, one corpus, one judge.** The spread is the thing a single-engine
project cannot produce: the same 69 cases against four models give 2, 4, 8 and
10 findings, and no engine passes everything.

**The gates are red because of these**, and that is the project working. A P0 or
P1 cannot be exempted, so a finding at those levels holds its engine's gate red
until the provider fixes it or the finding is withdrawn.

**Nothing has been filed yet**, by decision: the implementation is finished
first, and the register exists so that a fix landing in the interval is
detectable rather than arriving as a gate quietly turning green.

### 1.1 What the findings are about

| Class | Count | Example |
|---|---|---|
| `QC_LLM_INCONSISTENT` | 13 | A model answering the same question three ways, which makes every single-sample result from it a draw from a distribution nobody characterised |
| `QC_LLM_SOURCE_ALTERATION` | 4 | A stated figure changed, checkable by exact match against the source |
| `QC_LLM_INJECTION_SUSCEPTIBLE` | 3 | A planted canary emitted, meaning the model followed an instruction in its input rather than its instructions |
| `QC_LLM_HALLUCINATION`, `QC_LLM_DEFECT_MISSED` | 3 | A syntax error located in the wrong place, or a defect in an excerpt not reported |
| `QC_LLM_AMBIGUITY_UNHANDLED` | 1 | An incalculable figure assumed rather than asked about |

**One case fails on every engine**, `134205`, which asks whether a model
overstates a sourced figure. Four models, four failures, same case: that is a
finding about the task being hard rather than about any one provider, and it is
only visible with more than one engine recorded.

**The inconsistency findings are the ones that needed a method.** A single
sample cannot produce them: the project takes three observations per case and
escalates to five on a single disagreement, and a case that passes twice and
fails once is a finding rather than a pass. That decision is what makes
**fourteen of the twenty-four** visible at all.

**This figure was itself stale**, reading eleven of twenty from when three
engines were recorded; grok's four findings arrived on 2026-10-04 and the
sentence did not move. It is now recomputed from the registers by the case
repository's README check.

---

## 2. The dominant defect in our own work: right, and unreachable

**The thing is built, it is correct, and nothing establishes it is reached.**
Fourteen instances, and it is the single most common defect this project found
in itself.

**The count in this paragraph was itself wrong twice**, reading eleven while the
table carried thirteen rows and the closing summary said twelve. A hand-kept
figure beside the list it counts is the same defect one level down, which is
worth stating in a document about this shape rather than quietly correcting.

| What was built | What was missing |
|---|---|
| `--max-spend` | No workflow passed it, so every live leg ran with no ceiling. Harmless until a credential reached Actions, which made it live |
| `--priority` | The flag selected nothing for months |
| `--out-dir` | Two mandated artifacts and four invocations emitting one |
| `--judge-engine` | Named a judge; the binding passed an empty string, so `--judge-engine openai` graded with gemini **and recorded openai** |
| `--extra-columns` | Read and never applied |
| `--tests` | Translated to a `-k` expression by a workflow, which strips the dependency closure |
| `--case` | Reached metadata and made a run unverdictable while selecting nothing. **Half-implemented is worse than inert**: the artifact said a selection had happened |
| The emission hook | `emit_result` returned the whole metadata contract and had no caller, so a published result carried empty parameters and a severity label. **The three-engine comparison was unattributable from the artifact** |
| T5, the matrix family check | Takes a per-case mapping as an argument; nothing could build one, and it is written so an absent mapping means nothing to check rather than nothing to check **with**. It abstained silently for its whole life |
| The consumer regression gate | Had never run |
| `--family` | Resolved at requirement-row grain, selecting 15 cases where 6 graded the family |
| `--engine` | Enumerated three engines in the option registry, so rostering a fourth made the flag refuse one the roster named. The argument against enumerating was written one flag away and nobody applied it |
| The per-target workflow check | **The list of targets was a tuple, and its comment claimed it was the roster.** So "every rostered engine has a gate and a weekly workflow" could only fail for an engine somebody had already added by hand. grok was rostered, priced and recorded, and the consumer stayed green gating three of four targets |
| The roster gate | **Nothing checked the roster.** An engine with an adapter and no roster entry dispatched against the adapter's own default, which for grok was `grok-4`: a model the provider does not serve, so a 404 on every case reading as a broken harness |

### 2.1 Why it is the dominant shape

**Every one of these passes every test written about it.** The builder is
correct; the caller is absent. A test that exercises the builder cannot see that
nothing calls it, and a test that exercises the whole path is the expensive kind
nobody writes first.

**The remedy that worked was asking a different question.** Not "does this
work", but "what would be different if this were deleted". `112253` runs a real
pytest invocation and reads the artifact it produced, which is the only form of
evidence that would have caught the emission gap: every case about the mapping
passed while nothing published it.

---

## 3. Checks whose subject supplied their evidence

**A check that constructs its own input can only confirm the input is
self-consistent.**

| Check | What it fed itself |
|---|---|
| `112312` | Claimed to run the real matrix through five checks, deriving the requirements and the test names **from that same matrix**. T1 cannot fail against requirements taken from the rows it checks |
| The required-field list | Existed in three hand-maintained copies and nothing compared any pair, so adding a field touched the code and neither list |
| The matrix `families` column | Checked for being *registered* and for being *internally consistent*. **Consistency was checked and correctness had no source**, so a label applied wrongly to every affected row passed both checks |
| T4 against T7 | T4 asks a test what it claims and passes a test that claims nothing. T7 asks the suite what it contains |

**19 of 93 matrix rows were wrong** and two checks guarded that column. The one
designed to catch it had never been given the data it needed.

---

## 4. Records that were wrong about their own reason

**A rule with a wrong reason is worse than a rule with none, because the reason
is what the next person acts on.**

| Record | Claimed | Actually |
|---|---|---|
| `--tag` was unimplementable | No tag vocabulary existed | **79 tags existed and every task carried one.** What was missing was anything that could refuse a tag not among them |
| Heredocs mangle escapes | The shell, the heredoc, Python and the target format each interpret them | **The shell and the heredoc are innocent.** `$HOME` and backticks survive verbatim; backslashes are halved before the shell is reached |
| `--family` selects every case addressing a family | True | And also every other case sharing a requirement row |
| The account-action list | claude needed a key and a price; grok had no credential | All three had moved, some by days |
| A design claiming enforcement | Step 10 of the family procedure named a verification | That the named case never performed |

**Each of these pointed at a remedy that would not have worked.** A reader told
the shell is at fault reaches for more quoting; a reader told the tag vocabulary
is missing writes one, and still cannot refuse a typo.

---

## 5. Defects in the tooling the work was done with

Found by the project rather than by looking for them.

| Tool | Defect | How it surfaced |
|---|---|---|
| The editing tool's shell transport | **One level of backslash escaping stripped from a quoted heredoc body**, which POSIX requires to pass through byte for byte. Isolated with `od -c`: `$` and backticks survive, backslashes halve | Four failures in one session, one of them silent: a regex lost an escape, passed, and reported nothing |
| pytest | **An absolute `--alluredir` outside the repository moves the rootdir**, so `pytest.ini` is not found, no conftest loads, and the run collects nothing and exits 5. The first run into a fresh path works, because the directory only becomes a rootdir candidate once it exists | A findings tool wrote an empty register for all three engines and reported success |
| allure-pytest | Does not create an intermediate directory for `--alluredir` | As above, one layer down |
| Python `frozenset` | Iteration order varies per process, so a generated file built from one **differs from itself between runs** | A generated index could never be reported current |

**The first is reported to the vendor** with the probe. The others are
configuration hazards rather than bugs, and each is now recorded where somebody
would meet it.

---


## 5A. Local checks that asked an easier question than CI asks

**Both of these turned a green commit red on push, and neither defect was in the
code being tested.**

| What was verified locally | What CI verified | The gap |
|---|---|---|
| `pylint` over four of six path sets, depending which copy of the command you followed | The broadest set | A 154-character line in `conftest.py`, which three of the four copies do not lint |
| `yaml.safe_load` on an edited workflow | GitHub's workflow schema | A duplicate `inputs:` key, which YAML resolves last-wins and a schema rejects |
| A check run against a working tree holding untracked files | A fresh checkout | A register check requiring every named document to **exist**, where one was deliberately untracked: present where written, absent in every clone |
| `pylint ... | tail -3`, reading `rated at 10.00/10` | The **exit code** | A refactor message costs no score: pylint reported `R0914`, rated the code 10.00/10 and exited **8**, its bit for "refactor message issued". A pipe discards the left-hand status, so `echo $?` reported `tail` succeeding |

**The third is the second instance of its exact shape**, the first being
recorded on 2026-10-02. A check that reads something only one machine has can
only pass there, and the lesson had already been written down.

**The fourth was authored by the verification rather than found by it**, which
is worth stating plainly in a document about this class. Every lint check in
that session read the rating line and reported an exit code it had not looked
at, and the gate reads the exit code. **A score and a status are two different
questions**, and `fail-under=10.0` is the weaker of them: a message that costs
no score still fails the build, which is the stricter behaviour and the correct
one.

**The pylint command stood in four places with four path lists.** One omitted
`cmn/`, two omitted `conftest.py`, the gate omitted `tools/`, and only the
branch regression linted everything. A file in an omitted directory passes one
gate and fails another.

**A parse is not a schema check.** The duplicate key was accepted by
`yaml.safe_load`, which silently discarded the earlier block along with the
input it declared, and rejected by GitHub with a failed run carrying no jobs and
a filename for a name.

**These are verification gaps rather than implementation gaps**, and that makes
them the same shape as section 2: something was being checked, and not the thing
that mattered.

## 6. Configuration that the design depended on and nobody had made

| | |
|---|---|
| What the design said | Secrets are held in a GitHub Environment named `live`, which makes the credential boundary structural rather than conventional |
| What existed | **No environment and no secret in either repository**, while six workflows declared `environment: live` |
| Why nothing caught it | It is account state, not code. No test can see it, and the gates reference no provider secret so nothing failed |
| What a pinned model pointed at | `grok-4`, which the provider does not serve: a models call with the funded key returns 14 models and that is not among them |

**Twice now a pinned model was settled by asking the provider rather than by
reading a document**, the first being `gemini-3.8-flash`, whose replacement was
named by the provider's own 404.

---

## 7. What the method cost, and what it caught

| | |
|---|---|
| Harness preconditions | 688, all passing |
| Case-repository preconditions | 84, all passing |
| Graded cases | 69, across 7 corpora and 7 evaluation families |
| Model findings | 24, across four engines |
| Defects found in our own instrument | The lists above |
| Measured cost of a full recording run | **Six cents** for one family, cents for a full engine |

**The ratio is the point.** A project that found 24 findings about four
commercial models also found fourteen instances of its own machinery being
unreachable, two checks that fed themselves, 19 mislabelled matrix rows, a
credential boundary that existed only on paper and a pinned model the provider
does not serve. **The second list is longer than the first**, and every item on
it would have degraded a finding's credibility had it reached a vendor.
