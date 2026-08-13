"""A1 (AI Destekli Kullanım Videosu Stüdyosu) modülüne özgü metinler.

A1, sayfa dosyası tek başına ~2600 satır ve 6 şema/9 servis dosyasına
yayılmış ~1000 Türkçe string içerdiği için bu turda YALNIZCA dış kabuk
(başlık/caption/sidebar/dil uyarısı) çevrildi. Sayfanın geri kalanı
(proje girdisi, storyboard, video, görsel analiz akışları) bir sonraki
işe bırakıldı — bkz. CLAUDE.md."""
from __future__ import annotations

TR = {
    "a1.page_subtitle": "A1 — AI Destekli Kullanım Videosu Stüdyosu",
    "a1.i18n_scope_notice": (
        "Bu modülün arayüzü şu an yalnızca kısmen çevrilmiştir: başlık, "
        "sidebar ve genel çerçeve TR/EN destekler; proje girdisi, "
        "storyboard, video ve görsel analiz bölümlerinin tam çevirisi "
        "sonraki bir aşamada tamamlanacaktır."
    ),
}

EN = {
    "a1.page_subtitle": "A1 — AI-Assisted Tutorial Video Studio",
    "a1.i18n_scope_notice": (
        "This module's interface is currently only partially translated: "
        "the title, sidebar and overall shell support TR/EN; full "
        "translation of the project intake, storyboard, video and visual "
        "analysis sections will be completed in a later phase. Below is "
        "still shown in Turkish."
    ),
}
