# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The failure-cause tree a report groups by, which is the taxonomy's four families.

Created: 2026-10-28
Last updated: 2026-10-28

This file contains ``report_categories``, the classification a report's
Categories tab is built from; ``write_categories``, which puts it beside a
run's raw results where the report generator looks for it; and
``category_problems``, which reports a registered code no category matches, a
code two of them match, a separately named code the registry does not hold, and
a pattern that will not compile.

Both repositories' runs write the same file, because the taxonomy is one
registry and a report of either repository's results groups failures the same
way. The write happens at configuration, before any case runs, so a run that
crashes still leaves a classifiable result set behind.

**A category matches a message, never a label.** Allure offers a set of
statuses and one regular expression over the result's message, and it cannot
read the ``taxonomy_code`` label this project attaches, so the assertion
message is what the patterns read. Every pattern spans the message from end to
end, Allure applying a whole-string match rather than a search, and every one
sets the flag making a dot match a newline.

**The family prefixes come from ``cmn.registries``** rather than being restated
here, since ``framework-rules.md`` section 4.1 admits one registry of codes.
The three harness codes carrying a category of their own are a selection out of
that registry, and :func:`category_problems` re-resolves each one.

Design: ``docs/design/harness_test_taxonomy.md`` section 16.9.
"""

import json
import re
from pathlib import Path
from typing import Any, Final

from cmn.registries import family_prefixes, registered_codes

# WHERE A REPORT GENERATOR LOOKS FOR THE CLASSIFICATION, which is the results
# directory itself rather than a path given on the command line.
CATEGORIES_FILE: Final[str] = "categories.json"

# THE STATUSES ALLURE CLASSIFIES. A passed result never reaches this tab, so
# every set below is a subset of these three.
_FAILED: Final[tuple[str, ...]] = ("failed",)
_FAILED_OR_BROKEN: Final[tuple[str, ...]] = ("failed", "broken")
_NOT_PASSED: Final[tuple[str, ...]] = ("failed", "broken", "skipped")

# ONE CATEGORY PER FAMILY, named by what the family asserts about rather than
# by its prefix: the division a reader needs first is whether a red is a model
# finding or an instrument defect, because the remedies differ (section 16.9.2).
_FAMILY_CATEGORIES: Final[tuple[tuple[str, str, tuple[str, ...]], ...]] = (
    ("Model quality finding", "QC_LLM_", _FAILED),
    ("Model security finding", "QC_SEC_", _FAILED),
    ("Corpus or configuration diagnostic", "QC_DATA_", _FAILED_OR_BROKEN),
)

# THE HARNESS CODES CARRYING A CATEGORY OF THEIR OWN, because each takes a
# different remedy: another case's failure, a sweep that did not finish, and a
# decision already taken. This is `code-style.md` section 7.1's rule that a
# skip names its kind, applied to a report.
_NAMED_HARNESS_CODES: Final[tuple[tuple[str, str], ...]] = (
    ("Skipped behind a foundation that did not hold", "QC_HARNESS_DEPENDENCY_UNMET"),
    ("Skipped for a missing recording", "QC_HARNESS_FIXTURE_MISSING"),
    ("Skipped as a known failure in quarantine", "QC_HARNESS_QUARANTINED"),
)

_HARNESS_PREFIX: Final[str] = "QC_HARNESS_"
_INSTRUMENT_CATEGORY: Final[str] = "Instrument defect"
_UNCLASSIFIED_CATEGORY: Final[str] = "Carrying no registered code"


def _spanning(body: str) -> str:
    """Return a pattern matching any message containing the given body.

    Allure applies a whole-string match, so a pattern that only has to occur
    somewhere is written with both ends consumed, and the dot is made to match
    a newline because an assertion message here runs to several lines.

    Args:
        body (str): The part that has to occur.

    Returns:
        str: The spanning pattern.
    """
    return f"(?s).*{body}.*"


def _instrument_pattern() -> str:
    """Return the pattern matching every harness code not named on its own.

    **A negative lookahead rather than a second list.** The three named codes
    are excluded here by the same spellings that name them above, so a code
    cannot fall into two categories and have one failure counted under two
    headings (section 16.9.3).

    Returns:
        str: The spanning pattern.
    """
    excluded = "|".join(
        code.removeprefix(_HARNESS_PREFIX) for _, code in _NAMED_HARNESS_CODES
    )
    return _spanning(f"{_HARNESS_PREFIX}(?!(?:{excluded}))")


def _unclassified_pattern() -> str:
    """Return the pattern matching a message naming no registered family.

    **This is the category that earns its place.** A non-passing result whose
    message names no code was classified by nothing, and without a heading of
    its own it would be absent from the tab rather than conspicuous in it.

    Returns:
        str: The pattern, which asserts the absence before consuming the
        message.
    """
    families = "|".join(
        prefix.removeprefix("QC_").removesuffix("_") for prefix in family_prefixes()
    )
    return f"(?s)(?!.*QC_(?:{families})_).*"


def report_categories() -> list[dict[str, Any]]:
    """Return the classification a report's Categories tab is built from.

    Eight categories, in the order a reader works down them: the three model
    and corpus families, the instrument defects, the three named skips, and
    whatever carried no registered code at all.

    Design: ``harness_test_taxonomy.md`` section 16.9.2.

    Returns:
        list[dict]: One Allure category per entry, each naming its matched
        statuses and its message pattern.
    """
    categories: list[dict[str, Any]] = [
        {
            "name": name,
            "matchedStatuses": list(statuses),
            "messageRegex": _spanning(prefix),
        }
        for name, prefix, statuses in _FAMILY_CATEGORIES
    ]
    categories.append({
        "name": _INSTRUMENT_CATEGORY,
        "matchedStatuses": list(_NOT_PASSED),
        "messageRegex": _instrument_pattern(),
    })
    categories.extend(
        {
            "name": name,
            "matchedStatuses": ["skipped"],
            "messageRegex": _spanning(code),
        }
        for name, code in _NAMED_HARNESS_CODES
    )
    categories.append({
        "name": _UNCLASSIFIED_CATEGORY,
        "matchedStatuses": list(_NOT_PASSED),
        "messageRegex": _unclassified_pattern(),
    })
    return categories


def write_categories(results_dir: Path) -> Path:
    """Write the classification into a run's raw results directory.

    Called at configuration rather than at the end of a run, so a run that
    crashes still leaves a classifiable result set behind.

    Args:
        results_dir (Path): The directory the raw results are written to,
            which is created when it does not yet exist.

    Returns:
        Path: The file written.
    """
    results_dir.mkdir(parents=True, exist_ok=True)
    target = results_dir / CATEGORIES_FILE
    target.write_text(
        json.dumps(report_categories(), indent=2), encoding="utf-8"
    )
    return target


def _matching_names(message: str) -> list[str]:
    """Return the name of every category whose pattern matches a message.

    **Python's engine against patterns Allure runs on Java's.** The constructs
    used are the ones both engines spell identically: the dot-all flag, a
    non-capturing group and a negative lookahead. Anything outside that subset
    would need a check that generated a report, which is why nothing richer is
    written.

    Args:
        message (str): The message to classify.

    Returns:
        list[str]: The matching category names, in declaration order.
    """
    matched: list[str] = []
    for category in report_categories():
        if re.fullmatch(str(category["messageRegex"]), message, re.DOTALL):
            matched.append(str(category["name"]))
    return matched


def category_problems() -> list[str]:
    """Report every disagreement between the categories and the code registry.

    Four kinds, in a stable order: a pattern that will not compile, a
    separately named code the registry does not hold, a registered code no
    category matches, and a registered code two of them match.

    **Exactly one, rather than at least one.** A code matching two categories
    files one failure under two headings and the totals stop adding up, which
    is what the lookahead in the instrument pattern exists to prevent.

    Design: ``harness_test_taxonomy.md`` section 16.9.3.

    Returns:
        list[str]: One sentence per disagreement, empty where there is none.
    """
    problems: list[str] = []
    for category in report_categories():
        try:
            re.compile(str(category["messageRegex"]))
        except re.error as error:
            problems.append(
                f"the category {category['name']!r} carries a pattern that will "
                f"not compile, {error}, so every result it should classify "
                f"reaches no heading"
            )
    if problems:
        return problems

    registered = registered_codes()
    for name, code in _NAMED_HARNESS_CODES:
        if code not in registered:
            problems.append(
                f"the category {name!r} names {code}, which the code registry "
                f"does not hold, so it classifies nothing "
                f"(framework-rules.md section 4.1)"
            )

    for code in sorted(registered):
        matched = _matching_names(f"AssertionError: {code}: what the case found")
        if not matched:
            problems.append(
                f"{code} is registered and no category matches it, so a failure "
                f"carrying it reaches no heading in the report"
            )
        elif len(matched) > 1:
            problems.append(
                f"{code} is matched by {len(matched)} categories, {matched}, so "
                f"one failure is filed under each and the totals stop adding up"
            )

    return problems
