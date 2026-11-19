# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Planted workflows for the report publication cases, and their writer.

Created: 2026-11-19
Last updated: 2026-11-19

This file contains ``GENERATE``, the steps of a job that renders the report
with its trend and uploads the site; ``DEPLOY``, the step that deploys it;
``PAGES_PERMISSIONS``, the permission lines the deploying job declares; and
``plant_workflow``, which writes a workflow under a planted root and returns
that root.

The cases in ``mqc_uni_report_publication.py`` build one workflow per defect
from these and pass the root to ``report_publication_gaps``.

Specified by ``docs/design/harness_ci_pipeline.md`` section 7.4.6.
"""

from pathlib import Path
from typing import Final

GENERATE: Final[tuple[str, ...]] = (
    "    steps:",
    "      - name: Generate the report",
    "        run: |",
    "          curl --output reports/allure-results/history/history.json"
    " \"$base/history/history.json\"",
    "          allure generate reports/allure-results -o allure-report",
    "      - uses: actions/upload-pages-artifact@v5",
    "        with:",
    "          path: allure-report",
)
DEPLOY: Final[tuple[str, ...]] = (
    "    steps:",
    "      - uses: actions/deploy-pages@v5",
)
PAGES_PERMISSIONS: Final[tuple[str, ...]] = (
    "    permissions:",
    "      pages: write",
    "      id-token: write",
)


def plant_workflow(root: Path, *lines: str) -> Path:
    """Write ``gate-on-change.yml`` under a planted root, triggered by a push.

    Args:
        root (Path): The planted repository root.
        *lines (str): The ``jobs:`` block's lines, each already indented.

    Returns:
        Path: ``root``.
    """
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "gate-on-change.yml").write_text(
        "\n".join(["name: gate-on-change", "on:", "  push:", "jobs:", *lines]) + "\n",
        encoding="utf-8",
    )
    return root
