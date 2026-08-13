"""A1 — AI Destekli Kullanım Videosu.

Faz 1: proje girdilerini (proje meta verisi + sıralı ekran görüntüleri +
sahne notları) toplar ve doğrular.
Faz 2: doğrulanmış projeden iki Bedrock modeliyle (Qwen3 235B A22B 2507,
Qwen3 32B) storyboard üretir, Pydantic + deterministik iş kuralı doğrulaması
yapar ve kullanıcının bir storyboard seçip düzenlemesine izin verir.
Faz 3: seçili storyboard'dan ve oturumda tutulan gerçek ekran görüntüsü
baytlarından, herhangi bir üretici video modeli KULLANMADAN, Pillow (kare
kompozisyonu) ve FFmpeg (kodlama) ile yerel, deterministik, sessiz ve alt
yazılı bir MP4 üretir.
Faz 4: iki çalışma modu sunar —
  - **Güvenli Kurumsal Mod**: mevcut manuel-not iş akışı; ekran görüntüsü
    baytları HİÇBİR modele gönderilmez.
  - **AI Görsel Analiz Modu**: kullanıcının açık onayıyla, ekran görüntüsü
    baytları çok-modlu (multimodal) modellere (Qwen3 VL, Gemma) gönderilir;
    modeller görünen arayüz öğelerini, birincil eylemi ve vurgu koordinatını
    önerir. Tüm sonuçlar `requires_review=true` ile işaretlenir ve
    storyboard'a aktarılmadan önce kullanıcı tarafından gözden geçirilmesi
    gerekir.

Amazon Polly entegrasyonu sonraki bir fazda eklenecektir. Bu modülde insan
değerlendirmesi (Human Evaluation) yoktur.
"""
from __future__ import annotations

import copy
import json
import os
import time
from pathlib import Path
from typing import Dict

import streamlit as st
from dotenv import load_dotenv
from pydantic import ValidationError

from schemas.a1_project_models import validate_tutorial_project
from schemas.a1_storyboard_models import (
    ALLOWED_ACTION_TYPES,
    MAX_DURATION_SECONDS as MAX_DURATION_SECONDS_SCHEMA,
    MIN_DURATION_SECONDS as MIN_DURATION_SECONDS_SCHEMA,
    validate_storyboard,
)
from schemas.a1_video_models import (
    DEFAULT_SUBTITLE_SOURCE,
    FPS_OPTIONS,
    RESOLUTION_OPTIONS,
    SUBTITLE_SOURCE_OPTIONS,
    validate_video_settings,
)
from services.a1_project_service import (
    generate_image_id,
    move_screen_down,
    move_screen_up,
    read_image_dimensions,
    remove_screen,
)
from services.a1_storyboard_service import (
    build_narration_text,
    duplicate_scene,
    generate_unique_scene_id,
    migrate_scene_ids,
    move_scene_down as move_storyboard_scene_down,
    move_scene_up as move_storyboard_scene_up,
    recalculate_total_duration,
    remove_scene,
    run_storyboard_generation,
)
from services.a1_storyboard_validation import validate_storyboard_business_rules
from services.a1_duration_service import (
    MAX_SCENE_DURATION_SECONDS,
    MIN_SCENE_DURATION_SECONDS,
    estimate_recommended_duration,
    manual_duration_warning,
)
from services.a1_scene_expansion_service import (
    expand_grounded_scene_to_storyboard_scenes,
    run_scene_expansion,
)
from services.a1_vision_validation import SCREEN_MATCH_WARNING_THRESHOLD
from services.a1_video_service import (
    FFMPEG_MISSING_MESSAGE,
    calculate_expected_duration,
    check_overlay_content_warnings,
    compute_video_state_fingerprint,
    generate_safe_filename,
    generate_video,
    is_ffmpeg_available,
    validate_video_inputs,
)
from services.a1_vision_service import (
    build_highlight_preview,
    build_vision_storyboard,
    grounded_result_to_storyboard_scene,
    run_grounded_vision_analysis,
    run_vision_analysis,
    vision_result_to_storyboard_scene,
)
from services.a1_knowledge_service import (
    KnowledgeBaseLoadError,
    build_grounding_context,
    get_screen,
    get_ui_elements_for_screen,
    load_knowledge_base,
    match_screen,
)
from services.bedrock_client import (
    CONNECTION_MESSAGE_KEYS,
    CONNECTION_STATUS_LEVELS,
    CONNECTION_STATUS_NO_KEY,
    CONNECTION_STATUS_UNTESTED,
    is_api_key_configured,
    next_connection_status,
)
from services.comparison import ModelMetrics, build_comparison_summary
from services.cost_calculator import get_display_name, load_model_prices
from services.evaluation_logger import (
    log_evaluation,
    read_evaluations_csv,
    save_storyboard_selection,
    save_video_generation,
)
from services.i18n import LANG_EN, get_language, render_language_switcher, t
from services.model_registry import (
    A1_PLAN_A,
    A1_PLAN_B,
    A1_VISION_PLAN_A,
    A1_VISION_PLAN_B,
    MANTLE_ROUTE_OPENAI,
    resolve_model_route,
    route_display_label,
)

load_dotenv()

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent / "sample_data" / "a1"

FEATURE_NAME = "A1"

TARGET_AUDIENCE_OPTIONS = ["Learner", "Trainer", "Admin"]
TONE_OPTIONS = ["Kısa ve doğrudan", "Eğitici", "Kurumsal"]
WORKING_MODE_OPTIONS = ["Güvenli Mod", "AI Destekli Mod"]
WORKING_MODE_TO_VALUE = {"Güvenli Mod": "safe", "AI Destekli Mod": "assisted"}

WORKFLOW_MODE_OPTIONS = ["Güvenli Kurumsal Mod", "AI Görsel Analiz Modu"]
WORKFLOW_MODE_TO_VALUE = {"Güvenli Kurumsal Mod": "safe", "AI Görsel Analiz Modu": "vision"}
VISION_NOTE_PLACEHOLDER = "(AI Görsel Analiz Modu ile doldurulacak)"

VISION_PRIVACY_WARNING = (
    "Bu modda ekran görüntüleri analiz için seçilen yapay zekâ modeline "
    "gönderilir. Hassas müşteri verileri içeren ekranları yüklemeyin."
)
VISION_PRIVACY_CONFIRM_LABEL = "Ekran görüntülerinin model analizine gönderilmesini onaylıyorum."

SCENE_NOTE_GUIDANCE = (
    "Her ekran için yalnızca gerçek ürün adımını yazın. Model sonraki "
    "aşamada bu notu daha akıcı bir anlatıma dönüştürecektir. Ekranda veya "
    "gerçek akışta bulunmayan bir adım eklemeyin."
)
SCENE_NOTE_EXAMPLE = "Örnek: \"Sol menüden Öğrenme Yolculukları bölümüne gidilir.\""


def load_storyboard_system_prompt() -> str:
    return (PROMPTS_DIR / "a1_storyboard_system.txt").read_text(encoding="utf-8")


def load_vision_system_prompt() -> str:
    return (PROMPTS_DIR / "a1_vision_system.txt").read_text(encoding="utf-8")


def load_vision_observation_system_prompt() -> str:
    return (PROMPTS_DIR / "a1_vision_observation_system.txt").read_text(encoding="utf-8")


def load_vision_grounded_system_prompt() -> str:
    return (PROMPTS_DIR / "a1_vision_grounded_system.txt").read_text(encoding="utf-8")


def load_scene_expansion_system_prompt() -> str:
    return (PROMPTS_DIR / "a1_scene_expansion_system.txt").read_text(encoding="utf-8")


def _sum_call_metric(*values):
    """None olmayan değerleri toplar; hiçbiri yoksa None döner (iki aşamalı çağrı toplamları için)."""
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def init_session_state() -> None:
    if "a1_screens" not in st.session_state:
        st.session_state.a1_screens = []
    if "a1_screen_bytes" not in st.session_state:
        st.session_state.a1_screen_bytes = {}
    if "a1_processed_files" not in st.session_state:
        st.session_state.a1_processed_files = set()
    if "a1_export" not in st.session_state:
        st.session_state.a1_export = None
    if "total_cost_usd" not in st.session_state:
        st.session_state.total_cost_usd = 0.0
    if "connection_status" not in st.session_state:
        st.session_state.connection_status = (
            CONNECTION_STATUS_UNTESTED if is_api_key_configured() else CONNECTION_STATUS_NO_KEY
        )
    if "a1_storyboard_results" not in st.session_state:
        st.session_state.a1_storyboard_results = None
    if "a1_selected_storyboard" not in st.session_state:
        st.session_state.a1_selected_storyboard = None
    if "a1_selected_validation" not in st.session_state:
        st.session_state.a1_selected_validation = None
    if "a1_video_result" not in st.session_state:
        st.session_state.a1_video_result = None
    if "a1_video_fingerprint" not in st.session_state:
        st.session_state.a1_video_fingerprint = None
    if "a1_video_settings_used" not in st.session_state:
        st.session_state.a1_video_settings_used = None
    if "a1_video_generation_in_progress" not in st.session_state:
        st.session_state.a1_video_generation_in_progress = False
    if "a1_workflow_mode" not in st.session_state:
        st.session_state.a1_workflow_mode = "safe"
    if "a1_vision_privacy_confirmed" not in st.session_state:
        st.session_state.a1_vision_privacy_confirmed = False
    if "a1_vision_results" not in st.session_state:
        st.session_state.a1_vision_results = {}
    if "a1_vision_generation_in_progress" not in st.session_state:
        st.session_state.a1_vision_generation_in_progress = False
    if "a1_vision_selected_scenes" not in st.session_state:
        # Faz 4C: her image_id artık BİR sahne yerine bir SAHNE LİSTESİ
        # eşler (alt sahne genişletmesi birden fazla sahneye yol açabilir).
        st.session_state.a1_vision_selected_scenes = {}
    if "a1_vision_selected_model" not in st.session_state:
        st.session_state.a1_vision_selected_model = {}
    if "a1_expansion_results" not in st.session_state:
        st.session_state.a1_expansion_results = {}
    if "a1_kb" not in st.session_state:
        st.session_state.a1_kb = None
    if "a1_kb_error" not in st.session_state:
        st.session_state.a1_kb_error = None
    if st.session_state.a1_kb is None and st.session_state.a1_kb_error is None:
        try:
            st.session_state.a1_kb = load_knowledge_base()
        except KnowledgeBaseLoadError as exc:
            st.session_state.a1_kb_error = str(exc)


def render_sidebar() -> dict:
    st.sidebar.title(t("common.sidebar_title"))

    if not is_api_key_configured():
        st.session_state.connection_status = CONNECTION_STATUS_NO_KEY
    elif st.session_state.connection_status == CONNECTION_STATUS_NO_KEY:
        st.session_state.connection_status = CONNECTION_STATUS_UNTESTED

    level = CONNECTION_STATUS_LEVELS[st.session_state.connection_status]
    message = t(CONNECTION_MESSAGE_KEYS[st.session_state.connection_status])
    getattr(st.sidebar, level)(message)

    region = os.environ.get("AWS_REGION", "us-east-1")
    # Seçici Gemma 4 göçü: Plan A = Qwen3 235B (korunur), Plan B = Gemma 4
    # 31B (yeni). Eski A1_MODEL_A/B ortam değişkenleri geriye dönük
    # uyumluluk için hâlâ okunur (A1_STORYBOARD_MODEL_A/B ayarlanmamışsa).
    model_a = os.environ.get("A1_STORYBOARD_MODEL_A") or os.environ.get(
        "A1_MODEL_A", "qwen.qwen3-235b-a22b-2507"
    )
    model_b = os.environ.get("A1_STORYBOARD_MODEL_B") or os.environ.get("A1_MODEL_B") or "google.gemma-4-31b"
    storyboard_fallback_model = os.environ.get("A1_STORYBOARD_FALLBACK", "qwen.qwen3-32b")
    vision_model_a = os.environ.get("A1_VISION_MODEL_A")
    vision_model_b = os.environ.get("A1_VISION_MODEL_B", "google.gemma-4-31b")
    expansion_model = os.environ.get("A1_EXPANSION_MODEL", "google.gemma-4-31b")
    expansion_alt_model = os.environ.get("A1_EXPANSION_ALT_MODEL", "qwen.qwen3-235b-a22b-2507")

    st.sidebar.markdown(f"**Bölge:** {region}")
    st.sidebar.markdown(f"**{A1_PLAN_A.slot_label}:** {A1_PLAN_A.display_name}")
    st.sidebar.markdown(f"**{A1_PLAN_B.slot_label}:** {A1_PLAN_B.display_name}")
    st.sidebar.caption(
        "A1, B1/B6/C1 ve A2'den farklı bir model çifti kullanır. "
        "Karşılaştırma amaçlıdır; bir sağlayıcının otomatik olarak daha iyi "
        "olduğu anlamına gelmez."
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("**AI Görsel Analiz Modu modelleri:**")
    st.sidebar.markdown(f"**{A1_VISION_PLAN_A.slot_label}:** {A1_VISION_PLAN_A.display_name}")
    st.sidebar.markdown(f"**{A1_VISION_PLAN_B.slot_label}:** {A1_VISION_PLAN_B.display_name}")
    if not vision_model_a:
        st.sidebar.error(
            "A1_VISION_MODEL_A ortam değişkeni tanımlı değil. Lütfen .env "
            "dosyasında Bedrock kataloğundaki gerçek Qwen3 VL model "
            "kimliğini A1_VISION_MODEL_A olarak tanımlayın."
        )
    # Gemma vision, gerçek bir görsel girişle doğrulanmıştır (bkz. proje
    # geçmişi); yine de kayıt defterinde supports_vision=False işaretli bir
    # model B'ye yapılandırılırsa (ör. ileride farklı bir model), Qwen3 VL'nin
    # TEK aktif görsel model olarak kalması ve kullanıcının net bir yapılandırma
    # uyarısı görmesi için bu denetim eklenmiştir.
    vision_b_supports_vision = (
        resolve_model_route(vision_model_b).supports_vision if vision_model_b else True
    )
    if vision_model_b and not vision_b_supports_vision:
        st.sidebar.warning(
            f"'{vision_model_b}' görsel analiz desteklemiyor (doğrulanmamış). "
            "Yalnızca Qwen3 VL (Plan A) aktif görsel model olarak kullanılacak."
        )

    with st.sidebar.expander("Teknik detaylar"):
        route_a = resolve_model_route(model_a)
        route_b = resolve_model_route(model_b)
        vision_route_a = resolve_model_route(vision_model_a) if vision_model_a else None
        vision_route_b = resolve_model_route(vision_model_b) if vision_model_b else None
        lines = [
            f"Storyboard Model A: {model_a}",
            f"  Sağlayıcı: {route_a.provider} · Aile: {route_a.family} · "
            f"Rota: {route_display_label(route_a.mantle_route)}",
            f"Storyboard Model B: {model_b}",
            f"  Sağlayıcı: {route_b.provider} · Aile: {route_b.family} · "
            f"Rota: {route_display_label(route_b.mantle_route)}",
            f"Storyboard teknik yedek (fallback): {storyboard_fallback_model} "
            "(yalnızca burada gösterilir; aktif bir plan değildir)",
            "",
            f"Vision Model A: {vision_model_a or '(tanımlı değil)'}",
        ]
        if vision_route_a:
            lines.append(f"  API rotası: {route_display_label(vision_route_a.mantle_route)}")
        lines.append(f"Vision Model B: {vision_model_b}")
        if vision_route_b:
            lines.append(
                f"  API rotası: {route_display_label(vision_route_b.mantle_route)} · "
                f"Görsel destek: {'Evet' if vision_route_b.supports_vision else 'Hayır (doğrulanmamış)'}"
            )
        lines.append("")
        lines.append(f"Sahne genişletme modeli (varsayılan): {expansion_model}")
        lines.append(f"Sahne genişletme alternatifi: {expansion_alt_model}")
        st.code("\n".join(lines), language=None)
        if route_a.mantle_route == MANTLE_ROUTE_OPENAI or route_b.mantle_route == MANTLE_ROUTE_OPENAI:
            st.caption("Bu model Mantle'ın OpenAI uyumlu rotasını kullanır.")
        if (vision_route_a and vision_route_a.mantle_route == MANTLE_ROUTE_OPENAI) or (
            vision_route_b and vision_route_b.mantle_route == MANTLE_ROUTE_OPENAI
        ):
            st.caption("Bu model Mantle'ın OpenAI uyumlu rotasını kullanır.")

    temperature = st.sidebar.slider("Sıcaklık (Temperature)", 0.0, 1.0, 0.2, 0.05, key="a1_temperature")
    max_tokens = st.sidebar.number_input(
        "Maksimum çıktı token sayısı", min_value=256, max_value=8000, value=3000, step=100, key="a1_max_tokens"
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Oturumun tahmini toplam maliyeti:** ${st.session_state.total_cost_usd:.6f}")
    st.sidebar.caption(
        "Bu tutar yalnızca mevcut oturumda yapılan başarılı model çağrılarını "
        "içerir (B1, B6, C1, A2 ve A1 dahil). Sıfırlamak CSV geçmişini etkilemez."
    )
    if st.sidebar.button("Oturum maliyetini sıfırla", key="a1_reset_cost"):
        st.session_state.total_cost_usd = 0.0
        st.rerun()

    st.sidebar.markdown("---")
    csv_content = read_evaluations_csv()
    st.sidebar.download_button(
        label="Test kayıtlarını CSV indir",
        data=csv_content,
        file_name="evaluations.csv",
        mime="text/csv",
        key="a1_download_csv",
    )

    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Fiyatlar Temmuz 2026 us-east-1 Standard fiyatlarına dayalı tahmini "
        "değerlerdir, gerçek faturalandırma AWS tarafından belirlenir."
    )

    return {
        "model_a": model_a,
        "model_b": model_b,
        "storyboard_fallback_model": storyboard_fallback_model,
        "vision_model_a": vision_model_a,
        "vision_model_b": vision_model_b,
        "expansion_model": expansion_model,
        "expansion_alt_model": expansion_alt_model,
        "temperature": temperature,
        "max_tokens": int(max_tokens),
    }


def render_workflow_mode_selector() -> str:
    st.subheader("0. A1 Çalışma Modu")

    workflow_mode_label = st.radio(
        "Çalışma modu",
        WORKFLOW_MODE_OPTIONS,
        index=WORKFLOW_MODE_OPTIONS.index(
            "Güvenli Kurumsal Mod" if st.session_state.a1_workflow_mode == "safe" else "AI Görsel Analiz Modu"
        ),
        key="a1_workflow_mode_radio",
        horizontal=True,
    )
    workflow_mode = WORKFLOW_MODE_TO_VALUE[workflow_mode_label]
    st.session_state.a1_workflow_mode = workflow_mode

    with st.expander("Çalışma modları ne anlama gelir?", expanded=False):
        st.markdown(
            "**Güvenli Kurumsal Mod**: Mevcut manuel iş akışı. Ekran "
            "görüntüsü baytları HİÇBİR modele gönderilmez; yalnızca sizin "
            "yazdığınız sahne notları metin modeline gönderilir. Sahne "
            "notu girmek zorunludur.\n\n"
            "**AI Görsel Analiz Modu**: Ekran görüntüsü baytları, seçtiğiniz "
            "çok-modlu (multimodal) modele (Qwen3 VL / Gemma) gönderilir; "
            "model görünen arayüz öğelerini, birincil eylemi ve bir talimat "
            "önerir. Sahne notu artık opsiyoneldir. Gönderim öncesi açık "
            "onayınız istenir; tüm sonuçlar gözden geçirme gerektirir "
            "(requires_review=true)."
        )

    if workflow_mode == "safe":
        st.caption("Güvenli Kurumsal Mod aktif — ekran görüntüsü baytları hiçbir modele gönderilmez.")
    else:
        st.caption("AI Görsel Analiz Modu aktif — ekran görüntüsü baytları gönderim için onay gerektirir.")

    return workflow_mode


def render_project_metadata() -> dict:
    st.subheader("1. Proje Meta Verisi")

    title = st.text_input(
        "Video başlığı",
        value="Yeni Öğrenme Yolculuğu Oluşturma",
        key="a1_title",
    )

    col1, col2 = st.columns(2)
    with col1:
        target_audience = st.selectbox(
            "Hedef kitle",
            TARGET_AUDIENCE_OPTIONS,
            index=TARGET_AUDIENCE_OPTIONS.index("Trainer"),
            key="a1_target_audience",
        )
    with col2:
        tone = st.selectbox(
            "Ton",
            TONE_OPTIONS,
            index=TONE_OPTIONS.index("Kurumsal"),
            key="a1_tone",
        )

    working_mode_label = st.radio(
        "Çalışma modu",
        WORKING_MODE_OPTIONS,
        index=WORKING_MODE_OPTIONS.index("Güvenli Mod"),
        key="a1_working_mode",
        horizontal=True,
    )

    with st.expander("Çalışma modları ne anlama gelir?"):
        st.markdown(
            "**Güvenli Mod**: Model sonraki aşamada yalnızca kullanıcı "
            "tarafından girilen sahne notlarını yeniden yazabilecek, ürünle "
            "ilgili yeni bir adım uyduramayacaktır.\n\n"
            "**AI Destekli Mod**: Eksik detaylar için model tarafından öneri "
            "sunulabilir, ancak bu tür içerik incelenmek üzere "
            "işaretlenecektir."
        )

    return {
        "title": title,
        "target_audience": target_audience,
        "tone": tone,
        "working_mode": WORKING_MODE_TO_VALUE[working_mode_label],
    }


def _dedupe_key(uploaded_file) -> str:
    file_id = getattr(uploaded_file, "file_id", None)
    if file_id:
        return str(file_id)
    return f"{uploaded_file.name}_{uploaded_file.size}"


def render_screenshot_upload() -> None:
    st.subheader("2. Ekran Görüntüsü Yükleme")

    st.caption(SCENE_NOTE_GUIDANCE)
    st.caption(SCENE_NOTE_EXAMPLE)

    uploaded_files = st.file_uploader(
        "Ekran görüntülerini yükleyin (PNG, JPG, JPEG) — birden fazla dosya seçilebilir",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="a1_uploader",
    )

    if not uploaded_files:
        return

    for uploaded in uploaded_files:
        dedupe_key = _dedupe_key(uploaded)
        if dedupe_key in st.session_state.a1_processed_files:
            continue
        st.session_state.a1_processed_files.add(dedupe_key)

        file_bytes = uploaded.getvalue()
        dimensions, error = read_image_dimensions(file_bytes, uploaded.name)
        if error:
            st.error(error)
            continue

        width, height = dimensions
        next_order = len(st.session_state.a1_screens) + 1
        image_id = generate_image_id(next_order)

        st.session_state.a1_screens.append(
            {
                "image_id": image_id,
                "original_file_name": uploaded.name,
                "scene_label": None,
                "note": "",
                "order": next_order,
                "width": width,
                "height": height,
            }
        )
        st.session_state.a1_screen_bytes[image_id] = file_bytes


def render_scene_list(workflow_mode: str) -> None:
    st.subheader("3. Sahne Listesi")

    screens = st.session_state.a1_screens
    if not screens:
        st.info("Sahne listesini oluşturmak için en az bir ekran görüntüsü yükleyin.")
        return

    if workflow_mode == "vision":
        st.caption(
            "AI Görsel Analiz Modu aktif: sahne notu artık opsiyoneldir. "
            "Doldurursanız model bunu ek bağlam olarak kullanır."
        )

    action = None

    for idx, screen in enumerate(screens):
        image_id = screen["image_id"]
        with st.container(border=True):
            cols = st.columns([1, 2, 2, 1])

            with cols[0]:
                image_bytes = st.session_state.a1_screen_bytes.get(image_id)
                if image_bytes:
                    st.image(image_bytes, width="stretch")
                st.caption(f"{screen['width']}x{screen['height']} px")
                st.caption(screen["original_file_name"])

            with cols[1]:
                label_key = f"a1_label_{image_id}"
                if label_key not in st.session_state:
                    st.session_state[label_key] = screen.get("scene_label") or ""
                st.text_input("Sahne etiketi (opsiyonel)", key=label_key)
                screen["scene_label"] = st.session_state[label_key] or None

            with cols[2]:
                note_key = f"a1_note_{image_id}"
                if note_key not in st.session_state:
                    st.session_state[note_key] = screen.get("note") or ""
                note_label = "Sahne notu (opsiyonel)" if workflow_mode == "vision" else "Sahne notu"
                st.text_area(note_label, key=note_key, height=90)
                screen["note"] = st.session_state[note_key]

            with cols[3]:
                st.write(f"Sıra: {screen['order']}")
                if st.button("Yukarı taşı", key=f"a1_up_{image_id}", disabled=(idx == 0)):
                    action = ("up", idx)
                if st.button("Aşağı taşı", key=f"a1_down_{image_id}", disabled=(idx == len(screens) - 1)):
                    action = ("down", idx)
                if st.button("Sahneyi kaldır", key=f"a1_remove_{image_id}"):
                    action = ("remove", idx)

    if action:
        kind, idx = action
        if kind == "up":
            move_screen_up(st.session_state.a1_screens, idx)
        elif kind == "down":
            move_screen_down(st.session_state.a1_screens, idx)
        elif kind == "remove":
            removed = st.session_state.a1_screens[idx]
            remove_screen(st.session_state.a1_screens, idx)
            st.session_state.a1_screen_bytes.pop(removed["image_id"], None)
        st.rerun()


def render_project_summary(meta: dict) -> None:
    st.subheader("4. Proje Özeti")

    screens = st.session_state.a1_screens
    notes_completed = sum(1 for s in screens if s.get("note") and s["note"].strip())

    m1, m2, m3 = st.columns(3)
    m1.metric("Video başlığı", meta["title"] or "—")
    m2.metric("Hedef kitle", meta["target_audience"])
    m3.metric("Ton", meta["tone"])

    m4, m5 = st.columns(2)
    m4.metric("Ekran sayısı", len(screens))
    m5.metric("Notu tamamlanmış sahne sayısı", f"{notes_completed}/{len(screens)}")

    if not screens:
        return

    table_rows = [
        {
            "Sıra": s["order"],
            "image_id": s["image_id"],
            "Sahne etiketi": s.get("scene_label") or "—",
            "Dosya adı": s["original_file_name"],
            "Not durumu": "Tamamlandı" if s.get("note") and s["note"].strip() else "Eksik",
            "Boyut": f"{s['width']}x{s['height']}",
        }
        for s in sorted(screens, key=lambda s: s["order"])
    ]
    st.dataframe(table_rows, width="stretch", hide_index=True)


def render_export(meta: dict, workflow_mode: str) -> None:
    st.subheader("5. Proje Dışa Aktarımı")

    if st.button("Proje JSON'unu Hazırla", type="primary", key="a1_export_button"):
        project_dict = {
            "title": meta["title"],
            "target_audience": meta["target_audience"],
            "tone": meta["tone"],
            "working_mode": meta["working_mode"],
            "screens": [
                {
                    "image_id": s["image_id"],
                    "original_file_name": s["original_file_name"],
                    "scene_label": s.get("scene_label"),
                    # AI Görsel Analiz Modu'nda sahne notu opsiyoneldir; boş
                    # bırakılırsa proje şeması (note zorunlu alan) hâlâ
                    # geçerli kalsın diye nötr bir yer tutucu kullanılır.
                    "note": (
                        s["note"]
                        if (s["note"] and s["note"].strip()) or workflow_mode != "vision"
                        else VISION_NOTE_PLACEHOLDER
                    ),
                    "order": s["order"],
                    "width": s["width"],
                    "height": s["height"],
                }
                for s in st.session_state.a1_screens
            ],
        }

        try:
            validated = validate_tutorial_project(project_dict)
            st.session_state.a1_export = validated.model_dump()
            st.success("Proje doğrulandı ve JSON hazırlandı.")
        except ValidationError as exc:
            st.session_state.a1_export = None
            messages = "; ".join(err["msg"] for err in exc.errors())
            st.error(f"Proje doğrulanamadı: {messages}")

    if st.session_state.a1_export:
        export_json = json.dumps(st.session_state.a1_export, ensure_ascii=False, indent=2)
        with st.expander("Doğrulanmış Proje JSON'u"):
            st.code(export_json, language="json")

        st.download_button(
            label="JSON indir",
            data=export_json,
            file_name="a1_tutorial_project.json",
            mime="application/json",
            key="a1_download_json",
        )


def render_validation_help() -> None:
    with st.expander("Bu doğrulama sonuçları ne anlama geliyor?"):
        st.markdown(
            "**Dosya doğrulaması**: Yüklenen görselin desteklenen formatta "
            "ve okunabilir olduğunu gösterir.\n\n"
            "**Proje şeması**: Zorunlu proje alanlarının, sahne notlarının, "
            "sıralamanın ve image ID'lerin beklenen yapıya uyduğunu "
            "gösterir.\n\n"
            "**Sıra doğrulaması**: Sahne sıralarının 1'den başladığını, "
            "benzersiz ve ardışık olduğunu gösterir.\n\n"
            "Bu aşamadaki kontroller yalnızca proje girdilerinin teknik "
            "olarak hazır olduğunu gösterir; storyboard veya video "
            "kalitesini değerlendirmez."
        )


def run_and_log_storyboard(model_id: str, system_prompt: str, project, settings: dict) -> dict:
    outcome = run_storyboard_generation(model_id, system_prompt, project, settings["temperature"], settings["max_tokens"])
    call_result = outcome.call_result

    st.session_state.connection_status = next_connection_status(st.session_state.connection_status, call_result)

    scene_count = len(outcome.validated.scenes) if outcome.validated else 0
    total_duration = outcome.validated.total_duration_seconds if outcome.validated else None

    business_passed = outcome.business_result["passed"] if outcome.business_result else None
    business_details = "; ".join(outcome.business_result["errors"]) if outcome.business_result else ""

    run_id = log_evaluation(
        feature=FEATURE_NAME,
        model_id=model_id,
        input_tokens=call_result.input_tokens,
        output_tokens=call_result.output_tokens,
        total_tokens=call_result.total_tokens,
        latency_ms=call_result.latency_ms,
        estimated_cost_usd=call_result.estimated_cost_usd,
        json_valid=outcome.json_valid,
        schema_valid=outcome.schema_valid,
        question_count=scene_count,
        success=call_result.success,
        error=call_result.error,
        storyboard_validation_passed=business_passed,
        storyboard_validation_details=business_details,
        storyboard_scene_count=scene_count,
        storyboard_total_duration=total_duration,
        storyboard_selected=False,
        selected_storyboard_model="",
    )

    if call_result.estimated_cost_usd:
        st.session_state.total_cost_usd += call_result.estimated_cost_usd

    return {"run_id": run_id, "outcome": outcome}


def render_storyboard_validation_help() -> None:
    with st.expander("Bu doğrulama sonuçları ne anlama geliyor?"):
        st.markdown(
            "**JSON geçerli**: Model cevabının JSON olarak okunabildiğini "
            "gösterir.\n\n"
            "**Pydantic doğrulaması**: Storyboard alanlarının, veri "
            "tiplerinin, sürelerin ve yapısal kuralların beklenen şemaya "
            "uyduğunu gösterir.\n\n"
            "**İş kuralı doğrulaması**: Tüm ekranların doğru sırada ve "
            "birer kez kullanılması, toplam sürenin doğru hesaplanması ve "
            "bilinmeyen ekran kimliği eklenmemesi gibi deterministik "
            "kontrolleri gösterir.\n\n"
            "**Kaynak-not uyarıları**: Kullanıcı notunda açıkça bulunmayan "
            "kesin sonuç ifadelerini yakalamaya çalışır.\n\n"
            "Bu kontroller storyboard'un teknik tutarlılığını artırır; "
            "anlatımın ürün akışını eksiksiz temsil ettiğini kesin olarak "
            "garanti etmez."
        )


def render_storyboard_model_card(model_id: str, plan, outcome_entry: dict, project) -> None:
    prices = load_model_prices()
    display_name = get_display_name(model_id, prices)
    outcome = outcome_entry["outcome"]
    call_result = outcome.call_result

    st.markdown(f"### {plan.heading}")
    st.caption(plan.subtitle)
    if display_name != plan.display_name:
        st.caption(f"Yapılandırılmış model: {display_name}")

    if call_result.success and outcome.schema_valid:
        st.success("Başarılı")
    elif call_result.success and not outcome.schema_valid:
        st.warning("JSON alındı ancak şema doğrulaması başarısız")
    else:
        st.error("Başarısız")

    if call_result.error:
        st.error(call_result.error)

    m1, m2, m3 = st.columns(3)
    m1.metric("Girdi token", call_result.input_tokens if call_result.input_tokens is not None else "Yok")
    m2.metric("Çıktı token", call_result.output_tokens if call_result.output_tokens is not None else "Yok")
    m3.metric("Toplam token", call_result.total_tokens if call_result.total_tokens is not None else "Yok")

    m4, m5 = st.columns(2)
    latency_s = call_result.latency_ms / 1000 if call_result.latency_ms is not None else None
    m4.metric("Gecikme (sn)", f"{latency_s:.2f}" if latency_s is not None else "Yok")
    cost = call_result.estimated_cost_usd
    m5.metric("Tahmini maliyet", f"${cost:.6f}" if cost is not None else "Hesaplanamadı")

    st.write(f"**JSON geçerli mi:** {'Evet' if outcome.json_valid else 'Hayır'}")
    st.write(f"**Pydantic doğrulama:** {'Geçti' if outcome.schema_valid else 'Başarısız'}")
    if outcome.schema_error:
        with st.expander("Doğrulama hatası detayı"):
            st.code(outcome.schema_error)

    business_result = outcome.business_result
    if business_result is not None:
        if business_result["passed"]:
            st.success(f"İş kuralı doğrulaması: Geçti ({business_result['scenes_validated']} sahne)")
        else:
            st.error("İş kuralı doğrulaması: Başarısız — " + "; ".join(business_result["errors"]))
        if business_result["warnings"]:
            st.warning("Uyarılar: " + "; ".join(business_result["warnings"]))

    validated = outcome.validated
    if validated:
        st.markdown(f"**Toplam süre:** {validated.total_duration_seconds} sn")
        st.markdown(f"**Sahne sayısı:** {len(validated.scenes)}")
        st.markdown(f"**Kapanış metni:** {validated.closing_text}")

        note_by_id = {s.image_id: s.note for s in project.screens}

        st.markdown("#### Sahneler")
        for scene in sorted(validated.scenes, key=lambda s: s.scene_number):
            with st.container(border=True):
                cols = st.columns([1, 2])
                with cols[0]:
                    image_bytes = st.session_state.a1_screen_bytes.get(scene.image_id)
                    if image_bytes:
                        st.image(image_bytes, width="stretch")
                    st.caption(scene.image_id)
                with cols[1]:
                    st.markdown(f"**{scene.scene_number}. {scene.scene_title}**")
                    st.caption(f"Kaynak not: {note_by_id.get(scene.image_id, '—')}")
                    st.write(f"Anlatım: {scene.narration}")
                    st.caption(f"Ekran üstü metin: {scene.on_screen_text}")
                    st.caption(
                        f"Süre: {scene.duration_seconds} sn · Geçiş: {scene.transition} · "
                        f"Zoom: {'Evet' if scene.zoom_enabled else 'Hayır'}"
                    )
                    st.caption(f"Vurgu: {scene.highlight_description}")
                    if scene.requires_review:
                        st.warning("AI önerisi — doğrulanmalı")

        if st.button("Bu storyboard'u kullan", key=f"a1_select_{model_id}_{outcome_entry['run_id']}"):
            previous = st.session_state.a1_selected_storyboard
            if previous and previous.get("source_run_id"):
                save_storyboard_selection(previous["source_run_id"], False, "")
            st.session_state.a1_selected_storyboard = {
                "source_model_id": model_id,
                "source_model_label": plan.heading,
                "source_run_id": outcome_entry["run_id"],
                "storyboard": copy.deepcopy(validated.model_dump()),
            }
            st.session_state.a1_selected_validation = None
            save_storyboard_selection(outcome_entry["run_id"], True, model_id)
            st.rerun()
    else:
        st.caption("Şema doğrulaması başarısız olduğu için bu storyboard seçilemez.")

    if call_result.raw_text:
        with st.expander("Ham çıktı"):
            st.code(call_result.raw_text)

    if call_result.parsed_json:
        st.download_button(
            label="JSON indir",
            data=json.dumps(call_result.parsed_json, ensure_ascii=False, indent=2),
            file_name=f"{model_id.replace('.', '_')}_a1_storyboard.json",
            mime="application/json",
            key=f"a1_download_{model_id}_{outcome_entry['run_id']}",
        )

    render_storyboard_validation_help()


def render_storyboard_comparison(results: dict) -> None:
    outcome_a = results["a"]["outcome"]
    outcome_b = results["b"]["outcome"]

    metrics = [
        ModelMetrics(
            label=A1_PLAN_A.heading,
            cost=outcome_a.call_result.estimated_cost_usd,
            latency_ms=outcome_a.call_result.latency_ms,
            total_tokens=outcome_a.call_result.total_tokens,
            json_valid=outcome_a.json_valid,
            schema_valid=outcome_a.schema_valid,
            business_valid=outcome_a.business_result["passed"] if outcome_a.business_result else None,
        ),
        ModelMetrics(
            label=A1_PLAN_B.heading,
            cost=outcome_b.call_result.estimated_cost_usd,
            latency_ms=outcome_b.call_result.latency_ms,
            total_tokens=outcome_b.call_result.total_tokens,
            json_valid=outcome_b.json_valid,
            schema_valid=outcome_b.schema_valid,
            business_valid=outcome_b.business_result["passed"] if outcome_b.business_result else None,
        ),
    ]

    st.markdown("### Karşılaştırma Özeti")
    st.caption(
        "Yalnızca bu çalıştırmadan elde edilen ölçülebilir teknik verilere "
        "dayanır. En iyi storyboard'u veya en doğru modeli belirlemez."
    )
    for line in build_comparison_summary(metrics):
        st.write(f"- {line}")


def render_selected_storyboard_editor(project) -> None:
    selected = st.session_state.a1_selected_storyboard
    if not selected:
        st.info(
            "Düzenlemek için yukarıdaki kartlardan birinde "
            "'Bu storyboard'u kullan' butonuna tıklayın (veya AI Görsel "
            "Analiz Modu'nda sonuçları storyboard'a aktarın)."
        )
        return

    st.markdown(f"**Seçilen model:** {selected['source_model_label']}")
    storyboard = selected["storyboard"]
    is_vision_storyboard = selected.get("source_model_id") == "vision_analysis"
    note_by_id = {s.image_id: s.note for s in project.screens}

    closing_key = "a1_sel_closing_text"
    if closing_key not in st.session_state:
        st.session_state[closing_key] = storyboard.get("closing_text", "")
    st.text_area("Kapanış metni", key=closing_key)
    storyboard["closing_text"] = st.session_state[closing_key]

    scenes = storyboard["scenes"]
    action = None
    ordered_scenes = sorted(scenes, key=lambda s: s["scene_number"])
    image_id_counts: Dict[str, int] = {}
    for s in ordered_scenes:
        image_id_counts[s["image_id"]] = image_id_counts.get(s["image_id"], 0) + 1

    for idx, scene in enumerate(ordered_scenes):
        image_id = scene["image_id"]
        scene_id = scene.get("scene_id", f"{image_id}_{idx}")
        with st.container(border=True):
            st.caption(f"scene_id: `{scene_id}`" + (" · (bu ekran birden fazla sahnede kullanılıyor)" if image_id_counts[image_id] > 1 else ""))
            cols = st.columns([1, 2, 2, 1])

            with cols[0]:
                image_bytes = st.session_state.a1_screen_bytes.get(image_id)
                if image_bytes:
                    st.image(image_bytes, width="stretch")
                st.caption(image_id)
                if not is_vision_storyboard:
                    st.caption(f"Kaynak not: {note_by_id.get(image_id, '—')}")
                if scene.get("matched_screen_id"):
                    st.caption(f"Eşleşen ekran: {scene['matched_screen_id']}")
                if scene.get("target_element_id"):
                    st.caption(f"Hedef öğe: {scene['target_element_id']}")

            with cols[1]:
                title_key = f"a1_sel_title_{scene_id}"
                if title_key not in st.session_state:
                    st.session_state[title_key] = scene["scene_title"]
                st.text_input("Sahne başlığı", key=title_key)
                scene["scene_title"] = st.session_state[title_key]

                if scene.get("action_type") is not None:
                    action_key = f"a1_sel_action_type_{scene_id}"
                    if action_key not in st.session_state:
                        st.session_state[action_key] = scene["action_type"]
                    st.selectbox(
                        "Eylem türü", sorted(ALLOWED_ACTION_TYPES), key=action_key
                    )
                    scene["action_type"] = st.session_state[action_key]

                if scene.get("instruction_text") is not None:
                    instruction_key = f"a1_sel_instruction_{scene_id}"
                    if instruction_key not in st.session_state:
                        st.session_state[instruction_key] = scene["instruction_text"]
                    st.text_area("Talimat", key=instruction_key, height=60)
                    scene["instruction_text"] = st.session_state[instruction_key]

                narration_key = f"a1_sel_narration_{scene_id}"
                if narration_key not in st.session_state:
                    st.session_state[narration_key] = scene["narration"]
                st.text_area("Anlatım (narration)", key=narration_key, height=80)
                scene["narration"] = st.session_state[narration_key]

                onscreen_key = f"a1_sel_onscreen_{scene_id}"
                if onscreen_key not in st.session_state:
                    st.session_state[onscreen_key] = scene["on_screen_text"]
                st.text_input(
                    "Ekran üstü metin (maks. 40 karakter)", key=onscreen_key, max_chars=40
                )
                scene["on_screen_text"] = st.session_state[onscreen_key]

                highlight_key = f"a1_sel_highlight_{scene_id}"
                if highlight_key not in st.session_state:
                    st.session_state[highlight_key] = scene["highlight_description"]
                st.text_input("Vurgu açıklaması", key=highlight_key)
                scene["highlight_description"] = st.session_state[highlight_key]
                st.caption(
                    "Vurgu (highlight) koordinatı: "
                    + ("belirtilmiş" if scene.get("highlight_rect") else "belirtilmemiş")
                )

                if scene.get("grounding_source_ids"):
                    st.caption("Grounding kaynakları: " + ", ".join(scene["grounding_source_ids"]))
                if scene.get("grounding_warnings"):
                    st.warning("; ".join(scene["grounding_warnings"]))

            with cols[2]:
                recommended = scene.get("recommended_duration_seconds")
                if recommended is not None:
                    st.caption(f"Önerilen süre (deterministik): {recommended} sn")

                duration_key = f"a1_sel_duration_{scene_id}"
                if duration_key not in st.session_state:
                    st.session_state[duration_key] = float(scene["duration_seconds"])
                st.number_input(
                    "Süre (sn)",
                    min_value=float(MIN_DURATION_SECONDS_SCHEMA),
                    max_value=float(MAX_DURATION_SECONDS_SCHEMA),
                    step=0.5,
                    key=duration_key,
                )
                scene["duration_seconds"] = st.session_state[duration_key]
                duration_warning = manual_duration_warning(scene["narration"], scene["duration_seconds"])
                if duration_warning:
                    st.warning(duration_warning)

                transition_key = f"a1_sel_transition_{scene_id}"
                if transition_key not in st.session_state:
                    st.session_state[transition_key] = scene["transition"]
                st.selectbox("Geçiş", ["fade", "cut"], key=transition_key)
                scene["transition"] = st.session_state[transition_key]

                zoom_key = f"a1_sel_zoom_{scene_id}"
                if zoom_key not in st.session_state:
                    st.session_state[zoom_key] = scene["zoom_enabled"]
                st.checkbox("Yakınlaştırma (zoom) etkin", key=zoom_key)
                scene["zoom_enabled"] = st.session_state[zoom_key]

                cursor_key = f"a1_sel_cursor_{scene_id}"
                if cursor_key not in st.session_state:
                    st.session_state[cursor_key] = bool(scene.get("cursor_enabled", False))
                st.checkbox("İmleç (cursor) etkin", key=cursor_key)
                scene["cursor_enabled"] = st.session_state[cursor_key]

                click_key = f"a1_sel_click_{scene_id}"
                if click_key not in st.session_state:
                    st.session_state[click_key] = bool(scene.get("click_effect_enabled", False))
                st.checkbox("Tıklama efekti etkin", key=click_key)
                scene["click_effect_enabled"] = st.session_state[click_key]

                review_key = f"a1_sel_review_{scene_id}"
                if review_key not in st.session_state:
                    st.session_state[review_key] = scene["requires_review"]
                st.checkbox("Gözden geçirme gerekli (requires_review)", key=review_key)
                scene["requires_review"] = st.session_state[review_key]
                if scene["requires_review"]:
                    st.warning("AI önerisi — doğrulanmalı")

            with cols[3]:
                st.write(f"Sıra: {scene['scene_number']}")
                if st.button("Yukarı taşı", key=f"a1_sel_up_{scene_id}", disabled=(idx == 0)):
                    action = ("up", idx)
                if st.button(
                    "Aşağı taşı", key=f"a1_sel_down_{scene_id}", disabled=(idx == len(ordered_scenes) - 1)
                ):
                    action = ("down", idx)
                if st.button("Sahneyi çoğalt", key=f"a1_sel_duplicate_{scene_id}"):
                    action = ("duplicate", idx)
                if st.button(
                    "Sahneyi kaldır", key=f"a1_sel_remove_{scene_id}", disabled=(len(ordered_scenes) <= 1)
                ):
                    action = ("remove", idx)

    if action:
        kind, idx = action
        if kind == "up":
            move_storyboard_scene_up(ordered_scenes, idx)
        elif kind == "down":
            move_storyboard_scene_down(ordered_scenes, idx)
        elif kind == "duplicate":
            duplicate_scene(ordered_scenes, idx)
        elif kind == "remove":
            remove_scene(ordered_scenes, idx)
        storyboard["scenes"] = ordered_scenes
        storyboard["total_duration_seconds"] = recalculate_total_duration(ordered_scenes)
        st.rerun()

    storyboard["total_duration_seconds"] = recalculate_total_duration(storyboard["scenes"])
    st.caption(f"Toplam süre (otomatik hesaplanır): {storyboard['total_duration_seconds']:.1f} sn")

    if st.button("Seçili Storyboard'u Doğrula", key="a1_validate_selected"):
        try:
            validate_storyboard(storyboard)
            business_result = None
            if not is_vision_storyboard:
                business_result = validate_storyboard_business_rules(storyboard, project, project.working_mode)
            st.session_state.a1_selected_validation = {
                "schema_valid": True,
                "schema_error": None,
                "business_result": business_result,
            }
        except ValidationError as exc:
            st.session_state.a1_selected_validation = {
                "schema_valid": False,
                "schema_error": "Pydantic doğrulama hatası:\n" + str(exc),
                "business_result": None,
            }
        st.rerun()

    validation = st.session_state.a1_selected_validation
    if validation:
        if validation["schema_valid"]:
            st.success("Pydantic doğrulaması: Geçti")
        else:
            st.error("Pydantic doğrulaması: Başarısız")
            with st.expander("Doğrulama hatası detayı"):
                st.code(validation["schema_error"])
        if validation["business_result"]:
            br = validation["business_result"]
            if br["passed"]:
                st.success(f"İş kuralı doğrulaması: Geçti ({br['scenes_validated']} sahne)")
            else:
                st.error("İş kuralı doğrulaması: Başarısız — " + "; ".join(br["errors"]))
            if br["warnings"]:
                st.warning("Uyarılar: " + "; ".join(br["warnings"]))
        elif is_vision_storyboard and validation["schema_valid"]:
            st.caption(
                "Bu storyboard AI Görsel Analiz Modu'ndan geldiği için grounded "
                "doğrulama zaten üretim sırasında yapıldı; burada yalnızca "
                "yapısal (şema) doğrulama tekrarlanır."
            )

    export_json = json.dumps(storyboard, ensure_ascii=False, indent=2)
    with st.expander("Seçili Storyboard JSON"):
        st.code(export_json, language="json")
    st.download_button(
        label="Seçili storyboard JSON indir",
        data=export_json,
        file_name="a1_selected_storyboard.json",
        mime="application/json",
        key="a1_download_selected_json",
    )

    narration_txt = build_narration_text(storyboard["title"], storyboard["scenes"], storyboard["closing_text"])
    st.download_button(
        label="Anlatım (narration) TXT indir",
        data=narration_txt,
        file_name="a1_narration.txt",
        mime="text/plain",
        key="a1_download_narration_txt",
    )


def render_storyboard_section(settings: dict) -> None:
    st.subheader("Storyboard Üretimi")

    project = validate_tutorial_project(st.session_state.a1_export)

    generate_clicked = st.button(
        "İki Modelle Storyboard Üret", type="primary", key="a1_storyboard_generate"
    )

    if generate_clicked:
        if not is_api_key_configured():
            st.error("API anahtarı bulunamadı. Lütfen .env dosyasında OPENAI_API_KEY tanımlayın.")
        elif not settings["model_b"]:
            st.error(
                "A1_MODEL_B ortam değişkeni tanımlı değil. Lütfen .env dosyasında "
                "Bedrock kataloğundaki gerçek Qwen3 32B model kimliğini "
                "A1_MODEL_B olarak tanımlayın."
            )
        else:
            system_prompt = load_storyboard_system_prompt()

            with st.spinner("Model A (Qwen3 235B A22B 2507) çalıştırılıyor..."):
                outcome_a = run_and_log_storyboard(settings["model_a"], system_prompt, project, settings)

            throttle_delay = float(os.environ.get("INTER_MODEL_DELAY_SECONDS", "1"))
            if throttle_delay > 0:
                time.sleep(throttle_delay)

            with st.spinner("Model B (Qwen3 32B) çalıştırılıyor..."):
                outcome_b = run_and_log_storyboard(settings["model_b"], system_prompt, project, settings)

            st.session_state.a1_storyboard_results = {
                "a": outcome_a,
                "b": outcome_b,
                "settings": settings,
                "project": project,
            }
            st.session_state.a1_selected_storyboard = None
            st.session_state.a1_selected_validation = None
            st.rerun()

    results = st.session_state.a1_storyboard_results
    if not results:
        st.info("Storyboard sonuçlarını görmek için 'İki Modelle Storyboard Üret' butonuna tıklayın.")
        return

    render_storyboard_comparison(results)

    col_a, col_b = st.columns(2)
    with col_a:
        render_storyboard_model_card(results["settings"]["model_a"], A1_PLAN_A, results["a"], results["project"])
    with col_b:
        render_storyboard_model_card(results["settings"]["model_b"], A1_PLAN_B, results["b"], results["project"])


def render_video_settings(project) -> tuple:
    st.subheader("Video Ayarları")

    col1, col2 = st.columns(2)
    with col1:
        resolution = st.selectbox(
            "Çözünürlük", list(RESOLUTION_OPTIONS.keys()), index=0, key="a1_video_resolution"
        )
    with col2:
        fps = st.selectbox("Kare hızı (FPS)", list(FPS_OPTIONS), index=0, key="a1_video_fps")

    subtitle_source_labels = list(SUBTITLE_SOURCE_OPTIONS.values())
    subtitle_source_values = list(SUBTITLE_SOURCE_OPTIONS.keys())
    default_subtitle_index = subtitle_source_values.index(DEFAULT_SUBTITLE_SOURCE)

    col3, col4 = st.columns(2)
    with col3:
        subtitle_source_label = st.selectbox(
            "Altyazı Kaynağı", subtitle_source_labels, index=default_subtitle_index, key="a1_video_subtitle_source"
        )
        subtitle_source = subtitle_source_values[subtitle_source_labels.index(subtitle_source_label)]
        scene_titles_enabled = st.checkbox(
            "Sahne başlıklarını göster", value=True, key="a1_video_scene_titles"
        )
    with col4:
        zoom_enabled = st.checkbox("Yakınlaştırma (zoom) efekti", value=True, key="a1_video_zoom")
        highlight_enabled = st.checkbox("Vurgu (highlight) efekti", value=True, key="a1_video_highlight")

    st.caption(
        "**Anlatım metni**: tam anlatım cümlesi altyazı olarak gösterilir "
        "(varsayılan). **Kısa ekran metni**: yalnızca ekran üstü çağrı metni "
        "gösterilir. Sahne başlığı, seçili altyazıyla neredeyse aynıysa "
        "tekrarı önlemek için o sahnede otomatik gizlenir."
    )
    st.caption(
        "Ekran görüntüsünün en-boy oranı video kareleriyle uyuşmadığında "
        "nötr koyu bir arka plan (letterbox/pillarbox) kullanılır."
    )

    default_filename_key = "a1_video_filename"
    if default_filename_key not in st.session_state:
        st.session_state[default_filename_key] = generate_safe_filename(project.title)
    output_filename = st.text_input("Çıktı dosya adı", key=default_filename_key)

    try:
        settings = validate_video_settings(
            {
                "resolution": resolution,
                "fps": fps,
                "subtitle_source": subtitle_source,
                "scene_titles_enabled": scene_titles_enabled,
                "zoom_enabled": zoom_enabled,
                "highlight_enabled": highlight_enabled,
                "output_filename": output_filename,
            }
        )
        return settings, None
    except ValidationError as exc:
        return None, "Video ayarları doğrulanamadı: " + str(exc)


def render_video_result(storyboard: dict) -> None:
    result = st.session_state.a1_video_result

    if not result:
        st.info("Videoyu oluşturmak için yukarıdan 'Videoyu Oluştur' butonuna tıklayın.")
        return

    if not result.success:
        st.error(result.error or "Video üretilemedi.")
        with st.expander("Teknik detaylar"):
            st.write(f"FFmpeg mevcut: {'Evet' if result.ffmpeg_available else 'Hayır'}")
            st.write(f"Geçici dosyalar temizlendi: {'Evet' if result.temp_files_cleaned else 'Hayır'}")
        return

    used_settings = st.session_state.a1_video_settings_used
    st.success("Video başarıyla oluşturuldu.")
    st.video(result.video_bytes)

    expected = result.expected_duration_seconds
    actual = result.actual_duration_seconds
    diff = abs(expected - actual) if actual is not None else None

    m1, m2, m3 = st.columns(3)
    m1.metric("Çözünürlük", used_settings.resolution if used_settings else "—")
    m2.metric("FPS", used_settings.fps if used_settings else "—")
    m3.metric("Dosya boyutu", f"{result.file_size_bytes / 1024:.0f} KB" if result.file_size_bytes else "—")

    m4, m5, m6 = st.columns(3)
    m4.metric("Beklenen süre", f"{expected:.1f} sn")
    m5.metric("Üretilen süre", f"{actual:.1f} sn" if actual is not None else "Ölçülemedi")
    m6.metric("Üretim süresi", f"{result.generation_seconds:.1f} sn" if result.generation_seconds else "—")

    if used_settings and used_settings.subtitle_source != "none":
        subtitle_source_display = SUBTITLE_SOURCE_OPTIONS.get(used_settings.subtitle_source, "—")
    else:
        subtitle_source_display = "Kapalı"

    st.write(
        f"**Altyazı kaynağı:** {subtitle_source_display} · "
        f"**Sahne başlıkları:** {'Açık' if used_settings and used_settings.scene_titles_enabled else 'Kapalı'} · "
        f"**Yakınlaştırma:** {'Etkin' if used_settings and used_settings.zoom_enabled else 'Kapalı'} · "
        f"**Vurgu:** {'Etkin' if used_settings and used_settings.highlight_enabled else 'Kapalı'}"
    )

    if diff is not None and diff > 1.0:
        st.warning(
            f"Beklenen süre ({expected:.1f} sn) ile üretilen video süresi "
            f"({actual:.1f} sn) arasında {diff:.1f} saniyelik fark var."
        )

    filename = used_settings.output_filename if used_settings else "a1_tutorial_video.mp4"
    st.download_button(
        label="MP4 indir",
        data=result.video_bytes,
        file_name=filename,
        mime="video/mp4",
        key="a1_video_download_mp4",
    )

    narration_txt = build_narration_text(storyboard["title"], storyboard["scenes"], storyboard["closing_text"])
    dl_col1, dl_col2 = st.columns(2)
    with dl_col1:
        st.download_button(
            label="Seçili storyboard JSON indir",
            data=json.dumps(storyboard, ensure_ascii=False, indent=2),
            file_name="a1_selected_storyboard.json",
            mime="application/json",
            key="a1_video_download_storyboard_json",
        )
    with dl_col2:
        st.download_button(
            label="Anlatım (narration) TXT indir",
            data=narration_txt,
            file_name="a1_narration.txt",
            mime="text/plain",
            key="a1_video_download_narration_txt",
        )

    with st.expander("Teknik detaylar"):
        st.write(f"Kullanılan kodlayıcı: {result.encoder}")
        st.write(f"FFmpeg mevcut: {'Evet' if result.ffmpeg_available else 'Hayır'}")
        st.write(f"Sahne sayısı: {result.scene_count}")
        st.write(f"Geçici dosyalar temizlendi: {'Evet' if result.temp_files_cleaned else 'Hayır'}")


def render_video_validation_help() -> None:
    with st.expander("Bu doğrulama sonuçları ne anlama geliyor?"):
        st.markdown(
            "**Video girdi doğrulaması**: Storyboard ile ekran "
            "görüntülerinin birebir eşleştiğini gösterir.\n\n"
            "**Render doğrulaması**: Sahne sürelerinin, çözünürlüğün ve "
            "görsellerin üretime uygun olduğunu gösterir.\n\n"
            "**Video süre kontrolü**: Üretilen MP4 süresinin storyboard "
            "toplamına yakın olup olmadığını gösterir.\n\n"
            "Bu kontroller videonun teknik olarak üretilebilir ve tutarlı "
            "olduğunu gösterir; anlatımın ürün sürecini eksiksiz temsil "
            "ettiğini garanti etmez."
        )


def render_video_section(project) -> None:
    selected = st.session_state.a1_selected_storyboard
    if not selected:
        return

    storyboard = selected["storyboard"]
    try:
        validate_storyboard(storyboard)
    except ValidationError as exc:
        st.markdown("---")
        st.info(
            "Video Ayarları, seçili storyboard geçerli bir şemaya uyduğunda "
            "gösterilir. Önce yukarıdaki 'Seçili Storyboard'u Doğrula' "
            "butonuyla kontrol edip hataları düzeltin."
        )
        with st.expander("Doğrulama hatası detayı"):
            st.code(str(exc))
        return

    st.markdown("---")
    settings, settings_error = render_video_settings(project)
    if settings_error:
        st.error(settings_error)
        return

    fingerprint = compute_video_state_fingerprint(storyboard, settings)

    if st.session_state.a1_video_result and st.session_state.a1_video_result.success and (
        st.session_state.a1_video_fingerprint != fingerprint
    ):
        st.warning("Storyboard veya video ayarları değişti. Güncel video için yeniden oluşturun.")

    ffmpeg_ok = is_ffmpeg_available()
    if not ffmpeg_ok:
        st.error(FFMPEG_MISSING_MESSAGE)

    input_validation = validate_video_inputs(storyboard, st.session_state.a1_screen_bytes)
    if not input_validation["passed"]:
        st.error("Video girdi doğrulaması başarısız: " + "; ".join(input_validation["errors"]))

    overlay_warnings = check_overlay_content_warnings(storyboard, settings)
    if overlay_warnings:
        st.warning(
            "Bazı bindirmeler bu haliyle görünmeyecek: " + " ".join(overlay_warnings)
        )

    generate_clicked = st.button(
        "Videoyu Oluştur",
        type="primary",
        key="a1_video_generate",
        disabled=(not ffmpeg_ok or not input_validation["passed"]),
    )

    if generate_clicked and ffmpeg_ok and input_validation["passed"]:
        if st.session_state.a1_video_generation_in_progress:
            st.warning("Video üretimi zaten devam ediyor.")
        else:
            st.session_state.a1_video_generation_in_progress = True
            try:
                with st.spinner("Video oluşturuluyor... (FFmpeg ile kodlanıyor)"):
                    result = generate_video(storyboard, st.session_state.a1_screen_bytes, settings)
            finally:
                st.session_state.a1_video_generation_in_progress = False

            st.session_state.a1_video_result = result
            if result.success:
                st.session_state.a1_video_fingerprint = fingerprint
                st.session_state.a1_video_settings_used = settings
                source_run_id = selected.get("source_run_id")
                if source_run_id:
                    save_video_generation(
                        source_run_id,
                        video_generated=True,
                        video_resolution=settings.resolution,
                        video_fps=settings.fps,
                        video_expected_duration=result.expected_duration_seconds,
                        video_actual_duration=result.actual_duration_seconds,
                        video_file_size_bytes=result.file_size_bytes,
                        video_generation_seconds=result.generation_seconds,
                        video_encoder=result.encoder,
                    )
            st.rerun()

    render_video_result(storyboard)
    render_video_validation_help()


def _build_neighbor_context(screens: list, index: int) -> str:
    parts = []
    if index > 0:
        prev = screens[index - 1]
        parts.append(f"Önceki ekran: {prev.get('scene_label') or prev['image_id']}")
    if index < len(screens) - 1:
        nxt = screens[index + 1]
        parts.append(f"Sonraki ekran: {nxt.get('scene_label') or nxt['image_id']}")
    return " · ".join(parts)


def run_and_log_grounded_vision(
    model_id: str,
    observation_system_prompt: str,
    grounded_system_prompt: str,
    screen: dict,
    order: int,
    overall_goal: str,
    target_audience: str,
    tone: str,
    neighbor_context: str,
    settings: dict,
    kb,
    workflow_id,
    expected_order,
) -> dict:
    image_bytes = st.session_state.a1_screen_bytes[screen["image_id"]]
    outcome = run_grounded_vision_analysis(
        model_id,
        observation_system_prompt,
        grounded_system_prompt,
        image_bytes,
        screen["image_id"],
        order,
        screen.get("scene_label"),
        screen.get("note"),
        overall_goal,
        target_audience,
        tone,
        kb,
        settings["temperature"],
        settings["max_tokens"],
        workflow_id=workflow_id,
        expected_order=expected_order,
        neighbor_context=neighbor_context,
    )

    # İki aşamalı akışta her aşama bağımsız bir gerçek API çağrısıdır; bağlantı
    # durumu her ikisi için de (sırayla) güncellenir.
    st.session_state.connection_status = next_connection_status(
        st.session_state.connection_status, outcome.observation_call_result
    )
    if outcome.grounded_call_result is not None:
        st.session_state.connection_status = next_connection_status(
            st.session_state.connection_status, outcome.grounded_call_result
        )

    business_passed = outcome.business_result["passed"] if outcome.business_result else None
    business_details = "; ".join(outcome.business_result["errors"]) if outcome.business_result else ""

    grounded = outcome.grounded
    target_match = outcome.target_match

    grounded_call = outcome.grounded_call_result
    overall_success = outcome.observation_call_result.success and (grounded_call.success if grounded_call else False)
    overall_error = outcome.observation_call_result.error or (grounded_call.error if grounded_call else None)

    # Görsel analiz baytları hiçbir koşulda CSV'ye yazılmaz; yalnızca sayısal/
    # metin ölçümler kaydedilir. Aşama 1 + Aşama 2 çağrılarının ölçümleri
    # toplanarak tek bir satırda kaydedilir (her ikisi de gerçek API çağrısıdır).
    run_id = log_evaluation(
        feature=FEATURE_NAME,
        model_id=model_id,
        input_tokens=_sum_call_metric(
            outcome.observation_call_result.input_tokens, grounded_call.input_tokens if grounded_call else None
        ),
        output_tokens=_sum_call_metric(
            outcome.observation_call_result.output_tokens, grounded_call.output_tokens if grounded_call else None
        ),
        total_tokens=_sum_call_metric(
            outcome.observation_call_result.total_tokens, grounded_call.total_tokens if grounded_call else None
        ),
        latency_ms=_sum_call_metric(
            outcome.observation_call_result.latency_ms, grounded_call.latency_ms if grounded_call else None
        ),
        estimated_cost_usd=_sum_call_metric(
            outcome.observation_call_result.estimated_cost_usd,
            grounded_call.estimated_cost_usd if grounded_call else None,
        ),
        json_valid=outcome.observation_json_valid and outcome.grounded_json_valid,
        schema_valid=outcome.observation_schema_valid and outcome.grounded_schema_valid,
        question_count=1,
        success=overall_success,
        error=overall_error,
        storyboard_validation_passed=business_passed,
        storyboard_validation_details=business_details,
        storyboard_scene_count=1,
        vision_matched_screen_id=grounded.matched_screen_id if grounded else None,
        vision_screen_match_score=grounded.screen_match_score if grounded else None,
        vision_target_element_id=grounded.target_element_id if grounded else None,
        vision_target_match_score=target_match.get("target_match_score") if target_match else None,
        vision_grounding_source_ids=", ".join(grounded.grounding_source_ids) if grounded else None,
        vision_grounding_warnings="; ".join(grounded.grounding_warnings) if grounded else None,
    )

    total_cost = _sum_call_metric(
        outcome.observation_call_result.estimated_cost_usd,
        grounded_call.estimated_cost_usd if grounded_call else None,
    )
    if total_cost:
        st.session_state.total_cost_usd += total_cost

    return {"run_id": run_id, "outcome": outcome}


def _grounded_from_selection(image_id: str):
    """Bu ekran için hangi Plan A/B önerisinin seçildiğini bulup, ona ait
    GroundedSceneResult nesnesini döner (bulunamazsa None)."""
    results = st.session_state.a1_vision_results.get(image_id)
    selected_model_label = st.session_state.a1_vision_selected_model.get(image_id)
    if not results or not selected_model_label:
        return None
    if selected_model_label == A1_VISION_PLAN_A.slot_label:
        return results["a"]["outcome"].grounded
    if selected_model_label == A1_VISION_PLAN_B.slot_label:
        return results["b"]["outcome"].grounded
    return None


def run_and_log_scene_expansion(
    model_id: str,
    system_prompt: str,
    grounded,
    kb,
    grounding_context,
    workflow_id,
    expected_order,
    title: str,
    target_audience: str,
    tone: str,
    user_note,
    settings: dict,
):
    """Tek bir eşleşmiş ekranı alt sahnelere genişletir ve teknik ölçümleri loglar.

    Ekran görüntüsü baytı bu çağrıya hiç gönderilmez (yalnızca metin); bu
    yüzden CSV'ye yazılan hiçbir alan görsel içerik barındırmaz.
    """
    outcome = run_scene_expansion(
        model_id, system_prompt, grounded, kb, grounding_context, workflow_id, expected_order,
        title, target_audience, tone, user_note, settings["temperature"], settings["max_tokens"],
    )

    st.session_state.connection_status = next_connection_status(
        st.session_state.connection_status, outcome.call_result
    )

    business_passed = outcome.business_result["passed"] if outcome.business_result else None
    business_details = "; ".join(outcome.business_result["errors"]) if outcome.business_result else ""
    expanded_scene_count = len(outcome.parsed.sub_scenes) if outcome.parsed else None

    log_evaluation(
        feature=FEATURE_NAME,
        model_id=model_id,
        input_tokens=outcome.call_result.input_tokens,
        output_tokens=outcome.call_result.output_tokens,
        total_tokens=outcome.call_result.total_tokens,
        latency_ms=outcome.call_result.latency_ms,
        estimated_cost_usd=outcome.call_result.estimated_cost_usd,
        json_valid=outcome.json_valid,
        schema_valid=outcome.schema_valid,
        question_count=1,
        success=outcome.call_result.success,
        error=outcome.call_result.error,
        storyboard_validation_passed=business_passed,
        storyboard_validation_details=business_details,
        expanded_scene_count=expanded_scene_count,
    )

    if outcome.call_result.estimated_cost_usd:
        st.session_state.total_cost_usd += outcome.call_result.estimated_cost_usd

    return outcome


def render_vision_validation_help() -> None:
    with st.expander("Bu doğrulama sonuçları ne anlama geliyor?"):
        st.markdown(
            "**JSON geçerli**: Her iki aşamanın (görsel gözlem ve grounded "
            "sahne üretimi) yanıtlarının JSON olarak okunabildiğini "
            "gösterir.\n\n"
            "**Pydantic doğrulaması**: Alanların, action_type değerinin, "
            "confidence aralığının ve vurgu koordinatlarının beklenen "
            "şemaya uyduğunu gösterir.\n\n"
            "**Bilgi tabanı eşleştirmesi**: matched_screen_id, "
            "target_element_id ve grounding_source_ids alanlarının modelin "
            "serbest metnine değil, yerel bilgi tabanı üzerinde çalışan "
            "deterministik bir eşleştirmeye dayandığını; bu alanların model "
            "yanıtı ne olursa olsun uygulama tarafından üzerine yazıldığını "
            "gösterir.\n\n"
            "**Deterministik grounded doğrulama**: Yanıttaki image_id'nin "
            "istenen ekranla eşleştiğini, eşleşen ekran/hedef öğenin onaylı "
            "bilgi tabanında var olduğunu, grounding kaynaklarının geçerli "
            "olduğunu, görsel gözlem ile grounded sonuç arasında bir hedef "
            "çakışması olup olmadığını, kaçınılması gereken terminoloji "
            "kullanılıp kullanılmadığını, güven skorunun düşük olup "
            "olmadığını ve ekranda doğrulanamayan kesin sonuç ifadelerini "
            "gösterir.\n\n"
            "**Alt sahne doğrulaması**: Aynı ekranın farklı hedeflere "
            "odaklanan birden fazla sahneye bölünebildiğini ve her sahnenin "
            "benzersiz bir scene_id taşıdığını gösterir.\n\n"
            "**Grounding doğrulaması**: Her alt sahnenin onaylı ekran, "
            "arayüz öğesi ve iş akışı bilgilerine dayandığını gösterir.\n\n"
            "**Süre tahmini**: Sahne süresinin anlatım uzunluğu ve eylem "
            "türüne göre deterministik olarak önerildiğini gösterir.\n\n"
            "Bu kontroller AI görsel analiz sonucunun teknik olarak ve "
            "bilgi tabanıyla tutarlı olduğunu gösterir; önerilen talimatın "
            "veya vurgu konumunun kesin olarak doğru olduğunu garanti "
            "etmez — bu yüzden her sonuç gözden geçirme (requires_review) "
            "gerektirir.\n\n"
            "Bu kontroller daha ayrıntılı ve tutarlı videolar üretmeye "
            "yardımcı olur; oluşturulan eğitim anlatımı yine kullanıcı "
            "tarafından gözden geçirilmelidir."
        )


GROUNDING_STATEMENT = (
    "Bilgi tabanı eşleştirmesi deterministik olarak yapılır. Model, eşleşen "
    "ekranın onaylı ürün bilgilerini kullanarak anlatımı oluşturur."
)


def render_vision_model_card(image_id: str, model_id: str, plan, outcome_entry: dict, screen: dict, kb) -> None:
    prices = load_model_prices()
    display_name = get_display_name(model_id, prices)
    outcome = outcome_entry["outcome"]
    observation_call = outcome.observation_call_result
    grounded_call = outcome.grounded_call_result

    st.markdown(f"##### {plan.heading}")
    st.caption(plan.subtitle)
    if display_name != plan.display_name:
        st.caption(f"Yapılandırılmış model: {display_name}")

    overall_success = observation_call.success and (grounded_call.success if grounded_call else False)
    if overall_success and outcome.grounded_schema_valid:
        st.success("Başarılı")
    elif overall_success and not outcome.grounded_schema_valid:
        st.warning("JSON alındı ancak şema doğrulaması başarısız")
    else:
        st.error("Başarısız")

    if observation_call.error:
        st.error(f"Aşama 1 (görsel gözlem) hatası: {observation_call.error}")
    if grounded_call is not None and grounded_call.error:
        st.error(f"Aşama 2 (grounded) hatası: {grounded_call.error}")

    total_tokens = _sum_call_metric(observation_call.total_tokens, grounded_call.total_tokens if grounded_call else None)
    total_latency = _sum_call_metric(observation_call.latency_ms, grounded_call.latency_ms if grounded_call else None)
    total_cost = _sum_call_metric(
        observation_call.estimated_cost_usd, grounded_call.estimated_cost_usd if grounded_call else None
    )

    m1, m2, m3 = st.columns(3)
    m1.metric("Toplam token (2 aşama)", total_tokens if total_tokens is not None else "Yok")
    latency_s = total_latency / 1000 if total_latency is not None else None
    m2.metric("Gecikme (sn, 2 aşama)", f"{latency_s:.2f}" if latency_s is not None else "Yok")
    m3.metric("Tahmini maliyet (2 aşama)", f"${total_cost:.6f}" if total_cost is not None else "Hesaplanamadı")

    st.markdown("---")
    st.markdown("**1. Görsel Gözlem**")
    if outcome.observation_schema_error:
        with st.expander("Görsel gözlem doğrulama hatası"):
            st.code(outcome.observation_schema_error)
    observation = outcome.observation
    if observation is not None:
        st.caption("Görünen öğeler: " + ", ".join(observation.visible_ui_elements))
        st.caption("Tespit edilen etiketler: " + ", ".join(observation.detected_visible_labels))
        st.write(f"Olası birincil hedef: {observation.possible_primary_target}")
        st.write(f"Ön eylem türü (preliminary_action_type): {observation.preliminary_action_type}")
        st.caption(f"Gözlem güven skoru: {observation.confidence:.2f}")
        if observation.visual_uncertainties:
            st.warning("Belirsizlikler: " + "; ".join(observation.visual_uncertainties))
    else:
        st.caption("Görsel gözlem alınamadı veya şema doğrulaması başarısız oldu.")

    st.markdown("**2. Bilgi Tabanı Eşleştirmesi**")
    screen_match = outcome.screen_match
    target_match = outcome.target_match
    if screen_match is not None:
        if screen_match.get("matched_screen_id"):
            matched_screen = get_screen(kb, screen_match["matched_screen_id"]) if kb is not None else None
            screen_display = matched_screen.screen_name if matched_screen else screen_match["matched_screen_id"]
            st.success(
                f"Eşleşen ekran: {screen_display} (`{screen_match['matched_screen_id']}`) — "
                f"skor: {screen_match['score']:.2f}"
            )
        else:
            st.warning("Kesin bir ekran eşleşmesi bulunamadı (skor eşik değerinin altında).")
        st.caption("Eşleşen etiketler: " + (", ".join(screen_match.get("matched_labels", [])) or "—"))
        if screen_match.get("candidate_screens"):
            st.caption(
                "Alternatif adaylar: "
                + ", ".join(f"{c['screen_id']} ({c['score']:.2f})" for c in screen_match["candidate_screens"])
            )
        for warning in screen_match.get("warnings", []):
            st.warning(warning)

        if target_match is not None:
            if target_match.get("target_element_id"):
                st.write(
                    f"Eşleşen arayüz öğesi: `{target_match['target_element_id']}` "
                    f"(skor: {target_match['target_match_score']:.2f})"
                )
            else:
                st.caption(
                    f"Hedef arayüz öğesi güvenilir biçimde eşleşmedi "
                    f"(en iyi skor: {target_match.get('target_match_score', 0.0):.2f})."
                )
            for warning in target_match.get("target_match_warnings", []):
                st.warning(warning)
    else:
        st.caption("Görsel gözlem başarısız olduğu için bilgi tabanı eşleştirmesi çalıştırılamadı.")

    st.markdown("**3. Grounded Sonuç**")
    grounded = outcome.grounded
    business_result = outcome.business_result
    if business_result is not None:
        if business_result["passed"]:
            st.success("Deterministik doğrulama: Geçti")
        else:
            st.error("Deterministik doğrulama: Başarısız — " + "; ".join(business_result["errors"]))
        if business_result["warnings"]:
            st.warning("Uyarılar: " + "; ".join(business_result["warnings"]))

    if grounded is not None:
        preview_bytes = build_highlight_preview(
            st.session_state.a1_screen_bytes[image_id], grounded.highlight_rect
        )
        st.image(preview_bytes, width="stretch")
        if grounded.highlight_rect is None:
            st.caption("Vurgu koordinatı belirtilmemiş (model emin olamadı).")

        st.markdown(f"**Sahne başlığı:** {grounded.scene_title}")
        if grounded.matched_screen_name:
            st.caption(f"Onaylı ekran adı: {grounded.matched_screen_name}")
        st.caption("Görünen öğeler: " + ", ".join(grounded.visible_ui_elements))
        st.write(f"**Birincil hedef:** {grounded.primary_target}")
        if grounded.target_element_id:
            st.caption(f"Eşleşen arayüz öğesi: `{grounded.target_element_id}`")
        st.write(f"**Eylem türü:** {grounded.action_type}")
        st.write(f"**Talimat:** {grounded.instruction_text}")
        st.write(f"**Anlatım:** {grounded.narration}")
        st.caption(f"Ekran üstü metin: {grounded.on_screen_text}")
        st.caption(f"Güven skoru: {grounded.confidence:.2f}")
        if grounded.grounding_source_ids:
            st.caption("Grounding kaynakları: " + ", ".join(grounded.grounding_source_ids))
        if grounded.requires_review:
            st.warning("AI önerisi — doğrulanmalı")

        st.info(GROUNDING_STATEMENT)

        if st.button(
            f"{plan.slot_label} önerisini kullan",
            key=f"a1_vision_use_{image_id}_{model_id}_{outcome_entry['run_id']}",
        ):
            scene_number = screen["order"]
            single_scene = grounded_result_to_storyboard_scene(grounded, scene_number)
            single_scene["scene_id"] = f"{image_id}_step_01"
            st.session_state.a1_vision_selected_scenes[image_id] = [single_scene]
            st.session_state.a1_vision_selected_model[image_id] = plan.slot_label
            # Yeni bir öneri seçildiğinde, bu ekran için önceki bir
            # genişletme önerisi varsa artık geçersizdir (farklı bir grounded
            # sonuca dayanıyor olabilir).
            st.session_state.a1_expansion_results.pop(image_id, None)
            st.success(f"{plan.slot_label} önerisi bu ekran için seçildi.")
    else:
        st.caption("Grounded sonuç üretilemediği için bu öneri seçilemez.")

    with st.expander("Modele gönderilen bilgi tabanı bağlamı"):
        if outcome.grounding_context is not None:
            st.json(outcome.grounding_context)
        else:
            st.caption("Bu ekran için bir bilgi tabanı bağlamı oluşturulmadı (ekran güvenilir biçimde eşleşmedi).")

    with st.expander("Bu grounded sonuç nasıl üretildi?"):
        st.markdown(
            "**Aşama 1 — Görsel Gözlem**: Model yalnızca ekranda gördüğü "
            "öğeleri, etiketleri ve olası birincil hedefi bildirir; ürün "
            "davranışı yorumu yapmaz.\n\n"
            "**Aşama 2 — Bilgi Tabanı Eşleştirmesi**: Tespit edilen "
            "etiketler (ve varsa olası hedef), yerel ve deterministik bir "
            "puanlama ile onaylı Mobixa ekranlarıyla (ve eşleşen ekranın "
            "arayüz öğeleriyle) karşılaştırılır. Bu adım hiçbir modele "
            "çağrı yapmaz.\n\n"
            "**Aşama 3 — Grounded Sahne Üretimi**: Model, görsel gözlem ve "
            "(varsa) eşleşen ekranın onaylı bilgi tabanı bağlamını "
            "kullanarak nihai sahneyi üretir. matched_screen_id, "
            "target_element_id ve grounding_source_ids alanları modelin "
            "serbest metnine güvenilmez; uygulama tarafından deterministik "
            "eşleştirme sonuçlarıyla üzerine yazılır.\n\n" + GROUNDING_STATEMENT
        )

    if observation_call.raw_text or (grounded_call and grounded_call.raw_text):
        with st.expander("Ham çıktı"):
            if observation_call.raw_text:
                st.caption("Aşama 1 (görsel gözlem):")
                st.code(observation_call.raw_text)
            if grounded_call and grounded_call.raw_text:
                st.caption("Aşama 2 (grounded):")
                st.code(grounded_call.raw_text)


def render_scene_expansion_section(image_id: str, screen: dict, kb, project, settings: dict) -> None:
    st.markdown("##### Ayrıntılı Sahne Oluşturma")

    selected_scenes = st.session_state.a1_vision_selected_scenes.get(image_id)
    if not selected_scenes:
        st.caption("Önce yukarıdan bir Plan A/B önerisi seçin.")
        return

    matched_screen_id = selected_scenes[0].get("matched_screen_id")
    if not matched_screen_id or kb is None:
        st.caption(
            "Bu ekran onaylı bilgi tabanıyla güvenilir biçimde eşleşmediği için "
            "ayrıntılı sahne oluşturma kullanılamaz."
        )
        return

    screen_record = get_screen(kb, matched_screen_id)
    approved_elements = get_ui_elements_for_screen(kb, matched_screen_id)
    st.caption(f"Eşleşen ekran: {screen_record.screen_name if screen_record else matched_screen_id}")
    st.caption(
        "Onaylı arayüz öğeleri: "
        + (", ".join(e.visible_label for e in approved_elements) if approved_elements else "—")
    )
    st.caption(f"Mevcut sahne sayısı: {len(selected_scenes)}")

    # Maliyet açısından varsayılan olarak yalnızca TEK bir model kullanılır
    # (Gemma 4 31B); Qwen3 235B seçilebilir bir alternatiftir. İkisi birden
    # otomatik olarak çağrılmaz (bu, ayrı bir karşılaştırma özelliği değildir).
    expansion_model_default = settings.get("expansion_model", "google.gemma-4-31b")
    expansion_model_alt = settings.get("expansion_alt_model", "qwen.qwen3-235b-a22b-2507")
    expansion_model_options = [expansion_model_default, expansion_model_alt]
    expansion_model_choice_key = f"a1_expand_model_choice_{image_id}"
    chosen_expansion_model = st.selectbox(
        "Genişletme modeli",
        expansion_model_options,
        index=0,
        key=expansion_model_choice_key,
        help="Varsayılan olarak Gemma 4 31B kullanılır (maliyet için tek model). "
        "Qwen3 235B alternatif olarak seçilebilir.",
    )

    if st.button("Bu ekranı ayrıntılı sahnelere böl", key=f"a1_expand_{image_id}"):
        grounded = _grounded_from_selection(image_id)
        if grounded is None:
            st.error("Genişletme için bu ekrana ait grounded sonuç bulunamadı.")
        else:
            workflow_id = st.session_state.get("a1_vision_workflow_choice")
            workflow_id = None if workflow_id in (None, "(seçilmedi)") else workflow_id
            expected_order = screen["order"] if workflow_id else None
            grounding_context = build_grounding_context(
                kb, matched_screen_id, workflow_id=workflow_id, step_order=expected_order
            )
            system_prompt = load_scene_expansion_system_prompt()
            with st.spinner("Alt sahneler oluşturuluyor..."):
                outcome = run_and_log_scene_expansion(
                    chosen_expansion_model, system_prompt, grounded, kb, grounding_context,
                    workflow_id, expected_order, project.title, project.target_audience, project.tone,
                    None, settings,
                )
            st.session_state.a1_expansion_results[image_id] = {"outcome": outcome}
            st.rerun()

    proposal = st.session_state.a1_expansion_results.get(image_id)
    if not proposal:
        return

    outcome = proposal["outcome"]
    if outcome.parsed is None:
        st.error("Alt sahne üretimi başarısız oldu veya şema doğrulaması geçmedi.")
        if outcome.call_result.error:
            st.error(outcome.call_result.error)
        if outcome.schema_error:
            with st.expander("Doğrulama hatası detayı"):
                st.code(outcome.schema_error)
        if st.button("Önerileri iptal et", key=f"a1_expand_cancel_failed_{image_id}"):
            st.session_state.a1_expansion_results.pop(image_id, None)
            st.rerun()
        return

    business_result = outcome.business_result
    if business_result is not None:
        if business_result["passed"]:
            st.success("Deterministik doğrulama: Geçti")
        else:
            st.error("Deterministik doğrulama: Başarısız — " + "; ".join(business_result["errors"]))
        if business_result["warnings"]:
            st.warning("Uyarılar: " + "; ".join(business_result["warnings"]))

    for sub_scene in outcome.parsed.sub_scenes:
        with st.container(border=True):
            st.markdown(f"**{sub_scene.scene_title}**")
            st.caption(
                f"Hedef öğe: {sub_scene.target_element_id or '—'} · Eylem türü: {sub_scene.action_type}"
            )
            st.write(f"Talimat: {sub_scene.instruction_text}")
            st.write(f"Anlatım: {sub_scene.narration}")
            st.caption(f"Ekran üstü metin: {sub_scene.on_screen_text}")
            st.caption("Grounding kaynakları: " + (", ".join(sub_scene.grounding_source_ids) or "—"))
            recommended = estimate_recommended_duration(sub_scene.narration, sub_scene.action_type)
            st.caption(f"Önerilen süre: {recommended} sn")
            st.caption(
                "Vurgu (highlight) durumu: "
                + ("belirtilmiş" if sub_scene.highlight_rect else "belirtilmemiş")
            )
            sub_warnings = [
                w[len(f"{sub_scene.sub_scene_key}: "):] if w.startswith(f"{sub_scene.sub_scene_key}: ") else w
                for w in (business_result["warnings"] if business_result else [])
                if w.startswith(f"{sub_scene.sub_scene_key}: ")
            ]
            if sub_warnings:
                st.warning("; ".join(sub_warnings))

            if st.button("Bu alt sahneyi ekle", key=f"a1_expand_add_{image_id}_{sub_scene.sub_scene_key}"):
                existing_ids = [
                    s["scene_id"]
                    for lst in st.session_state.a1_vision_selected_scenes.values()
                    for s in lst
                ]
                new_scene = expand_grounded_scene_to_storyboard_scenes(
                    image_id, [sub_scene], matched_screen_id, 1, business_result
                )[0]
                new_scene["scene_id"] = generate_unique_scene_id(image_id, existing_ids)
                st.session_state.a1_vision_selected_scenes[image_id].append(new_scene)
                st.session_state.a1_vision_selected_model[image_id] = (
                    f"Ayrıntılı ({len(st.session_state.a1_vision_selected_scenes[image_id])} alt sahne)"
                )
                st.success("Alt sahne eklendi.")
                st.rerun()

    apply_col, cancel_col = st.columns(2)
    with apply_col:
        if st.button("Tüm önerileri uygula", key=f"a1_expand_apply_all_{image_id}"):
            new_scenes = expand_grounded_scene_to_storyboard_scenes(
                image_id, outcome.parsed.sub_scenes, matched_screen_id, 1, business_result
            )
            st.session_state.a1_vision_selected_scenes[image_id] = new_scenes
            st.session_state.a1_vision_selected_model[image_id] = f"Ayrıntılı ({len(new_scenes)} alt sahne)"
            st.session_state.a1_expansion_results.pop(image_id, None)
            st.success(f"{len(new_scenes)} alt sahne bu ekran için uygulandı.")
            st.rerun()
    with cancel_col:
        if st.button("Önerileri iptal et", key=f"a1_expand_cancel_{image_id}"):
            st.session_state.a1_expansion_results.pop(image_id, None)
            st.rerun()


def render_vision_screen_block(screen: dict, order: int, kb, project, settings: dict) -> None:
    image_id = screen["image_id"]
    results = st.session_state.a1_vision_results.get(image_id)
    if not results:
        return

    with st.container(border=True):
        st.markdown(f"#### {order}. {screen.get('scene_label') or image_id}")
        st.image(st.session_state.a1_screen_bytes[image_id], width="stretch")

        outcome_a = results["a"]["outcome"]
        outcome_b = results["b"]["outcome"]
        metrics = [
            ModelMetrics(
                label=A1_VISION_PLAN_A.heading,
                cost=_sum_call_metric(
                    outcome_a.observation_call_result.estimated_cost_usd,
                    outcome_a.grounded_call_result.estimated_cost_usd if outcome_a.grounded_call_result else None,
                ),
                latency_ms=_sum_call_metric(
                    outcome_a.observation_call_result.latency_ms,
                    outcome_a.grounded_call_result.latency_ms if outcome_a.grounded_call_result else None,
                ),
                total_tokens=_sum_call_metric(
                    outcome_a.observation_call_result.total_tokens,
                    outcome_a.grounded_call_result.total_tokens if outcome_a.grounded_call_result else None,
                ),
                json_valid=outcome_a.observation_json_valid and outcome_a.grounded_json_valid,
                schema_valid=outcome_a.observation_schema_valid and outcome_a.grounded_schema_valid,
                business_valid=outcome_a.business_result["passed"] if outcome_a.business_result else None,
            ),
            ModelMetrics(
                label=A1_VISION_PLAN_B.heading,
                cost=_sum_call_metric(
                    outcome_b.observation_call_result.estimated_cost_usd,
                    outcome_b.grounded_call_result.estimated_cost_usd if outcome_b.grounded_call_result else None,
                ),
                latency_ms=_sum_call_metric(
                    outcome_b.observation_call_result.latency_ms,
                    outcome_b.grounded_call_result.latency_ms if outcome_b.grounded_call_result else None,
                ),
                total_tokens=_sum_call_metric(
                    outcome_b.observation_call_result.total_tokens,
                    outcome_b.grounded_call_result.total_tokens if outcome_b.grounded_call_result else None,
                ),
                json_valid=outcome_b.observation_json_valid and outcome_b.grounded_json_valid,
                schema_valid=outcome_b.observation_schema_valid and outcome_b.grounded_schema_valid,
                business_valid=outcome_b.business_result["passed"] if outcome_b.business_result else None,
            ),
        ]
        st.caption(
            "Karşılaştırma yalnızca ölçülebilir teknik verilere dayanır; "
            "hangi modelin daha doğru olduğunu belirlemez."
        )
        for line in build_comparison_summary(metrics):
            st.write(f"- {line}")
        confidences = [
            o.grounded.confidence
            for o in (outcome_a, outcome_b)
            if o.grounded is not None
        ]
        if confidences:
            avg_confidence = sum(confidences) / len(confidences)
            st.write(f"- Ortalama güven skoru: {avg_confidence:.2f}")

        selected_model = st.session_state.a1_vision_selected_model.get(image_id)
        if selected_model:
            st.info(f"Bu ekran için seçilen öneri: {selected_model}")

        col_a, col_b = st.columns(2)
        with col_a:
            render_vision_model_card(image_id, results["a_model_id"], A1_VISION_PLAN_A, results["a"], screen, kb)
        with col_b:
            render_vision_model_card(image_id, results["b_model_id"], A1_VISION_PLAN_B, results["b"], screen, kb)

        st.markdown("---")
        render_scene_expansion_section(image_id, screen, kb, project, settings)


def render_vision_section(project, settings: dict) -> None:
    st.subheader("AI Görsel Analiz")

    overall_goal_key = "a1_vision_overall_goal"
    st.text_input(
        "Genel amaç (opsiyonel)",
        key=overall_goal_key,
        placeholder="Örn. \"Yeni bir öğrenme yolculuğunun nasıl oluşturulduğunu anlat.\"",
    )
    overall_goal = st.session_state[overall_goal_key]

    kb = st.session_state.a1_kb
    workflow_id = None
    if kb is not None and kb.workflows:
        workflow_options = ["(seçilmedi)"] + [w.workflow_id for w in kb.workflows]
        default_index = workflow_options.index("create_journey") if "create_journey" in workflow_options else 0
        workflow_choice = st.selectbox(
            "İş akışı (opsiyonel — beklenen adım sırası eşleştirmesi için)",
            workflow_options,
            index=default_index,
            key="a1_vision_workflow_choice",
        )
        workflow_id = None if workflow_choice == "(seçilmedi)" else workflow_choice
        if workflow_id:
            st.caption(
                "Ekranların yükleme sırası, seçilen iş akışının adım sırasıyla "
                "eşleştirilecek (1. ekran = 1. adım, vb.); bu yalnızca "
                "deterministik ekran eşleştirmesine bir ek sinyal sağlar."
            )
    elif kb is None:
        st.caption("Bilgi tabanı yüklenemediği için iş akışı sırası kullanılamıyor.")
    else:
        st.caption("Bilgi tabanında tanımlı bir iş akışı bulunamadı; eşleştirme yalnızca ekran etiketlerine dayanacak.")

    st.warning(VISION_PRIVACY_WARNING)
    st.checkbox(VISION_PRIVACY_CONFIRM_LABEL, key="a1_vision_privacy_confirmed")

    vision_model_a = settings.get("vision_model_a")
    vision_model_b = settings.get("vision_model_b")

    can_generate = (
        is_api_key_configured()
        and bool(vision_model_a)
        and bool(vision_model_b)
        and st.session_state.a1_vision_privacy_confirmed
        and kb is not None
    )

    if not vision_model_a:
        st.error(
            "A1_VISION_MODEL_A ortam değişkeni tanımlı değil. Lütfen .env "
            "dosyasında Bedrock kataloğundaki gerçek Qwen3 VL model "
            "kimliğini A1_VISION_MODEL_A olarak tanımlayın."
        )
    if kb is None:
        st.error("Bilgi tabanı yüklenemediği için AI Görsel Analiz Modu (grounded) kullanılamıyor.")
    if not st.session_state.a1_vision_privacy_confirmed:
        st.caption("Görsel analiz çağrısı yapılmadan önce yukarıdaki onay kutusu işaretlenmelidir.")

    generate_clicked = st.button(
        "İki Modelle Görsel Analiz Yap", type="primary", key="a1_vision_generate", disabled=not can_generate
    )

    if generate_clicked and can_generate:
        if st.session_state.a1_vision_generation_in_progress:
            st.warning("Görsel analiz zaten devam ediyor.")
        else:
            st.session_state.a1_vision_generation_in_progress = True
            try:
                observation_system_prompt = load_vision_observation_system_prompt()
                grounded_system_prompt = load_vision_grounded_system_prompt()
                screens = sorted(project.screens, key=lambda s: s.order)
                screens_as_dicts = [
                    {"image_id": s.image_id, "scene_label": s.scene_label, "note": s.note} for s in screens
                ]
                throttle_delay = float(os.environ.get("INTER_MODEL_DELAY_SECONDS", "1"))

                for idx, screen in enumerate(screens_as_dicts):
                    neighbor_context = _build_neighbor_context(screens_as_dicts, idx)
                    order = screens[idx].order
                    expected_order = (idx + 1) if workflow_id else None

                    with st.spinner(f"{order}. ekran — Plan A analiz ediliyor (görsel gözlem + grounded)..."):
                        outcome_a = run_and_log_grounded_vision(
                            vision_model_a,
                            observation_system_prompt,
                            grounded_system_prompt,
                            screen,
                            order,
                            overall_goal,
                            project.target_audience,
                            project.tone,
                            neighbor_context,
                            settings,
                            kb,
                            workflow_id,
                            expected_order,
                        )
                    if throttle_delay > 0:
                        time.sleep(throttle_delay)

                    with st.spinner(f"{order}. ekran — Plan B analiz ediliyor (görsel gözlem + grounded)..."):
                        outcome_b = run_and_log_grounded_vision(
                            vision_model_b,
                            observation_system_prompt,
                            grounded_system_prompt,
                            screen,
                            order,
                            overall_goal,
                            project.target_audience,
                            project.tone,
                            neighbor_context,
                            settings,
                            kb,
                            workflow_id,
                            expected_order,
                        )
                    if throttle_delay > 0:
                        time.sleep(throttle_delay)

                    st.session_state.a1_vision_results[screen["image_id"]] = {
                        "a": outcome_a,
                        "b": outcome_b,
                        "a_model_id": vision_model_a,
                        "b_model_id": vision_model_b,
                    }
            finally:
                st.session_state.a1_vision_generation_in_progress = False
            st.rerun()

    if not st.session_state.a1_vision_results:
        st.info("Görsel analiz sonuçlarını görmek için 'İki Modelle Görsel Analiz Yap' butonuna tıklayın.")
        return

    bulk_col1, bulk_col2, bulk_col3 = st.columns(3)
    ordered_screens = sorted(project.screens, key=lambda s: s.order)
    with bulk_col1:
        if st.button("Tüm sahnelerde Plan A'yı kullan", key="a1_vision_apply_all_a"):
            for screen in ordered_screens:
                results = st.session_state.a1_vision_results.get(screen.image_id)
                if results and results["a"]["outcome"].grounded:
                    single_scene = grounded_result_to_storyboard_scene(results["a"]["outcome"].grounded, screen.order)
                    single_scene["scene_id"] = f"{screen.image_id}_step_01"
                    st.session_state.a1_vision_selected_scenes[screen.image_id] = [single_scene]
                    st.session_state.a1_vision_selected_model[screen.image_id] = A1_VISION_PLAN_A.slot_label
                    st.session_state.a1_expansion_results.pop(screen.image_id, None)
            st.rerun()
    with bulk_col2:
        if st.button("Tüm sahnelerde Plan B'yi kullan", key="a1_vision_apply_all_b"):
            for screen in ordered_screens:
                results = st.session_state.a1_vision_results.get(screen.image_id)
                if results and results["b"]["outcome"].grounded:
                    single_scene = grounded_result_to_storyboard_scene(results["b"]["outcome"].grounded, screen.order)
                    single_scene["scene_id"] = f"{screen.image_id}_step_01"
                    st.session_state.a1_vision_selected_scenes[screen.image_id] = [single_scene]
                    st.session_state.a1_vision_selected_model[screen.image_id] = A1_VISION_PLAN_B.slot_label
                    st.session_state.a1_expansion_results.pop(screen.image_id, None)
            st.rerun()
    with bulk_col3:
        expand_all_clicked = st.button(
            "Güvenle eşleşen tüm ekranları böl", key="a1_vision_expand_all_confident"
        )

    if expand_all_clicked:
        workflow_id = st.session_state.get("a1_vision_workflow_choice")
        workflow_id = None if workflow_id in (None, "(seçilmedi)") else workflow_id
        expansion_system_prompt = load_scene_expansion_system_prompt()
        expanded_any = False
        for screen in ordered_screens:
            selected_scenes = st.session_state.a1_vision_selected_scenes.get(screen.image_id)
            if not selected_scenes or len(selected_scenes) != 1:
                continue
            matched_screen_id = selected_scenes[0].get("matched_screen_id")
            if not matched_screen_id:
                continue
            grounded = _grounded_from_selection(screen.image_id)
            if grounded is None or grounded.screen_match_score < SCREEN_MATCH_WARNING_THRESHOLD:
                continue
            expected_order = screen.order if workflow_id else None
            grounding_context = build_grounding_context(
                kb, matched_screen_id, workflow_id=workflow_id, step_order=expected_order
            )
            expansion_outcome = run_and_log_scene_expansion(
                settings.get("expansion_model", "google.gemma-4-31b"), expansion_system_prompt, grounded, kb,
                grounding_context, workflow_id, expected_order, project.title, project.target_audience,
                project.tone, None, settings,
            )
            if expansion_outcome.parsed is not None:
                new_scenes = expand_grounded_scene_to_storyboard_scenes(
                    screen.image_id, expansion_outcome.parsed.sub_scenes, matched_screen_id, 1,
                    expansion_outcome.business_result,
                )
                st.session_state.a1_vision_selected_scenes[screen.image_id] = new_scenes
                st.session_state.a1_vision_selected_model[screen.image_id] = (
                    f"Ayrıntılı ({len(new_scenes)} alt sahne)"
                )
                expanded_any = True
        if expanded_any:
            st.success("Güvenle eşleşen ekranlar ayrıntılı alt sahnelere bölündü.")
        else:
            st.info("Güvenle eşleşen ve henüz genişletilmemiş bir ekran bulunamadı.")
        st.rerun()

    for idx, screen in enumerate(ordered_screens, start=1):
        render_vision_screen_block(
            {"image_id": screen.image_id, "scene_label": screen.scene_label, "order": screen.order},
            screen.order,
            kb,
            project,
            settings,
        )

    st.markdown("### Storyboard'a Aktarım")
    st.info(
        "Bir ekran görüntüsü birden fazla sahnede kullanılabilir. Her sahne "
        "farklı bir öğe veya işlemi açıklamalıdır."
    )

    missing = [
        s.image_id for s in ordered_screens if s.image_id not in st.session_state.a1_vision_selected_scenes
    ]
    if missing:
        st.info(
            "Storyboard'a aktarmadan önce her ekran için bir öneri seçin. "
            "Eksik ekranlar: " + ", ".join(missing)
        )

    if not missing:
        selected_lists = [st.session_state.a1_vision_selected_scenes[s.image_id] for s in ordered_screens]
        flat_preview = [sc for lst in selected_lists for sc in lst]
        unique_screenshot_count = len(ordered_screens)
        repeated_screenshot_count = sum(1 for lst in selected_lists if len(lst) > 1)
        grounded_scene_count = sum(1 for sc in flat_preview if sc.get("matched_screen_id"))
        scenes_requiring_review = sum(1 for sc in flat_preview if sc.get("requires_review"))
        scenes_with_highlights = sum(1 for sc in flat_preview if sc.get("highlight_rect"))
        estimated_total_duration = sum(sc["duration_seconds"] for sc in flat_preview)
        duration_warnings = [
            w
            for sc in flat_preview
            if (w := manual_duration_warning(sc.get("narration", ""), sc["duration_seconds"])) is not None
        ]

        st.markdown("#### Hazırlık Özeti")
        m1, m2, m3 = st.columns(3)
        m1.metric("Benzersiz ekran görüntüsü", unique_screenshot_count)
        m2.metric("Toplam sahne sayısı", len(flat_preview))
        m3.metric("Tekrar kullanılan ekran sayısı", repeated_screenshot_count)
        m4, m5, m6 = st.columns(3)
        m4.metric("Grounded (bilgi tabanına bağlı) sahne", grounded_scene_count)
        m5.metric("Gözden geçirme gerektiren sahne", scenes_requiring_review)
        m6.metric("Vurgulu (highlight) sahne", scenes_with_highlights)
        st.caption(f"Tahmini toplam süre: {estimated_total_duration:.1f} sn")
        if duration_warnings:
            st.warning(
                f"{len(duration_warnings)} sahnede seçili süre, anlatımın okunması için "
                "önerilenden kısa olabilir (video üretimi yine de mümkündür)."
            )

    if st.button(
        "Görsel analiz sonuçlarını storyboard'a aktar",
        type="primary",
        key="a1_vision_transfer",
        disabled=bool(missing),
    ):
        selected_lists = [
            copy.deepcopy(st.session_state.a1_vision_selected_scenes[s.image_id]) for s in ordered_screens
        ]
        flat_scenes = [sc for lst in selected_lists for sc in lst]
        for i, sc in enumerate(flat_scenes, start=1):
            sc["scene_number"] = i

        vision_storyboard = build_vision_storyboard(
            project.title, project.target_audience, project.tone, flat_scenes
        )
        vision_storyboard = migrate_scene_ids(vision_storyboard)

        st.session_state.a1_selected_storyboard = {
            "source_model_id": "vision_analysis",
            "source_model_label": "AI Görsel Analiz",
            "source_run_id": None,
            "storyboard": vision_storyboard,
        }
        st.session_state.a1_selected_validation = None

        repeated_screenshot_count = sum(1 for lst in selected_lists if len(lst) > 1)
        expanded_scene_count = sum(len(lst) for lst in selected_lists if len(lst) > 1)
        estimated_total_duration = sum(sc["duration_seconds"] for sc in flat_scenes)
        all_grounding_warnings = [w for sc in flat_scenes for w in sc.get("grounding_warnings", [])]
        log_evaluation(
            feature=FEATURE_NAME,
            model_id="scene_expansion_summary",
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            latency_ms=None,
            estimated_cost_usd=None,
            json_valid=True,
            schema_valid=True,
            question_count=len(flat_scenes),
            success=True,
            error=None,
            storyboard_scene_count=len(flat_scenes),
            storyboard_total_duration=int(round(estimated_total_duration)),
            expanded_scene_count=expanded_scene_count,
            unique_screenshot_count=len(ordered_screens),
            repeated_screenshot_count=repeated_screenshot_count,
            estimated_total_duration=estimated_total_duration,
            scene_expansion_applied=repeated_screenshot_count > 0,
            scene_expansion_warnings="; ".join(all_grounding_warnings),
        )

        st.success(
            "Görsel analiz sonuçları storyboard'a aktarıldı. Videoyu "
            "oluşturmadan önce aşağıdaki 'Seçili Storyboard' bölümünde "
            "gözden geçirip düzenleyin."
        )
        st.rerun()

    render_vision_validation_help()


def render_knowledge_base_help() -> None:
    with st.expander("Bu doğrulama sonuçları ne anlama geliyor?"):
        st.markdown(
            "**Bilgi tabanı doğrulaması**: Kayıtların birbiriyle tutarlı ve "
            "referanslarının geçerli olduğunu gösterir.\n\n"
            "**Ekran eşleştirmesi**: Görsel analizde tespit edilen "
            "etiketlerin hangi onaylı Mobixa ekranıyla en iyi eşleştiğini "
            "deterministik olarak hesaplar.\n\n"
            "**Grounding context**: Modele yalnızca ilgili ekranın, "
            "butonların ve iş akışı adımının onaylı bilgilerinin "
            "gönderileceğini gösterir.\n\n"
            "Bilgi tabanı, modelin Mobixa terminolojisini ve iş akışını "
            "daha doğru anlamasına yardımcı olur; görsel analiz sonucunun "
            "yine kullanıcı tarafından kontrol edilmesi gerekir."
        )


def render_knowledge_base_overview(kb) -> None:
    approved_screens = [s for s in kb.screens if s.status == "approved"]
    approved_elements = [e for e in kb.ui_elements if e.status == "approved"]
    approved_workflows = [w for w in kb.workflows if w.status == "approved"]

    product_version = approved_screens[0].product_version if approved_screens else "—"
    last_updated = max((s.last_updated for s in approved_screens), default="—")

    m1, m2, m3 = st.columns(3)
    m1.metric("Onaylı ekran sayısı", len(approved_screens))
    m2.metric("Onaylı arayüz öğesi sayısı", len(approved_elements))
    m3.metric("İş akışı sayısı", len(approved_workflows))

    m4, m5 = st.columns(2)
    m4.metric("Ürün sürümü", product_version)
    m5.metric("Son güncelleme", last_updated)


def render_knowledge_base_browser(kb) -> None:
    tab_screens, tab_elements, tab_workflows, tab_terms = st.tabs(
        ["Ekranlar", "Arayüz Öğeleri", "İş Akışları", "Terminoloji"]
    )

    with tab_screens:
        query = st.text_input("Ekranlarda ara", key="a1_kb_screen_search")
        for screen in kb.screens:
            haystack = f"{screen.screen_id} {screen.screen_name} {screen.product_area}".lower()
            if query and query.strip().lower() not in haystack:
                continue
            with st.container(border=True):
                st.markdown(f"**{screen.screen_name}** (`{screen.screen_id}`) — {screen.status}")
                st.caption(f"Alan: {screen.product_area} · Sürüm: {screen.product_version} · Roller: {', '.join(screen.supported_roles)}")
                st.write(screen.purpose)
                st.caption("Görünür etiketler: " + ", ".join(screen.visible_labels))

    with tab_elements:
        query = st.text_input("Arayüz öğelerinde ara", key="a1_kb_element_search")
        for element in kb.ui_elements:
            haystack = f"{element.element_id} {element.visible_label} {element.screen_id}".lower()
            if query and query.strip().lower() not in haystack:
                continue
            with st.container(border=True):
                st.markdown(f"**{element.visible_label}** (`{element.element_id}`) — {element.status}")
                st.caption(
                    f"Ekran: {element.screen_id} · Tür: {element.element_type} · Eylem: {element.action_type}"
                )
                st.write(element.purpose)
                if element.result_screen_id:
                    st.caption(f"Sonuç ekranı: {element.result_screen_id}")
                if element.notes:
                    st.caption(f"Not: {element.notes}")

    with tab_workflows:
        for workflow in kb.workflows:
            with st.container(border=True):
                st.markdown(f"**{workflow.title}** (`{workflow.workflow_id}`) — {workflow.status}")
                st.write(workflow.purpose)
                st.caption(f"Roller: {', '.join(workflow.supported_roles)} · Sürüm: {workflow.product_version}")
                for step in sorted(workflow.steps, key=lambda s: s.order):
                    st.write(f"{step.order}. [{step.screen_id}] {step.instruction}")

    with tab_terms:
        for term in kb.terminology:
            with st.container(border=True):
                st.markdown(f"**{term.canonical}**")
                if term.alternatives:
                    st.caption("Kabul edilen alternatifler: " + ", ".join(term.alternatives))
                if term.avoid:
                    st.caption("Kullanılmaması gerekenler: " + ", ".join(term.avoid))


def render_knowledge_base_match_tester(kb) -> None:
    st.markdown("#### Bilgi tabanı eşleştirmesini dene")
    st.caption("Bu test paneli hiçbir modele çağrı yapmaz; yalnızca yerel, deterministik eşleştirmeyi çalıştırır.")

    labels_input = st.text_input(
        "Görünür etiketler (virgülle ayrılmış)",
        key="a1_kb_test_labels",
        placeholder="Örn. Yolculuk Ekle, Durum, Dışa aktar",
    )

    col1, col2 = st.columns(2)
    with col1:
        workflow_options = ["(seçilmedi)"] + [w.workflow_id for w in kb.workflows]
        workflow_choice = st.selectbox("İş akışı (opsiyonel)", workflow_options, key="a1_kb_test_workflow")
    with col2:
        expected_order = st.number_input(
            "Beklenen adım sırası (opsiyonel, 0 = yok)", min_value=0, max_value=50, value=0, key="a1_kb_test_order"
        )

    if st.button("Eşleştirmeyi Çalıştır", key="a1_kb_test_run"):
        labels = [l.strip() for l in labels_input.split(",") if l.strip()]
        workflow_id = None if workflow_choice == "(seçilmedi)" else workflow_choice
        order = int(expected_order) if expected_order > 0 else None

        result = match_screen(kb, labels, workflow_id=workflow_id, expected_order=order)
        st.session_state.a1_kb_test_result = result

    result = st.session_state.get("a1_kb_test_result")
    if result:
        if result["matched_screen_id"]:
            st.success(f"Eşleşen ekran: {result['matched_screen_id']} (skor: {result['score']:.2f})")
        else:
            st.warning("Kesin bir ekran eşleşmesi bulunamadı (skor eşik değerinin altında).")
        st.write("Eşleşen etiketler: " + (", ".join(result["matched_labels"]) or "—"))
        st.write("Alternatif adaylar:")
        for candidate in result["candidate_screens"]:
            st.caption(f"- {candidate['screen_id']}: {candidate['score']:.2f}")
        for warning in result["warnings"]:
            st.warning(warning)

        if result["matched_screen_id"]:
            workflow_id = None if st.session_state.get("a1_kb_test_workflow", "(seçilmedi)") == "(seçilmedi)" else st.session_state["a1_kb_test_workflow"]
            order_value = st.session_state.get("a1_kb_test_order", 0)
            order = int(order_value) if order_value and order_value > 0 else None
            context = build_grounding_context(kb, result["matched_screen_id"], workflow_id=workflow_id, step_order=order)
            with st.expander("Oluşturulan grounding context"):
                st.json(context)


def render_knowledge_base_section() -> None:
    with st.expander("Ürün Bilgi Tabanı"):
        if st.session_state.a1_kb_error:
            st.error(
                "Bilgi tabanı yüklenemedi: " + st.session_state.a1_kb_error
            )
            return
        kb = st.session_state.a1_kb
        if kb is None:
            st.info("Bilgi tabanı henüz yüklenmedi.")
            return

        render_knowledge_base_overview(kb)
        st.markdown("---")
        render_knowledge_base_browser(kb)
        st.markdown("---")
        render_knowledge_base_match_tester(kb)
        render_knowledge_base_help()


def render_a1_page() -> None:
    init_session_state()
    render_language_switcher()
    lang = get_language()

    st.title(t("app.title"))
    st.subheader(t("a1.page_subtitle"))
    st.caption(
        "Gerçek ürün ekran görüntüleri ve kullanıcı notları kullanılarak "
        "güvenilir bir eğitim videosu projesi hazırlanır. Proje "
        "doğrulandıktan sonra iki modelle storyboard üretilebilir. Video "
        "üretimi ve Amazon Polly entegrasyonu sonraki adımlarda "
        "eklenecektir."
    )
    if lang == LANG_EN:
        st.info(t("a1.i18n_scope_notice"))

    settings = render_sidebar()

    render_knowledge_base_section()
    st.markdown("---")

    workflow_mode = render_workflow_mode_selector()
    meta = render_project_metadata()
    render_screenshot_upload()
    render_scene_list(workflow_mode)
    render_project_summary(meta)
    render_export(meta, workflow_mode)
    render_validation_help()

    if st.session_state.a1_export:
        st.markdown("---")
        project = validate_tutorial_project(st.session_state.a1_export)
        if workflow_mode == "vision":
            render_vision_section(project, settings)
        else:
            render_storyboard_section(settings)

        if st.session_state.a1_selected_storyboard:
            st.markdown("---")
            st.markdown("### Seçili Storyboard")
            render_selected_storyboard_editor(project)

        render_video_section(project)


render_a1_page()
