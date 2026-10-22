# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Stand-ins for the pytest objects the run-context cases hand the harness.

Created: 2026-10-21
Last updated: 2026-10-21

This file contains ``StubConfig``, a configuration answering ``getoption`` from
a mapping and carrying an invocation, ``stub_items``, which builds collected
items from node identifiers, ``workflow_environment``, which builds the
variables GitHub Actions sets for one workflow file, and ``provenance_for``,
which builds the provenance a precondition record is matched against.

``tests/cmn/mqc_uni_run_context.py`` uses them, so a case module holds only
cases (``harness_test_taxonomy.md`` section 13).
"""

from dataclasses import dataclass, field
from typing import Any

from cmn.options import build_invocation
from cmn.prerequisites import Provenance

PRECONDITION_NODE = "tests/cmn/mqc_uni_sample.py::TestMQCSample::MQC_CMN_UNI_119990_sample"
GRADED_NODE = "tests/cases/mqc_eval_sample.py::TestMQCSample::MQC_CAS_EVAL_131990_sample"


@dataclass
class StubConfig:
    """A configuration answering ``getoption`` from a mapping.

    Attributes:
        options (dict): Option name, with its dashes, to value.
        supplied (dict): The selectors the invocation was built from.
    """

    options: dict[str, Any] = field(default_factory=dict)
    supplied: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Build the invocation the way ``configure_invocation`` records it.

        Returns:
            None
        """
        self.mqc_invocation = build_invocation(self.supplied)

    def getoption(self, name: str, default: Any = None) -> Any:
        """Return a named option, or the default.

        Args:
            name (str): The option, with its dashes.
            default (Any): What an absent option reads as.

        Returns:
            Any: The value.
        """
        return self.options.get(name, default)


@dataclass(frozen=True)
class StubItem:
    """A collected item, carrying the node identifier the harness reads.

    Attributes:
        nodeid (str): The pytest node identifier.
    """

    nodeid: str


def stub_items(*nodeids: str) -> list[StubItem]:
    """Return one collected item per node identifier.

    Args:
        *nodeids (str): The identifiers.

    Returns:
        list[StubItem]: The items, in order.
    """
    return [StubItem(nodeid) for nodeid in nodeids]


def workflow_environment(workflow_file: str) -> dict[str, str]:
    """Return the variables GitHub Actions sets for a run of one workflow file.

    Args:
        workflow_file (str): The file name under ``.github/workflows``.

    Returns:
        dict: ``GITHUB_ACTIONS`` and ``GITHUB_WORKFLOW_REF``.
    """
    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_WORKFLOW_REF": (
            f"apolskiy/AP-Model-QC/.github/workflows/{workflow_file}@refs/heads/main"
        ),
    }


def provenance_for(code_ref: str, case_ref: str = "c0ffee") -> Provenance:
    """Return the provenance a precondition record is written or matched with.

    Args:
        code_ref (str): The harness commit.
        case_ref (str): The corpus commit.

    Returns:
        Provenance: Engine and mode set, as a graded band's would be.
    """
    return Provenance(
        code_ref=code_ref, case_ref=case_ref, engine="openai", mode="live",
        platform="Linux", band="0",
    )
