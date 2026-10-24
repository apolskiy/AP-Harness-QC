<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# Project Code Style

Conventions every Python file in this repository must follow.

## 1. Naming & Variable Standards
* **No Single-Character Variables**: Single-letter variable names (`i`, `e`, `x`, `k`, `v`, `f`) are **strictly prohibited** in all scopes (including loops, list comprehensions, lambda functions, and exception handlers).
* **Minimum Length & Clarity**: All variable names MUST be at least **3 characters long** and clearly articulate their purpose (e.g., `index` instead of `i`, `error` or `exception` instead of `e`, `item_value` instead of `x`).
* **One exception, and it is narrow**: `id` is permitted as an **attribute** name where the record mirrors a third-party wire contract, because a double that renames a provider's field stops proving that our adapter reads the real one. It stays prohibited for variables, arguments and inline bindings, where the name is ours to choose and would shadow the builtin. `attr-rgx` and `class-attribute-rgx` in `.pylintrc` admit it; `variable-rgx`, `argument-rgx` and `inlinevar-rgx` do not, so the limit is mechanical rather than a matter of review.
* **Module-Level Constants**: Private module constants use `_UPPER_SNAKE_CASE` with a leading underscore (`_CONFIG_PATH`, `_DEFAULT_TIMEOUT_SEC`).
* **Encapsulated State**: Instance attributes are private (`self._client`, `self._retry_limit`). Expose attributes through `@property` decorators.
* **Private Helpers**: Private functions take a leading underscore (`_parse_json_payload`).
* **Class & Module Naming**: Classes use `PascalCase`; modules use `snake_case`.

## 1.1 Every Python file opens with an SPDX authorship header

Added 2026-09-23 with the repository split, which made the licence a per-file question rather than a repository-wide one.

Two comment lines, above the module docstring:

```
# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
```

The case repository uses `MIT` in the second line. Nothing else changes.

### Why SPDX rather than the Apache boilerplate

The Apache appendix recommends a thirteen-line notice per file. SPDX carries the same two facts in two lines and is **machine-readable**, which is the part that matters: licence scanners, SBOM generators and `reuse lint` parse these tags, and a human-prose notice is checked by nobody.

| | Apache appendix boilerplate | SPDX short form |
|---|---|---|
| Lines per file | 13 | 2 |
| Machine-readable | No | Yes, a registered identifier |
| States copyright holder | Yes | Yes |
| States licence | Yes, by quoting it | Yes, by identifier |

Neither is required by the licence. Apache 2.0 section 4 requires the `LICENSE` to travel with a distribution and requires modified files to carry change notices; it does not require a per-file header at all. This is chosen because **a file separated from its repository still says what it is**, which is the case the split just made real: code from one repository now installs into the other.

### The comment position is load-bearing

The header goes **above** the module docstring, not inside it. A docstring must remain the first statement in the file or `__doc__` is empty, and this project reads module docstrings as specification prose.

`MQC_CMN_UNI_112502` enforces presence, position and the correct identifier. A header nothing checks drifts the first time a file is added in a hurry, which is the pattern this project has corrected often enough to stop writing new instances of.


### 1.2 Documents and data carry the header too

Extended 2026-09-24. Section 1.1 covered Python files; markdown and YAML now
carry the same two facts in the comment syntax each format already uses.

```
<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
```

**Invisible where it would be noise.** An HTML comment renders as nothing, so a
design document reads exactly as it did. YAML takes the same `#` prefix the
corpus files already use throughout.

**Neither reason for the Python rule is weaker here, and one is stronger.**

| Reason from 1.1 | Applied to documents and data |
|---|---|
| Licence scanners parse these tags | REUSE requires **every** file to carry them, so 54 bare files meant the claim held for none of them |
| A file separated from its repository still says what it is | **The corpus is the material most likely to travel.** The case repository is MIT precisely because, in its own words, the cases are material people copy and adapt |

The two repositories carry different licences and their design documents
cross-reference constantly, so a reader holding `tier1_ingestion.md` alone
cannot otherwise tell whether it is Apache or MIT.

**`LICENSE` and `NOTICE` are excluded.** They are the licence text; a file
stating its own terms does not need a tag pointing at itself.

**The module docstring check does not apply.** That rule exists because a
docstring must remain the first statement or ``__doc__`` is empty. Markdown and
YAML have no such constraint, so the header sits first and the content follows.

#### 1.2.1 The header goes on at creation, never as a later pass

**Any new tracked file carries its header in the same edit that creates it.**
Python, markdown and YAML alike, and a generator emitting a file emits the
header with it.

Retrofitting is what produced this section: 54 files accumulated without one
because each was written to solve something else and the header was somebody's
later problem. A rule applied only when remembered is a convention, and this
project has corrected that pattern often enough to stop writing new instances
of it.

`MQC_CMN_UNI_112502` and `112503` enforce the state rather than the habit, which
is all that can be enforced: nothing records when a line was written, and what
can be checked is the file that results from skipping the step.

## 2. Type Annotations
* **Annotate Everything**: Every parameter and return type carries an explicit type hint, including `-> None` on procedures and `**kwargs: Any`. **This applies to test code identically.** A test callable is a function like any other, and its fixtures are its parameters.
* **Built-In Generics**: Use `list[dict]`, `dict[str, Any]`, `frozenset[int]`.
* **Explicit Optionals**: Optional parameters are explicitly annotated as `Optional[T]`.
* **Declaration Annotations**: Local variables initialized before assignment carry explicit type declarations (`results: list[dict] = []`).

### 2.1 Lazy annotations are the default on 3.14, and `from __future__ import annotations` is prohibited

Established 2026-09-23 by probing the interpreter rather than from recollection, because this is an area where a confident wrong answer is easy.

**Python 3.14 implements PEP 649.** Annotations are already evaluated lazily: a function can be defined with an annotation naming a type that does not exist yet, and nothing is evaluated until something asks. The project targets 3.14 (B3), so **the laziness is already there and costs nothing to rely on.**

```
def probe(value: Undefined_Type_Name) -> Also_Undefined: ...   # defines fine on 3.14
```

**`from __future__ import annotations` is therefore prohibited, and not merely unnecessary.** It selects PEP 563 instead, which stringizes every annotation. That is a different mechanism with a real cost:

| | PEP 649, the 3.14 default | PEP 563, the `__future__` import |
|---|---|---|
| Evaluation | Deferred, computed on access | Never; annotations become strings |
| `annotationlib.Format.VALUE` | Returns the real objects | Unavailable, strings only |
| `dataclasses`, `typing.get_type_hints` | Work directly | Need a resolution step with the right namespace |

The project is built on frozen dataclasses whose fields are read at class creation and whose values are cast at boundaries. Turning every annotation into a string to obtain laziness that is already present would trade a working mechanism for a weaker one.

**Forward references still take quotes** where a name genuinely is not yet defined, such as a method returning its own class. That is a local answer to a local problem and does not need a module-wide switch.

### 2.2 The rule is enforced, not merely stated

`MQC_CMN_UNI_112500` parses every Python file in the repository and fails when a parameter or return annotation is missing, and `MQC_CMN_UNI_112501` fails on a `__future__` annotations import.

**Pylint does not check this**, which is why the rule stood in this document while 597 test callables violated it. A rule nothing checks is a convention, and this project has corrected that pattern often enough to stop writing new instances of it.

## 3. Docstring Formatting
Google style docstrings are mandatory across all modules, classes, and functions:
* **Types In Parentheses**: Each `Args:` entry specifies its type in parentheses (`raw_payload (dict): Raw JSON response...`).
* **Returns Mandatory**: `Returns:` is never omitted, documented as `Returns: None` if the procedure returns nothing.
* **Sphinx Cross-References**: Use `:class:`, `:meth:`, `:func:`, `:exc:`, and `:mod:` roles in prose. Double backticks for literals.

### 3.1 A docstring states behaviour; the design documents state why

Added 2026-10-01 at the project owner's instruction, after a run of docstrings
opened with the history of the defect they were written for.

**The first line says what the code does.** Not what went wrong once, not which
boundary the file sits behind, not what was traded away. A reader opening a
callable wants its behaviour, and a reader wanting the reasoning is better served
by the document that owns it.

| | Belongs in |
|---|---|
| What it does, what it asserts, what it returns, the boundary values | The docstring |
| Why it was decided that way, what was rejected, what it cost | The design document |
| When it was found, what it broke, what the injection showed | `CLAUDE_LOG.md` |

**A pointer is enough.** `Design: cmn_verdict_and_cli.md section 4.9.2.1` carries
a reader to the reasoning in one line and does not reproduce it. Reproducing it
is the drift a single registry exists to prevent, applied to prose.

**Context that makes the behaviour legible stays.** The boundary value a case
sits on, the frame a path resolves in, the reason an assertion reads failures
rather than the minority: each of those is what the code does and belongs where
the code is.

**What this is not.** It is not an instruction to write thin docstrings. The
project's own history is worth recording and is recorded; the question this rule
answers is **where**, and the answer is not "in the first paragraph of every
callable that touches the subject".

#### 3.1.1 A module docstring opens with what the file contains

Added 2026-10-21 at the project owner's instruction, after `assertions.py` and
`pipeline.py` opened on a phrase only a reader of the design could place.

**A reader opening a file asks what is in it, and the first paragraph answers.**
It names what the file contains, the kinds, records or functions it defines,
and where they sit in the harness: what runs before them, what runs after, and
what a failure here means for the steps that follow. **Only then** does the
docstring go into how each part works and the rules it keeps.

| Order | Holds |
|---|---|
| First line | What the file is, in plain words |
| First paragraph | What it contains |
| Second paragraph | Its place in the flow, and what its outcome decides downstream |
| After that | How the parts work, the rules they keep, and the design pointer |

**The owner's example, for `assertions.py`:** the file contains programmatic
assertions, the deterministic part of evaluating a response. They run first,
and when one fails, depending on its severity or type, the LLM judge may not be
involved at all, for security or cost; each test family, or each test in it,
decides that in its own way. Only after that come the assertion descriptions
and how they work.

**This is section 3.1 applied to a file.** A phrase like "the deterministic
half of the dual pass" states behaviour accurately and still tells a newcomer
nothing, because it names the file by its place in an argument rather than by
its contents.

#### 3.1.2 A module docstring carries the date it was created and last updated

Added 2026-10-21 at the project owner's instruction. Whoever audits a file or
troubleshoots a case reads the text in front of them, not a pointer to history,
so the file says how old it is and when it last changed.

```
"""<What the file is for, in one plain line.>

Created: 2026-09-19
Last updated: 2026-10-21

<What it contains.>

<How it works and how it is used.>

Specified by ``docs/design/...`` section N.
"""
# ------------------------------------------------------------- cases in here
# (generated by tools/refresh_case_summaries.py, test modules only)
```

**The two date lines are the docstring's third and fourth lines**, after the
purpose line and a blank line, in ISO form.

| Line | Holds |
|---|---|
| `Created:` | The earliest record of the file: its first write in a session transcript, otherwise the day git first added it. Set once, at creation, and never moved |
| `Last updated:` | The day of the latest change. The date only: what changed is `git diff`'s answer |

**The docstring is the cover; the case list is not part of it.** The list stays
generated and dynamic, and the cover is written when the file is. A hand-written
`Covers` line duplicated the generated list and drifted from it, so case
numbers leave the cover and its section citations move to `Specified by`.

**Kept current by a tool, checked by a case.** `tools/refresh_file_dates.py`
stamps today's date on every file that differs from its last commit and gives a
new file both lines. `cmn.file_dates.file_date_problems` reports a missing
or malformed line, a `Created` later than `Last updated`, a date in the future,
and a file changed since its last commit whose `Last updated` is neither today
nor after that commit. `MQC_CMN_UNI_112526` and `MQC_CAS_UNI_115773` assert it
with each root.

## 4. Imports
* **Three Groups**: Standard library, third-party, and first-party imports, separated by blank lines.
* **Absolute Imports**: Always use absolute imports (`from ingestion.golden_rules import GoldenRuleParser`).
* **Logger Declaration**: Module-level logger `logger = logging.getLogger(__name__)` declared immediately after imports.

## 5. Layout & Syntax
* **Line Length**: 100 characters max, enforced by `.pylintrc`.
* **Strings**: Double quotes (`"..."`) everywhere. Interpolate using f-strings exclusively.
* **Keyword-Only Flags**: Boolean options must be keyword-only using `*` (`def parse_data(self, content: str, *, validate_schema: bool = True)`).

### 5.1 A module is split at nine hundred lines, by subject

Added 2026-10-05 at the project owner's instruction, after the thousand-line
ceiling fired three times in one day on changes that had nothing to do with it.

**The hard ceiling is a thousand lines and `.pylintrc` enforces it.** The
problem is never the limit, it is when it fires:

| | |
|---|---|
| `mqc_uni_metadata.py` | Sat at 998 lines. **A prose edit would have failed the build** |
| `mqc_uni_harness_pin.py` | Sat at 995, with five lines of headroom |
| `mqc_uni_metadata.py` again | One new case took it to 1024, mid-change |

**A ceiling nobody can plan around fires at the worst moment.** So nine
hundred lines is where a module is treated as full: **the next subject added
belongs in a module of its own, named for that subject.**

#### The margin is for prose, not for more cases

The hundred lines between the runway ceiling and the hard limit are room for
the comments, docstrings and design pointers an ordinary edit adds. **They are
not a budget for two more tests.** A case that pushes a module past nine
hundred moves out with its subject, which is cheap now that a case module
holds only cases (`harness_test_taxonomy.md` section 13).

#### Split by subject, never by number

`mqc_uni_criticality.py` came out of `mqc_uni_metadata.py` because the code
ranking is its own subject: that module is about what a result carries, this one
about which of several codes names a finding.

**A `_2` suffix would destroy the one-subject-per-module property**, which is
what makes the suite navigable and what section 13 depends on. The question at
nine hundred lines is "what is the second subject in here", and the answer is
the new module's name.

#### Enforced, with the backlog declared

`cmn.module_size.runway_problems` reports a module at the ceiling that
`config/module_runway.yaml` does not declare, an entry past its expiry, and an
entry whose module is back under the ceiling. `MQC_CMN_UNI_112331` and
`MQC_CAS_UNI_115715` assert it with each root.

**Six harness modules were already past it**, three of them production code, so
each is declared with a reason and an expiry rather than split in one sweep.
**The list shrinks and never grows**: a module crossing the ceiling after this
was written fails until it is split or declared deliberately.

## 6. Data Validation & Failure Handling
* **Dataclass Schemas**: Schemas use `@dataclass` with a `from_dict` classmethod.
* **Strict Validation**: `from_dict` validates all required keys before instantiation, raising `KeyError` on missing fields.
* **Explicit Casting**: Coerce parsed values explicitly (`str(...)`, `int(...)`, `float(...)`) at boundaries.
* **Exception Chaining**: Re-raise exceptions using `raise ... from error`.
* **Narrow Catching**: Catch specific exceptions (`KeyError`, `ValueError`, `json.JSONDecodeError`). No bare `except:` or `except Exception`.

## 7. Documentation Prose

Applies to every Markdown file in the repository, and to text the harness generates.

* **No em dashes or en dashes.** Use a colon to introduce an explanation, a semicolon to join two independent clauses, commas for a parenthetical, or split the sentence. Ranges take a hyphen (`10001-19999`), never an en dash.
* **No pipe characters outside Markdown tables.** A pipe in prose is ambiguous with table syntax and breaks rendering when a value reaches a table cell.
* **Naming a prohibited character.** Where a prohibited character is itself the subject, describe it rather than reproducing it. A literal inside backticks is permitted only when the exact byte sequence is what matters, such as quoting a command that failed because of it.
* **One colon per sentence.** A second colon in the same sentence reads as a broken parenthetical. Rewrite instead: lead with the main clause and let the colon introduce the list, or use commas.
* **Prefer the shorter punctuation.** A comma that works is better than a semicolon that also works.

These rules apply to model output as well, enforced as described in `docs/design/harness_test_taxonomy.md` section 6.1 and the boundary checks in `docs/design/harness_extensibility_standard.md` section 2.

### 7.1 A log line states what happened; the reasoning lives in the design

Added 2026-10-07 at the project owner's instruction, extending section 3.1 from
docstrings to output.

**The rule is the same and so is the reason.** A reader looking at a log line
wants the outcome. A reader wanting to know why the rule exists is better served
by the document that owns it, and reproducing the rationale in every line is the
drift a single registry exists to prevent, applied to output.

| | Belongs in |
|---|---|
| What ran, what passed, what did not, and the counts | The log line |
| Why the rule is drawn where it is, what was rejected | The design document |

**The exception is a failure and a debug line.** Where the line explains a
failure, the why is the point: "4 skipped behind a prerequisite that did not hold" names
the cause because the cause decides the remedy. Debug output is for a reader
who has already asked why.

#### A case announces itself before it runs

**`RUNNING <nodeid>`, from setup.** A traceback names the line that raised and
not the case that reached it, and the two differ whenever a helper is shared.
The identifier carries the module and the class, so the line hands a reader the
code segment to open. Specified in `harness_test_taxonomy.md` section 8.3.1.

#### One word per concept, and the one pair that is not drift

Added 2026-10-21 at the project owner's instruction to check "that the
vocabulary used across the files about the same funcitonality, especially key
concepts keep to the same vocabulary."

| Concept | The word | Not |
|---|---|---|
| The mode that reads a recording | **`replay`** | `fixture`, `frozen`. `--mode replay` is the flag and `testing-standards.md` says replay |
| The file a replay run reads | **`fixture`** | Anything else. A fixture is a file; replay is what a run does with it |
| A step of the attribution ladder | **`rung`** | `Job 1`. A CI job is also a job, and one rung is three jobs in the gate's shape |
| A CI job | **`job`** | `rung`, `step`. A step is a step of a job |
| The repository under test by a graded case | **`engine`**, then the model | `provider` where the engine is meant: a provider serves several |

**`consumer` and `the case repository` are both correct and mean different
things.** A **consumer** is the role: anything that installs this harness and
runs cases against it. `cmn/registries.py` holds a consumer registry,
`regress-consumers-on-merge.yml` fans out across it, and
`cmn_verdict_and_cli.md` records that "a harness with no registered consumers
has nothing to fan out to". **The case repository** is the one consumer that
exists, `AP-Model-QC`.

**So a sentence picks by what it is about**: a rule binding on anything that
installs the harness says *consumer*; a statement about where the corpus lives
or what that repository's `pytest.ini` sets says *the case repository*. This was
nearly swept into one word on 2026-10-21, with 199 uses of one against 55 of the
other reading as drift. **It is not drift, and the count is not the test.**

**In conversation it is the Model Repository**, which is a third name and
deliberately not in the documents.

#### The vocabulary for a measured run

**Total, executed, passed, failed, skipped**, in that order, and a skip carries
its cause:

```
Band P0: 15 total, 12 executed, 9 passed, 3 failed, 3 skipped behind a prerequisite that did not hold
```

**A crash is not a failure, and the block says so.** A case that raised
something other than an assertion adds `broken: <n>, so the run exits 3` and a
`broken 1 of n:` line naming it, its code and its exception, and it leaves the
`failed` count. Printed only when something broke, being an alarm
(`harness_test_taxonomy.md` section 5.1.1).

**"Not measured" is not a state.** A case that did not run was skipped, and
naming it anything else leaves a reader with no outcome to act on.

**A skip names its kind, because the kinds take different remedies.** Three
exist: behind a prerequisite that did not hold, as a known failure in quarantine, and for
a reason of ours. Collapsing two of them into one phrase is the same defect as
"not measured" at a smaller scale: the count stays right and the reader acts on
the wrong thing.

**A line reports only its own subject.** A band states its own total and never
how many cases the other bands hold, so pytest's deselected count is suppressed
rather than printed: it is the size of everything this run was not asked to do.

**And the counts are the last line.** The deselected count is the first thing an
engineer inspecting a failure sees, because pytest's summary line is written
after every hook that could replace it. Dropping the count happens before that
line is built and writing the counts happens after it, from two hooks, because
no single hook runs at both moments (`cmn_verdict_and_cli.md` section 7.11.2).

#### A test report breaks a run down by band, and audits apart

Added 2026-10-21 at the project owner's instruction: "need break down by p0, p1
and p2-p4 and audit separately not just how many tests how many executed how
many passed."

**A report of a run, in a session or a log entry, carries one line per
repository**, harness first, and each line is broken down rather than summed:

| Row | Holds |
|---|---|
| P0 | Total, executed, passed, failed, skipped, with each skip's cause |
| P1 | The same |
| P2-P4 | The same, as one row |
| Audits | The mutation audits, with whether they ran and why not |
| Preconditions | `UNI` and `SYS`, which carry no priority, as a row of their own |

**Graded results are given per engine**, one row each, since an engine's bands
are its own measurement. A count that differs from the total names its reason
on the row, "6 mutation audits deselected (not requested)", because a reader
handed "922 of 928" reads the gap as skips behind failures, which is exactly
how this rule came about.

### 7.2 A document's filename says which repository it belongs to

Added 2026-10-08 at the project owner's instruction. **Two repositories held a
`docs/harness_running_jobs.md` and a `docs/harness_document_register.md` each**, and an editor
tab shows a filename rather than a checkout.

**The failure is a change made in the wrong repository**, which is the most
expensive kind to find: both files parse, both lint, both commit, and the
mistake surfaces as a procedure that stopped matching the workflows it
dispatches. The two repositories' designs cross-reference constantly, so a
reader moves between them all day and the names are the only thing
distinguishing one open file from the other.

#### The rule

**A tracked document under `docs/` carries its repository's token.** `harness`
here, `model` in the case repository, which is the vocabulary the shipped names
already use: `harness_test_plan.md` against `model_evaluation_test_plan.md`, and
`rtm_harness.csv` against `rtm_model.csv`.

```
docs/harness_running_jobs.md        docs/model_harness_running_jobs.md
docs/harness_document_register.md   docs/model_harness_document_register.md
```

**A name already unambiguous needs nothing added.** `cmn_verdict_and_cli.md`,
`tier1_ingestion.md` and `consumer_ci.md` name subjects that exist in one
repository only, so a reader with one open knows where they are. The rule is
satisfied by the name being unmistakable, not by a prefix for its own sake.

#### What is exempt, and why each one is

| Exempt | Why |
|---|---|
| `README.md`, `DESIGN.md`, `CHANGELOG.md` | Conventional names a tool or a reader expects at a root. Renaming them hides them |
| `CLAUDE.md`, `CLAUDE_LOG.md` | Read by name by the assistant and by the governance list |
| `.claude/rules/*.md` | Governance, loaded by name |
| `LICENSE`, `NOTICE` | The licence texts themselves |

**The exempt set is small and sits at a repository root**, which is the thing
that makes it safe: a file at the root of a checkout is seen beside that
checkout's name, and a file three directories down is not.

#### The old names stay resolvable

A renamed document is recorded in the register with its former name and the date,
for the reason section 3.2 of `testing-standards.md` gives about identifiers:
`CLAUDE_LOG.md` carries the old path in entries that were true when written, and
a reader of that history has to be able to follow it.

#### Enforced, not remembered

`cmn.document_naming.undifferentiated_documents` reports a tracked document
under `docs/` whose name carries neither the repository's token nor an
exemption. **The token comes from the declared project name**, which travels
with the repository: reading the directory name failed on a runner, where the
checkout's parent carries the repository's name as well (section 8.0).
`MQC_CMN_UNI_112346` and `MQC_CAS_UNI_115718` call it with each root, which is
the one-implementation-two-callers arrangement the encoding, annotation and
header rules already use.

### 7.3 A section citation resolves, or it is not a citation

Added 2026-10-11 at the project owner's instruction, after a session found four
dangling citations and two duplicate section numbers by grepping for them.

**The designs cite each other constantly**, roughly two hundred times in the
harness alone, and a citation is how this project avoids restating a decision in
two places. A citation that resolves to nothing is therefore worse than a
restatement: the reader is sent somewhere and finds nothing there.

#### What went wrong, in two shapes

| Shape | Instance |
|---|---|
| **Dangling** | Four documents pointed at subsections 1.1, 2.1, 2.4.1 and 2.7 of the open-questions document, which numbers only 1, 2, 2A, 3 and 4 |
| **Duplicate** | `tier2_execution.md` had two section `7.8`s, and two requirements cited the number for different specifications |

**The duplicate is the worse of the two.** A dangling citation sends a reader
nowhere and they know it. A duplicate resolves, so nothing reports it and the
reader is simply misinformed: `MQC_REQ_HAR_EXE_0058` meant the judge dispatch
and `MQC_REQ_HAR_EXE_0083` meant the retained request, and both cited `7.8`.

**Three of the four dangling ones were worse still**, because they described a
settled question as open and two asserted a built check was "not built". A
design claiming an absence that does not exist costs the same way as one
claiming enforcement it lacks: the reader stops looking, or builds it twice.

#### The rule

**A citation naming a document and a section resolves to a heading in that
document, and a document numbers each section once.** Both halves are checked,
because each alone leaves the other's failure silent.

**This rule applies to itself, which is why the row above names no citation.**
A document describing a dangling citation contains one, so the subject is
described rather than reproduced: the same convention section 7 already states
for a prohibited character that is itself the subject. The check found this
section on its first run, reporting four citations that exist only as examples
of the defect.

**A retired number is not an exception.** `harness_open_questions.md` retires
numbers deliberately, so a reader returning to a reference finds what it named
or finds nothing. That rule is about the *target*; it does not license a citing
document to keep pointing at one. The citation moves to where the answer went.

#### Within a repository, and across one by declaration

A citation naming a document the other repository owns cannot be resolved from
here, because the harness owns no case data and the installed wheel ships no
tests. So the in-repository half runs everywhere, and the cross-repository half
declares the `paired` environment scope and is **deselected** where the sibling
checkout is absent (`harness_test_taxonomy.md` section 7.5.1).

**Deselected rather than skipped**, which is the arrangement section 8.0 already
relies on: a case that cannot run leaves the total rather than reporting a
non-outcome in it.

#### Enforced, not remembered

`cmn.document_citations.unresolved_citations` reports a citation whose target is
in this repository and whose section is not a heading in it, and
`duplicate_sections` reports a document numbering one section twice.
`MQC_CMN_UNI_112352` and `MQC_CAS_UNI_115734` call them with each root, the
one-implementation-two-callers arrangement the encoding, annotation, header and
naming rules already use.

### 7.4 A README change carries a changelog entry, in the same change

Added 2026-10-12 at the project owner's instruction: "anytime we update readme,
we need to update changelog, otherwise traceability is lost."

**The README describes the current state and nothing else**, which `CHANGELOG.md`
states as the division between them. That is what makes the README readable, and
it is also what makes it historyless: a figure that moves there leaves no record
of when it moved or why, and the why is the part a later reader needs.

| Document | Answers |
|---|---|
| `README.md` | What is true now |
| `CHANGELOG.md` | **What changed, when, and why** |

**So the two are edited together.** A README edit with no changelog entry is an
incomplete change, in the same way a regenerated artifact that was not
re-verified is incomplete.

#### It applies per repository, so both repositories hold both documents

`AP-Model-QC` had a README and no changelog until this rule was written, and its
README figures had moved repeatedly: the recorded-response count, the finding
totals, the precondition count. Each of those is a fact about a measurement, and
the record of when it changed was `CLAUDE_LOG.md` alone, which is a narrative
rather than a changelog and is not where a reader looks for a version history.

**The exemption in section 7.2 is about naming, not about existence.**
`README.md` and `CHANGELOG.md` keep their conventional names in both
repositories because a tool and a reader expect them at a root; that is the
opposite of a licence to omit one.

#### What cannot be checked here, and what can

Whether two files were edited **in the same change** is a property of a commit,
which no test running against a working tree can see. What a repository can
check is the state that results from skipping the step, which is the answer the
authoring-order rule already gives:

| Enforced | By |
|---|---|
| A repository holding a README holds a changelog, and the register names it | `MQC_CMN_UNI_112353` and `MQC_CAS_UNI_115735` |
| Both are in the document register | The register check, in both directions |
| **The two were edited together** | **Nothing here. A gate step compares the paths a pull request touched** |

#### 7.4.1 An entry states the purpose, then the change, and never who made it

Added 2026-10-18 at the project owner's instruction.

**The changelog tracks changes to the README, the scripts and the harness, not
their authorship.** The README and the changelog describe the project, its
structure, the repository and its tests as they are now, and the path they took
to get here. Who made a change says nothing about any of that.

**Authorship is already recorded, by the commit and the push.** The person
who commits or authorizes the push is responsible for the change, whoever or
whatever implemented it, and is the one who fixes what it breaks, with an
assistant or without. Naming an implementer in the changelog restates the git
history less reliably and blurs that responsibility.

| | Belongs in |
|---|---|
| Why the change was needed: the gap, the defect, what a reader could not learn | The changelog entry, first |
| What changed, and any figure that moved | The changelog entry, second |
| Who asked for it, in what words, and why they asked | `CLAUDE_LOG.md` and `.claude/logs/PROMPT_LOG.md` |

**A purpose the author does not agree with is discussed before it is written**,
not recorded as somebody else's reason. An entry attributing a change ("at the
owner's request", "rewritten by hand") has left out its purpose and put a
party in its place.

### 7.5 A document's sections read in numeric order

Added 2026-10-22 at the project owner's instruction, closing a gap both
repositories had recorded and neither had closed: "Nothing checks the order,
and a check is what would close this rather than one pass of reordering."

**A reader navigates a design by its numbers.** Section 7.3 makes a citation
resolve, so a reader sent to section 8.3 finds a section 8.3, and it says
nothing about where in the file that section sits. In `harness_ci_pipeline.md`
it sat after 8.4.

| | Guarantees |
|---|---|
| Section 7.3 | The number exists, and exactly once |
| This section | It appears where a reader scrolling for it will arrive |

**Thirty seven headings were out of order when this was written**, across
twelve documents in the two repositories: seven designs, two registers, a test
plan, a runbook and the referential index. The register naming the gap listed
four documents and a hand count of them found thirty one, so **both the
documents and the number were understated by a reader working from the
documents in front of him**, which is the argument for a check rather than for
one pass of reordering.

#### 7.5.1 What counts as a section number

**A heading whose text opens with a dotted number, or with a bare number
carrying a period.** `### 7.13.2 A recording without a request` and
`## 8. The credential boundary` are sections. A heading opening with a bare
number and no period is prose.

**The period is what separates the two, and admitting the bare form costs two
false reports.** Both repositories hold four such headings and all four are
prose: an HTTP status, a count of assertions, a count of violations and a case
identifier. A rule reading them as sections reports a document as disordered
because its prose headings do not ascend.

**A letter sorts after the digit it follows**, giving 5, 5.1, 5.3.1, 5A,
5A.1, 5B, 6. A lettered section is a sibling inserted after the fact, as
`tier3_evaluation.md` section 5A was, and its subsections belong with it
rather than among its neighbour's.

**A fenced block holds no headings.** A document showing a heading as an
example carries a line shaped exactly like one of its own sections, and the
period rule cannot separate the two: the example **is** a section number.

**The generated case list is not the reason, although it reads like one.**
Those lines open with a hash and a bare six-digit identifier, which the period
rule already excludes. An injection removing the fence handling went NOT
CAUGHT until the case was changed to assert an example heading rather than a
case list, and the comment in the code gave the same wrong reason.

#### 7.5.2 What it does not check, and why that stays open

**The heading rank against the depth of the number it carries.** A
heading's **parent by rank** is the nearest heading above it carrying fewer
hashes, and its **parent by number** is the longest prefix of its number the
document also numbers. Where the two disagree the rendering nests a section
under its neighbour rather than under its parent, which is what a
fourth-level 9.12 did under a third-level 9.11.

**Reordering fixed most of them and cannot fix the rest.** The twelve
documents held 152 such disagreements and hold 69: a section in the wrong
place usually had the wrong parent by rank as well, so moving it corrected
both. Ten more were exposed rather than created by the move, in three
documents whose ranks already disagreed, and those are corrected here. **What
remains is 69 headings whose hash count is simply wrong**, and changing them
is a decision about how a document renders rather than about where its
sections sit, so it is recorded as a gap in `harness_open_questions.md`
section 2B rather than made here.

#### 7.5.3 Enforced, not remembered

`cmn.document_citations.disordered_sections` reports every numbered heading
that sorts at or before the numbered heading above it, naming both.
`MQC_CMN_UNI_112399` and `MQC_CAS_UNI_115778` call it with each root, the
one-implementation-two-callers arrangement sections 7.2, 7.3 and 7.4 already
use.

**It sits beside the citation checks because it reads the same headings.**
`duplicate_sections` asks whether a number appears twice and this asks whether
the numbers ascend, from one parser, so a heading form that fools one cannot
slip past the other.

## 8. Cross-Platform Rules

The harness is verified on Ubuntu and Windows (A18). These are not style preferences: each one names a defect that occurs on exactly one platform and is silent on the other.

* **Every file open declares its encoding.** `open(path, encoding="utf-8")`, never the bare form. On Windows, Python 3.14 defaults to `cp1252`, so a rubric anchor containing an em dash reads as mojibake on Windows and correctly on Linux, with **no exception raised**. Ingestion uses `utf-8-sig` where a BOM is tolerated.
* **Every path is a `pathlib.Path`.** No string concatenation, no `os.sep`, no literal `/` or backslash in a constructed path. Paths read from configuration are converted at the boundary.
* **Content is normalized to LF before it is hashed or compared.** The request hash must not depend on how a file was checked out. `.gitattributes` also enforces this; both exist because either alone is a single point of failure.
* **CSV is opened with `newline=""`**, as the `csv` module requires, or an embedded newline in a quoted field is mangled on one platform only.
* **Identifiers that become filenames are case-normalized and screened.** Linux filesystems are case-sensitive and Windows is not, so two case definitions differing only by letter case collide on Windows and coexist on Linux. Windows also reserves `CON`, `PRN`, `AUX`, `NUL`, `COM1` to `COM9` and `LPT1` to `LPT9`, which cannot be directory names at all.
* **Temporary files come from `tempfile`.** Never a literal `/tmp` or `C:\Temp`.
* **No shell invocation.** `subprocess` is called with a list and `shell=False`, because quoting rules differ between `sh` and PowerShell.
* **Documented commands work on both.** Any command in a tracked document is either OS-neutral or given for both shells. `${VAR}` is not PowerShell and `$env:VAR` is not bash.

### 8.0 A case reads nothing above the repository root

Added 2026-10-08, after a case that passed on a developer's disk failed on both
runners and **failing the harness merge failed every model job behind it**.

**A checkout sits wherever somebody put it.** On a developer's disk this one is
`PythonProject/AP-Harness-QC`; GitHub Actions checks out to
`work/<repo>/<repo>`, so **the parent directory carries the same name as the
root**. A case asserting something about the parent is asserting something about
a path the project does not own.

| | Parent of the root |
|---|---|
| A developer's disk | `PythonProject`, or anything at all |
| A runner | `AP-Harness-QC`, the repository's own name again |
| A worktree | The worktree directory, named for a branch |

**What broke.** `MQC_CMN_UNI_112346` proved itself non-vacuous by asserting that
`undifferentiated_documents` refuses a root whose name carries no repository
token, and reached for `_ROOT.parent` as such a root. On a runner that parent is
`work/AP-Harness-QC`, which carries `harness`, so the refusal never fired and
the assertion failed with `DID NOT RAISE ValueError`.

**The rule.** A case builds what it needs under `tmp_path` and names it, or
reads inside the repository. `Path(__file__).resolve().parents[2]` is the root
and nothing above it is readable.

**One exception, and it is declared rather than assumed.** A case needing a
sibling checkout says so with the `paired` environment scope, naming the
directory it needs (`harness_test_taxonomy.md` section 7.5.1). That read is
above the root by design and **it cannot be wrong on a runner**, because the
absent sibling deselects the case instead of changing what it asserts. The
defect above was an undeclared read whose answer happened to differ; a declared
one has only two outcomes and both are correct.

#### It is the same class as the encoding rule, and fails the same way

Section 8.2.1 separates a platform difference that raises from one that silently
changes a value. This is the second kind one level up: the code was correct, the
test was correct about a path it did not own, and **it passed everywhere it was
ever run before CI**. Both runners agreed with each other and disagreed with the
author, which is the signature of a dependence on the environment rather than on
the platform.

#### Reproducing it costs a copy of the tree

**Not enforced mechanically**, because what a case reads is resolved at runtime
and a scanner cannot follow it. What can be done is reproduce the layout, which
is cheap and found this in one run:

```
<scratch>/work/AP-Harness-QC/AP-Harness-QC/     the tree, copied
pytest tests/cmn/mqc_uni_document_naming.py     run from there
```

Running the **committed** version there reproduced the runner's failure exactly,
and the fix passes. That is the injection `testing-standards.md` requires,
applied to an environment rather than to a defect.

#### And the mechanism it exposed was worth fixing too

`repository_token` read the directory name, which is incidental. It reads the
project name from `pyproject.toml` now and falls back to the directory name, so
the token **travels with the repository** rather than with where it was cloned.
A clone into `qc/` would otherwise have refused the whole suite.

### 8.1 File edits carrying escapes go through a script, never a shell heredoc

Added 2026-09-23 after four failures in one working session.

**A shell heredoc is a single point of failure for any content carrying a
backslash.** The rule below has held since it was written; **the reason given
for it was wrong, and was corrected on 2026-10-04 by isolating it.**

The original explanation was that the shell, the heredoc, Python's string
literal parsing and the target format each interpret escapes and a value has to
survive all four. **The shell and the heredoc are innocent.** A quoted
delimiter is required by POSIX to pass its body through byte for byte, and it
does: `$HOME` and a backtick both survive verbatim.

**What is eaten is backslashes, specifically, and before the shell sees them.**
Probed by writing a known body through a quoted heredoc and reading the file
back with `od -c`:

| Written | Landed |
|---|---|
| `\n` | `\n` |
| `\\n` | **`\n`** |
| `\\\\n` | **`\\n`** |
| `$HOME` | `$HOME`, unexpanded |
| A backtick pair | Verbatim |

One level of backslash unescaping happens in the tool layer that carries the
command, not in bash. So no amount of shell quoting fixes it, which is exactly
why the remedy below is to stop routing escaped content through a heredoc at
all rather than to quote it more carefully.

**Why the correction matters rather than being pedantry.** A rule with a wrong
reason invites somebody to work around the reason: a reader told the shell is at
fault will reach for `printf %q`, a quoted delimiter or an extra layer of
escaping, and all three fail because none of them touches the layer that is
actually stripping. This is the same failure mode section 7.7.5 records about a
gap whose recorded reason was wrong: the reason is what a reader acts on.

| What was written | What landed | Caught by |
|---|---|---|
| A newline escape inside a join | A real line break inside a string literal | Python, `SyntaxError` |
| A doubled backslash in a regex | Single-escaped, so the pattern never matched | Nothing. The check passed |
| A word-boundary escape in a YAML regex | **A literal backspace byte, 0x08** | The loader, `QC_DATA_MALFORMED_SOURCE` |
| A `pathlib.write_text` newline argument | The file truncated to zero bytes | Recovered from the git index |
| **This table** | Rows one and three mangled on first write | Reading it back |

**The rule.** Content containing a backslash, a triple quote, a backtick or a
dollar sign is written with the Write or Edit tool, or by a script file invoked
by path. It is never passed through a `<<'EOF'` block.

**Why a script file and not a quoted heredoc.** A quoted delimiter stops the
shell expanding variables and does not stop a backslash being halved before
bash is reached, because that happens upstream of the shell entirely. A file
written with the Write tool is read by exactly one parser, the one that will run
it, and no transport sits between.

**Selecting an edit target by searching for a substring is the same class of
error.** A repair in this session searched for a line containing `pattern:` and
`zero`, and matched a different assertion whose text contained the phrase
"below zero". Select by a stable identifier, and assert the match count before
writing.

**The third row above is the one that matters.** The first two fail loudly and
the fourth was recoverable. A regex that lost an escape **passes**, reports
nothing, and leaves a check that looks like coverage and is not.


#### 8.1.1 A short program is single-quoted, and still goes in a file once it carries a backslash

Added 2026-10-23 at the project owner's instruction, after a comment written
through the interpreter's program flag arrived with a word missing and the
script that wrote it reported success.

**A double-quoted program is read by the shell before the interpreter sees
it.** Backticks inside it are command substitution and a dollar sign is an
expansion, so the text that runs is not the text that was written. What landed
in the comment was the sentence with the backticked identifier deleted, and
nothing failed: the program ran, the file was written, and the damage was
found by reading the result.

**Single quotes stop that, and nothing else does.** Measured on 2026-10-23 by
writing a known body through the flag and printing what arrived:

| Written inside single quotes | Arrived |
|---|---|
| A backtick pair around a command name | Verbatim, unsubstituted |
| A dollar sign and a variable name | Verbatim, unexpanded |
| A doubled backslash before an `n` | **Single. One level was removed** |

**So the quoting fixes the shell and does not fix the transport.** The third
row is section 8.1 one layer up: one level of backslash unescaping happens in
the tool layer carrying the command, above the shell, and no quoting reaches
it. A program carrying a backslash is still written with the Write tool and
run by path.

| The program carries | Pass it |
|---|---|
| Nothing but letters, digits and double-quoted strings | With the flag, in single quotes |
| A backtick or a dollar sign | With the flag, in single quotes, which is what they are for |
| **A backslash, or a single quote** | **In a script file, run by path** |

**A single-quoted shell string cannot contain a single quote at all**, so the
program uses double quotes throughout, which is this document's rule for
Python strings anyway. A program needing both is a program that belongs in a
file.

**Why the rule is a quoting rule and not "always write a file".** A one-line
read of a registry is worth a single command, and the alternative is a file
per question. What the measurement establishes is where the line sits: the
shell is handled by quoting, and the transport is handled only by a file.


### 8.2 The encoding rule is enforced, not merely followed

Added 2026-09-24, after the security corpus became the first data in the
project whose meaning depends on non-ASCII code points.

Section 8 has always required `encoding="utf-8"` on every read and write. Every
file in both repositories complied when this was written, and **nothing
checked**, which is the state the annotation rule was in while 597 test
callables violated it.

`cmn.code_standards.encoding_gaps` now parses every module and reports any
`open`, `read_text` or `write_text` that declares no encoding.
`MQC_CMN_UNI_112511` and `MQC_CAS_UNI_115505` call it with each root, which is
the same one-implementation-two-callers arrangement the annotation and header
rules use.

**Parsed, not matched.** A regex for `open(` cannot tell a call from the word
in a docstring, and this project has already corrected one scanner that could
not tell a definition from a definition inside a string.

#### 8.2.1 Why this rule in particular fails silently

A missing encoding raises nothing. It reads `cp1252` on Windows and `utf-8` on
Linux, so the same commit produces **different values on the two platforms CI
runs**, and both runs report success.

| Rule | How a violation announces itself |
|---|---|
| Missing annotation | Nothing at runtime, caught by `112500` |
| PEP 563 import | Nothing at runtime, caught by `112501` |
| **Missing encoding** | **Nothing, ever. The value is simply different** |

The security corpus made this concrete rather than theoretical: `154105` carries
zero-width characters and `154106` Cyrillic homoglyphs, and those code points
**are** the attack. Read as `cp1252` they become something else, while the
canary assertions stay pure ASCII and keep passing. The case would go on
reporting a pass and stop being the test it claims to be.

**The rule these follow from:** a platform difference that raises an exception is a nuisance, and a platform difference that silently changes a value is a defect that reaches the durable record. Every rule above targets the second kind.

## 9. Static Analysis & Linting (Pylint 10/10)
* **Zero-Warning Tolerance**: All production and test code MUST achieve a **10.00/10** score against `.pylintrc`.
* **No Inline Suppressions Without Approval**: `# pylint: disable=...` directives are prohibited unless approved in Phase 2.
