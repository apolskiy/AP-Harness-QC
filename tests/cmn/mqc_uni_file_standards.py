# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""What every file in the repository must look like.

Covers ``MQC_CMN_UNI_11111`` through ``11113`` and ``11140``, inventoried in
``docs/design/cmn_verdict_and_cli.md`` sections 10.6, 10.7 and 10.20.

**Pylint checks none of these.** It has no opinion on whether an annotation is
present, on which annotation semantics a module selects, or on whether a file
says what licence it carries. Each rule stood in ``code-style.md`` while being
enforced by nothing.

**Split from the metadata module on 2026-09-24**, when that module crossed the
thousand line ceiling. The split follows the subject: these are about files,
and the rest of that module is about what a result record carries.

The checkers live in ``cmn.code_standards`` and take a root and a licence, so
the case repository runs the identical implementation against MIT.

A failure here is our defect, so the module carries no priority marker.
"""

from pathlib import Path

import pytest

from cmn.code_standards import (
    annotation_gaps,
    encoding_gaps,
    future_annotation_imports,
    header_problems,
    markup_header_problems,
    markup_sources,
    runbook_problems,
)

pytestmark = pytest.mark.unit

# The identifier this repository's files must declare. The case repository runs
# the same checks against MIT, which is the whole point of naming it rather
# than accepting any SPDX tag.
_REPOSITORY_LICENCE = "Apache-2.0"


class TestMQCAnnotationCoverage:
    """The annotation rule, enforced rather than stated."""

    def MQC_CMN_UNI_11111_every_callable_carries_parameter_and_return_hints(self) -> None:
        """Pylint does not check annotation presence, so nothing else does.

        The rule has stood in `code-style.md` section 2 since the project
        began, and an audit found production code at zero gaps and test code at
        597. A rule nothing checks is a convention.

        **Test code is held to it identically.** A test callable is a function
        like any other, and its fixtures are its parameters.

        Returns:
            None
        """
        gaps = annotation_gaps(Path(__file__).resolve().parents[2])
        assert not gaps, f"{len(gaps)} annotation gaps: " + "; ".join(gaps[:10])

    def MQC_CMN_UNI_11112_pep_563_future_annotations_import_is_rejected(self) -> None:
        """Laziness comes from the interpreter, not from stringizing.

        Python 3.14 implements PEP 649, so annotations are already evaluated
        lazily and the import buys nothing. What it does instead is select PEP
        563, which turns every annotation into a string and removes
        ``annotationlib.Format.VALUE``.

        On a project built from frozen dataclasses that read their fields at
        class creation, that trades a working mechanism for a weaker one to
        obtain something already present.

        Returns:
            None
        """
        # Parsed, not matched as a substring. This very file names the import in
        # a string literal in order to describe what it rejects, and a substring
        # check reports itself. That is the same over-reporting that trains a
        # check away on its second run.
        offending = future_annotation_imports(Path(__file__).resolve().parents[2])
        assert not offending, (
            "PEP 563 stringized annotations are prohibited, and 3.14 already "
            f"defers evaluation without them: {', '.join(offending)}"
        )


class TestMQCAuthorshipHeader:
    """Every file says what it is, even separated from its repository."""

    def MQC_CMN_UNI_11113_every_python_file_carries_its_spdx_header(self) -> None:
        """Presence, position and the correct licence identifier.

        **The split made this a per-file question.** Code from this repository
        now installs into another one under a different licence, so a file
        separated from its repository has to carry its own answer.

        **Position is checked, not only presence.** The header sits above the
        module docstring, because a docstring must remain the first statement or
        ``__doc__`` is empty, and this project reads module docstrings as
        specification prose. A header pasted inside one would satisfy a presence
        check while silently emptying the documentation.

        Returns:
            None
        """
        missing = header_problems(
            Path(__file__).resolve().parents[2], _REPOSITORY_LICENCE
        )
        assert not missing, f"{len(missing)} header problems: " + "; ".join(missing[:8])


class TestMQCMarkupHeaders:
    """Documents and data say what they are, like the code does."""

    def MQC_CMN_UNI_11140_a_document_or_data_file_without_an_spdx_header_is_reported(
        self,
    ) -> None:
        """Fifty-four files accumulated without one, and nothing said so.

        `code-style.md` section 1.1 justified the Python headers partly because
        licence scanners parse the tags. **REUSE requires every file to carry
        them**, so while markdown and YAML were bare that claim held for none
        of them.

        **A separate case from ``11113`` rather than a widening of it.** A
        Python file must carry the header above its module docstring, because a
        docstring must remain the first statement or ``__doc__`` is empty.
        Markdown and YAML have no such constraint, so the two checks assert
        different things.

        Returns:
            None
        """
        root = Path(__file__).resolve().parents[2]
        problems = markup_header_problems(root, _REPOSITORY_LICENCE)

        assert markup_sources(root), "no documents or data files were read"
        assert not problems, (
            f"{len(problems)} header problems: " + "; ".join(problems[:8])
        )


class TestMQCRunbook:
    """The operating procedure, checked against the workflows it describes."""

    def MQC_CMN_UNI_11143_a_runbook_command_naming_an_undeclared_input_is_reported(
        self,
    ) -> None:
        """A documented dispatch that GitHub rejects is worse than none.

        **The failure is silent at authoring time and lands on the reader.** A
        dispatch naming an input the workflow does not declare is rejected with
        a message about the input, and somebody following the documented
        procedure concludes the procedure is broken rather than the page.

        The runbook exists so that starting a run costs nobody a design read,
        and a runbook that does not work costs them that read plus the time
        spent trusting it.

        Returns:
            None
        """
        problems = runbook_problems(Path(__file__).resolve().parents[2])
        assert not problems, (
            "the runbook documents a dispatch that would be rejected, so the "
            "procedure fails for whoever follows it: " + "; ".join(problems)
        )


class TestMQCEncodingDeclared:
    """The rule that fails more quietly than any other here."""

    def MQC_CMN_UNI_11157_a_file_open_declaring_no_encoding_is_reported(
        self, tmp_path: Path
    ) -> None:
        """A missing encoding raises nothing and changes the value.

        It reads ``cp1252`` on Windows and ``utf-8`` on Linux, so the same
        commit produces different values on the two platforms CI runs, and
        **both runs report success**. Every other rule in
        ``code_standards`` guards something that is merely invisible; this one
        guards something that is invisible and platform dependent.

        Args:
            tmp_path (Path): A directory for the positive control.

        Returns:
            None
        """
        gaps = encoding_gaps(Path(__file__).resolve().parents[2])

        assert not gaps, (
            "a file is read or written without an encoding, so this commit "
            "yields different values on Windows and Linux: " + "; ".join(gaps)
        )

        # THE POSITIVE CONTROL, and this case is vacuous without it. Asserting
        # "no gaps found" cannot tell a clean repository from a checker that
        # stopped looking, which is exactly what injecting a narrowed
        # _ENCODED_CALLS demonstrated: the repository stayed clean, the case
        # stayed green, and the check had gone blind.
        probe = tmp_path / "mqc_probe.py"
        probe.write_text(
            "from pathlib import Path\n"
            "def read(path):\n"
            "    return path.read_text()\n"
            "def write(path):\n"
            "    return path.write_text('x')\n"
            "def plain(path):\n"
            "    return open(path).read()\n"
            "def binary(path):\n"
            "    return open(path, 'rb').read()\n"
            "def declared(path):\n"
            "    return path.read_text(encoding='utf-8')\n",
            encoding="utf-8",
        )
        reported = encoding_gaps(tmp_path)

        # ALL THREE CALL KINDS, because a checker covering two of them reports
        # nothing on the third and looks identical from here.
        assert len(reported) == 3, (
            f"the checker found {len(reported)} of three bare calls, so it is "
            f"blind to a kind: {reported}"
        )
        # AND NEITHER CORRECT CALL. A binary open carries no encoding and must
        # not claim one; a declared read is simply right.
        assert not any("binary" in entry or "declared" in entry for entry in reported)
