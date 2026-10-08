# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Which engines a run may name, and which list decides.

Covers ``MQC_CMN_UNI_112149`` and ``112150``, inventoried in
``docs/design/cmn_verdict_and_cli.md`` section 10 and designed in
``tier2_execution.md`` section 3.5.1.

**Written 2026-10-04, when rostering a fourth engine found two defects one
after the other.** `--engine` enumerated three engines in the option registry,
so the flag refused one the roster named; removing the enumeration revealed
that nothing checked the roster either, and an engine with an adapter and no
roster entry would have dispatched against the adapter's own default.

**Two lists, and only one can gate a run.** The adapter registry says code
exists for a provider. The roster says a model, an observation count and a
request spacing are configured. The second is the list.

A failure here is **not a model finding**, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

import pytest

from cmn.config import load_engines, packaged_roster_path
from cmn.pytest_support import require_rostered_engine
from execution.adapters.registry import adapter_for, credential_variables

pytestmark = pytest.mark.unit


class TestMQCEngineVocabulary:
    """Adding a provider is an entry in the roster, not an edit to a flag."""

    def MQC_CMN_UNI_112149_an_engine_absent_from_the_registry_is_refused(self) -> None:
        """An unknown engine is refused by the registry, not by a copy of it.

        **`--engine` carried a choices tuple until 2026-10-04**, enumerating
        three engines, so rostering a fourth left the flag refusing an engine
        `config/engines.yaml` named: "invalid choice: 'grok'". The argument
        against enumerating was already written one flag away, on
        `--judge-engine`: a list has to be edited whenever an adapter is added.

        **The guard moved rather than went.** The refusal is later, at dispatch
        rather than at parse time, and it names what is registered, so a typo
        still cannot reach a run that selects nothing and reports green.

        Design: ``tier2_execution.md`` section 3.5.

        Returns:
            None
        """
        with pytest.raises(ValueError, match="QC_HARNESS_PARSER_ERROR") as caught:
            adapter_for("gemeni")

        message = str(caught.value)
        assert "no adapter is registered" in message
        assert "gemeni" in message

        # IT NAMES WHAT IS REGISTERED, which is what makes a typo correctable
        # from the message rather than from the source.
        for engine in ("gemini", "openai", "claude", "grok"):
            assert engine in message

    def MQC_CMN_UNI_112150_an_engine_off_the_roster_is_refused_before_it_runs(
        self,
    ) -> None:
        """An engine with an adapter and no roster entry does not run.

        **Two lists exist and the weaker one was gating.** The adapter registry
        says code exists; the roster says a model, an observation count and a
        request spacing are configured. `dispatch_plan` resolves the model as
        ``roster[engine].model if engine in roster else None``, and a plan with
        no model dispatches against the **adapter's own default** — for grok,
        ``grok-4``, which the provider does not serve.

        So `--engine grok` before rostering would have produced a 404 on every
        case, which reads as a broken harness rather than as configuration not
        yet done.

        **Refused at configure time, with both remedies named.** Add a roster
        entry, or declare the absence under ``not_rostered``.

        Design: ``tier2_execution.md`` section 3.5.1.

        Returns:
            None
        """
        roster = load_engines(packaged_roster_path())

        assert sorted(roster) == ["claude", "gemini", "grok", "openai"], (
            "the roster changed; this case names what it expects so that "
            "adding an engine is a deliberate edit here too"
        )

        # EVERY ROSTERED ENGINE PASSES, or the gate would refuse a configured run.
        for engine in sorted(roster):
            require_rostered_engine(engine, roster)

        # AN ENGINE NAMING NOTHING PASSES, because the default applies and the
        # defaulted-engine warning is what covers that case.
        require_rostered_engine("", roster)

        # AND ONE OFF THE ROSTER IS REFUSED, naming what is on it.
        with pytest.raises(ValueError, match="QC_HARNESS_PREFLIGHT_FAILURE") as caught:
            require_rostered_engine("mistral", roster)

        message = str(caught.value)
        assert "not on the roster" in message
        assert "config/engines.yaml" in message
        assert "not_rostered" in message
        for engine in sorted(roster):
            assert engine in message

        # A REGISTERED ADAPTER IS NOT ENOUGH, which is the defect itself: grok
        # had an adapter for weeks while this would have refused it.
        assert any("XAI" in name for name in credential_variables()), (
            "the grok adapter is not registered, so this case no longer "
            "establishes that a registered adapter is insufficient"
        )
