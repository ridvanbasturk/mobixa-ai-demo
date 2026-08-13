"""A1 Ürün Bilgi Tabanı için yerel, deterministik yükleme ve eşleştirme.

Hiçbir vektör veritabanı, embedding, OpenSearch, Bedrock Knowledge Bases
veya başka bir ücretli servis KULLANMAZ; yalnızca yerel JSON dosyalarını
okur ve ağırlıklı, açıklanabilir (explainable) bir puanlama ile görünür
etiket eşleştirmesi yapar. Bu modül Streamlit'ten bağımsızdır.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

from schemas.a1_knowledge_models import (
    APPROVED_STATUS,
    KnowledgeScreen,
    KnowledgeUIElement,
    KnowledgeWorkflow,
    ProductKnowledgeBase,
    WorkflowStep,
    validate_knowledge_base,
)

DEFAULT_KB_DIR = Path(__file__).resolve().parent.parent / "sample_data" / "a1" / "knowledge_base"
DEFAULT_MATCH_THRESHOLD = 0.65
AMBIGUITY_MARGIN = 0.05

# Ekran eşleştirme skorunun bileşen ağırlıkları (toplamı 1.0). Açıklanabilir
# olması için her bileşen ayrı ayrı hesaplanır ve nihai skor bunların
# ağırlıklı toplamıdır. Kesin görünür-etiket eşleşmesi (exact_score) en
# güçlü sinyal olduğu için en yüksek ağırlığı taşır: tespit edilen tüm
# etiketlerin tek bir ekranda birebir bulunması, tek başına eşik değerini
# aşmaya yetecek şekilde tasarlanmıştır.
#
# Faz 4C: exact_score, eşleşen etiket sayısının TESPİT EDİLEN etiket
# sayısına oranı (precision) yerine, eşleşen etiket sayısının tespit edilen
# ve ekranın onaylı etiket sayısından KÜÇÜK OLANINA oranı (overlap
# coefficient / Szymkiewicz–Simpson katsayısı) olarak hesaplanır. Gerçek
# görsel analiz modelleri, KB'nin onaylı visible_labels listesinde yer
# almayan onlarca ek (alt menü, sayaç, dekoratif) etiket de bildirebilir;
# precision tabanlı ölçüm bu durumda doğru ekranı bile eşik altına
# düşürüyordu. Overlap coefficient, küçük/net sorgularda (precision testi)
# ve büyük/gürültülü gerçek tespitlerde (recall testi) aynı anda doğru
# sonuç verir; her iki tarafın da payda olarak KÜÇÜK olanı kullanılması
# sayesinde ne fazla ayrıntı ne de az ayrıntı cezalandırılır.
WEIGHT_EXACT_LABEL = 0.7
WEIGHT_TOKEN_OVERLAP = 0.1
WEIGHT_NAME_AREA = 0.05
WEIGHT_WORKFLOW_MEMBERSHIP = 0.1
WEIGHT_EXPECTED_ORDER = 0.05

# Hedef (target) arayüz öğesi eşleştirme ağırlıkları (toplamı 1.0).
WEIGHT_TARGET_EXACT = 0.7
WEIGHT_TARGET_TOKEN_OVERLAP = 0.3
DEFAULT_TARGET_MATCH_THRESHOLD = 0.5


class KnowledgeBaseLoadError(RuntimeError):
    """Bilgi tabanı dosyaları eksik, okunamaz veya JSON içeriği bozuksa fırlatılır."""


def _read_json_file(path: Path):
    if not path.exists():
        raise KnowledgeBaseLoadError(f"Bilgi tabanı dosyası bulunamadı: {path.name}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise KnowledgeBaseLoadError(f"Bilgi tabanı dosyası geçersiz JSON içeriyor ({path.name}): {exc}") from exc


def load_knowledge_base(kb_dir: Path = DEFAULT_KB_DIR) -> ProductKnowledgeBase:
    """screens.json / ui_elements.json / workflows.json / terminology.json dosyalarını okur ve doğrular."""
    screens_data = _read_json_file(kb_dir / "screens.json")
    ui_elements_data = _read_json_file(kb_dir / "ui_elements.json")
    workflows_data = _read_json_file(kb_dir / "workflows.json")
    terminology_data = _read_json_file(kb_dir / "terminology.json")

    combined = {
        "screens": screens_data,
        "ui_elements": ui_elements_data,
        "workflows": workflows_data,
        "terminology": terminology_data.get("approved_terms", []) if isinstance(terminology_data, dict) else [],
    }
    return validate_knowledge_base(combined)


# --- Basit erişimciler (yalnızca onaylı kayıtlar) ---------------------------


def get_screen(kb: ProductKnowledgeBase, screen_id: str) -> Optional[KnowledgeScreen]:
    for screen in kb.screens:
        if screen.screen_id == screen_id and screen.status == APPROVED_STATUS:
            return screen
    return None


def get_ui_elements_for_screen(kb: ProductKnowledgeBase, screen_id: str) -> List[KnowledgeUIElement]:
    return [e for e in kb.ui_elements if e.screen_id == screen_id and e.status == APPROVED_STATUS]


def get_workflow(kb: ProductKnowledgeBase, workflow_id: str) -> Optional[KnowledgeWorkflow]:
    for workflow in kb.workflows:
        if workflow.workflow_id == workflow_id and workflow.status == APPROVED_STATUS:
            return workflow
    return None


def get_workflow_step(kb: ProductKnowledgeBase, workflow_id: str, order: int) -> Optional[WorkflowStep]:
    workflow = get_workflow(kb, workflow_id)
    if workflow is None:
        return None
    for step in workflow.steps:
        if step.order == order:
            return step
    return None


def search_by_visible_labels(kb: ProductKnowledgeBase, labels: List[str]) -> List[KnowledgeScreen]:
    """En az bir etiketi eşleşen onaylı ekranları, eşleşme sayısına göre azalan sırada döner."""
    normalized_query = {_normalize_label(l) for l in labels if l and l.strip()}
    scored: List[tuple] = []
    for screen in kb.screens:
        if screen.status != APPROVED_STATUS:
            continue
        screen_labels_norm = {_normalize_label(l) for l in screen.visible_labels}
        overlap = normalized_query & screen_labels_norm
        if overlap:
            scored.append((len(overlap), screen))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [s for _, s in scored]


# --- Normalize/tokenize yardımcıları ----------------------------------------



# Anlam taşımayan, zararsız arayüz önekleri/biçimlendirme karakterleri.
# Faz 4C: gerçek Bedrock Mantle görsel analiz çıktılarında, modelin ekranda
# GERÇEKTEN gördüğü "+" işareti, madde imi veya tırnak varyasyonu gibi
# karakterleri birebir aktarması (ör. "+ Yeni Yolculuk Ekle") yüzünden
# aksi halde birebir eşleşecek onaylı etiketlerle ("Yeni Yolculuk Ekle")
# eşleşme skorunun eşik değerinin altında kalmasına neden oluyordu. Bu
# karakterlerin kaldırılması anlamlı hiçbir kelimeyi silmez; yalnızca
# dekoratif/biçimsel farkları giderir.
_LEADING_BULLET_PATTERN = re.compile(r"^[\s\+\-\*•●▪️›»<:]+")
_TRAILING_PUNCTUATION_PATTERN = re.compile(r"[\s:;\-–—<>»›]+$")
_TURKISH_APOSTROPHE_PATTERN = re.compile(r"[’ʼ`´]")


def _normalize_label(text: str) -> str:
    """Türkçe-farkındalıklı, büyük/küçük harf duyarsız, boşluk sadeleştirilmiş,
    zararsız önek/noktalama/madde imi farklarına karşı toleranslı normalize.

    Anlam taşıyan hiçbir kelime kaldırılmaz; yalnızca "+", madde imi, baştaki/
    sondaki noktalama, tekrarlı boşluk ve Türkçe kesme işareti (') varyantları
    (’, ʼ, `, ´) düz kesme işaretine indirgenir.
    """
    normalized = (text or "").replace("İ", "i").replace("I", "ı").casefold().strip()
    normalized = _TURKISH_APOSTROPHE_PATTERN.sub("'", normalized)
    normalized = _LEADING_BULLET_PATTERN.sub("", normalized)
    normalized = _TRAILING_PUNCTUATION_PATTERN.sub("", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _tokenize(text: str) -> Set[str]:
    normalized = _normalize_label(text)
    return set(re.findall(r"\w+", normalized, flags=re.UNICODE))


# --- Deterministik ekran eşleştirmesi ----------------------------------------


def match_screen(
    kb: ProductKnowledgeBase,
    detected_labels: List[str],
    workflow_id: Optional[str] = None,
    expected_order: Optional[int] = None,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> Dict:
    """Tespit edilen etiketleri onaylı ekranlarla ağırlıklı, açıklanabilir bir skorla eşleştirir.

    Hiçbir LLM kullanmaz. Skor eşik değerinin altındaysa matched_screen_id
    None döner (kesin bir eşleştirme yapılmaz).
    """
    warnings: List[str] = []
    cleaned_labels = [l for l in detected_labels if l and l.strip()]

    if not cleaned_labels:
        return {
            "matched_screen_id": None,
            "score": 0.0,
            "matched_labels": [],
            "candidate_screens": [],
            "warnings": ["Karşılaştırılacak etiket verilmedi."],
        }

    detected_norm_set = {_normalize_label(l) for l in cleaned_labels}
    detected_tokens: Set[str] = set()
    for l in cleaned_labels:
        detected_tokens |= _tokenize(l)

    expected_screen_id_for_step = None
    if workflow_id and expected_order is not None:
        step = get_workflow_step(kb, workflow_id, expected_order)
        if step is not None:
            expected_screen_id_for_step = step.screen_id

    candidates = []
    for screen in kb.screens:
        if screen.status != APPROVED_STATUS:
            continue

        screen_labels_norm = [_normalize_label(l) for l in screen.visible_labels]
        screen_label_set = set(screen_labels_norm)
        matched_norm = detected_norm_set & screen_label_set
        overlap_denominator = min(len(detected_norm_set), len(screen_label_set))
        exact_score = len(matched_norm) / overlap_denominator if overlap_denominator else 0.0

        screen_tokens: Set[str] = set()
        for l in screen_labels_norm:
            screen_tokens |= _tokenize(l)
        union_tokens = detected_tokens | screen_tokens
        token_overlap = len(detected_tokens & screen_tokens) / len(union_tokens) if union_tokens else 0.0

        name_area_tokens = _tokenize(screen.screen_name) | _tokenize(screen.product_area)
        name_area_score = 1.0 if (detected_tokens & name_area_tokens) else 0.0

        workflow_score = 1.0 if (workflow_id and workflow_id in screen.workflow_ids) else 0.0

        expected_order_score = (
            1.0
            if (expected_screen_id_for_step is not None and expected_screen_id_for_step == screen.screen_id)
            else 0.0
        )

        score = (
            WEIGHT_EXACT_LABEL * exact_score
            + WEIGHT_TOKEN_OVERLAP * token_overlap
            + WEIGHT_NAME_AREA * name_area_score
            + WEIGHT_WORKFLOW_MEMBERSHIP * workflow_score
            + WEIGHT_EXPECTED_ORDER * expected_order_score
        )

        matched_original_labels = sorted(
            {orig for orig in cleaned_labels if _normalize_label(orig) in matched_norm}
        )

        candidates.append(
            {
                "screen_id": screen.screen_id,
                "score": round(score, 4),
                "matched_labels": matched_original_labels,
            }
        )

    candidates.sort(key=lambda c: c["score"], reverse=True)

    if not candidates:
        return {
            "matched_screen_id": None,
            "score": 0.0,
            "matched_labels": [],
            "candidate_screens": [],
            "warnings": ["Onaylı ekran bulunamadı."],
        }

    best = candidates[0]
    matched_screen_id: Optional[str] = None
    if best["score"] >= threshold:
        matched_screen_id = best["screen_id"]
    else:
        warnings.append(
            f"En iyi eşleşme skoru ({best['score']:.2f}) eşik değerinin ({threshold:.2f}) "
            "altında; kesin bir ekran eşleşmesi yapılmadı."
        )

    if matched_screen_id is not None and len(candidates) > 1:
        second = candidates[1]
        if best["score"] - second["score"] < AMBIGUITY_MARGIN:
            warnings.append(
                f"'{best['screen_id']}' ve '{second['screen_id']}' skorları birbirine çok yakın "
                "({:.2f} / {:.2f}); eşleştirme belirsiz olabilir.".format(best["score"], second["score"])
            )

    return {
        "matched_screen_id": matched_screen_id,
        "score": best["score"],
        "matched_labels": best["matched_labels"],
        "candidate_screens": [{"screen_id": c["screen_id"], "score": c["score"]} for c in candidates[:5]],
        "warnings": warnings,
    }


# --- Deterministik hedef (target) öğe eşleştirmesi ---------------------------


def match_target_element(
    kb: ProductKnowledgeBase,
    screen_id: str,
    target_label: str,
    threshold: float = DEFAULT_TARGET_MATCH_THRESHOLD,
) -> Dict:
    """Görsel analizin önerdiği hedefi, eşleşen ekranın onaylı arayüz öğeleriyle karşılaştırır.

    Hiçbir LLM kullanmaz. Kesin etiket eşleşmesi ve normalize token
    örtüşmesine dayalı açıklanabilir bir skor üretir. Skor eşik değerinin
    altındaysa target_element_id None döner — hiçbir öğe uydurulmaz.
    """
    elements = get_ui_elements_for_screen(kb, screen_id)
    if not target_label or not target_label.strip():
        return {
            "target_element_id": None,
            "target_match_score": 0.0,
            "target_match_warnings": ["Karşılaştırılacak bir hedef etiketi verilmedi."],
        }
    if not elements:
        return {
            "target_element_id": None,
            "target_match_score": 0.0,
            "target_match_warnings": [f"'{screen_id}' ekranı için onaylı arayüz öğesi bulunamadı."],
        }

    normalized_target = _normalize_label(target_label)
    target_tokens = _tokenize(target_label)

    candidates = []
    for element in elements:
        normalized_label = _normalize_label(element.visible_label)
        exact_score = 1.0 if normalized_target == normalized_label else 0.0

        element_tokens = _tokenize(element.visible_label)
        union_tokens = target_tokens | element_tokens
        token_overlap = len(target_tokens & element_tokens) / len(union_tokens) if union_tokens else 0.0

        score = WEIGHT_TARGET_EXACT * exact_score + WEIGHT_TARGET_TOKEN_OVERLAP * token_overlap
        candidates.append((round(score, 4), element))

    candidates.sort(key=lambda t: t[0], reverse=True)
    best_score, best_element = candidates[0]

    if best_score >= threshold:
        return {"target_element_id": best_element.element_id, "target_match_score": best_score, "target_match_warnings": []}

    return {
        "target_element_id": None,
        "target_match_score": best_score,
        "target_match_warnings": [
            f"'{target_label}' onaylı arayüz öğeleriyle güvenilir biçimde eşleştirilemedi "
            f"(en iyi skor: {best_score:.2f})."
        ],
    }


# --- Grounding context --------------------------------------------------------


def build_grounding_context(
    kb: ProductKnowledgeBase,
    screen_id: str,
    workflow_id: Optional[str] = None,
    step_order: Optional[int] = None,
) -> Optional[Dict]:
    """Yalnızca ilgili ekranın, arayüz öğelerinin ve iş akışı adımının derli
    toplu bir özetini döner (Faz 4B'de modele gönderilecek). İlgisiz bilgi
    tabanı kayıtları dahil edilmez. Ekran onaylı değilse veya bulunamazsa
    None döner.
    """
    screen = get_screen(kb, screen_id)
    if screen is None:
        return None

    elements = get_ui_elements_for_screen(kb, screen_id)

    context: Dict = {
        "screen_id": screen.screen_id,
        "screen_name": screen.screen_name,
        "purpose": screen.purpose,
        "visible_labels": list(screen.visible_labels),
        "ui_elements": [
            {
                "visible_label": e.visible_label,
                "element_type": e.element_type,
                "purpose": e.purpose,
                "action_type": e.action_type,
            }
            for e in elements
        ],
        "product_version": screen.product_version,
        "terminology": [
            {"canonical": t.canonical, "alternatives": t.alternatives, "avoid": t.avoid} for t in kb.terminology
        ],
        "workflow": None,
        "current_step": None,
        "previous_step": None,
        "next_step": None,
    }

    if workflow_id:
        workflow = get_workflow(kb, workflow_id)
        if workflow is not None:
            context["workflow"] = {
                "workflow_id": workflow.workflow_id,
                "title": workflow.title,
                "purpose": workflow.purpose,
            }
            if step_order is not None:
                steps_by_order = {s.order: s for s in workflow.steps}
                current = steps_by_order.get(step_order)
                if current is not None:
                    context["current_step"] = {
                        "step_id": current.step_id,
                        "order": current.order,
                        "instruction": current.instruction,
                        "expected_next_screen_id": current.expected_next_screen_id,
                    }
                previous = steps_by_order.get(step_order - 1)
                if previous is not None:
                    context["previous_step"] = {
                        "step_id": previous.step_id,
                        "order": previous.order,
                        "instruction": previous.instruction,
                    }
                nxt = steps_by_order.get(step_order + 1)
                if nxt is not None:
                    context["next_step"] = {
                        "step_id": nxt.step_id,
                        "order": nxt.order,
                        "instruction": nxt.instruction,
                    }

    return context
