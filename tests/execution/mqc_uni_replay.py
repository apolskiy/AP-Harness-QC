# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for the fixture store and the request hash.

Covers `MQC_EXE_UNI_113600` through `113604`, `113605` through `113607`,
inventoried in ``docs/design/tier2_execution.md`` section 10.1.

**The hash is what makes replay honest.** Locating a fixture by identity keeps
it findable; verifying it by hash keeps it truthful. Without the hash, changing
prompt composition would silently replay a recorded answer to a different
question, which no later check would catch.

A failure here is **not a model finding**, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

from pathlib import Path
from typing import Any
import json

import pytest

from execution.dispatch import DispatchPlan, DispatchSession, dispatch_case
from execution.replay import (
    FixtureKey,
    FixtureMissing,
    FixtureStale,
    hash_request,
    load_fixture,
    record_fixture,
    stored_observation_count,
)

pytestmark = pytest.mark.unit

_CASE_ID = "MQC_TASK_alpha::MQC_RULE_grounding"
_REQUEST = {"prompt": "Rewrite the summary.", "model": "gemini-flash"}


@pytest.fixture(name="recorded_run")
def fixture_recorded_run(tmp_path: Path) -> None:
    """Record three observations of one case and return what locates them.

    Args:
        tmp_path (Path): pytest's temporary directory.

    Returns:
        tuple: The fixture root, the request hash, and the three responses.
    """
    digest = hash_request(_REQUEST)
    responses = [{"text": f"Rewrite variant {index}."} for index in range(3)]
    for index, response in enumerate(responses):
        record_fixture(
            tmp_path, FixtureKey(_CASE_ID, "gemini", index), digest, response, "gemini-flash-002"
        )
    return tmp_path, digest, responses


class TestMQCRequestHash:
    """What the hash covers, and what it must not depend on."""

    @pytest.mark.parametrize(
        "structure",
        [
            {"prompt": "line one\nline two"},
            {"message": {"prompt": "line one\nline two"}},
            {"documents": ["line one\nline two", "plain"]},
        ],
    )
    def MQC_EXE_UNI_113606_request_hash_is_identical_across_line_ending_conventions(
        self, structure: dict
    ) -> None:
        """The same commit must hash identically on both supported platforms.

        Normalization happens **before** serialization. A carriage return is
        escaped into a two-character sequence by the serializer, so a
        replacement applied afterwards finds no control character and silently
        does nothing, which is the defect this case exists to prevent.

        The parameters cover the top level, a nested mapping and a list,
        because a prompt is as likely to sit in a nested field as at the top.

        Args:
            structure (dict): A request carrying a multi-line value.

        Returns:
            None
        """
        as_text = json.dumps(structure)
        windows_form = json.loads(as_text.replace("\\n", "\\r\\n"))
        assert hash_request(structure) == hash_request(windows_form)

    def MQC_EXE_UNI_113608_different_requests_hash_differently(self) -> None:
        """The counterweight: normalization must not collapse real differences.

        A hash that ignored line endings by ignoring content would satisfy the
        case above and be useless.

        Returns:
            None
        """
        assert hash_request(_REQUEST) != hash_request({**_REQUEST, "prompt": "Summarise it."})
        assert hash_request({"a": 1, "b": 2}) == hash_request({"b": 2, "a": 1})

    def MQC_EXE_UNI_113609_an_unserializable_request_names_the_boundary_it_crossed(self) -> None:
        """A provider object reaching the hash should have stopped at the adapter.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR"):
            hash_request({"client": {1, 2, 3}})


class TestMQCFixtureStore:
    """Locating, verifying and recording observations."""

    def MQC_EXE_UNI_113607_a_fixture_path_never_contains_the_case_id_separator(
        self,
        tmp_path: Path,
    ) -> None:
        """A case identifier carries a colon, which Windows refuses in a path.

        The key stays the tuple and the path splits it, per design section
        7.2.1. This asserts the split rather than the platform, so the case
        fails on Linux too if the split is ever removed.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        path = FixtureKey(_CASE_ID, "gemini", 0).as_path(tmp_path)
        assert "::" not in path.as_posix()
        assert path.parent.name == "MQC_RULE_grounding"
        assert path.parent.parent.name == "MQC_TASK_alpha"

    def MQC_EXE_UNI_113600_replay_reproduces_all_three_recorded_observations(
        self, recorded_run: tuple
    ) -> None:
        """Three recordings replay as three different responses.

        Replaying one response three times would show zero variance and falsely
        imply the model is deterministic, destroying the same-commit
        reliability signal repeat observation exists to produce.

        Args:
            recorded_run (tuple): Root, hash and the recorded responses.

        Returns:
            None
        """
        root, digest, responses = recorded_run
        replayed = [
            load_fixture(root, FixtureKey(_CASE_ID, "gemini", index), digest).response
            for index in range(3)
        ]
        assert replayed == responses
        assert len({json.dumps(entry, sort_keys=True) for entry in replayed}) == 3

    def MQC_EXE_UNI_113601_replay_of_single_response_thrice_is_rejected(
        self,
        tmp_path: Path,
    ) -> None:
        """A run storing one observation cannot reproduce a three-observation run.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        digest = hash_request(_REQUEST)
        record_fixture(tmp_path, FixtureKey(_CASE_ID, "gemini", 0), digest, {"text": "x"}, "m")
        assert stored_observation_count(tmp_path, _CASE_ID, "gemini") == 1
        with pytest.raises(FixtureMissing):
            load_fixture(tmp_path, FixtureKey(_CASE_ID, "gemini", 1), digest)

    def MQC_EXE_UNI_113602_changed_request_hash_reports_fixture_stale(
        self,
        recorded_run: tuple,
    ) -> None:
        """A moved prompt must not replay an answer to the old question.

        Args:
            recorded_run (tuple): Root, hash and the recorded responses.

        Returns:
            None
        """
        root, _, _ = recorded_run
        moved = hash_request({**_REQUEST, "prompt": "A different question entirely."})
        with pytest.raises(FixtureStale, match="QC_HARNESS_FIXTURE_STALE") as caught:
            load_fixture(root, FixtureKey(_CASE_ID, "gemini", 0), moved)
        assert _CASE_ID in str(caught.value)

    def MQC_EXE_UNI_113603_absent_fixture_reports_fixture_missing(self, tmp_path: Path) -> None:
        """A missing fixture skips and names the case rather than failing.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        with pytest.raises(FixtureMissing, match="QC_HARNESS_FIXTURE_MISSING") as caught:
            load_fixture(tmp_path, FixtureKey(_CASE_ID, "gemini", 0), hash_request(_REQUEST))
        assert _CASE_ID in str(caught.value)

    def MQC_EXE_UNI_113604_recorded_fixture_carries_resolved_model_version(
        self, recorded_run: tuple
    ) -> None:
        """A recording knows which model it came from.

        Replaying it against a later model version is then visible in the
        record rather than assumed away.

        Args:
            recorded_run (tuple): Root, hash and the recorded responses.

        Returns:
            None
        """
        root, digest, _ = recorded_run
        assert load_fixture(
            root, FixtureKey(_CASE_ID, "gemini", 0), digest
        ).resolved_model == "gemini-flash-002"

    def MQC_EXE_UNI_113605_divergent_refs_report_staleness_as_a_finding(
        self, recorded_run: tuple
    ) -> None:
        """Under divergent refs the staleness report is the answer, not an error.

        A changed hash says the request composition moved between the two
        checkouts, which is exactly what the diagnostic in `ci_pipeline.md`
        section 6.4 is asking. The store reports and continues rather than
        deciding what the divergence means.

        Args:
            recorded_run (tuple): Root, hash and the recorded responses.

        Returns:
            None
        """
        root, _, _ = recorded_run
        other_checkout = hash_request({**_REQUEST, "prompt": "Composed differently."})
        stale_count = 0
        for index in range(3):
            try:
                load_fixture(root, FixtureKey(_CASE_ID, "gemini", index), other_checkout)
            except FixtureStale:
                stale_count += 1
        assert stale_count == 3

    def MQC_EXE_UNI_113610_an_unreadable_fixture_reports_missing_not_stale(
        self,
        tmp_path: Path,
    ) -> None:
        """A fixture that cannot be parsed carries no hash to compare.

        Reporting it stale would claim more than is known: staleness is a
        statement about a hash, and there is none.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        key = FixtureKey(_CASE_ID, "gemini", 0)
        path = key.as_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ truncated", encoding="utf-8")
        with pytest.raises(FixtureMissing):
            load_fixture(tmp_path, key, hash_request(_REQUEST))


class TestMQCDispatchConvertsFixtureFailures:
    """The store raises; dispatch must turn that into a skip."""

    def MQC_EXE_UNI_113611_a_missing_fixture_becomes_a_skip_rather_than_an_error(
        self, tmp_path: Path, minimal_case: Any
    ) -> None:
        """The documented skip never happened, for two years of exceptions.

        `_replay_case` promised "a skip when the fixture is missing or stale,
        both reported, never silently replayed", and caught `FileNotFoundError`
        and `ValueError`. **The store raises neither**: `FixtureMissing` and
        `FixtureStale` inherit from `Exception` alone, so the handler never
        fired and the exception escaped dispatch.

        **A harness event surfacing as an error is what this forbids.**
        `framework-rules.md` section 4 makes a `QC_HARNESS_*` code a skip or
        broken and never a failure, because a red suite reads as a finding
        about the model.

        **The existing cases assert that the store raises, which it does.**
        Nothing asserted that dispatch converts what it raises, and those are
        different claims about different modules.

        Args:
            tmp_path (Path): An empty fixture root.
            minimal_case (Any): A case carrying no optional furniture.

        Returns:
            None
        """
        plan = DispatchPlan(mode="replay", fixture_root=tmp_path)

        outcome = dispatch_case(minimal_case, "gemini", plan, DispatchSession())

        assert outcome.taxonomy_code == "QC_HARNESS_FIXTURE_MISSING", (
            "a missing fixture did not become a skip, so a harness event "
            "reaches the suite as a failure about the model"
        )
        assert outcome.response is None
        assert outcome.mode == "replay"

        # AND THE EXCEPTION DOES NOT ESCAPE, which is the whole defect: the
        # handler named two builtins the store never raises, so the call above
        # used to propagate instead of returning at all.
        assert outcome.attempts == 0
        assert outcome.rate_limit_encounters == 0
