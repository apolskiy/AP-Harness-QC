# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""What every file in the repository must look like.

Covers ``MQC_CMN_UNI_112500`` through ``112502`` and ``112503``, inventoried in
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

import re
from datetime import date
from pathlib import Path

import pytest
import yaml

from tools.consumer_regression import harness_faults
from cmn.workflow_standards import (
    disagreeing_pylint_invocations,
    duplicate_yaml_keys,
    pylint_invocations,
)
from cmn.module_size import runway_problems
from cmn.case_module_standards import (
    extraction_problems,
    unbounded_subprocess_calls,
)
from cmn.code_standards import (
    document_register_problems,
    registered_documents,
    artifact_mandate_gaps,
    flag_coverage_problems,
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


# A `python <path>.py` invocation inside a `run:` block. A literal path only: an
# expression is not known until the run, and `-m module` is not a path.
_WORKFLOW_SCRIPT = re.compile(r"\bpython[0-9.]*\s+(?!-)([A-Za-z0-9_./-]+\.py)\b")


def _own_checkout_path(job: dict) -> str:
    """Return where a job checks this repository out, or empty for the root.

    **This repository's checkout is the one naming no `repository`.** A step
    that names one is fetching somebody else, and where that lands says nothing
    about where our own files are.

    Args:
        job (dict): One job of a parsed workflow.

    Returns:
        str: The checkout path, or empty when the job uses the workspace root.
    """
    for step in job.get("steps") or []:
        if not isinstance(step, dict):
            continue
        if not str(step.get("uses") or "").startswith("actions/checkout"):
            continue
        settings = step.get("with") or {}
        if settings.get("repository"):
            continue
        return str(settings.get("path") or "")
    return ""




class TestMQCAnnotationCoverage:
    """The annotation rule, enforced rather than stated."""

    def MQC_CMN_UNI_112500_every_callable_carries_parameter_and_return_hints(self) -> None:
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

    def MQC_CMN_UNI_112501_pep_563_future_annotations_import_is_rejected(self) -> None:
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

    def MQC_CMN_UNI_112502_every_python_file_carries_its_spdx_header(self) -> None:
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

    def MQC_CMN_UNI_112503_a_document_or_data_file_without_an_spdx_header_is_reported(
        self,
    ) -> None:
        """Fifty-four files accumulated without one, and nothing said so.

        `code-style.md` section 1.1 justified the Python headers partly because
        licence scanners parse the tags. **REUSE requires every file to carry
        them**, so while markdown and YAML were bare that claim held for none
        of them.

        **A separate case from ``112502`` rather than a widening of it.** A
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


    def MQC_CMN_UNI_112521_a_generated_file_in_a_skipped_tree_is_not_read(
        self, tmp_path: Path
    ) -> None:
        """A tool cache is not a document this repository authors.

        **`112503` caught this and only by accident.** `pytest` writes
        `.pytest_cache/README.md`, the scan read it as a document, and it
        passed locally because an earlier header pass had written a header into
        the local copy. A fresh checkout had no such file, so CI failed on a
        commit that was green here, and the check was measuring the leftovers of
        its own remediation.

        **This case does not depend on a cache being dirty.** It builds the
        condition, which is the difference between a check that happens to
        notice and one that cannot miss: `112503` only fails when the working
        tree's cache is clean, and a developer who has ever run the header pass
        does not have one.

        Args:
            tmp_path (Path): A tree to plant the generated file in.

        Returns:
            None
        """
        authored = tmp_path / "docs" / "real.md"
        authored.parent.mkdir(parents=True)
        authored.write_text(
            "<!--\nSPDX-License-Identifier: Apache-2.0\n-->\n", encoding="utf-8"
        )

        for tree in (".pytest_cache", "__pycache__", "reports"):
            generated = tmp_path / tree / "README.md"
            generated.parent.mkdir(parents=True)
            generated.write_text(
                "# generated, and nobody signed it #\n", encoding="utf-8"
            )

        found = markup_sources(tmp_path)

        assert authored in found, "the authored document was not read"
        # THE AUTHORED FILE AND NOTHING ELSE. An earlier version of this asserted
        # only that the authored file appeared, which every generated file also
        # satisfied: it passed with the exclusion removed, which is the vacuous
        # shape this project checks for by injection.
        assert found == [authored], (
            f"a generated file was read as an authored one: "
            f"{[str(source.relative_to(tmp_path)) for source in found]}"
        )

class TestMQCArtifactContract:
    """The downstream artifact contract, checked against what the workflows run."""

    def MQC_CMN_UNI_112525_a_workflow_emitting_one_mandated_artifact_is_reported(
        self,
    ) -> None:
        """Every workflow invocation writing an artifact writes both of them.

        ``testing-standards.md`` section 5 mandates JUnit XML and Allure raw
        results together, and they are read by different people: JUnit for
        triaging a failure, Allure for the report a release is judged from. An
        invocation naming ``--out-dir`` satisfies both, since the flag derives
        each destination.

        **This repository's own workflows only.** The consumer owns its
        workflows, so the scanner is shared and
        ``MQC_CAS_UNI_115708`` calls it with the other root.

        Design: ``cmn_verdict_and_cli.md`` section 7.1.0.3.

        Returns:
            None
        """
        gaps = artifact_mandate_gaps(Path(__file__).resolve().parents[2])

        assert not gaps, (
            "workflow invocations emit one of the two mandated artifacts, so "
            "the run produces no report to judge readiness from: "
            + "; ".join(gaps)
        )


class TestMQCRunbook:
    """The operating procedure, checked against the workflows it describes."""

    def MQC_CMN_UNI_112524_a_workflow_step_running_an_absent_script_is_reported(
        self,
    ) -> None:
        """Every script a workflow step runs resolves where the step runs.

        A step with no ``working-directory`` runs from the workspace root. Where
        its job checks this repository out under a path, our own files are
        reached through that path, so a bare ``tools/x.py`` resolves to nothing
        even though it exists in the repository.

        That is the shape of the defect: the path is valid relative to the
        repository and invalid relative to the step, so resolving it against the
        repository reports success.

        Steps carrying a ``working-directory`` are skipped, their frame being
        that directory rather than the workspace.

        Design: ``ci_pipeline.md`` section 3B.3.2.

        Returns:
            None
        """
        root = Path(__file__).resolve().parents[2]
        workflows = sorted((root / ".github" / "workflows").glob("*.yml"))
        assert workflows, "no workflow was read"

        unresolved: list[str] = []
        examined = 0
        for workflow in workflows:
            parsed = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
            for name, job in (parsed.get("jobs") or {}).items():
                if not isinstance(job, dict):
                    continue
                prefix = _own_checkout_path(job)
                for step in job.get("steps") or []:
                    if not isinstance(step, dict) or step.get("working-directory"):
                        continue
                    script_block = str(step.get("run") or "")
                    if "${{" in script_block:
                        continue
                    for found in _WORKFLOW_SCRIPT.finditer(script_block):
                        script = found.group(1)
                        examined += 1
                        wanted = (
                            script[len(prefix) + 1:]
                            if prefix and script.startswith(f"{prefix}/")
                            else script if not prefix else None
                        )
                        if wanted is None or not (root / wanted).is_file():
                            unresolved.append(
                                f"{workflow.name} job {name!r} runs {script!r}"
                                + (f", expected under {prefix!r}" if prefix else "")
                            )

        assert examined, "no workflow step invoked a literal script"

        assert not unresolved, (
            f"{len(unresolved)} workflow step(s) run a script that does not "
            f"resolve where the step runs, so the step cannot start and its job "
            f"can report success while the step evaluated nothing: {unresolved}"
        )

    def MQC_CMN_UNI_112504_a_runbook_command_naming_an_undeclared_input_is_reported(
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



class TestMQCCaseModuleContents:
    """What a collected test module is allowed to define."""

    def MQC_CMN_UNI_112328_a_case_module_holding_support_code_is_reported(
        self,
    ) -> None:
        """A collected test module holds cases, not the library supporting them.

        **The convention existed and was unwritten**, which is what it cost:
        ``repository_root`` stood four times, byte-identical, once public in
        ``graded_support`` and once privately in each of three case modules. A
        helper nobody owned was cheaper to rewrite than to find.

        **``pytest.ini`` already draws the boundary** with
        ``python_files = mqc_*.py``, so a module outside that glob is support by
        construction. This asserts the other half: that a module inside it holds
        no support.

        **Fixtures are not support.** A ``@pytest.fixture`` is wiring for one
        module's cases, bound to them by name, and moving it would make the
        cases harder to read for a tidier line count.

        **The backlog is declared, not exempted.** Modules predating the rule
        are named in ``config/support_extraction.yaml`` with a reason and an
        expiry, and an expired entry fails this. The list shrinks and never
        grows, because anything undeclared fails here on the day it is written.

        Design: ``test_taxonomy.md`` section 13.

        Returns:
            None
        """
        root = Path(__file__).resolve().parents[2]
        problems = extraction_problems(
            root / "tests", root, root / "config" / "support_extraction.yaml",
            date.today(),
        )
        assert not problems, (
            f"{len(problems)} case module(s) hold support code that belongs in "
            f"a sibling module, or carry a lapsed declaration: "
            + "; ".join(problems)
        )


class TestMQCModuleRunway:
    """How close a module may get to the ceiling before it splits."""

    def MQC_CMN_UNI_112331_a_module_at_the_runway_ceiling_is_reported(
        self,
    ) -> None:
        """No module sits at the runway ceiling without a declared reason.

        **The hard ceiling fires at the worst moment and this one does not.**
        A module at 998 lines fails the build on a prose edit; a module at nine
        hundred is reported here, where the next author sees it before adding
        anything.

        **The margin is for prose, not for more cases.** A case that pushes a
        module past the ceiling moves out with its subject, which is cheap now
        that a case module holds only cases.

        Design: ``code-style.md`` section 5.1.

        Returns:
            None
        """
        root = Path(__file__).resolve().parents[2]
        problems = runway_problems(
            root, root / "config" / "module_runway.yaml", date.today()
        )
        assert not problems, (
            f"{len(problems)} module(s) are at the runway ceiling without a "
            f"declared reason, or carry a lapsed declaration: "
            + "; ".join(problems)
        )


class TestMQCBoundedSubprocesses:
    """What a case is allowed to wait for, and for how long."""

    def MQC_CMN_UNI_112329_a_subprocess_without_a_timeout_is_reported(
        self,
    ) -> None:
        """No subprocess invocation here waits without a bound.

        **A hang is the worst failure shape available.** A crash names itself;
        a hang names nothing, arrives after the longest possible delay, and
        presents as an environmental fault on whichever platform stalled. One
        cancelled a Windows job 22 minutes into a run that reported `failure`
        with no failing job and no log, while Ubuntu passed.

        **Six calls existed and none carried a timeout.** Five spawned a nested
        pytest; the sixth asked git. The case repository had a seventh, and it
        was the one that mattered most: `git ls-remote` over HTTPS, in the
        resolve job of every gate there.

        **No local run could have found this.** Those cases take 0.6s to 3.4s
        here. The defect was never that something hung; it was that nothing
        bounded how long it could.

        **The keyword is checked, not the value.** Whether 300s is right is a
        judgement; whether a bound exists is not, and only the second is
        mechanical.

        Design: ``test_taxonomy.md`` section 14.

        Returns:
            None
        """
        problems = unbounded_subprocess_calls(
            Path(__file__).resolve().parents[2]
        )
        assert not problems, (
            f"{len(problems)} subprocess invocation(s) carry no timeout, so a "
            f"child that stalls blocks until a runner cancels the job: "
            + "; ".join(problems)
        )


class TestMQCDocumentRegister:
    """The list a documentation review works through, checked against the tree."""

    def MQC_CMN_UNI_112255_a_document_outside_the_register_is_reported(
        self,
    ) -> None:
        """Every tracked document is registered, and every registered path resolves.

        **A reading order is not an inventory.** `DESIGN.md` section 3 named
        the document that fell behind for the whole time it was falling behind:
        that table says what to read first, and a review needs to know what
        exists. Two tracked documents were in no list at all and seven were
        covered only by the directory they sit in.

        **Both directions, for two different failures.** A tracked document the
        register does not name is one a review never reaches; a path the
        register names and the repository does not track is a citation that
        will not resolve for the reader following it.

        **Both directions read git rather than the filesystem.** A walk would
        find a generated `.pytest_cache/README.md` and need a denylist that
        grows, and asking whether a named path merely exists asks a question
        only the authoring machine can answer: it passes there and fails in
        every clone, which is how this case first went red in CI. A bare
        filename is a paired-repository citation and resolves elsewhere.

        Design: ``test_taxonomy.md`` section 12.

        Returns:
            None
        """
        root = Path(__file__).resolve().parents[2]
        register = root / "docs" / "document_register.md"

        assert register.is_file(), (
            "the register is absent, so nothing lists what a documentation "
            "review has to work through"
        )
        problems = document_register_problems(root, register)
        assert not problems, (
            "the register and the repository disagree, so a document would go "
            "unreviewed or a citation would not resolve: " + "; ".join(problems)
        )

        # THE READER FINDS ROWS, which is what a check that passed by reading
        # nothing would not. Section 12.2.
        named = registered_documents(register)
        assert len(named) > 25, (
            f"the register yielded only {len(named)} documents, so the row "
            f"pattern no longer matches the register it is checking"
        )
        assert "docs/document_register.md" in named, (
            "the register does not name itself, so adding it was not subject "
            "to the rule it introduces"
        )


class TestMQCEncodingDeclared:
    """The rule that fails more quietly than any other here."""

    def MQC_CMN_UNI_112522_a_registered_flag_no_case_names_is_reported(self) -> None:
        """Two flags were declared, documented and proved by nothing.

        `--max-spend` accepted a ceiling that could not stop a request, and
        `--priority` named a band and ran every band. Neither failed: both were
        read into the invocation record by `configure_invocation`, which reads
        the whole registry generically, so "is it read" was true of both and
        distinguished nothing.

        **Naming a flag in a case is what this asserts**, which is weaker than
        proving the flag works and is the strongest thing available
        structurally. It moves an absence from silent to arguable; whether the
        case is vacuous is settled by injection.

        **Only the harness share.** The registry is shared and the test trees
        are not: this repository must not read the case repository, and the
        installed wheel ships no tests. `config/flag_coverage.yaml` says who
        owns each flag and each side asserts its own.

        **A gap expires.** Nine flags are declared gaps as this is written,
        each with a reason and a date, because a list without an expiry is
        where unproven flags go to be forgotten.

        Returns:
            None
        """
        root = Path(__file__).resolve().parents[2]
        problems = flag_coverage_problems(
            root, "harness", root / "config" / "flag_coverage.yaml", date.today()
        )

        assert not problems, (
            f"{len(problems)} flag coverage problem(s): {'; '.join(problems)}"
        )

    def MQC_CMN_UNI_112523_a_consumer_run_fails_this_job_only_on_our_codes(
        self, tmp_path: Path
    ) -> None:
        """The regression ran the consumer's preconditions and stopped there.

        Three harness defects reached the case repository on 2026-09-28 and two
        broke the graded path, which this regression did not run: an
        `observation_index` that collapsed three judgements into one file, and
        an engine roster read by directory adjacency. Both surfaced only when
        the consumer's own gate went red after a later push, attributing the
        failure to whoever pushed the consumer.

        **A model finding must not fail this job.** The consumer carries two,
        and a harness regression red because the model overstates a figure
        would be reporting the wrong subject, permanently, for something no
        harness change can fix.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        model_only = tmp_path / "model.xml"
        model_only.write_text(
            "<testsuites><testsuite>"
            '<testcase name="MQC_EVL_EVAL_134205_x"><failure message="'
            'A_GND_NO_ROUNDED_UP_FIGURE (QC_LLM_SOURCE_ALTERATION): pattern found'
            '"/></testcase>'
            '<testcase name="MQC_EVL_EVAL_134000_y"><skipped message="'
            'QC_HARNESS_DEPENDENCY_UNMET: foundational case 134205 did not hold'
            '"/></testcase>'
            '<testcase name="MQC_EVL_SEC_154101_z"><failure message="'
            'QC_SEC_INJECTION_ATTEMPT"/></testcase>'
            "</testsuite></testsuites>",
            encoding="utf-8",
        )
        assert not harness_faults(model_only), (
            "a finding about the model, and a dependent skipped because of one, "
            "blamed this harness"
        )

        ours = tmp_path / "ours.xml"
        ours.write_text(
            "<testsuites><testsuite>"
            '<testcase name="MQC_EVL_EVAL_134401_a"><failure message="'
            'QC_HARNESS_FIXTURE_STALE: the judge request no longer matches'
            '"/></testcase>'
            '<testcase name="MQC_EVL_EVAL_134402_b"><error message="'
            'QC_HARNESS_PREFLIGHT_FAILURE: judge engine is not on the roster'
            '"/></testcase>'
            "</testsuite></testsuites>",
            encoding="utf-8",
        )
        faults = harness_faults(ours)
        assert len(faults) == 2, faults
        assert any("FIXTURE_STALE" in entry for entry in faults)
        # AN ERROR COUNTS WHATEVER IT SAYS, because reporting an error rather
        # than a failure is itself our defect.
        assert any("error rather than a failure" in entry for entry in faults)

        # AND A MISSING REPORT REFUSES. A regression that produced none verified
        # nothing, and an empty finding list would read as a pass.
        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR"):
            harness_faults(tmp_path / "absent.xml")

    def MQC_CMN_UNI_112511_a_file_open_declaring_no_encoding_is_reported(
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


class TestMQCLintParity:
    """One command, wherever it is written."""

    def MQC_CMN_UNI_112151_a_pylint_invocation_differing_from_the_rest_is_reported(
        self, tmp_path: Path
    ) -> None:
        """Every pylint invocation in the repository runs over the same paths.

        **The path list is part of the command.** Four copies stood with four
        different lists: one omitted `cmn/`, two omitted `conftest.py`, and the
        gate omitted `tools/`. A file in an omitted directory passes one gate
        and fails another, arriving as a red on a commit already reported
        green.

        **That is how this case came to exist.** A `conftest.py` line reached
        154 characters, local linting omitted `conftest.py`, and the gate failed
        on both platforms. The defect was in the file; the reason it escaped was
        in the command.

        **The prose counts as much as the workflow.** A documented command a
        contributor copies decides what they check before pushing.

        Design: ``ci_pipeline.md`` section 8.3.1.

        Returns:
            None
        """
        root = Path(__file__).resolve().parents[2]

        found = pylint_invocations(root)
        assert len(found) >= 4, (
            f"only {len(found)} file(s) name a pylint invocation, so the reader "
            f"no longer matches the places the command is written"
        )
        assert not disagreeing_pylint_invocations(root), (
            "pylint is run over different paths in different places: "
            + "; ".join(disagreeing_pylint_invocations(root))
        )

        # IT REPORTS A DISAGREEMENT, which a repository already in agreement
        # says nothing about.
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "wide.yml").write_text(
            "run: python -m pylint a/ b/ --rcfile=.pylintrc\n", encoding="utf-8"
        )
        (workflows / "also-wide.yml").write_text(
            "run: python -m pylint a/ b/ --rcfile=.pylintrc\n", encoding="utf-8"
        )
        (workflows / "narrow.yml").write_text(
            "run: python -m pylint a/ --rcfile=.pylintrc\n", encoding="utf-8"
        )
        reported = disagreeing_pylint_invocations(tmp_path)
        assert len(reported) == 1, f"expected one finding, got {reported}"
        assert "narrow.yml" in reported[0]

        # AND A TREE WITH NO INVOCATION AT ALL IS REPORTED, rather than passing
        # for having compared nothing.
        assert disagreeing_pylint_invocations(tmp_path / "empty")

    def MQC_CMN_UNI_112152_a_duplicated_yaml_key_is_reported(
        self, tmp_path: Path
    ) -> None:
        """A key appearing twice is reported rather than resolved last-wins.

        **This is the class a parse accepts and a schema rejects.** A workflow
        was given a second ``inputs:`` block; ``yaml.safe_load`` accepted it,
        discarded the first block silently along with the input it declared,
        and GitHub rejected the file outright with a failed run carrying no
        jobs and a filename for a name.

        **It is not a schema check and does not pretend to be one.**
        ``actionlint`` validates the workflow schema and runs in CI. What it
        cannot do is run before a push on a machine without it, and the only
        local verification in use was a parse.

        Design: ``ci_pipeline.md`` section 8.3.2.

        Returns:
            None
        """
        root = Path(__file__).resolve().parents[2]

        assert not duplicate_yaml_keys(root), (
            "a tracked YAML file carries a duplicated key, so a parse would "
            "discard one of them silently: " + "; ".join(duplicate_yaml_keys(root))
        )

        # IT REPORTS ONE, naming the key and the line, which is what makes it
        # correctable without bisecting the file.
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "twice.yml").write_text(
            "\n".join([
                "on:",
                "  workflow_dispatch:",
                "    inputs:",
                "      first:",
                "        type: string",
                "    inputs:",
                "      second:",
                "        type: string",
            ]) + "\n",
            encoding="utf-8",
        )
        reported = duplicate_yaml_keys(tmp_path)
        assert len(reported) == 1, f"expected one finding, got {reported}"
        assert "inputs" in reported[0]
        assert "twice.yml" in reported[0]
        assert "line 6" in reported[0], (
            f"the line number is what makes it correctable: {reported[0]}"
        )

        # AND THE SAME FILE WITH ONE BLOCK IS NOT REPORTED.
        (workflows / "twice.yml").write_text(
            "\n".join([
                "on:",
                "  workflow_dispatch:",
                "    inputs:",
                "      first:",
                "        type: string",
                "      second:",
                "        type: string",
            ]) + "\n",
            encoding="utf-8",
        )
        assert not duplicate_yaml_keys(tmp_path)
