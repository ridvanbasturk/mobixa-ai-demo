import json
from pathlib import Path

from scripts.build_activity_catalog import build_catalog, build_catalog_row

GAME_ACTIVITY = {
    "activityId": 17197,
    "activityType": "GAME",
    "activityTypeId": 1,
    "activitySubType": "DEEPLEARN",
    "activitySubTypeId": 10,
    "timeLimit": 0,
    "title": "Satış Bombası",
    "icon": "https://cdn-test.mobixa.ai/mobileIcons/dog.webp",
    "questions": {
        "88110": [
            {"questionId": 1, "category": "Satış Kapama", "duration": 30},
            {"questionId": 2, "category": "Satış Kapama", "duration": 20},
            {"questionId": 3, "category": "Satış Kapama", "duration": None},
        ]
    },
}

TEST_ACTIVITY = {
    "activityId": 17199,
    "activityType": "TEST",
    "activityTypeId": 2,
    "activitySubType": "EXAM",
    "activitySubTypeId": 1,
    "timeLimit": 35,
    "title": "Final Sınavı_3",
    "icon": "https://cdn-test.mobixa.ai/mobileIcons/Questions Answers.webp",
    "questionCount": 1,
    "questions": {"93120": [{"questionId": 1, "category": "", "duration": 20}]},
}

INCOMPLETE_ACTIVITY = {
    "activityType": "GAME",
    "activitySubType": "DEEPLEARN",
    "title": "Eksik aktivite",
}


def test_build_catalog_row_derives_topic_and_duration_from_questions():
    row = build_catalog_row(GAME_ACTIVITY, "sample.json")
    assert row["id"] == "17197"
    assert row["title"] == "Satış Bombası"
    assert row["activity_type"] == "GAME"
    assert row["activity_sub_type"] == "DEEPLEARN"
    assert row["topic"] == "Satış Kapama"
    assert row["duration_minutes"] == 1  # (30+20)s / 60 -> rounds to 1
    assert row["question_count"] == 3


def test_build_catalog_row_uses_time_limit_when_present():
    row = build_catalog_row(TEST_ACTIVITY, "sample.json")
    assert row["duration_minutes"] == 35
    assert row["question_count"] == 1


def test_build_catalog_row_returns_none_for_incomplete_activity(capsys):
    row = build_catalog_row(INCOMPLETE_ACTIVITY, "sample.json")
    assert row is None
    captured = capsys.readouterr()
    assert "atlandı" in captured.out


def test_build_catalog_from_directory(tmp_path: Path):
    (tmp_path / "a.json").write_text(json.dumps(GAME_ACTIVITY), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps(TEST_ACTIVITY), encoding="utf-8")
    (tmp_path / "c_broken.json").write_text("{not valid json", encoding="utf-8")

    rows = build_catalog(tmp_path)

    assert [r["id"] for r in rows] == ["17197", "17199"]


def test_build_catalog_skips_duplicate_activity_ids(tmp_path: Path, capsys):
    (tmp_path / "a.json").write_text(json.dumps(GAME_ACTIVITY), encoding="utf-8")
    (tmp_path / "a_dup.json").write_text(json.dumps(GAME_ACTIVITY), encoding="utf-8")

    rows = build_catalog(tmp_path)

    assert len(rows) == 1
    captured = capsys.readouterr()
    assert "zaten katalogda" in captured.out
