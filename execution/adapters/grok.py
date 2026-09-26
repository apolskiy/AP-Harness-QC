# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The xAI (Grok) engine.

**This module is the evidence for section 3.3.** It carries no protocol code,
no request composition, no normalization, no error mapping and no judging, and
it is enrolled in the full conformance battery the moment it is registered.
xAI serves the Chat Completions shape, so everything comes from
:mod:`execution.adapters.openai_protocol`.

Adding DeepSeek, Mistral, Groq, Together or OpenRouter is this file with three
values changed.

**Replay-only until a key is provisioned**, on the same footing as OpenAI and
Claude under A3. The credential is read from the environment at runtime and
appears in no configuration file.
"""

import logging
from typing import Final

from execution.adapters.openai_protocol import OpenAICompatibleAdapter

logger = logging.getLogger(__name__)

_ENGINE_NAME: Final[str] = "grok"

# Supplied at execution time per B8. The fallback when configuration names none.
_DEFAULT_MODEL: Final[str] = "grok-4"

# xAI's Chat Completions endpoint. THE ONLY FIELD THAT ROUTES A REQUEST: an
# engine that omits it reaches OpenAI with an xAI key, which fails as an
# authentication error naming the wrong vendor.
_BASE_URL: Final[str] = "https://api.x.ai/v1"


class GrokAdapter(OpenAICompatibleAdapter):
    """xAI, behind the one interface Tier 2 knows about.

    Attributes:
        ENGINE_NAME (str): The engine this adapter serves.
        DEFAULT_MODEL (str): Requested when configuration names none.
        BASE_URL (str): xAI's endpoint.
        API_KEY_ENV (str): The variable carrying the credential.
    """

    ENGINE_NAME = _ENGINE_NAME
    DEFAULT_MODEL = _DEFAULT_MODEL
    BASE_URL = _BASE_URL
    API_KEY_ENV = "XAI_API_KEY"
