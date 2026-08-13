"""Model-bilinçli (model-aware) Bedrock Mantle rota metadatası için testler.

AWS'den bağımsızdır; yalnızca services/model_registry.py::resolve_model_route
fonksiyonunun deterministik eşleştirme mantığını test eder.
"""
from __future__ import annotations

from services.model_registry import (
    A2_PLAN_A,
    A2_PLAN_B,
    MANTLE_ROUTE_OPENAI,
    MANTLE_ROUTE_STANDARD,
    MIGRATION_STATUS_ACTIVE,
    MIGRATION_STATUS_LEGACY_DISABLED,
    MIGRATION_STATUS_VERIFIED_AVAILABLE,
    MODEL_ROUTE_REGISTRY,
    PLAN_A,
    PLAN_B,
    ModelRouteInfo,
    is_legacy_disabled,
    resolve_model_route,
    route_display_label,
)


def test_qwen_model_resolves_to_standard_route():
    info = resolve_model_route("qwen.qwen3-235b-a22b-2507")
    assert info.mantle_route == MANTLE_ROUTE_STANDARD


def test_unknown_model_defaults_to_standard_route():
    info = resolve_model_route("some.unknown-model-id")
    assert info.mantle_route == MANTLE_ROUTE_STANDARD


def test_gemma_4_31b_resolves_to_openai_route():
    info = resolve_model_route("google.gemma-4-31b")
    assert info.mantle_route == MANTLE_ROUTE_OPENAI
    assert info.display_name == "Gemma 4 31B"
    assert info.supports_vision is True


def test_gemma_4_fallback_prefix_routes_unregistered_variant():
    # "google.gemma-4-mini" (uydurma, kayıt defterinde AÇIKÇA yer almayan bir
    # varyant) "google.gemma-4-" öneki fallback kuralıyla openai rotasına
    # yönlendirilmeli.
    assert "google.gemma-4-mini" not in MODEL_ROUTE_REGISTRY
    info = resolve_model_route("google.gemma-4-mini")
    assert info.mantle_route == MANTLE_ROUTE_OPENAI


def test_unrelated_google_model_does_not_use_gemma_route():
    # google.gemma-3-* "gemma-4-" ile başlamadığı için otomatik yönlendirilmemeli.
    info = resolve_model_route("google.gemma-3-27b-it")
    assert info.mantle_route == MANTLE_ROUTE_STANDARD


def test_other_google_prefixed_model_does_not_use_gemma_route():
    # Tüm google.* modelleri otomatik olarak openai rotasına gitmemeli.
    info = resolve_model_route("google.some-other-model")
    assert info.mantle_route == MANTLE_ROUTE_STANDARD


def test_explicit_registry_entry_overrides_fallback_prefix(monkeypatch):
    # google.gemma-4-31b normalde fallback öneki tarafından da openai'a
    # yönlendirilirdi; ama AÇIK kayıt önce kontrol edilir. Burada, kaydı
    # standart rotaya EZEREK (override) fallback'in görmezden gelindiğini
    # kanıtlıyoruz.
    override_registry = dict(MODEL_ROUTE_REGISTRY)
    override_registry["google.gemma-4-31b"] = ModelRouteInfo(
        model_id="google.gemma-4-31b",
        display_name="Gemma 4 31B (test override)",
        mantle_route=MANTLE_ROUTE_STANDARD,
    )
    monkeypatch.setattr("services.model_registry.MODEL_ROUTE_REGISTRY", override_registry)
    info = resolve_model_route("google.gemma-4-31b")
    assert info.mantle_route == MANTLE_ROUTE_STANDARD


def test_route_display_label_standard():
    assert route_display_label(MANTLE_ROUTE_STANDARD) == "Standart /v1"


def test_route_display_label_openai():
    assert route_display_label(MANTLE_ROUTE_OPENAI) == "OpenAI uyumlu /openai/v1"


def test_model_route_info_defaults():
    info = ModelRouteInfo(model_id="x", display_name="X")
    assert info.mantle_route == MANTLE_ROUTE_STANDARD
    assert info.api_family == "chat_completions"
    assert info.supports_text is True


# --- Seçici Gemma 4 göçü: aktif/legacy_disabled durum kontrolleri -----------


def test_qwen3_235b_remains_active_not_legacy():
    info = resolve_model_route("qwen.qwen3-235b-a22b-2507")
    assert info.migration_status == MIGRATION_STATUS_ACTIVE
    assert not info.is_legacy_disabled
    assert "b1_primary_text" in info.active_roles


def test_qwen3_32b_remains_active_fallback_role():
    info = resolve_model_route("qwen.qwen3-32b")
    assert info.migration_status == MIGRATION_STATUS_ACTIVE
    assert not info.is_legacy_disabled
    assert any("fallback" in role for role in info.active_roles)


def test_qwen3_vl_remains_active():
    info = resolve_model_route("qwen.qwen3-vl-235b-a22b-instruct")
    assert info.migration_status == MIGRATION_STATUS_ACTIVE
    assert info.supports_vision is True
    assert "a1_vision_primary" in info.active_roles


def test_gemma_4_31b_has_wide_active_roles():
    info = resolve_model_route("google.gemma-4-31b")
    assert info.migration_status == MIGRATION_STATUS_ACTIVE
    assert "a2_primary" in info.active_roles
    assert "a1_expansion_primary" in info.active_roles


def test_gemma_4_26b_a4b_active_as_a2_secondary():
    info = resolve_model_route("google.gemma-4-26b-a4b")
    assert info.migration_status == MIGRATION_STATUS_ACTIVE
    assert "a2_secondary" in info.active_roles
    assert info.mantle_route == MANTLE_ROUTE_OPENAI


def test_gemma_4_e2b_verified_but_not_active_role():
    info = resolve_model_route("google.gemma-4-e2b")
    assert info.migration_status == MIGRATION_STATUS_VERIFIED_AVAILABLE
    assert info.active_roles == ()


def test_kimi_marked_legacy_disabled():
    assert is_legacy_disabled("moonshotai.kimi-k2.5") is True
    info = resolve_model_route("moonshotai.kimi-k2.5")
    assert info.active_roles == ()


def test_deepseek_marked_legacy_disabled():
    assert is_legacy_disabled("deepseek.v3.2") is True


def test_glm_variants_marked_legacy_disabled():
    assert is_legacy_disabled("zai.glm-4.6") is True
    assert is_legacy_disabled("zai.glm-4.7-flash") is True


def test_nemotron_variants_marked_legacy_disabled():
    assert is_legacy_disabled("nvidia.nemotron-nano-12b-v2") is True
    assert is_legacy_disabled("nvidia.nemotron-nano-9b-v2") is True
    assert is_legacy_disabled("nvidia.nemotron-nano-3-30b") is True
    assert is_legacy_disabled("nvidia.nemotron-super-3-120b") is True


def test_obsolete_qwen3_next_marked_legacy_disabled():
    assert is_legacy_disabled("qwen.qwen3-next-80b-a3b-instruct") is True


def test_unknown_model_is_not_legacy_disabled():
    assert is_legacy_disabled("some.completely-unknown-model") is False


def test_plan_a_plan_b_are_qwen_and_gemma_labels():
    assert PLAN_A.slot_label == "Qwen Planı"
    assert PLAN_B.slot_label == "Gemma Planı"
    assert PLAN_A.display_name == "Qwen3 235B A22B 2507"
    assert PLAN_B.display_name == "Gemma 4 31B"


def test_a2_plans_are_gemma_only_labels():
    assert A2_PLAN_A.slot_label == "Gemma Plan A"
    assert A2_PLAN_B.slot_label == "Gemma Plan B"
    assert A2_PLAN_A.display_name == "Gemma 4 31B"
