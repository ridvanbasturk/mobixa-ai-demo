import csv

from services.evaluation_logger import (
    FIELDNAMES,
    log_evaluation,
    save_human_evaluation,
    save_storyboard_selection,
    save_video_generation,
)


def _write_legacy_csv(path):
    legacy_fields = [
        "timestamp",
        "feature",
        "model_id",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "latency_ms",
        "estimated_cost_usd",
        "json_valid",
        "schema_valid",
        "question_count",
        "success",
        "error",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=legacy_fields)
        writer.writeheader()
        writer.writerow(
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "feature": "B1",
                "model_id": "old-model",
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
                "latency_ms": 100.0,
                "estimated_cost_usd": 0.001,
                "json_valid": True,
                "schema_valid": True,
                "question_count": 3,
                "success": True,
                "error": "",
            }
        )


def test_log_evaluation_creates_file_with_new_schema(tmp_path):
    csv_path = tmp_path / "evaluations.csv"
    run_id = log_evaluation(
        feature="B1",
        model_id="test-model",
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        latency_ms=123.456,
        estimated_cost_usd=0.001,
        json_valid=True,
        schema_valid=True,
        question_count=2,
        success=True,
        error=None,
        csv_path=csv_path,
    )
    assert run_id

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == FIELDNAMES
        rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["run_id"] == run_id
    assert rows[0]["human_answer_key_correct"] == ""


def test_log_evaluation_migrates_legacy_csv(tmp_path):
    csv_path = tmp_path / "evaluations.csv"
    _write_legacy_csv(csv_path)

    log_evaluation(
        feature="B1",
        model_id="new-model",
        input_tokens=1,
        output_tokens=2,
        total_tokens=3,
        latency_ms=50.0,
        estimated_cost_usd=0.0005,
        json_valid=True,
        schema_valid=True,
        question_count=1,
        success=True,
        error=None,
        csv_path=csv_path,
    )

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == FIELDNAMES
        rows = list(reader)

    assert len(rows) == 2
    assert rows[0]["model_id"] == "old-model"
    assert rows[0]["run_id"] == ""
    assert rows[0]["human_answer_key_correct"] == ""
    assert rows[1]["model_id"] == "new-model"


def test_save_human_evaluation_updates_matching_row(tmp_path):
    csv_path = tmp_path / "evaluations.csv"
    run_id = log_evaluation(
        feature="B1",
        model_id="test-model",
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        latency_ms=100.0,
        estimated_cost_usd=0.001,
        json_valid=True,
        schema_valid=True,
        question_count=2,
        success=True,
        error=None,
        csv_path=csv_path,
    )

    saved = save_human_evaluation(
        run_id=run_id,
        answer_key_correct="Yes",
        groundedness="Partially",
        language_quality=4,
        notes="Looks reasonable",
        csv_path=csv_path,
    )
    assert saved is True

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["human_answer_key_correct"] == "Yes"
    assert rows[0]["human_groundedness"] == "Partially"
    assert rows[0]["human_language_quality"] == "4"
    assert rows[0]["human_notes"] == "Looks reasonable"


def test_save_human_evaluation_returns_false_when_run_id_missing(tmp_path):
    csv_path = tmp_path / "evaluations.csv"
    log_evaluation(
        feature="B1",
        model_id="test-model",
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        latency_ms=100.0,
        estimated_cost_usd=0.001,
        json_valid=True,
        schema_valid=True,
        question_count=2,
        success=True,
        error=None,
        csv_path=csv_path,
    )

    saved = save_human_evaluation(
        run_id="does-not-exist",
        answer_key_correct="Yes",
        groundedness="Yes",
        language_quality=5,
        notes="",
        csv_path=csv_path,
    )
    assert saved is False


def test_log_evaluation_records_b6_numeric_validation_fields(tmp_path):
    csv_path = tmp_path / "evaluations.csv"
    run_id = log_evaluation(
        feature="B6",
        model_id="qwen.qwen3-next-80b-a3b-instruct",
        input_tokens=100,
        output_tokens=200,
        total_tokens=300,
        latency_ms=500.0,
        estimated_cost_usd=0.002,
        json_valid=True,
        schema_valid=True,
        question_count=4,
        success=True,
        error=None,
        numeric_validation_passed=False,
        numeric_validation_details="99, 150",
        csv_path=csv_path,
    )

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert rows[0]["run_id"] == run_id
    assert rows[0]["feature"] == "B6"
    assert rows[0]["numeric_validation_passed"] == "False"
    assert rows[0]["numeric_validation_details"] == "99, 150"


def test_save_human_evaluation_supports_b6_fields_without_touching_b1_fields(tmp_path):
    csv_path = tmp_path / "evaluations.csv"
    run_id = log_evaluation(
        feature="B6",
        model_id="deepseek.v3.2",
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        latency_ms=100.0,
        estimated_cost_usd=0.001,
        json_valid=True,
        schema_valid=True,
        question_count=4,
        success=True,
        error=None,
        numeric_validation_passed=True,
        numeric_validation_details="",
        csv_path=csv_path,
    )

    saved = save_human_evaluation(
        run_id=run_id,
        groundedness="Yes",
        language_quality=4,
        notes="İyi görünüyor",
        numeric_accuracy="Yes",
        actionability=5,
        causality_issue="No",
        csv_path=csv_path,
    )
    assert saved is True

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    row = rows[0]
    assert row["human_numeric_accuracy"] == "Yes"
    assert row["human_actionability"] == "5"
    assert row["human_causality_issue"] == "No"
    assert row["human_groundedness"] == "Yes"
    assert row["human_language_quality"] == "4"
    assert row["human_notes"] == "İyi görünüyor"
    # B1'e özgü alan hiç dokunulmadığı için boş kalmalı
    assert row["human_answer_key_correct"] == ""


def test_b1_and_b6_rows_coexist_without_interference(tmp_path):
    csv_path = tmp_path / "evaluations.csv"

    b1_run_id = log_evaluation(
        feature="B1",
        model_id="qwen.qwen3-next-80b-a3b-instruct",
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        latency_ms=100.0,
        estimated_cost_usd=0.001,
        json_valid=True,
        schema_valid=True,
        question_count=5,
        success=True,
        error=None,
        csv_path=csv_path,
    )
    b6_run_id = log_evaluation(
        feature="B6",
        model_id="deepseek.v3.2",
        input_tokens=100,
        output_tokens=200,
        total_tokens=300,
        latency_ms=500.0,
        estimated_cost_usd=0.004,
        json_valid=True,
        schema_valid=True,
        question_count=4,
        success=True,
        error=None,
        numeric_validation_passed=True,
        numeric_validation_details="",
        csv_path=csv_path,
    )

    save_human_evaluation(
        run_id=b1_run_id,
        answer_key_correct="Yes",
        groundedness="Yes",
        language_quality=5,
        notes="B1 notu",
        csv_path=csv_path,
    )

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    b1_row = next(r for r in rows if r["run_id"] == b1_run_id)
    b6_row = next(r for r in rows if r["run_id"] == b6_run_id)

    assert b1_row["feature"] == "B1"
    assert b1_row["human_answer_key_correct"] == "Yes"
    assert b1_row["numeric_validation_passed"] == ""

    assert b6_row["feature"] == "B6"
    assert b6_row["numeric_validation_passed"] == "True"
    assert b6_row["human_answer_key_correct"] == ""


def test_log_evaluation_records_c1_business_validation_fields(tmp_path):
    csv_path = tmp_path / "evaluations.csv"
    run_id = log_evaluation(
        feature="C1",
        model_id="qwen.qwen3-next-80b-a3b-instruct",
        input_tokens=150,
        output_tokens=250,
        total_tokens=400,
        latency_ms=700.0,
        estimated_cost_usd=0.0025,
        json_valid=True,
        schema_valid=True,
        question_count=2,
        success=True,
        error=None,
        business_validation_passed=True,
        business_validation_details="",
        weak_topics_covered=2,
        weak_topics_total=2,
        csv_path=csv_path,
    )

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    row = rows[0]
    assert row["run_id"] == run_id
    assert row["feature"] == "C1"
    assert row["business_validation_passed"] == "True"
    assert row["weak_topics_covered"] == "2"
    assert row["weak_topics_total"] == "2"
    # C1 için insan değerlendirmesi alanı hiç kullanılmadığı için boş kalmalı
    assert row["human_answer_key_correct"] == ""


def test_b1_b6_and_c1_rows_coexist_without_interference(tmp_path):
    csv_path = tmp_path / "evaluations.csv"

    b1_run_id = log_evaluation(
        feature="B1",
        model_id="qwen.qwen3-next-80b-a3b-instruct",
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        latency_ms=100.0,
        estimated_cost_usd=0.001,
        json_valid=True,
        schema_valid=True,
        question_count=5,
        success=True,
        error=None,
        csv_path=csv_path,
    )
    b6_run_id = log_evaluation(
        feature="B6",
        model_id="deepseek.v3.2",
        input_tokens=100,
        output_tokens=200,
        total_tokens=300,
        latency_ms=500.0,
        estimated_cost_usd=0.004,
        json_valid=True,
        schema_valid=True,
        question_count=4,
        success=True,
        error=None,
        numeric_validation_passed=True,
        numeric_validation_details="",
        csv_path=csv_path,
    )
    c1_run_id = log_evaluation(
        feature="C1",
        model_id="qwen.qwen3-next-80b-a3b-instruct",
        input_tokens=150,
        output_tokens=250,
        total_tokens=400,
        latency_ms=700.0,
        estimated_cost_usd=0.0025,
        json_valid=True,
        schema_valid=True,
        question_count=2,
        success=True,
        error=None,
        business_validation_passed=False,
        business_validation_details="Toplam süre günlük limiti aşıyor",
        weak_topics_covered=1,
        weak_topics_total=2,
        csv_path=csv_path,
    )

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    b1_row = next(r for r in rows if r["run_id"] == b1_run_id)
    b6_row = next(r for r in rows if r["run_id"] == b6_run_id)
    c1_row = next(r for r in rows if r["run_id"] == c1_run_id)

    assert b1_row["feature"] == "B1"
    assert b1_row["business_validation_passed"] == ""
    assert b1_row["numeric_validation_passed"] == ""

    assert b6_row["feature"] == "B6"
    assert b6_row["numeric_validation_passed"] == "True"
    assert b6_row["business_validation_passed"] == ""

    assert c1_row["feature"] == "C1"
    assert c1_row["business_validation_passed"] == "False"
    assert c1_row["business_validation_details"] == "Toplam süre günlük limiti aşıyor"
    assert c1_row["weak_topics_covered"] == "1"
    assert c1_row["weak_topics_total"] == "2"
    assert c1_row["numeric_validation_passed"] == ""
    assert c1_row["human_answer_key_correct"] == ""


def test_log_evaluation_records_a2_grounding_and_escalation_fields(tmp_path):
    csv_path = tmp_path / "evaluations.csv"
    run_id = log_evaluation(
        feature="A2",
        model_id="deepseek.v3.2",
        input_tokens=80,
        output_tokens=60,
        total_tokens=140,
        latency_ms=300.0,
        estimated_cost_usd=0.0009,
        json_valid=True,
        schema_valid=True,
        question_count=1,
        success=True,
        error=None,
        retrieved_source_ids="KB01,KB05",
        cited_source_ids="KB01",
        grounding_validation_passed=True,
        grounding_validation_details="",
        model_escalation_recommended=False,
        final_needs_escalation=False,
        csv_path=csv_path,
    )

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    row = rows[0]
    assert row["run_id"] == run_id
    assert row["feature"] == "A2"
    assert row["retrieved_source_ids"] == "KB01,KB05"
    assert row["cited_source_ids"] == "KB01"
    assert row["grounding_validation_passed"] == "True"
    assert row["model_escalation_recommended"] == "False"
    assert row["final_needs_escalation"] == "False"
    # A2 için insan değerlendirmesi hiç kullanılmadığı için boş kalmalı
    assert row["human_answer_key_correct"] == ""


def test_b1_b6_c1_and_a2_rows_coexist_without_interference(tmp_path):
    csv_path = tmp_path / "evaluations.csv"

    b1_run_id = log_evaluation(
        feature="B1",
        model_id="qwen.qwen3-next-80b-a3b-instruct",
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        latency_ms=100.0,
        estimated_cost_usd=0.001,
        json_valid=True,
        schema_valid=True,
        question_count=5,
        success=True,
        error=None,
        csv_path=csv_path,
    )
    b6_run_id = log_evaluation(
        feature="B6",
        model_id="deepseek.v3.2",
        input_tokens=100,
        output_tokens=200,
        total_tokens=300,
        latency_ms=500.0,
        estimated_cost_usd=0.004,
        json_valid=True,
        schema_valid=True,
        question_count=4,
        success=True,
        error=None,
        numeric_validation_passed=True,
        numeric_validation_details="",
        csv_path=csv_path,
    )
    c1_run_id = log_evaluation(
        feature="C1",
        model_id="qwen.qwen3-next-80b-a3b-instruct",
        input_tokens=150,
        output_tokens=250,
        total_tokens=400,
        latency_ms=700.0,
        estimated_cost_usd=0.0025,
        json_valid=True,
        schema_valid=True,
        question_count=2,
        success=True,
        error=None,
        business_validation_passed=True,
        business_validation_details="",
        weak_topics_covered=2,
        weak_topics_total=2,
        csv_path=csv_path,
    )
    a2_run_id = log_evaluation(
        feature="A2",
        model_id="moonshotai.kimi-k2.5",
        input_tokens=80,
        output_tokens=60,
        total_tokens=140,
        latency_ms=300.0,
        estimated_cost_usd=0.0009,
        json_valid=True,
        schema_valid=True,
        question_count=1,
        success=True,
        error=None,
        retrieved_source_ids="KB01",
        cited_source_ids="KB01",
        grounding_validation_passed=False,
        grounding_validation_details="Bilinmeyen kaynak kimliği kullanılmış: KB99",
        model_escalation_recommended=False,
        final_needs_escalation=True,
        csv_path=csv_path,
    )

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    b1_row = next(r for r in rows if r["run_id"] == b1_run_id)
    b6_row = next(r for r in rows if r["run_id"] == b6_run_id)
    c1_row = next(r for r in rows if r["run_id"] == c1_run_id)
    a2_row = next(r for r in rows if r["run_id"] == a2_run_id)

    assert b1_row["feature"] == "B1"
    assert b1_row["grounding_validation_passed"] == ""
    assert b1_row["business_validation_passed"] == ""

    assert b6_row["feature"] == "B6"
    assert b6_row["numeric_validation_passed"] == "True"
    assert b6_row["grounding_validation_passed"] == ""

    assert c1_row["feature"] == "C1"
    assert c1_row["business_validation_passed"] == "True"
    assert c1_row["grounding_validation_passed"] == ""

    assert a2_row["feature"] == "A2"
    assert a2_row["grounding_validation_passed"] == "False"
    assert a2_row["final_needs_escalation"] == "True"
    assert a2_row["business_validation_passed"] == ""
    assert a2_row["numeric_validation_passed"] == ""
    assert a2_row["human_answer_key_correct"] == ""


def test_log_evaluation_records_a1_storyboard_fields(tmp_path):
    csv_path = tmp_path / "evaluations.csv"
    run_id = log_evaluation(
        feature="A1",
        model_id="deepseek.v3.2",
        input_tokens=200,
        output_tokens=400,
        total_tokens=600,
        latency_ms=900.0,
        estimated_cost_usd=0.003,
        json_valid=True,
        schema_valid=True,
        question_count=6,
        success=True,
        error=None,
        storyboard_validation_passed=True,
        storyboard_validation_details="",
        storyboard_scene_count=6,
        storyboard_total_duration=36,
        storyboard_selected=False,
        selected_storyboard_model="",
        csv_path=csv_path,
    )

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == FIELDNAMES
        rows = list(reader)

    row = rows[0]
    assert row["run_id"] == run_id
    assert row["feature"] == "A1"
    assert row["storyboard_validation_passed"] == "True"
    assert row["storyboard_scene_count"] == "6"
    assert row["storyboard_total_duration"] == "36"
    assert row["storyboard_selected"] == "False"
    assert row["human_answer_key_correct"] == ""
    assert row["business_validation_passed"] == ""


def test_save_storyboard_selection_updates_matching_row(tmp_path):
    csv_path = tmp_path / "evaluations.csv"
    run_id = log_evaluation(
        feature="A1",
        model_id="deepseek.v3.2",
        input_tokens=200,
        output_tokens=400,
        total_tokens=600,
        latency_ms=900.0,
        estimated_cost_usd=0.003,
        json_valid=True,
        schema_valid=True,
        question_count=6,
        success=True,
        error=None,
        storyboard_validation_passed=True,
        storyboard_validation_details="",
        storyboard_scene_count=6,
        storyboard_total_duration=36,
        storyboard_selected=False,
        selected_storyboard_model="",
        csv_path=csv_path,
    )

    saved = save_storyboard_selection(run_id, True, "deepseek.v3.2", csv_path=csv_path)
    assert saved is True

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["storyboard_selected"] == "True"
    assert rows[0]["selected_storyboard_model"] == "deepseek.v3.2"


def test_save_storyboard_selection_returns_false_when_run_id_missing(tmp_path):
    csv_path = tmp_path / "evaluations.csv"
    log_evaluation(
        feature="A1",
        model_id="deepseek.v3.2",
        input_tokens=200,
        output_tokens=400,
        total_tokens=600,
        latency_ms=900.0,
        estimated_cost_usd=0.003,
        json_valid=True,
        schema_valid=True,
        question_count=6,
        success=True,
        error=None,
        csv_path=csv_path,
    )

    saved = save_storyboard_selection("does-not-exist", True, "deepseek.v3.2", csv_path=csv_path)
    assert saved is False


def test_save_video_generation_updates_matching_row(tmp_path):
    csv_path = tmp_path / "evaluations.csv"
    run_id = log_evaluation(
        feature="A1",
        model_id="qwen.qwen3-32b",
        input_tokens=200,
        output_tokens=400,
        total_tokens=600,
        latency_ms=900.0,
        estimated_cost_usd=0.003,
        json_valid=True,
        schema_valid=True,
        question_count=6,
        success=True,
        error=None,
        storyboard_selected=True,
        selected_storyboard_model="qwen.qwen3-32b",
        csv_path=csv_path,
    )

    saved = save_video_generation(
        run_id,
        video_generated=True,
        video_resolution="1280x720",
        video_fps=24,
        video_expected_duration=36.0,
        video_actual_duration=35.2,
        video_file_size_bytes=524288,
        video_generation_seconds=12.4,
        video_encoder="ffmpeg (libx264)",
        csv_path=csv_path,
    )
    assert saved is True

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == FIELDNAMES
        rows = list(reader)

    row = rows[0]
    assert row["video_generated"] == "True"
    assert row["video_resolution"] == "1280x720"
    assert row["video_fps"] == "24"
    assert row["video_expected_duration"] == "36.0"
    assert row["video_actual_duration"] == "35.2"
    assert row["video_file_size_bytes"] == "524288"
    assert row["video_generation_seconds"] == "12.4"
    assert row["video_encoder"] == "ffmpeg (libx264)"
    # Storyboard alanlarına dokunulmamalı
    assert row["storyboard_selected"] == "True"
    assert row["selected_storyboard_model"] == "qwen.qwen3-32b"
    # Video/ekran görüntüsü baytları CSV'ye asla yazılmaz; şemada bu alanlar hiç yok
    assert "video_bytes" not in FIELDNAMES
    assert "screenshot_bytes" not in FIELDNAMES


def test_save_video_generation_returns_false_when_run_id_missing(tmp_path):
    csv_path = tmp_path / "evaluations.csv"
    log_evaluation(
        feature="A1",
        model_id="qwen.qwen3-32b",
        input_tokens=200,
        output_tokens=400,
        total_tokens=600,
        latency_ms=900.0,
        estimated_cost_usd=0.003,
        json_valid=True,
        schema_valid=True,
        question_count=6,
        success=True,
        error=None,
        csv_path=csv_path,
    )

    saved = save_video_generation(
        "does-not-exist", video_generated=True, video_resolution="1280x720", csv_path=csv_path
    )
    assert saved is False


def test_video_fields_blank_for_non_a1_rows(tmp_path):
    csv_path = tmp_path / "evaluations.csv"
    run_id = log_evaluation(
        feature="B1",
        model_id="qwen.qwen3-235b-a22b-2507",
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        latency_ms=100.0,
        estimated_cost_usd=0.001,
        json_valid=True,
        schema_valid=True,
        question_count=5,
        success=True,
        error=None,
        csv_path=csv_path,
    )

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    row = next(r for r in rows if r["run_id"] == run_id)
    assert row["video_generated"] == ""
    assert row["video_resolution"] == ""
    assert row["video_fps"] == ""
