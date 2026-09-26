<!--
SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
SPDX-License-Identifier: Apache-2.0
-->
# Git Worktree & Environment Isolation Rules

## 1. Context Boundaries
* Every feature branch or experimental evaluation pipeline developed in a separate Git worktree must remain self-contained.
* Do not import modules across worktrees or reference uncommitted files outside the active working directory tree.
* Tier boundaries from `../rules/framework-rules.md` hold inside a worktree exactly as they do on `main`. A worktree is not a place to shortcut the Ingestion / Execution / Evaluation separation.

## 2. Environment Safeguards
* Never expose API keys, credentials, or token secrets within worktrees or prompt logs.
* Provider credentials are read from the environment at runtime only. They are never written into design documents, test fixtures, golden rule files, or `CLAUDE_LOG.md`.
* Ensure local environment configurations (`.env`) are listed in `.gitignore` across all active worktrees.

## 3. Version Control Safety
* Worktree creation, branch switching, commits, and pushes are user-executed operations. The assistant does not run them.
* Each worktree carries its own `reports/` output directory. Never publish artifacts from one worktree under another worktree's artifact name, as this corrupts the downstream history for this repository.
