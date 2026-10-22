# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Support code for the flag citation cases, the documents they plant.

Created: 2026-10-22
Last updated: 2026-10-22

This file contains ``write_document``, which writes one markdown file under a
constructed tree's ``docs`` directory, where
``cmn.document_citations.live_documents`` will find it.

It is imported by ``mqc_uni_flag_citations.py`` in the ``unit`` precondition
gate, and is not collected itself, as its name carries no ``mqc_`` prefix.

Specified by ``docs/design/cmn_verdict_and_cli.md`` section 7.1.0.4.
"""

from pathlib import Path


def write_document(root: Path, name: str, body: str) -> None:
    """Write one document under the tree's ``docs`` directory.

    Args:
        root (Path): The constructed repository root.
        name (str): The document's filename.
        body (str): Its content.

    Returns:
        None
    """
    folder = root / "docs"
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(body, encoding="utf-8")
