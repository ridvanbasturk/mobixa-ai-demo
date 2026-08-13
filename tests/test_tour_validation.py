from schemas.tour_models import TourElement, validate_tour_decision
from services.tour_validation import (
    MAX_CONSECUTIVE_REPEATS,
    decision_signature,
    validate_decision_against_inventory,
)

INVENTORY = [
    TourElement(index=1, role="button", name="Turu Çek", key="a1_record", x=0, y=0, width=80, height=30),
    TourElement(index=2, role="text-input", name="Soru", key="a2_q", x=0, y=40, width=200, height=30),
    TourElement(
        index=3, role="button", name="Kapalı Buton", x=0, y=80, width=80, height=30, enabled=False
    ),
]


def _decide(**overrides):
    data = {"action": "click", "element_index": 1, "narration": "Butona basıyorum."}
    data.update(overrides)
    return validate_tour_decision(data)


def test_valid_click_passes_and_resolves_element():
    result = validate_decision_against_inventory(_decide(), INVENTORY)
    assert result["valid"] is True
    assert result["errors"] == []
    assert result["element"].name == "Turu Çek"


def test_hallucinated_element_index_is_rejected():
    # Ajanın en tehlikeli hatası: ekranda olmayan bir öğeye tıklamak ->
    # imleç boşluğa gider, video çöp olur.
    result = validate_decision_against_inventory(_decide(element_index=99), INVENTORY)
    assert result["valid"] is False
    assert any("böyle bir öğe yok" in error for error in result["errors"])
    assert result["element"] is None


def test_missing_element_index_for_click_is_rejected():
    result = validate_decision_against_inventory(_decide(element_index=None), INVENTORY)
    assert result["valid"] is False
    assert any("element_index gerektirir" in error for error in result["errors"])


def test_disabled_element_is_rejected():
    result = validate_decision_against_inventory(_decide(element_index=3), INVENTORY)
    assert result["valid"] is False
    assert any("devre dışı" in error for error in result["errors"])


def test_type_without_text_is_rejected():
    decision = _decide(action="type", element_index=2, text="  ")
    result = validate_decision_against_inventory(decision, INVENTORY)
    assert result["valid"] is False
    assert any("'text' alanı" in error for error in result["errors"])


def test_type_with_text_passes():
    decision = _decide(action="type", element_index=2, text="Şifremi unuttum")
    result = validate_decision_against_inventory(decision, INVENTORY)
    assert result["valid"] is True


def test_wait_and_done_need_no_element():
    for action in ("wait", "done"):
        decision = _decide(action=action, element_index=None)
        result = validate_decision_against_inventory(decision, INVENTORY)
        assert result["valid"] is True, action


def test_signature_uses_element_identity_not_positional_index():
    # REGRESYON: imza `element_index` üzerinden kurulursa, sayfada bir öğe
    # belirip kaybolunca tüm numaralar kayar ve ajan aynı butona basmaya
    # devam etse bile döngü fark edilmez. Gerçek bir kayıtta ajan bu yüzden
    # aynı radyo butonuna 8 kez bastı.
    decision = _decide(element_index=1)
    same_element_different_index = TourElement(
        index=7, role="button", name="Turu Çek", key="a1_record", x=0, y=0, width=80, height=30
    )
    assert decision_signature(decision, INVENTORY[0]) == decision_signature(
        decision, same_element_different_index
    )


def test_signature_falls_back_to_name_when_no_key():
    element = TourElement(index=1, role="button", name="Adsız", x=0, y=0, width=10, height=10)
    assert "Adsız" in decision_signature(_decide(), element)


def test_loop_detection_stops_repeated_identical_steps():
    decision = _decide()
    result_first = validate_decision_against_inventory(decision, INVENTORY)
    recent = [result_first["signature"]] * MAX_CONSECUTIVE_REPEATS
    result = validate_decision_against_inventory(decision, INVENTORY, recent_signatures=recent)
    assert result["valid"] is False
    assert any("zaten" in error and "kez arka arkaya" in error for error in result["errors"])


def test_loop_error_tells_the_agent_what_to_do_instead():
    # Hata mesajı ajana geri bildirilir; yalnızca "hata" demek yetmez, ne
    # yapması gerektiğini de söylemeli.
    decision = _decide()
    signature = validate_decision_against_inventory(decision, INVENTORY)["signature"]
    result = validate_decision_against_inventory(
        decision, INVENTORY, recent_signatures=[signature] * MAX_CONSECUTIVE_REPEATS
    )
    joined = " ".join(result["errors"])
    assert "ASIL eylemini" in joined or "done" in joined


def test_loop_detection_allows_repeat_below_threshold():
    decision = _decide()
    signature = validate_decision_against_inventory(decision, INVENTORY)["signature"]
    recent = [signature] * (MAX_CONSECUTIVE_REPEATS - 1)
    result = validate_decision_against_inventory(decision, INVENTORY, recent_signatures=recent)
    assert result["valid"] is True


def test_loop_detection_only_counts_consecutive_repeats():
    decision = _decide()
    signature = validate_decision_against_inventory(decision, INVENTORY)["signature"]
    # Araya farklı bir adım girmişse sayaç sıfırlanır.
    recent = [signature, signature, "click:baska_oge", signature]
    result = validate_decision_against_inventory(decision, INVENTORY, recent_signatures=recent)
    assert result["valid"] is True


def test_empty_inventory_rejects_element_actions():
    result = validate_decision_against_inventory(_decide(), [])
    assert result["valid"] is False
