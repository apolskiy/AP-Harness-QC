# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Fake model-metadata endpoints, shaped like each real SDK, for the conformance battery.

Created: 2026-10-29
Last updated: 2026-10-29

This file contains one metadata builder per provider, :func:`claude_metadata`,
:func:`gemini_metadata`, :func:`openai_metadata` and :func:`grok_metadata`;
:class:`ModelsClientDouble`, which stands in for a provider client and records
what it was asked about; ``METADATA_DOUBLES``, which maps each registered
engine to its builder and to the client factory its adapter calls; and
:func:`install_metadata_double`, which puts that double in place of the factory
for one test.

The conformance battery feeds these to ``ProviderAdapter.served_metadata`` in
place of a provider, so the check that every adapter reports what its provider
serves sends no request and needs no credential. `pytest.ini` collects only
`mqc_*.py`, so nothing here is collected.

**These are the metadata endpoint, not the response.** `provider_doubles.py`
holds what a provider returns for a prompt; this holds what it declares about a
model when nobody sent one. The two are separate subjects and separate modules
for the reason `code-style.md` section 5.1 gives, that module having reached
the runway ceiling.

**Each double declares a null and a private field.** Real endpoints return
both, and ``execution.adapters.base.declared_properties`` drops both, so a
double carrying neither would let a reduction that dropped nothing pass.

**Each double exposes ``model_dump``**, because all four providers return a
pydantic object and that is the branch production takes. A dataclass with no
such method would exercise the fallback instead and leave the real path
unmeasured.

Shapes come from the measurement recorded in ``tier2_execution.md`` section
5.2, which asked each provider's endpoint about its rostered model on
2026-10-29.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Final

import anthropic
import openai
from google import genai

from execution.adapters import claude as claude_module
from execution.adapters import gemini as gemini_module
from execution.adapters import openai_protocol as openai_module


@dataclass
class _DeclaredModel:
    """What a provider declares about one model, as its SDK object renders it.

    The fields differ per provider deliberately, because that difference is
    what the adapter contract absorbs. ``model_dump`` is what every one of
    the four real objects offers and what ``declared_properties`` reads.
    """

    fields: dict[str, Any]

    def model_dump(self) -> dict[str, Any]:
        """Return the declared fields as the provider's own object does.

        Returns:
            dict[str, Any]: The fields, including the nulls and the private
            key a real endpoint returns, which the reduction drops.
        """
        return dict(self.fields)


def claude_metadata() -> _DeclaredModel:
    """Build what the Anthropic models endpoint declares about a model.

    Returns:
        _DeclaredModel: Carrying the dated ``capabilities`` tree that is where
        a revision behind a stable identifier shows.
    """
    return _DeclaredModel(
        fields={
            "id": "claude-opus-5-5",
            "type": "model",
            "display_name": "Claude Opus 5.5",
            "created_at": "2026-02-05T00:00:00Z",
            "capabilities": {
                "context_management": {"compact_20260112": {"enabled": True}},
                "thinking": {"clear_thinking_20251015": {"enabled": True}},
            },
            "deprecated_at": None,
            "_request_id": "req_synthetic",
        }
    )


def gemini_metadata() -> _DeclaredModel:
    """Build what the Gen AI models endpoint declares about a model.

    Returns:
        _DeclaredModel: Carrying the ``version`` this provider reports of its
        own, which reads ``3.0`` against the ``3.8-flash`` in the name.
    """
    return _DeclaredModel(
        fields={
            "name": "models/gemini-3.8-flash",
            "version": "3.0",
            "display_name": "Gemini 3.8 Flash",
            "input_token_limit": 1048576,
            "output_token_limit": 65536,
            "supported_actions": ["generateContent", "countTokens"],
            "thinking": True,
            "default_temperature": 1.0,
            "top_p": 0.95,
            "tuned_model_info": None,
            "_response_id": "synthetic",
        }
    )


def openai_metadata() -> _DeclaredModel:
    """Build what the openai models endpoint declares about a model.

    Returns:
        _DeclaredModel: Carrying ``shutdown_date``, the declared retirement
        that earns the operation on its own (design section 5.2).
    """
    return _DeclaredModel(
        fields={
            "id": "gpt-4.1",
            "object": "model",
            "created": 1744070400,
            "owned_by": "system",
            "shutdown_date": "2027-01-14",
            "deprecation_date": None,
            "_request_id": "req_synthetic",
        }
    )


def grok_metadata() -> _DeclaredModel:
    """Build what the xAI models endpoint declares about a model.

    **Not openai's**, although the two share the dispatch protocol: this
    endpoint declares prices and a context length where openai declares a
    retirement date, which is why the two engines take separate doubles where
    the response doubles are shared.

    Returns:
        _DeclaredModel: Carrying the four token prices and the context length.
    """
    return _DeclaredModel(
        fields={
            "id": "grok-4.7",
            "object": "model",
            "created": 1759536000,
            "owned_by": "xai",
            "prompt_text_token_price": 200,
            "prompt_image_token_price": 200,
            "cached_prompt_token_price": 50,
            "completion_text_token_price": 1500,
            "context_length": 2000000,
            "long_context_threshold": 128000,
            "capabilities": {"reasoning_effort": ["low", "high"]},
            "aliases": None,
            "_request_id": "req_synthetic",
        }
    )


@dataclass
class ModelsClientDouble:
    """A provider client whose models endpoint returns a declared model.

    Exposes both spellings the four adapters use, ``get`` with a keyword and
    ``retrieve`` positionally, and records every identifier it was asked
    about so a case can assert the adapter asked for the model it requested
    rather than for something it had lying around.
    """

    declared: _DeclaredModel
    asked: list[str] = field(default_factory=list)

    @property
    def models(self) -> "ModelsClientDouble":
        """Return the endpoint, which is this double itself.

        Returns:
            ModelsClientDouble: Self, so ``client.models.get`` resolves.
        """
        return self

    def get(self, *, model: str) -> _DeclaredModel:
        """Return the declared model, as the Gen AI endpoint does.

        Args:
            model (str): The identifier asked about.

        Returns:
            _DeclaredModel: What this provider declares.
        """
        self.asked.append(model)
        return self.declared

    def retrieve(self, model: str) -> _DeclaredModel:
        """Return the declared model, as the Anthropic and openai endpoints do.

        Args:
            model (str): The identifier asked about.

        Returns:
            _DeclaredModel: What this provider declares.
        """
        self.asked.append(model)
        return self.declared


@dataclass(frozen=True)
class _MetadataDoubles:
    """One engine's metadata double and the client factory its adapter calls."""

    metadata: Callable[[], _DeclaredModel]
    namespace: Any
    factory: str


# EACH ENGINE'S FACTORY, NAMED RATHER THAN GUESSED. An adapter builds its
# client lazily from one symbol in its own module, and that symbol is the seam
# a case substitutes: patching it reaches the real call path without the test
# touching a private attribute.
METADATA_DOUBLES: Final[dict[str, _MetadataDoubles]] = {
    "claude": _MetadataDoubles(
        metadata=claude_metadata,
        namespace=claude_module.anthropic,
        factory=anthropic.Anthropic.__name__,
    ),
    "gemini": _MetadataDoubles(
        metadata=gemini_metadata,
        namespace=gemini_module.genai,
        factory=genai.Client.__name__,
    ),
    "openai": _MetadataDoubles(
        metadata=openai_metadata,
        namespace=openai_module.openai,
        factory=openai.OpenAI.__name__,
    ),
    # SEPARATE FROM OPENAI, unlike the response doubles. The protocol is shared
    # and the metadata is not: this endpoint declares prices and a context
    # length where openai declares a retirement date.
    "grok": _MetadataDoubles(
        metadata=grok_metadata,
        namespace=openai_module.openai,
        factory=openai.OpenAI.__name__,
    ),
}


def install_metadata_double(monkeypatch: Any, engine: str) -> ModelsClientDouble:
    """Put one engine's metadata double in place of its client factory.

    Args:
        monkeypatch (Any): pytest's patcher, which restores the factory.
        engine (str): The registered engine whose adapter will be called.

    Returns:
        ModelsClientDouble: The double the adapter will reach, for a case to
        read what it was asked about.
    """
    entry = METADATA_DOUBLES[engine]
    double = ModelsClientDouble(declared=entry.metadata())
    monkeypatch.setattr(
        entry.namespace, entry.factory, lambda **options: double
    )
    return double
