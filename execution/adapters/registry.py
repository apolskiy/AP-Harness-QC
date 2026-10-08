# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The registry mapping an engine name to the adapter serving it.

Specified by ``docs/design/tier2_execution.md`` section 3.2.

**This exists so that the conformance battery has something to parametrize
over.** ``harness_extensibility_standard.md`` section 10 requires registration to enrol
an adapter in its battery automatically, and a battery written against a
hand-maintained list is a second place to forget.

**The engine name is the only key.** It is already the value used in CLI
selection, result metadata and fixture paths, and those three have to agree.

**Classes, not instances.** A model identifier is supplied at execution time per
B8, so an instance would have to be built with one before the run knew which one
it wanted.
"""

import logging
from typing import Final, Iterator, Type

from execution.adapters.base import ProviderAdapter
from execution.adapters.claude import ClaudeAdapter
from execution.adapters.gemini import GeminiAdapter
from execution.adapters.grok import GrokAdapter
from execution.adapters.openai import OpenAIAdapter

logger = logging.getLogger(__name__)

_ADAPTERS: Final[dict[str, Type[ProviderAdapter]]] = {}


def register_adapter(adapter_class: Type[ProviderAdapter]) -> Type[ProviderAdapter]:
    """Enrol an adapter under the engine name it declares.

    Args:
        adapter_class (Type[ProviderAdapter]): The adapter to register.

    Returns:
        Type[ProviderAdapter]: The same class, so this reads as a decorator
        where an adapter prefers to register itself.

    Raises:
        ValueError: When the name is already taken. **This fires at import
        rather than at dispatch**, because a run that started before the
        collision was noticed would attribute its results to whichever adapter
        happened to register last, and a fixture recorded by one would replay
        through the other.
    """
    engine = adapter_class().engine_name
    existing = _ADAPTERS.get(engine)
    if existing is not None and existing is not adapter_class:
        logger.error("QC_HARNESS_PARSER_ERROR duplicate adapter registration for %s", engine)
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: engine {engine!r} is already served by "
            f"{existing.__name__}, so {adapter_class.__name__} cannot also claim it"
        )
    _ADAPTERS[engine] = adapter_class
    return adapter_class


def adapter_for(engine: str) -> Type[ProviderAdapter]:
    """Return the adapter class serving one engine.

    Args:
        engine (str): The engine name, as the CLI supplies it.

    Returns:
        Type[ProviderAdapter]: The registered class.

    Raises:
        ValueError: When nothing is registered under that name. The message
            lists what is registered, because a typo and an unimplemented
            provider are different problems and the reader should be able to
            tell which one they have.
    """
    normalized = str(engine).strip()
    if normalized not in _ADAPTERS:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: no adapter is registered for engine "
            f"{normalized!r}; registered engines are {registered_engines()}"
        )
    return _ADAPTERS[normalized]


def registered_engines() -> list[str]:
    """Return every registered engine name.

    Returns:
        list[str]: Names in sorted order, so a run's output and any message
        built from this do not depend on registration order.
    """
    return sorted(_ADAPTERS)


def registered_adapters() -> Iterator[Type[ProviderAdapter]]:
    """Yield every registered adapter class.

    **The conformance battery parametrizes over this.** A new adapter is
    therefore covered by the battery the moment it is registered, with no list
    to update and nothing to remember.

    Yields:
        Type[ProviderAdapter]: Each registered class, in engine-name order.
    """
    for engine in registered_engines():
        yield _ADAPTERS[engine]



# The roles an engine can fill. NEITHER IS A LIST OF ENGINES: candidacy follows
# from being registered and the judge role from a declared capability, so an
# engine arrives in both roles or in neither (design section 3.6).
CANDIDATE_ROLE: Final[str] = "candidate"
JUDGE_ROLE: Final[str] = "judge"
_ROLES: Final[frozenset[str]] = frozenset({CANDIDATE_ROLE, JUDGE_ROLE})


def engines_for_role(role: str) -> list[str]:
    """Return every registered engine that can fill one role.

    **Derived from the registry and the capability declaration**, never from a
    maintained list. `config/engines.yaml` has always said this in prose: any
    engine declaring ``structured_output`` may judge, and there is deliberately
    no list of permitted judge engines to keep in step with the adapters. This
    makes the sentence queryable.

    Args:
        role (str): ``candidate`` or ``judge``.

    Returns:
        list[str]: Engine names in sorted order, so output does not depend on
        registration order.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` for an unregistered role.
            **An unknown role returning an empty list would read as "no engine
            can do this"**, which is a different and much quieter failure.
    """
    if role not in _ROLES:
        raise ValueError(
            f"QC_HARNESS_PARSER_ERROR: {role!r} is not a role; "
            f"registered roles are {sorted(_ROLES)}"
        )
    if role == CANDIDATE_ROLE:
        return registered_engines()
    return [
        engine
        for engine in registered_engines()
        if _ADAPTERS[engine]().declare_capabilities().structured_output
    ]


def credential_variables() -> list[str]:
    """Return every environment variable the registered engines read.

    **Declared by the adapters, never listed here.** An engine added tomorrow
    is covered the moment it is registered, which is the arrangement the
    conformance battery already uses (design section 3.5).

    Returns:
        list[str]: Names in sorted order. Includes ``ALSO_READS`` for an
        adapter whose SDK resolves more than one name for itself, which the Gen
        AI client does.
    """
    names: set[str] = set()
    for adapter_class in registered_adapters():
        adapter = adapter_class()
        primary = getattr(adapter, "API_KEY_ENV", "")
        if primary:
            names.add(primary)
        names.update(getattr(adapter, "ALSO_READS", ()))
    return sorted(names)


register_adapter(ClaudeAdapter)
register_adapter(GeminiAdapter)
register_adapter(OpenAIAdapter)
register_adapter(GrokAdapter)
