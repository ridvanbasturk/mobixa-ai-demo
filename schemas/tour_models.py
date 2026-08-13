"""A1 Ürün Turu Stüdyosu için Pydantic şemaları.

Üç ayrı veri türü vardır ve karıştırılmamalıdır:

- `TourElement`  — tarayıcıdan DETERMİNİSTİK olarak çıkarılan gerçek arayüz
  öğesi. Model bunu üretmez, yalnızca okur.
- `TourStepDecision` — modelin o adımda verdiği karar. Modelden gelir,
  bu yüzden `services/tour_validation.py` ile ayrıca denetlenir.
- `TourStep` / `TourRecording` — gerçekten çalıştırılmış adımın ve tamamlanmış
  kaydın sonucu.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, field_validator

# Ajanın izin verilen eylemleri. Liste bilinçli olarak dardır: tarayıcıda
# keyfi kod çalıştırma, gezinti (URL yazma) veya dosya indirme YOKTUR.
ACTION_CLICK = "click"
ACTION_TYPE = "type"
ACTION_SCROLL_TO = "scroll_to"
ACTION_HIGHLIGHT = "highlight"
ACTION_WAIT = "wait"
ACTION_DONE = "done"

ALLOWED_ACTIONS = {
    ACTION_CLICK,
    ACTION_TYPE,
    ACTION_SCROLL_TO,
    ACTION_HIGHLIGHT,
    ACTION_WAIT,
    ACTION_DONE,
}

# Bir öğe hedefi GEREKTİREN eylemler.
ACTIONS_REQUIRING_ELEMENT = {ACTION_CLICK, ACTION_TYPE, ACTION_SCROLL_TO, ACTION_HIGHLIGHT}


class TourElement(BaseModel):
    """Canlı DOM'dan çıkarılmış, gerçekten var olan bir arayüz öğesi."""

    index: int
    role: str
    name: str
    key: Optional[str] = None
    x: float
    y: float
    width: float
    height: float
    in_sidebar: bool = False
    enabled: bool = True
    # Görünür alanın dışında mı? Öyleyse tıklanmadan önce kaydırılmalıdır.
    # Bu öğeler envanterden ELENMEZ; aksi halde uzun sayfalarda ekranın
    # altında kalan asıl eylem butonu ajana hiç görünmez.
    offscreen: bool = False

    @property
    def center(self) -> tuple:
        return (self.x + self.width / 2, self.y + self.height / 2)

    def describe(self) -> str:
        """Modele gönderilecek tek satırlık özet."""
        location = "sidebar" if self.in_sidebar else "main"
        key_part = f" key={self.key}" if self.key else ""
        state = "" if self.enabled else " (disabled)"
        scroll = " (aşağıda — kaydırılacak)" if self.offscreen else ""
        return f"[{self.index}] {self.role}: \"{self.name}\"{key_part} ({location}){state}{scroll}"


class TourStepDecision(BaseModel):
    """Modelin tek bir adım için verdiği karar (ham model çıktısı)."""

    action: str
    element_index: Optional[int] = None
    text: Optional[str] = None
    narration: str
    reason: str = ""

    @field_validator("action")
    @classmethod
    def known_action(cls, v: str) -> str:
        normalized = (v or "").strip().lower()
        if normalized not in ALLOWED_ACTIONS:
            raise ValueError(f"Bilinmeyen eylem: {v}. İzin verilenler: {sorted(ALLOWED_ACTIONS)}")
        return normalized

    @field_validator("narration")
    @classmethod
    def narration_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("narration boş olamaz")
        return v.strip()

    @property
    def is_done(self) -> bool:
        return self.action == ACTION_DONE


class TourStep(BaseModel):
    """Gerçekten çalıştırılmış bir adım (karar + sonuç)."""

    index: int
    action: str
    element_index: Optional[int] = None
    element_name: Optional[str] = None
    text: Optional[str] = None
    narration: str
    reason: str = ""
    start_seconds: float
    duration_seconds: float
    audio_path: Optional[str] = None
    model_id: Optional[str] = None
    latency_ms: Optional[float] = None
    estimated_cost_usd: Optional[float] = None

    @property
    def end_seconds(self) -> float:
        return self.start_seconds + self.duration_seconds


class TourRecording(BaseModel):
    """Tamamlanmış bir tur kaydının tüm metaverisi."""

    module: str
    language: str
    model_id: str
    steps: List[TourStep]
    video_path: Optional[str] = None
    subtitle_path: Optional[str] = None
    total_seconds: float = 0.0
    voiced: bool = False
    voice_unavailable_reason: Optional[str] = None
    source_fingerprint: Optional[str] = None
    total_cost_usd: Optional[float] = None
    stopped_reason: str = ""

    @property
    def step_count(self) -> int:
        return len(self.steps)


def validate_tour_decision(data: dict) -> TourStepDecision:
    """Ham model çıktısını TourStepDecision'a çevirir.

    Yalnızca YAPISAL doğrulama yapar (alanlar, izinli eylem). Kararın canlı
    ekrandaki öğelerle tutarlı olup olmadığı ayrıca
    `services/tour_validation.py::validate_decision_against_inventory`
    tarafından denetlenir.
    """
    return TourStepDecision.model_validate(data)
