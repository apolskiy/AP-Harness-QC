# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The post-execution screen, and what a hit means here.

Specified by ``docs/design/tier3_evaluation.md`` section 3.2.

**Tier 3 owns this screen** (A5c), on the principle that the component the
untrusted content threatens owns its own defence. Tier 2 normalizes and hands
over; it does not screen.

**Screening is a measurement. Isolation is the control.** This module detects;
:mod:`evaluation.isolation` defends. The distinction matters because isolation
is unconditional and does not depend on the screen finding anything.

**The vectors are not ours.** They come from :mod:`cmn.vectors`, shared with the
ingest screen, so `MQC_EVL_UNI_114608` asserts agreement between two screens
looking for identical things rather than comparing two pattern sets that drift.

**Never a model call.** A model asked to detect injection is itself injectable,
which relocates the problem rather than solving it.
"""

import logging
from dataclasses import dataclass
from typing import Final, Optional

from cmn.vectors import match_vectors

logger = logging.getLogger(__name__)

_INJECTION_CODE: Final[str] = "QC_SEC_INJECTION_ATTEMPT"


@dataclass(frozen=True)
class ResponseFinding:
    """One injection-shaped match in one evaluated field.

    The same four facts the ingest finding carries, about a different subject.
    A caller can only act on what a finding tells it, which is why the shape is
    fixed rather than left to each screen (`tier1_ingestion.md` section 7.1).

    Attributes:
        case_id (str): Which case carried it.
        field_name (str): Which field, so a reader can locate it.
        vector (str): The registered vector name that matched.
        excerpt (str): A bounded excerpt around the match, for the record.
        start (int): Where the match began, so a caller can redact the span.
        end (int): Where the match ended.
    """

    case_id: str
    field_name: str
    vector: str
    excerpt: str
    start: int
    end: int


@dataclass(frozen=True)
class ScreenDecision:
    """What the screen found, and what the pipeline should do about it.

    **The decision is separate from the detection** because the same findings
    mean different things: on an ordinary case a hit aborts, and on a declared
    adversarial case it is evidence feeding the grade.

    Attributes:
        case_id (str): Which case.
        findings (list): Every match, empty when the text is clean.
        aborts (bool): Whether the evaluation stops here.
        taxonomy_code (Optional[str]): The code to record, present only when a
            hit was found.
    """

    case_id: str
    findings: list[ResponseFinding]
    aborts: bool
    taxonomy_code: Optional[str] = None

    @property
    def matched(self) -> bool:
        """Report whether anything matched.

        Returns:
            bool: True when at least one vector fired.
        """
        return bool(self.findings)

    @property
    def vectors(self) -> list[str]:
        """Return the distinct vectors that matched.

        Returns:
            list[str]: Vector names, sorted, so the record is reproducible.
        """
        return sorted({finding.vector for finding in self.findings})


def screen_text(case_id: str, field_name: str, text: str) -> list[ResponseFinding]:
    """Apply every registered vector to one piece of evaluated text.

    Args:
        case_id (str): Which case the text belongs to.
        field_name (str): Which field it came from.
        text (str): The text to screen.

    Returns:
        list[ResponseFinding]: One finding per vector that fired.
    """
    return [
        ResponseFinding(
            case_id=case_id,
            field_name=field_name,
            vector=match.vector,
            excerpt=match.excerpt,
            start=match.start,
            end=match.end,
        )
        for match in match_vectors(text)
    ]


def screen_response(
    case_id: str, text: str, *, declared_adversarial: bool = False
) -> ScreenDecision:
    """Screen candidate output and decide what a hit means.

    Args:
        case_id (str): Which case produced the output.
        text (str): The candidate output.
        declared_adversarial (bool): Whether the case declares that it carries
            a payload on purpose.

    Returns:
        ScreenDecision: **An ordinary case aborts on a hit**, because there is
        nothing to score and forwarding the content is the risk the screen
        exists to prevent. **A declared adversarial case continues to the
        assertions**, because a case built to carry a payload would otherwise
        discard the very measurement it exists to produce.
    """
    findings = screen_text(case_id, "candidate_output", text)
    if not findings:
        return ScreenDecision(case_id=case_id, findings=[], aborts=False)

    vectors = sorted({finding.vector for finding in findings})
    if declared_adversarial:
        logger.info(
            "%s matched %s on a declared adversarial case; continuing to assertions",
            case_id, ", ".join(vectors),
        )
        return ScreenDecision(
            case_id=case_id, findings=findings, aborts=False,
            taxonomy_code=_INJECTION_CODE,
        )

    logger.warning("%s %s matched %s", _INJECTION_CODE, case_id, ", ".join(vectors))
    return ScreenDecision(
        case_id=case_id, findings=findings, aborts=True, taxonomy_code=_INJECTION_CODE,
    )
