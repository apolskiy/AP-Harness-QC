# SPDX-FileCopyrightText: 2026 Aleksandr Polskiy
# SPDX-License-Identifier: Apache-2.0
"""Unit preconditions for the YAML and CSV loaders.

Covers `MQC_ING_UNI_111200` through `111213`, inventoried in
``docs/design/tier1_ingestion.md`` section 13.1.

**The CSV cases carry most of the weight**, because CSV is where the loaders
can silently disagree. YAML distinguishes a value, an empty string, an explicit
null and an absent field; CSV distinguishes text from blank. Every case here
pins one consequence of closing that gap.

A failure in this module is **not a model finding**, so the module carries no priority
marker, per ``framework-rules.md`` section 3.3.
"""

from pathlib import Path
from typing import Any
import pytest

from ingestion.loaders import (
    load_corpus,
    UnknownColumnPolicy,
    assert_loaders_agree,
    load_tasks_from_csv,
    load_tasks_from_yaml,
)

pytestmark = pytest.mark.unit


def _corpus_with_both_formats(root: Path) -> Path:
    """Write a corpus holding one YAML task, one CSV task and one rule set.

    Args:
        root (Path): Where to build it.

    Returns:
        Path: The corpus root.
    """
    (root / "tasks").mkdir(parents=True, exist_ok=True)
    (root / "rules").mkdir(parents=True, exist_ok=True)
    (root / "tasks" / "yaml_side.yaml").write_text(
        "- task_id: MQC_TASK_from_yaml\n"
        "  rubric_ids: [MQC_RULE_only]\n"
        "  user_prompt: Summarise this.\n",
        encoding="utf-8",
    )
    (root / "tasks" / "csv_side.csv").write_text(
        "task_id,rubric_ids,user_prompt\n"
        "MQC_TASK_from_csv,MQC_RULE_only,Summarise this.\n",
        encoding="utf-8",
    )
    (root / "rules" / "only.yaml").write_text(
        "- rule_id: MQC_RULE_only\n"
        "  priority: 2\n"
        "  priority_conditions: [P2_DOCUMENTED_BEHAVIOUR]\n"
        "  assertions:\n"
        "    - assertion_id: A_ONLY\n"
        "      kind: contains\n"
        "      parameters: {value: summary}\n"
        "      taxonomy_code: QC_LLM_INSTRUCTION_DRIFT\n"
        "      severity: violation\n",
        encoding="utf-8",
    )
    return root


_HEADER = "task_id,rubric_ids,user_prompt"


class TestMQCCsvLoader:
    """Reading flat task rows without inference or silent alteration."""


    def MQC_ING_UNI_111219_a_corpus_directory_loads_each_file_by_its_format(
        self, tmp_path: Path
    ) -> None:
        """A corpus directory loads YAML and CSV task files together.

        The reader comes from each file's suffix, so one corpus may hold both
        and the objects are indistinguishable afterwards, which is the
        abstraction ``assert_loaders_agree`` exists to protect.

        Design: ``tier1_ingestion.md`` section 4.5.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        root = _corpus_with_both_formats(tmp_path)

        tasks, rules = load_corpus(root)

        assert sorted(task.task_id for task in tasks) == [
            "MQC_TASK_from_csv", "MQC_TASK_from_yaml",
        ]
        assert [rule.rule_id for rule in rules] == ["MQC_RULE_only"]

        # THE CSV TASK IS A TASK, not a near-miss: the suffix chose a reader and
        # the reader produced the same kind of object.
        from_csv = next(task for task in tasks if task.task_id == "MQC_TASK_from_csv")
        assert from_csv.user_prompt == "Summarise this."
        assert from_csv.rubric_ids == ["MQC_RULE_only"]

    def MQC_ING_UNI_111220_a_rules_csv_or_an_empty_corpus_is_refused(
        self, tmp_path: Path
    ) -> None:
        """A rules file in CSV, an absent directory and an empty one are refused.

        A rule set carries nested anchors and assertions that CSV cannot
        express, so no reader claims one and the file is refused rather than
        skipped: a corpus half-loaded reports a smaller suite and not an error.

        An empty corpus is refused for the same reason. Nothing further along
        can tell it from a wrong path, and a run that measured nothing would
        otherwise report a clean pass.

        Design: ``tier1_ingestion.md`` section 4.5.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        root = _corpus_with_both_formats(tmp_path / "rules_as_csv")
        (root / "rules" / "extra.csv").write_text("rule_id\n", encoding="utf-8")

        with pytest.raises(ValueError, match="QC_DATA_MALFORMED_SOURCE"):
            load_corpus(root)

        # AN ABSENT DIRECTORY, which is what a wrong --golden-rules looks like.
        # Tasks are populated so the missing rules directory is what fires: the
        # loader checks each kind in turn, so an empty tasks folder would report
        # itself first and this case would not be about the absent one.
        bare = _corpus_with_both_formats(tmp_path / "bare")
        for leftover in (bare / "rules").iterdir():
            leftover.unlink()
        (bare / "rules").rmdir()
        with pytest.raises(ValueError, match="names no rules directory"):
            load_corpus(bare)

        # AND AN EMPTY ONE, which a wrong path also looks like.
        empty = tmp_path / "empty"
        (empty / "tasks").mkdir(parents=True)
        (empty / "rules").mkdir(parents=True)
        with pytest.raises(ValueError, match="no readable tasks file"):
            load_corpus(empty)

    def MQC_ING_UNI_111200_csv_loader_parses_flat_task_rows(self, write_text_file: Any) -> None:
        """A well-formed file yields one record per row, in file order.

        Args:
            write_text_file (Any): Helper writing a UTF-8 file.

        Returns:
            None
        """
        path = write_text_file(
            "tasks.csv", f"{_HEADER}\nMQC_TASK_one,R1;R2,Rewrite it\nMQC_TASK_two,R1,Summarise it\n"
        )
        tasks = load_tasks_from_csv(path)
        assert [task.task_id for task in tasks] == ["MQC_TASK_one", "MQC_TASK_two"]
        assert tasks[0].rubric_ids == ["R1", "R2"]

    def MQC_ING_UNI_111201_csv_loader_rejects_duplicate_column_headers(
        self,
        write_text_file: Any,
    ) -> None:
        """A repeated header is caught before any mapping is built.

        A dictionary keyed by column name keeps one of the two and produces
        wrong data with no error at all, so the raw header is checked first.

        Args:
            write_text_file (Any): Helper writing a UTF-8 file.

        Returns:
            None
        """
        path = write_text_file("dup.csv", "task_id,task_id,rubric_ids,user_prompt\na,b,R1,p\n")
        with pytest.raises(ValueError, match="QC_DATA_DUPLICATE_COLUMN") as caught:
            load_tasks_from_csv(path)
        assert "task_id" in str(caught.value)

    def MQC_ING_UNI_111202_csv_blank_cell_takes_declared_default(
        self, write_text_file: Any
    ) -> None:
        """A blank cell equals an absent field, because CSV cannot express null.

        Args:
            write_text_file (Any): Helper writing a UTF-8 file.

        Returns:
            None
        """
        path = write_text_file(
            "blank.csv",
            f"{_HEADER},system_instruction\nMQC_TASK_one,R1,Rewrite it,Be terse\n"
            "MQC_TASK_two,R1,Summarise it,\n",
        )
        tasks = load_tasks_from_csv(path)
        assert tasks[0].system_instruction == "Be terse"
        assert tasks[1].system_instruction is None

    def MQC_ING_UNI_111203_csv_absent_optional_column_takes_default(
        self,
        write_text_file: Any,
    ) -> None:
        """An omitted optional column behaves as a blank one.

        Args:
            write_text_file (Any): Helper writing a UTF-8 file.

        Returns:
            None
        """
        path = write_text_file("min.csv", f"{_HEADER}\nMQC_TASK_one,R1,Rewrite it\n")
        assert load_tasks_from_csv(path)[0].tags == frozenset()

    def MQC_ING_UNI_111204_csv_absent_required_column_is_rejected(
        self,
        write_text_file: Any,
    ) -> None:
        """A missing required column names the field rather than failing vaguely.

        Args:
            write_text_file (Any): Helper writing a UTF-8 file.

        Returns:
            None
        """
        path = write_text_file("short.csv", "task_id,user_prompt\nMQC_TASK_one,Rewrite it\n")
        with pytest.raises(ValueError, match="QC_DATA_REQUIRED_FIELD_MISSING") as caught:
            load_tasks_from_csv(path)
        assert "rubric_ids" in str(caught.value)

    def MQC_ING_UNI_111205_csv_unknown_column_rejected_by_default(
        self,
        write_text_file: Any,
    ) -> None:
        """The default policy refuses a column the schema does not declare.

        Args:
            write_text_file (Any): Helper writing a UTF-8 file.

        Returns:
            None
        """
        path = write_text_file("extra.csv", f"{_HEADER},notes\nMQC_TASK_one,R1,Rewrite it,hello\n")
        with pytest.raises(ValueError, match="QC_DATA_UNKNOWN_FIELD") as caught:
            load_tasks_from_csv(path)
        assert "notes" in str(caught.value)

    def MQC_ING_UNI_111206_csv_unknown_column_dropped_under_override(
        self,
        write_text_file: Any,
    ) -> None:
        """The override proceeds, and the choice belongs in result metadata.

        A run that silently dropped three columns has to be distinguishable
        from a clean one, which is why the policy is a named value rather than
        a boolean flag.

        Args:
            write_text_file (Any): Helper writing a UTF-8 file.

        Returns:
            None
        """
        path = write_text_file("extra.csv", f"{_HEADER},notes\nMQC_TASK_one,R1,Rewrite it,hello\n")
        tasks = load_tasks_from_csv(path, unknown_columns=UnknownColumnPolicy.DROP)
        assert tasks[0].task_id == "MQC_TASK_one"

    def MQC_ING_UNI_111207_csv_entirely_blank_column_treated_as_absent(
        self,
        write_text_file: Any,
    ) -> None:
        """A column blank in every row takes its default rather than an empty value.

        Args:
            write_text_file (Any): Helper writing a UTF-8 file.

        Returns:
            None
        """
        path = write_text_file(
            "blankcol.csv",
            f"{_HEADER},tags\nMQC_TASK_one,R1,Rewrite it,\nMQC_TASK_two,R1,Summarise it,\n",
        )
        assert all(task.tags == frozenset() for task in load_tasks_from_csv(path))

    def MQC_ING_UNI_111208_csv_preserves_leading_zeros_without_inference(
        self,
        write_text_file: Any,
    ) -> None:
        """No numeric inference, so an identifier keeps the shape it was written in.

        Args:
            write_text_file (Any): Helper writing a UTF-8 file.

        Returns:
            None
        """
        path = write_text_file("zeros.csv", f"{_HEADER}\nMQC_TASK_007,R1,Rewrite it\n")
        assert load_tasks_from_csv(path)[0].task_id == "MQC_TASK_007"

    def MQC_ING_UNI_111209_csv_blank_cell_is_empty_string_not_nan(
        self,
        write_text_file: Any,
    ) -> None:
        """A blank never becomes a float that later stringifies as text.

        Reading without null filtering is the load-bearing decision here: a NaN
        reaching a string field would arrive downstream as the four characters
        that spell it, and nothing would report an error.

        Args:
            write_text_file (Any): Helper writing a UTF-8 file.

        Returns:
            None
        """
        path = write_text_file(
            "nan.csv", f"{_HEADER},system_instruction\nMQC_TASK_one,R1,Rewrite it,\n"
        )
        loaded = load_tasks_from_csv(path)[0]
        assert loaded.system_instruction is None
        assert "nan" not in str(loaded.system_instruction).lower()

    def MQC_ING_UNI_111210_csv_strips_surrounding_whitespace(self, write_text_file: Any) -> None:
        """Whitespace is removed as a documented transformation, not silently.

        Args:
            write_text_file (Any): Helper writing a UTF-8 file.

        Returns:
            None
        """
        path = write_text_file("pad.csv", f"{_HEADER}\n  MQC_TASK_one  ,R1,  Rewrite it  \n")
        loaded = load_tasks_from_csv(path)[0]
        assert loaded.task_id == "MQC_TASK_one"
        assert loaded.user_prompt == "Rewrite it"

    def MQC_ING_UNI_111211_csv_tolerates_utf8_bom_in_header(self, tmp_path: Path) -> None:
        """A byte order mark must not become part of the first column name.

        Written as bytes deliberately: the defect this guards appears only when
        a real BOM is present, and a helper that writes text could normalize it
        away and make the test vacuous.

        Args:
            tmp_path (Path): pytest's temporary directory.

        Returns:
            None
        """
        path = tmp_path / "bom.csv"
        path.write_bytes(f"\ufeff{_HEADER}\nMQC_TASK_one,R1,Rewrite it\n".encode("utf-8"))
        assert load_tasks_from_csv(path)[0].task_id == "MQC_TASK_one"

    def MQC_ING_UNI_111214_csv_rejects_a_yaml_only_column(self, write_text_file: Any) -> None:
        """A nested field has no honest flat encoding, so the file is refused.

        Accepting it would mean inventing one, and the two loaders would stop
        producing identical objects from equivalent input.

        Args:
            write_text_file (Any): Helper writing a UTF-8 file.

        Returns:
            None
        """
        path = write_text_file(
            "nested.csv", f"{_HEADER},constraints\nMQC_TASK_one,R1,Rewrite it,something\n"
        )
        with pytest.raises(ValueError, match="QC_DATA_MALFORMED_SOURCE") as caught:
            load_tasks_from_csv(path)
        assert "constraints" in str(caught.value)


class TestMQCLoaderAgreement:
    """The two loaders provide one abstraction, and that claim is checked."""

    def MQC_ING_UNI_111212_loaders_produce_identical_objects_for_equivalent_input(
        self, write_text_file: Any
    ) -> None:
        """Equivalent YAML and CSV yield equal records.

        If they diverge, every downstream result depends on which file an
        author happened to use, and nothing else would surface it.

        Args:
            write_text_file (Any): Helper writing a UTF-8 file.

        Returns:
            None
        """
        csv_path = write_text_file("same.csv", f"{_HEADER}\nMQC_TASK_one,R1;R2,Rewrite it\n")
        yaml_path = write_text_file(
            "same.yaml",
            "- task_id: MQC_TASK_one\n  rubric_ids: [R1, R2]\n  user_prompt: Rewrite it\n",
        )
        from_csv = load_tasks_from_csv(csv_path)
        from_yaml = load_tasks_from_yaml(yaml_path)
        assert from_csv == from_yaml
        assert_loaders_agree(from_yaml, from_csv)

    def MQC_ING_UNI_111213_loader_divergence_is_reported(self, write_text_file: Any) -> None:
        """A difference is named rather than tolerated.

        Args:
            write_text_file (Any): Helper writing a UTF-8 file.

        Returns:
            None
        """
        csv_path = write_text_file("a.csv", f"{_HEADER}\nMQC_TASK_one,R1,Rewrite it\n")
        yaml_path = write_text_file(
            "a.yaml",
            "- task_id: MQC_TASK_one\n  rubric_ids: [R1]\n  user_prompt: Summarise it\n",
        )
        with pytest.raises(ValueError, match="QC_DATA_LOADER_DIVERGENCE") as caught:
            assert_loaders_agree(load_tasks_from_yaml(yaml_path), load_tasks_from_csv(csv_path))
        assert "MQC_TASK_one" in str(caught.value)


class TestMQCYamlLoader:
    """Reading the format that carries everything CSV cannot."""

    def MQC_ING_UNI_111215_yaml_rejects_an_unparseable_document(self, write_text_file: Any) -> None:
        """A syntax error is a malformed source, reported with its file.

        Args:
            write_text_file (Any): Helper writing a UTF-8 file.

        Returns:
            None
        """
        path = write_text_file("bad.yaml", "task_id: [unclosed\n")
        with pytest.raises(ValueError, match="QC_DATA_MALFORMED_SOURCE"):
            load_tasks_from_yaml(path)

    def MQC_ING_UNI_111216_yaml_rejects_a_document_of_the_wrong_shape(
        self,
        write_text_file: Any,
    ) -> None:
        """A list of scalars is not a list of records.

        Args:
            write_text_file (Any): Helper writing a UTF-8 file.

        Returns:
            None
        """
        path = write_text_file("shape.yaml", "- 1\n- 2\n")
        with pytest.raises(ValueError, match="QC_DATA_MALFORMED_SOURCE"):
            load_tasks_from_yaml(path)

    def MQC_ING_UNI_111217_yaml_accepts_a_single_mapping_or_a_list(
        self,
        write_text_file: Any,
    ) -> None:
        """One record may be written without list syntax.

        Args:
            write_text_file (Any): Helper writing a UTF-8 file.

        Returns:
            None
        """
        single = write_text_file(
            "one.yaml", "task_id: MQC_TASK_one\nrubric_ids: [R1]\nuser_prompt: Rewrite it\n"
        )
        listed = write_text_file(
            "list.yaml", "- task_id: MQC_TASK_one\n  rubric_ids: [R1]\n  user_prompt: Rewrite it\n"
        )
        assert load_tasks_from_yaml(single) == load_tasks_from_yaml(listed)

    def MQC_ING_UNI_111218_identifiers_colliding_by_case_are_rejected(
        self,
        write_text_file: Any,
    ) -> None:
        """Two identifiers with one canonical form collide on Windows.

        They coexist on Linux, so nothing surfaces the problem until a fixture
        directory is silently reused on the other platform.

        Args:
            write_text_file (Any): Helper writing a UTF-8 file.

        Returns:
            None
        """
        path = write_text_file(
            "collide.csv", f"{_HEADER}\nMQC_TASK_Alpha,R1,Rewrite it\nMQC_TASK_alpha,R1,Do it\n"
        )
        with pytest.raises(ValueError, match="QC_DATA_IDENTIFIER_UNSAFE"):
            load_tasks_from_csv(path)
