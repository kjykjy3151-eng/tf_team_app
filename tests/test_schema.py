# 2026-10-27 16:04 KST
import psycopg
import pytest
from psycopg import errors


def _student(conn, no: str, role: str = "기획자") -> int:
    return conn.execute(
        "insert into tf_students (student_no, name, main_role, password_hash)"
        " values (%s, %s, %s, 'x') returning id",
        (no, f"이름{no}", role),
    ).fetchone()[0]


def _team(conn, no: int) -> int:
    conn.execute("insert into tf_teams (id, name) values (%s, %s)", (no, f"팀{no}"))
    return no


def _application(conn, team_id: int, student_id: int, status: str = "대기") -> int:
    return conn.execute(
        "insert into tf_applications (team_id, student_id, status) values (%s, %s, %s) returning id",
        (team_id, student_id, status),
    ).fetchone()[0]


def test_all_tables_start_with_tf(conn, schema_name):
    rows = conn.execute(
        "select table_name from information_schema.tables where table_schema = %s",
        (schema_name,),
    ).fetchall()
    names = sorted(r[0] for r in rows)
    assert names == [
        "tf_ai_logs", "tf_applications", "tf_members", "tf_settings",
        "tf_student_sub_roles", "tf_students", "tf_teams", "tf_votes",
    ]


def test_slot_no_must_be_1_to_4(conn):
    t = _team(conn, 1)
    s = _student(conn, "1")
    with pytest.raises(errors.CheckViolation):
        conn.execute("insert into tf_members (team_id, slot_no, student_id) values (%s, 5, %s)", (t, s))


def test_same_slot_twice_rejected(conn):
    t = _team(conn, 1)
    a, b = _student(conn, "1"), _student(conn, "2", "테스터")
    conn.execute("insert into tf_members (team_id, slot_no, student_id) values (%s, 1, %s)", (t, a))
    with pytest.raises(errors.UniqueViolation):
        conn.execute("insert into tf_members (team_id, slot_no, student_id) values (%s, 1, %s)", (t, b))


def test_student_in_two_teams_rejected(conn):
    t1, t2 = _team(conn, 1), _team(conn, 2)
    s = _student(conn, "1")
    conn.execute("insert into tf_members (team_id, slot_no, student_id) values (%s, 1, %s)", (t1, s))
    with pytest.raises(errors.UniqueViolation):
        conn.execute("insert into tf_members (team_id, slot_no, student_id) values (%s, 1, %s)", (t2, s))


def test_unknown_role_rejected(conn):
    with pytest.raises(errors.CheckViolation):
        _student(conn, "1", "디자이너")
    s = _student(conn, "2")
    with pytest.raises(errors.CheckViolation):
        conn.execute("insert into tf_student_sub_roles (student_id, role) values (%s, '디자이너')", (s,))


def test_vote_cannot_change(conn):
    t = _team(conn, 1)
    voter, applicant = _student(conn, "1"), _student(conn, "2", "테스터")
    app = _application(conn, t, applicant)
    conn.execute("insert into tf_votes (application_id, voter_id, vote) values (%s, %s, '찬성')", (app, voter))
    with pytest.raises(errors.UniqueViolation):
        conn.execute("insert into tf_votes (application_id, voter_id, vote) values (%s, %s, '거부')", (app, voter))


def test_one_pending_application_per_student(conn):
    t1, t2 = _team(conn, 1), _team(conn, 2)
    s = _student(conn, "1")
    _application(conn, t1, s, "거절")
    _application(conn, t1, s, "대기")
    with pytest.raises(errors.UniqueViolation):
        _application(conn, t2, s, "대기")


def test_status_and_vote_values(conn):
    t = _team(conn, 1)
    voter, applicant = _student(conn, "1"), _student(conn, "2", "테스터")
    with pytest.raises(errors.CheckViolation):
        _application(conn, t, applicant, "보류")
    app = _application(conn, t, applicant)
    with pytest.raises(errors.CheckViolation):
        conn.execute("insert into tf_votes (application_id, voter_id, vote) values (%s, %s, '기권')", (app, voter))


def test_rls_enabled_on_all_tables(conn, schema_name):
    rows = conn.execute(
        "select c.relname, c.relrowsecurity from pg_class c join pg_namespace n on n.oid = c.relnamespace"
        " where n.nspname = %s and c.relkind = 'r'",
        (schema_name,),
    ).fetchall()
    assert len(rows) == 8
    assert all(on for _, on in rows), [name for name, on in rows if not on]
