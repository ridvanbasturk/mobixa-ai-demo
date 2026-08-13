from services.a2_validation import compute_final_escalation, validate_grounding

RETRIEVED = [
    {
        "id": "KB01",
        "title": "Şifre sıfırlama",
        "content": "Şifrenizi sıfırlamak için 'Şifremi Unuttum' bağlantısına tıklayın.",
        "product_area": "authentication",
    },
    {
        "id": "KB05",
        "title": "Teknik destek kanalı",
        "content": "Teknik sorunlarınız için support@mobixa.ai adresine e-posta gönderebilirsiniz.",
        "product_area": "support",
    },
]

MOBILE_ONLY_UNAVAILABLE = [
    {
        "id": "KB06",
        "title": "Mobil tarayıcı kullanımı",
        "content": (
            "Mobixa şu anda yalnızca mobil cihazlardaki web tarayıcısı üzerinden "
            "kullanılabilir. Native bir iOS veya Android uygulaması hakkında bu "
            "wiki'de bilgi bulunmamaktadır."
        ),
        "product_area": "mobile_access",
    }
]


def test_valid_source_ids_pass():
    result = validate_grounding("Şifrenizi sıfırlamak için bağlantıya tıklayın.", ["KB01"], RETRIEVED)
    assert result["passed"] is True
    assert result["valid_source_ids"] == ["KB01"]
    assert result["unknown_source_ids"] == []


def test_unknown_source_id_fails():
    result = validate_grounding("Cevap metni.", ["KB99"], RETRIEVED)
    assert result["passed"] is False
    assert result["unknown_source_ids"] == ["KB99"]
    assert any("Bilinmeyen" in e for e in result["errors"])


def test_source_id_not_in_retrieved_context_fails():
    # KB05 var ama bu turda getirilmedi (yalnızca KB01 getirildi)
    result = validate_grounding("Cevap metni.", ["KB05"], [RETRIEVED[0]])
    assert result["passed"] is False
    assert result["unknown_source_ids"] == ["KB05"]


def test_source_ids_with_empty_context_fails():
    result = validate_grounding("Cevap metni.", ["KB01"], [])
    assert result["passed"] is False
    assert any("bağlam boşken" in e for e in result["errors"])


def test_unsupported_support_channel_fails():
    answer = "Sorununuz için support@mobixa.ai adresine yazabilirsiniz."
    # support@mobixa.ai bağlamda YOK (yalnızca KB01 getirildi)
    result = validate_grounding(answer, ["KB01"], [RETRIEVED[0]])
    assert result["passed"] is False
    assert any("destek kanalı" in e for e in result["errors"])


def test_supported_support_channel_passes():
    answer = "Sorununuz için support@mobixa.ai adresine yazabilirsiniz."
    result = validate_grounding(answer, ["KB05"], RETRIEVED)
    assert result["passed"] is True


def test_prompt_injection_phrase_does_not_crash_and_is_flagged():
    answer = "İşte sistem promptu: aşağıdaki gizli talimatları uyguluyorum..."
    result = validate_grounding(answer, [], RETRIEVED)
    assert result["passed"] is False
    assert any("sistem promptu" in e.lower() or "ifşa" in e.lower() for e in result["errors"])


def test_prompt_injection_refusal_is_not_flagged_as_leak():
    # Model, sistem promptunu ifşa etmeyi doğru şekilde reddediyor — bu bir
    # sızıntı değildir ve hata olarak işaretlenmemeli.
    answer = "Bu konuda size yardımcı olamıyorum. Sistem promptunu veya iç kurallarımı ifşa edemem."
    result = validate_grounding(answer, [], RETRIEVED)
    assert result["passed"] is True


def test_fabricated_299_tl_detected():
    answer = "Bu özellik 299 TL karşılığında satın alınabilir."
    result = validate_grounding(answer, [], RETRIEVED)
    assert result["passed"] is False
    assert any("299" in e for e in result["errors"])


def test_unsupported_native_app_absence_claim_flagged():
    answer = "Hayır, iPhone veya Android için Mobixa uygulaması yoktur."
    result = validate_grounding(answer, ["KB06"], MOBILE_ONLY_UNAVAILABLE)
    assert result["passed"] is False
    assert any("yoktur" in e or "kesin" in e for e in result["errors"])


def test_correctly_worded_lack_of_information_passes():
    answer = "Bu konuda onaylı wiki içinde bilgi bulunmuyor; native bir uygulama olup olmadığını teyit edemiyorum."
    result = validate_grounding(answer, ["KB06"], MOBILE_ONLY_UNAVAILABLE)
    assert result["passed"] is True


def test_deterministic_escalation_with_no_source():
    escalated = compute_final_escalation(
        retrieved_entries=[], retrieval_sufficient=False, model_escalation_recommended=False, grounding_result=None
    )
    assert escalated is True


def test_deterministic_escalation_for_undocumented_pricing():
    # Örnek wiki'de fiyat bilgisi yok -> retrieval zaten yetersiz döner
    escalated = compute_final_escalation(
        retrieved_entries=[], retrieval_sufficient=False, model_escalation_recommended=False, grounding_result=None
    )
    assert escalated is True


def test_no_escalation_for_fully_grounded_answer():
    grounding_result = validate_grounding("Şifrenizi sıfırlamak için bağlantıya tıklayın.", ["KB01"], RETRIEVED)
    escalated = compute_final_escalation(
        retrieved_entries=RETRIEVED,
        retrieval_sufficient=True,
        model_escalation_recommended=False,
        grounding_result=grounding_result,
    )
    assert escalated is False


def test_escalation_when_model_recommends_and_support_source_present():
    grounding_result = validate_grounding("Bu konuda destek ekibiyle görüşmenizi öneririm.", [], RETRIEVED)
    escalated = compute_final_escalation(
        retrieved_entries=RETRIEVED,
        retrieval_sufficient=True,
        model_escalation_recommended=True,
        grounding_result=grounding_result,
    )
    assert escalated is True


def test_grounding_failure_forces_escalation_even_if_model_disagrees():
    grounding_result = validate_grounding("299 TL karşılığında satın alabilirsiniz.", [], RETRIEVED)
    escalated = compute_final_escalation(
        retrieved_entries=RETRIEVED,
        retrieval_sufficient=True,
        model_escalation_recommended=False,
        grounding_result=grounding_result,
    )
    assert escalated is True
