"""B1 — İçerikten Otomatik Soru ve Aktivite Üretimi.

İki Bedrock modelini (Qwen3, Gemma) aynı içerik ve prompt ile
karşılaştırmalı olarak çalıştıran Streamlit sayfası. TR/EN dil desteği
`services/i18n.py` üzerinden sağlanır.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from pydantic import ValidationError

from schemas.b1_models import validate_b1_output
from services.bedrock_client import (
    CONNECTION_MESSAGE_KEYS,
    CONNECTION_STATUS_LEVELS,
    CONNECTION_STATUS_NO_KEY,
    CONNECTION_STATUS_UNTESTED,
    build_diagnostic_info,
    call_model,
    get_endpoint_region,
    is_api_key_configured,
    next_connection_status,
    region_display_name,
)
from services.comparison import ModelMetrics, build_comparison_summary
from services.cost_calculator import get_display_name, load_model_prices
from services.document_parser import extract_text
from services.evaluation_logger import log_evaluation, read_evaluations_csv, save_human_evaluation
from services.i18n import LANG_EN, get_language, render_language_switcher, t
from services.model_registry import PLAN_A, PLAN_B, resolve_model_route, route_display_label

load_dotenv()

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent / "sample_data"

FEATURE_NAME = "B1"

DIFFICULTY_KEYS = {
    "easy": "b1.difficulty.easy",
    "medium": "b1.difficulty.medium",
    "hard": "b1.difficulty.hard",
    "mixed": "b1.difficulty.mixed",
}


def load_system_prompt(language: str) -> str:
    filename = "b1_system_en.txt" if language == LANG_EN else "b1_system.txt"
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def build_user_prompt(
    content: str,
    question_count: int,
    difficulty: str,
    generate_cards: bool,
) -> str:
    difficulty_line = (
        t("b1.user_prompt.difficulty_mixed")
        if difficulty == "mixed"
        else t("b1.user_prompt.difficulty_fixed").format(difficulty=difficulty)
    )
    cards_line = t("b1.user_prompt.cards_yes") if generate_cards else t("b1.user_prompt.cards_no")
    return f"""{t("b1.user_prompt.content_label")}
---
{content}
---

{t("b1.user_prompt.instruction").format(count=question_count)}
{difficulty_line}
{cards_line}
"""


def init_session_state() -> None:
    if "total_cost_usd" not in st.session_state:
        st.session_state.total_cost_usd = 0.0
    if "results" not in st.session_state:
        st.session_state.results = None
    if "connection_status" not in st.session_state:
        st.session_state.connection_status = (
            CONNECTION_STATUS_UNTESTED if is_api_key_configured() else CONNECTION_STATUS_NO_KEY
        )
    if "b1_generation_in_progress" not in st.session_state:
        st.session_state.b1_generation_in_progress = False


def render_connection_test(model_a: str, model_b: str) -> None:
    """Tek bir modeli, kısa bir prompt ve düşük token limitiyle test eder.

    Bu, normal bir B1 üretim çalıştırması SAYILMAZ: `evaluations.csv`'ye
    yazmaz, oturum maliyetine eklenmez ve `st.session_state.results`'ı
    değiştirmez. Yalnızca bağlantının/modelin yanıt verip vermediğini ve ne
    kadar sürdüğünü göstermek içindir.
    """
    st.markdown("---")
    st.caption(t("b1.conn_test.caption"))
    test_choice = st.radio(
        t("b1.conn_test.radio_label"),
        [t("b1.conn_test.option_a"), t("b1.conn_test.option_b")],
        key="b1_conn_test_choice",
        horizontal=True,
    )
    test_model_id = model_a if test_choice == t("b1.conn_test.option_a") else model_b

    if st.button(t("b1.conn_test.button"), key="b1_conn_test_button"):
        if not is_api_key_configured():
            st.error(t("common.api_key_missing_error"))
        else:
            diagnostic = build_diagnostic_info(test_model_id)
            with st.spinner(t("b1.conn_test.spinner").format(choice=test_choice)):
                call_result = call_model(
                    test_model_id,
                    "You are a helpful assistant that gives short, direct answers.",
                    "Just write OK.",
                    temperature=0.0,
                    max_tokens=20,
                )

            st.write(f"**{t('b1.conn_test.endpoint_label')}** {diagnostic.endpoint_host}")
            st.write(
                f"**{t('b1.conn_test.region_label')}** "
                f"{region_display_name(diagnostic.region)} ({diagnostic.region})"
            )
            st.write(f"**{t('b1.conn_test.model_label')}** {diagnostic.model_id}")
            st.write(
                f"**{t('b1.conn_test.timeout_label')}** "
                + t("b1.conn_test.timeout_value").format(
                    connect=diagnostic.connect_timeout_seconds,
                    request=diagnostic.request_timeout_seconds,
                    retries=diagnostic.max_retries,
                )
            )
            latency_s = call_result.latency_ms / 1000 if call_result.latency_ms is not None else None
            latency_text = (
                t("b1.conn_test.latency_value").format(latency=latency_s)
                if latency_s is not None
                else t("common.value.none")
            )
            st.write(f"**{t('b1.conn_test.latency_label')}** {latency_text}")

            if call_result.api_call_success:
                st.success(
                    t("b1.conn_test.success").format(snippet=(call_result.raw_text or "").strip()[:200])
                )
            else:
                st.error(
                    t("b1.conn_test.failure").format(
                        category=call_result.error_category or "unknown", error=call_result.error
                    )
                )


def render_sidebar() -> dict:
    st.sidebar.title(t("common.sidebar_title"))

    # API anahtarı .env üzerinden sonradan eklenip session yeniden
    # çalıştırılırsa "no_key" durumundan çıkılabilsin.
    if not is_api_key_configured():
        st.session_state.connection_status = CONNECTION_STATUS_NO_KEY
    elif st.session_state.connection_status == CONNECTION_STATUS_NO_KEY:
        st.session_state.connection_status = CONNECTION_STATUS_UNTESTED

    level = CONNECTION_STATUS_LEVELS[st.session_state.connection_status]
    message = t(CONNECTION_MESSAGE_KEYS[st.session_state.connection_status])
    getattr(st.sidebar, level)(message)

    # Bölge, AWS_REGION yerine gerçek OPENAI_BASE_URL uç noktasından
    # türetilir; böylece AWS_REGION yanlışlıkla eski bir değerde kalsa bile
    # sidebar gerçek uç noktayı yansıtır.
    region = get_endpoint_region()
    # Seçici Gemma 4 göçü: Plan A = Qwen3 235B (korunur), Plan B = Gemma 4 31B
    # (yeni). Eski paylaşımlı TEXT_MODEL_A/B ortam değişkenleri geriye dönük
    # uyumluluk için hâlâ okunur (B1_MODEL_A/B ayarlanmamışsa).
    model_a = os.environ.get("B1_MODEL_A") or os.environ.get("TEXT_MODEL_A", "qwen.qwen3-235b-a22b-2507")
    model_b = os.environ.get("B1_MODEL_B") or os.environ.get("TEXT_MODEL_B", "google.gemma-4-31b")
    fallback_model = os.environ.get("B1_FALLBACK_MODEL", "qwen.qwen3-32b")

    lang = get_language()
    st.sidebar.markdown(f"**{t('common.region_label')}:** {region_display_name(region)} ({region})")
    st.sidebar.markdown(f"**{PLAN_A.slot_label_for(lang)}:** {PLAN_A.display_name}")
    st.sidebar.markdown(f"**{PLAN_B.slot_label_for(lang)}:** {PLAN_B.display_name}")
    st.sidebar.caption(t("common.comparison_note"))

    with st.sidebar.expander(t("common.technical_details")):
        route_a = resolve_model_route(model_a)
        route_b = resolve_model_route(model_b)
        st.code(
            f"Model A: {model_a}\n"
            f"  Sağlayıcı: {route_a.provider} · Aile: {route_a.family} · "
            f"Rota: {route_display_label(route_a.mantle_route)}\n"
            f"Model B: {model_b}\n"
            f"  Sağlayıcı: {route_b.provider} · Aile: {route_b.family} · "
            f"Rota: {route_display_label(route_b.mantle_route)}\n"
            f"Teknik yedek (fallback): {fallback_model} (yalnızca burada gösterilir; "
            "normal karşılaştırmada aktif bir plan olarak kullanılmaz)",
            language=None,
        )
        render_connection_test(model_a, model_b)

    temperature = st.sidebar.slider(t("common.temperature_label"), 0.0, 1.0, 0.2, 0.05)
    max_tokens = st.sidebar.number_input(
        t("common.max_tokens_label"), min_value=256, max_value=8000, value=2000, step=100
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**{t('common.session_cost_label')}** ${st.session_state.total_cost_usd:.6f}")
    st.sidebar.caption(
        "Bu tutar yalnızca mevcut oturumda yapılan başarılı model çağrılarını "
        "içerir. Sıfırlamak CSV geçmişini etkilemez."
        if lang != LANG_EN
        else "This amount only includes successful model calls made in the "
        "current session. Resetting does not affect the CSV history."
    )
    if st.sidebar.button(t("common.reset_cost_button")):
        st.session_state.total_cost_usd = 0.0
        st.rerun()

    st.sidebar.markdown("---")
    csv_content = read_evaluations_csv()
    st.sidebar.download_button(
        label=t("common.download_csv_button"),
        data=csv_content,
        file_name="evaluations.csv",
        mime="text/csv",
    )

    st.sidebar.markdown("---")
    st.sidebar.caption(t("common.pricing_caption"))

    return {
        "model_a": model_a,
        "model_b": model_b,
        "temperature": temperature,
        "max_tokens": int(max_tokens),
    }


def render_content_input() -> str:
    st.subheader(t("b1.section.content_input"))
    source_options = [
        t("b1.content_source.paste"),
        t("b1.content_source.upload"),
        t("b1.content_source.sample"),
    ]
    source = st.radio(t("b1.content_source_label"), source_options, horizontal=True)

    content = ""
    if source == t("b1.content_source.paste"):
        content = st.text_area(t("b1.content_paste_label"), height=250)
    elif source == t("b1.content_source.upload"):
        uploaded = st.file_uploader(t("b1.file_uploader_label"), type=["txt", "pdf", "docx", "pptx"])
        if uploaded is not None:
            result = extract_text(uploaded.getvalue(), uploaded.name)
            if result.success:
                content = result.text
                st.success(t("b1.file_extract_success").format(count=len(content)))
                with st.expander(t("b1.file_extract_preview")):
                    st.text(content[:3000])
            else:
                st.error(result.error)
    else:
        sample_path = SAMPLE_DATA_DIR / "information_security.txt"
        content = sample_path.read_text(encoding="utf-8")
        st.info(t("b1.sample_text_info"))
        with st.expander(t("b1.sample_text_preview")):
            st.text(content)

    return content


def render_generation_settings() -> dict:
    st.subheader(t("b1.section.generation_settings"))
    col1, col2, col3 = st.columns(3)
    with col1:
        question_count = st.number_input(t("b1.question_count_label"), min_value=1, max_value=15, value=5)
    with col2:
        difficulty = st.selectbox(
            t("b1.difficulty_label"), ["easy", "medium", "hard", "mixed"], format_func=lambda v: t(DIFFICULTY_KEYS[v])
        )
    with col3:
        generate_cards = st.checkbox(t("b1.generate_cards_label"), value=True)

    return {
        "question_count": int(question_count),
        "difficulty": difficulty,
        "generate_cards": generate_cards,
    }


def run_model_and_validate(
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    expected_question_count: int,
    expect_learning_cards: bool,
) -> dict:
    call_result = call_model(model_id, system_prompt, user_prompt, temperature, max_tokens)

    st.session_state.connection_status = next_connection_status(
        st.session_state.connection_status, call_result
    )

    schema_valid = False
    schema_error = None
    validated = None

    if call_result.success and call_result.parsed_json is not None:
        try:
            validated = validate_b1_output(
                call_result.parsed_json, expected_question_count, expect_learning_cards
            )
            schema_valid = True
        except ValidationError as exc:
            schema_error = "Pydantic doğrulama hatası:\n" + str(exc)
        except ValueError as exc:
            schema_error = str(exc)

    json_valid = call_result.parsed_json is not None
    question_count = len(validated.questions) if validated else 0

    run_id = log_evaluation(
        feature=FEATURE_NAME,
        model_id=model_id,
        input_tokens=call_result.input_tokens,
        output_tokens=call_result.output_tokens,
        total_tokens=call_result.total_tokens,
        latency_ms=call_result.latency_ms,
        estimated_cost_usd=call_result.estimated_cost_usd,
        json_valid=json_valid,
        schema_valid=schema_valid,
        question_count=question_count,
        success=call_result.success,
        error=call_result.error,
    )

    if call_result.estimated_cost_usd:
        st.session_state.total_cost_usd += call_result.estimated_cost_usd

    return {
        "run_id": run_id,
        "call_result": call_result,
        "schema_valid": schema_valid,
        "schema_error": schema_error,
        "validated": validated,
        "json_valid": json_valid,
    }


def render_validation_help() -> None:
    with st.expander(t("b1.validation_help.title")):
        st.markdown(t("b1.validation_help.body"))


def render_human_evaluation(run_id: str) -> None:
    st.markdown(f"#### {t('b1.human_eval.title')}")

    key_answer = f"human_answer_{run_id}"
    key_ground = f"human_ground_{run_id}"
    key_lang = f"human_lang_{run_id}"
    key_notes = f"human_notes_{run_id}"

    not_evaluated = t("b1.human_eval.not_evaluated")
    yes, no, partial = t("common.yes"), t("common.no"), t("b1.human_eval.partial")

    st.selectbox(t("b1.human_eval.answer_key_label"), [not_evaluated, yes, no], key=key_answer)
    st.selectbox(
        t("b1.human_eval.groundedness_label"),
        [not_evaluated, yes, partial, no],
        key=key_ground,
    )
    st.slider(t("b1.human_eval.language_quality_label"), 1, 5, 3, key=key_lang)
    st.text_area(t("b1.human_eval.notes_label"), key=key_notes, height=80)

    if st.button(t("b1.human_eval.save_button"), key=f"save_human_{run_id}"):
        saved = save_human_evaluation(
            run_id=run_id,
            answer_key_correct=st.session_state[key_answer],
            groundedness=st.session_state[key_ground],
            language_quality=st.session_state[key_lang],
            notes=st.session_state[key_notes],
        )
        if saved:
            st.success(t("b1.human_eval.saved"))
        else:
            st.error(t("b1.human_eval.save_failed"))


def render_model_card(model_id: str, plan, outcome: dict) -> None:
    prices = load_model_prices()
    display_name = get_display_name(model_id, prices)
    call_result = outcome["call_result"]
    lang = get_language()

    st.markdown(f"### {plan.heading_for(lang)}")
    st.caption(plan.subtitle_for(lang))
    if display_name != plan.display_name:
        st.caption(t("b1.configured_model_caption").format(name=display_name))

    if call_result.success and outcome["schema_valid"]:
        st.success(t("common.status.success"))
    elif call_result.success and not outcome["schema_valid"]:
        st.warning(t("common.status.json_received_schema_failed"))
    else:
        st.error(t("common.status.failed"))

    if call_result.error:
        st.error(call_result.error)

    none_value = t("common.value.none")
    m1, m2, m3 = st.columns(3)
    m1.metric(t("common.metric.input_tokens"), call_result.input_tokens if call_result.input_tokens is not None else none_value)
    m2.metric(t("common.metric.output_tokens"), call_result.output_tokens if call_result.output_tokens is not None else none_value)
    m3.metric(t("common.metric.total_tokens"), call_result.total_tokens if call_result.total_tokens is not None else none_value)

    m4, m5 = st.columns(2)
    latency_s = call_result.latency_ms / 1000 if call_result.latency_ms is not None else None
    m4.metric(t("common.metric.latency"), f"{latency_s:.2f}" if latency_s is not None else none_value)
    cost = call_result.estimated_cost_usd
    m5.metric(t("common.metric.cost"), f"${cost:.6f}" if cost is not None else t("common.value.not_calculated"))

    yes, no = t("common.yes"), t("common.no")
    st.write(f"**{t('common.json_valid_label')}** {yes if outcome['json_valid'] else no}")
    st.write(f"**{t('common.pydantic_label')}** {t('common.status.passed') if outcome['schema_valid'] else t('common.status.failed')}")
    if outcome["schema_error"]:
        with st.expander(t("common.validation_error_expander")):
            st.caption(t("common.raw_text_language_note"))
            st.code(outcome["schema_error"])

    validated = outcome["validated"]
    if validated:
        st.markdown(f"**{t('b1.title_label')}** {validated.title}")

        st.markdown(f"#### {t('b1.section.questions')}")
        for i, q in enumerate(validated.questions, start=1):
            with st.container(border=True):
                st.markdown(f"**{i}. {q.question}**")
                for j, opt in enumerate(q.options, start=1):
                    marker = "✅" if j == q.correct_answer else "▫️"
                    st.write(f"{marker} {j}. {opt}")
                st.caption(f"{t('b1.explanation_label')} {q.explanation}")
                st.caption(f"{t('b1.source_quote_label')} \"{q.source_quote}\"")
                difficulty_label = t(DIFFICULTY_KEYS.get(q.difficulty, "b1.difficulty.mixed"))
                st.caption(t("b1.category_meta").format(difficulty=difficulty_label, category=q.category))

        if validated.learning_cards:
            st.markdown(f"#### {t('b1.section.learning_cards')}")
            for card in validated.learning_cards:
                with st.container(border=True):
                    st.markdown(f"**{card.title}**")
                    st.write(card.content)
                    st.caption(f"{t('b1.key_takeaway_label')} {card.key_takeaway}")

    if call_result.raw_text:
        with st.expander(t("common.raw_output_expander")):
            st.code(call_result.raw_text)

    if call_result.parsed_json:
        st.download_button(
            label=t("common.download_json_button"),
            data=json.dumps(call_result.parsed_json, ensure_ascii=False, indent=2),
            file_name=f"{model_id.replace('.', '_')}_output.json",
            mime="application/json",
            key=f"download_{model_id}_{outcome['run_id']}",
        )

    render_validation_help()
    render_human_evaluation(outcome["run_id"])


def render_comparison_summary(results: dict) -> None:
    outcome_a = results["a"]
    outcome_b = results["b"]
    lang = get_language()

    metrics = [
        ModelMetrics(
            label=PLAN_A.heading_for(lang),
            cost=outcome_a["call_result"].estimated_cost_usd,
            latency_ms=outcome_a["call_result"].latency_ms,
            total_tokens=outcome_a["call_result"].total_tokens,
            json_valid=outcome_a["json_valid"],
            schema_valid=outcome_a["schema_valid"],
        ),
        ModelMetrics(
            label=PLAN_B.heading_for(lang),
            cost=outcome_b["call_result"].estimated_cost_usd,
            latency_ms=outcome_b["call_result"].latency_ms,
            total_tokens=outcome_b["call_result"].total_tokens,
            json_valid=outcome_b["json_valid"],
            schema_valid=outcome_b["schema_valid"],
        ),
    ]

    st.markdown(f"### {t('common.comparison_title')}")
    st.caption(t("common.comparison_caption"))
    for line in build_comparison_summary(metrics, lang=lang):
        st.write(f"- {line}")


def render_b1_page() -> None:
    init_session_state()
    render_language_switcher()
    lang = get_language()

    st.title(t("app.title"))
    st.subheader(t("b1.page_subtitle"))

    settings = render_sidebar()
    content = render_content_input()
    gen_settings = render_generation_settings()

    st.subheader(t("b1.section.generation"))
    generate_clicked = st.button(t("b1.generate_button"), type="primary")

    if generate_clicked:
        if not content or not content.strip():
            st.error(t("b1.error.no_content"))
        elif not is_api_key_configured():
            st.error(t("common.api_key_missing_error"))
        elif st.session_state.b1_generation_in_progress:
            st.warning(t("b1.warning.generation_in_progress"))
        else:
            st.session_state.b1_generation_in_progress = True
            # Sonuçlar her model tamamlandıkça kademeli olarak yazılır; bu
            # sayede Model B beklenmedik bir şekilde çökerse bile Model A'nın
            # sonucu kaybolmaz (kısmi sonuç görünürlüğü).
            st.session_state.results = {"a": None, "b": None, "settings": settings}
            try:
                system_prompt = load_system_prompt(lang)
                user_prompt = build_user_prompt(
                    content,
                    gen_settings["question_count"],
                    gen_settings["difficulty"],
                    gen_settings["generate_cards"],
                )

                with st.spinner(t("b1.spinner.model_a")):
                    outcome_a = run_model_and_validate(
                        settings["model_a"],
                        system_prompt,
                        user_prompt,
                        settings["temperature"],
                        settings["max_tokens"],
                        gen_settings["question_count"],
                        gen_settings["generate_cards"],
                    )
                st.session_state.results["a"] = outcome_a

                throttle_delay = float(os.environ.get("INTER_MODEL_DELAY_SECONDS", "1"))
                if throttle_delay > 0:
                    time.sleep(throttle_delay)

                with st.spinner(t("b1.spinner.model_b")):
                    outcome_b = run_model_and_validate(
                        settings["model_b"],
                        system_prompt,
                        user_prompt,
                        settings["temperature"],
                        settings["max_tokens"],
                        gen_settings["question_count"],
                        gen_settings["generate_cards"],
                    )
                st.session_state.results["b"] = outcome_b
            finally:
                # generation_in_progress her koşulda (başarı, model hatası
                # veya beklenmeyen bir istisna) temizlenir; spinner asla
                # kalıcı olarak takılı kalmaz.
                st.session_state.b1_generation_in_progress = False

            # Sidebar (bağlantı durumu, oturum maliyeti) bu script çalışmasının
            # başında zaten render edildi; güncel durumu göstermek için
            # script'i güncellenmiş session_state ile yeniden çalıştır.
            # generate_clicked yalnızca tıklamanın gerçekleştiği bu çalıştırmada
            # True olduğundan, bu rerun ödemeli çağrıları tekrarlamaz.
            st.rerun()

    st.subheader(t("b1.section.results"))
    if st.session_state.results and (st.session_state.results["a"] or st.session_state.results["b"]):
        results = st.session_state.results
        if results["a"] is not None and results["b"] is not None:
            render_comparison_summary(results)
        else:
            st.warning(t("b1.warning.comparison_needs_both"))

        col_a, col_b = st.columns(2)
        with col_a:
            if results["a"] is not None:
                render_model_card(results["settings"]["model_a"], PLAN_A, results["a"])
            else:
                st.info(t("b1.info.no_result_for_plan").format(plan=PLAN_A.heading_for(lang)))
        with col_b:
            if results["b"] is not None:
                render_model_card(results["settings"]["model_b"], PLAN_B, results["b"])
            else:
                st.info(t("b1.info.no_result_for_plan").format(plan=PLAN_B.heading_for(lang)))
    else:
        st.info(t("b1.info.click_to_generate"))


render_b1_page()
