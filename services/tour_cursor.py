"""Videoda görünen yapay imleç overlay'i.

Playwright'ın yerleşik video kaydı GERÇEK fare imlecini kaydetmez — kayıtta
imleç hiç görünmez. Bu yüzden sayfaya kendi imlecimizi bir DOM öğesi olarak
enjekte ediyoruz: yumuşak hareket eden bir ok ve tıklama anında genişleyen
bir halka.

`add_init_script` ile enjekte edilir; Streamlit tek sayfalık (SPA) bir
uygulama olduğu için yeniden çalıştırmalarda (rerun) overlay kaybolmaz, ancak
sayfa gezinmelerine karşı `ensure_cursor` ile savunmacı biçimde tekrar
kurulabilir.
"""
from __future__ import annotations

# Overlay'i kuran ve global `window.__tourCursor` API'sini tanımlayan script.
# Idempotenttir: birden fazla kez çalıştırılırsa ikinci imleci oluşturmaz.
CURSOR_INIT_SCRIPT = r"""
(() => {
  if (window.__tourCursor) return;

  const install = () => {
    if (document.getElementById('__tour_cursor')) return;

    const style = document.createElement('style');
    style.id = '__tour_cursor_style';
    style.textContent = `
      #__tour_cursor {
        position: fixed;
        top: 0; left: 0;
        width: 24px; height: 24px;
        margin: -2px 0 0 -2px;
        pointer-events: none;
        z-index: 2147483647;
        transform: translate(-100px, -100px);
        transition: transform 120ms linear;
        will-change: transform;
      }
      #__tour_cursor svg { display: block; filter: drop-shadow(0 2px 3px rgba(0,0,0,.45)); }
      #__tour_ripple {
        position: fixed;
        top: 0; left: 0;
        width: 14px; height: 14px;
        margin: -7px 0 0 -7px;
        border-radius: 50%;
        border: 2px solid rgba(47,111,94,.9);
        background: rgba(47,111,94,.22);
        pointer-events: none;
        z-index: 2147483646;
        opacity: 0;
        transform: translate(-100px, -100px) scale(1);
      }
      @keyframes __tour_ripple_anim {
        0%   { opacity: .95; }
        100% { opacity: 0; }
      }
      #__tour_halo {
        position: fixed;
        top: 0; left: 0;
        border: 2px solid rgba(47,111,94,.95);
        border-radius: 6px;
        box-shadow: 0 0 0 3px rgba(47,111,94,.18);
        pointer-events: none;
        z-index: 2147483645;
        opacity: 0;
        transition: opacity 180ms ease, top 260ms ease, left 260ms ease,
                    width 260ms ease, height 260ms ease;
      }
    `;
    document.head.appendChild(style);

    const halo = document.createElement('div');
    halo.id = '__tour_halo';
    document.body.appendChild(halo);

    const ripple = document.createElement('div');
    ripple.id = '__tour_ripple';
    document.body.appendChild(ripple);

    const cursor = document.createElement('div');
    cursor.id = '__tour_cursor';
    cursor.innerHTML =
      '<svg width="24" height="24" viewBox="0 0 24 24" fill="none">' +
      '<path d="M4 2 L4 19 L8.6 14.7 L11.4 21 L14.3 19.7 L11.6 13.6 L18 13.3 Z" ' +
      'fill="#ffffff" stroke="#182420" stroke-width="1.4" stroke-linejoin="round"/>' +
      '</svg>';
    document.body.appendChild(cursor);
  };

  if (document.body) {
    install();
  } else {
    document.addEventListener('DOMContentLoaded', install);
  }

  window.__tourCursor = {
    ensure: install,

    moveTo(x, y, durationMs) {
      install();
      const cursor = document.getElementById('__tour_cursor');
      if (!cursor) return;
      cursor.style.transition = `transform ${Math.max(0, durationMs | 0)}ms cubic-bezier(.33,.7,.32,1)`;
      cursor.style.transform = `translate(${x}px, ${y}px)`;
    },

    click(x, y) {
      install();
      const ripple = document.getElementById('__tour_ripple');
      if (!ripple) return;
      ripple.style.animation = 'none';
      ripple.style.transform = `translate(${x}px, ${y}px) scale(1)`;
      // reflow -> animasyon yeniden başlasın
      void ripple.offsetWidth;
      ripple.style.animation = '__tour_ripple_anim 450ms ease-out';
      ripple.style.transform = `translate(${x}px, ${y}px) scale(2.6)`;
    },

    highlight(x, y, width, height) {
      install();
      const halo = document.getElementById('__tour_halo');
      if (!halo) return;
      halo.style.left = (x - 4) + 'px';
      halo.style.top = (y - 4) + 'px';
      halo.style.width = (width + 8) + 'px';
      halo.style.height = (height + 8) + 'px';
      halo.style.opacity = '1';
    },

    clearHighlight() {
      const halo = document.getElementById('__tour_halo');
      if (halo) halo.style.opacity = '0';
    },
  };
})();
"""

# İmlecin bir noktadan diğerine kayma süresi (ms). Videonun izlenebilir
# olması için insan hızına yakın tutulur.
CURSOR_MOVE_MS = 620

# Tıklama sonrası halkanın sönmesi için beklenen süre (ms).
CLICK_SETTLE_MS = 260
