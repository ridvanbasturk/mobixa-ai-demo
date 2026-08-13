"""B6 — Rapor Değerlendirmesi.

Metrikler Python/pandas ile deterministik olarak hesaplanır; yalnızca
hesaplanan metrik JSON'u iki Bedrock modeline (Qwen3, Gemma)
gönderilerek yönetim değerlendirme kartları üretilir. TR/EN dil desteği
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

from schemas.b6_models import validate_b6_output
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
from services.evaluation_logger import log_evaluation, read_evaluations_csv, save_human_evaluation
from services.i18n import LANG_EN, get_language, render_language_switcher, t
from services.model_registry import PLAN_A, PLAN_B, resolve_model_route, route_display_label
from services.report_service import compute_report_metrics, load_and_validate_report, validate_numeric_grounding

load_dotenv()

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent / "sample_data"

FEATURE_NAME = "B6"

SEVERITY_KEYS = {"low": "b6.severity.low", "medium": "b6.severity.medium", "high": "b6.severity.high"}


def load_system_prompt(language: str) -> str:
    filename = "b6_system_en.txt" if language == LANG_EN else "b6_system.txt"
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def build_user_prompt(metrics: dict) -> str:
    metrics_json = json.dumps(metrics, ensure_ascii=False, indent=2)
    return f"""{t("b6.user_prompt.metrics_label")}
---
{metrics_json}
---

{t("b6.user_prompt.instruction")}
"""


def init_session_state() -> None:
    if "total_cost_usd" not in st.session_state:
        st.session_state.total_cost_usd = 0.0
    if "connection_status" not in st.session_state:
        st.session_state.connection_status = (
            CONNECTION_STATUS_UNTESTED if is_api_key_configured() else CONNECTION_STATUS_NO_KEY
        )
    if "b6_results" not in st.session_state:
        st.session_state.b6_results = None


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
    # uyumluluk için hâlâ okunur (B6_MODEL_A/B ayarlanmamışsa).
    model_a = os.environ.get("B6_MODEL_A") or os.environ.get("TEXT_MODEL_A", "qwen.qwen3-235b-a22b-2507")
    model_b = os.environ.get("B6_MODEL_B") or os.environ.get("TEXT_MODEL_B", "google.gemma-4-31b")
    fallback_model = os.environ.get("B6_FALLBACK_MODEL", "qwen.qwen3-32b")

    lang = get_language()
    st.sidebar.markdown(f"**{t('common.region_label')}:** {region}")
    st.sidebar.markdown(f"**{PLAN_A.slot_label_for(lang)}:** {PLAN_A.display_name}")
    st.sidebar.markdown(f"**{PLAN_B.slot_label_for(lang)}:** {PLAN_B.display_name}")
    st.sidebar.caption(t("b6.sidebar_comparison_note"))

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

    temperature = st.sidebar.slider(t("common.temperature_label"), 0.0, 1.0, 0.2, 0.05, key="b6_temperature")
    max_tokens = st.sidebar.number_input(
        t("common.max_tokens_label"), min_value=256, max_value=8000, value=2000, step=100, key="b6_max_tokens"
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**{t('common.session_cost_label')}** ${st.session_state.total_cost_usd:.6f}")
    st.sidebar.caption(t("b6.session_cost_caption"))
    if st.sidebar.button(t("common.reset_cost_button"), key="b6_reset_cost"):
        st.session_state.total_cost_usd = 0.0
        st.rerun()

    st.sidebar.markdown("---")
    csv_content = read_evaluations_csv()
    st.sidebar.download_button(
        label=t("common.download_csv_button"),
        data=csv_content,
        file_name="evaluations.csv",
        mime="text/csv",
        key="b6_download_csv",
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
    st.subheader(t("b6.section.data_selection"))
    source = st.radio(
        t("b6.data_source_label"),
        [t("b6.data_source.sample"), t("b6.data_source.upload")],
        horizontal=True,
        key="b6_source",
    )

    df = None
    validation_error = None

    if source == t("b6.data_source.sample"):
        sample_path = SAMPLE_DATA_DIR / "report.csv"
        df, validation_error = load_and_validate_report(sample_path)
    else:
        uploaded = st.file_uploader(t("b6.file_uploader_label"), type=["csv"], key="b6_uploader")
        if uploaded is not None:
            df, validation_error = load_and_validate_report(uploaded)
        else:
            st.info(t("b6.info.upload_csv"))

    if validation_error:
        st.error(validation_error)

    st.subheader(t("b6.section.raw_preview"))
    if df is not None:
        st.dataframe(df, width="stretch")
    else:
        st.info(t("b6.info.select_valid_csv"))

    return df, validation_error


def render_metrics(metrics: dict) -> None:
    st.subheader(t("b6.section.metrics"))
    m1, m2, m3 = st.columns(3)
    m1.metric(t("b6.metric.total_active_users"), metrics["total_active_users"])
    m2.metric(t("b6.metric.overall_completion_rate"), metrics["overall_completion_rate"])
    m3.metric(t("b6.metric.overall_average_quiz_score"), metrics["overall_average_quiz_score"])

    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**{t('b6.metric.lowest_completion_group')}** {metrics['lowest_completion_group']}")
        st.write(f"**{t('b6.metric.highest_completion_group')}** {metrics['highest_completion_group']}")
    with c2:
        st.write(f"**{t('b6.metric.lowest_quiz_group')}** {metrics['lowest_quiz_group']}")
        st.write(f"**{t('b6.metric.highest_quiz_group')}** {metrics['highest_quiz_group']}")

    st.subheader(t("b6.section.risk_groups"))
    if metrics["risk_groups"]:
        for rg in metrics["risk_groups"]:
            st.warning(f"{rg['group']}: {', '.join(rg['risk_codes'])}")
    else:
        st.success(t("b6.no_risk_groups"))

    with st.expander(t("b6.section.metrics_json")):
        st.code(json.dumps(metrics, ensure_ascii=False, indent=2), language="json")


def run_model_and_validate(
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    metrics: dict,
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
            validated = validate_b6_output(call_result.parsed_json)
            schema_valid = True
        except ValidationError as exc:
            schema_error = "Pydantic doğrulama hatası:\n" + str(exc)
        except ValueError as exc:
            schema_error = str(exc)

    json_valid = call_result.parsed_json is not None
    insight_count = len(validated.insights) if validated else 0

    numeric_passed = None
    numeric_warnings: list = []
    if validated:
        insights_as_dicts = [i.model_dump() for i in validated.insights]
        numeric_passed, numeric_warnings = validate_numeric_grounding(insights_as_dicts, metrics)

    numeric_details = ", ".join(numeric_warnings)

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
        question_count=insight_count,
        success=call_result.success,
        error=call_result.error,
        numeric_validation_passed=numeric_passed,
        numeric_validation_details=numeric_details,
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
        "numeric_passed": numeric_passed,
        "numeric_warnings": numeric_warnings,
    }


def render_validation_help() -> None:
    with st.expander(t("b6.validation_help.title")):
        st.markdown(t("b6.validation_help.body"))


def render_human_evaluation(run_id: str) -> None:
    st.markdown(f"#### {t('b6.human_eval.title')}")

    key_numeric = f"b6_human_numeric_{run_id}"
    key_ground = f"b6_human_ground_{run_id}"
    key_action = f"b6_human_action_{run_id}"
    key_lang = f"b6_human_lang_{run_id}"
    key_causal = f"b6_human_causal_{run_id}"
    key_notes = f"b6_human_notes_{run_id}"

    not_evaluated = t("b6.human_eval.not_evaluated")
    yes, no, partial = t("common.yes"), t("common.no"), t("b6.human_eval.partial")

    st.selectbox(t("b6.human_eval.numeric_label"), [not_evaluated, yes, no], key=key_numeric)
    st.selectbox(
        t("b6.human_eval.groundedness_label"),
        [not_evaluated, yes, partial, no],
        key=key_ground,
    )
    st.slider(t("b6.human_eval.actionability_label"), 1, 5, 3, key=key_action)
    st.slider(t("b6.human_eval.language_quality_label"), 1, 5, 3, key=key_lang)
    st.selectbox(
        t("b6.human_eval.causality_label"),
        [not_evaluated, no, partial, yes],
        key=key_causal,
    )
    st.text_area(t("b6.human_eval.notes_label"), key=key_notes, height=80)

    if st.button(t("b6.human_eval.save_button"), key=f"b6_save_human_{run_id}"):
        saved = save_human_evaluation(
            run_id=run_id,
            groundedness=st.session_state[key_ground],
            language_quality=st.session_state[key_lang],
            notes=st.session_state[key_notes],
            numeric_accuracy=st.session_state[key_numeric],
            actionability=st.session_state[key_action],
            causality_issue=st.session_state[key_causal],
        )
        if saved:
            st.success(t("b6.human_eval.saved"))
        else:
            st.error(t("b6.human_eval.save_failed"))


def render_model_card(model_id: str, plan, outcome: dict) -> None:
    prices = load_model_prices()
    display_name = get_display_name(model_id, prices)
    call_result = outcome["call_result"]
    lang = get_language()

    st.markdown(f"### {plan.heading_for(lang)}")
    st.caption(plan.subtitle_for(lang))
    if display_name != plan.display_name:
        st.caption(t("b6.configured_model_caption").format(name=display_name))

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

    if outcome["validated"] is not None:
        if outcome["numeric_passed"]:
            st.success(t("b6.numeric_check.passed"))
        else:
            st.warning(t("b6.numeric_check.warning").format(numbers=", ".join(outcome["numeric_warnings"])))

    validated = outcome["validated"]
    if validated:
        st.markdown(f"**{t('b6.executive_summary_label')}** {validated.executive_summary}")

        st.markdown(f"#### {t('b6.section.insights')}")
        for i, insight in enumerate(validated.insights, start=1):
            with st.container(border=True):
                severity_label = t(SEVERITY_KEYS.get(insight.severity, "b6.severity.medium"))
                st.markdown(f"**{i}. {insight.title}** · {t('b6.severity_label')} {severity_label}")
                st.write(f"{t('b6.finding_label')} {insight.finding}")
                st.caption(f"{t('b6.evidence_label')} {insight.evidence}")
                st.caption(f"{t('b6.recommendation_label')} {insight.recommendation}")

    if call_result.raw_text:
        with st.expander(t("common.raw_output_expander")):
            st.code(call_result.raw_text)

    if call_result.parsed_json:
        st.download_button(
            label=t("common.download_json_button"),
            data=json.dumps(call_result.parsed_json, ensure_ascii=False, indent=2),
            file_name=f"{model_id.replace('.', '_')}_b6_output.json",
            mime="application/json",
            key=f"b6_download_{model_id}_{outcome['run_id']}",
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


def render_b6_page() -> None:
    init_session_state()
    render_language_switcher()

    st.title(t("app.title"))
    st.subheader(t("b6.page_subtitle"))
    st.caption(t("b6.page_caption"))

    settings = render_sidebar()

    st.subheader(t("b6.section.report_period"))
    report_period = st.text_input(t("b6.report_period_label"), value="2026 Q2", key="b6_report_period")

    df, validation_error = render_data_selection()

    metrics = None
    if df is not None:
        if not report_period.strip():
            st.warning(t("b6.warning.missing_period"))
        else:
            try:
                metrics = compute_report_metrics(df, report_period.strip())
            except ValueError as exc:
                st.error(str(exc))

    if metrics:
        render_metrics(metrics)

    st.subheader(t("b6.section.generation"))
    generate_clicked = st.button(t("b6.generate_button"), type="primary", key="b6_generate")

    if generate_clicked:
        if metrics is None:
            st.error(t("b6.error.missing_data"))
        elif not is_api_key_configured():
            st.error(t("common.api_key_missing_error"))
        else:
            lang = get_language()
            system_prompt = load_system_prompt(lang)
            user_prompt = build_user_prompt(metrics)

            with st.spinner(t("b6.spinner.model_a")):
                outcome_a = run_model_and_validate(
                    settings["model_a"],
                    system_prompt,
                    user_prompt,
                    settings["temperature"],
                    settings["max_tokens"],
                    metrics,
                )

            throttle_delay = float(os.environ.get("INTER_MODEL_DELAY_SECONDS", "1"))
            if throttle_delay > 0:
                time.sleep(throttle_delay)

            with st.spinner(t("b6.spinner.model_b")):
                outcome_b = run_model_and_validate(
                    settings["model_b"],
                    system_prompt,
                    user_prompt,
                    settings["temperature"],
                    settings["max_tokens"],
                    metrics,
                )

            st.session_state.b6_results = {"a": outcome_a, "b": outcome_b, "settings": settings}
            st.rerun()

    st.subheader(t("b6.section.results"))
    if st.session_state.b6_results:
        render_comparison_summary(st.session_state.b6_results)

        col_a, col_b = st.columns(2)
        with col_a:
            render_model_card(
                st.session_state.b6_results["settings"]["model_a"], PLAN_A, st.session_state.b6_results["a"]
            )
        with col_b:
            render_model_card(
                st.session_state.b6_results["settings"]["model_b"], PLAN_B, st.session_state.b6_results["b"]
            )
    else:
        st.info(t("b6.info.click_to_generate"))


render_b6_page()
