<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->

# Active Focus

**What is being worked on in this repository right now, and what is waiting.**
Added 2026-11-01. One item per row, each naming what must hold before it is
done, so a session resuming after a reset picks up the work rather than
rediscovering it.

**It is the shortest-lived of the three tracked records, and the division is by
time.**

| Document | Answers |
|---|---|
| `README.md`, `DESIGN.md`, `docs/design/*`, the test plan and `rtm_harness.csv` | The architecture, the requirements and their traces |
| `CLAUDE.md` | The directive router, the core directives, the boundaries |
| `CLAUDE_TASK.md` | **What is active now.** Entries are added, worked and removed |
| `CLAUDE_LOG.md` | The permanent development trail: what was found, what it broke, what the injection showed |

**An entry leaves this file when it is done, and its record goes to
`CLAUDE_LOG.md`.** Nothing is kept here for history, so a reader asking what
happened reads the log and a reader asking what is open reads this.

**`docs/harness_open_questions.md` is not this file.** That holds decisions
waiting on a person and blockers only the account owner can clear; this holds
work in progress. An item moves from here to there when it stops being work and
becomes a question.


## In progress

Nothing. The last item closed on 2026-11-01, when `stale_judgements` began
reporting a judgement that scores a response its own recording no longer
holds, and `MQC_CAS_UNI_115799` began calling it against the shipped
fixtures.


## Waiting

| Item | Waiting on |
|---|---|
| The quarantine trigger at `cmn/verdict.py` is unreachable | Nothing. The project owner ruled it is not to be fixed, and it is recorded here so it is not rediscovered as a finding |
