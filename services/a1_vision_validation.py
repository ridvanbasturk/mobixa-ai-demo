"""A1 AI Görsel Analiz Modu için deterministik doğrulama.

Model çıktısı (VisionSceneResult / GroundedSceneResult) her zaman gösterilir;
bu modül yalnızca istenen ekranla eşleşme, vurgu koordinatlarının görsel
sınırları içinde kalması, düşük güven skoru, eksik hedef ve desteklenmeyen
kesin sonuç iddiaları gibi durumları deterministik olarak işaretleyen bir
doğrulama raporu (errors/warnings) üretir. Hiçbir sonucu gizlemez.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from schemas.a1_knowledge_models import APPROVED_STATUS, ProductKnowledgeBase
from schemas.a1_scene_expansion_models import SceneExpansionResult
from schemas.a1_vision_models import GroundedSceneResult, VisionSceneResult, VisualObservation

LOW_CONFIDENCE_THRESHOLD = 0.65

ACTIONS_REQUIRING_TARGET = {"click", "select", "enter_text"}

PLACEHOLDER_TARGET_VALUES = {"bilinmiyor", "belirsiz", "yok", "-", "unknown", "n/a", "none"}

# Ekran görüntüsü yalnızca statik bir anı yansıtır; model bu ifadelerle bir
# eylemin SONUÇLANDIĞINI iddia ediyorsa bu deterministik olarak işaretlenir
# (hata değil, uyarı — ekran görüntüsü gerçekten bir sonuç ekranı olabilir).
UNSUPPORTED_CLAIM_PHRASES = [
    "yayınlandı",
    "başarıyla oluşturuldu",
    "tamamlandı",
    "kaydedildi",
    "aktiviteler eklendi",
    "başarıyla eklendi",
]


def _normalize_tr(text: str) -> str:
    """Türkçe-farkındalıklı, büyük/küçük harf duyarsız normalize eder."""
    return text.replace("İ", "i").replace("I", "ı").casefold()


def validate_vision_result(result: VisionSceneResult, requested_image_id: str) -> Dict:
    """Tek bir ekranın görsel analiz sonucunu deterministik olarak doğrular."""
    errors: List[str] = []
    warnings: List[str] = []

    if result.image_id != requested_image_id:
        errors.append(
            f"Model yanıtındaki image_id ('{result.image_id}') istenen ekranla "
            f"('{requested_image_id}') eşleşmiyor."
        )

    if result.highlight_rect is not None:
        rect = result.highlight_rect
        if (
            rect.x < 0
            or rect.y < 0
            or rect.x + rect.width > 1.0 + 1e-6
            or rect.y + rect.height > 1.0 + 1e-6
        ):
            errors.append(f"{result.image_id}: highlight_rect görsel sınırlarının dışına taşıyor.")

    if result.action_type in ACTIONS_REQUIRING_TARGET and not result.primary_target.strip():
        errors.append(f"{result.image_id}: '{result.action_type}' eylemi için primary_target gereklidir.")

    if result.action_type == "click" and result.highlight_rect is None:
        warnings.append(
            f"{result.image_id}: 'click' eylemi için vurgu (highlight) dikdörtgeni belirtilmemiş."
        )

    if result.confidence < LOW_CONFIDENCE_THRESHOLD:
        warnings.append(
            f"{result.image_id}: Güven skoru düşük ({result.confidence:.2f}), gözden geçirilmeli."
        )

    if not result.requires_review:
        warnings.append(
            f"{result.image_id}: requires_review=false olarak işaretlenmiş; tüm AI görsel "
            "analiz sonuçları gözden geçirme gerektirir."
        )

    if result.primary_target.strip().lower() in PLACEHOLDER_TARGET_VALUES:
        warnings.append(
            f"{result.image_id}: primary_target belirsiz/placeholder görünüyor "
            f"('{result.primary_target}')."
        )

    combined_text = " ".join([result.narration, result.instruction_text, result.on_screen_text])
    normalized_combined = _normalize_tr(combined_text)
    for phrase in UNSUPPORTED_CLAIM_PHRASES:
        if _normalize_tr(phrase) in normalized_combined:
            warnings.append(
                f"{result.image_id}: Kesin sonuç ifadesi tespit edildi (\"{phrase}\") — ekran "
                "görüntüsü bunu doğrulamıyor olabilir."
            )

    return {"passed": len(errors) == 0, "errors": errors, "warnings": warnings}


# --- Faz 4B: grounded (bilgi tabanına bağlı) sonuç doğrulaması ----------------

SCREEN_MATCH_WARNING_THRESHOLD = 0.65
NO_MATCH_WARNING = "Ekran bilgi tabanıyla güvenilir biçimde eşleştirilemedi."
TARGET_CONFLICT_WARNING_TEMPLATE = (
    "Görselde tespit edilen hedef ile bilgi tabanındaki beklenen öğe tam olarak eşleşmiyor."
)


def _is_near_duplicate_text(a: str, b: str) -> bool:
    """İki metnin (Türkçe-farkındalıklı normalize edilerek) aynı ya da
    birinin diğerini kapsayacak kadar yakın olup olmadığını kontrol eder."""
    norm_a = _normalize_tr(a or "").strip()
    norm_b = _normalize_tr(b or "").strip()
    if not norm_a or not norm_b:
        return False
    if norm_a == norm_b:
        return True
    return norm_a in norm_b or norm_b in norm_a


def _parse_grounding_source_id(source_id: str) -> Optional[tuple]:
    """'screen:X', 'element:X' veya 'workflow:X:step:N' biçimini ayrıştırır."""
    parts = source_id.split(":")
    if len(parts) == 2 and parts[0] in {"screen", "element"}:
        return (parts[0], parts[1])
    if len(parts) == 4 and parts[0] == "workflow" and parts[2] == "step":
        try:
            return ("workflow", parts[1], int(parts[3]))
        except ValueError:
            return None
    return None


def validate_grounding_source_ids(source_ids: List[str], kb: ProductKnowledgeBase) -> List[str]:
    """grounding_source_ids listesindeki her kaynağın onaylı bilgi tabanında var olduğunu doğrular.

    Geçersiz/tanınmayan her kaynak için bir hata mesajı döner (boş liste = tümü geçerli).
    """
    valid_screen_ids = {s.screen_id for s in kb.screens if s.status == APPROVED_STATUS}
    valid_element_ids = {e.element_id for e in kb.ui_elements if e.status == APPROVED_STATUS}
    valid_workflow_ids = {w.workflow_id for w in kb.workflows if w.status == APPROVED_STATUS}

    errors: List[str] = []
    for source_id in source_ids:
        parsed = _parse_grounding_source_id(source_id)
        if parsed is None:
            errors.append(f"Tanınmayan grounding kaynağı biçimi: '{source_id}'")
            continue
        kind = parsed[0]
        if kind == "screen" and parsed[1] not in valid_screen_ids:
            errors.append(f"Geçersiz grounding kaynağı: '{source_id}' (onaylı ekran bulunamadı)")
        elif kind == "element" and parsed[1] not in valid_element_ids:
            errors.append(f"Geçersiz grounding kaynağı: '{source_id}' (onaylı arayüz öğesi bulunamadı)")
        elif kind == "workflow" and parsed[1] not in valid_workflow_ids:
            errors.append(f"Geçersiz grounding kaynağı: '{source_id}' (onaylı iş akışı bulunamadı)")

    return errors


def validate_grounded_result(
    result: GroundedSceneResult,
    requested_image_id: str,
    kb: ProductKnowledgeBase,
    observation: Optional[VisualObservation] = None,
    expected_screen_id: Optional[str] = None,
) -> Dict:
    """Grounded (bilgi tabanına bağlı) sahne sonucunu deterministik olarak doğrular.

    matched_screen_id/target_element_id/grounding_source_ids alanları
    `run_grounded_vision_analysis` tarafından zaten deterministik olarak
    hesaplanmıştır; bu fonksiyon yalnızca bunların onaylı bilgi tabanıyla
    hâlâ tutarlı olduğunu (savunma katmanı) ve anlamsal uyarıları kontrol
    eder.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if result.image_id != requested_image_id:
        errors.append(
            f"Model yanıtındaki image_id ('{result.image_id}') istenen ekranla "
            f"('{requested_image_id}') eşleşmiyor."
        )

    if result.matched_screen_id is not None:
        valid_screen_ids = {s.screen_id for s in kb.screens if s.status == APPROVED_STATUS}
        if result.matched_screen_id not in valid_screen_ids:
            errors.append(f"matched_screen_id '{result.matched_screen_id}' onaylı bilgi tabanında bulunamadı.")
    else:
        warnings.append(NO_MATCH_WARNING)

    if result.target_element_id is not None:
        screen_element_ids = set()
        if result.matched_screen_id is not None:
            screen_element_ids = {
                e.element_id
                for e in kb.ui_elements
                if e.screen_id == result.matched_screen_id and e.status == APPROVED_STATUS
            }
        if result.target_element_id not in screen_element_ids:
            errors.append(
                f"target_element_id '{result.target_element_id}' eşleşen ekrana "
                f"('{result.matched_screen_id}') ait değil."
            )
    elif result.action_type in ACTIONS_REQUIRING_TARGET:
        warnings.append(
            f"{result.image_id}: '{result.action_type}' eylemi için onaylı bir arayüz öğesi eşleşmedi."
        )

    warnings.extend(validate_grounding_source_ids(result.grounding_source_ids, kb))

    if expected_screen_id is not None and result.matched_screen_id is not None and result.matched_screen_id != expected_screen_id:
        warnings.append(
            f"Eşleşen ekran ('{result.matched_screen_id}') beklenen iş akışı adımıyla "
            f"('{expected_screen_id}') uyuşmuyor; sıra çakışması olabilir."
        )

    if result.screen_match_score and result.screen_match_score < SCREEN_MATCH_WARNING_THRESHOLD:
        warnings.append(f"{result.image_id}: Ekran eşleşme skoru düşük ({result.screen_match_score:.2f}).")

    if result.confidence < LOW_CONFIDENCE_THRESHOLD:
        warnings.append(f"{result.image_id}: Güven skoru düşük ({result.confidence:.2f}), gözden geçirilmeli.")

    if not result.requires_review:
        warnings.append(
            f"{result.image_id}: requires_review=false olarak işaretlenmiş; tüm AI görsel "
            "analiz sonuçları gözden geçirme gerektirir."
        )

    # Görsel gözlem ile grounded sonuç arasındaki hedef çakışması.
    if observation is not None and result.target_element_id is not None:
        matched_element = next(
            (e for e in kb.ui_elements if e.element_id == result.target_element_id),
            None,
        )
        if matched_element is not None and not _is_near_duplicate_text(
            observation.possible_primary_target, matched_element.visible_label
        ):
            warnings.append(TARGET_CONFLICT_WARNING_TEMPLATE)

    # Kullanılmaması gereken (discouraged) terminoloji.
    combined_text = " ".join([result.narration, result.instruction_text, result.on_screen_text, result.scene_title])
    normalized_combined = _normalize_tr(combined_text)
    for term in kb.terminology:
        for avoided in term.avoid:
            if _normalize_tr(avoided) in normalized_combined:
                warnings.append(
                    f"Kullanılmaması gereken terim tespit edildi: \"{avoided}\" "
                    f"(onaylı terim: \"{term.canonical}\")."
                )

    for phrase in UNSUPPORTED_CLAIM_PHRASES:
        if _normalize_tr(phrase) in normalized_combined:
            warnings.append(
                f"{result.image_id}: Kesin sonuç ifadesi tespit edildi (\"{phrase}\") — ekran "
                "görüntüsü bunu doğrulamıyor olabilir."
            )

    return {"passed": len(errors) == 0, "errors": errors, "warnings": warnings}


# --- Faz 4C: alt sahne (sub-scene) genişletmesi doğrulaması -------------------


def validate_scene_expansion(
    result: SceneExpansionResult,
    matched_screen_id: str,
    kb: ProductKnowledgeBase,
) -> Dict:
    """Bir ekranın alt sahnelere genişletilmiş sonucunu deterministik olarak doğrular.

    sub_scene_key benzersizliği ve en fazla 4 alt sahne kuralı zaten Pydantic
    şemasında (schemas/a1_scene_expansion_models.py) uygulanır; bu fonksiyon
    yalnızca bilgi tabanına dayalı (KB'ye özgü) kontrolleri yapar:
    target_element_id'nin eşleşen ekrana ait olması, grounding_source_ids
    geçerliliği, tekrarlanan hedef uyarısı, eylem gerektiren sahnelerde hedef
    zorunluluğu, kaçınılması gereken terminoloji ve desteklenmeyen kesin
    sonuç iddiaları.
    """
    errors: List[str] = []
    warnings: List[str] = []

    screen_element_ids = {
        e.element_id for e in kb.ui_elements if e.screen_id == matched_screen_id and e.status == APPROVED_STATUS
    }

    target_element_ids_used: List[str] = []
    for sub_scene in result.sub_scenes:
        if sub_scene.target_element_id is not None:
            if sub_scene.target_element_id not in screen_element_ids:
                errors.append(
                    f"{sub_scene.sub_scene_key}: target_element_id '{sub_scene.target_element_id}' "
                    f"eşleşen ekrana ('{matched_screen_id}') ait değil."
                )
            target_element_ids_used.append(sub_scene.target_element_id)
        elif sub_scene.action_type in ACTIONS_REQUIRING_TARGET:
            warnings.append(
                f"{sub_scene.sub_scene_key}: '{sub_scene.action_type}' eylemi için onaylı bir "
                "arayüz öğesi eşleşmedi."
            )

        warnings.extend(
            f"{sub_scene.sub_scene_key}: {w}"
            for w in validate_grounding_source_ids(sub_scene.grounding_source_ids, kb)
        )

        if not sub_scene.requires_review:
            warnings.append(
                f"{sub_scene.sub_scene_key}: requires_review=false olarak işaretlenmiş; tüm "
                "AI tarafından üretilen alt sahneler gözden geçirme gerektirir."
            )

        combined_text = " ".join(
            [sub_scene.narration, sub_scene.instruction_text, sub_scene.on_screen_text, sub_scene.scene_title]
        )
        normalized_sub_combined = _normalize_tr(combined_text)
        for term in kb.terminology:
            for avoided in term.avoid:
                if _normalize_tr(avoided) in normalized_sub_combined:
                    warnings.append(
                        f"{sub_scene.sub_scene_key}: Kullanılmaması gereken terim tespit edildi: "
                        f"\"{avoided}\" (onaylı terim: \"{term.canonical}\")."
                    )
        for phrase in UNSUPPORTED_CLAIM_PHRASES:
            if _normalize_tr(phrase) in normalized_sub_combined:
                warnings.append(
                    f"{sub_scene.sub_scene_key}: Kesin sonuç ifadesi tespit edildi (\"{phrase}\") — "
                    "ekran görüntüsü bunu doğrulamıyor olabilir."
                )

    duplicated_targets = sorted(
        {tid for tid in target_element_ids_used if target_element_ids_used.count(tid) > 1}
    )
    if duplicated_targets:
        warnings.append(
            "Aynı arayüz öğesi birden fazla alt sahnede hedef olarak kullanılmış: "
            + ", ".join(duplicated_targets)
        )

    return {"passed": len(errors) == 0, "errors": errors, "warnings": warnings}
