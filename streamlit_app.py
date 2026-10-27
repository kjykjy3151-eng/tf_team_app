# 2026-10-27 16:08 KST
"""팀 편성 앱 진입점. 1단계에서는 DB 연결만 확인한다."""
import streamlit as st

from tf.db import get_pool

st.set_page_config(page_title="팀 편성")

try:
    with get_pool().connection() as conn:
        conn.execute("select 1").fetchone()
    st.write("DB 연결: 있음")
except Exception as e:
    # 예외 메시지에 DB 주소가 섞일 수 있어 종류만 보여 준다.
    st.write(f"DB 연결: 없음({type(e).__name__})")
