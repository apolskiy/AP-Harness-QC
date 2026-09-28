# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Storing and replaying a judgement.

Covers ``MQC_CMN_UNI_11136`` through ``11139``, inventoried in
``docs/design/cmn_verdict_and_cli.md`` section 10.19. The design is
``tier2_execution.md`` section 7.4.

**Tier 3 is unchanged by any of this.** ``JudgeBinding.invoke`` is an injected
callable, so a replaying judge is a different callable bound by the caller, and
``evaluation/`` still imports nothing from ``execution/``. The principle that a
tier does not know how the tier below obtained its input extends to the judge
without amendment.

A failure here is our defect, so the module carries no priority marker.
"""

from pathlib import Path
from typing import Any

import pytest
from google.genai import errors as genai_errors

from evaluation.isolation import JudgeRequest
from execution import judge_channel
from execution.adapters.gemini import GeminiAdapter
from execution.judge_channel import JudgeChannel, JudgementPlan
from execution.replay import (
    FixtureMissing,
    FixtureStale,
    JudgementKey,
    hash_request,
    load_judgement,
    record_judgement,
)
from tests.execution.provider_doubles import gemini_judgement

pytestmark = pytest.mark.unit

_CASE = "MQC_TASK_alpha::MQC_RULE_grounding"
_REQUEST = "sha256:judgerequest"
_MODEL = "gemini-2.5-flash"


def _recorded(root: Path, reply: Any = None) -> JudgementKey:
    """Record one judgement and return its key.

    Args:
        root (Path): The fixture root.
        reply (Any): The reply to store.

    Returns:
        JudgementKey: What was recorded.
    """
    key = JudgementKey(case_id=_CASE, judge_engine="gemini", observation_index=0)
    record_judgement(root, key, _REQUEST, _MODEL, reply or {"scores": [4, 5]})
    return key


class TestMQCJudgementFixture:
    """What a stored judgement is keyed by, and what invalidates it."""

    def MQC_CMN_UNI_11136_a_recorded_judgement_is_replayed_for_the_same_request(
        self, tmp_path: Path
    ) -> None:
        """A replay run is free and deterministic only if the judge is replayed.

        Before this, a replay run replayed the response and called the judge
        live, so two runs of one commit could produce different verdicts. That
        contradicts the verdict being recomputable from stored artifacts.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        key = _recorded(tmp_path)
        stored = load_judgement(tmp_path, key, _REQUEST, _MODEL)

        assert stored.reply == {"scores": [4, 5]}
        assert stored.judge_model == _MODEL

        # KEYED BY THE JUDGE ENGINE. Two judges scoring one observation produce
        # two judgements, not one overwriting the other.
        other = JudgementKey(case_id=_CASE, judge_engine="claude", observation_index=0)
        record_judgement(tmp_path, other, _REQUEST, "claude-opus-5-5", {"scores": [2]})
        assert load_judgement(tmp_path, key, _REQUEST, _MODEL).reply == {
            "scores": [4, 5]
        }

    def MQC_CMN_UNI_11137_a_judgement_from_a_different_judge_model_is_stale(
        self, tmp_path: Path
    ) -> None:
        """The question is the same and the instrument is not.

        **Nothing else in the fixture machinery sees this.** The judge model is
        not part of the composed request, so the request hash is identical
        across a provider updating the judge. Storing it separately is what
        makes the change visible.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        key = _recorded(tmp_path)

        with pytest.raises(FixtureStale, match="instrument"):
            load_judgement(tmp_path, key, _REQUEST, "gemini-2.5-pro")

        # The request is unchanged, which is the whole point of the case.
        assert load_judgement(tmp_path, key, _REQUEST, _MODEL).request_hash == _REQUEST

    def MQC_CMN_UNI_11138_a_judgement_whose_request_hash_moved_is_stale(
        self, tmp_path: Path
    ) -> None:
        """A rubric edit or a different response changes what was asked.

        The composed judge request carries the case, the rubric and the
        candidate material, so all three are covered by the hash. Replaying a
        score recorded against a different request would answer a question
        nobody asked.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        key = _recorded(tmp_path)

        with pytest.raises(FixtureStale, match="different question"):
            load_judgement(tmp_path, key, "sha256:rubricedited", _MODEL)

    def MQC_CMN_UNI_11139_a_missing_judgement_raises_rather_than_judging_live(
        self, tmp_path: Path
    ) -> None:
        """The fail-open path does not exist to be taken by accident.

        A fallback to a live call would restore both the drift and the quota
        spend silently, under exactly the load that would hide it. Raising
        means a replay run records a skip, excluded from the skip-rate
        denominator because nothing was measured about the model.

        **The consequence is accepted**: a new graded case is unjudged in
        replay until a live run records its judgement. That reports that
        nothing was measured rather than guessing.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        absent = JudgementKey(
            case_id="MQC_TASK_new::MQC_RULE_new",
            judge_engine="gemini",
            observation_index=0,
        )

        with pytest.raises(FixtureMissing, match="QC_HARNESS_FIXTURE_MISSING"):
            load_judgement(tmp_path, absent, _REQUEST, _MODEL)

        # It returns nothing a caller could mistake for a score, in any branch.
        assert not hasattr(load_judgement, "default")


class TestMQCJudgeChannelMode:
    """What the channel does with `--judge-mode`, which nothing honoured."""

    @staticmethod
    def _request() -> Any:
        """Return a judge request the channel can compose from.

        Returns:
            Any: A ``JudgeRequest`` carrying a trivial reply schema.
        """
        return JudgeRequest(
            case_id="MQC_TASK_alpha::MQC_RULE_grounding",
            instruction="Score the response against the rubric.",
            reply_schema={"type": "object", "properties": {"scores": {}}},
            data={"candidate_output": "A grounded summary."},
        )

    def MQC_EXE_UNI_10283_a_replay_judgement_never_reaches_the_provider(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """A replay channel loads a stored judgement and dispatches nothing.

        **This is a quota leak, not a missing feature.** `FixtureKey` keys the
        candidate only, so a bound judge is a live call whatever `--mode` says.
        A replay run that judged would spend provider quota on every pull
        request.

        **The provider is made to fail if reached**, rather than counted. A
        count asserts how often something happened; raising asserts that it
        must not happen at all, which is the actual claim.

        Args:
            tmp_path (Path): A directory for the judgement store.
            monkeypatch (Any): pytest's patcher.

        Returns:
            None
        """
        def forbidden(self: Any, request: Any) -> Any:
            """Refuse to be dispatched.

            Args:
                self (Any): The adapter.
                request (Any): The composed request.

            Returns:
                Any: Never; this always raises.

            Raises:
                AssertionError: Always.
            """
            assert request is not None and self is not None
            raise AssertionError("a replay judgement reached the provider")

        monkeypatch.setattr(GeminiAdapter, "dispatch", forbidden)

        channel = JudgeChannel(
            "gemini",
            model="gemini-2.5-flash",
            plan=JudgementPlan(mode="replay", fixture_root=tmp_path),
        )
        request = self._request()
        composed = channel.adapter.compose_judgement(
            request.rendered(), request.reply_schema
        )
        stored = {"scores": {"MQC_CRIT_grounding": {"score": 4, "rationale": "Fine."}}}
        record_judgement(
            tmp_path,
            JudgementKey(request.case_id, "gemini", 0),
            hash_request(composed),
            "gemini-2.5-flash",
            stored,
        )

        assert channel.invoke(request) == stored

        # A MISSING JUDGEMENT RAISES RATHER THAN FALLING BACK, or the
        # fail-open path would exist to be taken by accident.
        empty = JudgeChannel(
            "gemini",
            model="gemini-2.5-flash",
            plan=JudgementPlan(mode="replay", fixture_root=tmp_path / "elsewhere"),
        )
        with pytest.raises(FixtureMissing):
            empty.invoke(request)

    def MQC_EXE_UNI_10284_a_live_judgement_is_recorded_for_later_replay(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """What a live channel obtains is stored against the text it scored.

        **The round trip is the assertion.** Recording a file proves a write
        happened; replaying it through a channel that refuses to dispatch
        proves the write is usable, which is the only property anybody wants.

        Args:
            tmp_path (Path): A directory for the judgement store.
            monkeypatch (Any): pytest's patcher.

        Returns:
            None
        """
        awarded = {"scores": {"MQC_CRIT_grounding": {"score": 5, "rationale": "Good."}}}

        def answer(self: Any, request: Any) -> Any:
            """Return a schema-constrained reply.

            Args:
                self (Any): The adapter.
                request (Any): The composed request.

            Returns:
                Any: A Gen AI response double carrying the judgement.
            """
            assert request is not None and self is not None
            return gemini_judgement(awarded)

        monkeypatch.setattr(GeminiAdapter, "dispatch", answer)

        live = JudgeChannel(
            "gemini",
            model="gemini-2.5-flash",
            plan=JudgementPlan(mode="live", fixture_root=tmp_path, record=True),
        )
        request = self._request()

        assert live.invoke(request) == awarded

        def forbidden(self: Any, request: Any) -> Any:
            """Refuse to be dispatched.

            Args:
                self (Any): The adapter.
                request (Any): The composed request.

            Returns:
                Any: Never; this always raises.

            Raises:
                AssertionError: Always.
            """
            assert request is not None and self is not None
            raise AssertionError("the replay reached the provider")

        monkeypatch.setattr(GeminiAdapter, "dispatch", forbidden)
        replayed = JudgeChannel(
            "gemini",
            model="gemini-2.5-flash",
            plan=JudgementPlan(mode="replay", fixture_root=tmp_path),
        )
        assert replayed.invoke(request) == awarded

        # AND A PLAN THAT CANNOT DO WHAT IT SAYS IS REFUSED AT CONSTRUCTION.
        with pytest.raises(ValueError, match="nothing to replay from"):
            JudgementPlan(mode="replay")
        with pytest.raises(ValueError, match="is not a judge mode"):
            JudgementPlan(mode="cached")


    def MQC_EXE_UNI_10307_each_observation_records_its_own_judgement(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """Three observations of a case kept one judgement, overwriting.

        `JudgeRequest` carried no `observation_index` and the channel read one
        through `getattr(request, "observation_index", 0)`, so every
        observation keyed at zero. Observation 1 overwrote 0, observation 2
        overwrote 1, and the surviving file held the hash of the last
        observation judged. Replay then started at observation 0, recomputed a
        hash over different candidate text, and failed the case as
        `QC_HARNESS_FIXTURE_STALE` — the amb family recorded live and would not
        replay.

        **The round trip here used one observation**, which is why it passed
        throughout: the collision needs two.

        Args:
            tmp_path (Path): pytest's temporary directory.
            monkeypatch (Any): Replaces the adapter's dispatch.

        Returns:
            None
        """
        awarded = {"scores": {"C_ONE": {"score": 4, "rationale": "Grounded."}}}

        def answer(self: Any, request: Any) -> Any:
            """Return a judgement for whatever was composed.

            Args:
                self (Any): The adapter.
                request (Any): The composed request.

            Returns:
                Any: A Gen AI response double.
            """
            assert request is not None and self is not None
            return gemini_judgement(awarded)

        monkeypatch.setattr(GeminiAdapter, "dispatch", answer)

        # TWO OBSERVATIONS OF ONE CASE, DIFFERING ONLY IN THE CANDIDATE TEXT,
        # which is exactly what repeat observations are: the same prompt
        # answered again.
        requests = [
            JudgeRequest(
                case_id=_CASE,
                instruction="Score the response against the rubric.",
                reply_schema={"type": "object", "properties": {"scores": {}}},
                data={"candidate_output": text},
                observation_index=index,
            )
            for index, text in enumerate(["A grounded summary.", "Another wording."])
        ]

        live = JudgeChannel(
            "gemini",
            model=_MODEL,
            plan=JudgementPlan(mode="live", fixture_root=tmp_path, record=True),
        )
        for request in requests:
            assert live.invoke(request) == awarded

        stored = sorted(
            path.name
            for path in (tmp_path / "judgements" / "gemini" / "MQC_TASK_alpha").rglob(
                "*.json"
            )
        )
        assert stored == ["0.json", "1.json"], stored

        def forbidden(self: Any, request: Any) -> Any:
            """Refuse to be dispatched.

            Args:
                self (Any): The adapter.
                request (Any): The composed request.

            Returns:
                Any: Never; this always raises.

            Raises:
                AssertionError: Always.
            """
            assert request is not None and self is not None
            raise AssertionError("the replay reached the provider")

        monkeypatch.setattr(GeminiAdapter, "dispatch", forbidden)
        replayed = JudgeChannel(
            "gemini", model=_MODEL, plan=JudgementPlan(mode="replay", fixture_root=tmp_path)
        )
        # AND BOTH REPLAY, which is the failure this reproduces: under the old
        # key, observation 0 met observation 1's hash and raised.
        for request in requests:
            assert replayed.invoke(request) == awarded

class TestMQCJudgeFailureContainment:
    """A provider failure while judging, which used to escape."""

    def MQC_EXE_UNI_10291_a_provider_failure_while_judging_is_contained(
        self, monkeypatch: Any
    ) -> None:
        """The judge reaches the same taxonomy the candidate path does.

        **Every provider failure during judging escaped as a raw SDK
        exception.** The channel mapped nothing and the pipeline caught only
        `ValueError`, so a busy provider that the candidate path handles as a
        retryable skip crashed a judged case outright.

        **Raised as a ValueError carrying the code**, because that is what the
        pipeline already records as `judge_reply_unusable`: a harness event on
        the judge path is a skip with a code, as it is everywhere else.

        Args:
            monkeypatch (Any): pytest's patcher.

        Returns:
            None
        """
        failures = {
            "QC_HARNESS_PROVIDER_UNAVAILABLE": genai_errors.ServerError(
                code=503, response_json={"error": {"code": 503}}
            ),
            "QC_HARNESS_ENGINE_UNREACHABLE": genai_errors.ClientError(
                code=302, response_json={"error": {"code": 302}}
            ),
            "QC_HARNESS_RATE_LIMIT": genai_errors.ClientError(
                code=429, response_json={"error": {"code": 429}}
            ),
        }

        for expected, raised in failures.items():
            def failing(self: Any, request: Any, error: Any = raised) -> Any:
                """Fail the way a provider fails.

                Args:
                    self (Any): The adapter.
                    request (Any): The composed request.
                    error (Any): What to raise.

                Returns:
                    Any: Never.

                Raises:
                    Exception: The supplied failure.
                """
                assert self is not None and request is not None
                raise error

            monkeypatch.setattr(GeminiAdapter, "dispatch", failing)
            channel = JudgeChannel("gemini", model="gemini-3.8-flash")

            with pytest.raises(ValueError) as reported:
                channel.invoke(_JudgeRequestDouble())

            assert expected in str(reported.value), (
                f"a judge failure reported {reported.value} rather than "
                f"{expected}, so the judge path does not reach the taxonomy "
                f"the candidate path uses"
            )

    def MQC_EXE_UNI_10292_the_judge_channel_imports_no_evaluation_module(
        self,
    ) -> None:
        """Containing the failure must not cost the tier boundary.

        Naming the hijack exception here would have been the obvious way to
        let it through, and would have made `execution/` import
        `evaluation/`, which neither tier does in either direction. **It
        cannot arrive here anyway**: it is raised by `validate_judge_reply`
        after this returns.

        Returns:
            None
        """
        source = Path(judge_channel.__file__).read_text(encoding="utf-8")
        offenders = [
            line.strip()
            for line in source.splitlines()
            if line.startswith(("from evaluation", "import evaluation"))
        ]
        assert not offenders, (
            f"the judge channel imports Tier 3: {offenders}"
        )


class _JudgeRequestDouble:
    """The shape a judge request presents to a channel.

    Attributes:
        case_id (str): The case being judged.
        reply_schema (dict): What the judge must reply in.
        observation_index (int): Which observation this is.
    """

    case_id = "MQC_TASK_alpha::MQC_RULE_grounding"
    reply_schema: dict[str, Any] = {"type": "object"}
    observation_index = 0

    def rendered(self) -> str:
        """Return the composed prompt.

        Returns:
            str: The prompt text, composed by Tier 3.
        """
        return "Score the response against the rubric."
