# 2026-10-27 16:05 KST
import os

import psycopg
import pytest
from dotenv import load_dotenv

from tf.db import make_pool

load_dotenv()


def test_pool_recovers_after_connection_killed():
    url = os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL 없음")
    pool = make_pool(url)
    try:
        with pool.connection() as conn:
            with pytest.raises(psycopg.OperationalError):
                conn.execute("select pg_terminate_backend(pg_backend_pid())")
        with pool.connection() as conn:
            assert conn.execute("select 1").fetchone()[0] == 1
    finally:
        pool.close()
