# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Verdict computation: a pure function of observations, config and a date.

Specified by ``docs/design/cmn_verdict_and_cli.md`` section 4.

**No clock, no filesystem, no environment.** The evaluation date is injected
because quarantine expiry depends on it, and a function that calls ``now()``
cannot be tested at a boundary without manipulating the machine. That property
is what makes every rule here exercisable with synthetic observation sets.

**Every breached rule is reported, never only the first.** Short-circuiting
would mean fixing V1 and discovering V3 on the next run, then V4 on the one
after; for a suite whose live runs are scheduled rather than on demand, each
rediscovery costs a cycle.

**No metric divides without first testing its denominator for zero.** A zero
denominator means the question is unanswerable, which is never the same as the
answer being fine.

**Red does not always mean blocked.** This function returns red with reasons;
the workflow decides whether red blocks a merge. Putting that knowledge here
would couple a pure computation to CI topology.
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Final, Optional

from cmn.layers import (
    layer_properties,
    outcome_properties,
    skip_blocks,
    skip_counts_toward_rate,
)
from cmn.quarantine import (
    QUARANTINE_WINDOW_DAYS,
    QuarantineEntry,
    excluded_bands,
)
from cmn.observations import Observation

logger = logging.getLogger(__name__)

_NOTHING_MEASURED: Final[str] = "NOTHING_MEASURED"
_PRECONDITION_FAILED: Final[str] = "PRECONDITION_FAILED"
_RUN_UNSOUND: Final[str] = "RUN_UNSOUND"

# Below this many graded case definitions the distribution check reports counts
# and returns no verdict: one case moves the share by over three percent, so a
# ceiling expressed as a percentage says more about the population size than
# about priority inflation.
_DISTRIBUTION_MINIMUM: Final[int] = 30



@dataclass(frozen=True)
class Thresholds:
    """The standard a run is judged against.

    Thresholds are configuration, and the effective values are emitted into
    result metadata so the standard applied to a run is recoverable from its
    artifact.

    Attributes:
        pass_floor (float): Minimum overall pass rate (V2).
        skip_ceiling (float): Maximum total skip rate (V3).
        priority_skip_ceiling (float): Maximum P0 and P1 skip rate (V4).
        inconsistency_ceiling (float): Maximum share of measured cases whose
            repeat observations disagree, before the run is unsound
            (a `RUN_UNSOUND` condition, not a numbered verdict rule).
            **0.20 as of 2026-10-01**, decided once three corpora had been
            recorded. It was 0.10, matched to ``priority_skip_ceiling`` rather
            than derived, and the owner's judgement is that a suite carrying a
            fifth of its cases as wobbling has still measured something.
            **A statement about the run, not about a case**: whether one case's
            observations disagree stays binary, because a majority would discard
            the finding the repeats exist to produce (design sections 4.9.1 and
            4.9.2.1).
        p0_share_ceiling (float): Maximum share of case definitions at P0.
        p1_share_ceiling (float): Maximum share at P1.
        combined_share_ceiling (float): Maximum share at P0 and P1 together.
        distribution_minimum (int): Case definitions below which the
            distribution check reports counts without a verdict.
        quarantine_window_days (int): How long a quarantine entry stays
            valid when the model has not changed. **Recorded rather than
            constant** so a stored verdict stays recomputable; section
            4.6.2 gives the reasoning for 21.
    """

    pass_floor: float = 0.90
    skip_ceiling: float = 0.20
    priority_skip_ceiling: float = 0.10
    inconsistency_ceiling: float = 0.20
    p0_share_ceiling: float = 0.10
    p1_share_ceiling: float = 0.20
    combined_share_ceiling: float = 0.30
    distribution_minimum: int = _DISTRIBUTION_MINIMUM
    quarantine_window_days: int = QUARANTINE_WINDOW_DAYS




@dataclass(frozen=True)
class VerdictConfig:
    """Everything the verdict reads besides the observations themselves.

    Attributes:
        thresholds (Thresholds): The standard applied.
        quarantine (list): Entries excluded from the pass-rate denominator.
        unsupported_pairs (frozenset): Declared capability gaps, which are not
            environmental failures and must not consume skip budget (A13).
    """

    thresholds: Thresholds = field(default_factory=Thresholds)
    quarantine: list[QuarantineEntry] = field(default_factory=list)
    unsupported_pairs: frozenset[str] = frozenset()

    def quarantined_ids(self) -> frozenset[str]:
        """Return every quarantined case identifier.

        Returns:
            frozenset[str]: The identifiers.
        """
        return frozenset(entry.case_id for entry in self.quarantine)


@dataclass(frozen=True)
class RuleBreach:
    """One verdict rule that fired.

    Attributes:
        rule (str): The rule identifier, such as ``V2``.
        reason (str): What it found, stated so a reader needs no other context.
    """

    rule: str
    reason: str


@dataclass(frozen=True)
class DistributionReport:
    """What the priority distribution check found.

    Attributes:
        case_definitions (int): Unique case definitions in the denominator.
        p0_share (Optional[float]): Share at P0, absent below the minimum.
        p1_share (Optional[float]): Share at P1, absent below the minimum.
        combined_share (Optional[float]): Share at P0 and P1 together.
        demoted_count (int): How many cases were demoted from a higher level.
        verdict_returned (bool): Whether the check reached a verdict at all.
    """

    case_definitions: int
    demoted_count: int
    verdict_returned: bool
    p0_share: Optional[float] = None
    p1_share: Optional[float] = None
    combined_share: Optional[float] = None


@dataclass(frozen=True)
class Verdict:
    """What one run scored, and why.

    Attributes:
        green (bool): Whether the run passed every rule.
        breaches (list): **Every** rule that fired, not the first.
        exit_code (int): 0 green, 1 red, 3 precondition failure, 4 refused.
        pass_rate (Optional[float]): Absent when the denominator was zero.
        skip_rate (Optional[float]): Absent when the denominator was zero.
        score_spread (dict[str, float]): The range of judged scores per
            case across its observations. **Recorded rather than gated**: a
            score moving inside the passing band is information and not a
            failure, and gating it would need a second threshold nobody has
            evidence for. Absent where a case has fewer than two scores,
            because a range needs two points (design section 4.9.4).
        distribution (Optional[DistributionReport]): What the check found.
        quarantined (list): Case identifiers excluded from the pass rate.
        excluded_bands (dict): Each quarantined case that ran, and the
            priority band it sits in. **A pass over an excluded P0 or P1
            is a pass over an accepted release blocker**, which is the
            one thing a silent green did not say (section 4.6.11). A
            case with no observations is absent rather than banded,
            because nothing ran it.
        unconfirmed_quarantine (list): Case identifiers whose entry
            carries no date or no observed model, so its expiry could not
            be evaluated. **Not a breach**: carried beside them because
            `QC_HARNESS_*` never fails a run (section 4.6.4).
        thresholds (Thresholds): The standard applied, carried so a verdict is
            self-describing.
    """

    green: bool
    exit_code: int
    breaches: list[RuleBreach] = field(default_factory=list)
    pass_rate: Optional[float] = None
    skip_rate: Optional[float] = None
    score_spread: dict[str, float] = field(default_factory=dict)
    distribution: Optional[DistributionReport] = None
    quarantined: list[str] = field(default_factory=list)
    excluded_bands: dict[str, int] = field(default_factory=dict)
    unconfirmed_quarantine: list[str] = field(default_factory=list)
    thresholds: Thresholds = field(default_factory=Thresholds)

    @property
    def breached_rules(self) -> list[str]:
        """Return the identifiers of every rule that fired.

        Returns:
            list[str]: Rule identifiers in the order they were evaluated.
        """
        return [breach.rule for breach in self.breaches]


@dataclass(frozen=True)
class _Population:
    """The observation sets each denominator is computed over.

    Attributes:
        graded (list): Every graded observation.
        executions (list): Graded observations counting toward the pass rate,
            excluding quarantined cases.
        skippable (list): Graded observations counting toward the skip rate.
        skipped (list): Of those, the ones that skipped.
        priority_skippable (list): The P0 and P1 subset of ``skippable``.
        priority_skipped (list): Of those, the ones that skipped.
        resolved_model (str): The one model this run reported, or empty
            when it reported none or several. **Empty leaves the
            quarantine model trigger unevaluated**, because which of two
            models an entry should be compared against has no answer
            (design section 4.6.2).
    """

    graded: list[Observation]
    executions: list[Observation]
    skippable: list[Observation]
    skipped: list[Observation]
    priority_skippable: list[Observation]
    priority_skipped: list[Observation]
    resolved_model: str = ""


def verdict(
    observations: list[Observation],
    config: Optional[VerdictConfig] = None,
    as_of_date: Optional[date] = None,
) -> Verdict:
    """Compute one run's verdict.

    Args:
        observations (list): Every observation the run produced.
        config (Optional[VerdictConfig]): Thresholds, quarantine and declared
            unsupported pairs.
        as_of_date (Optional[date]): The injected evaluation date. **Required
            in substance**: it defaults to the minimum representable date so a
            caller that forgot it cannot silently pick up today and make
            quarantine expiry depend on when the function happened to run.

    Returns:
        Verdict: Green or red, with every breached rule and the metrics behind
        them.
    """
    settings = config or VerdictConfig()
    evaluated_on = as_of_date or date.min

    precondition = _evaluate_preconditions(observations)
    if precondition is not None:
        return precondition

    # AFTER THE PRECONDITIONS AND BEFORE THE GRADED RULES. A broken or
    # unfinished observation means the run cannot be trusted, so the graded
    # rules have nothing worth deciding about. cmn_verdict_and_cli.md 10.24.
    unsound = _evaluate_soundness(observations, settings.thresholds)
    if unsound is not None:
        return unsound

    population = _build_population(observations, settings)
    breaches: list[RuleBreach] = []
    for rule in registered_verdict_rules():
        fired, reason = rule(population, settings, evaluated_on)
        if fired:
            breaches.append(RuleBreach(rule=getattr(rule, "rule_id", "V?"), reason=reason))

    distribution = evaluate_distribution(observations, settings.thresholds)
    breaches.extend(_distribution_breaches(distribution, settings.thresholds))

    return Verdict(
        green=not breaches,
        exit_code=1 if breaches else 0,
        breaches=breaches,
        pass_rate=_rate(
            [entry for entry in population.executions if entry.passed],
            population.executions,
        ),
        skip_rate=_rate(population.skipped, population.skippable),
        # RECORDED, NEVER GATED. A score moving inside the passing band is
        # information about the judge and the response together, and the case
        # passed on every observation (design section 4.9.4).
        score_spread=score_spread(observations),
        distribution=distribution,
        quarantined=sorted(settings.quarantined_ids()),
        excluded_bands=excluded_bands(population.graded, settings.quarantined_ids()),
        unconfirmed_quarantine=sorted(
            entry.case_id for entry in settings.quarantine if not entry.confirmed
        ),
        thresholds=settings.thresholds,
    )



def inconsistent_cases(observations: list[Observation]) -> dict[str, set[str]]:
    """Return every case whose repeat observations disagree on outcome.

    **Two passes and a fail is not a pass.** No majority is taken, because a
    majority discards exactly the finding the repeats exist to produce: this
    model does not reliably do this (design section 4.9.1).

    **A case observed once cannot disagree with itself** and is absent from the
    result. That is the honest answer rather than a false negative: with one
    sample there is nothing to compare, which is why A4.1 decided on three.

    **Skips and broken outcomes are excluded from the comparison.** A harness
    event says our infrastructure produced no measurement, so a case that was
    measured twice and skipped once is not a model inconsistency; it is one
    measurement short, which the skip rules already count.

    Args:
        observations (list[Observation]): Every observation in the run.

    Returns:
        dict[str, set[str]]: Case identifier to the distinct outcomes seen, for
        every case showing more than one. Empty when the run is consistent.
    """
    measured: dict[str, set[str]] = {}
    for entry in observations:
        if entry.outcome in ("skip", "broken"):
            continue
        measured.setdefault(entry.case_id, set()).add(entry.outcome)
    return {case: seen for case, seen in measured.items() if len(seen) > 1}



def mixed_model_engines(observations: list[Observation]) -> dict[str, set[str]]:
    """Return every engine whose observations came from more than one model.

    **Every comparison in this project rests on one premise: the model did not
    change.** `RunMetadata.resolved_models` states it per engine and can only
    hold one value each, so a corpus spanning two versions does not contradict
    the record; it silently picks one. That is the failure this checks for.

    **It became reachable rather than theoretical.** A free-tier quota is keyed
    per model (design section 8.6.4), so switching model is the obvious way to
    keep recording once the day's allowance is spent, and the fixture store is
    keyed by engine rather than by model. Twenty more requests a day is exactly
    the incentive that produces a mixed corpus.

    **A replayed corpus is included, not exempt.** Fixtures carry the model that
    produced them, so a replay of a mixed corpus is mixed, and the point of
    recording the resolved model was to make that visible later.

    Args:
        observations (list[Observation]): Every observation in the run.

    Returns:
        dict[str, set[str]]: Engine to the distinct models it reported, for
        engines reporting more than one. **Empty where every engine is
        coherent.** Observations with no resolved model are ignored rather than
        counted as a version: a skip never reached a model, and treating its
        blank as a second version would report a mixture that did not happen.
    """
    seen: dict[str, set[str]] = {}
    for entry in observations:
        if not entry.engine or not entry.resolved_model:
            continue
        seen.setdefault(entry.engine, set()).add(entry.resolved_model)
    return {engine: models for engine, models in seen.items() if len(models) > 1}


def _range_of(scores: list[float]) -> Optional[float]:
    """Return the range between the highest and lowest score.

    Args:
        scores (list[float]): The scores one case was awarded.

    Returns:
        Optional[float]: The range, or ``None`` for fewer than two scores.
        **None rather than zero**, because zero means the judge agreed with
        itself and one observation cannot establish that.
    """
    if len(scores) < 2:
        return None
    return max(scores) - min(scores)


def score_spread(observations: list[Observation]) -> dict[str, float]:
    """Return the range of judged scores per case, across its observations.

    **Consistency of verdict and consistency of score are different questions**,
    and the first does not answer the second. Three observations scoring 4, 4
    and 5 all clear a threshold of 4, so all three pass and
    :func:`inconsistent_cases` finds nothing. **The spread is real and the
    verdict cannot see it.**

    **Recorded, never gated.** A score that moves inside the passing band is
    information about the judge and the response together, and it is not a
    failure: the case passed on every observation, which is what the threshold
    was set to decide. Turning a spread into a verdict would need a second
    threshold nobody has evidence for (design section 4.9.4).

    **The range is computed here rather than borrowed.** `cmn` imports
    nothing from `evaluation`, and `evaluation.calibration` is where
    `observation_variance` lives, so reaching for it would invert the
    dependency the tiers hold. Section 4.9.3 claimed that function was
    now called; it is not, and the claim is corrected rather than the
    boundary.

    Args:
        observations (list[Observation]): Every observation in the run.

    Returns:
        dict[str, float]: Case identifier to the range between its highest and
        lowest judged score, for every case observed more than once with a
        score. **Absent where a case has one score or none**, because a range
        needs two points and reporting zero would be indistinguishable from
        agreement.
    """
    scored: dict[str, list[float]] = {}
    for entry in observations:
        if entry.outcome in ("skip", "broken") or entry.score is None:
            continue
        scored.setdefault(entry.case_id, []).append(float(entry.score))

    spread: dict[str, float] = {}
    for case, scores in scored.items():
        measured = _range_of(scores)
        if measured is not None:
            spread[case] = measured
    return spread

def inconsistency_rate(observations: list[Observation]) -> float:
    """Return the share of measured cases whose observations disagree.

    Args:
        observations (list[Observation]): Every observation in the run.

    Returns:
        float: Inconsistent cases over cases that were measured at all.
        **Zero when nothing was measured**, so an empty run is not reported as
        perfectly inconsistent, which the ceiling would then fail on.
    """
    measured = {
        entry.case_id
        for entry in observations
        if entry.outcome not in ("skip", "broken")
    }
    if not measured:
        return 0.0
    return len(inconsistent_cases(observations)) / len(measured)

def _evaluate_preconditions(observations: list[Observation]) -> Optional[Verdict]:
    """Return a verdict when the preconditions did not hold.

    **100% pass, zero skips.** A unit test has nothing external to block it, so
    a skip means something is broken rather than unavailable.

    Args:
        observations (list): Every observation.

    Returns:
        Optional[Verdict]: A precondition-failure verdict, or ``None`` when the
        preconditions held and the graded rules should run. Exit code 3, not 1:
        a red verdict is a finding about a measured run, while a precondition
        failure means nothing was measured, and collapsing them would let CI
        treat a broken harness as an underperforming model.
    """
    preconditions = [entry for entry in observations if not entry.graded]
    failures = [
        entry for entry in preconditions
        if not entry.passed or entry.outcome == "skip"
    ]
    if not failures:
        return None

    logger.error(
        "%s %d precondition observations did not pass",
        _PRECONDITION_FAILED, len(failures),
    )
    return Verdict(
        green=False,
        exit_code=3,
        breaches=[
            RuleBreach(
                rule=_PRECONDITION_FAILED,
                reason=(
                    f"{len(failures)} precondition observations did not pass, so the "
                    f"graded layers were not executed and nothing was measured"
                ),
            )
        ],
    )



def _evaluate_soundness(
    observations: list[Observation], thresholds: Thresholds
) -> Optional[Verdict]:
    """Return a verdict when the run itself cannot be trusted.

    **Broken and unfinished are our defects, not the model's**, so neither is
    tolerated as a proportion and neither exits 1. Exit 1 says a suite measured
    something and it failed, which is a finding about a third party; these say
    the measurement is not worth reading.

    Args:
        observations (list): Every observation.

    Returns:
        Optional[Verdict]: A soundness verdict, or ``None`` when the run is
        sound and the graded rules should decide.
    """
    broken = [entry for entry in observations if entry.outcome == "broken"]
    unfinished = [
        entry for entry in observations
        if entry.outcome == "skip" and skip_blocks(entry.skip_reason)
    ]
    # AN INCONSISTENT MODEL CHARACTERISES NOTHING. A single-sample green
    # from a model that answers one question three ways is a draw from a
    # distribution nobody measured, so the run's other numbers would overstate
    # what they established. Exit 3 rather than 1: this is not a bad score, it
    # is a run that cannot be trusted to have measured anything (section 4.9.2).
    disagreeing = inconsistent_cases(observations)
    rate = inconsistency_rate(observations)
    wobbling = bool(disagreeing) and rate >= thresholds.inconsistency_ceiling

    # TWO MODELS IN ONE CORPUS MEASURE NEITHER. Every number in the run
    # attributes a result to a model, and a corpus spanning two versions
    # attributes it to whichever one answered that case. Exit 3 for the same
    # reason as the rest of this function: this is not a bad score, it is a run
    # whose subject is not one thing (section 4.9.6). Like its neighbours
    # here it reports `RUN_UNSOUND` and carries no V number: V1 to V9 are
    # the rules that decide red against green, which is a different job.
    mixed = mixed_model_engines(observations)

    if not broken and not unfinished and not wobbling and not mixed:
        return None

    breaches: list[RuleBreach] = []
    if mixed:
        detail = "; ".join(
            f"{engine} reported {', '.join(sorted(models))}"
            for engine, models in sorted(mixed.items())
        )
        logger.error(
            "%s %d engine(s) reported more than one model", _RUN_UNSOUND, len(mixed),
        )
        breaches.append(
            RuleBreach(
                rule=_RUN_UNSOUND,
                reason=(
                    f"{len(mixed)} engine(s) reported more than one resolved "
                    f"model, so no result in this run attributes to a single "
                    f"model and the comparison every checkpoint rests on does "
                    f"not hold: {detail}"
                ),
            )
        )
    if wobbling:
        names = ", ".join(sorted(disagreeing))
        logger.error(
            "%s %d of the measured cases disagreed with themselves",
            _RUN_UNSOUND, len(disagreeing),
        )
        breaches.append(
            RuleBreach(
                rule=_RUN_UNSOUND,
                reason=(
                    f"{len(disagreeing)} case(s) produced different outcomes "
                    f"on repeat observations, a rate of {rate:.0%} against a "
                    f"ceiling of {thresholds.inconsistency_ceiling:.0%}. The "
                    f"model does not answer consistently, so no single-sample "
                    f"result in this run characterises anything: {names}"
                ),
            )
        )
    if broken:
        names = ", ".join(sorted({entry.case_id for entry in broken}))
        logger.error("%s %d observations broke", _RUN_UNSOUND, len(broken))
        breaches.append(
            RuleBreach(
                rule=_RUN_UNSOUND,
                reason=(
                    f"{len(broken)} observations broke, so our code failed "
                    f"while measuring and the result is not a finding about "
                    f"any model: {names}"
                ),
            )
        )
    if unfinished:
        names = ", ".join(sorted({entry.case_id for entry in unfinished}))
        breaches.append(
            RuleBreach(
                rule=_RUN_UNSOUND,
                reason=(
                    f"{len(unfinished)} observations skipped as unfinished "
                    f"work, which no ceiling tolerates: {names}"
                ),
            )
        )
    return Verdict(green=False, exit_code=3, breaches=breaches)


def _build_population(
    observations: list[Observation], config: VerdictConfig
) -> _Population:
    """Split the observations into the sets each denominator is computed over.

    Args:
        observations (list): Every observation.
        config (VerdictConfig): For the quarantine list.

    Returns:
        _Population: The sets, each excluding what its own rule excludes.
    """
    quarantined = config.quarantined_ids()
    graded = [entry for entry in observations if entry.graded]

    executions = [
        entry for entry in graded
        if entry.case_id not in quarantined
        and outcome_properties(entry.outcome).counts_in_pass_rate
    ]
    skippable = [
        entry for entry in graded
        if entry.outcome != "skip" or skip_counts_toward_rate(entry.skip_reason)
    ]
    skipped = [entry for entry in skippable if entry.outcome == "skip"]
    priority_skippable = [
        entry for entry in skippable if entry.priority in (0, 1)
    ]
    # ONE MODEL OR NONE. A mixed corpus leaves this empty rather than
    # picking one: `mixed_model_engines` reports the run as mixed, and
    # expiring quarantine on an arbitrary pick would attach a second
    # consequence to that one cause. Design section 4.6.2.
    reported = {entry.resolved_model for entry in observations if entry.resolved_model}
    return _Population(
        graded=graded,
        executions=executions,
        skippable=skippable,
        skipped=skipped,
        priority_skippable=priority_skippable,
        priority_skipped=[
            entry for entry in priority_skippable if entry.outcome == "skip"
        ],
        resolved_model=reported.pop() if len(reported) == 1 else "",
    )



def _rate(numerator: list[Observation], denominator: list[Observation]) -> Optional[float]:
    """Return a rate, or ``None`` when the denominator is empty.

    Args:
        numerator (list): The counted observations.
        denominator (list): The population.

    Returns:
        Optional[float]: The rate. **Never a division by zero and never a
        substituted zero**: an empty denominator means the question is
        unanswerable, which is not the same as the answer being fine.
    """
    if not denominator:
        return None
    return len(numerator) / len(denominator)


def _rule_v1(
    population: _Population, config: VerdictConfig, as_of: date
) -> tuple[bool, str]:
    """Any P0 or P1 observation not passing fails the run.

    Args:
        population (_Population): The split observation sets.
        config (VerdictConfig): Unused by this rule.
        as_of (date): Unused by this rule.

    Returns:
        tuple: Whether it fired, and what it found.
    """
    del config, as_of
    failing = [
        entry for entry in population.graded
        if entry.priority in (0, 1) and not entry.passed and entry.outcome != "skip"
    ]
    if not failing:
        return False, ""
    names = ", ".join(sorted({entry.case_id for entry in failing}))
    return True, f"{len(failing)} P0 or P1 observations did not pass: {names}"


def _rule_v2(
    population: _Population, config: VerdictConfig, as_of: date
) -> tuple[bool, str]:
    """The overall pass rate must reach the floor.

    Args:
        population (_Population): The split observation sets.
        config (VerdictConfig): For the threshold.
        as_of (date): Unused by this rule.

    Returns:
        tuple: Whether it fired, and what it found.
    """
    del as_of
    rate = _rate([entry for entry in population.executions if entry.passed],
                 population.executions)
    if rate is None:
        return False, ""
    floor = config.thresholds.pass_floor
    if rate >= floor:
        return False, ""
    return True, f"pass rate {rate:.1%} is below the floor of {floor:.0%}"


def _rule_v3(
    population: _Population, config: VerdictConfig, as_of: date
) -> tuple[bool, str]:
    """The total skip rate must stay within its ceiling.

    Args:
        population (_Population): The split observation sets.
        config (VerdictConfig): For the threshold.
        as_of (date): Unused by this rule.

    Returns:
        tuple: Whether it fired, and what it found.
    """
    del as_of
    rate = _rate(population.skipped, population.skippable)
    if rate is None:
        return False, ""
    ceiling = config.thresholds.skip_ceiling
    if rate <= ceiling:
        return False, ""
    return True, f"skip rate {rate:.1%} is above the ceiling of {ceiling:.0%}"


def _rule_v4(
    population: _Population, config: VerdictConfig, as_of: date
) -> tuple[bool, str]:
    """The P0 and P1 skip rate must stay within its own, tighter ceiling.

    Args:
        population (_Population): The split observation sets.
        config (VerdictConfig): For the threshold.
        as_of (date): Unused by this rule.

    Returns:
        tuple: Whether it fired, and what it found.
    """
    del as_of
    rate = _rate(population.priority_skipped, population.priority_skippable)
    if rate is None:
        return False, ""
    ceiling = config.thresholds.priority_skip_ceiling
    if rate <= ceiling:
        return False, ""
    return True, f"P0 and P1 skip rate {rate:.1%} is above the ceiling of {ceiling:.0%}"


def _rule_v5(
    population: _Population, config: VerdictConfig, as_of: date
) -> tuple[bool, str]:
    """An expired quarantine entry fails the run.

    Expiry is by model change or by the configured window, per design section
    4.6.2. **An unconfirmed entry does not fire this rule**: it is our
    bookkeeping failing rather than a model finding, and is reported as
    ``QC_HARNESS_QUARANTINE_UNCONFIRMED`` instead (section 4.6.4).

    Args:
        population (_Population): For the run's resolved model.
        config (VerdictConfig): For the quarantine list and the window.
        as_of (date): The injected evaluation date.

    Returns:
        tuple: Whether it fired, and what it found. Without this, quarantine
        becomes where failures go to be forgotten.
    """
    window = config.thresholds.quarantine_window_days
    expired = [
        entry for entry in config.quarantine
        if entry.expired(as_of, population.resolved_model, window)
    ]
    if not expired:
        return False, ""
    names = ", ".join(sorted(entry.case_id for entry in expired))
    return True, (
        f"{len(expired)} quarantine entries expired as of {as_of}, by a changed "
        f"model or the {window}-day window: {names}"
    )


def _rule_v6(
    population: _Population, config: VerdictConfig, as_of: date
) -> tuple[bool, str]:
    """A run that measured nothing must never report green.

    Covers every degenerate input at once: no observations at all, no graded
    observations, every graded case quarantined, and every pair unsupported.
    Each leaves a denominator at zero, and each would otherwise pass every
    other rule vacuously.

    Args:
        population (_Population): The split observation sets.
        config (VerdictConfig): Unused by this rule.
        as_of (date): Unused by this rule.

    Returns:
        tuple: Whether it fired, and what it found.
    """
    del config, as_of
    if not population.graded:
        return True, f"{_NOTHING_MEASURED}: the run produced no graded observations"
    if not population.executions:
        return True, (
            f"{_NOTHING_MEASURED}: every graded observation was excluded from the "
            f"pass-rate denominator, so the suite verified nothing"
        )
    if not population.skippable:
        return True, (
            f"{_NOTHING_MEASURED}: every graded observation was excluded from the "
            f"skip denominator"
        )
    return False, ""


_VERDICT_RULES: Final[list[Callable]] = []


def register_verdict_rule(rule_id: str) -> Callable:
    """Register a verdict rule under an identifier.

    **Rules are a registry, not a fixed list.** A new test type needing its own
    gating condition contributes a rule returning ``(fired, reason)``; it does
    not modify the existing ones. A regression in the function deciding every
    run's outcome would misreport every existing test, not only the new one.

    Args:
        rule_id (str): The identifier the breach is reported under.

    Returns:
        Callable: A decorator registering the rule.
    """
    def register(rule: Callable) -> Callable:
        """Attach the identifier and add the rule to the registry.

        Args:
            rule (Callable): The rule function.

        Returns:
            Callable: The same function.
        """
        rule.rule_id = rule_id
        _VERDICT_RULES.append(rule)
        return rule
    return register


def registered_verdict_rules() -> list[Callable]:
    """Return every registered rule, in evaluation order.

    Returns:
        list[Callable]: The rules. **Every one is evaluated**, because the
        result carries all breaches rather than the first.
    """
    return list(_VERDICT_RULES)


def unregister_verdict_rule(rule_id: str) -> None:
    """Remove a registered rule.

    Exists for the extension cases, which register a rule and must leave the
    registry as they found it.

    Args:
        rule_id (str): The identifier to remove.

    Returns:
        None
    """
    for rule in list(_VERDICT_RULES):
        if getattr(rule, "rule_id", None) == rule_id:
            _VERDICT_RULES.remove(rule)


def evaluate_distribution(
    observations: list[Observation], thresholds: Thresholds
) -> DistributionReport:
    """Report the priority distribution over unique case definitions.

    **The denominator is case definitions, not executions.** A4 gives three
    observations per case, and counting executions would leave the share
    unchanged while tripling the numbers, which invites reading a count as a
    population.

    **The security layer is excluded entirely**, read from its declared
    exemption rather than by naming it. Security coverage does not compete with
    functional coverage for a budget.

    Args:
        observations (list): Every observation.
        thresholds (Thresholds): The ceilings and the minimum population.

    Returns:
        DistributionReport: The shares, or counts alone below the minimum.
    """
    counted: dict[str, Observation] = {}
    for entry in observations:
        properties = layer_properties(entry.layer)
        if properties.graded and not properties.distribution_exempt:
            counted.setdefault(entry.case_id, entry)

    definitions = len(counted)
    demoted = len([entry for entry in counted.values() if entry.demoted])

    if definitions < thresholds.distribution_minimum:
        logger.info(
            "Distribution check reports counts without a verdict: %d case definitions "
            "is below the minimum of %d",
            definitions, thresholds.distribution_minimum,
        )
        return DistributionReport(
            case_definitions=definitions, demoted_count=demoted, verdict_returned=False
        )

    at_zero = len([entry for entry in counted.values() if entry.priority == 0])
    at_one = len([entry for entry in counted.values() if entry.priority == 1])
    return DistributionReport(
        case_definitions=definitions,
        demoted_count=demoted,
        verdict_returned=True,
        p0_share=at_zero / definitions,
        p1_share=at_one / definitions,
        combined_share=(at_zero + at_one) / definitions,
    )


def _distribution_breaches(
    report: DistributionReport, thresholds: Thresholds
) -> list[RuleBreach]:
    """Return the ceilings the distribution breached.

    Args:
        report (DistributionReport): What the check found.
        thresholds (Thresholds): The ceilings.

    Returns:
        list[RuleBreach]: One per breached ceiling. **Below the minimum
        population this is always empty**, because the check returned counts
        rather than a verdict.
    """
    if not report.verdict_returned:
        return []

    breaches: list[RuleBreach] = []
    for rule, share, ceiling, label in (
        ("V7", report.p0_share, thresholds.p0_share_ceiling, "P0"),
        ("V8", report.p1_share, thresholds.p1_share_ceiling, "P1"),
        ("V9", report.combined_share, thresholds.combined_share_ceiling, "P0 and P1"),
    ):
        if share is not None and share > ceiling:
            breaches.append(
                RuleBreach(
                    rule=rule,
                    reason=(
                        f"{label} share {share:.1%} of {report.case_definitions} case "
                        f"definitions is above the ceiling of {ceiling:.0%}"
                    ),
                )
            )
    return breaches


register_verdict_rule("V1")(_rule_v1)
register_verdict_rule("V2")(_rule_v2)
register_verdict_rule("V3")(_rule_v3)
register_verdict_rule("V4")(_rule_v4)
register_verdict_rule("V5")(_rule_v5)
register_verdict_rule("V6")(_rule_v6)
