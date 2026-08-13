"""C1 — Otomatik Journey Oluşturma.

Bir Journey talebi (brief: hedef kitle, amaç, zorunlu konular, aktivite
sayısı sınırları) ve mevcut bir aktivite kataloğu Python ile doğrulanır;
aynı doğrulanmış veriler iki Bedrock modeline (Qwen3, Gemma) gönderilerek
yalnızca katalogdaki aktivitelerden oluşan, sıralı bir Journey önerilir.
Model çıktısı ayrıca deterministik iş kurallarına göre denetlenir. TR/EN
dil desteği `services/i18n.py` üzerinden sağlanır.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from pydantic import ValidationError

from schemas.c1_models import validate_c1_output
from services.bedrock_client import (
    CONNECTION_MESSAGE_KEYS,
    CONNECTION_STATUS_LEVELS,
    CONNECTION_STATUS_NO_KEY,
    CONNECTION_STATUS_UNTESTED,
    call_model,
    is_api_key_configured,
    next_connection_status,
)
from services.comparison import ModelMetrics, build_comparison_summary
from services.cost_calculator import get_display_name, load_model_prices
from services.evaluation_logger import log_evaluation, read_evaluations_csv
from services.i18n import LANG_EN, get_language, render_language_switcher, t
from services.learning_path_service import (
    find_unknown_excluded_ids,
    load_and_validate_catalog,
    load_and_validate_journey_brief,
    validate_business_rules,
)
from services.model_registry import PLAN_A, PLAN_B, resolve_model_route, route_display_label

load_dotenv()

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent / "sample_data"

FEATURE_NAME = "C1"


def load_system_prompt(language: str) -> str:
    filename = "c1_system_en.txt" if language == LANG_EN else "c1_system.txt"
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def build_user_prompt(brief: dict, catalog_df) -> str:
    brief_json = json.dumps(brief, ensure_ascii=False, indent=2)
    catalog_json = json.dumps(catalog_df.to_dict(orient="records"), ensure_ascii=False, indent=2)
    return f"""{t("c1.user_prompt.brief_label")}
---
{brief_json}
---

{t("c1.user_prompt.catalog_label")}
---
{catalog_json}
---

{t("c1.user_prompt.instruction")}
"""


def init_session_state() -> None:
    if "total_cost_usd" not in st.session_state:
        st.session_state.total_cost_usd = 0.0
    if "connection_status" not in st.session_state:
        st.session_state.connection_status = (
            CONNECTION_STATUS_UNTESTED if is_api_key_configured() else CONNECTION_STATUS_NO_KEY
        )
    if "c1_results" not in st.session_state:
        st.session_state.c1_results = None


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
    # Seçici Gemma 4 göçü: Plan A = Qwen3 235B (korunur), Plan B = Gemma 4 31B
    # (yeni). Eski paylaşımlı TEXT_MODEL_A/B ortam değişkenleri geriye dönük
    # uyumluluk için hâlâ okunur (C1_MODEL_A/B ayarlanmamışsa).
    model_a = os.environ.get("C1_MODEL_A") or os.environ.get("TEXT_MODEL_A", "qwen.qwen3-235b-a22b-2507")
    model_b = os.environ.get("C1_MODEL_B") or os.environ.get("TEXT_MODEL_B", "google.gemma-4-31b")
    fallback_model = os.environ.get("C1_FALLBACK_MODEL", "qwen.qwen3-32b")

    lang = get_language()
    st.sidebar.markdown(f"**{t('common.region_label')}:** {region}")
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

    temperature = st.sidebar.slider(t("common.temperature_label"), 0.0, 1.0, 0.2, 0.05, key="c1_temperature")
    max_tokens = st.sidebar.number_input(
        t("common.max_tokens_label"), min_value=256, max_value=8000, value=2000, step=100, key="c1_max_tokens"
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**{t('common.session_cost_label')}** ${st.session_state.total_cost_usd:.6f}")
    st.sidebar.caption(t("c1.session_cost_caption"))
    if st.sidebar.button(t("common.reset_cost_button"), key="c1_reset_cost"):
        st.session_state.total_cost_usd = 0.0
        st.rerun()

    st.sidebar.markdown("---")
    csv_content = read_evaluations_csv()
    st.sidebar.download_button(
        label=t("common.download_csv_button"),
        data=csv_content,
        file_name="evaluations.csv",
        mime="text/csv",
        key="c1_download_csv",
    )

    st.sidebar.markdown("---")
    st.sidebar.caption(t("common.pricing_caption"))

    return {
        "model_a": model_a,
        "model_b": model_b,
        "temperature": temperature,
        "max_tokens": int(max_tokens),
    }


def render_data_selection() -> tuple:
    st.subheader(t("c1.section.data_selection"))
    source = st.radio(
        t("c1.data_source_label"),
        [t("c1.data_source.sample"), t("c1.data_source.upload")],
        horizontal=True,
        key="c1_source",
    )

    brief = None
    brief_error = None
    catalog_df = None
    catalog_error = None

    if source == t("c1.data_source.sample"):
        brief, brief_error = load_and_validate_journey_brief(SAMPLE_DATA_DIR / "journey_brief.json")
        catalog_df, catalog_error = load_and_validate_catalog(SAMPLE_DATA_DIR / "activity_catalog.csv")
    else:
        brief_file = st.file_uploader(t("c1.brief_uploader_label"), type=["json"], key="c1_brief_uploader")
        catalog_file = st.file_uploader(t("c1.catalog_uploader_label"), type=["csv"], key="c1_catalog_uploader")

        if brief_file is not None:
            brief, brief_error = load_and_validate_journey_brief(brief_file)
        else:
            st.info(t("c1.info.upload_brief"))

        if catalog_file is not None:
            catalog_df, catalog_error = load_and_validate_catalog(catalog_file)
        else:
            st.info(t("c1.info.upload_catalog"))

    if brief_error:
        st.error(brief_error)
    if catalog_error:
        st.error(catalog_error)

    st.subheader(t("c1.section.brief_preview"))
    if brief is not None:
        st.json(brief)
    else:
        st.info(t("c1.info.provide_valid_brief"))

    st.subheader(t("c1.section.catalog_preview"))
    if catalog_df is not None:
        st.dataframe(catalog_df, width="stretch")
        st.caption(t("c1.catalog_synthetic_note"))
    else:
        st.info(t("c1.info.provide_valid_catalog"))

    if brief is not None and catalog_df is not None:
        unknown_excluded = find_unknown_excluded_ids(brief, catalog_df)
        if unknown_excluded:
            st.warning(t("c1.warning.unknown_excluded").format(ids=", ".join(unknown_excluded)))

    return brief, catalog_df


def render_brief_summary(brief: dict) -> None:
    st.subheader(t("c1.section.brief_summary"))
    st.markdown(f"**{brief['journey_name']}** ({brief['journey_type']})")
    st.write(brief["audience_description"])
    st.write(brief["goal_description"])

    yes, no = t("common.yes"), t("common.no")
    m1, m2, m3 = st.columns(3)
    m1.metric(t("c1.metric.min_activities"), brief["min_activities"])
    m2.metric(t("c1.metric.max_activities"), brief["max_activities"])
    m3.metric(t("c1.metric.must_end_with_test"), yes if brief["must_end_with_test"] else no)

    st.metric(t("c1.metric.required_topics_count"), len(brief["required_topics"]))


def run_model_and_validate(
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    brief: dict,
    catalog_df,
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
            validated = validate_c1_output(call_result.parsed_json)
            schema_valid = True
        except ValidationError as exc:
            schema_error = "Pydantic doğrulama hatası:\n" + str(exc)
        except ValueError as exc:
            schema_error = str(exc)

    json_valid = call_result.parsed_json is not None
    activity_count = len(validated.recommended_activities) if validated else 0

    business_result = None
    if validated:
        recommended_activities_dicts = [a.model_dump() for a in validated.recommended_activities]
        business_result = validate_business_rules(
            recommended_activities_dicts, validated.total_minutes, brief, catalog_df
        )

    business_passed = business_result["passed"] if business_result else None
    business_details = "; ".join(business_result["errors"]) if business_result else ""
    topics_covered = business_result["required_topics_covered"] if business_result else None
    topics_total = business_result["required_topics_total"] if business_result else None

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
        question_count=activity_count,
        success=call_result.success,
        error=call_result.error,
        business_validation_passed=business_passed,
        business_validation_details=business_details,
        weak_topics_covered=topics_covered,
        weak_topics_total=topics_total,
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
        "business_result": business_result,
    }


def render_validation_help() -> None:
    with st.expander(t("c1.validation_help.title")):
        st.markdown(t("c1.validation_help.body"))


def render_model_card(model_id: str, plan, outcome: dict) -> None:
    prices = load_model_prices()
    display_name = get_display_name(model_id, prices)
    call_result = outcome["call_result"]
    lang = get_language()

    st.markdown(f"### {plan.heading_for(lang)}")
    st.caption(plan.subtitle_for(lang))
    if display_name != plan.display_name:
        st.caption(t("c1.configured_model_caption").format(name=display_name))

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

    business_result = outcome["business_result"]
    if business_result is not None:
        if business_result["passed"]:
            st.success(t("c1.business_check.passed"))
        else:
            st.error(t("c1.business_check.failed").format(errors="; ".join(business_result["errors"])))
        if business_result["warnings"]:
            st.warning(t("c1.business_check.warnings").format(warnings="; ".join(business_result["warnings"])))
        st.caption(
            t("c1.business_check.topics_coverage").format(
                covered=business_result["required_topics_covered"],
                total=business_result["required_topics_total"],
            )
        )

    validated = outcome["validated"]
    if validated:
        st.markdown(f"**{t('c1.audience_fit_label')}** {validated.audience_fit_summary}")
        st.markdown(f"**{t('c1.strategy_summary_label')}** {validated.strategy_summary}")
        st.markdown(f"**{t('c1.total_minutes_label')}** {validated.total_minutes} {t('c1.minutes_suffix')}")

        enriched_by_id = {}
        if business_result:
            enriched_by_id = {e["activity_id"]: e for e in business_result["enriched_path"]}

        st.markdown(f"#### {t('c1.section.recommended_journey')}")
        for activity in sorted(validated.recommended_activities, key=lambda a: a.order):
            enriched = enriched_by_id.get(activity.activity_id, {})
            with st.container(border=True):
                title = enriched.get("title") or t("c1.activity_unknown_title")
                st.markdown(f"**{activity.order}. {title}** ({activity.activity_id})")
                st.caption(
                    t("c1.activity_meta").format(
                        type=enriched.get("activity_type") or "—",
                        sub_type=enriched.get("activity_sub_type") or "—",
                        topic=enriched.get("topic") or "—",
                        minutes=activity.estimated_minutes,
                    )
                )
                st.write(f"{t('c1.reason_label')} {activity.reason}")

    if call_result.raw_text:
        with st.expander(t("common.raw_output_expander")):
            st.code(call_result.raw_text)

    if call_result.parsed_json:
        st.download_button(
            label=t("common.download_json_button"),
            data=json.dumps(call_result.parsed_json, ensure_ascii=False, indent=2),
            file_name=f"{model_id.replace('.', '_')}_c1_output.json",
            mime="application/json",
            key=f"c1_download_{model_id}_{outcome['run_id']}",
        )

    render_validation_help()


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
            business_valid=outcome_a["business_result"]["passed"] if outcome_a["business_result"] else None,
        ),
        ModelMetrics(
            label=PLAN_B.heading_for(lang),
            cost=outcome_b["call_result"].estimated_cost_usd,
            latency_ms=outcome_b["call_result"].latency_ms,
            total_tokens=outcome_b["call_result"].total_tokens,
            json_valid=outcome_b["json_valid"],
            schema_valid=outcome_b["schema_valid"],
            business_valid=outcome_b["business_result"]["passed"] if outcome_b["business_result"] else None,
        ),
    ]

    st.markdown(f"### {t('common.comparison_title')}")
    st.caption(t("common.comparison_caption"))
    for line in build_comparison_summary(metrics, lang=lang):
        st.write(f"- {line}")


def render_c1_page() -> None:
    init_session_state()
    render_language_switcher()

    st.title(t("app.title"))
    st.subheader(t("c1.page_subtitle"))
    st.caption(t("c1.page_caption"))

    settings = render_sidebar()

    brief, catalog_df = render_data_selection()

    if brief is not None:
        render_brief_summary(brief)

    st.subheader(t("c1.section.generation"))
    generate_clicked = st.button(t("c1.generate_button"), type="primary", key="c1_generate")

    if generate_clicked:
        if brief is None or catalog_df is None:
            st.error(t("c1.error.missing_data"))
        elif not is_api_key_configured():
            st.error(t("common.api_key_missing_error"))
        else:
            lang = get_language()
            system_prompt = load_system_prompt(lang)
            user_prompt = build_user_prompt(brief, catalog_df)

            with st.spinner(t("c1.spinner.model_a")):
                outcome_a = run_model_and_validate(
                    settings["model_a"],
                    system_prompt,
                    user_prompt,
                    settings["temperature"],
                    settings["max_tokens"],
                    brief,
                    catalog_df,
                )

            throttle_delay = float(os.environ.get("INTER_MODEL_DELAY_SECONDS", "1"))
            if throttle_delay > 0:
                time.sleep(throttle_delay)

            with st.spinner(t("c1.spinner.model_b")):
                outcome_b = run_model_and_validate(
                    settings["model_b"],
                    system_prompt,
                    user_prompt,
                    settings["temperature"],
                    settings["max_tokens"],
                    brief,
                    catalog_df,
                )

            st.session_state.c1_results = {"a": outcome_a, "b": outcome_b, "settings": settings}
            st.rerun()

    st.subheader(t("c1.section.results"))
    if st.session_state.c1_results:
        render_comparison_summary(st.session_state.c1_results)

        col_a, col_b = st.columns(2)
        with col_a:
            render_model_card(
                st.session_state.c1_results["settings"]["model_a"], PLAN_A, st.session_state.c1_results["a"]
            )
        with col_b:
            render_model_card(
                st.session_state.c1_results["settings"]["model_b"], PLAN_B, st.session_state.c1_results["b"]
            )
    else:
        st.info(t("c1.info.click_to_generate"))


render_c1_page()
