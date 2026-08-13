import pytest
from pydantic import ValidationError

from schemas.a2_models import validate_a2_output

VALID_DATA = {
    "answer": "Şifrenizi sıfırlamak için giriş ekranındaki bağlantıya tıklayın.",
    "source_ids": ["KB01"],
    "escalation_recommended": False,
    "support_reason": "Soru onaylı wiki içeriğiyle tam olarak yanıtlandı.",
}


def test_valid_output_passes():
    result = validate_a2_output(dict(VALID_DATA))
    assert result.answer.startswith("Şifrenizi")
    assert result.source_ids == ["KB01"]


def test_blank_answer_fails():
    data = dict(VALID_DATA, answer="   ")
    with pytest.raises(ValidationError):
        validate_a2_output(data)


def test_blank_support_reason_fails():
    data = dict(VALID_DATA, support_reason="")
    with pytest.raises(ValidationError):
        validate_a2_output(data)


def test_duplicate_source_ids_fail():
    data = dict(VALID_DATA, source_ids=["KB01", "KB01"])
    with pytest.raises(ValidationError):
        validate_a2_output(data)


def test_non_boolean_escalation_recommended_fails():
    data = dict(VALID_DATA, escalation_recommended="evet")
    with pytest.raises(ValidationError):
        validate_a2_output(data)


def test_empty_source_ids_allowed():
    data = dict(VALID_DATA, source_ids=[])
    result = validate_a2_output(data)
    assert result.source_ids == []
