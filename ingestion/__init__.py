# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Ingestion, which turns task and rule files into the validated cases a run executes.

Created: 2026-09-26
Last updated: 2026-10-21

This package holds the schema records, the loaders, the ingest injection
screen, the referential integrity checks and case building. It is Tier 1, the
first of the harness's three tiers, and it uses no network and knows nothing
about engines, so its output is the same whichever model is then tested.

Specified by ``docs/design/tier1_ingestion.md``.
"""
