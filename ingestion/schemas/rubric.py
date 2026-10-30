# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The rubric records, which define how an LLM judge scores a response.

Created: 2026-10-18
Last updated: 2026-10-29

This file contains :class:`Rubric`, which holds the criteria, the pass
threshold and the aggregation strategy; :class:`RubricCriterion`, one judged
dimension with its weight and its anchors; and :class:`Anchor`, what one level
of a criterion's scale means, with an optional exemplar. Each is built through
``from_dict``, which enforces the rubric invariants.

**A rule set carries at most one rubric, and the judge is what reads it.** The
criteria and anchors become the judge's instruction text, aggregation turns
the scores into one result against the threshold, and calibration sends the
exemplars back through the judge to check it still scores them at their level.

Design: ``docs/design/tier1_ingestion.md`` sections 3.0 and 3.6 to 3.8.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Final, Optional

from cmn.registries import (
    aggregation_scale,
)
from ingestion.schemas.fields import (
    _normalize_text,
    _reject_unknown_keys,
    _require_present_and_filled,
    _optional_text,
    _coerce_int,
    _coerce_float,
)

logger = logging.getLogger(__name__)

_ANCHOR_REQUIRED_LEVELS: Final[frozenset[int]] = frozenset({1, 3, 5})
_ANCHOR_PERMITTED_LEVELS: Final[frozenset[int]] = frozenset({1, 2, 3, 4, 5})


@dataclass(frozen=True)
class Anchor:
    """What one point on a rubric scale means.

    Attributes:
        description (str): What a response scoring at this level looks like.
        exemplar (Optional[str]): A response that should score here, used by
            calibration to detect judge drift.
    """

    description: str
    exemplar: Optional[str] = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Anchor":
        """Build an anchor from a validated mapping.

        Args:
            payload (dict): Mapping carrying ``description``.

        Returns:
            Anchor: The frozen record.

        Raises:
            KeyError: When a required field is absent or an unknown key is present.
            ValueError: When a required field is present but empty.
        """
        _reject_unknown_keys(payload, cls, "<anchor>")
        _require_present_and_filled(payload, ("description",), cls.__name__, "<anchor>")
        supplied_exemplar = payload.get("exemplar")
        return cls(
            description=_normalize_text(payload["description"]),
            exemplar=None if supplied_exemplar is None else _normalize_text(supplied_exemplar),
        )


@dataclass(frozen=True)
class RubricCriterion:
    """One judged dimension, with the anchors that define its scale.

    Attributes:
        criterion_id (str): Identifies the criterion within the rubric.
        name (str): Short label.
        description (str): What the criterion measures.
        anchors (dict): Level to :class:`Anchor`. Invariant G3 applies.
        weight (float): Relative contribution under weighted aggregation.
        constraint_ref (Optional[str]): The constraint this criterion judges,
            checked by referential integrity rule R2.
    """

    criterion_id: str
    name: str
    description: str
    anchors: dict[int, Anchor]
    weight: float = 1.0
    constraint_ref: Optional[str] = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RubricCriterion":
        """Build a criterion from a validated mapping, enforcing invariant G3.

        G3 requires anchors at levels 1, 3 and 5; levels 2 and 4 are permitted.
        Requiring all five is authoring burden without proportional benefit, and
        a judge discriminates better against few sharply distinguished anchors
        than five similar ones.

        Args:
            payload (dict): Mapping carrying ``criterion_id``, ``name``,
                ``description`` and ``anchors``.

        Returns:
            RubricCriterion: The frozen record.

        Raises:
            KeyError: When a required field is absent or an unknown key is present.
            ValueError: When a required field is empty, an anchor level falls
                outside 1 to 5, a required level is absent, or the weight is not
                numeric.
        """
        owner = str(payload.get("criterion_id", "<unidentified>"))
        _reject_unknown_keys(payload, cls, owner)
        _require_present_and_filled(
            payload, ("criterion_id", "name", "description", "anchors"), cls.__name__, owner
        )
        anchors = cls._build_anchors(payload["anchors"], owner)
        return cls(
            criterion_id=_normalize_text(payload["criterion_id"]),
            name=_normalize_text(payload["name"]),
            description=_normalize_text(payload["description"]),
            anchors=anchors,
            weight=_coerce_float(payload.get("weight", 1.0), "weight", owner),
            constraint_ref=_optional_text(payload.get("constraint_ref")),
        )

    @staticmethod
    def _build_anchors(supplied: Any, owner: str) -> dict[int, Anchor]:
        """Validate and build the anchor mapping for one criterion.

        Args:
            supplied (Any): The authored anchors, expected as a mapping of level
                to anchor payload.
            owner (str): Criterion identifier, for the message.

        Returns:
            dict[int, Anchor]: Anchors keyed by integer level.

        Raises:
            ValueError: When the anchors are not a mapping, a level is not an
                integer in 1 to 5, or levels 1, 3 and 5 are not all present.
        """
        if not isinstance(supplied, dict):
            raise ValueError(
                f"QC_DATA_MALFORMED_SOURCE: RubricCriterion {owner} anchors must be a mapping, "
                f"received {type(supplied).__name__}"
            )
        anchors: dict[int, Anchor] = {}
        for raw_level, anchor_payload in supplied.items():
            level = _coerce_int(raw_level, "anchor level", owner)
            if level not in _ANCHOR_PERMITTED_LEVELS:
                raise ValueError(
                    f"QC_DATA_INVARIANT_VIOLATION: RubricCriterion {owner} anchor level {level} "
                    f"falls outside 1 to 5"
                )
            anchors[level] = Anchor.from_dict(dict(anchor_payload))

        absent = sorted(_ANCHOR_REQUIRED_LEVELS - set(anchors))
        if absent:
            raise ValueError(
                f"QC_DATA_REQUIRED_FIELD_MISSING: RubricCriterion {owner} is missing required "
                f"anchor levels {absent}; 1, 3 and 5 are mandatory"
            )
        return anchors


@dataclass(frozen=True)
class Rubric:
    """The judged half of a rule set.

    Attributes:
        criteria (list): The judged dimensions. Invariant G2 requires at least one.
        threshold (float): The score at or above which the rubric passes.
        aggregation (str): Registered strategy name.
        aggregation_params (dict): Parameters for that strategy.
        planted_score (Optional[int]): The score a case's payload asks the judge
            for, on no anchored level and below ``threshold``; a judgement
            returning it fails the observation (``tier3_evaluation.md`` section
            4C.5). Invariants G9 and G11.
    """

    criteria: list[RubricCriterion]
    threshold: float
    aggregation: str = "weighted_mean"
    aggregation_params: dict[str, Any] = field(default_factory=dict)
    planted_score: Optional[int] = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Rubric":
        """Build a rubric from a validated mapping, enforcing invariant G2.

        Args:
            payload (dict): Mapping carrying ``criteria`` and ``threshold``.

        Returns:
            Rubric: The frozen record.

        Raises:
            KeyError: When a required field is absent or an unknown key is present.
            ValueError: When criteria is empty, or the threshold is not numeric.
        """
        _reject_unknown_keys(payload, cls, "<rubric>")
        _require_present_and_filled(payload, ("criteria", "threshold"), cls.__name__, "<rubric>")
        aggregation = _normalize_text(payload.get("aggregation", "weighted_mean"))
        if aggregation_scale(aggregation) is None:
            raise ValueError(
                f"QC_DATA_INVARIANT_VIOLATION: Rubric names unregistered aggregation strategy "
                f"{aggregation!r}; a score with no declared scale cannot be compared"
            )
        criteria = [
            RubricCriterion.from_dict(dict(entry)) for entry in payload["criteria"]
        ]
        threshold = _coerce_float(payload["threshold"], "threshold", "<rubric>")
        return cls(
            criteria=criteria,
            threshold=threshold,
            aggregation=aggregation,
            aggregation_params=dict(payload.get("aggregation_params", {})),
            planted_score=cls._validate_planted(
                payload.get("planted_score"), criteria, threshold
            ),
        )

    @staticmethod
    def _validate_planted(
        supplied: Any, criteria: list[RubricCriterion], threshold: float
    ) -> Optional[int]:
        """Validate a planted score against the scale, the anchors and the threshold.

        Invariants G9 and G11. Design: ``tier1_ingestion.md`` section 3.6.

        Args:
            supplied (Any): The authored value, or None.
            criteria (list): The built criteria, whose anchors it must avoid.
            threshold (float): The rubric's passing score, which it must fall below.

        Returns:
            Optional[int]: The planted score, None where none is declared.

        Raises:
            ValueError: When it falls outside 1 to 5, a criterion anchors it, or
                it reaches the threshold. A level the rubric anchors is one the
                judge returns for honest reasons, and a level the rubric would
                pass leaves the fingerprint as the only thing failing a steered
                judgement, so a fingerprint that misfires becomes a finding.
        """
        if supplied is None:
            return None
        planted = _coerce_int(supplied, "planted_score", "<rubric>")
        if planted not in _ANCHOR_PERMITTED_LEVELS:
            raise ValueError(
                f"QC_DATA_INVARIANT_VIOLATION: Rubric planted_score {planted} falls "
                f"outside 1 to 5"
            )
        anchoring = sorted(
            entry.criterion_id for entry in criteria if planted in entry.anchors
        )
        if anchoring:
            raise ValueError(
                f"QC_DATA_INVARIANT_VIOLATION: Rubric planted_score {planted} is an "
                f"anchored level of {anchoring}, so a judgement returning it proves nothing"
            )
        if planted >= threshold:
            raise ValueError(
                f"QC_DATA_INVARIANT_VIOLATION: Rubric planted_score {planted} reaches "
                f"the threshold {threshold}, so the rubric would pass a judgement the "
                f"payload asked for and only the fingerprint would fail it"
            )
        return planted
