# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit precondition for whether a document's name says where it belongs.

Covers `MQC_CMN_UNI_112346`, inventoried in
``docs/design/cmn_verdict_and_cli.md`` section 10.

**An editor tab shows a filename rather than a checkout.** Two repositories
held a `running_jobs.md` and a `document_register.md` each, and a change made
in the wrong one parses, lints and commits.

A failure here is **not a model finding**, so the module carries no priority
marker, per ``framework-rules.md`` section 3.3.
"""

from pathlib import Path
from typing import Final

import pytest

from cmn.document_naming import (
    repository_token,
    root_conventions,
    undifferentiated_documents,
)

pytestmark = pytest.mark.unit

_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

# EXEMPT, AND EACH FOR A STATED REASON. The rule is satisfied by a name being
# unmistakable rather than by a prefix for its own sake (`code-style.md`
# section 7.2), so a document naming a harness tier or a harness module names
# this repository already.
#
# **A generic name is not exempt however old it is.** Any repository carrying
# tests has a taxonomy, a pipeline, an extensibility standard and project
# phases, so those six took the token on 2026-10-08 rather than waiting for the
# collision: the project owner's instruction was that names which can criss
# cross are a problem before they do.
_EXEMPT: Final[frozenset[str]] = frozenset({
    "tier1_ingestion.md",
    "tier2_execution.md",
    "tier3_evaluation.md",
    "cmn_verdict_and_cli.md",
})


class TestMQCDocumentNaming:
    """Every document under `docs` says which repository it belongs to."""

    def MQC_CMN_UNI_112346_a_document_naming_no_repository_is_reported(self) -> None:
        """A filename carries the repository's token, or an exemption's reason.

        **The four exemptions name a harness tier or a harness module**, so a
        reader with one open knows where they are without a prefix. Nothing
        else is exempt: a generic name is a collision waiting to happen, which
        is why `test_taxonomy.md`, `ci_pipeline.md`,
        `extensibility_standard.md`, `phase0_project_ambiguities.md`,
        `OPEN_QUESTIONS.md` and `problems_found.md` took the token.

        Design: ``.claude/rules/code-style.md`` section 7.2.

        Returns:
            None
        """
        assert repository_token(_ROOT) == "harness", (
            "the repository root carries no token, so no document name can be "
            "checked against one"
        )

        problems = undifferentiated_documents(_ROOT, _EXEMPT)
        assert not problems, (
            f"{len(problems)} document name(s) do not say which repository "
            f"they belong to, so an open editor tab does not either: "
            + "; ".join(problems)
        )

        # THE EXEMPTIONS ARE SPENT, NOT BANKED. An entry naming a document that
        # no longer exists is a permission nobody can audit, and the list is
        # meant to shrink.
        present = {path.name for path in (_ROOT / "docs").rglob("*.md")}
        stale = sorted(_EXEMPT - present)
        assert not stale, (
            f"{len(stale)} exemption(s) name a document this repository does "
            f"not carry: {', '.join(stale)}"
        )

        # AND THE CHECK IS NOT VACUOUS. A root with no token is refused rather
        # than passed, because passing would report agreement having read
        # nothing.
        with pytest.raises(ValueError):
            undifferentiated_documents(_ROOT.parent)

        # THE ROOT CONVENTIONS ARE PINNED, so each addition is one more file
        # whose name says nothing about its checkout.
        assert root_conventions() == frozenset({
            "README.md", "DESIGN.md", "CHANGELOG.md", "CLAUDE.md",
            "CLAUDE_LOG.md", "LICENSE", "NOTICE",
        })
