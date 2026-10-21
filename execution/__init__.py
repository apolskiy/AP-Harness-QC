# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Execution, which sends each case to a model and records the response it returns.

Created: 2026-09-26
Last updated: 2026-10-21

This package holds the provider adapters, dispatch with its pacing and replay
routing, the fixture store, response normalization, model version preflight
and the judge's own channel. It is Tier 2, between ingestion and evaluation,
and it captures tool-call intent without executing it.

Specified by ``docs/design/tier2_execution.md``.
"""
