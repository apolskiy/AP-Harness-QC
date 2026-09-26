# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Whether the model invoked what it was told to, and nothing it was not.

Covers ``MQC_EVL_UNI_10383`` through ``10387``, inventoried and specified in
``docs/design/tier3_evaluation.md`` section 5B, which owns the ``EVL`` block.

**Built from the real records rather than from doubles.** The evaluator takes
its arguments loosely, so Tier 3 does not import Tier 1's record for an
attribute walk, and a double would verify the duck typing against itself. These
pass the actual ``ToolCall``, ``ToolDefinition`` and ``ToolExpectation``, which
is what will reach it in a run.

A failure here is our defect, so the module carries no priority marker.
"""

from typing import Any

import pytest

from evaluation.tool_compliance import evaluate_tool_compliance
from execution.normalize import ToolCall
from ingestion.schemas import ToolDefinition, ToolExpectation

pytestmark = pytest.mark.unit


def _call(tool_name: str, sequence: int = 0, **arguments: Any) -> ToolCall:
    """Build one captured tool call.

    Args:
        tool_name (str): The tool the model named.
        sequence (int): Order within the response.
        **arguments: The arguments the model sent.

    Returns:
        ToolCall: The captured intent.
    """
    return ToolCall(tool_name=tool_name, arguments=dict(arguments), sequence=sequence)


def _tool(tool_name: str, schema: Any = None) -> ToolDefinition:
    """Build one offered tool.

    Args:
        tool_name (str): The name the model may invoke.
        schema (Any): Its declared parameter schema.

    Returns:
        ToolDefinition: The offered tool.
    """
    return ToolDefinition(
        tool_name=tool_name,
        description=f"{tool_name} does something",
        parameters_schema=schema or {},
    )


_LOOKUP = _tool(
    "lookup_order",
    {
        "type": "object",
        "properties": {"order_id": {"type": "string"}, "limit": {"type": "integer"}},
        "required": ["order_id"],
    },
)
_REFUND = _tool("issue_refund")


class TestMQCToolCompliance:
    """Gate 5 had no evaluator, and the corpus would have concealed it."""

    def MQC_EVL_UNI_10383_a_required_tool_not_invoked_is_reported(self) -> None:
        """A tool the model was told to use and did not.

        Returns:
            None
        """
        expectation = ToolExpectation(required_tools=frozenset({"lookup_order"}))

        results = evaluate_tool_compliance((), expectation, (_LOOKUP,))

        assert len(results) == 1
        assert not results[0].passed
        assert results[0].taxonomy_code == "QC_LLM_TOOL_VIOLATION"
        assert "lookup_order" in results[0].detail

        # Invoking it satisfies the requirement, and satisfying it reports
        # nothing rather than reporting a pass.
        assert not evaluate_tool_compliance(
            (_call("lookup_order", order_id="A-1"),), expectation, (_LOOKUP,)
        )

    def MQC_EVL_UNI_10384_a_forbidden_tool_invoked_is_reported(self) -> None:
        """A tool the model was told not to use and did.

        Returns:
            None
        """
        expectation = ToolExpectation(forbidden_tools=frozenset({"issue_refund"}))

        results = evaluate_tool_compliance(
            (_call("issue_refund", amount=50),), expectation, (_LOOKUP, _REFUND)
        )

        codes = [entry.taxonomy_code for entry in results]
        assert "QC_LLM_TOOL_VIOLATION" in codes
        assert any("issue_refund" in entry.detail for entry in results)

        # NOT INVOKING IT IS THE WHOLE REQUIREMENT, and reports nothing.
        assert not evaluate_tool_compliance(
            (_call("lookup_order", order_id="A-1"),), expectation, (_LOOKUP, _REFUND)
        )

    def MQC_EVL_UNI_10385_a_tool_absent_from_the_offered_set_is_reported(
        self,
    ) -> None:
        """A name the model invented, which no forbidden list would catch.

        **This is the check not implied by the other two.** A forbidden list
        names the tools an author thought of; the offered set is everything
        that exists.

        Returns:
            None
        """
        expectation = ToolExpectation(forbidden_tools=frozenset({"issue_refund"}))

        results = evaluate_tool_compliance(
            (_call("delete_account", user="root"),), expectation, (_LOOKUP, _REFUND)
        )

        assert results, (
            "a tool nobody offered was invoked and nothing reported it, so the "
            "forbidden list is the only protection there is"
        )
        assert any(
            entry.assertion_id == "A_TOOL_WAS_OFFERED" for entry in results
        )
        assert any("delete_account" in entry.detail for entry in results)

        # AN EMPTY OFFERED SET REPORTS NOTHING. A task that offered no tools
        # gives no basis for saying which names exist, and reporting every call
        # would fire on every case that declares none.
        assert not evaluate_tool_compliance(
            (_call("anything_at_all"),), ToolExpectation(), ()
        )

    def MQC_EVL_UNI_10386_no_expectation_and_a_satisfied_one_both_report_nothing(
        self,
    ) -> None:
        """The boundary runs both ways, and neither way records a pass.

        A blank taking its default is normal operation, so recording a passing
        result would corrupt every later count of tool behaviour.

        Returns:
            None
        """
        # NO EXPECTATION AT ALL, which is the common case: most rule sets make
        # no tool claim and must not be reported as complying or failing.
        #
        # ASSERTED WITH A CALL THAT WOULD OTHERWISE VIOLATE, an invented name
        # carrying an undeclared argument. A compliant call here would pass
        # whether or not the absent expectation short-circuits, which is how
        # this was first written and what injecting that defect exposed.
        assert not evaluate_tool_compliance(
            (_call("delete_account", sudo=True),), None, (_LOOKUP, _REFUND)
        ), (
            "an absent tool expectation produced results, so a rule set making "
            "no tool claim is judged against one"
        )

        # AN EXPECTATION THE RESPONSE SATISFIES, exactly.
        expectation = ToolExpectation(
            required_tools=frozenset({"lookup_order"}),
            forbidden_tools=frozenset({"issue_refund"}),
        )
        assert not evaluate_tool_compliance(
            (_call("lookup_order", order_id="A-1", limit=5),),
            expectation,
            (_LOOKUP, _REFUND),
        )

        # AND AN EXPECTATION CARRYING NEITHER SET, which is a claim about
        # nothing and must behave like the satisfied case rather than the
        # absent one.
        assert not evaluate_tool_compliance(
            (_call("lookup_order", order_id="A-1"),), ToolExpectation(), (_LOOKUP,)
        )

    def MQC_EVL_UNI_10387_tool_arguments_violating_the_declared_schema_are_reported(
        self,
    ) -> None:
        """Calling the right tool wrongly is a different defect.

        It carries `QC_LLM_SCHEMA_VIOLATION` rather than the tool code, because
        one code covering both would make them indistinguishable in the record.

        Returns:
            None
        """
        expectation = ToolExpectation(required_tools=frozenset({"lookup_order"}))

        # A REQUIRED ARGUMENT OMITTED.
        missing = evaluate_tool_compliance(
            (_call("lookup_order", limit=5),), expectation, (_LOOKUP,)
        )
        assert [entry.taxonomy_code for entry in missing] == [
            "QC_LLM_SCHEMA_VIOLATION"
        ]
        assert "order_id" in missing[0].detail

        # AN ARGUMENT NOBODY DECLARED.
        invented = evaluate_tool_compliance(
            (_call("lookup_order", order_id="A-1", sudo=True),),
            expectation,
            (_LOOKUP,),
        )
        assert invented and invented[0].taxonomy_code == "QC_LLM_SCHEMA_VIOLATION"

        # THE WRONG TYPE. A string where an integer was declared.
        mistyped = evaluate_tool_compliance(
            (_call("lookup_order", order_id="A-1", limit="five"),),
            expectation,
            (_LOOKUP,),
        )
        assert mistyped and "limit" in mistyped[0].detail

        # A BOOLEAN IS NOT AN INTEGER, although Python says bool is a subclass
        # of int. A flag sent where a count was declared would otherwise pass.
        flagged = evaluate_tool_compliance(
            (_call("lookup_order", order_id="A-1", limit=True),),
            expectation,
            (_LOOKUP,),
        )
        assert flagged, "a boolean passed where an integer was declared"

        # A TOOL WITH NO DECLARED SCHEMA CONSTRAINS NOTHING, so any arguments
        # conform and nothing is reported.
        assert not evaluate_tool_compliance(
            (_call("issue_refund", anything=1),),
            ToolExpectation(required_tools=frozenset({"issue_refund"})),
            (_REFUND,),
        )
