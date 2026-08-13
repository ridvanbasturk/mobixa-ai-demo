"""A1 storyboard'u için deterministik iş kuralı doğrulaması.

Model çıktısı her zaman gösterilir; bu modül yalnızca kaynak proje
ekranlarıyla tutarlılığı (sıra, en az bir kez kullanım, toplam süre,
requires_review kullanımı) ve kaynak notunda bulunmayan kesin sonuç
ifadelerini (ör. "Yayınlandı") deterministik olarak kontrol eden bir
doğrulama raporu (errors/warnings) üretir.

Faz 4C: Aynı ekran görüntüsünün (image_id) birden fazla sahnede (alt sahne
genişletmesi) kullanılabilmesi için "her image_id tam olarak bir kez
kullanılmalı" kuralı KALDIRILDI. Yerine: her kaynak ekran, kullanıcı açıkça
hariç tutmadığı sürece EN AZ bir kez kullanılmalı; image_id tekrarına izin
verilir; her scene_id benzersiz olmalı; her sahne var olan bir image_id'ye
referans vermeli.

Girdi, C1'in `validate_business_rules` fonksiyonuyla aynı desende, ham
dict/sözlük yapısı (Pydantic modeli değil) kabul eder; böylece Pydantic
şemasının zaten reddedeceği durumlar dahi deterministik katman düzeyinde
bağımsız olarak test edilebilir.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set

from schemas.a1_project_models import TutorialProject

MAX_ON_SCREEN_TEXT_LENGTH = 40

# Kaynak notta açıkça bulunmayan, kesin bir sonucun gerçekleştiğini iddia
# eden ifadeler. Normalize edilmiş (Türkçe-farkında, büyük/küçük harf
# duyarsız) eşleştirme ile aranır.
UNSUPPORTED_CLAIM_PHRASES = [
    "yayınlandı",
    "başarıyla oluşturuldu",
    "tamamlandı",
    "kaydedildi",
    "aktiviteler eklendi",
]


def _normalize_tr(text: str) -> str:
    """Türkçe-farkındalıklı, büyük/küçük harf duyarsız normalize eder."""
    return text.replace("İ", "i").replace("I", "ı").casefold()


def validate_storyboard_business_rules(
    storyboard: Dict,
    project: TutorialProject,
    working_mode: str,
    excluded_image_ids: Optional[Set[str]] = None,
) -> Dict:
    """Storyboard'u (dict) kaynak proje ekranlarına göre deterministik olarak doğrular.

    excluded_image_ids: kullanıcının storyboard'a bilerek dahil ETMEDİĞİ
    kaynak ekranlar (ör. "bu ekranı atla" seçimi). Bu kümedeki ekranlar
    "kullanılmayan kaynak ekran" hatasından muaf tutulur.
    """
    errors: List[str] = []
    warnings: List[str] = []

    scenes: List[Dict] = storyboard["scenes"]
    excluded_image_ids = excluded_image_ids or set()

    source_screens = sorted(project.screens, key=lambda s: s.order)
    source_ids_ordered = [s.image_id for s in source_screens]
    source_id_set = set(source_ids_ordered)
    note_by_id = {s.image_id: s.note for s in source_screens}

    scenes_sorted = sorted(scenes, key=lambda sc: sc["scene_number"])
    scene_ids_ordered = [sc["image_id"] for sc in scenes_sorted]

    unknown_ids = sorted({iid for iid in scene_ids_ordered if iid not in source_id_set})
    if unknown_ids:
        errors.append(f"Bilinmeyen image_id kullanılmış: {', '.join(unknown_ids)}")

    used_counts: Dict[str, int] = {}
    for iid in scene_ids_ordered:
        used_counts[iid] = used_counts.get(iid, 0) + 1

    # Faz 4C: her kaynak ekran EN AZ bir kez kullanılmalı (açıkça hariç
    # tutulmadığı sürece); tekrarlanan image_id artık bir hata değildir.
    missing_ids = [
        iid
        for iid in source_ids_ordered
        if used_counts.get(iid, 0) == 0 and iid not in excluded_image_ids
    ]
    if missing_ids:
        errors.append(f"Kullanılmayan kaynak ekran(lar): {', '.join(missing_ids)}")

    # Sıra kontrolü: her image_id'nin İLK göründüğü konumun sırası, kaynak
    # ekran sırasıyla tutarlı olmalı. Aynı image_id'ye ait sonraki (alt sahne)
    # geçişleri bu kontrolü etkilemez — böylece bir ekranın ardışık birden
    # fazla alt sahneye bölünmesi sıra ihlali sayılmaz.
    first_occurrence_order: List[str] = []
    seen: Set[str] = set()
    for iid in scene_ids_ordered:
        if iid in source_id_set and iid not in seen:
            first_occurrence_order.append(iid)
            seen.add(iid)
    expected_order = [iid for iid in source_ids_ordered if used_counts.get(iid, 0) > 0]
    if first_occurrence_order != expected_order:
        errors.append("Kaynak ekran sırası korunmamış.")

    # scene_id: her sahne benzersiz, boş olmayan bir scene_id taşımalı.
    scene_ids = [sc.get("scene_id") for sc in scenes]
    if any(not sid or not str(sid).strip() for sid in scene_ids):
        errors.append("Her sahne benzersiz ve boş olmayan bir scene_id taşımalı.")
    elif len(scene_ids) != len(set(scene_ids)):
        errors.append("scene_id değerleri benzersiz olmalı.")

    scene_numbers = [sc["scene_number"] for sc in scenes]
    if len(scene_numbers) != len(set(scene_numbers)):
        errors.append("scene_number değerleri benzersiz olmalı.")
    elif sorted(scene_numbers) != list(range(1, len(scene_numbers) + 1)):
        errors.append("scene_number değerleri 1'den başlayarak ardışık olmalı.")

    calculated_total = sum(sc["duration_seconds"] for sc in scenes)
    if abs(storyboard["total_duration_seconds"] - calculated_total) > 1e-6:
        errors.append(
            f"Toplam süre tutarsız: model {storyboard['total_duration_seconds']} sn bildirdi, "
            f"sahnelerden hesaplanan toplam {calculated_total} sn"
        )

    any_requires_review = False
    for sc in scenes:
        image_id = sc["image_id"]

        if len(sc["on_screen_text"]) > MAX_ON_SCREEN_TEXT_LENGTH:
            errors.append(f"{image_id}: on_screen_text {MAX_ON_SCREEN_TEXT_LENGTH} karakteri aşıyor.")

        source_note = note_by_id.get(image_id)
        if source_note is None:
            # Bilinmeyen image_id zaten yukarıda raporlandı; kaynak notu yok.
            continue

        if working_mode == "safe" and sc["requires_review"]:
            errors.append(
                f"{image_id}: Güvenli modda requires_review=true kullanılamaz "
                "(yalnızca kullanıcı notunun yeniden yazımı beklenir, çıkarım yapılmamalı)."
            )

        if sc["requires_review"]:
            any_requires_review = True

        combined_text = " ".join([sc["narration"], sc["on_screen_text"], sc["highlight_description"]])
        normalized_combined = _normalize_tr(combined_text)
        normalized_note = _normalize_tr(source_note)
        for phrase in UNSUPPORTED_CLAIM_PHRASES:
            normalized_phrase = _normalize_tr(phrase)
            if normalized_phrase in normalized_combined and normalized_phrase not in normalized_note:
                warnings.append(
                    f"{image_id}: Kaynak notta bulunmayan kesin sonuç ifadesi tespit edildi: \"{phrase}\""
                )

    if working_mode == "assisted" and not any_requires_review:
        warnings.append(
            "AI Destekli modda hiçbir sahne requires_review=true olarak işaretlenmedi; "
            "model ek bilgi eklediyse bu durum gözden kaçmış olabilir."
        )

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "scenes_validated": len(scenes),
    }
