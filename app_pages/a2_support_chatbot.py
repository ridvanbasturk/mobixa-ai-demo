"""A2 — Destek/Onboarding Chatbot.

Üç ayrı katmanı açıkça gösterir: Wiki (onaylı bilgi kaynağı), Skillset
(şu anda gerçekten çalışan yetenekler) ve Plugins (henüz gerçek bir
backend entegrasyonu olmayan, simüle edilmiş/gelecek özellikler).

Sorular yerel, deterministik bir sözcük eşleştirme katmanıyla (RAG'a
benzer ama Bedrock Knowledge Bases veya vektör veritabanı KULLANMAZ)
onaylı wiki'den ilgili kayıtları getirir; yalnızca bu kayıtlar iki
Bedrock modeline (Gemma varyantları) gönderilir. TR/EN dil desteği
`services/i18n.py` üzerinden sağlanır; bilgi tabanı da dile göre TR/EN
sürümünden yüklenir.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from services.a2_chat_service import run_chat_turn
from services.a2_retrieval_service import load_knowledge_base, retrieve_relevant_entries
from services.a2_skill_registry import (
    SIMULATION_DISCLAIMER,
    SIMULATION_DISCLAIMER_EN,
    get_activity_status,
    get_active_skills,
    get_future_plugins,
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
from services.evaluation_logger import log_evaluation, read_evaluations_csv
from services.i18n import LANG_EN, LANG_TR, get_language, render_language_switcher, t
from services.model_registry import A2_PLAN_A, A2_PLAN_B, resolve_model_route, route_display_label

load_dotenv()

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent / "sample_data"

FEATURE_NAME = "A2"

SAMPLE_QUESTIONS_TR = [
    "Şifremi unuttum, ne yapmalıyım?",
    "Atanmamış bir eğitime nasıl erişebilirim?",
    "Quiz tekrar hakkım kaç?",
    "iPhone uygulaması var mı?",
    "Sertifikamı nereden indirebilirim?",
    "Puanlarımı ve rozetlerimi nerede görürüm?",
    "Bildirimleri nasıl kapatırım?",
    "Uygulama dilini nasıl değiştiririm?",
    "İnternetim yokken eğitime devam edebilir miyim?",
    "Hesabımı silmek istiyorum, nasıl yaparım?",
]

SAMPLE_QUESTIONS_EN = [
    "I forgot my password, what should I do?",
    "How can I access a training that isn't assigned to me?",
    "How many quiz retry attempts do I have?",
    "Is there an iPhone app?",
    "Where can I download my certificate?",
    "Where do I see my points and badges?",
    "How do I turn off notifications?",
    "How do I change the app language?",
    "Can I continue a training without internet?",
    "I want to delete my account, how do I do that?",
]


def sample_questions(language: str) -> list:
    return SAMPLE_QUESTIONS_EN if language == LANG_EN else SAMPLE_QUESTIONS_TR


def load_system_prompt(language: str) -> str:
    filename = "a2_system_en.txt" if language == LANG_EN else "a2_system.txt"
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _kb_filename(language: str) -> str:
    return "a2_knowledge_base_en.json" if language == LANG_EN else "a2_knowledge_base.json"


def init_session_state() -> None:
    if "total_cost_usd" not in st.session_state:
        st.session_state.total_cost_usd = 0.0
    if "connection_status" not in st.session_state:
        st.session_state.connection_status = (
            CONNECTION_STATUS_UNTESTED if is_api_key_configured() else CONNECTION_STATUS_NO_KEY
        )
    if "a2_chat_history" not in st.session_state:
        st.session_state.a2_chat_history = []
    # Bilgi tabanı dile göre değişebildiği için hem TR hem EN sürümü ayrı
    # session_state anahtarlarında (dosya adına göre) cache'lenir; dil
    # değişince yeniden yüklemeye gerek kalmaz.
    if "a2_kb_by_file" not in st.session_state:
        st.session_state.a2_kb_by_file = {}


def get_current_kb(language: str) -> list:
    filename = _kb_filename(language)
    if filename not in st.session_state.a2_kb_by_file:
        st.session_state.a2_kb_by_file[filename] = load_knowledge_base(SAMPLE_DATA_DIR / filename)
    return st.session_state.a2_kb_by_file[filename]


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
    # A2, aktif yanıt üretim modellerinin YALNIZCA Gemma olduğu TEK istisnadır
    # (bkz. services/model_registry.py). Kimi K2.5 ve DeepSeek V3.2 artık
    # aktif değildir (legacy_disabled); Qwen3 32B yalnızca acil durum teknik
    # yedeğidir ve normal arayüzde aktif bir Plan B olarak GÖSTERİLMEZ.
    model_a = os.environ.get("A2_MODEL_A", "google.gemma-4-31b")
    model_b = os.environ.get("A2_MODEL_B", "").strip() or None
    fallback_model = os.environ.get("A2_FALLBACK_MODEL", "qwen.qwen3-32b")
    has_second_gemma = bool(model_b)

    lang = get_language()
    st.sidebar.markdown(f"**{t('common.region_label')}:** {region}")
    st.sidebar.markdown(f"**{A2_PLAN_A.slot_label_for(lang)}:** {A2_PLAN_A.display_name}")
    if has_second_gemma:
        st.sidebar.markdown(f"**{A2_PLAN_B.slot_label_for(lang)}:** {A2_PLAN_B.display_name}")
    else:
        st.sidebar.caption(t("a2.second_gemma_missing"))
    st.sidebar.caption(t("a2.sidebar_pair_note"))

    with st.sidebar.expander(t("common.technical_details")):
        route_a = resolve_model_route(model_a)
        lines = [
            f"Gemma Plan A: {model_a}",
            f"  Sağlayıcı: {route_a.provider} · Aile: {route_a.family} · "
            f"Rota: {route_display_label(route_a.mantle_route)} · "
            f"Aktif rol: {', '.join(route_a.active_roles) or '—'}",
        ]
        if has_second_gemma:
            route_b = resolve_model_route(model_b)
            lines.append(f"Gemma Plan B: {model_b}")
            lines.append(
                f"  Sağlayıcı: {route_b.provider} · Aile: {route_b.family} · "
                f"Rota: {route_display_label(route_b.mantle_route)} · "
                f"Aktif rol: {', '.join(route_b.active_roles) or '—'}"
            )
        else:
            lines.append("Gemma Plan B: (yapılandırılmamış — ikinci doğrulanmış Gemma varyantı yok)")
        route_fallback = resolve_model_route(fallback_model)
        lines.append(
            f"Acil durum teknik yedek (fallback): {fallback_model} "
            f"({route_fallback.provider}, {route_display_label(route_fallback.mantle_route)}) "
            "— normal arayüzde aktif bir plan olarak KULLANILMAZ"
        )
        st.code("\n".join(lines), language=None)

    temperature = st.sidebar.slider(t("common.temperature_label"), 0.0, 1.0, 0.2, 0.05, key="a2_temperature")
    max_tokens = st.sidebar.number_input(
        t("common.max_tokens_label"), min_value=256, max_value=8000, value=1000, step=100, key="a2_max_tokens"
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**{t('common.session_cost_label')}** ${st.session_state.total_cost_usd:.6f}")
    st.sidebar.caption(t("a2.session_cost_caption"))
    if st.sidebar.button(t("common.reset_cost_button"), key="a2_reset_cost"):
        st.session_state.total_cost_usd = 0.0
        st.rerun()

    st.sidebar.markdown("---")
    csv_content = read_evaluations_csv()
    st.sidebar.download_button(
        label=t("common.download_csv_button"),
        data=csv_content,
        file_name="evaluations.csv",
        mime="text/csv",
        key="a2_download_csv",
    )

    st.sidebar.markdown("---")
    st.sidebar.caption(t("common.pricing_caption"))

    return {
        "model_a": model_a,
        "model_b": model_b,
        "has_second_gemma": has_second_gemma,
        "fallback_model": fallback_model,
        "temperature": temperature,
        "max_tokens": int(max_tokens),
    }


def run_turn(
    model_id: str,
    system_prompt: str,
    question: str,
    retrieved_entries: list,
    retrieval_sufficient: bool,
    temperature: float,
    max_tokens: int,
    language: str,
) -> dict:
    turn_result = run_chat_turn(
        model_id, system_prompt, question, retrieved_entries, retrieval_sufficient, temperature, max_tokens, language
    )
    call_result = turn_result.call_result

    st.session_state.connection_status = next_connection_status(
        st.session_state.connection_status, call_result
    )

    retrieved_ids = ",".join(e["id"] for e in retrieved_entries)
    cited_ids = ",".join(turn_result.validated.source_ids) if turn_result.validated else ""
    grounding_passed = turn_result.grounding_result["passed"] if turn_result.grounding_result else None
    grounding_details = "; ".join(turn_result.grounding_result["errors"]) if turn_result.grounding_result else ""

    run_id = log_evaluation(
        feature=FEATURE_NAME,
        model_id=model_id,
        input_tokens=call_result.input_tokens,
        output_tokens=call_result.output_tokens,
        total_tokens=call_result.total_tokens,
        latency_ms=call_result.latency_ms,
        estimated_cost_usd=call_result.estimated_cost_usd,
        json_valid=turn_result.json_valid,
        schema_valid=turn_result.schema_valid,
        question_count=1,
        success=call_result.success,
        error=call_result.error,
        retrieved_source_ids=retrieved_ids,
        cited_source_ids=cited_ids,
        grounding_validation_passed=grounding_passed,
        grounding_validation_details=grounding_details,
        model_escalation_recommended=turn_result.model_escalation_recommended,
        final_needs_escalation=turn_result.final_needs_escalation,
    )

    if call_result.estimated_cost_usd:
        st.session_state.total_cost_usd += call_result.estimated_cost_usd

    return {"run_id": run_id, "turn_result": turn_result}


def render_retrieved_sources(retrieved_entries: list, retrieval_sufficient: bool) -> None:
    st.markdown(f"##### {t('a2.retrieved_sources_title')}")
    if not retrieved_entries:
        st.warning(t("a2.no_relevant_source_warning"))
        return

    for e in retrieved_entries:
        with st.container(border=True):
            st.markdown(f"**{e['id']} — {e['title']}** (skor: {e['score']})")
            snippet = e["content"][:220] + ("…" if len(e["content"]) > 220 else "")
            st.caption(snippet)

    if not retrieval_sufficient:
        st.caption(t("a2.below_threshold_caption"))


def render_validation_help() -> None:
    with st.expander(t("a2.validation_help.title")):
        st.markdown(t("a2.validation_help.body"))


def render_model_card(model_id: str, plan, outcome: dict, retrieved_entries: list) -> None:
    prices = load_model_prices()
    display_name = get_display_name(model_id, prices)
    turn_result = outcome["turn_result"]
    call_result = turn_result.call_result
    lang = get_language()

    st.markdown(f"### {plan.heading_for(lang)}")
    st.caption(plan.subtitle_for(lang))
    if display_name != plan.display_name:
        st.caption(t("common.configured_model_caption").format(name=display_name))

    if call_result.success and turn_result.schema_valid:
        st.success(t("common.status.success"))
    elif call_result.success and not turn_result.schema_valid:
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
    st.write(f"**{t('common.json_valid_label')}** {yes if turn_result.json_valid else no}")
    st.write(f"**{t('common.pydantic_label')}** {t('common.status.passed') if turn_result.schema_valid else t('common.status.failed')}")
    if turn_result.schema_error:
        with st.expander(t("common.validation_error_expander")):
            st.caption(t("common.raw_text_language_note"))
            st.code(turn_result.schema_error)

    grounding = turn_result.grounding_result
    if grounding is not None:
        source_ok = len(grounding["unknown_source_ids"]) == 0
        if source_ok:
            st.success(t("a2.source_validation.passed"))
        else:
            st.error(t("a2.source_validation.failed").format(ids=", ".join(grounding["unknown_source_ids"])))

        if grounding["passed"]:
            st.success(t("a2.grounding.passed"))
        else:
            st.error(t("a2.grounding.failed").format(errors="; ".join(grounding["errors"])))
        if grounding["warnings"]:
            st.warning(t("a2.grounding.warnings").format(warnings="; ".join(grounding["warnings"])))
    else:
        st.info(t("a2.grounding.not_run"))

    validated = turn_result.validated
    if validated:
        st.markdown(f"**{t('a2.answer_label')}** {validated.answer}")
        st.write(
            f"**{t('a2.cited_sources_label')}** "
            + (", ".join(validated.source_ids) if validated.source_ids else "—")
        )
        st.caption(f"{t('a2.support_reason_label')} {validated.support_reason}")

    model_rec = turn_result.model_escalation_recommended
    st.write(
        f"**{t('a2.model_escalation_label')}** "
        + (t("common.yes") if model_rec else t("common.no") if model_rec is not None else t("a2.no_value"))
    )
    if turn_result.final_needs_escalation:
        st.warning(f"**{t('a2.final_escalation_yes')}**")
    else:
        st.success(f"**{t('a2.final_escalation_no')}**")

    if call_result.raw_text:
        with st.expander(t("common.raw_output_expander")):
            st.code(call_result.raw_text)

    if call_result.parsed_json:
        st.download_button(
            label=t("common.download_json_button"),
            data=json.dumps(call_result.parsed_json, ensure_ascii=False, indent=2),
            file_name=f"{model_id.replace('.', '_')}_a2_output.json",
            mime="application/json",
            key=f"a2_download_{model_id}_{outcome['run_id']}",
        )

    render_validation_help()


def _source_id_usage_label(turn_result) -> str:
    if turn_result.grounding_result is None:
        return t("a2.usage.not_measured")
    valid = len(turn_result.grounding_result["valid_source_ids"])
    unknown = len(turn_result.grounding_result["unknown_source_ids"])
    total = valid + unknown
    if total == 0:
        return t("a2.usage.none")
    return t("a2.usage.valid_of_total").format(valid=valid, total=total)


def render_comparison_summary(turn: dict) -> None:
    outcome_a = turn["outcome_a"]
    outcome_b = turn["outcome_b"]
    tr_a = outcome_a["turn_result"]
    lang = get_language()

    if outcome_b is None:
        # İkinci doğrulanmış bir Gemma varyantı yapılandırılmamış; tek
        # aktif model kullanıldığı için bir karşılaştırma özeti YOKTUR.
        st.caption(t("a2.comparison_no_second_gemma"))
        return

    tr_b = outcome_b["turn_result"]

    metrics = [
        ModelMetrics(
            label=A2_PLAN_A.heading_for(lang),
            cost=tr_a.call_result.estimated_cost_usd,
            latency_ms=tr_a.call_result.latency_ms,
            total_tokens=tr_a.call_result.total_tokens,
            json_valid=tr_a.json_valid,
            schema_valid=tr_a.schema_valid,
            business_valid=tr_a.grounding_result["passed"] if tr_a.grounding_result else None,
        ),
        ModelMetrics(
            label=A2_PLAN_B.heading_for(lang),
            cost=tr_b.call_result.estimated_cost_usd,
            latency_ms=tr_b.call_result.latency_ms,
            total_tokens=tr_b.call_result.total_tokens,
            json_valid=tr_b.json_valid,
            schema_valid=tr_b.schema_valid,
            business_valid=tr_b.grounding_result["passed"] if tr_b.grounding_result else None,
        ),
    ]

    st.markdown(f"### {t('common.comparison_title')}")
    st.caption(t("a2.comparison_extra_caption"))
    for line in build_comparison_summary(metrics, lang=lang):
        st.write(f"- {line}")
    st.write(
        "- "
        + t("a2.source_id_usage_line").format(
            label_a=A2_PLAN_A.heading_for(lang),
            usage_a=_source_id_usage_label(tr_a),
            label_b=A2_PLAN_B.heading_for(lang),
            usage_b=_source_id_usage_label(tr_b),
        )
    )


def _assistant_answer_text(outcome: dict) -> str:
    """Sohbet balonunda gösterilecek, kullanıcı dostu cevap metni.

    Model/şema hatası olsa bile ham bir hata mesajı DEĞİL, açıklayıcı bir
    yedek mesaj döner — teknik ayrıntı (gerçek hata metni) yalnızca
    "Teknik detaylar" panelinde gösterilir.
    """
    turn_result = outcome["turn_result"]
    if turn_result.validated is not None:
        return turn_result.validated.answer
    if turn_result.call_result.success:
        return t("a2.answer_fallback_schema_invalid")
    return t("a2.answer_fallback_failed")


_LANGUAGE_BADGE = {LANG_TR: "🇹🇷 TR", LANG_EN: "🇬🇧 EN"}


def render_chat_turn(turn: dict) -> None:
    with st.chat_message("user"):
        st.write(turn["question"])
        # Bu tur hangi dilde soruldu/cevaplandıysa o dilde KALIR — dil
        # anahtarı sonradan değiştirilse bile geçmiş cevaplar geriye dönük
        # çevrilmez (gerçek chat ürünlerinin standart davranışı; ayrıca
        # cevap, o an seçili dildeki wiki'den getirilen kaynaklara
        # dayanıyordu, yeniden çevirmek bu dayanağı yanlış yansıtırdı).
        # Küçük bir bayrak rozeti, karışık dilli bir geçmişte hangi turun
        # hangi dilde geçtiğini şeffaf biçimde gösterir.
        st.caption(_LANGUAGE_BADGE.get(turn.get("language", LANG_TR), ""))

    outcome_a = turn["outcome_a"]
    turn_result_a = outcome_a["turn_result"]

    with st.chat_message("assistant", avatar="🤖"):
        st.caption(t("a2.assistant_name"))
        st.write(_assistant_answer_text(outcome_a))

        if turn_result_a.validated and turn_result_a.validated.source_ids:
            st.caption(f"{t('a2.citations_label')} " + ", ".join(turn_result_a.validated.source_ids))

        if turn_result_a.final_needs_escalation:
            st.caption(t("a2.escalation_note_chat"))

        with st.expander(t("a2.tech_details_expander")):
            render_retrieved_sources(turn["retrieved_entries"], turn["retrieval_sufficient"])

            st.markdown(f"###### {t('a2.tech_details_primary_label')}")
            render_model_card(
                turn["settings"]["model_a"], A2_PLAN_A, outcome_a, turn["retrieved_entries"]
            )

            outcome_b = turn.get("outcome_b")
            if turn.get("comparison_mode") and outcome_b is not None:
                st.markdown("---")
                st.markdown(f"###### {t('a2.tech_details_comparison_label')}")
                render_comparison_summary({"outcome_a": outcome_a, "outcome_b": outcome_b})
                render_model_card(
                    turn["settings"]["model_b"], A2_PLAN_B, outcome_b, turn["retrieved_entries"]
                )
            elif turn["settings"].get("has_second_gemma") and not turn.get("comparison_mode"):
                st.caption(t("a2.comparison_off_note"))


def render_chatbot_tab(settings: dict) -> None:
    lang = get_language()
    history = st.session_state.a2_chat_history

    comparison_mode = st.checkbox(
        t("a2.comparison_mode_label"),
        value=False,
        help=t("a2.comparison_mode_help"),
        key="a2_comparison_mode",
        disabled=not settings["has_second_gemma"],
    )

    question_to_run = None

    if not history:
        with st.chat_message("assistant", avatar="🤖"):
            st.caption(t("a2.assistant_name"))
            st.write(t("a2.chat_greeting"))

        st.caption(t("a2.suggestions_title"))
        questions = sample_questions(lang)
        for row_start in range(0, len(questions), 5):
            row = questions[row_start : row_start + 5]
            cols = st.columns(len(row))
            for offset, (col, sample_question) in enumerate(zip(cols, row)):
                with col:
                    if st.button(sample_question, key=f"a2_sample_{row_start + offset}"):
                        question_to_run = sample_question
    else:
        for turn in history:
            render_chat_turn(turn)

    typed_question = st.chat_input(t("a2.chat_input_placeholder"))
    if typed_question and typed_question.strip():
        question_to_run = typed_question.strip()

    if question_to_run:
        if not is_api_key_configured():
            st.error(t("common.api_key_missing_error"))
        else:
            kb = get_current_kb(lang)
            retrieved_entries, retrieval_sufficient = retrieve_relevant_entries(
                question_to_run, kb, language=lang
            )
            system_prompt = load_system_prompt(lang)

            with st.spinner(t("a2.spinner.plan_a").format(plan=A2_PLAN_A.heading_for(lang))):
                outcome_a = run_turn(
                    settings["model_a"],
                    system_prompt,
                    question_to_run,
                    retrieved_entries,
                    retrieval_sufficient,
                    settings["temperature"],
                    settings["max_tokens"],
                    lang,
                )

            outcome_b = None
            if settings["has_second_gemma"] and comparison_mode:
                throttle_delay = float(os.environ.get("INTER_MODEL_DELAY_SECONDS", "1"))
                if throttle_delay > 0:
                    time.sleep(throttle_delay)

                with st.spinner(t("a2.spinner.plan_a").format(plan=A2_PLAN_B.heading_for(lang))):
                    outcome_b = run_turn(
                        settings["model_b"],
                        system_prompt,
                        question_to_run,
                        retrieved_entries,
                        retrieval_sufficient,
                        settings["temperature"],
                        settings["max_tokens"],
                        lang,
                    )

            st.session_state.a2_chat_history.append(
                {
                    "question": question_to_run,
                    "retrieved_entries": retrieved_entries,
                    "retrieval_sufficient": retrieval_sufficient,
                    "outcome_a": outcome_a,
                    "outcome_b": outcome_b,
                    "comparison_mode": comparison_mode,
                    "language": lang,
                    "settings": settings,
                }
            )
            st.rerun()


def render_wiki_tab() -> None:
    lang = get_language()
    kb = get_current_kb(lang)

    st.subheader(t("a2.wiki.title"))
    st.info(t("a2.wiki.info"))

    search = st.text_input(t("a2.wiki.search_label"), key="a2_wiki_search")
    entries = kb
    if search.strip():
        q = search.strip().lower()
        entries = [e for e in entries if q in e["title"].lower() or q in e["content"].lower()]

    for e in entries:
        with st.container(border=True):
            status_badge = "✅ approved" if e["status"] == "approved" else f"⚠️ {e['status']}"
            st.markdown(f"**{e['id']} — {e['title']}**")
            st.caption(
                f"{status_badge} · {t('a2.wiki.roles_label')} {', '.join(e['role'])} · "
                f"{t('a2.wiki.product_area_label')} {e['product_area']} · "
                f"{t('a2.wiki.version_label')} {e['version']} · "
                f"{t('a2.wiki.last_updated_label')} {e['last_updated']}"
            )
            st.write(e["content"])


def render_skills_tab() -> None:
    lang = get_language()
    st.subheader(t("a2.skills.active_title"))
    for skill in get_active_skills(lang):
        st.write(f"✅ {skill}")

    st.subheader(t("a2.skills.future_title"))
    st.caption(t("a2.skills.future_caption"))
    for plugin in get_future_plugins(lang):
        with st.container(border=True):
            st.markdown(f"**{plugin['name']}**")
            st.write(f"{t('a2.skills.purpose_label')} {plugin['purpose']}")
            st.caption(
                f"{t('a2.skills.expected_input_label')} {plugin['expected_input']} · "
                f"{t('a2.skills.expected_output_label')} {plugin['expected_output']}"
            )
            st.warning(plugin["status"])

    st.subheader(t("a2.skills.simulation_title"))
    st.caption(t("a2.skills.simulation_caption"))
    activity_id = st.text_input(t("a2.skills.activity_id_label"), value="A01", key="a2_sim_activity_id")
    if st.button(t("a2.skills.simulation_button"), key="a2_sim_button"):
        result = get_activity_status(activity_id.strip(), lang)
        st.warning(SIMULATION_DISCLAIMER_EN if lang == LANG_EN else SIMULATION_DISCLAIMER)
        st.json(result)


def render_a2_page() -> None:
    init_session_state()
    render_language_switcher()

    st.title(t("app.title"))
    st.subheader(t("a2.page_subtitle"))
    st.caption(t("a2.page_caption"))

    settings = render_sidebar()

    tab_chat, tab_wiki, tab_skills = st.tabs([t("a2.tab.chatbot"), t("a2.tab.wiki"), t("a2.tab.skills")])

    with tab_chat:
        render_chatbot_tab(settings)

    with tab_wiki:
        render_wiki_tab()

    with tab_skills:
        render_skills_tab()


render_a2_page()
