# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Per-adapter cases covering each provider's own conventions.

Covers `MQC_EXE_UNI_113000` through `113008`, inventoried in
``docs/design/tier2_execution.md`` section 10.1.3.

**Passing the conformance battery is necessary and not sufficient**
(``harness_extensibility_standard.md`` section 11). An adapter can satisfy every shared
contract assertion while mapping its provider's rate-limit error to the wrong
code or dropping a system instruction, because the contract cannot know what
each implementation was supposed to do internally.

**Every case here names a real difference between the three providers**, taken
from ingestion.schemas import EvaluationCase
from typing import Any
from their published API documentation rather than from a recorded call. A case
that merely restated the shared contract would belong in the battery, where it
would run against all three instead of one.

A failure here is **not a model finding**, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

from typing import Any, Final

import json

import pytest

from cmn.pricing import TokenUsage
from evaluation.isolation import UnauthoredMaterial, compose_judge_request
from execution.adapters.claude import ClaudeAdapter
from execution.adapters.gemini import GeminiAdapter
from execution.adapters.grok import GrokAdapter
from execution.adapters.openai import OpenAIAdapter
from execution.adapters.openai_protocol import OpenAICompatibleAdapter
from execution.adapters.registry import (
    CANDIDATE_ROLE,
    JUDGE_ROLE,
    adapter_for,
    engines_for_role,
    registered_engines,
)
from execution.replay import hash_request
from ingestion.schemas import EvaluationCase, Rubric
from tests.execution.provider_doubles import (
    ADAPTER_DOUBLES,
    claude_response,
    gemini_blocked_prompt,
    gemini_error,
    gemini_response,
    openai_response,
)

pytestmark = pytest.mark.unit

_CASE_ID = "MQC_TASK_alpha::MQC_RULE_grounding"


# THE 429 GEMINI ACTUALLY RETURNED on 2026-09-26, trimmed to the fields the
# check reads and kept verbatim so a change in the provider's shape surfaces
# here rather than as a recording run that quietly stops making progress.
_SPENT_DAY_BODY: Final[str] = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded"
    " your current quota, please check your plan and billing details.', 'deta"
    "ils': [{'violations': [{'quotaMetric': 'generativelanguage.googleapis.co"
    "m/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerD"
    "ayPerProjectPerModel-FreeTier', 'quotaValue': '20'}]}, {'retryDelay': '5"
    "2s'}]}}"
)

def _rubric_with(criterion_id: str) -> Any:
    """Return a one-criterion rubric, for composing a real judgement schema.

    Args:
        criterion_id (str): What to call the criterion.

    Returns:
        Any: A rubric the composer accepts.
    """
    return Rubric.from_dict(
        {
            "threshold": 3.0,
            "criteria": [
                {
                    "criterion_id": criterion_id,
                    "name": "Usefulness",
                    "description": "Whether the answer is useful.",
                    "anchors": {
                        1: {"description": "Answers nothing."},
                        3: {"description": "Answers in part."},
                        5: {"description": "Answers fully."},
                    },
                }
            ],
        }
    )



class TestMQCClaudeAdapter:
    """What this provider does that the other two do not."""

    def MQC_EXE_UNI_113000_claude_maps_refusal_stop_reason_to_content_filter(self) -> None:
        """This provider names a policy refusal; the others do not.

        Flattening it into an ordinary stop would let a refusal read as a
        completed answer, and the rubric would score the refusal text as though
        the model had attempted the task.

        Returns:
            None
        """
        adapter = ClaudeAdapter()
        refused = claude_response(text="I cannot help with that.", stop_reason="refusal")
        assert adapter.normalize_response(refused, _CASE_ID).finish_reason == "content_filter"

        ordinary = claude_response(stop_reason="end_turn")
        assert adapter.normalize_response(ordinary, _CASE_ID).finish_reason == "stop"

    def MQC_EXE_UNI_113022_a_claude_refusal_is_recorded_as_a_block(self) -> None:
        """A Claude refusal is recorded as a block, with the provider's own word.

        ``stop_reason="refusal"`` yields ``block_reason`` of ``refusal`` and
        ``block_stage`` of ``response``, alongside the canonical
        ``content_filter`` finish reason. An ordinary reply claims neither.

        The reason is verbatim, never mapped: the canonical value says content
        was withheld and this says what the provider called it.

        Design: ``tier2_execution.md`` section 4.3.1.

        Returns:
            None
        """
        adapter = adapter_for("claude")()

        refused = adapter.normalize_response(
            claude_response(text="", stop_reason="refusal"), "case"
        )

        # VERBATIM, NEVER MAPPED. The canonical vocabulary says content was
        # withheld; this says what the provider called it.
        assert refused.block_reason == "refusal"
        assert refused.block_stage == "response"
        assert refused.blocked_by_provider is True
        assert refused.produced_output is False
        assert refused.finish_reason == "content_filter"

        # AND AN ORDINARY REPLY CLAIMS NEITHER.
        ordinary = adapter.normalize_response(claude_response(text="hello"), "case")
        assert not ordinary.block_reason
        assert not ordinary.block_stage
        assert ordinary.blocked_by_provider is False

    def MQC_EXE_UNI_113001_claude_concatenates_every_text_block_in_order(self) -> None:
        """This provider splits text across blocks where the others send a field.

        Reading only the first block would silently truncate the answer, and a
        truncated answer scores as an incomplete one rather than as a defect.

        Returns:
            None
        """
        response = claude_response(
            text_blocks=["The posting requires ", "five years ", "of Python."]
        )
        normalized = ClaudeAdapter().normalize_response(response, _CASE_ID)
        assert normalized.text == "The posting requires five years of Python."

    def MQC_EXE_UNI_113009_claude_sends_the_system_instruction_as_its_own_field(
        self, furnished_case: EvaluationCase, minimal_case: EvaluationCase
    ) -> None:
        """This provider takes a top-level field where OpenAI takes a message role.

        Folding it into the prompt would change what is being measured: a
        system instruction and a user instruction are followed at different
        rates, which is itself a model quality.

        Args:
            furnished_case (Any): A case carrying a system instruction.
            minimal_case (Any): A case carrying none.

        Returns:
            None
        """
        adapter = ClaudeAdapter()
        composed = adapter.compose_request(furnished_case)
        assert composed["system"] == furnished_case.task.system_instruction
        assert "system" not in adapter.compose_request(minimal_case)


    def MQC_EXE_UNI_113011_composed_request_states_effort_rather_than_inheriting_it(
        self, minimal_case: EvaluationCase
    ) -> None:
        """An API-side default must not move a recorded observation.

        This model defaults the effort level one step below its predecessor, so
        an adapter sending no ``output_config`` would have changed how much the
        model thinks **without any line of this repository changing**, and the
        observations would have been recorded as though nothing had moved.

        Naming the value puts it in the composed request and therefore in the
        request hash, so moving it reports ``QC_HARNESS_FIXTURE_STALE`` rather
        than replaying a response recorded under a setting that no longer
        applies.

        Args:
            minimal_case (EvaluationCase): A case carrying no system
                instruction.

        Returns:
            None
        """
        composed = ClaudeAdapter().compose_request(minimal_case)

        assert composed["output_config"] == {"effort": "medium"}
        # In the request means in the hash, which is what makes a change to it
        # visible as a stale fixture rather than as silent drift. Asserted by
        # hashing with the field removed: equal digests would mean the setting
        # was not recorded against the fixture at all.
        assert hash_request(composed) != hash_request(
            {key: value for key, value in composed.items() if key != "output_config"}
        )

    def MQC_EXE_UNI_113012_composed_request_carries_no_field_the_model_rejects(
        self, furnished_case: EvaluationCase
    ) -> None:
        """The four breaking changes, held as a standing check.

        Migrating to this model required no adapter change because the request
        carried none of the fields it rejects. **That is a property worth
        keeping**, and nothing else enforces it: a later edit adding a thinking
        budget or forcing a tool call would be accepted by the composer and
        discovered as a 400 during a live run, which is the one place this
        project cannot afford to learn it.

        Args:
            furnished_case (EvaluationCase): A case carrying a system
                instruction and tools.

        Returns:
            None
        """
        composed = ClaudeAdapter().compose_request(furnished_case)

        # Thinking cannot be disabled and takes no budget on this model.
        thinking = composed.get("thinking", {})
        assert thinking.get("type") not in {"disabled", "enabled"}
        assert "budget_tokens" not in thinking

        # Forced tool use is rejected. Tool use is behaviour under test here, so
        # forcing a call would also measure the harness rather than the model.
        assert composed.get("tool_choice", {}).get("type") not in {"any", "tool"}

        # Computer use would be tool EXECUTION rather than capture, which Tier 2
        # does not do at all.
        declared = {tool.get("type") for tool in composed.get("tools") or []}
        assert "computer_20251124" not in declared

        # Sampling parameters were removed from this model family.
        assert not {"temperature", "top_p", "top_k"} & set(composed)


class TestMQCOpenAIAdapter:
    """What this provider does that the other two do not."""

    def MQC_EXE_UNI_113002_openai_maps_the_superseded_tool_call_finish_reason(self) -> None:
        """An older deployment still emits the previous spelling.

        Dropping it would record a successful tool call as an unknown outcome,
        and tool-use compliance would report a failure the model did not
        commit.

        Returns:
            None
        """
        adapter = OpenAIAdapter()
        for spelling in ("tool_calls", "function_call"):
            response = openai_response(
                tool_calls=[("search", {"query": "x"})], finish_reason=spelling
            )
            assert adapter.normalize_response(response, _CASE_ID).finish_reason == "tool_calls"

    def MQC_EXE_UNI_113003_openai_absent_tool_calls_field_yields_an_empty_list(self) -> None:
        """This provider omits the field rather than sending an empty list.

        A boundary rather than a positive: no tool call is the ordinary case,
        so the shape the inventory is likeliest to leave untested is the one
        that occurs most often.

        Returns:
            None
        """
        response = openai_response()
        assert response.choices[0].message.tool_calls is None
        normalized = OpenAIAdapter().normalize_response(response, _CASE_ID)
        assert not normalized.tool_calls

    def MQC_EXE_UNI_113010_openai_sends_the_system_instruction_as_a_message_role(
        self, furnished_case: EvaluationCase, minimal_case: EvaluationCase
    ) -> None:
        """This provider takes a message role where Anthropic takes a field.

        The instruction must lead the conversation. Appending it after the user
        prompt would make it a follow-up correction, which models follow at a
        different rate than an opening instruction.

        Args:
            furnished_case (Any): A case carrying a system instruction.
            minimal_case (Any): A case carrying none.

        Returns:
            None
        """
        adapter = OpenAIAdapter()
        messages = adapter.compose_request(furnished_case)["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == furnished_case.task.system_instruction
        assert all(
            entry["role"] != "system"
            for entry in adapter.compose_request(minimal_case)["messages"]
        )


class TestMQCGeminiAdapter:
    """What this provider does that the other two do not."""

    def MQC_EXE_UNI_113004_gemini_reads_the_resolved_version_from_its_own_field(self) -> None:
        """This provider names the resolved model differently from the other two.

        An adapter reading the field the other providers use would find nothing
        and abort preflight for a provider that answered correctly.

        Returns:
            None
        """
        response = gemini_response(resolved_model="gemini-flash-002")
        assert GeminiAdapter().resolve_model_version(response) == "gemini-flash-002"
        assert not hasattr(response, "model")

    def MQC_EXE_UNI_113005_gemini_reconciles_a_stop_reason_carrying_captured_calls(self) -> None:
        """This provider ends a tool-calling turn with the ordinary stop reason.

        The other two say so in the finish reason. Transcribing the literal
        value would make a cross-engine comparison of tool-use rates a
        comparison of vendor conventions, per design section 4.3.

        The derivation is narrow: a truncated turn keeps its own reason even
        when calls were captured, because truncation is the more important fact
        about that response.

        Returns:
            None
        """
        adapter = GeminiAdapter()
        calling = gemini_response(
            tool_calls=[("search", {"query": "x"})], finish_reason="STOP"
        )
        assert adapter.normalize_response(calling, _CASE_ID).finish_reason == "tool_calls"

        plain = gemini_response(finish_reason="STOP")
        assert adapter.normalize_response(plain, _CASE_ID).finish_reason == "stop"

        truncated = gemini_response(
            tool_calls=[("search", {"query": "x"})], finish_reason="MAX_TOKENS"
        )
        assert adapter.normalize_response(truncated, _CASE_ID).finish_reason == "length"

    def MQC_EXE_UNI_113006_gemini_a_blocked_candidate_yields_empty_text_not_an_error(self) -> None:
        """A blocked candidate carries no content at all, not empty content.

        Raising here would turn a model behaviour worth recording into a
        harness failure that records nothing, and a safety block is exactly the
        kind of result a security suite exists to observe.

        Returns:
            None
        """
        blocked = gemini_response(blocked=True, finish_reason="SAFETY")
        normalized = GeminiAdapter().normalize_response(blocked, _CASE_ID)
        assert normalized.text == ""
        assert not normalized.tool_calls
        assert normalized.finish_reason == "content_filter"

    def MQC_EXE_UNI_113007_gemini_disables_provider_side_automatic_function_calling(
        self, furnished_case: EvaluationCase
    ) -> None:
        """This SDK executes the model's tool calls unless told not to.

        A9 forbids tool execution, and relying on not passing tools is no
        defence because a tool case passes tools by definition. Left enabled,
        the harness would run a tool the model chose, on the machine running
        the suite, and record a multi-turn exchange as one response.

        Args:
            furnished_case (Any): A case carrying a tool definition.

        Returns:
            None
        """
        config = GeminiAdapter().compose_request(furnished_case)["config"]
        assert config["automatic_function_calling"] == {"disable": True}
        assert config["tools"][0]["function_declarations"][0]["name"] == "search_postings"

    @pytest.mark.parametrize(
        "kind,expected",
        [
            ("rate_limit", "QC_HARNESS_RATE_LIMIT"),
            ("auth", "QC_HARNESS_AUTH_ERROR"),
            ("not_found", "QC_HARNESS_VERSION_UNAVAILABLE"),
            ("timeout", "QC_HARNESS_CANDIDATE_TIMEOUT"),
        ],
    )
    def MQC_EXE_UNI_113008_gemini_maps_each_error_status_to_its_harness_code(
        self, kind: str, expected: Any
    ) -> None:
        """This provider raises one class for every client failure.

        The distinction lives in the status code, so the adapter maps statuses
        rather than exception types. An adapter matching on the class alone
        would record every provider failure as the same code.

        Args:
            kind (str): Which failure to raise.
            expected (str): The harness code it must map to.

        Returns:
            None
        """
        assert GeminiAdapter().map_error(gemini_error(kind)) == expected


    def MQC_EXE_UNI_113016_gemini_reads_the_spent_period_from_the_quota_id(self) -> None:
        """The period is taken from the quota id, not from the retry hint.

        **The provider's own hint is wrong for this condition.** The body below
        quotes a `retryDelay` of 52 seconds beside a quota that resets once a
        day, so anything honouring that hint would retry until the day turned.
        The quota id is what carries the truth, and it spells the period.

        Returns:
            None
        """
        adapter = GeminiAdapter()

        assert adapter.period_quota_exhausted(RuntimeError(_SPENT_DAY_BODY)) is True
        # A PER-MINUTE LIMIT IS A DIFFERENT CONDITION with a different remedy,
        # and it keeps its retry.
        per_minute = _SPENT_DAY_BODY.replace("PerDay", "PerMinute")
        assert adapter.period_quota_exhausted(RuntimeError(per_minute)) is False
        # AN UNRECOGNISED BODY FAILS OPEN rather than abandoning the attempts.
        assert adapter.period_quota_exhausted(RuntimeError("429 too many")) is False

    def MQC_EXE_UNI_113017_every_adapter_reports_the_four_token_counts(self) -> None:
        """Each provider spells them differently, and all four are read.

        **Three of the four were being discarded.** Every adapter read its usage
        object and kept only the output count, while the input count sat in the
        same object unread: input is the larger half for this corpus, so every
        cost figure the harness could have produced was wrong in one direction.

        **The doubles report distinct values per category** so an adapter that
        read the wrong field cannot pass by coincidence.

        Returns:
            None
        """
        for engine in sorted(registered_engines()):
            adapter = adapter_for(engine)()
            response = ADAPTER_DOUBLES[engine].response(text="An answer.")
            usage = adapter.read_usage(response)

            assert usage.input_tokens > 0, f"{engine} reported no input count"
            assert usage.output_tokens > 0, f"{engine} reported no output count"
            assert usage.cached_input_tokens > 0, f"{engine} reported no cache count"
            # NORMALIZING AND READING DIRECTLY MUST AGREE, because the candidate
            # path uses the first and the judge path the second.
            assert adapter.normalize_response(response, "case").usage == usage

    def MQC_EXE_UNI_113018_thinking_is_counted_only_where_reported_separately(
        self,
    ) -> None:
        """Anthropic folds thinking into output; the others report it apart.

        **Populating a thinking field for Anthropic would double it.** Its
        `output_tokens` already includes thinking, and section 5A.2 records that
        thinking cannot be disabled on that model, so the output count always
        carries some. Reporting it twice would inflate the one engine whose
        thinking is least avoidable.

        Returns:
            None
        """
        separate = adapter_for("gemini")().read_usage(
            ADAPTER_DOUBLES["gemini"].response(text="x")
        )
        folded = adapter_for("claude")().read_usage(
            ADAPTER_DOUBLES["claude"].response(text="x")
        )

        assert separate.thinking_tokens > 0, "gemini reports thinking apart"
        assert folded.thinking_tokens == 0, (
            "anthropic includes thinking in its output count, so counting it "
            "again here would bill it twice"
        )

    def MQC_EXE_UNI_113019_a_response_carrying_no_usage_reports_zero_not_an_error(
        self,
    ) -> None:
        """A provider that sent no usage object is not a failure.

        **Zero, and zero means no tokens rather than no price.** An unpriced
        model yields ``None`` from the cost function, which is a different
        condition with a different remedy: price the model, against report the
        usage the provider withheld.

        Returns:
            None
        """
        for engine in sorted(registered_engines()):
            usage = adapter_for(engine)().read_usage(object())
            assert usage == TokenUsage(), f"{engine} invented a count"

    def MQC_EXE_UNI_113020_a_refused_prompt_is_recorded_with_its_reason_and_stage(
        self,
    ) -> None:
        """Zero candidates is the shape of a refusal, and it carried no reason.

        **The double had the wrong shape, which is why nothing caught this.** It
        built one candidate whose content was absent, while a prompt refused
        before generation returns **no candidate at all** and explains itself in
        `prompt_feedback`. So `154002` was reported as a model failure for three
        recorded runs.

        **The stage is recorded although both stages count the same today.** A
        prompt refused before generation and a response stopped midway are
        different events, and a corpus that stored only "blocked" could not be
        split afterwards if the requirement changed.

        Returns:
            None
        """
        adapter = adapter_for("gemini")()

        refused = adapter.normalize_response(gemini_blocked_prompt("OTHER"), "case")
        assert refused.block_reason == "OTHER"
        assert refused.block_stage == "prompt"
        assert refused.blocked_by_provider is True
        assert refused.produced_output is False

        # RESPONSE STAGE: generation began and the provider stopped it.
        stopped = adapter.normalize_response(
            gemini_response(text="", finish_reason="SAFETY"), "case"
        )
        assert stopped.block_reason == "SAFETY"
        assert stopped.block_stage == "response"

        # AND AN ORDINARY REPLY CLAIMS NEITHER.
        ordinary = adapter.normalize_response(gemini_response(text="hello"), "case")
        assert not ordinary.block_reason
        assert not ordinary.block_stage
        assert ordinary.blocked_by_provider is False



    def MQC_EXE_UNI_113021_the_judgement_schema_drops_keywords_the_provider_rejects(
        self,
    ) -> None:
        """No judgement had ever reached this provider, and nothing said so.

        Every judgement returned `400 INVALID_ARGUMENT` naming
        `additional_properties` as a field it cannot find: Gen AI's
        `response_schema` takes a restricted OpenAPI subset rather than JSON
        Schema. **The whole `EVAL` family was unjudgeable live**, and the
        security family did not reveal it because those rules carry no rubric.

        **The schema Tier 3 composed is not wrong and is not changed.**
        `additionalProperties: false` is what makes the reply validation strict:
        a judge returning a criterion nobody asked for must fail, and
        `_require_schema_valid` reads the same schema. So the adapter translates
        it for the wire, which is where a provider's constraints belong.

        Returns:
            None
        """
        adapter = adapter_for("gemini")()
        # THE SCHEMA TIER 3 ACTUALLY COMPOSES, not a hand-copy of its shape. A
        # literal here would assert against my memory of the builder rather than
        # the builder, and the builder is what the provider rejected.
        strict = compose_judge_request(
            "MQC_TASK_probe::MQC_RULE_probe",
            _rubric_with("C_ONE"),
            UnauthoredMaterial(candidate_output="An answer.", task_instruction="Ask."),
        ).reply_schema
        assert "additionalProperties" in json.dumps(strict), (
            "the composed schema no longer carries the keyword this translates, "
            "so the case is asserting nothing"
        )

        composed = adapter.compose_judgement("Score it.", strict)
        sent = composed["config"]["response_schema"]

        # NESTED OCCURRENCES TOO, because the rejection named both the root and
        # a property: removing only the outer one would still be a 400.
        assert "additionalProperties" not in json.dumps(sent)
        # AND NOTHING ELSE IS LOST. The structure the judge must reply in is
        # what constrains the reply, so dropping a keyword must not drop a field.
        assert sent["required"] == ["scores"]
        assert "C_ONE" in sent["properties"]["scores"]["properties"]
        # THE CALLER'S SCHEMA IS UNTOUCHED, because Tier 3 validates the reply
        # against it and needs the strictness the wire cannot carry.
        assert "additionalProperties" in json.dumps(strict)

class TestMQCWireProtocolReuse:
    """Adding an engine on a served protocol costs four values."""

    def MQC_EXE_UNI_113013_an_engine_on_a_shared_protocol_inherits_it_entire(
        self,
    ) -> None:
        """Grok overrides no protocol method, which is the whole claim.

        **Asserted structurally rather than behaviourally.** Checking that
        Grok composes a correct request would pass just as well against a
        copy-pasted module, which is exactly the duplication this removes. What
        is asserted is that the functions **are the same objects**, so there is
        no second copy to drift.

        Args:
            None

        Returns:
            None
        """
        inherited = [
            "compose_request",
            "dispatch",
            "normalize_response",
            "extract_tool_calls",
            "resolve_model_version",
            "map_error",
            "declare_capabilities",
            # JUDGING TOO. An engine on a served protocol can judge the day it
            # is registered, which is the property design section 3.3 claims.
            "compose_judgement",
            "parse_judgement",
        ]
        for name in inherited:
            assert getattr(GrokAdapter, name) is getattr(OpenAICompatibleAdapter, name), (
                f"GrokAdapter overrides {name}, so the protocol has a second "
                f"copy that can drift from the first"
            )

        # AND IT IS STILL ITS OWN ENGINE, or inheriting everything would mean
        # inheriting the identity as well.
        assert GrokAdapter().engine_name == "grok"
        assert GrokAdapter().requested_model != OpenAIAdapter().requested_model
        assert "grok" in registered_engines()

    def MQC_EXE_UNI_113014_two_engines_on_one_protocol_do_not_share_a_credential(
        self, monkeypatch: Any
    ) -> None:
        """Each engine resolves its own endpoint and its own variable.

        **`BASE_URL` is the only field that routes a request.** An engine
        omitting it reaches the SDK's default vendor holding another vendor's
        key, which surfaces as an authentication failure naming the wrong
        vendor and sends the reader to the wrong dashboard.

        **The values here are synthetic.** No real credential is read, and the
        assertion is on which variable was consulted rather than on what it
        held.

        Args:
            monkeypatch (Any): pytest's patcher, for a synthetic environment.

        Returns:
            None
        """
        monkeypatch.setenv("OPENAI_API_KEY", "synthetic-openai")
        monkeypatch.setenv("XAI_API_KEY", "synthetic-xai")

        openai_options = OpenAIAdapter().client_options()
        grok_options = GrokAdapter().client_options()

        assert grok_options["base_url"] == "https://api.x.ai/v1"
        assert "base_url" not in openai_options, (
            "OpenAI declared an endpoint, so it is no longer the SDK default "
            "and a change to it would silently reroute the other engines"
        )
        assert grok_options["api_key"] != openai_options["api_key"]

        # AND AN ABSENT VARIABLE IS OMITTED, never passed empty, so the SDK
        # raises its own error naming what it looked for.
        monkeypatch.delenv("XAI_API_KEY")
        assert "api_key" not in GrokAdapter().client_options()


class TestMQCEngineRoles:
    """Who may be a candidate, and who may judge."""

    def MQC_EXE_UNI_113015_a_role_is_derived_from_the_registry_not_a_list(
        self,
    ) -> None:
        """Both roles follow from the registry and a declared capability.

        **A list is a second place to forget.** `config/engines.yaml` has
        always said any engine declaring `structured_output` may judge, with
        deliberately no list of permitted judge engines to keep in step with
        the adapters. This asserts the sentence rather than restating it.

        **Grok is the evidence.** It arrived in both roles in one registration,
        because the capability came with the protocol it serves.

        Args:
            None

        Returns:
            None
        """
        candidates = engines_for_role(CANDIDATE_ROLE)
        judges = engines_for_role(JUDGE_ROLE)

        assert candidates == registered_engines(), (
            "candidacy is not registration, so some engine is registered and "
            "cannot be dispatched against"
        )
        assert set(judges) <= set(candidates)
        assert "grok" in candidates and "grok" in judges

        # DERIVED, NOT LISTED: every judge declares the capability, and every
        # engine declaring it is a judge. Both directions, or a list could
        # still be hiding behind an agreeing answer.
        for engine in candidates:
            declared = adapter_for(engine)().declare_capabilities()
            assert (engine in judges) == declared.structured_output, (
                f"{engine} declares structured_output="
                f"{declared.structured_output} and is "
                f"{'in' if engine in judges else 'not in'} the judge role"
            )

        with pytest.raises(ValueError, match="is not a role"):
            engines_for_role("referee")
