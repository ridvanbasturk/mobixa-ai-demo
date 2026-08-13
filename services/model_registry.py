"""Model plan etiketleri (Qwen Planı / Gemma Planı vb.) ve model-bilinçli
Bedrock Mantle rota + göç (migration) metadatası — arayüz genelinde tek kaynak.

Bu etiketler "hangi slotun" ne anlama geldiğini tanımlar; gerçek model kimliği
(.env üzerinden değişebilir) sidebar'daki "Teknik detaylar" expander'ında
ayrıca gösterilir.

Bu modül ayrıca model-bilinçli (model-aware) Bedrock Mantle ROTA metadatasının
VE seçici Gemma 4 göçünün (bkz. proje geçmişi) tek kaynağıdır (`resolve_model_route`).
Bazı modeller (ör. google.gemma-4-31b) standart `/v1` rotasında değil, yalnızca
OpenAI-uyumlu `/openai/v1` rotasında çalışır; bu dosya hangi model_id'nin hangi
rotayı kullanacağını VE hangi göç durumunda (`migration_status`) olduğunu
tanımlar. Gerçek rota->base_url çevrimi `services/bedrock_client.py` içinde
yapılır (bu modül URL/istemci oluşturmaz, yalnızca metadata döner).

SEÇİCİ GEMMA 4 GÖÇÜ — ÖZET (bkz. proje geçmişi için ayrıntılı gerekçe):
  - B1/B6/C1: Plan A = Qwen3 235B (korunur), Plan B = Gemma 4 31B (yeni).
    Qwen3 32B yalnızca teknik yedek (fallback) olarak kalır.
  - A1 Storyboard: aynı Qwen3 235B / Gemma 4 31B çifti + Qwen3 32B yedek.
  - A1 Vision: Qwen3 VL 235B (korunur) + Gemma 4 31B (görsel girişle
    doğrulanmış).
  - A1 Genişletme (scene expansion): varsayılan TEK aktif model Gemma 4 31B
    (maliyet için); Qwen3 235B seçilebilir alternatif olarak kalır.
  - A2: TEK istisna — aktif yanıt üretim modelleri YALNIZCA Gemma'dır
    (Plan A = Gemma 4 31B, Plan B = Gemma 4 26B-A4B, ikisi de gerçek çağrıyla
    doğrulanmıştır). Kimi K2.5 ve DeepSeek V3.2 artık aktif değildir
    (legacy_disabled); Qwen3 32B yalnızca acil durum teknik yedeğidir ve
    normal A2 arayüzünde aktif Plan B olarak GÖSTERİLMEZ.
  - legacy_disabled: Kimi, DeepSeek, GLM, Nemotron, Qwen3 Next 80B (eski/
    bozuk yedek varsayılan). Qwen3 235B / Qwen3 32B / Qwen3 VL 235B ASLA
    legacy_disabled İŞARETLENMEZ.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class PlanInfo:
    slot_label: str
    display_name: str
    subtitle: str
    # EN alanları opsiyoneldir; boş bırakılırsa (yeni bir PlanInfo eklenip
    # unutulursa) TR metne düşer — sessizce çökmez, yalnızca çeviri eksik
    # kalır. `display_name` (model adı, ör. "Qwen3 235B A22B 2507") kasıtlı
    # olarak dilden bağımsızdır, çevrilmez.
    slot_label_en: str = ""
    subtitle_en: str = ""

    @property
    def heading(self) -> str:
        return f"{self.slot_label} — {self.display_name}"

    def slot_label_for(self, lang: str) -> str:
        if lang == "en" and self.slot_label_en:
            return self.slot_label_en
        return self.slot_label

    def subtitle_for(self, lang: str) -> str:
        if lang == "en" and self.subtitle_en:
            return self.subtitle_en
        return self.subtitle

    def heading_for(self, lang: str) -> str:
        return f"{self.slot_label_for(lang)} — {self.display_name}"


# PLAN_A/PLAN_B, B1, B6 ve C1 tarafından ORTAK kullanılır (bkz.
# B1_MODEL_A/B, B6_MODEL_A/B, C1_MODEL_A/B, .env.example). Buradaki isim/
# etiket değişikliği her üç modülün sidebar'ında aynı anda yansır.
#
# Seçici Gemma 4 göçü: Plan A = Qwen3 235B (korunur, "birincil" metin
# modeli), Plan B = Gemma 4 31B (yeni karşılaştırma modeli). Qwen3 32B
# artık normal bir "Plan B" değil, yalnızca teknik bir yedektir (bkz.
# B1_FALLBACK_MODEL vb. — sidebar'ın "Teknik detaylar" bölümünde gösterilir,
# normal karşılaştırma kartı olarak DEĞİL).
PLAN_A = PlanInfo(
    slot_label="Qwen Planı",
    display_name="Qwen3 235B A22B 2507",
    subtitle="Mevcut birincil kalite adayı",
    slot_label_en="Qwen Plan",
    subtitle_en="Current primary quality candidate",
)

PLAN_B = PlanInfo(
    slot_label="Gemma Planı",
    display_name="Gemma 4 31B",
    subtitle="Yeni Gemma karşılaştırma adayı",
    slot_label_en="Gemma Plan",
    subtitle_en="New Gemma comparison candidate",
)

# A2 (Destek/Onboarding Chatbot) kendi model çiftini kullanır; B1/B6/C1
# yapılandırmasının yerine geçmez. A2, aktif yanıt üretim modellerinin
# YALNIZCA Gemma olduğu TEK istisnadır — bu yüzden her iki slot da "Gemma
# Plan A/B" olarak etiketlenir (Qwen/Gemma karşılaştırması değil, iki farklı
# Gemma varyantı karşılaştırması). Plan B yalnızca ikinci bir doğrulanmış
# Gemma varyantı gerçekten yapılandırılmışsa aktif bir karşılaştırma kartı
# olarak gösterilir (bkz. app_pages/a2_support_chatbot.py).
A2_PLAN_A = PlanInfo(
    slot_label="Gemma Plan A",
    display_name="Gemma 4 31B",
    subtitle="Birincil Gemma yanıt modeli",
    slot_label_en="Gemma Plan A",
    subtitle_en="Primary Gemma response model",
)

A2_PLAN_B = PlanInfo(
    slot_label="Gemma Plan B",
    display_name="Gemma 4 26B-A4B",
    subtitle="İkincil doğrulanmış Gemma varyantı (varsa)",
    slot_label_en="Gemma Plan B",
    subtitle_en="Secondary verified Gemma variant (if configured)",
)

# A1 (AI Destekli Kullanım Videosu — storyboard üretimi) kendi model
# çiftini kullanır; B1/B6/C1 veya A2 yapılandırmasının yerine geçmez.
# Aynı seçici göç deseni: Plan A = Qwen3 235B, Plan B = Gemma 4 31B.
A1_PLAN_A = PlanInfo(
    slot_label="Qwen Planı",
    display_name="Qwen3 235B A22B 2507",
    subtitle="Storyboard kalite adayı",
    slot_label_en="Qwen Plan",
    subtitle_en="Storyboard quality candidate",
)

A1_PLAN_B = PlanInfo(
    slot_label="Gemma Planı",
    display_name="Gemma 4 31B",
    subtitle="Storyboard Gemma karşılaştırma adayı",
    slot_label_en="Gemma Plan",
    subtitle_en="Storyboard Gemma comparison candidate",
)

# A1 AI Görsel Analiz Modu (vision) kendi çok-modlu model çiftini kullanır;
# A1_PLAN_A/B (metin tabanlı storyboard üretimi) ile karıştırılmamalıdır.
A1_VISION_PLAN_A = PlanInfo(
    slot_label="Qwen Planı",
    display_name="Qwen3 VL 235B A22B",
    subtitle="Birincil görsel analiz adayı",
    slot_label_en="Qwen Plan",
    subtitle_en="Primary visual analysis candidate",
)

A1_VISION_PLAN_B = PlanInfo(
    slot_label="Gemma Planı",
    display_name="Gemma 4 31B",
    subtitle="Gerçek görsel girişle doğrulanmış Gemma alternatifi",
    slot_label_en="Gemma Plan",
    subtitle_en="Gemma alternative verified with real visual input",
)


# --- Model-bilinçli Bedrock Mantle rota metadatası --------------------------
#
# Doğrulanmış kök neden (bkz. proje geçmişi): google.gemma-4-31b, standart
# `/v1` rotasında `models.list()` çıktısında GÖRÜNÜR ama chat.completions
# çağrısı o rotada "isn't supported on this route" (HTTP 400) hatasıyla
# reddedilir; aynı model `/openai/v1` rotasında hem chat.completions hem de
# responses API ile başarıyla çalışır. Bu yüzden asıl sorun model
# kullanılabilirliği veya API stili değil, ROTA seçimidir.

MANTLE_ROUTE_STANDARD = "standard"
MANTLE_ROUTE_OPENAI = "openai"
ALLOWED_MANTLE_ROUTES = {MANTLE_ROUTE_STANDARD, MANTLE_ROUTE_OPENAI}

API_FAMILY_CHAT_COMPLETIONS = "chat_completions"
API_FAMILY_RESPONSES = "responses"

# Göç durumu (migration_status) değerleri:
#   - "active": şu anda en az bir özellikte fiilen kullanılıyor.
#   - "legacy_disabled": daha önce kullanılıyordu, Gemma 4 göçü sonrası
#     devre dışı bırakıldı; geçmiş değerlendirme kayıtları SİLİNMEDİ, yalnızca
#     bu model artık yeni çağrılarda seçilmiyor.
#   - "verified_available": gerçek bir çağrıyla doğrulandı ve çalışıyor, ama
#     şu an hiçbir özellikte aktif bir role atanmadı (gereksiz ekstra
#     yönlendirme/çağrı eklenmediği için).
MIGRATION_STATUS_ACTIVE = "active"
MIGRATION_STATUS_LEGACY_DISABLED = "legacy_disabled"
MIGRATION_STATUS_VERIFIED_AVAILABLE = "verified_available"

# "google.gemma-4-" ile başlayan (ve MODEL_ROUTE_REGISTRY'de AÇIKÇA
# kaydedilmemiş) modeller için güvenli varsayılan geri düşüş (fallback).
# Yalnızca gemma-4 ailesini kapsar; diğer google.* modelleri (ör.
# google.gemma-3-*) OTOMATİK olarak bu rotaya yönlendirilmez.
GEMMA4_ROUTE_FALLBACK_PREFIX = "google.gemma-4-"


@dataclass(frozen=True)
class ModelRouteInfo:
    """Bir model_id için rota, sağlayıcı, göç durumu ve aktif rol metadatası
    (istemci/URL oluşturmaz — yalnızca salt metadata)."""

    model_id: str
    display_name: str
    mantle_route: str = MANTLE_ROUTE_STANDARD
    api_family: str = API_FAMILY_CHAT_COMPLETIONS
    supports_text: bool = True
    supports_vision: bool = True
    provider: str = "Bilinmiyor"
    family: str = "bilinmiyor"
    migration_status: str = MIGRATION_STATUS_ACTIVE
    active_roles: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_legacy_disabled(self) -> bool:
        return self.migration_status == MIGRATION_STATUS_LEGACY_DISABLED


# Bilinen model kimlikleri için AÇIK metadata kaydı. `resolve_model_route`
# önce burayı kontrol eder; burada bulunmayan modeller için genel geri
# düşüş kuralları (gemma-4 öneki) veya standart/bilinmeyen varsayılan
# uygulanır.
MODEL_ROUTE_REGISTRY: Dict[str, ModelRouteInfo] = {
    # --- Aktif Qwen modelleri (KORUNUR, legacy_disabled İŞARETLENMEZ) -----
    "qwen.qwen3-235b-a22b-2507": ModelRouteInfo(
        model_id="qwen.qwen3-235b-a22b-2507",
        display_name="Qwen3 235B A22B 2507",
        mantle_route=MANTLE_ROUTE_STANDARD,
        provider="Alibaba (Qwen)",
        family="qwen3",
        migration_status=MIGRATION_STATUS_ACTIVE,
        supports_vision=False,
        active_roles=(
            "b1_primary_text",
            "b6_primary_text",
            "c1_primary_text",
            "a1_storyboard_primary_text",
            "a1_expansion_alternative",
            "comparison_with_gemma",
        ),
    ),
    "qwen.qwen3-32b": ModelRouteInfo(
        model_id="qwen.qwen3-32b",
        display_name="Qwen3 32B",
        mantle_route=MANTLE_ROUTE_STANDARD,
        provider="Alibaba (Qwen)",
        family="qwen3",
        migration_status=MIGRATION_STATUS_ACTIVE,
        supports_vision=False,
        active_roles=(
            "fallback_b1",
            "fallback_b6",
            "fallback_c1",
            "fallback_a1_storyboard",
            "fallback_a2_emergency",
        ),
    ),
    "qwen.qwen3-vl-235b-a22b-instruct": ModelRouteInfo(
        model_id="qwen.qwen3-vl-235b-a22b-instruct",
        display_name="Qwen3 VL 235B A22B",
        mantle_route=MANTLE_ROUTE_STANDARD,
        provider="Alibaba (Qwen)",
        family="qwen3-vl",
        migration_status=MIGRATION_STATUS_ACTIVE,
        supports_vision=True,
        active_roles=("a1_vision_primary",),
    ),
    # --- Aktif Gemma 4 modelleri -------------------------------------------
    "google.gemma-4-31b": ModelRouteInfo(
        model_id="google.gemma-4-31b",
        display_name="Gemma 4 31B",
        mantle_route=MANTLE_ROUTE_OPENAI,
        api_family=API_FAMILY_CHAT_COMPLETIONS,
        provider="Google",
        family="gemma-4",
        migration_status=MIGRATION_STATUS_ACTIVE,
        supports_text=True,
        supports_vision=True,
        active_roles=(
            "b1_comparison_gemma",
            "b6_comparison_gemma",
            "c1_comparison_gemma",
            "a1_storyboard_comparison_gemma",
            "a1_vision_comparison",
            "a1_expansion_primary",
            "a2_primary",
        ),
    ),
    "google.gemma-4-26b-a4b": ModelRouteInfo(
        model_id="google.gemma-4-26b-a4b",
        display_name="Gemma 4 26B-A4B",
        mantle_route=MANTLE_ROUTE_OPENAI,
        api_family=API_FAMILY_CHAT_COMPLETIONS,
        provider="Google",
        family="gemma-4",
        migration_status=MIGRATION_STATUS_ACTIVE,
        supports_text=True,
        # Yalnızca metin çağrısıyla doğrulandı; görsel girişle test
        # edilmedi, bu yüzden supports_vision temkinli biçimde False.
        supports_vision=False,
        active_roles=("a2_secondary",),
    ),
    "google.gemma-4-e2b": ModelRouteInfo(
        model_id="google.gemma-4-e2b",
        display_name="Gemma 4 E2B",
        mantle_route=MANTLE_ROUTE_OPENAI,
        api_family=API_FAMILY_CHAT_COMPLETIONS,
        provider="Google",
        family="gemma-4",
        # Gerçek metin çağrısıyla doğrulandı (models.list() + minimal
        # invocation başarılı) ama hiçbir özellikte aktif bir role
        # atanmadı — gereksiz bir yönlendirme/çağrı katmanı eklenmedi.
        migration_status=MIGRATION_STATUS_VERIFIED_AVAILABLE,
        supports_text=True,
        supports_vision=False,
        active_roles=(),
    ),
    # --- legacy_disabled: Gemma 4 göçü sonrası aktif seçimden kaldırıldı ---
    # (Geçmiş evaluations.csv kayıtları SİLİNMEDİ; bu yalnızca yeni
    # çağrılarda artık seçilmediklerini belirtir.)
    "moonshotai.kimi-k2.5": ModelRouteInfo(
        model_id="moonshotai.kimi-k2.5",
        display_name="Kimi K2.5",
        provider="Moonshot AI",
        family="kimi",
        migration_status=MIGRATION_STATUS_LEGACY_DISABLED,
        active_roles=(),
    ),
    "deepseek.v3.2": ModelRouteInfo(
        model_id="deepseek.v3.2",
        display_name="DeepSeek V3.2",
        provider="DeepSeek",
        family="deepseek",
        migration_status=MIGRATION_STATUS_LEGACY_DISABLED,
        active_roles=(),
    ),
    "zai.glm-4.6": ModelRouteInfo(
        model_id="zai.glm-4.6",
        display_name="GLM 4.6",
        provider="Zhipu AI (Z.ai)",
        family="glm",
        migration_status=MIGRATION_STATUS_LEGACY_DISABLED,
        active_roles=(),
    ),
    "zai.glm-4.7-flash": ModelRouteInfo(
        model_id="zai.glm-4.7-flash",
        display_name="GLM 4.7 Flash",
        provider="Zhipu AI (Z.ai)",
        family="glm",
        migration_status=MIGRATION_STATUS_LEGACY_DISABLED,
        active_roles=(),
    ),
    "nvidia.nemotron-nano-12b-v2": ModelRouteInfo(
        model_id="nvidia.nemotron-nano-12b-v2",
        display_name="Nemotron Nano 12B v2",
        provider="NVIDIA",
        family="nemotron",
        migration_status=MIGRATION_STATUS_LEGACY_DISABLED,
        active_roles=(),
    ),
    "nvidia.nemotron-nano-9b-v2": ModelRouteInfo(
        model_id="nvidia.nemotron-nano-9b-v2",
        display_name="Nemotron Nano 9B v2",
        provider="NVIDIA",
        family="nemotron",
        migration_status=MIGRATION_STATUS_LEGACY_DISABLED,
        active_roles=(),
    ),
    "nvidia.nemotron-nano-3-30b": ModelRouteInfo(
        model_id="nvidia.nemotron-nano-3-30b",
        display_name="Nemotron Nano 3 30B",
        provider="NVIDIA",
        family="nemotron",
        migration_status=MIGRATION_STATUS_LEGACY_DISABLED,
        active_roles=(),
    ),
    "nvidia.nemotron-super-3-120b": ModelRouteInfo(
        model_id="nvidia.nemotron-super-3-120b",
        display_name="Nemotron Super 3 120B",
        provider="NVIDIA",
        family="nemotron",
        migration_status=MIGRATION_STATUS_LEGACY_DISABLED,
        active_roles=(),
    ),
    "qwen.qwen3-next-80b-a3b-instruct": ModelRouteInfo(
        model_id="qwen.qwen3-next-80b-a3b-instruct",
        display_name="Qwen3 Next 80B A3B",
        provider="Alibaba (Qwen)",
        family="qwen3-next",
        # Eski/bozuk bir yedek varsayılandı (Frankfurt uç noktasında
        # dakikalarca yanıt vermiyordu); modası geçmiş yinelenen bir Qwen
        # alternatifi olarak devre dışı bırakıldı. qwen3-235b/qwen3-32b
        # bunun yerini zaten alıyor.
        migration_status=MIGRATION_STATUS_LEGACY_DISABLED,
        active_roles=(),
    ),
}


def resolve_model_route(model_id: str) -> ModelRouteInfo:
    """model_id için tam model metadatasını (rota, sağlayıcı, göç durumu,
    aktif roller) döner.

    Öncelik sırası:
      1) MODEL_ROUTE_REGISTRY'de açık bir kayıt varsa o kullanılır (bu,
         gemma-4 öneki geri düşüşünü de EZER — ör. ileride
         "google.gemma-4-e2b" standart rotada çalıştığı kanıtlanırsa,
         burada standart olarak açıkça kaydedilip geri düşüş atlanabilir).
      2) Kayıtlı olmayan ama "google.gemma-4-" ile başlayan bir model_id,
         güvenli varsayılan olarak openai rotasına yönlendirilir.
      3) Aksi halde standart rota (mevcut davranışla birebir aynı; Qwen ve
         diğer tüm modeller için hiçbir şey değişmez).
    """
    known = MODEL_ROUTE_REGISTRY.get(model_id)
    if known is not None:
        return known

    if model_id.startswith(GEMMA4_ROUTE_FALLBACK_PREFIX):
        return ModelRouteInfo(
            model_id=model_id,
            display_name=model_id,
            mantle_route=MANTLE_ROUTE_OPENAI,
            api_family=API_FAMILY_CHAT_COMPLETIONS,
            provider="Google",
            family="gemma-4",
        )

    return ModelRouteInfo(model_id=model_id, display_name=model_id)


def is_legacy_disabled(model_id: str) -> bool:
    """model_id, Gemma 4 göçü sonrası devre dışı bırakılmış (legacy_disabled)
    bilinen bir model mi? Kayıtlı olmayan model kimlikleri için her zaman
    False döner (yalnızca AÇIKÇA devre dışı bırakılmış modelleri işaretler)."""
    return resolve_model_route(model_id).is_legacy_disabled


def route_display_label(mantle_route: str) -> str:
    """Rota türü için kullanıcıya dönük (Türkçe) kısa etiket döner."""
    if mantle_route == MANTLE_ROUTE_OPENAI:
        return "OpenAI uyumlu /openai/v1"
    return "Standart /v1"
