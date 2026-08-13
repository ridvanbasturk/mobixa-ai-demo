"""A1 storyboard üretimi için model çağrısı orkestrasyonu ve saf yardımcılar.

Streamlit'ten bağımsızdır (a2_chat_service.py ile aynı desen); yalnızca
`run_storyboard_generation` gerçek bir Bedrock çağrısı yapar, geri kalanı
(prompt oluşturma, sahne yeniden sıralama, anlatım metni oluşturma, scene_id
göçü) saf Python'dur ve AWS bağlantısı olmadan test edilebilir.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Dict, List, Optional

from pydantic import ValidationError

from schemas.a1_project_models import TutorialProject
from schemas.a1_storyboard_models import Storyboard, validate_storyboard
from services.a1_storyboard_validation import validate_storyboard_business_rules
from services.bedrock_client import ModelCallResult, call_model


def build_storyboard_user_prompt(project: TutorialProject) -> str:
    """Modele yalnızca proje/sahne meta verisini gönderir; görsel içerik göndermez."""
    screens_payload = [
        {
            "image_id": s.image_id,
            "scene_label": s.scene_label,
            "note": s.note,
            "order": s.order,
        }
        for s in sorted(project.screens, key=lambda s: s.order)
    ]
    project_payload = {
        "title": project.title,
        "target_audience": project.target_audience,
        "tone": project.tone,
        "working_mode": project.working_mode,
        "screens": screens_payload,
    }
    return f"""PROJE META VERİSİ VE SIRALI SAHNE NOTLARI:
---
{json.dumps(project_payload, ensure_ascii=False, indent=2)}
---

Yukarıdaki proje meta verisi ve sıralı sahne notlarından, kurallara tam
olarak uyan bir storyboard JSON'u üret.
"""


@dataclass
class StoryboardRunOutcome:
    call_result: ModelCallResult
    json_valid: bool
    schema_valid: bool
    schema_error: Optional[str]
    validated: Optional[Storyboard]
    business_result: Optional[Dict]


def run_storyboard_generation(
    model_id: str,
    system_prompt: str,
    project: TutorialProject,
    temperature: float,
    max_tokens: int,
) -> StoryboardRunOutcome:
    """Tek bir modelle storyboard üretir, şema ve iş kuralı doğrulaması yapar."""
    user_prompt = build_storyboard_user_prompt(project)
    call_result = call_model(model_id, system_prompt, user_prompt, temperature, max_tokens)

    schema_valid = False
    schema_error = None
    validated = None

    if call_result.success and call_result.parsed_json is not None:
        try:
            validated = validate_storyboard(call_result.parsed_json)
            schema_valid = True
        except (ValidationError, ValueError) as exc:
            schema_error = "Pydantic doğrulama hatası:\n" + str(exc)

    json_valid = call_result.parsed_json is not None

    if call_result.success and call_result.parsed_json is not None and not schema_valid:
        # scene_id eksikse (model bu alanı üretmedi/bilmiyor) önce
        # deterministik olarak göç ettirip yeniden doğrulamayı dener.
        migrated = migrate_scene_ids(call_result.parsed_json)
        try:
            validated = validate_storyboard(migrated)
            schema_valid = True
            schema_error = None
        except (ValidationError, ValueError):
            pass

    business_result = None
    if validated is not None:
        business_result = validate_storyboard_business_rules(
            validated.model_dump(), project, project.working_mode
        )

    return StoryboardRunOutcome(
        call_result=call_result,
        json_valid=json_valid,
        schema_valid=schema_valid,
        schema_error=schema_error,
        validated=validated,
        business_result=business_result,
    )


def migrate_scene_ids(storyboard: Dict) -> Dict:
    """scene_id İÇERMEYEN (Faz 4C öncesi) storyboard'ları deterministik olarak göç ettirir.

    Orijinal sözlüğü DEĞİŞTİRMEZ; her zaman düzenlenebilir yeni bir kopya
    döner. scene_id zaten mevcut ve boş olmayan sahnelere dokunulmaz.
    Eksik/boş scene_id, sahnenin scene_number sırasına göre
    "{image_id}_step_{sıra:02d}" biçiminde üretilir (aynı image_id'nin
    ikinci geçtiği yerde _step_02, üçüncüsünde _step_03 vb.). Üretilen
    kimlik, storyboard'da halihazırda var olan bir scene_id ile çakışırsa
    (nadir durum) sıra numarası çakışma kalmayana kadar artırılır.
    """
    migrated = copy.deepcopy(storyboard)
    scenes = migrated.get("scenes") or []

    existing_ids = {s.get("scene_id") for s in scenes if s.get("scene_id")}
    occurrence_by_image_id: Dict[str, int] = {}

    for scene in sorted(scenes, key=lambda s: s.get("scene_number", 0)):
        if scene.get("scene_id"):
            continue
        image_id = scene.get("image_id", "scene")
        occurrence_by_image_id[image_id] = occurrence_by_image_id.get(image_id, 0) + 1
        occurrence = occurrence_by_image_id[image_id]
        candidate = f"{image_id}_step_{occurrence:02d}"
        while candidate in existing_ids:
            occurrence += 1
            candidate = f"{image_id}_step_{occurrence:02d}"
        scene["scene_id"] = candidate
        existing_ids.add(candidate)

    return migrated


def generate_unique_scene_id(image_id: str, existing_scene_ids: List[str]) -> str:
    """Verilen image_id için, mevcut scene_id kümesiyle çakışmayan yeni bir kimlik üretir.

    Sahne çoğaltma (duplication) özelliğinde kullanılır.
    """
    existing = set(existing_scene_ids)
    occurrence = 1
    candidate = f"{image_id}_step_{occurrence:02d}"
    while candidate in existing:
        occurrence += 1
        candidate = f"{image_id}_step_{occurrence:02d}"
    return candidate


def _renumber_scenes(scenes: List[Dict]) -> List[Dict]:
    for idx, scene in enumerate(scenes):
        scene["scene_number"] = idx + 1
    return scenes


def recalculate_total_duration(scenes: List[Dict]) -> int:
    return sum(scene["duration_seconds"] for scene in scenes)


def move_scene_up(scenes: List[Dict], index: int) -> List[Dict]:
    """Sahneyi bir yukarı taşır ve scene_number değerlerini yeniden numaralandırır."""
    if index <= 0 or index >= len(scenes):
        return scenes
    scenes[index - 1], scenes[index] = scenes[index], scenes[index - 1]
    return _renumber_scenes(scenes)


def move_scene_down(scenes: List[Dict], index: int) -> List[Dict]:
    """Sahneyi bir aşağı taşır ve scene_number değerlerini yeniden numaralandırır."""
    if index < 0 or index >= len(scenes) - 1:
        return scenes
    scenes[index + 1], scenes[index] = scenes[index], scenes[index + 1]
    return _renumber_scenes(scenes)


def duplicate_scene(scenes: List[Dict], index: int) -> List[Dict]:
    """index konumundaki sahneyi çoğaltır: aynı image_id, yeni benzersiz scene_id,
    requires_review=true olarak işaretlenmiş bir kopya, hemen ardına eklenir.
    scene_number değerleri yeniden numaralandırılır."""
    if index < 0 or index >= len(scenes):
        return scenes
    original = scenes[index]
    copy_scene = copy.deepcopy(original)
    copy_scene["scene_id"] = generate_unique_scene_id(
        original.get("image_id", "scene"), [s.get("scene_id", "") for s in scenes]
    )
    copy_scene["requires_review"] = True
    scenes.insert(index + 1, copy_scene)
    return _renumber_scenes(scenes)


def remove_scene(scenes: List[Dict], index: int) -> List[Dict]:
    """index konumundaki sahneyi kaldırır. En az bir sahne kalmalıdır; storyboard'da
    tek sahne varsa bu fonksiyon listeyi değiştirmeden döner (çağıran taraf bu
    durumu kullanıcıya bildirmelidir)."""
    if len(scenes) <= 1 or index < 0 or index >= len(scenes):
        return scenes
    del scenes[index]
    return _renumber_scenes(scenes)


def build_narration_text(title: str, scenes: List[Dict], closing_text: str) -> str:
    """Seslendirme için sıralı sahne anlatımlarını ve kapanış metnini birleştirir."""
    lines = [f"Video Başlığı: {title}", ""]
    for scene in sorted(scenes, key=lambda s: s["scene_number"]):
        lines.append(f"Sahne {scene['scene_number']}: {scene['scene_title']}")
        lines.append(scene["narration"])
        lines.append("")
    lines.append("Kapanış:")
    lines.append(closing_text)
    return "\n".join(lines)
