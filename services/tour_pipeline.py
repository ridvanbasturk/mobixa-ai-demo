"""Uçtan uca tur kaydı orkestrasyonu.

Akış:
  1. Kaydedilecek Streamlit uygulaması ayrı bir portta başlatılır
  2. Playwright video kaydıyla tarayıcıyı açar, imleç overlay'ini enjekte eder
  3. Hedef modüle gidilir, dil ayarlanır
  4. AJANTİK DÖNGÜ: ekran görüntüsü → envanter → model kararı → doğrulama →
     seslendirme → imleç hareketi → eylem → Streamlit'in işi bitene kadar bekle
  5. Kayıt kapatılır, FFmpeg altyazı/ses ile nihai MP4'ü üretir

Streamlit'ten bağımsızdır (arayüz yalnızca `progress_callback` ile bilgilendirilir),
bu sayede `scripts/record_tour.py` ile komut satırından da çalıştırılabilir.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from schemas.tour_models import (
    ACTION_CLICK,
    ACTION_DONE,
    ACTION_HIGHLIGHT,
    ACTION_SCROLL_TO,
    ACTION_TYPE,
    ACTION_WAIT,
    TourRecording,
    TourStep,
)
from services.evaluation_logger import log_evaluation
from services.tour_agent_service import AgentContext, decide_next_step, dump_steps_json, summarize_decision
from services.tour_app_server import running_app
from services.tour_cursor import CLICK_SETTLE_MS, CURSOR_INIT_SCRIPT, CURSOR_MOVE_MS
from services.tour_dom_inspector import INVENTORY_SCRIPT, build_inventory
from services.tour_tts import NullTTS, get_tts_engine
from services.tour_video_service import render_final_video, write_srt

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "outputs" / "tour_videos"

VIEWPORT = {"width": 1440, "height": 900}
FEATURE_NAME = "A1"

# Turu çekilebilecek modüller. `nav_label`, kenar çubuğundaki gezinme
# bağlantısının metniyle eşleşir (app.py'deki st.Page başlıkları).
TOUR_MODULES: Dict[str, Dict] = {
    "c1": {
        "nav_label": "C1 — Öğrenme Yolu",
        "title_tr": "C1 — Otomatik Journey Oluşturma",
        "title_en": "C1 — Automatic Journey Generation",
        "sources": ["app_pages/c1_learning_path.py", "services/i18n_strings/c1.py"],
    },
    "a2": {
        "nav_label": "A2 — Destek Chatbot'u",
        "title_tr": "A2 — Destek/Oryantasyon Sohbet Botu",
        "title_en": "A2 — Support/Onboarding Chatbot",
        "sources": ["app_pages/a2_support_chatbot.py", "services/i18n_strings/a2.py"],
    },
    "b1": {
        "nav_label": "B1 — İçerik Üretimi",
        "title_tr": "B1 — İçerikten Otomatik Soru ve Aktivite Üretimi",
        "title_en": "B1 — Automatic Question & Activity Generation",
        "sources": ["app_pages/b1_content_generation.py", "services/i18n_strings/b1.py"],
    },
    "b6": {
        "nav_label": "B6 — Rapor Değerlendirmesi",
        "title_tr": "B6 — Rapor Değerlendirmesi",
        "title_en": "B6 — Report Insights",
        "sources": ["app_pages/b6_report_insights.py", "services/i18n_strings/b6.py"],
    },
}

DEFAULT_MAX_STEPS = 18
# Streamlit'in bir yeniden çalıştırmayı bitirmesi için beklenecek en uzun süre.
# C1/B1 gibi modüllerde gerçek model çağrısı tetiklendiği için cömert tutulur.
STREAMLIT_IDLE_TIMEOUT_MS = 120_000

# Bir adımda geçersiz karar gelirse ajana hatası bildirilip kaç kez daha
# şans verilir. Tek bir bozuk karar tüm turu öldürmemeli; ajan hatasını
# görüp düzeltebilmelidir (agentic döngünün doğal parçası).
MAX_DECISION_RETRIES = 2

# Dil seçicinin Streamlit anahtarı (services/i18n.py::_LANGUAGE_WIDGET_KEY).
LANGUAGE_WIDGET_KEY = "app_language_widget"


def module_title(module: str, language: str) -> str:
    config = TOUR_MODULES[module]
    return config["title_en"] if language == "en" else config["title_tr"]


def compute_source_fingerprint(module: str) -> str:
    """Modülün arayüzünü etkileyen dosyaların içerik parmak izi.

    Kod değişince videoların otomatik yenilenmesi İLERİDE eklenecek; parmak izi
    şimdiden metaveriye yazılır ki o iş geldiğinde geçmiş kayıtlar da
    karşılaştırılabilsin.
    """
    digest = hashlib.sha256()
    sources = list(TOUR_MODULES[module]["sources"]) + ["app.py", "services/i18n_strings/common.py"]
    for relative in sorted(sources):
        path = REPO_ROOT / relative
        if path.exists():
            digest.update(relative.encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


@dataclass
class TourProgress:
    """Arayüze/CLI'ya gönderilen ilerleme bildirimi."""

    stage: str
    step_index: int = 0
    message: str = ""
    narration: str = ""
    action: str = ""
    valid: bool = True
    screenshot: Optional[bytes] = None


ProgressCallback = Callable[[TourProgress], None]


def _noop(_: TourProgress) -> None:
    return None


def _wait_for_streamlit_idle(page, timeout_ms: int = STREAMLIT_IDLE_TIMEOUT_MS) -> None:
    """Streamlit yeniden çalıştırmayı bitirene kadar bekler.

    "Meşgul" sinyali olarak hem çalışma göstergesi (stStatusWidget) hem de
    spinner kullanılır; ikisi de kaybolduğunda sayfa oturmuş demektir.
    """
    page.wait_for_timeout(350)
    try:
        page.wait_for_function(
            """
            () => {
              const status = document.querySelector('[data-testid="stStatusWidget"]');
              const spinner = document.querySelector('[data-testid="stSpinner"]');
              return !status && !spinner;
            }
            """,
            timeout=timeout_ms,
        )
    except Exception:  # noqa: BLE001 - zaman aşımı turu bitirmemeli
        pass
    page.wait_for_timeout(250)


def _capture_inventory(page) -> List:
    raw = page.evaluate(INVENTORY_SCRIPT)
    return build_inventory(raw or [])


def _wait_for_main_content(page, timeout_ms: int = 30_000) -> bool:
    """Ana içerik alanında gerçekten etkileşimli öğeler belirene kadar bekler.

    `_wait_for_streamlit_idle` tek başına YETMEZ: ilk yüklemede "çalışıyor"
    göstergesi henüz belirmemiş olabilir, bu yüzden kontrol anında sayfa
    "boşta" görünür ve fonksiyon hemen döner. Sonuç olarak envanter yalnızca
    kenar çubuğunu içerir ve ajan YARI YÜKLÜ bir sayfada ilk kararını verir
    (gerçek kayıtlarda ilk adımda hep "6 öğe" görülmesinin nedeni buydu).
    """
    try:
        page.wait_for_function(
            """
            () => {
              const sidebar = document.querySelector('[data-testid="stSidebar"]');
              const controls = Array.from(document.querySelectorAll(
                'button, input, textarea, select, [role="button"], [role="radio"], [role="tab"]'
              ));
              return controls.some((el) => {
                if (sidebar && sidebar.contains(el)) return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 8 && rect.height > 8;
              });
            }
            """,
            timeout=timeout_ms,
        )
        return True
    except Exception:  # noqa: BLE001 - içerik gelmezse tur yine denenir
        return False


def _scroll_into_view(page, element):
    """Ekran dışındaki bir öğeyi görünür alana kaydırır ve YENİ konumunu döner.

    Kaydırmadan sonra koordinatlar değişir; eski koordinatlarla tıklamak
    imleci yanlış yere gönderirdi. Bu yüzden kaydırma sonrası öğe kimliğiyle
    (Streamlit anahtarı veya görünen adı) yeniden bulunup konumu tazelenir.
    """
    page.evaluate(
        """
        ([targetY, viewportHeight]) => {
          window.scrollTo({ top: window.scrollY + targetY - viewportHeight / 2, behavior: 'smooth' });
        }
        """,
        [element.y, VIEWPORT["height"]],
    )
    page.wait_for_timeout(700)

    fresh = page.evaluate(
        """
        ([key, name]) => {
          const candidates = Array.from(document.querySelectorAll(
            'button, a[href], input, textarea, select, [role="button"], [role="tab"]'
          ));
          const match = candidates.find((el) => {
            if (key) {
              let node = el;
              for (let d = 0; node && d < 12; d++, node = node.parentElement) {
                if (node.classList && node.classList.contains('st-key-' + key)) return true;
              }
              return false;
            }
            return (el.innerText || '').trim().startsWith(name);
          });
          if (!match) return null;
          const rect = match.getBoundingClientRect();
          return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
        }
        """,
        [element.key, element.name],
    )

    if fresh:
        element = element.model_copy(update=fresh)
    return element


def _fill_field_at(page, x: float, y: float, text: str) -> bool:
    """Verilen koordinattaki metin alanını doldurur ve gönderir.

    `page.keyboard.type()` KULLANILMAZ: Streamlit'in React kontrollü
    `st.chat_input` textarea'sı sentetik tuş olaylarını değer olarak
    kaydetmiyor — gönder butonu devre dışı kalıyor ve mesaj hiç
    gönderilemiyor (A2 turunda ajan bu yüzden altı kez yazmayı deneyip
    başaramamıştı). Playwright'ın `fill()`'i doğru input olaylarını
    tetiklediği için değer gerçekten yerleşir.
    """
    handle = page.evaluate_handle(
        """
        ([x, y]) => {
          const at = document.elementFromPoint(x, y);
          if (!at) return null;
          if (at.matches('input, textarea')) return at;
          return at.querySelector('input, textarea')
              || at.closest('div, label')?.querySelector('input, textarea')
              || null;
        }
        """,
        [x, y],
    )
    field = handle.as_element()
    if field is None:
        return False

    try:
        field.fill(text)
        page.wait_for_timeout(250)
        field.press("Enter")
        return True
    except Exception:  # noqa: BLE001 - alan doldurulamazsa tur devam etmeli
        return False


def _move_cursor_and_act(page, element, action: str, text: Optional[str]) -> None:
    """İmleci hedefe götürür ve eylemi uygular."""
    if element.offscreen:
        element = _scroll_into_view(page, element)

    center_x, center_y = element.center

    page.evaluate(CURSOR_INIT_SCRIPT)
    page.evaluate(
        "([x, y, d]) => window.__tourCursor.moveTo(x, y, d)",
        [center_x, center_y, CURSOR_MOVE_MS],
    )
    page.wait_for_timeout(CURSOR_MOVE_MS + 120)

    if action == ACTION_HIGHLIGHT:
        page.evaluate(
            "([x, y, w, h]) => window.__tourCursor.highlight(x, y, w, h)",
            [element.x, element.y, element.width, element.height],
        )
        return

    page.evaluate("() => window.__tourCursor.clearHighlight()")

    if action == ACTION_SCROLL_TO:
        page.mouse.wheel(0, max(0, center_y - VIEWPORT["height"] / 2))
        return

    page.evaluate("([x, y]) => window.__tourCursor.click(x, y)", [center_x, center_y])
    page.wait_for_timeout(CLICK_SETTLE_MS)

    if action == ACTION_TYPE:
        page.mouse.click(center_x, center_y)
        page.wait_for_timeout(150)
        _fill_field_at(page, center_x, center_y, text or "")
    elif action == ACTION_CLICK:
        page.mouse.click(center_x, center_y)


def _navigate_to_module(page, module: str) -> bool:
    """Kenar çubuğundaki gezinme bağlantısına tıklayarak modüle geçer."""
    nav_label = TOUR_MODULES[module]["nav_label"]
    links = page.query_selector_all('[data-testid="stSidebarNavLink"]')
    for link in links:
        text = (link.inner_text() or "").strip()
        if nav_label.split("—")[0].strip() and text.startswith(nav_label.split("—")[0].strip()):
            link.click()
            _wait_for_streamlit_idle(page)
            _wait_for_main_content(page)
            return True
    return False


def _set_language(page, language: str) -> bool:
    """Sağ üstteki TR/EN seçicisini ayarlar (kayıt öncesi hazırlık adımı).

    Dil seçici `st.segmented_control` ile çizilir ve DOM'da `<button>` DEĞİL,
    `role="radio"` olarak görünür — bu yüzden metin tabanlı bir buton
    seçicisiyle bulunamaz (ilk sürümde İngilizce tur çekilirken arayüz
    Türkçe kalmıştı). Envanterin kendisi kullanılarak doğru öğe bulunur.
    """
    label = "EN" if language == "en" else "TR"
    try:
        for element in _capture_inventory(page):
            if element.key == LANGUAGE_WIDGET_KEY and element.name.strip().upper() == label:
                center_x, center_y = element.center
                page.mouse.click(center_x, center_y)
                _wait_for_streamlit_idle(page)
                _wait_for_main_content(page)
                return True
    except Exception:  # noqa: BLE001 - dil ayarlanamazsa tur yine çekilir
        pass
    return False


def run_tour(
    module: str,
    language: str = "tr",
    model_id: Optional[str] = None,
    max_steps: Optional[int] = None,
    enable_voice: bool = True,
    progress_callback: Optional[ProgressCallback] = None,
    call_model: Optional[Callable] = None,
    output_dir: Path = OUTPUT_DIR,
) -> TourRecording:
    """Bir modülün tur videosunu uçtan uca çeker."""
    if module not in TOUR_MODULES:
        raise ValueError(f"Bilinmeyen modül: {module}. Geçerli: {sorted(TOUR_MODULES)}")

    from playwright.sync_api import sync_playwright  # noqa: PLC0415 - ağır bağımlılık

    if call_model is None:
        from services.bedrock_client import call_model as _call_model  # noqa: PLC0415

        call_model = _call_model

    notify = progress_callback or _noop
    model_id = model_id or os.environ.get("A1_TOUR_MODEL", "google.gemma-4-31b")
    max_steps = max_steps or int(os.environ.get("A1_TOUR_MAX_STEPS", DEFAULT_MAX_STEPS))

    tts = get_tts_engine(prefer_polly=enable_voice)
    if isinstance(tts, NullTTS):
        notify(TourProgress(stage="voice", message=tts.description, valid=False))
    else:
        notify(TourProgress(stage="voice", message=tts.description))

    output_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = Path(tempfile.mkdtemp(prefix="tour_audio_"))
    video_dir = Path(tempfile.mkdtemp(prefix="tour_video_"))

    context = AgentContext(
        module_title=module_title(module, language),
        language=language,
        max_steps=max_steps,
    )
    steps: List[TourStep] = []
    step_dump: List[Dict] = []
    stopped_reason = ""
    total_cost = 0.0

    notify(TourProgress(stage="server", message="Uygulama başlatılıyor..."))

    with running_app() as server:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser_context = browser.new_context(
                viewport=VIEWPORT,
                record_video_dir=str(video_dir),
                record_video_size=VIEWPORT,
            )
            browser_context.add_init_script(CURSOR_INIT_SCRIPT)
            page = browser_context.new_page()

            try:
                notify(TourProgress(stage="open", message=f"Tarayıcı açılıyor: {server.base_url}"))
                page.goto(server.base_url, wait_until="domcontentloaded", timeout=60_000)
                _wait_for_streamlit_idle(page)
                _wait_for_main_content(page)

                if not _set_language(page, language):
                    notify(
                        TourProgress(
                            stage="open",
                            message=f"Dil '{language}' olarak ayarlanamadı; arayüz varsayılan dilde kalabilir.",
                            valid=False,
                        )
                    )
                if not _navigate_to_module(page, module):
                    stopped_reason = f"'{module}' modülünün gezinme bağlantısı bulunamadı."
                    notify(TourProgress(stage="error", message=stopped_reason, valid=False))

                recording_started = time.monotonic()

                if not stopped_reason:
                    for step_index in range(1, max_steps + 1):
                        page.evaluate(CURSOR_INIT_SCRIPT)
                        screenshot = page.screenshot()
                        inventory = _capture_inventory(page)

                        notify(
                            TourProgress(
                                stage="thinking",
                                step_index=step_index,
                                message=f"Ajan {len(inventory)} öğe arasından karar veriyor...",
                                screenshot=screenshot,
                            )
                        )

                        # Geçersiz karar gelirse ajana hatası bildirilip yeniden
                        # sorulur; tek bir bozuk karar turu öldürmemeli.
                        result = None
                        for attempt in range(MAX_DECISION_RETRIES + 1):
                            result = decide_next_step(
                                call_model=call_model,
                                model_id=model_id,
                                context=context,
                                inventory=inventory,
                                screenshot_bytes=screenshot,
                                step_index=step_index,
                            )

                            if result.estimated_cost_usd:
                                total_cost += result.estimated_cost_usd

                            log_evaluation(
                                feature=FEATURE_NAME,
                                model_id=model_id,
                                input_tokens=result.input_tokens,
                                output_tokens=result.output_tokens,
                                total_tokens=result.total_tokens,
                                latency_ms=result.latency_ms,
                                estimated_cost_usd=result.estimated_cost_usd,
                                json_valid=result.decision is not None,
                                schema_valid=result.decision is not None,
                                question_count=1,
                                success=result.call_success,
                                error=result.call_error,
                                tour_module=module,
                                tour_language=language,
                                tour_step_index=step_index,
                                tour_action=result.decision.action if result.decision else "",
                                tour_decision_valid=result.valid,
                                tour_decision_error="; ".join(result.errors),
                            )

                            if result.valid:
                                context.last_error = None
                                break

                            context.last_error = "; ".join(result.errors)
                            notify(
                                TourProgress(
                                    stage="retry",
                                    step_index=step_index,
                                    message=f"{context.last_error} (yeniden deneniyor {attempt + 1}/{MAX_DECISION_RETRIES})",
                                    valid=False,
                                )
                            )

                        if result is None or result.decision is None or not result.valid:
                            stopped_reason = (
                                "; ".join(result.errors) if result else "Ajan geçerli bir karar üretemedi."
                            )
                            notify(
                                TourProgress(
                                    stage="invalid",
                                    step_index=step_index,
                                    message=stopped_reason,
                                    valid=False,
                                )
                            )
                            break

                        decision = result.decision
                        if decision.action == ACTION_DONE:
                            stopped_reason = "Ajan turu tamamladı."
                            notify(
                                TourProgress(
                                    stage="done",
                                    step_index=step_index,
                                    message=stopped_reason,
                                    narration=decision.narration,
                                )
                            )
                            break

                        speech = tts.synthesize(
                            decision.narration,
                            language,
                            audio_dir / f"step_{step_index:02d}.mp3",
                        )
                        start_seconds = time.monotonic() - recording_started

                        notify(
                            TourProgress(
                                stage="acting",
                                step_index=step_index,
                                message=result.element.name if result.element else decision.action,
                                narration=decision.narration,
                                action=decision.action,
                            )
                        )

                        if result.element is not None:
                            _move_cursor_and_act(page, result.element, decision.action, decision.text)
                            _wait_for_streamlit_idle(page)

                        elapsed = (time.monotonic() - recording_started) - start_seconds
                        remaining = max(0.0, speech.duration_seconds - elapsed)
                        if remaining > 0:
                            page.wait_for_timeout(int(remaining * 1000))

                        steps.append(
                            TourStep(
                                index=step_index,
                                action=decision.action,
                                element_index=decision.element_index,
                                element_name=result.element.name if result.element else None,
                                text=decision.text,
                                narration=decision.narration,
                                reason=decision.reason,
                                start_seconds=start_seconds,
                                duration_seconds=max(
                                    speech.duration_seconds,
                                    (time.monotonic() - recording_started) - start_seconds,
                                ),
                                audio_path=str(speech.audio_path) if speech.audio_path else None,
                                model_id=model_id,
                                latency_ms=result.latency_ms,
                                estimated_cost_usd=result.estimated_cost_usd,
                            )
                        )
                        step_dump.append(summarize_decision(decision, result.element))
                        context.remember(decision, result.element, result.signature)
                    else:
                        stopped_reason = f"Adım sınırına ulaşıldı ({max_steps})."

                total_seconds = time.monotonic() - recording_started
            finally:
                video_object = page.video
                browser_context.close()
                browser.close()

            raw_video_path = Path(video_object.path()) if video_object else None

    notify(TourProgress(stage="render", message="Video işleniyor (altyazı/ses)..."))

    base_name = f"{module}_{language}"
    subtitle_path = write_srt(steps, output_dir / f"{base_name}.srt") if steps else None
    output_path = output_dir / f"{base_name}.mp4"

    voiced = False
    if raw_video_path and raw_video_path.exists() and steps:
        render_result = render_final_video(
            raw_video_path,
            steps,
            output_path,
            subtitle_path=subtitle_path,
            total_seconds=total_seconds,
        )
        if render_result["success"]:
            voiced = render_result["voiced"]
        else:
            # FFmpeg başarısızsa ham kaydı yine de sun — hata gizlenmez.
            fallback = output_dir / f"{base_name}.webm"
            shutil.copy(raw_video_path, fallback)
            output_path = fallback
            stopped_reason = f"{stopped_reason} (Video işlenemedi: {render_result['error']})".strip()
    else:
        output_path = None

    recording = TourRecording(
        module=module,
        language=language,
        model_id=model_id,
        steps=steps,
        video_path=str(output_path) if output_path else None,
        subtitle_path=str(subtitle_path) if subtitle_path else None,
        total_seconds=round(total_seconds, 2),
        voiced=voiced,
        voice_unavailable_reason=None if voiced else tts.description,
        source_fingerprint=compute_source_fingerprint(module),
        total_cost_usd=round(total_cost, 6) if total_cost else None,
        stopped_reason=stopped_reason,
    )

    dump_steps_json(step_dump, output_dir / f"{base_name}.steps.json")
    (output_dir / f"{base_name}.meta.json").write_text(
        recording.model_dump_json(indent=2, exclude={"steps"}), encoding="utf-8"
    )

    notify(TourProgress(stage="finished", message=stopped_reason or "Tur tamamlandı."))
    return recording


def load_existing_recordings(output_dir: Path = OUTPUT_DIR) -> List[Dict]:
    """Daha önce üretilmiş kayıtların metaverisini okur (stüdyo listesi için)."""
    if not output_dir.exists():
        return []
    recordings: List[Dict] = []
    for meta_path in sorted(output_dir.glob("*.meta.json")):
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        module = data.get("module")
        if module in TOUR_MODULES:
            data["fingerprint_current"] = compute_source_fingerprint(module)
            data["is_stale"] = data.get("source_fingerprint") != data["fingerprint_current"]
        recordings.append(data)
    return recordings
