# 2026-10-27 16:12 KST
"""명단 CSV 읽기와 명단으로 처음 상태 만들기(공고 2.6절)."""
import csv
import io

import psycopg

from tf.auth import User, hash_password, require_admin
from tf.config import ADMIN_NO, ROLES, STUDENT_PASSWORD
from tf.rules import Student

COLUMNS = ["student_no", "name", "main_role", "sub_roles"]


class RosterError(Exception):
    pass


def parse_roster(data: bytes) -> list[Student]:
    """BOM이 있어도 읽는다(utf-8-sig). 값 앞뒤 공백과 빈 줄은 무시한다."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise RosterError("CSV를 UTF-8로 읽을 수 없음")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or [c.strip() for c in rows[0]] != COLUMNS:
        raise RosterError("CSV 1행: 머리글이 student_no,name,main_role,sub_roles가 아님")

    students: list[Student] = []
    seen: set[str] = set()
    for line_no, row in enumerate(rows[1:], start=2):
        cells = [c.strip() for c in row]
        if not any(cells):
            continue
        if len(cells) != 4:
            raise RosterError(f"CSV {line_no}행: 열이 4개가 아님")
        no, name, main_role, subs = cells
        sub_roles = tuple(s.strip() for s in subs.split(";") if s.strip())
        if not no or not name:
            raise RosterError(f"CSV {line_no}행: 학번이나 이름이 비어 있음")
        if no == ADMIN_NO:
            raise RosterError(f"CSV {line_no}행: 학번 admin은 쓸 수 없음")
        if no in seen:
            raise RosterError(f"CSV {line_no}행: 학번 {no}이(가) 겹침")
        if main_role not in ROLES:
            raise RosterError(f"CSV {line_no}행: 주 역할 '{main_role}'은(는) 6개 역할이 아님")
        bad = [r for r in sub_roles if r not in ROLES]
        if bad:
            raise RosterError(f"CSV {line_no}행: 보조 역할 '{bad[0]}'은(는) 6개 역할이 아님")
        if main_role in sub_roles:
            raise RosterError(f"CSV {line_no}행: 보조 역할에 주 역할 '{main_role}'이(가) 또 있음")
        if len(sub_roles) > 2 or len(set(sub_roles)) != len(sub_roles):
            raise RosterError(f"CSV {line_no}행: 보조 역할은 서로 다른 0~2개여야 함")
        seen.add(no)
        students.append(Student(no, name, main_role, sub_roles))
    if not students:
        raise RosterError("CSV에 학생이 없음")
    return students


def reset_with_roster(conn: psycopg.Connection, user: User, students: list[Student], team_count: int) -> None:
    """지원, 투표, 팀원, 마감 표시를 지우고 명단의 학생과 빈 팀을 만든다. 관리자 계정은 남긴다."""
    require_admin(user)
    if team_count < 1:
        raise RosterError("팀 수는 1 이상이어야 함")
    password_hash = hash_password(STUDENT_PASSWORD)  # 모두 같은 비밀번호이므로 한 번만 해시한다.
    with conn.transaction():
        conn.execute("delete from tf_votes")
        conn.execute("delete from tf_applications")
        conn.execute("delete from tf_members")
        conn.execute("delete from tf_teams")
        conn.execute("delete from tf_students where not is_admin")
        # DB 서버와 왕복을 줄이려고 여러 행을 한 번에 보낸다.
        with conn.cursor() as cur:
            cur.executemany(
                "insert into tf_students (student_no, name, main_role, password_hash) values (%s, %s, %s, %s)",
                [(s.student_no, s.name, s.main_role, password_hash) for s in students],
            )
            ids = dict(cur.execute("select student_no, id from tf_students where not is_admin").fetchall())
            cur.executemany(
                "insert into tf_student_sub_roles (student_id, role) values (%s, %s)",
                [(ids[s.student_no], role) for s in students for role in s.sub_roles],
            )
            cur.executemany(
                "insert into tf_teams (id, name) values (%s, %s)",
                [(no, f"팀{no}") for no in range(1, team_count + 1)],
            )
        conn.execute(
            "insert into tf_settings (key, value) values ('closed', 'false')"
            " on conflict (key) do update set value = 'false'"
        )
