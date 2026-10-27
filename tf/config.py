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


# 오픈라우터 무료 텍스트 생성 모델(공고 4.3절). 1차가 실패하면 2차, 3차로 넘어간다.
# 이름이 :free로 끝나는 모델만 쓴다(비용 0원). openrouter/free 라우터는 쓰지 않는다.
AI_MODELS: tuple[str, str, str] = (
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemma-4-31b-it:free",
    "poolside/laguna-s-2.1:free",
)
AI_DEADLINE_SEC = 120  # 모델 하나를 부른 때부터 응답을 다 받을 때까지
AI_MAX_TOKENS = 8000
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
