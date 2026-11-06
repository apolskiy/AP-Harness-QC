# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The adapter that sends cases to OpenAI's models, over the Responses protocol.

Created: 2026-09-26
Last updated: 2026-11-06

This file contains :class:`OpenAIAdapter`, which names the ``openai`` engine,
its default model and the ``OPENAI_API_KEY`` credential variable, and inherits
everything else from
:class:`~execution.adapters.openai_responses.OpenAIResponsesAdapter`. The
registry enrols it, so dispatch and the judge channel reach it whenever a run
names ``openai``.

The Responses protocol lives in :mod:`execution.adapters.openai_responses`.
**What remains here is what is actually specific to OpenAI**, which is its
name, its default model and the fact that it needs no endpoint override
because it is the SDK's own default.

Specified by ``docs/design/tier2_execution.md`` section 3.5.4, which records
why this engine left Chat Completions.
"""

import logging
from typing import Final

from execution.adapters.openai_responses import OpenAIResponsesAdapter

logger = logging.getLogger(__name__)

_ENGINE_NAME: Final[str] = "openai"

# Supplied at execution time per B8, never hardcoded into a case. This is the
# fallback when configuration names no model, so an unconfigured run is still
# reproducible rather than failing at the boundary.
_DEFAULT_MODEL: Final[str] = "gpt-6-astra"


class OpenAIAdapter(OpenAIResponsesAdapter):
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
