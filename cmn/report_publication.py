# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The report publication check: what a repository's workflows must hold to publish its report.

Created: 2026-11-19
Last updated: 2026-11-19

This file contains ``report_publication_gaps``, which reads a repository's
workflows and reports what stops its Allure report reaching GitHub Pages: no
job generating it, a generating job that deploys itself or uploads no Pages
artifact, no job needing it that deploys, a deploying job without the Pages
permissions, a publisher a pull request can reach unguarded, a trend not
carried forward, inclusion decided from a run's conclusion, and a publisher
beside gates that fails hard.

Precondition cases in both repositories call it with their own root:
``MQC_CMN_UNI_420005`` and ``420011`` here, ``MQC_CAS_UNI_430002`` in the case
repository.

Split from ``workflow_standards.py`` on 2026-11-19, when the deploy split took
that module past its nine-hundred-line runway (``code-style.md`` section 5.1).

Specified by ``docs/design/harness_ci_pipeline.md`` sections 7.4 to 7.4.6.
"""

import re
from pathlib import Path
from typing import Any, Final

import yaml


# THE PUBLISHING JOB, by what it does rather than by its name. A job is the
# publisher when it generates the report; everything else is checked of that
# job, so a renamed job is still found (`harness_ci_pipeline.md` 7.4).
_GENERATE_COMMAND: Final[str] = "allure generate"
_DEPLOY_ACTION: Final[str] = "actions/deploy-pages"

# WHAT THE GENERATING JOB HANDS THE DEPLOYING JOB. The deploy runs in a job of
# its own that needs the uploader, because an artifact is listed for the run
# reliably once its job has ended (`harness_ci_pipeline.md` 7.4.6).
_PAGES_UPLOAD: Final[str] = "actions/upload-pages-artifact"

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

# A PUBLISHER DECIDING FROM A RUN'S CONCLUSION, in the job's condition or in
# the step that selects which runs to download. `harness_ci_pipeline.md`
# section 7.4 makes the report a readiness view, and a readiness view that
# drops the engines carrying findings reads as though everything passed; the
# case repository's `consumer_ci.md` section 4.22.2 decides inclusion by head
# commit and says nothing about conclusion.
#
# **Both spellings, because the two surfaces differ.** A job condition reads
# `github.event.workflow_run.conclusion`, and the artifact lookup filters a
# `gh run list` with a `.conclusion` field. Matching only the first left the
# second in place for a week.
_CONCLUSION: Final[re.Pattern] = re.compile(
    r"workflow_run\.conclusion|\.conclusion\s*==|--status[ =]+success"
)


def report_publication_gaps(root: Path) -> list[str]:
    """Report what stops this repository publishing a readable report.

    One job generates the report and uploads the site, and a second job that
    needs it deploys the site. The generating job is checked for existing, for
    uploading rather than deploying itself, and for carrying the trend forward;
    a job needing it must deploy, and declares the deployment permissions
    itself.
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
    for name, job_name, reachable, jobs in publishers:
        problems.extend(_publisher_problems(name, job_name, reachable, jobs))
    return problems


def _publishing_jobs(
    root: Path,
) -> list[tuple[str, str, bool, dict[str, Any]]]:
    """Return every job that generates a report, with its workflow's trigger and jobs.

    Args:
        root (Path): The repository root.

    Returns:
        list: The workflow's filename, the job's name, whether its workflow
        can be triggered by a pull request, and every job of that workflow.
    """
    publishers: list[tuple[str, str, bool, dict[str, Any]]] = []
    for workflow in sorted((root / ".github" / "workflows").glob("*.yml")):
        definition = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
        # `on:` IS READ AS A BOOLEAN BY A YAML 1.1 LOADER, which is why the
        # true key is tried first and the word second.
        triggers = definition.get(True, definition.get("on", {})) or {}
        reachable = _PULL_REQUEST in set(triggers)
        jobs = {str(name): job or {} for name, job in (definition.get("jobs") or {}).items()}
        for job_name, job in jobs.items():
            if _GENERATE_COMMAND in _job_text(job, "run"):
                publishers.append((workflow.name, job_name, reachable, jobs))
    return publishers


def _job_text(job: dict[str, Any], key: str) -> str:
    """Return one field of every step of a job, joined.

    Args:
        job (dict): The job definition.
        key (str): ``run`` or ``uses``.

    Returns:
        str: The fields, space separated, empty where none is set.
    """
    return " ".join(str((step or {}).get(key) or "") for step in job.get("steps") or [])


def _deployers(jobs: dict[str, Any], generator: str) -> dict[str, dict[str, Any]]:
    """Return the jobs that deploy the site and need the generating job.

    Args:
        jobs (dict): Every job of the workflow, by name.
        generator (str): The generating job's name.

    Returns:
        dict: Name to job, for each job using the deploy action whose
        ``needs:`` names the generating job.
    """
    found: dict[str, dict[str, Any]] = {}
    for name, job in jobs.items():
        needs = job.get("needs") or []
        needed = [needs] if isinstance(needs, str) else list(needs)
        if _DEPLOY_ACTION in _job_text(job, "uses") and generator in needed:
            found[name] = job
    return found


def _publisher_problems(
    workflow: str, generator: str, reachable: bool, jobs: dict[str, Any]
) -> list[str]:
    """Report what one generating job, and the jobs deploying what it uploads, are missing.

    Args:
        workflow (str): The workflow's filename, for the message.
        generator (str): The generating job's name.
        reachable (bool): Whether a pull request can trigger its workflow.
        jobs (dict): Every job of the workflow, by name.

    Returns:
        list[str]: One entry per missing property, empty where it publishes as
        section 7.4 states.
    """
    problems: list[str] = []
    job = jobs[generator]
    where = f"{workflow} job {generator}"
    scripts = _job_text(job, "run")
    deployers = _deployers(jobs, generator)

    if _DEPLOY_ACTION in _job_text(job, "uses"):
        problems.append(
            f"{where} deploys in the job that uploaded the site, so the deploy can "
            f"look for the Pages artifact before the run lists it and find none. "
            f"Deploy from a job that needs this one"
        )
    elif _PAGES_UPLOAD not in _job_text(job, "uses"):
        problems.append(
            f"{where} generates the report and does not use {_PAGES_UPLOAD}, so "
            f"there is nothing for a deploy to publish"
        )
    if not deployers and _DEPLOY_ACTION not in _job_text(job, "uses"):
        problems.append(
            f"{where} generates the report and no job that needs it uses "
            f"{_DEPLOY_ACTION}, so nothing publishes what it rendered"
        )
    for name, deployer in deployers.items():
        missing = [one for one in _DEPLOY_PERMISSIONS
                   if one not in set(deployer.get("permissions") or {})]
        if missing:
            problems.append(
                f"{workflow} job {name} deploys and declares no {', '.join(missing)} "
                f"permission of its own, so the deploy fails or depends on a "
                f"workflow-wide grant"
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
    conditioned = _CONCLUSION.search(str(job.get("if") or "")) or _CONCLUSION.search(scripts)
    if conditioned:
        problems.append(
            f"{where} decides what to publish from a run's conclusion, so an "
            f"engine carrying findings publishes nothing and the site reads as "
            f"though everything passed. Inclusion is by head commit"
        )
    # BESIDE GATES MEANS A JOB THAT IS NEITHER THIS GENERATOR NOR ITS DEPLOYER,
    # so a workflow holding only the two has no conclusion to poison (7.4.3).
    beside_gates = set(jobs) - {generator} - set(deployers)
    for name, each in {generator: job, **deployers}.items():
        if beside_gates and not each.get(_SOFT_FAILURE):
            problems.append(
                f"{workflow} job {name} publishes beside other jobs and declares no "
                f"{_SOFT_FAILURE}, so a rendering failure concludes the whole run "
                f"failure and every consumer pinning the commit refuses it"
            )
    return problems
