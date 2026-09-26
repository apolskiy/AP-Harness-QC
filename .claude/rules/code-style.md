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

`MQC_CMN_UNI_11113` enforces presence, position and the correct identifier. A header nothing checks drifts the first time a file is added in a hurry, which is the pattern this project has corrected often enough to stop writing new instances of.


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

`MQC_CMN_UNI_11113` and `11140` enforce the state rather than the habit, which
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

`MQC_CMN_UNI_11111` parses every Python file in the repository and fails when a parameter or return annotation is missing, and `MQC_CMN_UNI_11112` fails on a `__future__` annotations import.

**Pylint does not check this**, which is why the rule stood in this document while 597 test callables violated it. A rule nothing checks is a convention, and this project has corrected that pattern often enough to stop writing new instances of it.

## 3. Docstring Formatting
Google style docstrings are mandatory across all modules, classes, and functions:
* **Types In Parentheses**: Each `Args:` entry specifies its type in parentheses (`raw_payload (dict): Raw JSON response...`).
* **Returns Mandatory**: `Returns:` is never omitted, documented as `Returns: None` if the procedure returns nothing.
* **Sphinx Cross-References**: Use `:class:`, `:meth:`, `:func:`, `:exc:`, and `:mod:` roles in prose. Double backticks for literals.

## 4. Imports
* **Three Groups**: Standard library, third-party, and first-party imports, separated by blank lines.
* **Absolute Imports**: Always use absolute imports (`from ingestion.golden_rules import GoldenRuleParser`).
* **Logger Declaration**: Module-level logger `logger = logging.getLogger(__name__)` declared immediately after imports.

## 5. Layout & Syntax
* **Line Length**: 100 characters max, enforced by `.pylintrc`.
* **Strings**: Double quotes (`"..."`) everywhere. Interpolate using f-strings exclusively.
* **Keyword-Only Flags**: Boolean options must be keyword-only using `*` (`def parse_data(self, content: str, *, validate_schema: bool = True)`).

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

These rules apply to model output as well, enforced as described in `docs/design/test_taxonomy.md` section 6.1 and the boundary checks in `docs/design/extensibility_standard.md` section 2.

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

### 8.1 File edits carrying escapes go through a script, never a shell heredoc

Added 2026-09-23 after four failures in one working session.

**A shell heredoc is a single point of failure for any content carrying a
backslash.** The shell, the heredoc, Python's string literal parsing and the
target format each interpret escapes, and a value has to survive all four
unchanged. It usually does not.

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
shell expanding variables and does not stop the heredoc from being one more
layer that has to be got right. A file on disk is read by exactly one parser,
the one that will run it.

**Selecting an edit target by searching for a substring is the same class of
error.** A repair in this session searched for a line containing `pattern:` and
`zero`, and matched a different assertion whose text contained the phrase
"below zero". Select by a stable identifier, and assert the match count before
writing.

**The third row above is the one that matters.** The first two fail loudly and
the fourth was recoverable. A regex that lost an escape **passes**, reports
nothing, and leaves a check that looks like coverage and is not.


### 8.2 The encoding rule is enforced, not merely followed

Added 2026-09-24, after the security corpus became the first data in the
project whose meaning depends on non-ASCII code points.

Section 8 has always required `encoding="utf-8"` on every read and write. Every
file in both repositories complied when this was written, and **nothing
checked**, which is the state the annotation rule was in while 597 test
callables violated it.

`cmn.code_standards.encoding_gaps` now parses every module and reports any
`open`, `read_text` or `write_text` that declares no encoding.
`MQC_CMN_UNI_11157` and `MQC_CAS_UNI_10445` call it with each root, which is
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
| Missing annotation | Nothing at runtime, caught by `11111` |
| PEP 563 import | Nothing at runtime, caught by `11112` |
| **Missing encoding** | **Nothing, ever. The value is simply different** |

The security corpus made this concrete rather than theoretical: `50006` carries
zero-width characters and `50007` Cyrillic homoglyphs, and those code points
**are** the attack. Read as `cp1252` they become something else, while the
canary assertions stay pure ASCII and keep passing. The case would go on
reporting a pass and stop being the test it claims to be.

**The rule these follow from:** a platform difference that raises an exception is a nuisance, and a platform difference that silently changes a value is a defect that reaches the durable record. Every rule above targets the second kind.

## 9. Static Analysis & Linting (Pylint 10/10)
* **Zero-Warning Tolerance**: All production and test code MUST achieve a **10.00/10** score against `.pylintrc`.
* **No Inline Suppressions Without Approval**: `# pylint: disable=...` directives are prohibited unless approved in Phase 2.
