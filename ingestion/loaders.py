# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""YAML and CSV loaders for task data and golden rule sets.

Specified by ``docs/design/tier1_ingestion.md`` section 4. Two formats carry
different things for different reasons:

* **YAML** carries :class:`~ingestion.schemas.GoldenRuleSet` entirely, and the
  nested fields of :class:`~ingestion.schemas.TaskDataSet`. Rubric anchors need
  prose, prompts are multi-line, and comments matter.
* **CSV** carries flat task rows, for bulk authoring and pattern scanning.

**CSV cannot express null**, which is the constraint the whole format boundary
follows from. YAML distinguishes a value, an empty string, an explicit null and
an absent field; CSV distinguishes text from blank. A blank cell therefore
equals an absent field and takes the declared default, and any field where empty
and null genuinely differ is YAML-only.

Both loaders must produce identical objects from equivalent input, because that
is the abstraction they exist to provide. :func:`assert_loaders_agree` makes the
claim checkable rather than assumed.
"""

import csv
import io
import logging
from dataclasses import MISSING, fields as dataclass_fields
from pathlib import Path
from typing import Any, Final, Iterable, Optional

import yaml

from ingestion.schemas import GoldenRuleSet, TaskDataSet, canonical_identifier

logger = logging.getLogger(__name__)

# utf-8-sig tolerates a byte order mark, which otherwise becomes part of the
# first column name invisibly and turns a correct header into an unknown one.
# Stated explicitly on every read: on Windows the default is cp1252, so an
# unqualified open silently mojibakes any non-ASCII rubric anchor (A18).
_ENCODING: Final[str] = "utf-8-sig"

# CSV expresses a list in one cell. Semicolon rather than comma, because comma
# is the delimiter and quoting a list in every row is an authoring trap.
_LIST_DELIMITER: Final[str] = ";"

_LIST_COLUMNS: Final[frozenset[str]] = frozenset({"rubric_ids", "tags"})
_BOOLEAN_COLUMNS: Final[frozenset[str]] = frozenset({"contains_adversarial_content"})
_TRUE_TOKENS: Final[frozenset[str]] = frozenset({"true", "yes", "1"})

# Fields whose values are nested structures. CSV has no honest flat encoding for
# them, so a CSV carrying such a column is rejected rather than half-supported.
_YAML_ONLY_COLUMNS: Final[frozenset[str]] = frozenset(
    {"constraints", "context_documents", "available_tools"}
)


class UnknownColumnPolicy:
    """The two policies for a CSV column the schema does not declare.

    Carried as a value rather than a boolean flag so that the choice appears in
    result metadata by name: a run that silently dropped three columns has to be
    distinguishable from a clean one.
    """

    REJECT = "reject"
    DROP = "drop"


def load_yaml_document(source_path: Path) -> Any:
    """Read one YAML document, refusing anything that is not a safe scalar tree.

    Args:
        source_path (Path): The file to read.

    Returns:
        Any: The parsed document, ordinarily a mapping or a list of mappings.

    Raises:
        ValueError: When the file cannot be parsed as YAML, chained from the
            underlying parser error so the original position survives.
        OSError: When the file cannot be read.
    """
    try:
        text = source_path.read_text(encoding=_ENCODING)
        return yaml.safe_load(text)
    except yaml.YAMLError as error:
        logger.error("QC_DATA_MALFORMED_SOURCE %s is not parseable YAML", source_path)
        raise ValueError(
            f"QC_DATA_MALFORMED_SOURCE: {source_path} is not parseable YAML"
        ) from error


def load_tasks_from_yaml(source_path: Path) -> list[TaskDataSet]:
    """Load task records from a YAML file.

    Args:
        source_path (Path): A YAML file holding one task mapping or a list of them.

    Returns:
        list[TaskDataSet]: The loaded tasks, in file order.

    Raises:
        ValueError: When the document shape is wrong, a record is invalid, or two
            identifiers collide once canonicalized.
        KeyError: When a record is missing a required field or carries an unknown key.
    """
    document = load_yaml_document(source_path)
    payloads = _as_payload_list(document, source_path)
    tasks = [TaskDataSet.from_dict(dict(entry)) for entry in payloads]
    _reject_colliding_identifiers([task.task_id for task in tasks], "task_id", source_path)
    logger.info("Loaded %d task records from %s", len(tasks), source_path)
    return tasks


def load_rule_sets_from_yaml(source_path: Path) -> list[GoldenRuleSet]:
    """Load golden rule sets from a YAML file.

    ``GoldenRuleSet`` is YAML-only. Rubric criteria with per-point anchors are
    inherently nested and have no honest flat encoding; this is a stated
    limitation rather than a defect to work around later.

    Args:
        source_path (Path): A YAML file holding one rule mapping or a list of them.

    Returns:
        list[GoldenRuleSet]: The loaded rule sets, in file order.

    Raises:
        ValueError: When the document shape is wrong, a record is invalid, or two
            identifiers collide once canonicalized.
        KeyError: When a record is missing a required field or carries an unknown key.
    """
    document = load_yaml_document(source_path)
    payloads = _as_payload_list(document, source_path)
    rule_sets = [GoldenRuleSet.from_dict(dict(entry)) for entry in payloads]
    _reject_colliding_identifiers([rule.rule_id for rule in rule_sets], "rule_id", source_path)
    logger.info("Loaded %d rule sets from %s", len(rule_sets), source_path)
    return rule_sets


def load_tasks_from_csv(
    source_path: Path, *, unknown_columns: str = UnknownColumnPolicy.REJECT
) -> list[TaskDataSet]:
    """Load flat task rows from a CSV file.

    Reading is deliberately literal. No type inference, so ``007`` stays
    ``"007"``; no null filtering, so a blank cell arrives as an empty string
    rather than a floating-point NaN that would later stringify as ``"nan"``.

    Args:
        source_path (Path): The CSV file.
        unknown_columns (str): ``reject`` or ``drop``, from
            :class:`UnknownColumnPolicy`. The chosen policy belongs in result
            metadata, because a run that dropped columns is not a clean one.

    Returns:
        list[TaskDataSet]: The loaded tasks, in file order.

    Raises:
        ValueError: When headers duplicate, a required column is absent, an
            unknown column is present under the reject policy, a YAML-only
            column appears, or two identifiers collide once canonicalized.
        KeyError: When a row is missing a required field.
    """
    text = source_path.read_text(encoding=_ENCODING)
    header = _read_and_check_header(text, source_path)
    known = _declared_task_columns()
    _reject_yaml_only_columns(header, source_path)
    _check_column_coverage(header, known, source_path, unknown_columns)

    reader = csv.DictReader(io.StringIO(text, newline=""))
    rows = [dict(row) for row in reader]
    present = _columns_carrying_values(header, rows)
    payloads = [
        _row_to_payload(row, present, known, source_path, row_number)
        for row_number, row in enumerate(rows, start=2)
    ]
    tasks = [TaskDataSet.from_dict(payload) for payload in payloads]
    _reject_colliding_identifiers([task.task_id for task in tasks], "task_id", source_path)
    logger.info("Loaded %d task rows from %s", len(tasks), source_path)
    return tasks


def assert_loaders_agree(
    yaml_tasks: Iterable[TaskDataSet], csv_tasks: Iterable[TaskDataSet]
) -> None:
    """Raise when two loaders produced different objects from equivalent input.

    The two loaders exist to provide one abstraction over two formats. If they
    diverge, every downstream result depends on which file an author happened to
    use, and nothing else would surface it.

    Args:
        yaml_tasks (Iterable): Tasks as loaded from YAML.
        csv_tasks (Iterable): Tasks as loaded from CSV.

    Returns:
        None

    Raises:
        ValueError: Naming the identifiers that differ, with
            ``QC_DATA_LOADER_DIVERGENCE``.
    """
    from_yaml = {task.task_id: task for task in yaml_tasks}
    from_csv = {task.task_id: task for task in csv_tasks}
    divergent = sorted(
        {identifier for identifier in set(from_yaml) | set(from_csv)
         if from_yaml.get(identifier) != from_csv.get(identifier)}
    )
    if divergent:
        logger.error("QC_DATA_LOADER_DIVERGENCE identifiers %s", divergent)
        raise ValueError(
            f"QC_DATA_LOADER_DIVERGENCE: loaders produced different records for {divergent}"
        )


def _declared_task_columns() -> frozenset[str]:
    """Return the task fields a CSV row may carry.

    Returns:
        frozenset[str]: Field names, excluding those with no honest flat
        encoding. Derived from the dataclass rather than a second hand-kept
        list, so the two cannot disagree.
    """
    return frozenset(
        entry.name for entry in dataclass_fields(TaskDataSet)
    ) - _YAML_ONLY_COLUMNS


def _read_and_check_header(text: str, source_path: Path) -> list[str]:
    """Read the raw header row and reject duplicate column names.

    Duplicate headers are checked **before** any dictionary is built, because a
    mapping keyed by column name silently keeps one of the two and produces
    wrong data with no error at all.

    Args:
        text (str): The whole file contents.
        source_path (Path): The file, for the message.

    Returns:
        list[str]: The header names, whitespace stripped.

    Raises:
        ValueError: When the file is empty or a header name repeats.
    """
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = [name.strip() for name in next(reader)]
    except StopIteration as error:
        raise ValueError(
            f"QC_DATA_REQUIRED_FIELD_MISSING: {source_path} carries no header row"
        ) from error

    duplicates = sorted({name for name in header if header.count(name) > 1})
    if duplicates:
        logger.error("QC_DATA_DUPLICATE_COLUMN %s repeats %s", source_path, duplicates)
        raise ValueError(
            f"QC_DATA_DUPLICATE_COLUMN: {source_path} repeats column headers {duplicates}"
        )
    return header


def _reject_yaml_only_columns(header: list[str], source_path: Path) -> None:
    """Raise when a CSV carries a column that only YAML can express.

    Args:
        header (list): The header names.
        source_path (Path): The file, for the message.

    Returns:
        None

    Raises:
        ValueError: Naming the offending columns. Accepting them would mean
            inventing a flat encoding for nested data, and the two loaders would
            stop producing identical objects.
    """
    offending = sorted(set(header) & _YAML_ONLY_COLUMNS)
    if offending:
        raise ValueError(
            f"QC_DATA_MALFORMED_SOURCE: {source_path} carries YAML-only columns {offending}; "
            f"nested fields have no honest flat encoding"
        )


def _check_column_coverage(
    header: list[str], known: frozenset[str], source_path: Path, unknown_columns: str
) -> None:
    """Apply the column policy to a header row.

    Args:
        header (list): The header names.
        known (frozenset): Column names the schema declares.
        source_path (Path): The file, for the message.
        unknown_columns (str): ``reject`` or ``drop``.

    Returns:
        None

    Raises:
        ValueError: When a required column is absent, or an unknown column is
            present under the reject policy.
    """
    required = _required_task_columns()
    absent = sorted(required - set(header))
    if absent:
        logger.error("QC_DATA_REQUIRED_FIELD_MISSING %s absent columns %s", source_path, absent)
        raise ValueError(
            f"QC_DATA_REQUIRED_FIELD_MISSING: {source_path} is missing required columns {absent}"
        )

    unknown = sorted(set(header) - known)
    if not unknown:
        return
    if unknown_columns == UnknownColumnPolicy.DROP:
        logger.warning("QC_DATA_EXTRA_COLUMN_DROPPED %s dropped %s", source_path, unknown)
        return
    logger.error("QC_DATA_UNKNOWN_FIELD %s unknown columns %s", source_path, unknown)
    raise ValueError(
        f"QC_DATA_UNKNOWN_FIELD: {source_path} carries unknown columns {unknown}"
    )


def _required_task_columns() -> frozenset[str]:
    """Return the task fields that have no default and must therefore appear.

    Required versus optional is derived from whether the dataclass field carries
    a default, so no second list is maintained and the two cannot disagree.

    Returns:
        frozenset[str]: The required column names.
    """
    return frozenset(
        entry.name
        for entry in dataclass_fields(TaskDataSet)
        if entry.default is MISSING and entry.default_factory is MISSING
    )


def _columns_carrying_values(header: list[str], rows: list[dict[str, str]]) -> frozenset[str]:
    """Return the columns that hold a value in at least one row.

    A column present but blank in every row is treated as absent, so that it
    takes its declared default rather than forcing an empty string into a field
    whose default is something else.

    Args:
        header (list): The header names.
        rows (list): The parsed rows.

    Returns:
        frozenset[str]: Columns carrying at least one non-blank value.
    """
    carrying = {
        name for name in header
        if any((row.get(name) or "").strip() for row in rows)
    }
    for name in sorted(set(header) - carrying):
        logger.info("QC_DATA_COLUMN_ABSENT column %s is blank throughout", name)
    return frozenset(carrying)


def _row_to_payload(
    row: dict[str, str],
    present: frozenset[str],
    known: frozenset[str],
    source_path: Path,
    row_number: int,
) -> dict[str, Any]:
    """Convert one CSV row into a payload the schema can validate.

    Args:
        row (dict): The raw row, all values strings.
        present (frozenset): Columns carrying a value somewhere in the file.
        known (frozenset): Columns the schema declares.
        source_path (Path): The file, for logging.
        row_number (int): One-based line number including the header, for logging.

    Returns:
        dict[str, Any]: A payload carrying only the fields this row supplies, so
        that every other field takes its declared default.
    """
    payload: dict[str, Any] = {}
    for column, raw_value in row.items():
        if column not in known or column not in present:
            continue
        value = (raw_value or "")
        stripped = value.strip()
        if stripped != value:
            logger.info(
                "QC_DATA_WHITESPACE_STRIPPED %s row %d column %s", source_path, row_number, column
            )
        if not stripped:
            logger.info(
                "QC_DATA_BLANK_CELL_DEFAULTED %s row %d column %s", source_path, row_number, column
            )
            continue
        payload[column] = _coerce_cell(column, stripped)
    return payload


def _coerce_cell(column: str, value: str) -> Any:
    """Convert one non-blank cell to the shape its field expects.

    Args:
        column (str): The column name.
        value (str): The stripped cell text.

    Returns:
        Any: A list for list-valued columns, a bool for boolean columns, and the
        text unchanged otherwise. Text is never numerically inferred, so a
        leading zero survives.
    """
    if column in _LIST_COLUMNS:
        return [part.strip() for part in value.split(_LIST_DELIMITER) if part.strip()]
    if column in _BOOLEAN_COLUMNS:
        return value.lower() in _TRUE_TOKENS
    return value


def _as_payload_list(document: Any, source_path: Path) -> list[dict[str, Any]]:
    """Normalize a YAML document into a list of record mappings.

    Args:
        document (Any): The parsed document.
        source_path (Path): The file, for the message.

    Returns:
        list[dict]: One mapping per record.

    Raises:
        ValueError: When the document is empty, or is neither a mapping nor a
            list of mappings.
    """
    if document is None:
        raise ValueError(f"QC_DATA_REQUIRED_FIELD_MISSING: {source_path} is empty")
    if isinstance(document, dict):
        return [document]
    if isinstance(document, list) and all(isinstance(entry, dict) for entry in document):
        return list(document)
    raise ValueError(
        f"QC_DATA_MALFORMED_SOURCE: {source_path} must hold a mapping or a list of mappings, "
        f"found {type(document).__name__}"
    )


def _reject_colliding_identifiers(
    identifiers: list[str], field_name: str, source_path: Optional[Path]
) -> None:
    """Raise when two identifiers differ only in a way a filesystem ignores.

    Two identifiers with one canonical form coexist on Linux and collide on
    Windows, where the second silently reuses the first's directory. Rejecting
    the pair at ingest costs nothing; discovering it later costs a corrupted
    fixture store on one platform only (A18).

    Args:
        identifiers (list): The identifiers as authored.
        field_name (str): Which field they came from, for the message.
        source_path (Optional[Path]): The file, for the message.

    Returns:
        None

    Raises:
        ValueError: Naming each colliding group.
    """
    grouped: dict[str, list[str]] = {}
    for identifier in identifiers:
        grouped.setdefault(canonical_identifier(identifier), []).append(identifier)
    collisions = sorted(
        sorted(group) for group in grouped.values() if len(set(group)) > 1
    )
    if collisions:
        logger.error("QC_DATA_IDENTIFIER_UNSAFE %s collisions %s", source_path, collisions)
        raise ValueError(
            f"QC_DATA_IDENTIFIER_UNSAFE: {source_path} carries {field_name} values that "
            f"differ only by letter case or Unicode form, and collide on a case-insensitive "
            f"filesystem: {collisions}"
        )
