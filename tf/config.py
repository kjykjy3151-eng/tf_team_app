# 2026-10-27 16:05 KST
"""앱 전체에서 쓰는 상수와 비밀 값 읽기."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

ROLES: tuple[str, ...] = ("기획자", "웹 프로그래머", "프론트엔드 디자이너", "테스터", "보고서 작성자", "발표자")
REQUIRED_ROLES: tuple[str, ...] = ("기획자", "웹 프로그래머")
TEAM_MIN = 2
TEAM_MAX = 4
STUDENT_PASSWORD = "1234"
ADMIN_NO = "admin"

KST = ZoneInfo("Asia/Seoul")


def get_secret(name: str) -> str | None:
    """배포에서는 Streamlit Secrets, 로컬에서는 .env에서 같은 이름의 값을 읽는다. 값은 출력하지 않는다."""
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass  # secrets.toml이 없으면 .env를 쓴다.
    from dotenv import load_dotenv

    load_dotenv()
    return os.getenv(name) or None


def to_kst(dt: datetime) -> str:
    """DB의 시각(UTC)을 한국 시각 문자열로 바꾼다."""
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
