"""A1 — Otomatik Ürün Turu Stüdyosu.

Görsel bir ajanın çalışan uygulamayı gezip video kaydettiği stüdyo. Diğer
modüllerden iki önemli farkı vardır:

  1. İki modelli karşılaştırma YOKTUR — ajan her adımda tek bir karar verir,
     aynı turu iki modelle sürmek karşılaştırılabilir bir şey üretmez.
  2. İnsan değerlendirmesi YOKTUR — çıktı bir metin değil, izlenebilir bir
     videodur; şeffaflık adım dökümüyle sağlanır.

Ağır iş `services/tour_pipeline.py` içindedir; bu dosya yalnızca arayüzdür.
"""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from services.bedrock_client import (
    CONNECTION_MESSAGE_KEYS,
    CONNECTION_STATUS_LEVELS,
    CONNECTION_STATUS_NO_KEY,
    CONNECTION_STATUS_UNTESTED,
    is_api_key_configured,
)
from services.evaluation_logger import read_evaluations_csv
from services.i18n import LANG_EN, LANG_TR, get_language, render_language_switcher, t
from services.model_registry import A1_TOUR_DRIVER, resolve_model_route, route_display_label
from services.tour_pipeline import (
    DEFAULT_MAX_STEPS,
    TOUR_MODULES,
    load_existing_recordings,
    module_title,
    run_tour,
)
from services.tour_tts import NullTTS, get_tts_engine
from services.tour_video_service import is_ffmpeg_available

load_dotenv()

FEATURE_NAME = "A1"


def init_session_state() -> None:
    if "total_cost_usd" not in st.session_state:
        st.session_state.total_cost_usd = 0.0
    if "connection_status" not in st.session_state:
        st.session_state.connection_status = (
            CONNECTION_STATUS_UNTESTED if is_api_key_configured() else CONNECTION_STATUS_NO_KEY
        )
    if "a1_recording" not in st.session_state:
        st.session_state.a1_recording = None


def render_sidebar() -> dict:
    st.sidebar.title(t("common.sidebar_title"))

    if not is_api_key_configured():
        st.session_state.connection_status = CONNECTION_STATUS_NO_KEY
    elif st.session_state.connection_status == CONNECTION_STATUS_NO_KEY:
        st.session_state.connection_status = CONNECTION_STATUS_UNTESTED

    level = CONNECTION_STATUS_LEVELS[st.session_state.connection_status]
    st.sidebar.__getattribute__(level)(t(CONNECTION_MESSAGE_KEYS[st.session_state.connection_status]))

    lang = get_language()
    model_id = os.environ.get("A1_TOUR_MODEL", "google.gemma-4-31b")
    alt_model = os.environ.get("A1_TOUR_MODEL_ALT", "").strip()

    st.sidebar.markdown(f"**{t('common.region_label')}:** {os.environ.get('AWS_REGION', 'us-east-1')}")
    st.sidebar.markdown(f"**{A1_TOUR_DRIVER.slot_label_for(lang)}:** {A1_TOUR_DRIVER.display_name}")
    st.sidebar.caption(t("a1.driver_note"))

    with st.sidebar.expander(t("common.technical_details")):
        route = resolve_model_route(model_id)
        lines = [
            f"{t('a1.driver_label')}: {model_id}",
            f"  {route.provider} · {route.family} · {route_display_label(route.mantle_route)}",
            f"  Görsel destek: {'evet' if route.supports_vision else 'HAYIR'}",
        ]
        if alt_model:
            alt_route = resolve_model_route(alt_model)
            lines.append(f"Alternatif: {alt_model} ({route_display_label(alt_route.mantle_route)})")
        lines.append(f"FFmpeg: {'bulundu' if is_ffmpeg_available() else 'BULUNAMADI'}")
        st.code("\n".join(lines), language=None)

    st.sidebar.markdown("---")
    st.sidebar.download_button(
        label=t("common.download_csv_button"),
        data=read_evaluations_csv(),
        file_name="evaluations.csv",
        mime="text/csv",
        key="a1_download_csv",
    )
    st.sidebar.markdown("---")
    st.sidebar.caption(t("common.pricing_caption"))

    return {"model_id": model_id}


def render_settings() -> dict:
    st.subheader(t("a1.section.settings"))

    module_keys = list(TOUR_MODULES.keys())
    lang = get_language()

    col_module, col_lang = st.columns(2)
    with col_module:
        module = st.selectbox(
            t("a1.module_label"),
            module_keys,
            format_func=lambda key: module_title(key, lang),
            key="a1_module",
        )
    with col_lang:
        tour_language = st.selectbox(
            t("a1.language_label"),
            [LANG_TR, LANG_EN],
            format_func=lambda code: "Türkçe" if code == LANG_TR else "English",
            key="a1_tour_language",
        )

    col_steps, col_voice = st.columns(2)
    with col_steps:
        max_steps = st.number_input(
            t("a1.max_steps_label"),
            min_value=4,
            max_value=40,
            value=DEFAULT_MAX_STEPS,
            step=1,
            help=t("a1.max_steps_help"),
            key="a1_max_steps",
        )
    with col_voice:
        enable_voice = st.checkbox(
            t("a1.enable_voice_label"),
            value=True,
            help=t("a1.enable_voice_help"),
            key="a1_enable_voice",
        )

    tts = get_tts_engine(prefer_polly=enable_voice)
    if isinstance(tts, NullTTS):
        st.warning(t("a1.voice_unavailable").format(detail=tts.description))
    else:
        st.success(t("a1.voice_ready").format(detail=tts.description))

    if not is_ffmpeg_available():
        st.warning(t("a1.ffmpeg_missing"))

    st.info(t("a1.cost_warning").format(steps=int(max_steps)))

    return {
        "module": module,
        "language": tour_language,
        "max_steps": int(max_steps),
        "enable_voice": enable_voice,
    }


def _stage_message(progress) -> str:
    key = f"a1.stage.{progress.stage}"
    template = t(key)
    if template == key:  # bilinmeyen aşama — ham mesajı göster
        return progress.message or progress.stage
    return template.format(step=progress.step_index, message=progress.message)


def render_recording(settings: dict) -> None:
    st.subheader(t("a1.section.record"))

    if st.button(t("a1.record_button"), type="primary", key="a1_record"):
        if not is_api_key_configured():
            st.error(t("common.api_key_missing_error"))
            return

        try:
            import playwright  # noqa: F401,PLC0415 - yalnızca varlık kontrolü
        except ImportError:
            st.error(t("a1.playwright_missing"))
            return

        with st.status(t("a1.recording_status"), expanded=True) as status:
            preview = st.empty()

            def on_progress(progress) -> None:
                status.write(_stage_message(progress))
                if progress.narration:
                    status.caption(progress.narration)
                if progress.screenshot:
                    preview.image(progress.screenshot, use_container_width=True)

            try:
                recording = run_tour(
                    module=settings["module"],
                    language=settings["language"],
                    max_steps=settings["max_steps"],
                    enable_voice=settings["enable_voice"],
                    progress_callback=on_progress,
                )
            except Exception as exc:  # noqa: BLE001 - kayıt hatası sayfayı çökertmemeli
                status.update(label=t("a1.stage.error"), state="error")
                st.error(f"{type(exc).__name__}: {exc}")
                return

            preview.empty()
            status.update(label=t("a1.stage.finished"), state="complete")

        st.session_state.a1_recording = recording
        if recording.total_cost_usd:
            st.session_state.total_cost_usd += recording.total_cost_usd
        st.rerun()


def render_result() -> None:
    st.subheader(t("a1.section.result"))
    recording = st.session_state.a1_recording

    if recording is None:
        st.info(t("a1.result_none"))
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(t("a1.metric.steps"), recording.step_count)
    m2.metric(t("a1.metric.duration"), f"{recording.total_seconds:.1f}")
    m3.metric(
        t("a1.metric.cost"),
        f"${recording.total_cost_usd:.6f}" if recording.total_cost_usd else t("common.value.not_calculated"),
    )
    m4.metric(t("a1.metric.voiced"), t("a1.voiced_yes") if recording.voiced else t("a1.voiced_no"))

    if recording.stopped_reason:
        st.caption(f"{t('a1.stopped_reason_label')} {recording.stopped_reason}")
    if not recording.voiced and recording.voice_unavailable_reason:
        st.warning(t("a1.voice_unavailable").format(detail=recording.voice_unavailable_reason))

    video_path = Path(recording.video_path) if recording.video_path else None
    if video_path and video_path.exists():
        video_bytes = video_path.read_bytes()
        st.video(video_bytes)
        st.download_button(
            t("a1.download_video"),
            data=video_bytes,
            file_name=video_path.name,
            mime="video/mp4" if video_path.suffix == ".mp4" else "video/webm",
            key="a1_dl_video",
        )
    else:
        st.error(t("a1.result_video_missing").format(reason=recording.stopped_reason or "-"))

    subtitle_path = Path(recording.subtitle_path) if recording.subtitle_path else None
    if subtitle_path and subtitle_path.exists():
        st.download_button(
            t("a1.download_subtitle"),
            data=subtitle_path.read_text(encoding="utf-8"),
            file_name=subtitle_path.name,
            mime="text/plain",
            key="a1_dl_srt",
        )

    if recording.steps:
        st.markdown(f"#### {t('a1.section.steps')}")
        st.caption(t("a1.steps_caption"))
        st.dataframe(
            [
                {
                    t("a1.step_column.index"): step.index,
                    t("a1.step_column.action"): step.action,
                    t("a1.step_column.target"): step.element_name or "—",
                    t("a1.step_column.narration"): step.narration,
                    t("a1.step_column.reason"): step.reason,
                }
                for step in recording.steps
            ],
            width="stretch",
            hide_index=True,
        )


def render_library() -> None:
    st.subheader(t("a1.section.library"))
    recordings = load_existing_recordings()
    if not recordings:
        st.info(t("a1.library_empty"))
        return

    lang = get_language()
    for data in recordings:
        module = data.get("module", "?")
        with st.container(border=True):
            label = module_title(module, lang) if module in TOUR_MODULES else module
            st.markdown(f"**{label}** · `{data.get('language', '?')}`")
            st.caption(
                f"{data.get('total_seconds', 0)} sn · "
                f"{t('a1.metric.voiced')}: "
                f"{t('a1.voiced_yes') if data.get('voiced') else t('a1.voiced_no')}"
            )
            if data.get("is_stale"):
                st.warning(t("a1.library_stale"))
            else:
                st.success(t("a1.library_fresh"))

            path = Path(data["video_path"]) if data.get("video_path") else None
            if path and path.exists():
                st.video(path.read_bytes())


def render_a1_page() -> None:
    init_session_state()
    render_language_switcher()

    st.title(t("app.title"))
    st.subheader(t("a1.page_subtitle"))
    st.caption(t("a1.page_caption"))

    with st.expander(t("a1.how_it_works_title")):
        st.markdown(t("a1.how_it_works_body"))

    render_sidebar()
    settings = render_settings()
    render_recording(settings)
    render_result()
    render_library()


render_a1_page()
