<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->

# Running Jobs: Debug, Diagnose And Stabilization

**You do not need to read a design document to start a run.** This page is the
whole operating procedure for the three on-demand workflows. Every command
works unchanged in `bash` and in PowerShell.

If you want to know *why*, `docs/design/ci_pipeline.md` covers the workflows
and section 3C covers branch topology. Nothing here requires reading them.

---
---

## 0. Before Anything: Cutting A Branch

**`main` is the master branch.** Everything is cut from it, merged back into
it, and deleted. `main` is never merged into a branch.

```
<kind>-<referent>-<MM-DD-YYYY>
```

```
git checkout main
git pull
git checkout -b expand-10428-09-24-2026
```

The date is **the day you cut it**, and it is not decoration: it is the last
moment your branch and `main` agreed, and the gate reads it.

### 0.1 The four kinds

| Kind | For |
|---|---|
| `expand` | New cases needing no harness change |
| `extend` | Cases that cannot exist until the harness grows a capability |
| `stabilization` | Integrating finished branches before they reach `main` |
| `debug` | Chasing one problem |

### 0.2 The referent says what the work is

A date says when. It does not say what, so the last part is a **referent** from
a registered kind rather than free text.

| Kind | Looks like | Use when |
|---|---|---|
| Ticket | `MQC-1234` | Anything tracked, and anything spanning several cases |
| Case identifier | `10428` | The branch fixes exactly that case |
| Release | `v1.2.0` | Cutting or stabilizing a release |

**`expand-fix-the-thing-09-24-2026` is refused**, because free text is not a
referent. A case identifier is checked for existence, so a typo is reported on
your first push rather than at review.

**One referent per working branch.** Work spanning three cases takes a ticket,
because a branch naming three things is a branch doing three things.

### 0.2.1 A stabilization branch may leave the referent out

```
stabilization-09-24-2026
stabilization-v1.2.0-09-24-2026
```

**Collecting several tickets is what that branch is for**, so naming one of
them would assert something untrue about the rest. For a cycle the date is the
identity, not a timestamp on it.

Give a referent when there genuinely is one, such as a release being
stabilized. **A bare date is refused for `expand`, `extend` and `debug`**,
because each of those holds exactly one unit of work and should say which.

### 0.3 Everything reaches main through a stabilization branch

| From | To | |
|---|---|---|
| `expand`, `extend`, `debug` | `stabilization-*` | Yes |
| `stabilization-*` | `main` | Yes |
| `expand`, `extend`, `debug` | `main` | **Refused** |
| `main` | anything | **Refused** |

A pull request taking a forbidden route is reported by the gate with
`QC_HARNESS_BRANCH_ROUTE`.

### 0.4 When your branch goes stale

| Age | What happens |
|---|---|
| Under 14 days | Nothing |
| 14 to 29 days | The gate reports the age in its summary and stays green |
| 30 days or more | **The gate fails** until you succeed the branch |

**You cannot merge `main` into your branch to fix this.** Succeed it instead:

```
git checkout main
git pull
git checkout -b stabilization-10-24-2026
git merge stabilization-09-24-2026
git branch -d stabilization-09-24-2026
```

The work moves onto a fresh base. The base is never dragged to the work, which
is why this is allowed and a back-merge is not. **Editing the date instead is
the one repair that makes the name lie**, and the two-week warning band exists
so nobody is tempted to.


## 1. Which One

Three on-demand workflows, and picking between them is the only hard part.

| You want to | Use | Key input |
|---|---|---|
| Rerun named tests, possibly several times | `debug-failures-on-demand` | `tests`, `repeat` |
| Find out whether **code** or **fixtures** changed a result | `diagnose-on-demand` | `code_ref`, `fixture_ref` |
| Run the whole suite against one ref | `regress-harness-on-branch` | `ref` |

**None of the three reports a status check, and none yields a verdict.**
Nothing they do can contribute to, cancel or colour a gate run on the same
commit.

---

## 2. Rerunning Named Tests

```
gh workflow run debug-failures-on-demand.yml --ref stabilization --field tests=11141
```

| Input | Answers | Default |
|---|---|---|
| `tests` | Which tests. Identifiers or nodeids, one per line or comma separated | Required |
| `repeat` | How many times to run them | `1` |
| `ref` | Branch, tag or commit | The dispatching ref |
| `engine` | `gemini`, `openai` or `claude` | `gemini` |
| `mode` | `replay` or `live` | `replay` |

### 2.1 `repeat` is how you tell a flake from a failure

A test that fails once and passes four times is not the same object as one that
fails five times out of five, and the fix is different in each case.

```
gh workflow run debug-failures-on-demand.yml --field tests=11141 --field repeat=5
```

**Set it above 1 whenever you are not sure**, which is most of the time when a
test failed in CI and passes on your machine.

---

## 3. Telling Code From Fixtures

`diagnose-on-demand` takes two refs and holds one fixed, which is the same
one-variable-at-a-time principle the gates are built on.

| `code_ref` | `fixture_ref` | A change in the result means |
|---|---|---|
| Your branch | `main` | **Your code** changed it |
| `main` | Your branch | **Your fixtures** changed it |
| Your branch | Your branch | Something did. This tells you nothing |

```
gh workflow run diagnose-on-demand.yml --field code_ref=extend-judge-replay-09-24-2026 --field fixture_ref=main
```

`fixture_ref` defaults to whatever `code_ref` is, which is the third row and
the one that answers nothing. **Fill both in when you are diagnosing**, or you
have run an ordinary suite with extra steps.

`selection` takes a pytest marker expression and runs the full suite when
empty.

```
gh workflow run diagnose-on-demand.yml --field code_ref=stabilization --field fixture_ref=main --field selection="unit or system"
```

---

## 4. Regressing A Branch

```
gh workflow run regress-harness-on-branch.yml --ref stabilization
gh workflow run regress-harness-on-branch.yml --field ref=a1b2c3d
```

**This does not cancel a run already in progress.** A regression is asked for
deliberately, and cancelling one because a second was requested discards the
answer somebody was waiting for. Two runs may be deliberately comparing two
refs.

The gate cancels superseded runs because a newer commit makes an older gate
result irrelevant. That reasoning does not carry here.

---

## 5. Watching And Collecting

```
gh run list --workflow debug-failures-on-demand.yml --limit 5
gh run watch
gh run download <run-id>
```

Every on-demand run names itself for what it is, so the Actions list is
readable without opening anything:

```
DEBUG (no verdict) on stabilization
DIAGNOSTIC (no verdict) on extend-judge-replay-09-24-2026
Full regression on a1b2c3d
```

Artifacts from these runs are excluded from the durable record. **A debug or
diagnostic run yields no verdict**, because a hand-typed selection is arbitrary
and has no backstop. What a subset costs is the verdict, never the ability to
run.

---

## 6. When Something Refuses

| Exit | Means | Do |
|---|---|---|
| 0 | Ran, and passed | Nothing |
| 1 | Ran, and a test failed | Read the artifact |
| 2 | An argument was wrong | Fix the dispatch inputs |
| **3** | **A precondition failed** | Below |
| 4 | Refused, no verdict computable | Check the ref exists |

**Exit 3 is the one worth understanding.** Preconditions sit above the priority
scale rather than at the top of it. A precondition failure means the graded
layers never executed, the run measured nothing, and no result it produced says
anything about any model.

That is a stronger consequence than a P0 failure, which fails a run that did
measure something.


### 6.1 A skip is not a failure, and the code says whose problem it is

Every `QC_HARNESS_*` code is a **skip**, never a red case. That is the rule and
it is load-bearing: a harness event means our infrastructure produced no
measurement, so recording it as a failure would assert something about a model
nobody asked.

**The code tells you whose defect it is and what to do.** This table is what a
reader of a skipped case actually needs:

| Code | Whose | Retried | What to do |
|---|---|---|---|
| `QC_HARNESS_REQUEST_REJECTED` | Ours | No | The provider refused what we composed. A corpus or adapter defect |
| `QC_HARNESS_AUTH_ERROR` | Ours | No | The credential is missing, wrong or lacks the grant |
| `QC_HARNESS_VERSION_UNAVAILABLE` | Ours | No | The configured model is not callable. **See below** |
| `QC_HARNESS_RATE_LIMIT` | Nobody's | Yes | You asked too often, or the quota is spent. **See below** |
| `QC_HARNESS_PROVIDER_UNAVAILABLE` | Theirs | Yes | The service said it is busy. Wait |
| `QC_HARNESS_GATEWAY_FAILURE` | **The path** | Yes | A proxy, CDN or egress rule failed. **Not the provider** |
| `QC_HARNESS_ENGINE_UNREACHABLE` | **The path** | No | A redirect or connection failure. Check proxy, DNS, VPN |
| `QC_HARNESS_FIXTURE_MISSING` | Ours | No | Nothing recorded yet. Record it, or run live |
| `QC_HARNESS_FIXTURE_STALE` | Ours | No | The question or the instrument moved. Re-record |
| `QC_HARNESS_DEPENDENCY_UNMET` | Ours | No | A foundational case did not hold. Fix that one first |

**The last three rows of the path group are worth separating in your head.** A
gateway failure and an unreachable engine both mean you are not talking to the
engine you addressed, and neither is the provider having a bad day. A corporate
proxy answering with a login page produces one of them, and waiting will not
help.

#### 6.1.1 The level tells you what to act on

Added 2026-09-26. The table above lists codes; **the levels below are why it is
shaped that way**, and a remedy always acts at one level:

| Level | What you change | Codes |
|---|---|---|
| Ours | The request we compose | `QC_HARNESS_REQUEST_REJECTED` |
| Connection | The socket. The harness already reconnects per retry | (transport, before a status) |
| Path | Proxy, DNS, egress, endpoint | `QC_HARNESS_GATEWAY_FAILURE`, `QC_HARNESS_ENGINE_UNREACHABLE` |
| Service | Nothing. Wait | `QC_HARNESS_PROVIDER_UNAVAILABLE` |
| Environmental | The account, the credential, the configuration | `QC_HARNESS_RATE_LIMIT`, `QC_HARNESS_AUTH_ERROR`, `QC_HARNESS_VERSION_UNAVAILABLE` |

**Reading the level first saves acting on the wrong thing.** A rate limit and a
wedged socket both stop a request and share nothing else: one is answered by
waiting or raising a tier, the other by discarding a socket. The harness already
opens a fresh connection for every retry attempt, so **if you are still seeing
failures after retries, the level is not the connection.**

### 6.2 Reading a rate limit, which has three meanings

`QC_HARNESS_RATE_LIMIT` is a `429`, and a provider uses that one status for a
per-minute rate, an exhausted allowance for the day or month, and an account with
no credit. **They read identically at the status, and only the first clears while
you wait.**

| What you see | Likely | Remedy |
|---|---|---|
| Some pass, others skip, spread through the run | A per-minute rate | Widen `spacing_sec` |
| Early cases pass, then everything skips | The plan quota is spent | Wait for the reset |
| **Nothing has ever passed on this engine** | **No credit on the account** | Add credit |

**Read the provider's message; it distinguishes them and the remedies do not
overlap.** Widening the pace against a spent quota achieves nothing, and this
project proved that in one run: 4.0s to 6.0s produced zero additional
observations.

**An authenticated key is not a funded one.** A credential can list every model
a vendor offers and call none of them, and a subscription to the vendor's
consumer product funds nothing on its API.

#### The harness now reads the message, because the message is structured

**An earlier version of this section said distinguishing the two would mean
parsing a provider's prose, and declined to.** That was wrong about the shape of
the data. The period is not in prose; it is in the quota identifier, which names
it:

```
quotaId    : GenerateRequestsPerDayPerProjectPerModel-FreeTier
quotaValue : 20
retryDelay : 52s
```

So the adapter reads it, and a case whose quota period is spent **stops after one
attempt instead of three**. The encounter is still counted and the skip still
carries `QC_HARNESS_RATE_LIMIT`; what changes is that the run no longer spends
two further attempts on a question already answered.

**Ignore `retryDelay` when the period is a day.** The 52 seconds above sits
beside a quota that resets once daily. Nothing in the harness reads that field,
and nothing should: honouring it would retry until the day turned.

**An adapter that cannot tell keeps its retries.** Only the vendor knows its own
body shape, so an adapter with no answer returns "unknown", and unknown keeps the
backoff rather than abandoning it. Losing the per-minute recovery in order to
handle the daily one would be the wrong trade.

#### What the free tier actually allows

Measured 2026-09-26 against Gemini:

| | |
|---|---|
| Allowance | **20 requests per day, per model** |
| Three observations per case (A4.1) | ~6 cases per day |
| The security family, 21 cases | 63 requests, so **four days** |

**A recording run that stops making progress is usually this and not a bug.**
`--fill-gaps` is what makes it resumable: each day's run adds what is missing and
leaves what is already recorded alone.

**An authenticated key is not a funded one, and a paid tier removes all of
this.**

### 6.3 A model that is listed and not callable

`QC_HARNESS_VERSION_UNAVAILABLE` is a `404`, and the most confusing cause is a
model the provider **still lists** and no longer serves. `models.list()`
returning a name is not a promise that `generateContent` will accept it: a
model retired for new users appears in one and fails in the other.

The provider's 404 body usually names the replacement. Re-pointing the roster
is a **version change**, so pin the replacement rather than reaching for a
`-latest` alias: the resolved identifier is recorded so a later score change
stays interpretable, and an alias moving under a recorded baseline defeats
that.

---

## 7. Running It Locally

```
pytest -m unit
pytest -m system --mode replay
pytest -k 11141
pylint ingestion/ execution/ evaluation/ cmn/ tests/ --rcfile=.pylintrc
```

Preconditions need no credentials and no network, so they run anywhere. **Gate
1 is blocking for every later gate**, so run pylint before you push rather than
after CI tells you.

A local run yields no verdict, for the same reason a dispatched debug run does
not. Run whatever subset you like.


## 8. Connections, And When To Hold One Open

**You almost certainly do not need this flag.** It is documented so that a run
which needs it can find it, not because a normal run should think about it.

By default each case opens its provider connection and releases it once the
response is captured, so a wedged socket or a provider session gone strange is
scoped to the one case that met it and reports as a single
`QC_HARNESS_*` skip. Shared, the same event would be inherited by every case
that followed.

```
pytest -m sec --engine gemini                      # released per case, the default
pytest -m sec --engine gemini --keep-connection    # held open for reuse
```

**The cost of the default is small because the run is already waiting.** A
handshake is roughly 0.1s against the 4.0s spacing `config/engines.yaml`
configures for `gemini`, which exists because the free tier requires it.

**Reach for `--keep-connection` when that stops being true**, which today means
a provider needing no pacing, or a suite large enough that handshakes stop
being noise. Measure before assuming: the flag trades away per-case isolation,
and a run that keeps a connection and then reports a cluster of unexplained
failures has bought a harder debugging problem than it saved.

It changes no measurement, so it does not cost the run its verdict the way a
selection flag does.

**The judge never shares the candidate's connection, whatever this flag says.**
It dispatches through its own adapter with its own pacing, which is not
configurable and is not meant to be: the two would otherwise spend one
free-tier quota from two uncounted directions.


## 9. Adding An Engine, Or A Second Judge

### 9.1 An engine on a protocol somebody already serves

xAI (Grok), DeepSeek, Mistral, Groq, Together, OpenRouter and Ollama all serve
the **Chat Completions** shape. For any of them, the whole engine is four
values:

```
# execution/adapters/deepseek.py
class DeepSeekAdapter(OpenAICompatibleAdapter):
    ENGINE_NAME = "deepseek"
    DEFAULT_MODEL = "deepseek-chat"
    BASE_URL = "https://api.deepseek.com/v1"
    API_KEY_ENV = "DEEPSEEK_API_KEY"
```

Then three one-line edits:

| File | Add |
|---|---|
| `execution/adapters/registry.py` | the import and `register_adapter(DeepSeekAdapter)` |
| `tests/execution/provider_doubles.py` | a `ADAPTER_DOUBLES` entry reusing the OpenAI builders |
| `config/engines.yaml` | a roster entry with its `spacing_sec` |

**That is all.** No request composition, no normalization, no error mapping and
no judging: those belong to the protocol. The conformance battery enrols the
engine automatically and will fail loudly if anything is missing, which is how
you find out rather than by reading this list carefully.

**`BASE_URL` is the only field that routes a request.** Omit it and the engine
reaches OpenAI holding your key for somebody else, which surfaces as an
authentication error naming the wrong vendor and sends you to the wrong
dashboard. `MQC_EXE_UNI_10281` guards it.

**The credential is a variable name, never a value.** `API_KEY_ENV` says where
to look; nothing reads it until a client is constructed, and no configuration
file ever holds a secret.

### 9.2 An engine on a protocol nobody serves yet

Write a full adapter against `ProviderAdapter`, as `gemini.py` and `claude.py`
do. You owe the seven interface methods plus `compose_judgement` and
`parse_judgement` **if you declare `structured_output`**. Declaring it and not
implementing it is refused by `MQC_EXE_UNI_10278`; declaring it false is
allowed and costs the engine only the judge role.

If a second engine ever arrives on your new protocol, lift the shared part out
the way `openai_protocol.py` was lifted, rather than copying the module.

### 9.3 Which engines can judge

```
python -c "from execution.adapters.registry import engines_for_role, JUDGE_ROLE; print(engines_for_role(JUDGE_ROLE))"
```

Derived from the registry and the declared capability, never from a list. An
engine you add arrives in both roles or in neither.

### 9.4 Wiring a second judge

```
judge:
  engine: gemini      # decides the verdict
  also:
    - claude          # scored, recorded, never gates
```

**The primary decides and the rest measure.** Every threshold keeps the meaning
it has with one judge, and adding a judge cannot turn a green suite red. Each
additional judge scores the same observation and the result records the signed
difference:

```
score: 4.2
divergence:
  claude: +0.6
```

A positive number means that judge was kinder than the primary. **Zero is
recorded** and means they agreed; a judge that could not be reached is
**omitted**, because that is a missing measurement rather than agreement.

**It costs quota.** Each panel member multiplies judge requests against the
same free-tier ceiling, so nothing runs unless `also` names it. Use
`--judge-panel off` to suppress the panel for one run without editing the
roster.

**Naming the primary in `also` does nothing**, deliberately: it would compare a
judge with itself and record a guaranteed zero that reads exactly like
agreement. It is dropped, and `MQC_CMN_UNI_11167` guards that.
