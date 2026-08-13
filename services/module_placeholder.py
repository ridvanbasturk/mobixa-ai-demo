"""Henüz uygulanmamış modüller için paylaşılan placeholder ekranı."""
from __future__ import annotations

import streamlit as st


def render_placeholder(title: str) -> None:
    st.title(title)
    st.info("Bu modül bir sonraki geliştirme aşamasında eklenecektir.")
