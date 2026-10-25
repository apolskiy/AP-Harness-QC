# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Workflow standards checks, what the CI definitions must hold, checked before a push.

Created: 2026-10-04
Last updated: 2026-10-24

This file contains ``uncapped_spending_steps``, which reports a workflow step
that can spend on a provider and names no ``--max-spend`` ceiling;
``pylint_invocations`` and ``disagreeing_pylint_invocations``, which report a
pylint command differing from its copies; ``duplicate_yaml_keys``;
``engine_list_gaps``, a workflow engine list disagreeing with the roster;
``unoffered_credentials``, a live-capable workflow missing a credential; and
``report_publication_gaps``, which reports a repository that renders no report
or renders one from a job that could publish a proposal's results.

Precondition cases in both repositories call these with their own root, so a
workflow defect fails the unit layer locally instead of surfacing in CI.

Specified by ``docs/design/harness_ci_pipeline.md`` sections 8.2, 8.3, 8.5 and
8.5.4.

**Split from ``code_standards.py`` on 2026-10-04**, when these took that module
past the thousand-line ceiling. The concerns differ: that module is about the
source a reader writes, this one about the pipeline definitions and the commands
written beside them.

**None of these replaces ``actionlint``**, which validates the workflow schema
and runs ``shellcheck`` over every ``run:`` block. They cover what reading the
definition can catch: a command that disagrees with its copies, a step that can
spend without a ceiling, and the one malformed-YAML class a parse accepts.
**What a step's shell says is not read here at all**, so a workflow change is
linted with ``actionlint`` before it is pushed, from the repository root
(``harness_ci_pipeline.md`` section 10.1).
"""

import logging
import re
from pathlib import Path
from typing import Any, Final, Iterable

import yaml

from cmn.branch_policy import BRANCH_KINDS, MAIN, name_problems
from cmn.metadata import DEBUG_PREFIX

logger = logging.getLogger(__name__)


_PYLINT_CALL: Final[re.Pattern] = re.compile(
    r"pylint\s+([^\n]*?--rcfile=\.pylintrc)"
)


_CEILING_FLAG: Final[str] = "--max-spend"


# A STEP THAT CAN REACH A PROVIDER. `--mode live` dispatches to the candidate
# and `--judge-mode live` dispatches to the judge whatever the candidate mode.
# Either spends. Design `harness_ci_pipeline.md` section 8.2.
_SPENDING_FLAGS: Final[tuple[str, ...]] = ("--mode live", "--judge-mode live")

# The triggers whose ``branches`` filter names a branch, and the filter that
# names every branch at once.
_BRANCH_FILTERED_EVENTS: Final[tuple[str, ...]] = ("push", "pull_request", "workflow_run")
_EVERY_BRANCH: Final[str] = "**"

# The cadence suffix of a workflow that runs only when somebody dispatches it,
# which is what makes it a debug workflow (harness_ci_pipeline.md section 2).
_ON_DEMAND_SUFFIX: Final[str] = "-on-demand.yml"
_UPLOAD_ACTION: Final[str] = "actions/upload-artifact"

# THE PUBLISHING JOB, by what it does rather than by its name. A job is the
# publisher when it generates the report; everything else is checked of that
# job, so a renamed job is still found (`harness_ci_pipeline.md` 7.4).
_GENERATE_COMMAND: Final[str] = "allure generate"
_DEPLOY_ACTION: Final[str] = "actions/deploy-pages"

# WHAT THE DEPLOYMENT NEEDS AND NOTHING ELSE MAY HAVE. Declared on the job
# rather than the workflow, so no step that runs a test can reach the
# credential that writes the site.
_DEPLOY_PERMISSIONS: Final[tuple[str, ...]] = ("pages", "id-token")

# WHAT KEEPS A RENDERING FAILURE OFF THE RUN'S CONCLUSION. A consumer's
# pairing resolver reads the conclusion of a workflow run, not of a job, so a
# publisher sharing a workflow with the gates has to fail softly or it refuses
# every consumer pinning the commit (`harness_ci_pipeline.md` 7.4.3).
_SOFT_FAILURE: Final[str] = "continue-on-error"

# A PULL REQUEST NEVER PUBLISHES. A fork's run cannot hold the credential, and
# a run that could would overwrite the branch's picture with a proposal's. The
# rule is about reachability rather than about one guard: a workflow a pull
# request cannot trigger needs no condition, and one it can needs the job to
# name the event.
_PULL_REQUEST: Final[str] = "pull_request"
_EVENT_GUARD: Final[str] = "github.event_name"

# THE TREND, WHICH ALLURE CARRIES BY READING THE PREVIOUS REPORT. A job that
# generates without fetching it publishes a report whose history starts again
# every run, which reads as a project with no past.
#
# A PATH AND NOT THE BARE WORD, so a job mentioning history in a comment does
# not satisfy it. **What this establishes is that the trend is fetched, not
# where it lands**: the destination is a directory name the job chooses, and
# one repository renders a report per engine into a directory of its own.
# The destination rule is stated in `harness_ci_pipeline.md` section 7.4.2
# and is not checked here.
_HISTORY: Final[str] = "/history/"

# A run withholding the judge, written literally, and the input value a debug
# workflow offers to ask for one (tier3_evaluation.md section 5A.5.3).
_JUDGE_OFF: Final[re.Pattern] = re.compile(r"--judge-mode[ =]+[\"']?off\b")
_UNJUDGED_CHOICE: Final[str] = "unjudged"

# AND THE ONE THAT BOUNDS IT. `--max-spend` aborts before a request would take
# the run past a figure, and fails closed on an unpriced model.


def uncapped_spending_steps(root: Path) -> list[str]:
    """Report every workflow step that can spend and names no ceiling.

    **The flag existed and nothing passed it**, which is this project's
    recurring shape: `--max-spend` is implemented and covered, and until
    2026-10-04 no workflow set a value, so a live run had no ceiling at all.
    That mattered the moment a credential reached Actions.

    **Keyed on the mode flags rather than on a job's environment.** A job can
    name ``environment: live`` and run only replay legs, and a step can spend
    from a workflow whose other jobs do not; what decides is whether the
    invocation dispatches live.

    **A matrix-valued mode counts as spending.** A step whose mode comes from
    ``matrix.mode`` may be live on one leg, so it is reported unless it carries
    a ceiling, on the same reasoning that makes the artifact check key on the
    flags rather than on the word pytest.

    Design: ``harness_ci_pipeline.md`` section 8.2.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per step, naming the workflow and the line. Empty
        when every step that can reach a provider carries a ceiling.
    """
    problems: list[str] = []
    for workflow in sorted((root / ".github" / "workflows").glob("*.yml")):
        for number, invocation in _shell_invocations(workflow):
            spends = any(flag in invocation for flag in _SPENDING_FLAGS)
            matrix_mode = "--mode ${{ matrix.mode }}" in invocation
            if not spends and not matrix_mode:
                continue
            if _CEILING_FLAG in invocation:
                continue
            problems.append(
                f"{workflow.name}:{number} can dispatch live and names no "
                f"{_CEILING_FLAG}, so the run has no ceiling"
            )
    return problems


def _shell_invocations(workflow: Path) -> list[tuple[int, str]]:
    """Return each shell command in a workflow as one logical line.

    **Continuations are joined first.** A pytest invocation in CI is written
    across several lines with trailing backslashes, so a line-based reader sees
    ``--mode live`` and ``--max-spend`` as different lines and reports a step
    that carries both. A check that over-reports is one a reader learns to
    skip, which is worse than the gap it was written for.

    Args:
        workflow (Path): The workflow file.

    Returns:
        list[tuple[int, str]]: The line the command starts on, and the command
        with its continuations joined.
    """
    joined: list[tuple[int, str]] = []
    pending: list[str] = []
    start = 0
    for number, line in enumerate(
        workflow.read_text(encoding="utf-8").splitlines(), start=1
    ):
        stripped = line.strip()
        if not pending:
            start = number
        if stripped.endswith("\\"):
            pending.append(stripped[:-1].strip())
            continue
        pending.append(stripped)
        joined.append((start, " ".join(pending)))
        pending = []
    if pending:
        joined.append((start, " ".join(pending)))
    return joined


# EVERY PYLINT INVOCATION IN THE REPOSITORY, wherever it is written. The path
# list is part of the command: a directory omitted from one copy passes that
# gate and fails another, which arrives as a red on a commit already reported
# green. Design `harness_ci_pipeline.md` section 8.3.


def pylint_invocations(root: Path, runbook: str) -> dict[str, list[str]]:
    """Return every pylint invocation written in the repository, by file.

    Reads the workflows and the tracked prose, because a documented command a
    reader copies is as load-bearing as the one CI runs: a contributor who
    lints less than the gate does finds out from the gate.

    Args:
        root (Path): The repository root.
        runbook (str): The runbook's path relative to that root, supplied by the
            caller because the two repositories name theirs differently
            (`code-style.md` section 7.2).

    Returns:
        dict[str, list[str]]: Relative path to each invocation's argument
        string, normalised on whitespace so formatting is not a difference.
    """
    found: dict[str, list[str]] = {}
    sources = sorted((root / ".github" / "workflows").glob("*.yml"))
    sources += [
        root / ".claude" / "rules" / "testing-standards.md",
        root / runbook,
    ]
    for source in sources:
        if not source.is_file():
            continue
        calls = [
            " ".join(match.split())
            for match in _PYLINT_CALL.findall(source.read_text(encoding="utf-8"))
        ]
        if calls:
            found[source.relative_to(root).as_posix()] = calls
    return found


def disagreeing_pylint_invocations(root: Path, runbook: str) -> list[str]:
    """Report every pylint invocation that differs from the others.

    **The path list is part of the command.** Four copies stood with four
    different lists until 2026-10-04: one omitted ``cmn/``, two omitted
    ``conftest.py``, the gate omitted ``tools/``. A file in an omitted
    directory passes the gate and fails the branch regression, which arrives as
    a red on a commit that was already reported green.

    Design: ``harness_ci_pipeline.md`` section 8.3.

    Args:
        root (Path): The repository root.
        runbook (str): The runbook's path relative to that root, which the two
            repositories name differently (`code-style.md` section 7.2).

    Returns:
        list[str]: One entry per invocation that is not the majority form,
        empty when every copy agrees.
    """
    found = pylint_invocations(root, runbook)
    everything = [call for calls in found.values() for call in calls]
    if not everything:
        return [
            "no pylint invocation was found at all, so this reader would "
            "report agreement by having read nothing"
        ]

    agreed = max(set(everything), key=everything.count)
    return [
        f"{where} runs pylint over {call!r} while the rest run it over "
        f"{agreed!r}"
        for where, calls in sorted(found.items())
        for call in calls
        if call != agreed
    ]


def duplicate_yaml_keys(root: Path) -> list[str]:
    """Report every tracked YAML file carrying a duplicated mapping key.

    **This is the class a parse accepts and a schema rejects.** YAML permits a
    duplicate key and resolves it last-wins, so a stanza given a second
    ``inputs:`` block loses the first silently along with whatever it declared,
    while GitHub rejects the file outright.

    **Composed rather than loaded.** ``yaml.compose`` returns the node tree
    before any mapping is constructed, so the duplicate is still visible; a
    loader that constructs the mapping has already resolved it. It needs no
    loader subclass either, which the ancestor limit in ``.pylintrc`` refuses.

    Design: ``harness_ci_pipeline.md`` section 8.3.2.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per offending file, naming the key and the line.
    """
    problems: list[str] = []
    sources = sorted((root / ".github" / "workflows").glob("*.yml"))
    sources += sorted((root / "config").glob("*.yaml"))
    for source in sources:
        try:
            tree = yaml.compose(source.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            problems.append(f"{source.name}: will not parse at all, {error}")
            continue
        if tree is not None:
            problems.extend(
                f"{source.name}: {detail}" for detail in _repeated_keys(tree)
            )
    return problems


def engine_list_gaps(root: Path, roster: Iterable[str]) -> list[str]:
    """Report every workflow engine list that disagrees with the roster.

    Reads each ``engine`` choice input under ``workflow_dispatch`` or
    ``workflow_call`` and each ``engine`` matrix dimension written as a list.
    A list is reported when it omits a rostered engine or names one the roster
    does not carry; order is not compared. A free-text input and a matrix
    written as ``include`` entries are not read.

    Design: ``harness_ci_pipeline.md`` section 8.5.

    Args:
        root (Path): The repository root.
        roster (Iterable[str]): The rostered engine names.

    Returns:
        list[str]: One entry per disagreeing list, naming the workflow, the
        list and the engines missing or extra. Empty when every list agrees.
    """
    expected = set(roster)
    problems: list[str] = []
    for workflow in sorted((root / ".github" / "workflows").glob("*.yml")):
        definition = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
        for where, listed in _engine_lists(definition):
            missing = sorted(expected - set(listed))
            extra = sorted(set(listed) - expected)
            if missing or extra:
                problems.append(
                    f"{workflow.name} {where} offers {listed}: missing "
                    f"{missing}, not on the roster {extra}"
                )
    return problems


def collectable_debug_uploads(root: Path) -> list[str]:
    """Report every artifact a debug workflow uploads without the debug prefix.

    A debug workflow is one whose cadence is ``on-demand``. Each of its
    ``actions/upload-artifact`` steps must name the artifact with
    :data:`cmn.metadata.DEBUG_PREFIX`, so a collector matching the collected
    prefix never picks a debug run up.

    Design: ``cmn_verdict_and_cli.md`` section 7.1.3.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per offending upload, naming the workflow, the
        job and the artifact name. Empty when every debug upload is prefixed.
    """
    problems: list[str] = []
    for workflow in sorted((root / ".github" / "workflows").glob(f"*{_ON_DEMAND_SUFFIX}")):
        definition = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
        for job_name, job in (definition.get("jobs") or {}).items():
            for step in (job or {}).get("steps") or []:
                if not str(step.get("uses", "")).startswith(_UPLOAD_ACTION):
                    continue
                name = str((step.get("with") or {}).get("name", "")).strip()
                if not name.startswith(DEBUG_PREFIX):
                    problems.append(
                        f"{workflow.name} job {job_name} uploads {name!r}, which does not "
                        f"start with {DEBUG_PREFIX!r}"
                    )
    return problems


def report_publication_gaps(root: Path) -> list[str]:
    """Report what stops this repository publishing a readable report.

    One job generates the report and deploys it. Four properties are checked
    of it: that it exists, that it deploys what it generated, that it declares
    the deployment permissions itself, and that it carries the trend forward.
    A fifth is checked of its reachability: a job in a workflow a pull request
    can trigger names the event, and a job in a workflow a pull request cannot
    reach needs no condition.

    **Keyed on the command rather than on a job name**, so renaming the job
    does not silence the check, which is the same reasoning
    :func:`artifact_mandate_gaps` uses about the artifact flags.

    Design: ``harness_ci_pipeline.md`` section 7.4.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per gap, empty where the report is published as
        the design states.
    """
    publishers = _publishing_jobs(root)
    if not publishers:
        return [
            f"no workflow runs {_GENERATE_COMMAND!r}, so the raw results are published "
            f"and nothing renders them"
        ]

    problems: list[str] = []
    for name, job_name, job, reachable, shares in publishers:
        problems.extend(
            _publisher_problems(f"{name} job {job_name}", job, reachable, shares)
        )
    return problems


def _publishing_jobs(
    root: Path,
) -> list[tuple[str, str, dict[str, Any], bool, bool]]:
    """Return every job that generates a report, with what its workflow exposes it to.

    Args:
        root (Path): The repository root.

    Returns:
        list: The workflow's filename, the job's name, the job, whether its
        workflow can be triggered by a pull request, and whether other jobs
        share that workflow.
    """
    publishers: list[tuple[str, str, dict[str, Any], bool, bool]] = []
    for workflow in sorted((root / ".github" / "workflows").glob("*.yml")):
        definition = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
        # `on:` IS READ AS A BOOLEAN BY A YAML 1.1 LOADER, which is why the
        # true key is tried first and the word second.
        triggers = definition.get(True, definition.get("on", {})) or {}
        reachable = _PULL_REQUEST in set(triggers)
        for job_name, job in (definition.get("jobs") or {}).items():
            scripts = " ".join(
                str((step or {}).get("run") or "") for step in (job or {}).get("steps") or []
            )
            if _GENERATE_COMMAND in scripts:
                publishers.append((
                    workflow.name, str(job_name), job or {}, reachable,
                    len(definition.get("jobs") or {}) > 1,
                ))
    return publishers


def _publisher_problems(
    where: str, job: dict[str, Any], reachable: bool, shares: bool
) -> list[str]:
    """Report what one publishing job is missing.

    Args:
        where (str): The workflow and job, for the message.
        job (dict): The job definition.
        reachable (bool): Whether a pull request can trigger its workflow.
        shares (bool): Whether other jobs share its workflow, which decides
            whether its failure can reach the run's conclusion.

    Returns:
        list[str]: One entry per missing property, empty where it publishes as
        section 7.4 states.
    """
    problems: list[str] = []
    steps = [step or {} for step in job.get("steps") or []]
    uses = " ".join(str(step.get("uses") or "") for step in steps)
    scripts = " ".join(str(step.get("run") or "") for step in steps)
    granted = set((job.get("permissions") or {}))

    if _DEPLOY_ACTION not in uses:
        problems.append(
            f"{where} generates the report and does not use {_DEPLOY_ACTION}, so "
            f"nothing publishes what it rendered"
        )
    missing = [one for one in _DEPLOY_PERMISSIONS if one not in granted]
    if missing:
        problems.append(
            f"{where} publishes and declares no {', '.join(missing)} permission of "
            f"its own, so the deploy fails or depends on a workflow-wide grant"
        )
    if reachable and _EVENT_GUARD not in str(job.get("if") or ""):
        problems.append(
            f"{where} publishes from a workflow a pull request can trigger and "
            f"names no event condition, so a proposal could overwrite the default "
            f"branch's report with its own results"
        )
    if _HISTORY not in scripts:
        problems.append(
            f"{where} generates no history, so each published report starts the "
            f"trend again"
        )
    if shares and not job.get(_SOFT_FAILURE):
        problems.append(
            f"{where} publishes beside other jobs and declares no "
            f"{_SOFT_FAILURE}, so a rendering failure concludes the whole run "
            f"failure and every consumer pinning the commit refuses it"
        )
    return problems


def unjudged_gated_runs(root: Path) -> list[str]:
    """Report every workflow outside the on-demand cadence that can withhold the judge.

    A workflow is reported when it is not ``on-demand`` and either passes
    ``--judge-mode off`` or offers a ``judge`` dispatch input listing
    ``unjudged``. Only a debug run may check the assertions without the judge,
    so a gated workflow never reports a rubric-bearing case as unjudged.

    Design: ``tier3_evaluation.md`` section 5A.5.3.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per offending workflow, naming what it does.
        Empty when only on-demand workflows can withhold the judge.
    """
    problems: list[str] = []
    for workflow in sorted((root / ".github" / "workflows").glob("*.yml")):
        if workflow.name.endswith(_ON_DEMAND_SUFFIX):
            continue
        text = workflow.read_text(encoding="utf-8")
        if _JUDGE_OFF.search(text):
            problems.append(f"{workflow.name} passes --judge-mode off outside a debug run")
        definition = yaml.safe_load(text) or {}
        triggers = definition.get("on", definition.get(True)) or {}
        inputs = ((triggers.get("workflow_dispatch") or {}) if isinstance(triggers, dict)
                  else {}).get("inputs") or {}
        offered = (inputs.get("judge") or {}).get("options") or []
        if _UNJUDGED_CHOICE in [str(option) for option in offered]:
            problems.append(f"{workflow.name} offers a judge input of 'unjudged' outside a "
                            f"debug run")
    return problems


def unaccepted_branch_names(root: Path) -> list[str]:
    """Report every branch a workflow filter or a consumer pairing names wrongly.

    Reads the ``branches`` list of each workflow's ``push``, ``pull_request``
    and ``workflow_run`` trigger, and each key of a consumer's ``refs`` in
    ``config/consumers.yaml``. A name is accepted when it is ``main``, ``**``
    for every branch, passes :func:`cmn.branch_policy.name_problems`, or is a
    ``<kind>-*`` pattern over a registered kind.

    Design: ``harness_ci_pipeline.md`` section 3C.6.8.

    Args:
        root (Path): The repository root.

    Returns:
        list[str]: One entry per unaccepted name, naming the file and where it
        sits. Empty when every name is accepted.
    """
    named: list[tuple[str, str]] = []
    for workflow in sorted((root / ".github" / "workflows").glob("*.yml")):
        definition = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
        triggers = definition.get("on", definition.get(True)) or {}
        if not isinstance(triggers, dict):
            continue
        for event in _BRANCH_FILTERED_EVENTS:
            filters = triggers.get(event)
            if not isinstance(filters, dict):
                continue
            for branch in filters.get("branches") or []:
                named.append((f"{workflow.name} on.{event}.branches", str(branch)))
    consumers = root / "config" / "consumers.yaml"
    if consumers.exists():
        declared = yaml.safe_load(consumers.read_text(encoding="utf-8")) or {}
        for entry in declared.get("consumers") or []:
            for branch in (entry.get("refs") or {}):
                named.append((f"consumers.yaml {entry.get('name')} refs", str(branch)))
    return [
        f"{where}: {branch!r} is not main, **, an accepted branch name or a <kind>-* pattern"
        for where, branch in named
        if not _accepted_branch(branch)
    ]


def _accepted_branch(branch: str) -> bool:
    """Report whether a named branch or branch pattern is one the policy accepts.

    Args:
        branch (str): A branch name, or a pattern ending ``-*``.

    Returns:
        bool: True for ``main``, ``**``, an accepted name or a pattern over a
        kind.
    """
    if branch in (MAIN, _EVERY_BRANCH):
        return True
    if branch.endswith("-*"):
        return branch[:-2] in BRANCH_KINDS
    return not name_problems(branch)


def unoffered_credentials(root: Path, variables: Iterable[str]) -> list[str]:
    """Report every live-capable engine workflow missing a credential assignment.

    A workflow is read when it writes an engine list, as
    :func:`engine_list_gaps` reads one, and has a ``mode`` choice input
    offering ``live``. Each variable must be assigned from the secret of the
    same name somewhere in the workflow; a mention in a comment does not count.
    No secret value is read.

    Design: ``harness_ci_pipeline.md`` section 8.5.4.

    Args:
        root (Path): The repository root.
        variables (Iterable[str]): The credential variables the rostered
            adapters declare.

    Returns:
        list[str]: One entry per workflow, naming the variables it does not
        assign. Empty when every such workflow assigns them all.
    """
    required = sorted(set(variables))
    problems: list[str] = []
    for workflow in sorted((root / ".github" / "workflows").glob("*.yml")):
        body = workflow.read_text(encoding="utf-8")
        definition = yaml.safe_load(body) or {}
        if not _engine_lists(definition) or not _offers_live_mode(definition):
            continue
        missing = [
            name for name in required
            if not re.search(
                rf"^\s*{re.escape(name)}:\s*\$\{{\{{\s*secrets\.{re.escape(name)}\s*\}}\}}",
                body, re.MULTILINE,
            )
        ]
        if missing:
            problems.append(
                f"{workflow.name} can run any engine live and does not assign "
                f"{missing} from secrets, so a live run of that engine refuses "
                f"at preflight"
            )
    return problems


def _offers_live_mode(definition: dict[str, Any]) -> bool:
    """Return whether a parsed workflow has a ``mode`` choice offering ``live``.

    Args:
        definition (dict[str, Any]): The workflow, as ``yaml.safe_load``
            returns it.

    Returns:
        bool: True when a dispatch or call input named ``mode`` lists ``live``.
    """
    triggers = definition.get("on", definition.get(True)) or {}
    if not isinstance(triggers, dict):
        return False
    for trigger in ("workflow_dispatch", "workflow_call"):
        inputs = (triggers.get(trigger) or {}).get("inputs") or {}
        options = (inputs.get("mode") or {}).get("options")
        if isinstance(options, list) and "live" in options:
            return True
    return False


def _engine_lists(definition: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """Return each engine list a parsed workflow writes, with where it sits.

    Args:
        definition (dict[str, Any]): The workflow, as ``yaml.safe_load``
            returns it. YAML 1.1 reads the ``on`` key as ``True``.

    Returns:
        list[tuple[str, list[str]]]: The location, and the engines listed.
    """
    found: list[tuple[str, list[str]]] = []
    triggers = definition.get("on", definition.get(True)) or {}
    if isinstance(triggers, dict):
        for trigger in ("workflow_dispatch", "workflow_call"):
            inputs = (triggers.get(trigger) or {}).get("inputs") or {}
            options = (inputs.get("engine") or {}).get("options")
            if isinstance(options, list):
                found.append((f"{trigger} input engine", [str(name) for name in options]))
    for job_name, job in (definition.get("jobs") or {}).items():
        matrix = ((job or {}).get("strategy") or {}).get("matrix") or {}
        engines = matrix.get("engine") if isinstance(matrix, dict) else None
        if isinstance(engines, list):
            found.append((f"job {job_name} matrix engine", [str(name) for name in engines]))
    return found


def _repeated_keys(node: Any) -> list[str]:
    """Return a description of every duplicated key in a composed node tree.

    Args:
        node (Any): A composed YAML node.

    Returns:
        list[str]: One entry per duplicate, naming the key and its line.
    """
    found: list[str] = []
    if isinstance(node, yaml.MappingNode):
        seen: set[str] = set()
        for key_node, value_node in node.value:
            name = getattr(key_node, "value", None)
            if isinstance(name, str):
                if name in seen:
                    found.append(
                        f"QC_DATA_MALFORMED_SOURCE: key {name!r} appears twice "
                        f"in the same mapping at line "
                        f"{key_node.start_mark.line + 1}, and YAML would "
                        f"resolve it last-wins, discarding the first silently"
                    )
                seen.add(name)
            found.extend(_repeated_keys(value_node))
    elif isinstance(node, yaml.SequenceNode):
        for entry in node.value:
            found.extend(_repeated_keys(entry))
    return found
