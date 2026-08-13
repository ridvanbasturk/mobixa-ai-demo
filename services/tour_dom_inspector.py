"""Canlı Streamlit sayfasından etkileşimli öğe envanteri çıkarır.

Bu katman TAMAMEN DETERMİNİSTİKTİR — model burada devrede değildir. Amaç,
ajanın "ekranda ne var" sorusuna piksel tahminiyle değil, gerçek DOM'a
dayanarak cevap verebilmesidir. Böylece ajan yine her adımda kendi kararını
verir ama imleç her zaman gerçek bir kontrolün üzerine gider.

Streamlit'e özgü seçiciler (bu oturumda 1.59.2 üzerinde doğrulandı):
  - `.st-key-<key>`            : `key=` verilmiş her widget'ın sarmalayıcısı
  - `[data-testid=stSidebar]`  : kenar çubuğu
  - `[data-testid=stSidebarNavLink]` : modüller arası gezinme bağlantıları
"""
from __future__ import annotations

from typing import List

from schemas.tour_models import TourElement

# Sayfada görünür ve etkileşimli olan öğeleri toplayan JS. Bilinçli olarak
# "her şeyi" değil, bir kullanıcının gerçekten tıklayabileceği/yazabileceği
# öğeleri döndürür; ayrıca çok küçük veya ekran dışındaki öğeleri eler.
INVENTORY_SCRIPT = """
() => {
  const SELECTOR = [
    'button',
    'a[href]',
    'input',
    'textarea',
    'select',
    '[role="button"]',
    '[role="checkbox"]',
    '[role="radio"]',
    '[role="tab"]',
    '[role="combobox"]',
    '[role="slider"]',
    '[data-testid="stSidebarNavLink"]',
  ].join(',');

  const MIN_SIZE = 8;
  const seen = new Set();
  const out = [];

  // ÖNEMLİ: görünür alan (viewport) dışındaki öğeler ELENMEZ, yalnızca
  // "offscreen" olarak işaretlenir. Aksi halde uzun sayfalarda ekranın
  // altında kalan ASIL eylem butonu (ör. "İki Modelle Journey Üret") ajana
  // hiç görünmez; ajan sayfanın asıl işini yaptıramadan turu bitirir.
  const visible = (el, rect) => {
    if (rect.width < MIN_SIZE || rect.height < MIN_SIZE) return false;
    const style = window.getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') return false;
    if (parseFloat(style.opacity || '1') < 0.05) return false;
    return true;
  };

  const isOffscreen = (rect) =>
    rect.bottom < 0 || rect.top > window.innerHeight ||
    rect.right < 0 || rect.left > window.innerWidth;

  const accessibleName = (el) => {
    const aria = el.getAttribute('aria-label');
    if (aria && aria.trim()) return aria.trim();
    const labelled = el.getAttribute('aria-labelledby');
    if (labelled) {
      const target = document.getElementById(labelled);
      if (target && target.innerText.trim()) return target.innerText.trim();
    }
    const text = (el.innerText || '').trim();
    if (text) return text.split('\\n')[0].slice(0, 120);

    // Streamlit'te radio/checkbox girdilerinin kendi metni yoktur; görünen
    // etiket onları saran <label> içindedir. Bu olmadan ajan "[3] radio-input:
    // ''" gibi anlamsız bir satır görür ve hangi seçeneği seçtiğini bilemez.
    const label = el.closest('label');
    if (label) {
      const labelText = (label.innerText || '').trim();
      if (labelText) return labelText.split('\\n')[0].slice(0, 120);
    }

    const placeholder = el.getAttribute('placeholder');
    if (placeholder && placeholder.trim()) return placeholder.trim();
    const title = el.getAttribute('title');
    if (title && title.trim()) return title.trim();
    return '';
  };

  const streamlitKey = (el) => {
    let node = el;
    for (let depth = 0; node && depth < 12; depth++, node = node.parentElement) {
      if (!node.classList) continue;
      for (const cls of node.classList) {
        if (cls.startsWith('st-key-')) return cls.slice('st-key-'.length);
      }
    }
    return null;
  };

  const roleOf = (el) => {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    if (tag === 'input') return (el.getAttribute('type') || 'text') + '-input';
    if (tag === 'textarea') return 'textarea';
    if (tag === 'a') return 'link';
    if (el.getAttribute('data-testid') === 'stSidebarNavLink') return 'nav-link';
    return tag;
  };

  const sidebar = document.querySelector('[data-testid="stSidebar"]');

  document.querySelectorAll(SELECTOR).forEach((el) => {
    const rect = el.getBoundingClientRect();
    if (!visible(el, rect)) return;

    // Aynı kontrolün iç içe sarmalayıcılarını tek kez al.
    const positionKey = [Math.round(rect.x), Math.round(rect.y),
                         Math.round(rect.width), Math.round(rect.height)].join(':');
    if (seen.has(positionKey)) return;
    seen.add(positionKey);

    const name = accessibleName(el);
    const key = streamlitKey(el);
    if (!name && !key) return;  // adsız ve anahtarsız öğe ajana bir şey ifade etmez

    out.push({
      role: roleOf(el),
      name: name,
      key: key,
      x: rect.x,
      y: rect.y,
      width: rect.width,
      height: rect.height,
      in_sidebar: sidebar ? sidebar.contains(el) : false,
      enabled: !(el.disabled === true || el.getAttribute('aria-disabled') === 'true'),
      offscreen: isOffscreen(rect),
    });
  });

  // Kararlı sıra: önce ana alan (yukarıdan aşağı), sonra kenar çubuğu.
  out.sort((a, b) => {
    if (a.in_sidebar !== b.in_sidebar) return a.in_sidebar ? 1 : -1;
    if (Math.abs(a.y - b.y) > 6) return a.y - b.y;
    return a.x - b.x;
  });

  return out;
}
"""


def build_inventory(raw_elements: List[dict]) -> List[TourElement]:
    """JS'ten dönen ham listeyi numaralandırılmış TourElement listesine çevirir.

    Numaralandırma burada (Python tarafında) yapılır ki envanterle modele
    gönderilen rozetli görüntü aynı indeksleri kullansın.
    """
    inventory: List[TourElement] = []
    for index, raw in enumerate(raw_elements, start=1):
        inventory.append(
            TourElement(
                index=index,
                role=str(raw.get("role") or "unknown"),
                name=str(raw.get("name") or "").strip(),
                key=(raw.get("key") or None),
                x=float(raw.get("x") or 0.0),
                y=float(raw.get("y") or 0.0),
                width=float(raw.get("width") or 0.0),
                height=float(raw.get("height") or 0.0),
                in_sidebar=bool(raw.get("in_sidebar")),
                enabled=bool(raw.get("enabled", True)),
                offscreen=bool(raw.get("offscreen")),
            )
        )
    return inventory


def format_inventory_for_model(inventory: List[TourElement]) -> str:
    """Envanteri modele gönderilecek metin bloğuna çevirir."""
    if not inventory:
        return "(Ekranda etkileşimli öğe bulunamadı.)"
    return "\n".join(element.describe() for element in inventory)
