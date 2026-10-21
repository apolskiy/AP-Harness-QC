# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The cross-cutting package, code that every tier and the test run share.

Created: 2026-09-26
Last updated: 2026-10-21

This package holds what belongs to no single tier: configuration loading, the
option registry and the pytest hooks behind the CLI, the observation record and
the run verdict computed from it, result metadata and reporting, and the
traceability and standards checks the precondition suite runs against both
repositories.

Ingestion, execution and evaluation import from here, and nothing here imports
from a tier, so a helper placed in this package is reachable from anywhere
without crossing a tier boundary.

Specified by ``docs/design/cmn_verdict_and_cli.md``.
"""
