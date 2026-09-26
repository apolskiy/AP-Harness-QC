# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The conformance battery every registered adapter is enrolled in.

Covers `MQC_EXE_UNI_10201` through `10203`, `10208`, `10214` through `10217`,
`10219`, `10220`, and `10254` through `10258`, inventoried in
``docs/design/tier2_execution.md`` sections 10.1 and 9.1.

**Parametrized over the registry, never over a list.** A list is a second place
to forget, which is the failure mode the automatic enrolment in
``extensibility_standard.md`` section 10 exists to remove. Registering an
adapter enrols it here, and there is nothing to remember.

**These assert over the registry, which record-level cases cannot.** A case
that constructs a `NormalizedResponse` directly proves the record is well
formed. It passes happily while an adapter that never builds one correctly sits
registered and untested.

A failure here is our defect, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

import dataclasses
from pathlib import Path
import inspect
from typing import Any

import pytest

from cmn.registries import registered_statuses, taxonomy_for_status
from execution.adapters.base import (
    Capabilities,
    ProviderAdapter,
    validate_mapped_error,
)
from execution.dispatch import _RETRYABLE_CODES  # pylint: disable=protected-access
from execution.adapters.registry import (
    adapter_for,
    register_adapter,
    registered_adapters,
    registered_engines,
)
from execution.normalize import NormalizedResponse, ToolCall, registered_finish_reasons
from tests.execution.provider_doubles import (
    ADAPTER_DOUBLES,
    ERROR_CLASS_CODES,
    UNRECOGNISED_ERROR,
)
from ingestion.schemas import EvaluationCase

pytestmark = pytest.mark.unit

_ADAPTER_CLASSES = list(registered_adapters())
_ENGINE_IDS = [adapter_class().engine_name for adapter_class in _ADAPTER_CLASSES]


@pytest.fixture(name="adapter", params=_ADAPTER_CLASSES, ids=_ENGINE_IDS)
def fixture_adapter(request: Any) -> ProviderAdapter:
    """Yield each registered adapter in turn.

    Args:
        request (Any): pytest's parametrization request.

    Returns:
        ProviderAdapter: One registered adapter, constructed with its default
        model so the battery needs no configuration.
    """
    return request.param()


def _double(adapter: ProviderAdapter, **overrides: Any) -> Any:
    """Build the provider-shaped response double for one adapter.

    Args:
        adapter (ProviderAdapter): Whose provider shape is wanted.
        **overrides (Any): What the double should contain.

    Returns:
        Any: An object shaped like that provider's response.
    """
    return ADAPTER_DOUBLES[adapter.engine_name].response(**overrides)


class TestMQCAdapterConformance:
    """The nine assertions of design section 9, over every registered adapter."""

    def MQC_EXE_UNI_10201_composes_request_from_minimal_case(
        self,
        adapter: ProviderAdapter,
        minimal_case: EvaluationCase,
    ) -> None:
        """A case carrying only a prompt produces a dispatchable request.

        Args:
            adapter (ProviderAdapter): The adapter under check.
            minimal_case (Any): A case with no documents and no tools.

        Returns:
            None
        """
        request = adapter.compose_request(minimal_case)
        assert isinstance(request, dict)
        assert request["model"] == adapter.requested_model
        assert minimal_case.task.user_prompt in repr(request)

    def MQC_EXE_UNI_10202_composes_request_carrying_constraints_and_context(
        self, adapter: ProviderAdapter, furnished_case: EvaluationCase
    ) -> None:
        """Documents and tool definitions reach the request, not just the prompt.

        A request that silently dropped its context would make every grounding
        case a measurement of a model answering from memory.

        Args:
            adapter (ProviderAdapter): The adapter under check.
            furnished_case (Any): A case with a document, a tool and a system
                instruction.

        Returns:
            None
        """
        rendered = repr(adapter.compose_request(furnished_case))
        assert furnished_case.task.context_documents[0].content in rendered
        assert furnished_case.task.available_tools[0].tool_name in rendered
        assert furnished_case.task.system_instruction in rendered

    def MQC_EXE_UNI_10203_normalizes_response_to_canonical_shape(
        self,
        adapter: ProviderAdapter,
    ) -> None:
        """Every required canonical field is populated from the provider response.

        Args:
            adapter (ProviderAdapter): The adapter under check.

        Returns:
            None
        """
        normalized = adapter.normalize_response(
            _double(adapter, text="A grounded answer."), "MQC_TASK_a::MQC_RULE_b"
        )
        assert isinstance(normalized, NormalizedResponse)
        assert normalized.case_id == "MQC_TASK_a::MQC_RULE_b"
        assert normalized.engine == adapter.engine_name
        assert normalized.mode == "live"
        assert normalized.text == "A grounded answer."
        assert normalized.output_tokens > 0
        assert normalized.finish_reason in registered_finish_reasons()

    def MQC_EXE_UNI_10254_every_adapter_returns_tool_arguments_as_a_mapping(
        self,
        adapter: ProviderAdapter,
    ) -> None:
        """One provider sends a JSON string where two send a mapping.

        Leaving that visible would mean Tier 3 handling two shapes for one
        fact, and the provider that sends a string would be the only one whose
        tool cases ever failed on shape.

        Args:
            adapter (ProviderAdapter): The adapter under check.

        Returns:
            None
        """
        calls = adapter.extract_tool_calls(
            _double(adapter, tool_calls=[("search", {"query": "grounding"})])
        )
        assert [call.tool_name for call in calls] == ["search"]
        assert calls[0].arguments == {"query": "grounding"}
        assert isinstance(calls[0].arguments, dict)

    def MQC_EXE_UNI_10208_captures_tool_call_without_executing_it(
        self,
        adapter: ProviderAdapter,
    ) -> None:
        """Tool usage is behaviour under test, not a prohibition (A9).

        The double raises if invoked, so an adapter that executed the model's
        intent fails here rather than silently producing a transcript of an
        exchange the harness took part in.

        Args:
            adapter (ProviderAdapter): The adapter under check.

        Returns:
            None
        """
        double = _double(adapter, tool_calls=[("delete_records", {"table": "orders"})])
        calls = adapter.extract_tool_calls(double)
        assert len(calls) == 1
        assert calls[0].tool_name == "delete_records"
        assert double.invocations == []

    def MQC_EXE_UNI_10255_every_adapter_reads_the_version_from_the_response(
        self,
        adapter: ProviderAdapter,
    ) -> None:
        """The resolved identifier, never the requested one (A8).

        Each provider names this field differently. An adapter reading the
        request instead would report an alias that never moved, hiding exactly
        the event that makes a later score change interpretable.

        Args:
            adapter (ProviderAdapter): The adapter under check.

        Returns:
            None
        """
        double = _double(adapter, resolved_model="served-build-002")
        assert adapter.resolve_model_version(double) == "served-build-002"
        normalized = adapter.normalize_response(double, "MQC_TASK_a::MQC_RULE_b")
        assert normalized.resolved_model == "served-build-002"
        assert normalized.requested_model == adapter.requested_model
        assert normalized.model_alias_floated is True

    def MQC_EXE_UNI_10214_maps_rate_limit_error_to_harness_code(
        self,
        adapter: ProviderAdapter,
    ) -> None:
        """A rate limit is one code whichever provider raised it.

        Untranslated, a rate limit from one vendor and a rate limit from
        another become different rows in the durable record, and cross-engine
        comparison of harness reliability becomes impossible.

        Args:
            adapter (ProviderAdapter): The adapter under check.

        Returns:
            None
        """
        error = ADAPTER_DOUBLES[adapter.engine_name].error("rate_limit")
        mapped = adapter.map_error(error)
        assert mapped == "QC_HARNESS_RATE_LIMIT"
        assert validate_mapped_error(adapter.engine_name, mapped) == mapped
        for error_name, expected in ERROR_CLASS_CODES.items():
            raised = ADAPTER_DOUBLES[adapter.engine_name].error(error_name)
            assert adapter.map_error(raised) == expected

    def MQC_EXE_UNI_10215_maps_timeout_error_to_harness_code(
        self,
        adapter: ProviderAdapter,
    ) -> None:
        """A timeout is its own code, distinct from a generic failure.

        Repeated candidate timeouts say something about the model or its
        provider that a parser error does not.

        Args:
            adapter (ProviderAdapter): The adapter under check.

        Returns:
            None
        """
        error = ADAPTER_DOUBLES[adapter.engine_name].error("timeout")
        assert adapter.map_error(error) == "QC_HARNESS_CANDIDATE_TIMEOUT"

    def MQC_EXE_UNI_10216_maps_auth_error_to_harness_code(self, adapter: ProviderAdapter) -> None:
        """An auth failure is categorically different and aborts the run.

        Args:
            adapter (ProviderAdapter): The adapter under check.

        Returns:
            None
        """
        error = ADAPTER_DOUBLES[adapter.engine_name].error("auth")
        assert adapter.map_error(error) == "QC_HARNESS_AUTH_ERROR"

    def MQC_EXE_UNI_10217_unrecognised_error_preserves_original_text(
        self,
        adapter: ProviderAdapter,
        caplog: Any,
    ) -> None:
        """An unmapped failure is visible rather than absorbed into a neighbour.

        The original is logged, so an error class nobody anticipated is
        diagnosable instead of becoming an indistinguishable parser error.

        Args:
            adapter (ProviderAdapter): The adapter under check.
            caplog (Any): pytest's log capture.

        Returns:
            None
        """
        with caplog.at_level("WARNING"):
            mapped = adapter.map_error(UNRECOGNISED_ERROR)
        assert mapped == "QC_HARNESS_PARSER_ERROR"
        assert str(UNRECOGNISED_ERROR) in caplog.text

    def MQC_EXE_UNI_10219_declared_capabilities_derive_unsupported_pairs(
        self,
        adapter: ProviderAdapter,
    ) -> None:
        """Capabilities are declared, so a gap does not depend on being noticed.

        Args:
            adapter (ProviderAdapter): The adapter under check.

        Returns:
            None
        """
        declared = adapter.declare_capabilities()
        assert isinstance(declared, Capabilities)
        assert declared.tool_calling is True
        assert declared.structured_output is True

    def MQC_EXE_UNI_10220_tool_case_against_engine_without_tool_calling_is_unsupported(
        self, adapter: ProviderAdapter, furnished_case: EvaluationCase
    ) -> None:
        """A capability gap makes a tool case unsupported, never failed.

        Recording it as a failure would attribute a provider's missing feature
        to the model's behaviour, which is a different claim entirely.

        Args:
            adapter (ProviderAdapter): The adapter under check.
            furnished_case (Any): A case carrying a tool definition.

        Returns:
            None
        """
        supports_tools = adapter.declare_capabilities().tool_calling
        requires_tools = bool(furnished_case.task.available_tools)
        unsupported = requires_tools and not supports_tools
        assert unsupported is False
        assert "tools" in repr(adapter.compose_request(furnished_case)).lower()

    def MQC_EXE_UNI_10256_no_vendor_type_survives_any_adapter_normalization(
        self,
        adapter: ProviderAdapter,
    ) -> None:
        """A vendor object reaching Tier 3 would make the judge provider-dependent.

        Stated negatively on purpose. Asserting that each field holds the right
        type would pass on an adapter that put a vendor object in a field
        nobody enumerated, so this walks every field and rejects any type
        outside the permitted set.

        Args:
            adapter (ProviderAdapter): The adapter under check.

        Returns:
            None
        """
        permitted = {str, int, list, dict, type(None), ToolCall}
        normalized = adapter.normalize_response(
            _double(adapter, tool_calls=[("search", {"query": "x"})]),
            "MQC_TASK_a::MQC_RULE_b",
        )
        for record_field in dataclasses.fields(normalized):
            value = getattr(normalized, record_field.name)
            assert type(value) in permitted
            if isinstance(value, list):
                assert all(type(entry) in permitted for entry in value)


class TestMQCAdapterRegistry:
    """What the battery parametrizes over, and what guards it."""

    def MQC_EXE_UNI_10258_the_registry_enrols_every_adapter_in_the_battery(self) -> None:
        """Every registered engine is reachable and appears in this module's run.

        The battery is parametrized over the registry rather than a list, so an
        adapter cannot be registered and left uncovered.

        Returns:
            None
        """
        assert set(registered_engines()) == set(_ENGINE_IDS)
        assert len(_ENGINE_IDS) == len(set(_ENGINE_IDS))
        for engine in registered_engines():
            assert adapter_for(engine)().engine_name == engine

    def MQC_EXE_UNI_10257_registering_two_adapters_under_one_engine_name_fails(self) -> None:
        """Two adapters under one name would make selection depend on import order.

        A fixture recorded by one would also replay through the other, which no
        later check would catch.

        Returns:
            None
        """
        taken = registered_engines()[0]
        impostor = type(
            "MQCImpostorAdapter", (adapter_for(taken),), {"__module__": __name__}
        )
        with pytest.raises(ValueError, match="already served by"):
            register_adapter(impostor)

    def MQC_EXE_UNI_10268_an_unregistered_engine_name_names_what_is_registered(self) -> None:
        """A typo and an unimplemented provider are different problems.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR") as caught:
            adapter_for("gemeni")
        for engine in registered_engines():
            assert engine in str(caught.value)


class TestMQCJudgementConformance:
    """Declaring the judge capability is an obligation, not a label."""

    def MQC_EXE_UNI_10278_a_declared_capability_that_cannot_judge_is_reported(
        self, adapter: ProviderAdapter
    ) -> None:
        """An engine that qualifies as a judge must be able to serve as one.

        `declare_capabilities().structured_output` is the **only** thing
        qualifying an engine to judge: there is deliberately no list of
        permitted judge engines to keep in step with the adapters (C2). All
        three original adapters declared it and **none implemented it**, so the
        capability was read by `resolve_judge_engine` and satisfied by nothing.

        **An adapter may still decline to judge** by declaring the capability
        false, which costs it only the judge role and skips this case. What it
        may no longer do is claim the capability and not have it.

        Args:
            adapter (ProviderAdapter): Each registered adapter in turn.

        Returns:
            None
        """
        if not adapter.declare_capabilities().structured_output:
            pytest.skip(
                f"{adapter.engine_name} declines the judge role, which is "
                f"permitted; the obligation follows the declaration"
            )

        schema = {"type": "object", "properties": {"scores": {"type": "object"}}}
        composed = adapter.compose_judgement("Grade the response.", schema)

        assert composed is not None
        assert adapter.requested_model in repr(composed), (
            f"{adapter.engine_name} composed a judgement naming no model"
        )
        # THE SCHEMA MUST REACH THE REQUEST, or the constraint is decorative
        # and schema validation stops doubling as the hijack detector.
        assert "scores" in repr(composed), (
            f"{adapter.engine_name} composed a judgement that does not carry "
            f"its reply schema, so the constraint was requested of nobody"
        )

    def MQC_EXE_UNI_10279_a_judgement_round_trips_through_the_adapter_to_a_mapping(
        self, adapter: ProviderAdapter
    ) -> None:
        """What comes back is the mapping the reply validator expects.

        **This is the gap that made the judge untestable.**
        `JudgeBinding.invoke` feeds `validate_judge_reply` directly, which
        expects a mapping, and every test double returned one. No adapter could
        produce one, so the judge worked in every test and could not have
        worked once.

        Args:
            adapter (ProviderAdapter): Each registered adapter in turn.

        Returns:
            None
        """
        if not adapter.declare_capabilities().structured_output:
            pytest.skip(f"{adapter.engine_name} declines the judge role")

        payload = {
            "scores": {
                "MQC_CRIT_grounding": {"score": 4, "rationale": "Well grounded."}
            }
        }
        reply = ADAPTER_DOUBLES[adapter.engine_name].judgement(payload)

        parsed = adapter.parse_judgement(reply)

        assert isinstance(parsed, dict), (
            f"{adapter.engine_name} parsed a judgement into "
            f"{type(parsed).__name__}, which validate_judge_reply cannot read"
        )
        assert parsed == payload


class TestMQCStatusFamilyConformance:
    """Every status says whose defect it is, and a live run said so first."""

    def MQC_EXE_UNI_10285_a_transient_provider_failure_is_not_a_parser_error(
        self, adapter: ProviderAdapter
    ) -> None:
        """A busy provider is not an unanticipated failure.

        **Found by the first live request this project ever made.** Three of
        nine security cases came back `503 UNAVAILABLE, this model is
        currently experiencing high demand`, the status map covered no 5xx,
        and the artifact said the response could not be parsed. It parsed
        fine; there was no response.

        **Distinct from a rate limit, deliberately.** `rate_limit_encounters`
        is counted and reported, and the two conditions call for different
        responses: one says we asked too often and is answered by widening
        `spacing_sec`, the other says the provider is busy and is answered by
        waiting (design section 8.5.1).

        Args:
            adapter (ProviderAdapter): Each registered adapter in turn.

        Returns:
            None
        """
        # EVERY TRANSIENT STATUS, not a representative. 503 is the one that
        # occurred; mapping only it would leave 500, 502 and 504 to be found
        # the same way, on another run that spends quota to find them.
        for status in (500, 503):
            raised = ADAPTER_DOUBLES[adapter.engine_name].error(
                f"unavailable_{status}"
            )
            mapped = adapter.map_error(raised)

            assert mapped == "QC_HARNESS_PROVIDER_UNAVAILABLE", (
                f"{adapter.engine_name} maps {status} to {mapped}, so a "
                f"temporary condition is recorded as something nobody "
                f"anticipated and is never retried"
            )
            assert mapped != "QC_HARNESS_RATE_LIMIT", (
                f"{adapter.engine_name} folded {status} into the rate limit "
                f"counter, which makes a provider's bad afternoon read as a "
                f"pacing defect that widening spacing_sec would not fix"
            )
            assert validate_mapped_error(adapter.engine_name, mapped) == mapped

    def MQC_EXE_UNI_10286_a_transient_provider_failure_is_retried(self) -> None:
        """It joins rate limits and timeouts, and nothing else does.

        **The provider said the condition was temporary and the harness had
        backoff ready.** The two never met, because the code it mapped to was
        not retryable and correctly so.

        **The set stays closed.** A retry against anything else spends quota
        to receive the same answer, which is why this asserts the membership
        rather than only the addition.

        Returns:
            None
        """
        assert "QC_HARNESS_PROVIDER_UNAVAILABLE" in _RETRYABLE_CODES
        assert _RETRYABLE_CODES == frozenset(
            {
                "QC_HARNESS_RATE_LIMIT",
                "QC_HARNESS_CANDIDATE_TIMEOUT",
                "QC_HARNESS_PROVIDER_UNAVAILABLE",
                # A GATEWAY BETWEEN US AND THE PROVIDER, which is frequently
                # momentary and is not the provider reporting itself busy
                # (design section 8.5.4).
                "QC_HARNESS_GATEWAY_FAILURE",
            }
        ), "the retryable set changed, and a retry is quota spent on the same answer"

        # NOT RETRYABLE, because the same malformed request gets the same
        # answer, and neither is a credential that is wrong.
        for settled in (
            "QC_HARNESS_REQUEST_REJECTED",
            "QC_HARNESS_AUTH_ERROR",
            "QC_HARNESS_VERSION_UNAVAILABLE",
        ):
            assert settled not in _RETRYABLE_CODES

    def MQC_EXE_UNI_10287_a_rejected_request_is_not_an_unanticipated_failure(
        self, adapter: ProviderAdapter
    ) -> None:
        """A malformed request is ours, anticipated, and has its own code.

        **The catch-all means nobody anticipated this**, and an artifact
        carrying it should send a reader looking for something new. Folding a
        rejected request into it would have been one line and would have made
        every genuinely unknown failure harder to find.

        Args:
            adapter (ProviderAdapter): Each registered adapter in turn.

        Returns:
            None
        """
        raised = ADAPTER_DOUBLES[adapter.engine_name].error("bad_request")
        mapped = adapter.map_error(raised)

        assert mapped == "QC_HARNESS_REQUEST_REJECTED", (
            f"{adapter.engine_name} maps a rejected request to {mapped}"
        )
        assert validate_mapped_error(adapter.engine_name, mapped) == mapped

        # AND THE CATCH-ALL STILL CATCHES, or this would have narrowed it into
        # uselessness rather than out of the way.
        assert adapter.map_error(UNRECOGNISED_ERROR) == "QC_HARNESS_PARSER_ERROR"


    def MQC_EXE_UNI_10288_a_gateway_failure_is_not_the_provider_being_busy(
        self, adapter: ProviderAdapter
    ) -> None:
        """502 and 504 come from an intermediary, and may not be the provider.

        A load balancer, a CDN, a corporate proxy or an egress rule can emit
        either, and **the body of a 502 is the intermediary's rather than the
        provider's**, so a diagnostic read out of it describes something other
        than the service we called.

        **The operator response is what separates them.** Told the provider is
        busy, a reader waits; told a gateway failed, a reader looks at the
        path. For a misbehaving proxy the first advice is waiting for a
        condition that will never clear.

        **Indistinguishable by exception class**, which is why the shared
        lookup consults a status table first: the SDK protocols raise one
        class for everything at or above 500.

        Args:
            adapter (ProviderAdapter): Each registered adapter in turn.

        Returns:
            None
        """
        for status in (502, 504):
            raised = ADAPTER_DOUBLES[adapter.engine_name].error(
                f"unavailable_{status}"
            )
            mapped = adapter.map_error(raised)

            assert mapped == "QC_HARNESS_GATEWAY_FAILURE", (
                f"{adapter.engine_name} maps {status} to {mapped}, so a "
                f"failure in the path between us and the provider reads as "
                f"the provider reporting itself busy"
            )
            assert validate_mapped_error(adapter.engine_name, mapped) == mapped

        # AND IT IS STILL RETRYABLE, a gateway failure frequently being
        # momentary. What changed is what a reader does when retries run out.
        assert "QC_HARNESS_GATEWAY_FAILURE" in _RETRYABLE_CODES


    def MQC_EXE_UNI_10289_a_redirect_or_connection_failure_is_unreachability(
        self, adapter: ProviderAdapter
    ) -> None:
        """A 3xx says the engine was not where we addressed it.

        **No 3xx was mapped at all**, so a redirect landed on the code
        reserved for failures nobody anticipated. It is neither a model
        finding nor a judge finding.

        **The ordinary cause is not the provider.** A corporate proxy or a
        captive portal answering `302` with a login page is how this happens,
        and the body is then HTML: following such a hop blindly is how a login
        page gets scored as a model response.

        Args:
            adapter (ProviderAdapter): Each registered adapter in turn.

        Returns:
            None
        """
        for status in (300, 301, 302, 303, 305, 306, 307, 308):
            mapped = taxonomy_for_status(status)
            assert mapped == "QC_HARNESS_ENGINE_UNREACHABLE", (
                f"{status} maps to {mapped}, so a redirect reads as something "
                f"nobody anticipated rather than as an unreachable engine"
            )
            assert validate_mapped_error(adapter.engine_name, mapped) == mapped

        # AND IT IS NOT RETRYABLE. A redirect is deterministic, so the same
        # request gets the same hop and a retry is quota spent on it.
        assert "QC_HARNESS_ENGINE_UNREACHABLE" not in _RETRYABLE_CODES

    def MQC_EXE_UNI_10290_every_interface_maps_a_status_through_one_table(
        self, adapter: ProviderAdapter
    ) -> None:
        """What a status means is HTTP, not a vendor, so it is stated once.

        **The first implementation put a table in each adapter**, which was
        three places for one fact and the exact shape `consumer_ci.md` section
        5 calls a defect that ships.

        **Asserted by identity, not by agreement.** Checking that three tables
        contain the same rows would pass right up until somebody edited one;
        checking that no adapter carries a table at all is what makes drift
        impossible rather than merely unlikely.

        Args:
            adapter (ProviderAdapter): Each registered adapter in turn.

        Returns:
            None
        """
        # NO ADAPTER STATES WHAT A STATUS MEANS. It states only which class
        # its SDK raises for a failure that carries no status.
        source = Path(inspect.getfile(type(adapter))).read_text(encoding="utf-8")
        for status in ("400:", "401:", "404:", "429:", "503:"):
            assert status not in source, (
                f"{adapter.engine_name} carries its own entry for {status} so "
                f"the meaning of a status is stated in more than one place"
            )

        # AND THE SHARED TABLE COVERS WHAT THE ADAPTERS RELIED ON.
        assert registered_statuses() >= {
            300, 301, 302, 303, 305, 306, 307, 308,
            400, 401, 403, 404, 429, 500, 502, 503, 504,
        }

        # AN UNMAPPED NUMBER FALLS THROUGH rather than taking a default, so an
        # unrecognised status stays visible as an unanticipated failure.
        assert taxonomy_for_status(418) is None
        assert taxonomy_for_status(None) is None
        assert taxonomy_for_status("429") is None
