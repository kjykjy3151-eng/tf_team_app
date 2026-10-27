# 2026-10-27 16:05 KST
"""DB 연결 풀. 연결은 풀에서 빌려 다시 쓴다(공고 4.2절)."""
from pathlib import Path

import psycopg
import streamlit as st
from psycopg_pool import ConnectionPool

from tf.config import get_secret

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "schema.sql"


def make_pool(url: str) -> ConnectionPool:
    """연결 몇 개를 만들어 두고 돌려 쓰는 풀. 끊긴 연결은 빌려줄 때 검사해 새로 만든다."""
    return ConnectionPool(
        url,
        min_size=1,
        max_size=4,
        check=ConnectionPool.check_connection,
        kwargs={"connect_timeout": 10},
        open=True,
    )


@st.cache_resource
def get_pool() -> ConnectionPool:
    """앱 프로세스에서 한 번만 만든다."""
    url = get_secret("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL 없음")
    return make_pool(url)


def apply_schema(conn: psycopg.Connection) -> None:
    """schema.sql을 실행해 tf_ 테이블을 만든다."""
    conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
