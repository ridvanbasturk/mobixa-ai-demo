"""Mobixa AI Demo — giriş noktası ve modül navigasyonu.

B1, B6, C1, A2 aktiftir. A1 Faz 1 (proje girdi hazırlığı) aktiftir;
storyboard/video üretimi sonraki fazlarda eklenecektir.
"""
import streamlit as st

st.set_page_config(page_title="Mobixa AI Demo", layout="wide")

pages = [
    st.Page("app_pages/b1_content_generation.py", title="B1 — İçerik Üretimi", default=True),
    st.Page("app_pages/b6_report_insights.py", title="B6 — Rapor Değerlendirmesi"),
    st.Page("app_pages/c1_learning_path.py", title="C1 — Öğrenme Yolu"),
    st.Page("app_pages/a2_support_chatbot.py", title="A2 — Destek Chatbot'u"),
    st.Page("app_pages/a1_tutorial_video.py", title="A1 — Kullanım Videosu Stüdyosu"),
]

navigation = st.navigation(pages)
navigation.run()
