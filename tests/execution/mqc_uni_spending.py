# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for what a run is allowed to spend.

Covers `MQC_EXE_UNI_10301` through `10304`, inventoried in
``docs/design/tier2_execution.md`` section 10.1.

**Split out of ``mqc_uni_dispatch.py`` on 2026-09-28**, which had reached 1014
lines against a 1000-line limit. The split is by subject: what a run may spend and
what an empty balance means are questions about money, while retry and backoff ask
whether a request is worth repeating. They shared a module because both live on
the dispatch path, which is not the same as being the same subject.

**Nothing here spends anything.** Every case prices a scripted double against the
shipped table on a fixed date, so the arithmetic is exercised without a provider.

A failure here is our defect, so the module carries no priority marker, per
``framework-rules.md`` section 3.3.
"""

from datetime import date
from pathlib import Path
from typing import Any, Iterator

import pytest

from cmn.pricing import load_price_table
from cmn.registries import registered_codes, taxonomy_for_status
from execution.adapters.claude import ClaudeAdapter
from execution.dispatch import (
    _RETRYABLE_CODES,
    DispatchPlan,
    DispatchSession,
    dispatch_case,
)
from ingestion.schemas import EvaluationCase
from tests.execution.provider_doubles import claude_response

pytestmark = pytest.mark.unit

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

# The window the shipped table prices today. Injected rather than read from a
# clock, for the reason the verdict injects its date.
_PRICED_ON = date(2026, 9, 27)


@pytest.fixture(name="scripted")
def fixture_scripted(monkeypatch: Any) -> Iterator[Any]:
    """Return a helper that scripts what the claude adapter's dispatch does.

    Args:
        monkeypatch (Any): pytest's patcher.

    Yields:
        Any: A callable taking the results to serve, returning the call log.
    """
    calls: list[Any] = []

    def script(*results: Any) -> list[Any]:
        """Install a scripted dispatch and return its call log.

        Args:
            *results (Any): Responses to return, the last repeated.

        Returns:
            list: Every request the adapter was asked to dispatch.
        """
        remaining = list(results)

        def fake_dispatch(_self: Any, request: Any) -> Any:
            calls.append(request)
            return remaining.pop(0) if len(remaining) > 1 else remaining[0]

        monkeypatch.setattr(ClaudeAdapter, "dispatch", fake_dispatch)
        return calls

    yield script


def _plan(tmp_path: Any) -> DispatchPlan:
    """Return a live plan rooted in a temporary fixture store.

    Args:
        tmp_path (Any): pytest's temporary directory.

    Returns:
        DispatchPlan: A live plan that records nothing.
    """
    return DispatchPlan(mode="live", fixture_root=tmp_path, record=False)


class TestMQCSpendCeiling:
    """What a run may spend, and what stops it when it may not."""


    def MQC_EXE_UNI_10301_a_run_at_its_spend_ceiling_dispatches_nothing_further(
        self, minimal_case: EvaluationCase, tmp_path: Path, scripted: Any,
        monkeypatch: Any
    ) -> None:
        """The control that makes authorising a paid key safe rather than hopeful.

        **The corpus is too small to threaten a wallet, and that is not what this
        protects against.** It protects against a condition nobody predicted: a
        model that suddenly thinks ten times as hard, a corpus that grew, a key
        pointed at a model an order more expensive. In each case the bill is
        discovered after it is incurred, and a ceiling converts that into a run
        that stopped.

        Args:
            minimal_case (Any): The case to dispatch.
            tmp_path (Any): pytest's temporary directory.
            scripted (Any): Dispatch scripting helper.

        Returns:
            None
        """
        table = load_price_table(_REPOSITORY_ROOT / "config" / "pricing.yaml")
        # THE DOUBLE IS MADE TO RESOLVE TO A PRICED MODEL, so this case exercises
        # spending rather than the unpriced refusal `10303` covers. Without this
        # it passed for the wrong reason: the claude double resolves to a model
        # the table does not price, so nothing accumulated and the run stopped
        # for a different cause entirely.
        monkeypatch.setattr(
            ClaudeAdapter, "resolve_model_version",
            lambda _self, _response: "gemini-3.8-flash",
        )
        session = DispatchSession(
            spacing_sec=0.0, max_spend=0.0004, prices=table,
            priced_on=date(2026, 9, 27),
        )
        calls = scripted(claude_response())

        outcomes = [
            dispatch_case(minimal_case, "claude", _plan(tmp_path), session, index)
            for index in range(4)
        ]

        stopped = [entry for entry in outcomes if not entry.measured]
        assert stopped, "the ceiling never engaged, so it protects nothing"
        assert stopped[0].taxonomy_code == "QC_HARNESS_BUDGET_EXHAUSTED"
        # SPENDING STOPPED IT, not an unpriced model.
        assert not session.unpriced
        assert session.spent >= session.max_spend
        # THE REQUESTS AFTER THE CEILING WERE NEVER ISSUED, which is the point:
        # a ceiling that only reports is an invoice, not a control.
        assert len(calls) == len(outcomes) - len(stopped)

    def MQC_EXE_UNI_10302_a_run_with_no_ceiling_is_unchanged(
        self, minimal_case: EvaluationCase, tmp_path: Path, scripted: Any
    ) -> None:
        """Zero means no ceiling, and every replay gate relies on that.

        **The default must not gate anything.** Replay spends nothing, so a
        ceiling there would be a number to get wrong rather than a protection,
        and a run that stopped because of an unset budget would fail every
        pull request.

        Args:
            minimal_case (Any): The case to dispatch.
            tmp_path (Any): pytest's temporary directory.
            scripted (Any): Dispatch scripting helper.

        Returns:
            None
        """
        session = DispatchSession(spacing_sec=0.0)
        scripted(claude_response())

        outcomes = [
            dispatch_case(minimal_case, "claude", _plan(tmp_path), session, index)
            for index in range(4)
        ]

        assert all(entry.measured for entry in outcomes)
        assert session.ceiling_reached() is False
        # UNPRICED, SO NOTHING ACCUMULATED, and the tokens still did.
        assert session.spent == 0.0
        assert session.usage.input_tokens > 0

    def MQC_EXE_UNI_10303_a_ceiling_against_an_unpriced_model_stops_the_run(
        self, minimal_case: EvaluationCase, tmp_path: Path, scripted: Any
    ) -> None:
        """A cap that cannot be enforced must not look enforced.

        **This was a real hole, found by a case that would not fail.** An
        unpriced model's responses cost nothing the harness can compute, so
        `spent` never grew and the ceiling never engaged: a run configured with a
        budget would have spent without limit while reporting a cap.

        **`claude-opus-5-5` is exactly this case.** It is deliberately unpriced,
        it is the model a new key would most likely point at, and its thinking
        cannot be disabled, so it is the worst model to be silently uncapped
        against.

        Args:
            minimal_case (Any): The case to dispatch.
            tmp_path (Any): pytest's temporary directory.
            scripted (Any): Dispatch scripting helper.

        Returns:
            None
        """
        table = load_price_table(_REPOSITORY_ROOT / "config" / "pricing.yaml")
        session = DispatchSession(
            spacing_sec=0.0, max_spend=10.0, prices=table,
            priced_on=date(2026, 9, 27),
        )
        calls = scripted(claude_response())

        first = dispatch_case(minimal_case, "claude", _plan(tmp_path), session, 0)
        second = dispatch_case(minimal_case, "claude", _plan(tmp_path), session, 1)

        # THE FIRST IS MEASURED, because the model is only discovered to be
        # unpriced once a response reports which model served it.
        assert first.measured is True
        assert session.unpriced, "the unpriced model was not recorded"
        # AND THE RUN STOPS, far below a ceiling of ten dollars, because the
        # ceiling cannot be honoured at all rather than because it was reached.
        assert second.measured is False
        assert second.taxonomy_code == "QC_HARNESS_BUDGET_EXHAUSTED"
        assert session.spent == 0.0
        assert len(calls) == 1

    def MQC_EXE_UNI_10304_an_empty_balance_is_its_own_code_not_an_auth_failure(
        self,
    ) -> None:
        """A valid key with no money is not a rejected key.

        **Reachable from 2026-09-28**, when the project first held prepaid
        credit that could run out. Before that no request could return 402, and
        the status fell through to `QC_HARNESS_PARSER_ERROR`: at the moment the
        true cause was an empty balance, the run would have reported that it
        could not parse something.

        **Not the auth code, deliberately.** `.env.example` already says an
        authenticated key is not a funded one, and sending a reader to rotate a
        credential that works is the wrong remedy at the wrong level. This is
        environmental, like the no-credit variant of a 429: the fix is money,
        which no run can supply, so nothing retries it.

        Returns:
            None
        """
        assert taxonomy_for_status(402) == "QC_HARNESS_CREDIT_EXHAUSTED"
        assert taxonomy_for_status(401) == "QC_HARNESS_AUTH_ERROR"
        assert "QC_HARNESS_CREDIT_EXHAUSTED" in registered_codes()
        # NOT RETRYABLE. A retry asks a question already answered, and the
        # answer does not change until somebody pays.
        assert "QC_HARNESS_CREDIT_EXHAUSTED" not in _RETRYABLE_CODES
