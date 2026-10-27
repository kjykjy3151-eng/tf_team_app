# 2026-10-27 16:12 KST
"""비밀번호 해시, 로그인, 관리자 계정."""
from dataclasses import dataclass

import bcrypt
import psycopg

from tf.config import ADMIN_NO


@dataclass(frozen=True)
class User:
    student_no: str
    name: str
    is_admin: bool


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())


def login(conn: psycopg.Connection, student_no: str, password: str) -> User | None:
    """학번과 비밀번호가 모두 맞을 때만 User를 돌려준다."""
    student_no = student_no.strip()
    if not student_no or not password:
        return None
    row = conn.execute(
        "select name, password_hash, is_admin from tf_students where student_no = %s", (student_no,)
    ).fetchone()
    if row is None or not check_password(password, row[1]):
        return None
    return User(student_no, row[0], row[2])


def ensure_admin(conn: psycopg.Connection, password: str) -> None:
    """관리자 계정이 없으면 만들고, 있으면 비밀번호를 갱신한다."""
    conn.execute(
        "insert into tf_students (student_no, name, main_role, password_hash, is_admin)"
        " values (%s, '관리자', null, %s, true)"
        " on conflict (student_no) do update set password_hash = excluded.password_hash, is_admin = true",
        (ADMIN_NO, hash_password(password)),
    )


def require_admin(user: User | None) -> None:
    """관리자 기능 함수가 맨 앞에서 부른다."""
    if user is None or not user.is_admin:
        raise PermissionError("막힘: 관리자만 할 수 있음")
