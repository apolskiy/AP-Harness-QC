# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The OpenAI engine, which is one engine on a protocol several vendors serve.

The Chat Completions protocol lives in
:mod:`execution.adapters.openai_protocol`. **What remains here is what is
actually specific to OpenAI**, which is its name, its default model and the
fact that it needs no endpoint override because it is the SDK's own default.

Replay-only under A3 until a key is provisioned.
"""

import logging
from typing import Final

from execution.adapters.openai_protocol import OpenAICompatibleAdapter

logger = logging.getLogger(__name__)

_ENGINE_NAME: Final[str] = "openai"

# Supplied at execution time per B8, never hardcoded into a case. This is the
# fallback when configuration names no model, so an unconfigured run is still
# reproducible rather than failing at the boundary.
_DEFAULT_MODEL: Final[str] = "gpt-4.1"


class OpenAIAdapter(OpenAICompatibleAdapter):
    """OpenAI, behind the one interface Tier 2 knows about.

    Attributes:
        ENGINE_NAME (str): The engine this adapter serves.
        DEFAULT_MODEL (str): Requested when configuration names none.
        BASE_URL (Optional[str]): ``None``, this being the SDK's own default.
        API_KEY_ENV (str): The variable carrying the credential.
    """

    ENGINE_NAME = _ENGINE_NAME
    DEFAULT_MODEL = _DEFAULT_MODEL
    BASE_URL = None
    API_KEY_ENV = "OPENAI_API_KEY"
