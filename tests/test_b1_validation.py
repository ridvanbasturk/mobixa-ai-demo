import pytest
from pydantic import ValidationError

from schemas.b1_models import validate_b1_output

VALID_QUESTION = {
    "question": "CIA üçgeninin unsurları nelerdir?",
    "options": ["Gizlilik, Bütünlük, Erişilebilirlik", "Hız, Güvenlik, Maliyet", "A, B, C", "X, Y, Z"],
    "correct_answer": 1,
    "explanation": "Metinde CIA üçgeni açıklanmıştır.",
    "source_quote": "CIA üçgeni (Confidentiality, Integrity, Availability)",
    "difficulty": "easy",
    "category": "Temel Kavramlar",
}


def make_data(questions, learning_cards=None, title="Test Başlık"):
    return {
        "title": title,
        "questions": questions,
        "learning_cards": learning_cards or [],
    }


def test_valid_output_passes():
    data = make_data([VALID_QUESTION])
    result = validate_b1_output(data, expected_question_count=1, expect_learning_cards=False)
    assert result.title == "Test Başlık"
    assert len(result.questions) == 1


def test_wrong_option_count_fails():
    bad_question = dict(VALID_QUESTION, options=["A", "B", "C"])
    data = make_data([bad_question])
    with pytest.raises(ValidationError):
        validate_b1_output(data, expected_question_count=1, expect_learning_cards=False)


def test_invalid_correct_answer_fails():
    bad_question = dict(VALID_QUESTION, correct_answer=5)
    data = make_data([bad_question])
    with pytest.raises(ValidationError):
        validate_b1_output(data, expected_question_count=1, expect_learning_cards=False)


def test_question_count_mismatch_fails():
    data = make_data([VALID_QUESTION])
    with pytest.raises(ValueError):
        validate_b1_output(data, expected_question_count=2, expect_learning_cards=False)


def test_duplicate_questions_fail():
    data = make_data([VALID_QUESTION, dict(VALID_QUESTION)])
    with pytest.raises(ValidationError):
        validate_b1_output(data, expected_question_count=2, expect_learning_cards=False)


def test_learning_cards_required_when_expected():
    data = make_data([VALID_QUESTION], learning_cards=[])
    with pytest.raises(ValueError):
        validate_b1_output(data, expected_question_count=1, expect_learning_cards=True)


def test_learning_cards_optional_when_not_expected():
    data = make_data([VALID_QUESTION], learning_cards=[])
    result = validate_b1_output(data, expected_question_count=1, expect_learning_cards=False)
    assert result.learning_cards == []
