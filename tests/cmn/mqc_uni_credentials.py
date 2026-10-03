# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Where a credential comes from, and where it must never come from.

Covers ``MQC_CMN_UNI_112512`` through ``112515``, inventoried in
``docs/design/cmn_verdict_and_cli.md`` section 10.34.

**Two cases because they run in different places.** The local loader has no
behaviour to assert on a runner, and the boundary it must not cross has to be
asserted everywhere. A single case would disable half of itself depending on
where it ran, and a case that skips part of its own assertions is one whose
green says less than it appears to.

**No case here reads the real credential file.** Every fixture is synthetic and
every environment is an injected mapping, so nothing in this module can print,
log or assert against a key.

A failure here is our defect, so the module carries no priority marker.
"""

import os
import re
from pathlib import Path
from typing import Final

import pytest

from cmn.config import (
    ENV_FILE,
    load_env_file,
    orphan_credentials,
    warn_orphan_credentials,
)
from execution.adapters.registry import (
    adapter_for,
    credential_variables,
    registered_engines,
)

# THIS REPOSITORY'S ROOT, named once. Three checks reach for it and two of
# them computed it inline.
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.unit

# The markers a runner sets. Named once so the skip and the check agree.
_CI_MARKERS = ("CI", "GITHUB_ACTIONS")

_UNDER_CI = any(marker in os.environ for marker in _CI_MARKERS)


class TestMQCLocalCredentialFile:
    """The loader `.env.example` has always instructed readers to rely on."""

    @pytest.mark.skipif(
        _UNDER_CI,
        reason="the local loader is inert on a runner; 11164 asserts that it is",
    )
    def MQC_CMN_UNI_112512_a_local_env_file_is_loaded_without_overwriting_anything(
        self, tmp_path: Path
    ) -> None:
        """The file was documented for a year and read by nothing.

        `.env.example` opens with "Copy to `.env` and fill in what you need"
        and the README repeats it. **No loader existed**, so a key placed there
        never reached the process and the suite reported the credential absent.

        **Explicit environment wins.** A variable already set is never
        replaced: somebody who exported a key in their shell meant that key,
        and a file silently overriding it would succeed against the wrong
        account.

        Args:
            tmp_path (Path): A directory for a synthetic credential file.

        Returns:
            None
        """
        (tmp_path / ENV_FILE).write_text(
            "# a comment\n"
            "\n"
            "MQC_PROBE_FRESH=from_the_file\n"
            "MQC_PROBE_EXISTING=from_the_file\n"
            'MQC_PROBE_QUOTED="quoted value"\n'
            "export MQC_PROBE_EXPORTED=prefixed\n",
            encoding="utf-8",
        )
        environ = {"MQC_PROBE_EXISTING": "from_the_shell"}

        applied = load_env_file(tmp_path, environ)

        assert "MQC_PROBE_FRESH" in applied
        assert environ["MQC_PROBE_FRESH"] == "from_the_file"

        # NEVER OVERWRITTEN, and never reported as applied either.
        assert "MQC_PROBE_EXISTING" not in applied
        assert environ["MQC_PROBE_EXISTING"] == "from_the_shell"

        # Quoting and an `export` prefix are both tolerated, because a file
        # written by hand carries both and neither changes the value.
        assert environ["MQC_PROBE_QUOTED"] == "quoted value"
        assert environ["MQC_PROBE_EXPORTED"] == "prefixed"

    @pytest.mark.skipif(
        _UNDER_CI,
        reason="the local loader is inert on a runner; 11164 asserts that it is",
    )
    def MQC_CMN_UNI_112513_a_line_that_is_not_an_assignment_is_skipped_by_number(
        self, tmp_path: Path
    ) -> None:
        """A line with no assignment is skipped, and says so by number.

        **Refusing outright was the first implementation and it was wrong.** It
        crashed the whole suite on a real file whose first line was an ordinary
        note, which is worse than the silence it was defending against. The
        line number is named and the line never is, because it may carry a key.

        **An absent file is not an error.** The suite runs without credentials
        by design, which is what `.env.example` states at length.

        Args:
            tmp_path (Path): A directory for a synthetic credential file.

        Returns:
            None
        """
        (tmp_path / ENV_FILE).write_text(
            "a note somebody typed\nMQC_PROBE_AFTER=still_loaded\n", encoding="utf-8"
        )
        environ: dict[str, str] = {}

        applied = load_env_file(tmp_path, environ)

        # THE LINE AFTER IT STILL LOADS, which is the whole reason for
        # skipping rather than raising.
        assert applied == ["MQC_PROBE_AFTER"]
        assert environ["MQC_PROBE_AFTER"] == "still_loaded"

        # An absent file yields nothing and raises nothing.
        assert not load_env_file(tmp_path / "nowhere", {})


class TestMQCCredentialsNeverReachCI:
    """CI takes credentials from its own store, and only from there."""

    def MQC_CMN_UNI_112514_a_credential_file_reaching_ci_is_reported(
        self, tmp_path: Path
    ) -> None:
        """A file on a runner is a credential arriving by an unaudited path.

        **Refused rather than merely unnecessary.** "Harmless because nothing
        calls it" is the reasoning this project has corrected repeatedly, most
        recently for a redaction fallback that was implemented and unreachable.

        **This case runs everywhere**, including on the runner it is about,
        which is the half 11162 and 11163 cannot cover.

        Args:
            tmp_path (Path): A directory for a synthetic credential file.

        Returns:
            None
        """
        (tmp_path / ENV_FILE).write_text(
            "MQC_PROBE_SHOULD_NOT_LOAD=from_a_file\n", encoding="utf-8"
        )

        for marker in _CI_MARKERS:
            environ = {marker: "true"}

            assert not load_env_file(tmp_path, environ), (
                f"the loader read a credential file with {marker} set, so a "
                f"file on a runner competes with the environment's own store"
            )
            assert "MQC_PROBE_SHOULD_NOT_LOAD" not in environ

        # AND WITHOUT A MARKER IT LOADS, or the refusal above would pass
        # against a loader that simply never worked.
        assert load_env_file(tmp_path, {}) == ["MQC_PROBE_SHOULD_NOT_LOAD"]

    def MQC_CMN_UNI_112515_no_workflow_reads_a_credential_file(self) -> None:
        """The other half: nothing in CI is written to look for one.

        A loader that refuses is one mechanism. A workflow that never asks is
        the other, and the two are independent for the same reason the debug
        artifact exclusion has two.

        Returns:
            None
        """
        roots = [_REPO_ROOT]
        sibling = roots[0].parent / "AP-Model-QC"
        if sibling.is_dir():
            roots.append(sibling)

        workflows = [
            path
            for root in roots
            for path in sorted((root / ".github" / "workflows").glob("*.yml"))
        ]
        assert workflows, "no workflows were read, so this check establishes nothing"

        # MATCHED AS A FILENAME, NOT A SUBSTRING. `.env` occurs inside
        # `os.environ`, and the first version of this check reported three
        # workflows that merely read an environment variable. A substring
        # where a token was meant is the error this project produces most.
        filename = re.compile(
            r"(?<![A-Za-z0-9_])" + re.escape(ENV_FILE) + r"(?![A-Za-z0-9_])"
        )
        offenders = [
            f"{path.parent.parent.parent.name}/{path.name}"
            for path in workflows
            if filename.search(path.read_text(encoding="utf-8"))
        ]
        assert not offenders, (
            f"these workflows reference {ENV_FILE}, so a credential could reach "
            f"a runner by a path nobody audited: {offenders}"
        )


class TestMQCCredentialFileLocation:
    """Where the consumer looks, and in what order."""

    @pytest.mark.skipif(
        _UNDER_CI,
        reason="the local loader is inert on a runner; 11164 asserts that it is",
    )
    def MQC_CMN_UNI_112516_a_credential_file_beside_the_roster_is_found(
        self, tmp_path: Path
    ) -> None:
        """The file lives with the roster, and the consumer reaches for it.

        **It existed and was read by nobody.** `.env` was created in the
        harness checkout, naming the judge's credential, and the graded cases
        load from their own root. The suite reported the credential absent
        while the file sat one directory away, which is the same defect
        section 10.34 was written for with the loader now present and looking
        in the wrong place.

        **Two calls rather than merge logic.** `load_env_file` never
        overwrites a variable that is already set, so calling it for the local
        root and then for the sibling gives "local wins, sibling as fallback"
        with nothing new to get wrong.

        Args:
            tmp_path (Path): A directory holding two synthetic checkouts.

        Returns:
            None
        """
        consumer = tmp_path / "AP-Model-QC"
        harness = tmp_path / "AP-Harness-QC"
        consumer.mkdir()
        harness.mkdir()
        (harness / ENV_FILE).write_text(
            "MQC_PROBE_BESIDE_ROSTER=from_the_harness\n"
            "MQC_PROBE_CONTESTED=from_the_harness\n",
            encoding="utf-8",
        )

        # NOTHING LOCAL, so the sibling supplies it. This is the arrangement
        # that was reporting the credential absent.
        environ: dict[str, str] = {}
        load_env_file(consumer, environ)
        load_env_file(harness, environ)
        assert environ["MQC_PROBE_BESIDE_ROSTER"] == "from_the_harness"

        # AND A LOCAL FILE STILL WINS, because the first call gets there
        # first and the second refuses to overwrite.
        (consumer / ENV_FILE).write_text(
            "MQC_PROBE_CONTESTED=from_the_consumer\n", encoding="utf-8"
        )
        contested: dict[str, str] = {}
        load_env_file(consumer, contested)
        load_env_file(harness, contested)
        assert contested["MQC_PROBE_CONTESTED"] == "from_the_consumer"

        # The sibling still supplies what the local file does not name.
        assert contested["MQC_PROBE_BESIDE_ROSTER"] == "from_the_harness"

    def MQC_CMN_UNI_112517_the_consumer_conftest_searches_both_roots(self) -> None:
        """The functions can be right and the caller can look in one place.

        **That is exactly what happened.** `load_env_file` worked, the
        credential file existed, and the consumer's hook passed one root. A
        case exercising the loader alone passes throughout, which is why this
        one reads the hook.

        Returns:
            None
        """
        consumer = _REPO_ROOT.parent / "AP-Model-QC"
        if not consumer.is_dir():
            pytest.skip("the consumer checkout is not beside this one")

        hook = (consumer / "conftest.py").read_text(encoding="utf-8")
        # THE CALLS, not the import, which carries no parenthesis.
        calls = hook.count("load_env_file(")
        assert calls >= 2, (
            f"the consumer conftest calls load_env_file {calls} time(s), so "
            f"it searches one root and a credential beside the roster is not "
            f"found; the suite then reports it absent"
        )
        assert "AP-Harness-QC" in hook, (
            "the consumer conftest names no harness checkout, so the fallback "
            "root is not the one the roster lives in"
        )


class TestMQCOrphanedCredential:
    """A credential the file names and nothing reads."""

    def MQC_CMN_UNI_112518_a_credential_no_engine_reads_is_reported(
        self, tmp_path: Path
    ) -> None:
        """A name off by an underscore loads cleanly and reaches nothing.

        **This happened.** `OPEN_AI_APi_KEY` differs from `OPENAI_API_KEY` in
        two places, an underscore and a letter's case. The file loaded, the
        variable was set, the loader reported it applied, and no engine would
        ever look at it.

        **The file is one a reader is told not to print**, so this is the place
        they have least ability to check their own work, which is why silence
        here is worse than silence elsewhere.

        **A warning, not a refusal.** A file may legitimately carry a
        credential for something outside this harness; refusing to start over a
        name we merely do not recognise would be the harness overreaching.

        Args:
            tmp_path (Path): A directory for a synthetic credential file.

        Returns:
            None
        """
        reads = ["OPENAI_API_KEY", "GEMINI_API_KEY"]

        # THE REAL TYPO, and the loose pattern is what catches it: a check
        # demanding the correct spelling would miss every case it is for.
        assert orphan_credentials(["OPEN_AI_APi_KEY"], reads) == ["OPEN_AI_APi_KEY"]
        assert orphan_credentials(["OPENAI_APIKEY"], reads) == ["OPENAI_APIKEY"]

        # A NAME AN ENGINE READS IS NOT AN ORPHAN, whatever its case.
        assert not orphan_credentials(["OPENAI_API_KEY"], reads)
        assert not orphan_credentials(["openai_api_key"], reads)

        # AND SOMETHING THAT IS NOT CREDENTIAL SHAPED IS LEFT ALONE, or the
        # warning would fire on every ordinary variable in the file.
        assert not orphan_credentials(["MQC_PROBE_FRESH", "HTTPS_PROXY"], reads)

        # THE FILE IS READ AND ONLY NAMES ARE RETURNED.
        (tmp_path / ENV_FILE).write_text(
            "# a note\n"
            "OPEN_AI_APi_KEY=synthetic-value-never-printed\n"
            "OPENAI_API_KEY=another-synthetic-value\n",
            encoding="utf-8",
        )
        reported = warn_orphan_credentials(tmp_path, reads)
        assert reported == ["OPEN_AI_APi_KEY"]
        assert all("synthetic" not in name for name in reported), (
            "a credential value reached the report, which is the one thing "
            "this check must never do"
        )

        # AN ABSENT FILE REPORTS NOTHING AND RAISES NOTHING.
        assert not warn_orphan_credentials(tmp_path / "nowhere", reads)

    def MQC_CMN_UNI_112519_the_engines_declare_the_names_the_check_reads(
        self,
    ) -> None:
        """The comparison cannot drift, because no list is maintained.

        **An engine added tomorrow is covered the moment it is registered.** A
        maintained list would be a second place to forget, which is the failure
        mode the conformance battery's automatic enrolment exists to remove.

        Returns:
            None
        """
        declared = credential_variables()

        assert declared, "no engine declares a credential variable"
        for engine in registered_engines():
            adapter = adapter_for(engine)()
            primary = getattr(adapter, "API_KEY_ENV", "")
            assert primary, f"{engine} declares no credential variable"
            assert primary in declared, f"{engine} names {primary}, which is absent"

        # GEN AI RESOLVES ITS OWN AND ACCEPTS TWO NAMES, so both are declared.
        assert "GEMINI_API_KEY" in declared
        assert "GOOGLE_API_KEY" in declared


class TestMQCEveryCredentialIsDocumented:
    """A key an adapter reads and nobody documents is a key nobody sets."""

    def MQC_CMN_UNI_112520_every_declared_credential_appears_in_the_example(
        self,
    ) -> None:
        """`.env.example` names every variable a registered adapter reads.

        **This gap was real and this check is why it is not.** `XAI_API_KEY`
        arrived with the grok adapter and `GOOGLE_API_KEY` with the Gen AI
        client's second name, and neither reached `.env.example`: the file is
        the only place a reader learns what to set, so an omission there makes
        an engine look unavailable rather than unconfigured.

        **It runs in this direction on purpose.** The reverse — a documented
        name no adapter reads — is `orphan_credentials`, which warns rather than
        fails, because a key left in an environment after an engine is retired
        is untidy and not wrong. A key an adapter needs and nothing documents is
        wrong.

        Returns:
            None
        """
        example = (_REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        # THE ASSIGNMENT, NOT A MENTION. A first version of this searched the
        # whole file for the name and passed on the comment heading above the
        # assignment, so deleting the settable line left it green. What a reader
        # copies is `NAME=`, so that is what is required.
        settable = {
            line.split("=", 1)[0].strip()
            for line in example.splitlines()
            if "=" in line and not line.lstrip().startswith("#")
        }
        missing = sorted(set(credential_variables()) - settable)

        assert not missing, (
            f"{len(missing)} credential(s) are read by a registered adapter and "
            f"have no settable line in .env.example: {missing}. Add each with "
            f"what it unlocks and where to get it"
        )
