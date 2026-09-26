# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""The fixture store, and the hash that keeps replay honest.

Specified by ``docs/design/tier2_execution.md`` section 7.

**Locating by identity keeps fixtures findable; verifying by hash keeps them
honest.** Without the hash, changing prompt composition would silently replay a
recorded answer to a **different question**, which is the same class of
corruption as an unmarked replay (A6) and considerably harder to notice.

**Every observation is stored and every observation is replayed.** A4 gives
three observations per case, and a live recording captures three genuinely
different responses. Replaying one of them three times would show zero variance
and falsely imply the model is deterministic, destroying the same-commit
reliability signal repeat observation exists to produce.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

logger = logging.getLogger(__name__)

_ENCODING: Final[str] = "utf-8"

# The hash covers the composed request and nothing else. Including the response
# would make every fixture stale the moment a model answered differently, which
# is the event replay exists to preserve rather than to detect.
_HASH_ALGORITHM: Final[str] = "sha256"

# Mirrors ingestion.cases. Declared rather than imported, because Tier 2
# importing a Tier 1 module to learn how an identifier is punctuated would
# couple dispatch to ingestion for a two-character fact.
_CASE_ID_SEPARATOR: Final[str] = "::"


@dataclass(frozen=True)
class FixtureKey:
    """What locates one stored observation.

    Attributes:
        case_id (str): Which case.
        engine (str): Which provider produced it.
        observation_index (int): Which of the three observations, zero based.
    """

    case_id: str
    engine: str
    observation_index: int

    @property
    def task_id(self) -> str:
        """Return the task half of the case identifier.

        Returns:
            str: Everything before the separator.
        """
        return self.case_id.split(_CASE_ID_SEPARATOR, maxsplit=1)[0]

    @property
    def rule_id(self) -> str:
        """Return the rule-set half of the case identifier.

        Returns:
            str: Everything after the separator, or the whole identifier when
            it carries none, so a malformed key still produces a usable path
            rather than an index error.
        """
        parts = self.case_id.split(_CASE_ID_SEPARATOR, maxsplit=1)
        return parts[1] if len(parts) == 2 else parts[0]

    def as_path(self, root: Path) -> Path:
        """Return the file this observation is stored at.

        **The key is the tuple; the path splits it** (design section 7.2.1). A
        `case_id` cannot be a path segment: it carries a colon, which Windows
        treats as the drive separator and refuses outright. The two halves are
        already validated identifiers, so splitting needs no encoding and keeps
        a fixture findable by reading the path.

        Args:
            root (Path): The fixture root directory.

        Returns:
            Path: The fixture file path.
        """
        return (
            root / self.engine / self.task_id / self.rule_id
            / f"{self.observation_index}.json"
        )


@dataclass(frozen=True)
class StoredFixture:
    """One recorded observation, with the identity it was recorded under.

    Attributes:
        request_hash (str): Hash of the request that produced the response.
        response (dict): The recorded response, already normalized.
        resolved_model (str): The model identity the recording came from, so
            replaying against a later version is visible in the record rather
            than assumed away.
    """

    request_hash: str
    response: dict[str, Any]
    resolved_model: str


class FixtureStale(Exception):
    """A fixture exists and was recorded under a different request."""


class FixtureMissing(Exception):
    """No fixture exists for this case, engine and observation index."""


def hash_request(request: Any) -> str:
    """Return the stable hash of a composed request.

    Serialized with sorted keys and no whitespace variance, so two structurally
    identical requests hash identically regardless of how they were built.

    **Line endings are normalized before hashing.** Without it, the same commit
    checked out on Windows and on Linux produces different hashes for the same
    fixture, and every replay reports stale on whichever platform did not record
    it (A18). `.gitattributes` also pins this; both exist because either alone
    is a single point of failure.

    **No serializer fallback is configured.** A fallback would stringify a
    provider object into its repr, which carries a memory address and therefore
    changes every run: the hash would never match, every replay would report
    stale, and nothing would say why. Raising is the louder failure and the
    correct one.

    Args:
        request (Any): The composed request, as a JSON-serializable structure.

    Returns:
        str: The hexadecimal digest.

    Raises:
        ValueError: With ``QC_HARNESS_PARSER_ERROR`` when the request cannot be
            serialized, which means it carries a provider object that should
            have stopped at the adapter.
    """
    try:
        serialized = json.dumps(
            _normalize_newlines(request), sort_keys=True, separators=(",", ":")
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            "QC_HARNESS_PARSER_ERROR: request is not serializable, which means a provider "
            "object reached the hash; it should have stopped at the adapter"
        ) from error
    digest = hashlib.new(_HASH_ALGORITHM)
    digest.update(serialized.encode(_ENCODING))
    return digest.hexdigest()


def _normalize_newlines(value: Any) -> Any:
    """Return the value with every string's line endings normalized to LF.

    **Normalization happens before serialization, not after.** ``json.dumps``
    escapes a carriage return into a two-character sequence, so a replacement
    applied to the serialized text finds no control character and silently does
    nothing. The same commit then hashes differently on Windows and on Linux,
    which is the defect this exists to prevent.

    Args:
        value (Any): Any part of the request structure.

    Returns:
        Any: The same structure with strings normalized. Mappings and sequences
        are walked, because a prompt is as likely to sit in a nested field as at
        the top level.
    """
    if isinstance(value, str):
        return value.replace("\r\n", "\n").replace("\r", "\n")
    if isinstance(value, dict):
        return {key: _normalize_newlines(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_newlines(item) for item in value]
    return value


def load_fixture(root: Path, key: FixtureKey, request_hash: str) -> StoredFixture:
    """Load one observation, refusing a stale or absent one.

    Args:
        root (Path): The fixture root directory.
        key (FixtureKey): What to load.
        request_hash (str): Hash of the request about to be replayed.

    Returns:
        StoredFixture: The recorded observation.

    Raises:
        FixtureMissing: With ``QC_HARNESS_FIXTURE_MISSING``, naming the case.
        FixtureStale: With ``QC_HARNESS_FIXTURE_STALE``, naming the case. The
            run skips rather than failing, because a stale fixture is our defect
            and not a finding about a model.
    """
    path = key.as_path(root)
    if not path.is_file():
        logger.warning(
            "QC_HARNESS_FIXTURE_MISSING %s engine %s observation %d",
            key.case_id, key.engine, key.observation_index,
        )
        raise FixtureMissing(
            f"QC_HARNESS_FIXTURE_MISSING: no fixture for {key.case_id} on {key.engine} "
            f"observation {key.observation_index}"
        )

    stored = _read_fixture(path, key)
    if stored.request_hash != request_hash:
        logger.warning(
            "QC_HARNESS_FIXTURE_STALE %s engine %s observation %d",
            key.case_id, key.engine, key.observation_index,
        )
        raise FixtureStale(
            f"QC_HARNESS_FIXTURE_STALE: {key.case_id} on {key.engine} observation "
            f"{key.observation_index} was recorded under a different request"
        )
    return stored


def record_fixture(
    root: Path, key: FixtureKey, request_hash: str, response: dict[str, Any],
    resolved_model: str,
) -> Path:
    """Write one observation, with the identity it was recorded under.

    Recording happens only in live mode. A recorded fixture carries the model
    identity it came from, so replaying it against a later model version is
    visible in the record rather than assumed away.

    Args:
        root (Path): The fixture root directory.
        key (FixtureKey): What is being recorded.
        request_hash (str): Hash of the request that produced the response.
        response (dict): The normalized response.
        resolved_model (str): The model the provider reported serving.

    Returns:
        Path: Where the fixture was written.
    """
    path = key.as_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "request_hash": request_hash,
        "resolved_model": resolved_model,
        "response": response,
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding=_ENCODING, newline="\n"
    )
    logger.info("Recorded %s observation %d", key.case_id, key.observation_index)
    return path


def stored_observation_count(root: Path, case_id: str, engine: str) -> int:
    """Count the observations stored for one case on one engine.

    Args:
        root (Path): The fixture root directory.
        case_id (str): The case.
        engine (str): The engine.

    Returns:
        int: How many observations exist. A count below the configured
        observation count means replay cannot reproduce the recorded run, which
        is the condition `MQC_EXE_UNI_10222` covers.
    """
    key = FixtureKey(case_id=case_id, engine=engine, observation_index=0)
    directory = key.as_path(root).parent
    if not directory.is_dir():
        return 0
    return len([entry for entry in directory.glob("*.json") if entry.is_file()])


def _read_fixture(path: Path, key: FixtureKey) -> StoredFixture:
    """Parse one fixture file.

    Args:
        path (Path): The fixture file.
        key (FixtureKey): What it should hold, for the message.

    Returns:
        StoredFixture: The parsed record.

    Raises:
        FixtureMissing: When the file exists and cannot be read as a fixture.
            Treated as missing rather than stale, because a fixture that cannot
            be parsed carries no hash to compare and a stale report would claim
            more than is known.
    """
    try:
        payload = json.loads(path.read_text(encoding=_ENCODING))
        return StoredFixture(
            request_hash=str(payload["request_hash"]),
            response=dict(payload["response"]),
            resolved_model=str(payload["resolved_model"]),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        logger.warning("QC_HARNESS_FIXTURE_MISSING %s is unreadable", path)
        raise FixtureMissing(
            f"QC_HARNESS_FIXTURE_MISSING: {key.case_id} on {key.engine} observation "
            f"{key.observation_index} exists and cannot be read as a fixture"
        ) from error


@dataclass(frozen=True)
class JudgementKey:
    """What locates one stored judgement.

    **Keyed by the judge engine, not the candidate engine.** A judgement is a
    measurement made by an instrument, and which instrument made it is part of
    its identity. Two judges scoring the same observation produce two
    judgements, not one that overwrites the other.

    Attributes:
        case_id (str): The case the judged observation belongs to.
        judge_engine (str): Which engine graded it.
        observation_index (int): Which of the observations, zero based.
    """

    case_id: str
    judge_engine: str
    observation_index: int

    def path(self, root: Path) -> Path:
        """Return where this judgement is stored.

        Args:
            root (Path): The fixture root directory.

        Returns:
            Path: The judgement file path, under a ``judgements`` subtree so it
            never collides with a candidate fixture for an engine of the same
            name.
        """
        task_id, _, rule_id = self.case_id.partition("::")
        return (
            root / "judgements" / self.judge_engine / task_id / (rule_id or "_")
            / f"{self.observation_index}.json"
        )


@dataclass(frozen=True)
class StoredJudgement:
    """One recorded judgement, with the identity it was recorded under.

    Attributes:
        request_hash (str): Hash of the judge request that produced it. Covers
            the case, the rubric and the candidate material, because all three
            are in the composed request.
        judge_model (str): The resolved model that produced it. **Stored
            separately because it is not part of the request**, so a hash
            comparison alone cannot see a provider updating the judge.
        reply (Any): The judge reply, as recorded.
    """

    request_hash: str
    judge_model: str
    reply: Any


def load_judgement(
    root: Path, key: JudgementKey, request_hash: str, judge_model: str
) -> StoredJudgement:
    """Return a recorded judgement, or refuse to replay a stale one.

    Args:
        root (Path): The fixture root.
        key (JudgementKey): What to load.
        request_hash (str): Hash of the judge request about to be replayed.
        judge_model (str): The model that would judge now.

    Returns:
        StoredJudgement: The recorded judgement.

    Raises:
        FixtureMissing: With ``QC_HARNESS_FIXTURE_MISSING`` when none exists.
            **It raises rather than returning anything a caller could mistake
            for a score**, so the fail-open path does not exist to be taken by
            accident. A replay run records a skip; it never calls a judge live.
        FixtureStale: With ``QC_HARNESS_FIXTURE_STALE`` when the request hash or
            the judge model has moved. **Reported separately**, because a hash
            mismatch means the question changed and a model mismatch means the
            question is the same and the instrument is not, and the operator
            response differs.
    """
    path = key.path(root)
    if not path.is_file():
        raise FixtureMissing(
            f"QC_HARNESS_FIXTURE_MISSING: no judgement for {key.case_id} "
            f"observation {key.observation_index} judged by {key.judge_engine}"
        )

    payload = json.loads(path.read_text(encoding=_ENCODING))
    stored = StoredJudgement(
        request_hash=str(payload["request_hash"]),
        judge_model=str(payload["judge_model"]),
        reply=payload["reply"],
    )

    if stored.request_hash != request_hash:
        raise FixtureStale(
            f"QC_HARNESS_FIXTURE_STALE: the judge request for {key.case_id} no "
            f"longer matches the one this judgement was recorded against, so "
            f"replaying it would answer a different question"
        )
    if stored.judge_model != judge_model:
        raise FixtureStale(
            f"QC_HARNESS_FIXTURE_STALE: {key.case_id} was judged by "
            f"{stored.judge_model} and would now be judged by {judge_model}. "
            f"The question is unchanged and the instrument is not"
        )
    return stored


def record_judgement(
    root: Path, key: JudgementKey, request_hash: str, judge_model: str, reply: Any
) -> Path:
    """Store a judgement for later replay.

    Args:
        root (Path): The fixture root.
        key (JudgementKey): What is being stored.
        request_hash (str): Hash of the judge request that produced it.
        judge_model (str): The resolved model that produced it.
        reply (Any): The judge reply.

    Returns:
        Path: Where it was written.
    """
    path = key.path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "request_hash": request_hash,
                "judge_model": judge_model,
                "reply": reply,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding=_ENCODING,
        newline="\n",
    )
    logger.info("Recorded judgement for %s at %s", key.case_id, path)
    return path
