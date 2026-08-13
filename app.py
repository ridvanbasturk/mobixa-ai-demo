"""Mobixa AI Demo — giriş noktası ve modül navigasyonu.

B1, B6, C1, A2 içerik/analiz modülleridir. A1 ise diğer modülleri konu alan
otomatik ürün turu videolarını üreten stüdyodur (tarayıcıyı gerçekten süren
görsel bir ajan tarafından kaydedilir).
"""
import streamlit as st

st.set_page_config(page_title="Mobixa AI Demo", layout="wide")

pages = [
    st.Page("app_pages/b1_content_generation.py", title="B1 — İçerik Üretimi", default=True),
    st.Page("app_pages/b6_report_insights.py", title="B6 — Rapor Değerlendirmesi"),
    st.Page("app_pages/c1_learning_path.py", title="C1 — Öğrenme Yolu"),
    st.Page("app_pages/a2_support_chatbot.py", title="A2 — Destek Chatbot'u"),
    st.Page("app_pages/a1_tour_studio.py", title="A1 — Ürün Turu Stüdyosu"),
]

navigation = st.navigation(pages)
navigation.run()
