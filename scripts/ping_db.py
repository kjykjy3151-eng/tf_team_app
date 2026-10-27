# 2026-10-27 17:22 KST
"""DB에 SELECT 1을 보낸다(Supabase 무료 프로젝트 일시정지 막기, 공고 3장 어려운 해결).

DATABASE_URL 환경 변수를 쓴다. 주소와 오류 메시지 본문은 출력하지 않는다(주소가 섞일 수 있음).
"""
import os
import sys

import psycopg


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL: 없음")
        return 1
    try:
        with psycopg.connect(url, connect_timeout=20) as conn:
            value = conn.execute("select 1").fetchone()[0]
    except Exception as e:
        print(f"DB 응답 실패: {type(e).__name__}")
        return 1
    print(f"DB 응답: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
