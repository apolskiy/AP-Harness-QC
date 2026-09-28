# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The one interface every provider adapter implements.

Specified by ``docs/design/tier2_execution.md`` section 3.

**This is a stable interface** under ``extensibility_standard.md`` section 9:
it may gain an optional parameter with a default and may never gain a required
one. A required parameter would break every adapter written before it, which is
the guarantee stability means.

**An adapter normalizes and hands over. It does not evaluate.** An adapter that
begins interpreting output has become a second evaluator with no rubric, and
nothing downstream would know its opinion was being mixed into a score.

**Tier 2 does not screen for injection.** The post-execution screen belongs to
Tier 3 ingress, on the principle that the component the untrusted content
threatens owns its own defence (A5c).
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from cmn.tokens import TokenUsage
from cmn.registries import is_adapter_error_code, taxonomy_for_status
from execution.normalize import NormalizedResponse, ToolCall

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Capabilities:
    """What a provider supports, declared rather than discovered.

    Unsupported pairs are **derived** from these rather than hand-maintained,
    so a capability gap does not depend on someone noticing it and writing a
    configuration entry.

    Attributes:
        tool_calling (bool): When false, every tool case for this engine becomes
            an unsupported pair rather than a failure.
        structured_output (bool): When false, this engine cannot serve as judge.
        system_instruction (bool): When false, the instruction is folded into
            the prompt and the deviation is recorded rather than hidden.
    """

    tool_calling: bool
    structured_output: bool
    system_instruction: bool


class ProviderAdapter(ABC):
    """One provider, behind the only interface Tier 2 knows about.

    Every operation is abstract. A partial implementation is a registration
    error rather than a runtime surprise, because the conformance suite in
    design section 9 enrols an adapter automatically once it is registered.
    """

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Return the engine identifier this adapter serves.

        Returns:
            str: The name used in CLI selection, result metadata and fixture
            paths. One value, because those three must agree.
        """

    @abstractmethod
    def compose_request(self, case: Any) -> Any:
        """Build a provider-shaped request from an evaluation case.

        Args:
            case (Any): An ``EvaluationCase``, typed loosely here so that Tier 2
                does not import Tier 1's record and invert the dependency.

        Returns:
            Any: The provider-shaped request. Its type is the adapter's
            business and stops at this boundary.
        """

    @abstractmethod
    def dispatch(self, request: Any) -> Any:
        """Issue exactly one request and return the provider's response.

        **One call. No loop, no agentic cycle, no tool execution.** The model's
        tool-call intent is captured and never acted on, because tool usage is
        behaviour under test rather than a prohibition.

        Args:
            request (Any): The composed request.

        Returns:
            Any: The provider-shaped response.
        """

    @abstractmethod
    def normalize_response(self, response: Any, case_id: str) -> NormalizedResponse:
        """Convert a provider response into the canonical shape.

        Args:
            response (Any): The provider-shaped response.
            case_id (str): The case this answers.

        Returns:
            NormalizedResponse: The only shape that crosses into Tier 3.
        """

    @abstractmethod
    def extract_tool_calls(self, response: Any) -> list[ToolCall]:
        """Capture the tool calls the model intended.

        Args:
            response (Any): The provider-shaped response.

        Returns:
            list[ToolCall]: Intent only, with arguments parsed into mappings.
            Empty when the model called nothing.
        """

    @abstractmethod
    def resolve_model_version(self, response: Any) -> str:
        """Return the model version the provider reported serving.

        **The resolved identifier, never the requested one.** Aliases float, and
        recording only the request hides precisely the event that makes a later
        score change uninterpretable.

        Args:
            response (Any): The provider-shaped response.

        Returns:
            str: The version the provider returned.

        Raises:
            ValueError: With ``QC_HARNESS_VERSION_UNAVAILABLE`` when the
                provider returned nothing usable. Preflight fails and the run
                aborts, because a run whose model identity is unknown produces
                scores nobody can interpret later.
        """

    @abstractmethod
    def map_error(self, error: Exception) -> str:
        """Translate a provider failure into the closed harness code set.

        Provider taxonomies differ in naming, in HTTP status usage, and in what
        they consider retryable. Untranslated, a rate limit from one vendor and
        a rate limit from another become different rows in the durable record,
        and cross-engine comparison of harness reliability becomes impossible.

        An unrecognised error maps to ``QC_HARNESS_PARSER_ERROR`` and records
        the original, so an unmapped case is visible rather than absorbed
        silently into a neighbouring category.

        Args:
            error (Exception): The provider's exception.

        Returns:
            str: One code from the adapter-permitted set.
        """

    def compose_judgement(self, prompt: str, reply_schema: dict[str, Any]) -> Any:
        """Build a provider request asking for a reply in the given schema.

        **Concrete, not abstract, and that is deliberate.**
        ``extensibility_standard.md`` section 9 permits a stable interface to
        gain an optional parameter and never a required one. A new abstract
        method is worse than a required parameter: it breaks every existing
        implementation at import rather than at a call.

        **The default refuses rather than approximating.** Asking for JSON in
        plain text and parsing whatever comes back would satisfy the call and
        quietly remove a security control: C2 makes structured output mandatory
        for the judge precisely so that schema validation doubles as the hijack
        detector (design section 7.8.2).

        Args:
            prompt (str): The rendered judge request. **Already composed by
                Tier 3**, which owns the isolation split; an adapter that
                rebuilt it could put candidate output into the instruction.
            reply_schema (dict): The structure the judge must reply in.

        Returns:
            Any: The provider-shaped request.

        Raises:
            NotImplementedError: With ``QC_HARNESS_PREFLIGHT_FAILURE`` when the
                adapter declares ``structured_output`` and has not implemented
                this. ``MQC_EXE_UNI_10278`` reports it across the registry, so
                the declaration is an obligation rather than a label.
        """
        del prompt, reply_schema
        raise NotImplementedError(
            f"QC_HARNESS_PREFLIGHT_FAILURE: {self.engine_name} declares "
            f"structured output and cannot compose a judgement, so it qualifies "
            f"as a judge and cannot serve as one"
        )

    def parse_judgement(self, response: Any) -> dict[str, Any]:
        """Read a provider reply into the mapping the validator expects.

        **Parsed here and validated in Tier 3.** This turns a provider object
        into a mapping and makes no judgement about its contents; whether the
        scores are in range, whether every criterion is answered and whether
        the shape is evidence of hijack all belong to
        :func:`evaluation.judge.validate_judge_reply`.

        Args:
            response (Any): The provider-shaped reply.

        Returns:
            dict[str, Any]: The reply as a mapping.

        Raises:
            NotImplementedError: As :meth:`compose_judgement`.
        """
        del response
        raise NotImplementedError(
            f"QC_HARNESS_PREFLIGHT_FAILURE: {self.engine_name} declares "
            f"structured output and cannot parse a judgement"
        )

    @abstractmethod
    def declare_capabilities(self) -> Capabilities:
        """Return what this provider supports.

        Returns:
            Capabilities: The declaration unsupported pairs are derived from.
        """


@dataclass(frozen=True)
class ProviderFacts:
    """What an adapter extracted from one provider response.

    Named so that assembling the canonical record happens in one place. Without
    it every adapter repeats the same eleven-field constructor call, and a field
    added to the record has to be found in three places rather than one.

    Attributes:
        text (str): The primary output, already concatenated where the provider
            splits it across blocks.
        tool_calls (list): Captured intent, empty when the model called nothing.
        block_reason (str): The provider's own word for refusing, empty where
            it did not. Verbatim, never mapped.
        block_stage (str): ``prompt``, ``response`` or empty, so a refusal can be
            reclassified later without re-running the corpus.
        usage (TokenUsage): Every token count the provider reported, read
            through :meth:`ConfiguredAdapter.read_usage` so the provider's
            spellings live in one place. **Output is read from here too**: it was
            briefly a field of its own beside this one, which meant each adapter
            computed it twice from the same object.
        input_tokens (int): Everything sent. **The larger half for this
            corpus**, and read from the same usage object that already gave the
            output count, where it sat unread until 2026-09-27.
        thinking_tokens (int): Reasoning the provider billed and did not return
            in the text. Counted apart from ``output_tokens`` because providers
            report it apart, and billed at the output rate because they bill it
            that way.
        cached_input_tokens (int): The part of the input served from the
            provider's cache, at a tenth of the input rate. **Included in
            ``input_tokens``**, never added to it, so the two cannot
            double-count.
        finish_reason (str): Already mapped into the canonical vocabulary.
        raw_reference (str): Pointer to the stored original, never the payload.
        resolved_model (str): What the provider reported serving (A8).
    """

    text: str
    tool_calls: list[ToolCall]
    finish_reason: str
    raw_reference: str
    resolved_model: str
    # DEFAULTED, so an adapter that cannot report a count is not forced to
    # invent one. A provider reporting nothing yields zero, which the cost
    # function reads as "no tokens here" rather than "no price here": the
    # second is what an unpriced MODEL yields, and the two are different
    # failures.
    usage: TokenUsage = field(default_factory=TokenUsage)
    block_reason: str = ""
    block_stage: str = ""


class ConfiguredAdapter(ProviderAdapter):
    """Construction and identity, shared by every adapter.

    Sits between the interface and each adapter. The three adapters converged
    independently on identical code for storing a requested model, reporting an
    engine name and populating the canonical record, which is the interface's
    own shape showing through rather than a coincidence.

    **This does not weaken the stability guarantee** in
    ``extensibility_standard.md`` section 9. :class:`ProviderAdapter` remains
    the interface and an adapter may implement it directly; this is a
    convenience beneath the contract, not a requirement above it.

    Attributes:
        ENGINE_NAME (str): The engine this adapter serves.
        DEFAULT_MODEL (str): Requested when configuration names no model, so an
            unconfigured run is reproducible rather than failing at the
            boundary. The model itself is supplied at execution time per B8.
    """

    ENGINE_NAME: str = ""
    DEFAULT_MODEL: str = ""

    def __init__(self, model: Optional[str] = None) -> None:
        """Record which model this adapter requests.

        The provider client is constructed lazily on first dispatch, so
        building an adapter needs no credential and every offline operation
        stays testable.

        Args:
            model (Optional[str]): The model to request, or ``None`` for the
                adapter's declared default.

        Returns:
            None
        """
        self._model = model or self.DEFAULT_MODEL
        self._client: Any = None

    @property
    def connected(self) -> bool:
        """Return whether a provider client is currently held.

        Returns:
            bool: True once a dispatch has constructed one, until it is
            released. **Read by the cases rather than by the dispatcher**,
            which releases unconditionally.
        """
        return self._client is not None

    # THE EXCEPTION TABLE, declared by each adapter whose SDK distinguishes
    # failures by class. **Ordered, and the order is load-bearing**: these
    # classes overlap, so the first match wins and the most specific comes
    # first. An adapter whose SDK carries the distinction in a status code
    # instead overrides `map_error` and leaves this empty, which is what
    # gemini does.
    ERROR_CLASSES: tuple[tuple[type, str], ...] = ()

    def map_error(self, error: Exception) -> str:
        """Translate a provider failure into the closed harness code set.

        **Written once because two protocols ask the same question.** Both
        previously carried an identical loop, which pylint reported as
        duplication and which would have drifted the first time a code was
        added to one.

        Args:
            error (Exception): The provider's exception.

        Returns:
            str: One code from the adapter-permitted set. **An unrecognised
            error maps to ``QC_HARNESS_PARSER_ERROR``** so an unmapped case is
            visible rather than absorbed into a neighbouring category, which
            is the property design section 8.5.3 keeps clear by giving a
            rejected request its own code.
        """
        # THE STATUS FIRST, being the more specific of the two, and read from
        # ONE table rather than a copy per adapter: what a status means is a
        # property of HTTP, not of a vendor (design section 8.5.6). The SDKs
        # differ only in which attribute carries it.
        mapped = taxonomy_for_status(
            getattr(error, "status_code", getattr(error, "code", None))
        )
        if mapped is not None:
            return mapped

        for error_class, code in self.ERROR_CLASSES:
            if isinstance(error, error_class):
                return code
        logger.warning(
            "Unmapped %s error %s: %s", self.ENGINE_NAME,
            type(error).__name__, error,
        )
        return "QC_HARNESS_PARSER_ERROR"

    def period_quota_exhausted(self, error: Exception) -> bool:  # pylint: disable=unused-argument
        """Report whether a rate limit names a period this run cannot outwait.

        **A 429 is one status carrying three conditions, and they sit at
        different levels** (design section 8.6). A per-minute rate is reachable
        by pacing; a per-day allowance and a missing credit are not reachable
        by anything a run can do. A retry is a connection-level remedy, so it
        is justified for the first and futile for the other two.

        **Which condition it is, is the one vendor-specific part.** The status
        means the same thing everywhere, which is why it is read from one table
        (section 8.5.6); the *quota that was exceeded* is named in the
        provider's own body, in the provider's own shape. So the shared code
        asks the question and each adapter answers it.

        **The provider's retry hint cannot answer it.** Gemini quotes a
        `retryDelay` of around 52 seconds for a quota that resets once a day
        (section 8.6.4). Honouring that hint would retry forever, which is why
        nothing here reads it.

        Args:
            error (Exception): The provider failure already mapped to
                ``QC_HARNESS_RATE_LIMIT``.

        Returns:
            bool: ``True`` only where the provider named an exhausted period.
            **False by default, including where the answer is unknown**, so an
            adapter that cannot tell keeps the retry it has today rather than
            silently losing it.
        """
        return False

    @staticmethod
    def raw_reference_of(response: Any) -> str:
        """Return the provider's own identifier for a response.

        **Three spellings, one fact.** Two providers call it `id` and the third
        `response_id`, which made the read identical in two adapters and
        different in the third: pylint reported the pair as duplication, and the
        pair would have drifted the first time one of them learned something.

        Args:
            response (Any): The provider's response object.

        Returns:
            str: The identifier, or an empty string where the provider sent
            none. **Never the payload**: this is a pointer to the stored
            original, and carrying the response here would put a model's output
            in a field nothing redacts.
        """
        for name in ("id", "response_id"):
            found = getattr(response, name, None)
            if found:
                return str(found)
        return ""

    # THE NAMES A PROVIDER GIVES ITS USAGE OBJECT. Two call it `usage` and the
    # Gen AI client calls it `usage_metadata`, and an adapter should not have to
    # restate the search to answer what its own fields are called.
    USAGE_ATTRIBUTES: tuple[str, ...] = ("usage", "usage_metadata")

    def read_usage(self, response: Any) -> TokenUsage:
        """Return the four token counts a provider reported for one response.

        **Two callers, which is why this exists at all.** The candidate path
        reads usage while normalizing; the judge path reads it from a judgement
        response, whose parse discards the object. Writing the field names twice
        is how they drift.

        **The absence is handled once, here.** Every adapter had the same guard
        before this: fetch the object, return empty where it is missing, read the
        fields otherwise. Only the last step differs per provider, so only that
        step is overridden, in :meth:`usage_from`.

        Args:
            response (Any): The provider's own response object.

        Returns:
            TokenUsage: The counts. **Zero where the provider reported nothing**,
            which the cost function reads as no tokens rather than no price: an
            unpriced model is a different failure and yields ``None``.
        """
        for name in self.USAGE_ATTRIBUTES:
            usage = getattr(response, name, None)
            if usage is not None:
                return self.usage_from(usage)
        return TokenUsage()

    def usage_from(self, usage: Any) -> TokenUsage:  # pylint: disable=unused-argument
        """Return the counts, reading this provider's own field names.

        Args:
            usage (Any): The provider's usage object, already found and known
                to be present.

        Returns:
            TokenUsage: The counts. **Empty by default**, so an adapter whose
            provider reports nothing useful is not forced to invent a shape.
        """
        return TokenUsage()
    def release(self) -> None:
        """Drop the provider client, closing its connection pool.

        **A connection belongs to one case** (design section 7.7). Sharing one
        across cases couples their outcomes: a wedged socket or a client whose
        internal state has gone strange would be inherited by every case that
        followed, turning one event into a cascade attributable to nothing.

        **Idempotent, and safe before any dispatch.** Releasing an adapter that
        never built a client is a no-op rather than an error, so a replay run
        may call this on the same path a live run does.

        **A client that refuses to close is not this run's problem.** The
        reference is dropped whatever happens, because a failure to shut a
        socket down cleanly must not become a finding about a model.

        Returns:
            None
        """
        client = self._client
        self._client = None
        if not hasattr(client, "close"):
            return
        try:
            client.close()
        except (OSError, RuntimeError, ValueError, TypeError) as error:
            logger.debug(
                "%s: releasing the client raised %s, and the reference is "
                "dropped regardless",
                self.ENGINE_NAME,
                type(error).__name__,
            )

    @property
    def engine_name(self) -> str:
        """Return the engine identifier this adapter serves.

        Returns:
            str: The name used in CLI selection, result metadata and fixture
            paths. One value, because those three must agree.
        """
        return self.ENGINE_NAME

    @property
    def requested_model(self) -> str:
        """Return the model this adapter asks for.

        Returns:
            str: The requested identifier, which the resolved one may differ
            from. Both are recorded, per A8.
        """
        return self._model

    def build_response(self, case_id: str, facts: ProviderFacts) -> NormalizedResponse:
        """Assemble the canonical record from what the adapter extracted.

        ``duration_ms`` is zero here and stamped by the dispatcher, which is
        the only place that can exclude configured request spacing from the
        interval (design section 4.4).

        Args:
            case_id (str): The case this answers.
            facts (ProviderFacts): The provider-specific values.

        Returns:
            NormalizedResponse: The only shape that crosses into Tier 3.
        """
        return NormalizedResponse(
            case_id=case_id,
            engine=self.ENGINE_NAME,
            mode="live",
            requested_model=self._model,
            resolved_model=facts.resolved_model,
            text=facts.text,
            tool_calls=facts.tool_calls,
            output_tokens=facts.usage.output_tokens,
            input_tokens=facts.usage.input_tokens,
            thinking_tokens=facts.usage.thinking_tokens,
            cached_input_tokens=facts.usage.cached_input_tokens,
            block_reason=facts.block_reason,
            block_stage=facts.block_stage,
            duration_ms=0,
            finish_reason=facts.finish_reason,
            raw_reference=facts.raw_reference,
        )


def validate_mapped_error(adapter_name: str, taxonomy_code: str) -> str:
    """Refuse a code an adapter is not permitted to return.

    Called by the conformance suite rather than by `map_error` itself, so that
    an adapter cannot satisfy the check by never being asked.

    Args:
        adapter_name (str): The adapter under check, for the message.
        taxonomy_code (str): What `map_error` returned.

    Returns:
        str: The code, unchanged, once it is known to be permitted.

    Raises:
        ValueError: When the code is outside the adapter-permitted set. A
            fixture code comes from the replay store and a dependency code from
            the runner; an adapter returning either is reporting on something
            it cannot observe.
    """
    if not is_adapter_error_code(taxonomy_code):
        logger.error(
            "QC_HARNESS_PARSER_ERROR adapter %s returned unpermitted code %s",
            adapter_name, taxonomy_code,
        )
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: adapter {adapter_name} mapped an error to "
            f"{taxonomy_code!r}, which is not a code an adapter may return"
        )
    return taxonomy_code


def require_json_object(payload: str, engine: str) -> dict[str, Any]:
    """Parse a JSON object, refusing anything that is not one.

    **Shared by every protocol that receives its judgement as text**, which is
    all of them except Anthropic Messages, where a forced tool call arrives
    already parsed. It lives here rather than in any one protocol module so
    that a Google adapter does not import an OpenAI one to borrow it.

    Args:
        payload (str): The reply text.
        engine (str): Which engine is reporting, for the message.

    Returns:
        dict[str, Any]: The parsed object.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the text is not JSON
            or is JSON that is not an object. **The payload is never quoted**:
            a judge reply carries candidate output, and a parser error is
            exactly where it would otherwise reach a log.
    """
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: {engine} returned a judgement that is "
            f"not JSON, so the schema constraint was not honoured"
        ) from error
    if not isinstance(parsed, dict):
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: {engine} returned JSON that is not an "
            f"object, so it cannot carry the required scores"
        )
    return parsed
