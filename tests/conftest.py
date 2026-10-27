# 2026-10-27 16:04 KST
"""테스트마다 Supabase 안에 임시 스키마를 만들어 그 안에서만 돌리고 지운다.

실제 앱이 쓰는 public 스키마의 tf_ 테이블은 건드리지 않는다.
"""
import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

load_dotenv()


def _url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL 없음")
    return url


@pytest.fixture
def schema_name():
    from tf.db import apply_schema

    name = f"tf_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(_url(), autocommit=True) as admin:
        admin.execute(f'create schema "{name}"')
        admin.execute(f'set search_path to "{name}"')
        apply_schema(admin)
    yield name
    with psycopg.connect(_url(), autocommit=True) as admin:
        admin.execute(f'drop schema "{name}" cascade')


@pytest.fixture
def connect(schema_name):
    """같은 임시 스키마를 search_path로 둔 새 연결을 돌려주는 함수."""
    opened = []

    def _connect(autocommit: bool = True) -> psycopg.Connection:
        conn = psycopg.connect(_url(), autocommit=autocommit)
        conn.execute(f'set search_path to "{schema_name}"')
        if not autocommit:
            conn.commit()
        opened.append(conn)
        return conn

    yield _connect
    for c in opened:
        c.close()


@pytest.fixture
def conn(connect):
    return connect()
