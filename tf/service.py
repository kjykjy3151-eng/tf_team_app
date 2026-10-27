# 2026-10-27 16:32 KST
"""DB를 읽고 쓰는 동작: 상태 읽기, 지원, 투표(공고 2.4절).

한 팀을 바꾸는 동작은 트랜잭션 안에서 tf_teams 행을 FOR UPDATE로 잠가 하나씩 처리한다.
잠그는 차례는 늘 팀 → 지원이다(교착을 막기 위해).
"""
from dataclasses import dataclass

import psycopg
from psycopg import errors

from tf.auth import User, require_admin
from tf.config import TEAM_MAX
from tf.rules import Student, Team, join_block_reason, validate_assignment

STUDENT_SQL = """
    select s.id, s.student_no, s.name, s.main_role,
           coalesce(array_agg(r.role order by r.role) filter (where r.role is not null), '{}')
    from tf_students s left join tf_student_sub_roles r on r.student_id = s.id
"""


@dataclass
class State:
    teams: list[Team]  # no 오름차순
    unassigned: list[Student]  # 관리자 빼고 팀이 없는 학생, 학번 오름차순
    closed: bool


@dataclass
class PendingApp:
    applicant: Student
    my_vote: str | None


def _to_student(row) -> tuple[int, Student]:
    return row[0], Student(row[1], row[2], row[3], tuple(row[4]))


def _student(conn: psycopg.Connection, student_no: str) -> tuple[int, Student]:
    row = conn.execute(STUDENT_SQL + " where s.student_no = %s group by s.id", (student_no,)).fetchone()
    if row is None:
        raise LookupError(f"없는 학번: {student_no}")
    return _to_student(row)


def _members(conn: psycopg.Connection, team_no: int) -> list[tuple[int, Student]]:
    rows = conn.execute(
        STUDENT_SQL + " join tf_members m on m.student_id = s.id where m.team_id = %s"
        " group by s.id, m.slot_no order by m.slot_no",
        (team_no,),
    ).fetchall()
    return [_to_student(r) for r in rows]


def _closed(conn: psycopg.Connection) -> bool:
    row = conn.execute("select value from tf_settings where key = 'closed'").fetchone()
    return row is not None and row[0] == "true"


def _lock_team(conn: psycopg.Connection, team_no: int) -> bool:
    return conn.execute("select id from tf_teams where id = %s for update", (team_no,)).fetchone() is not None


def _add_member(conn: psycopg.Connection, team_no: int, student_id: int) -> None:
    used = {r[0] for r in conn.execute("select slot_no from tf_members where team_id = %s", (team_no,))}
    slot = min(n for n in range(1, TEAM_MAX + 1) if n not in used)
    conn.execute(
        "insert into tf_members (team_id, slot_no, student_id) values (%s, %s, %s)", (team_no, slot, student_id)
    )


def _decide(conn: psycopg.Connection, app_id: int, status: str, reason: str | None) -> None:
    conn.execute(
        "update tf_applications set status = %s, reason = %s, decided_at = now() where id = %s",
        (status, reason, app_id),
    )


def load_state(conn: psycopg.Connection) -> State:
    rows = conn.execute(STUDENT_SQL + " where not s.is_admin group by s.id").fetchall()
    students = dict(_to_student(r) for r in rows)
    teams = {r[0]: Team(r[0], []) for r in conn.execute("select id from tf_teams order by id")}
    placed = set()
    for team_id, student_id in conn.execute("select team_id, student_id from tf_members order by team_id, slot_no"):
        teams[team_id].members.append(students[student_id])
        placed.add(student_id)
    unassigned = sorted((s for sid, s in students.items() if sid not in placed), key=lambda s: s.student_no)
    return State(list(teams.values()), unassigned, _closed(conn))


def my_team_no(conn: psycopg.Connection, student_no: str) -> int | None:
    row = conn.execute(
        "select m.team_id from tf_members m join tf_students s on s.id = m.student_id where s.student_no = %s",
        (student_no,),
    ).fetchone()
    return row[0] if row else None


def my_pending_team_no(conn: psycopg.Connection, student_no: str) -> int | None:
    row = conn.execute(
        "select a.team_id from tf_applications a join tf_students s on s.id = a.student_id"
        " where s.student_no = %s and a.status = '대기'",
        (student_no,),
    ).fetchone()
    return row[0] if row else None


def pending_for_team(conn: psycopg.Connection, team_no: int, voter_no: str) -> list[PendingApp]:
    """그 팀에 들어온 대기 지원(지원 시각 순)과 voter의 투표."""
    rows = conn.execute(
        "select s.student_no, v.vote from tf_applications a"
        " join tf_students s on s.id = a.student_id"
        " left join tf_votes v on v.application_id = a.id"
        "   and v.voter_id = (select id from tf_students where student_no = %s)"
        " where a.team_id = %s and a.status = '대기' order by a.created_at, a.id",
        (voter_no, team_no),
    ).fetchall()
    return [PendingApp(_student(conn, no)[1], my_vote) for no, my_vote in rows]


def apply(conn: psycopg.Connection, student_no: str, team_no: int) -> str:
    """지원 단추. 막히면 기록하지 않고 '막힘: 이유'를 돌려준다."""
    try:
        with conn.transaction():
            if _closed(conn):
                return "막힘: 모집이 마감됨"
            sid, me = _student(conn, student_no)
            if not _lock_team(conn, team_no):
                return f"막힘: 팀{team_no}은 없는 팀임"
            if my_team_no(conn, student_no) is not None:
                return "막힘: 이미 팀이 있음"
            if my_pending_team_no(conn, student_no) is not None:
                return "막힘: 결과를 기다리는 지원이 있음"
            members = [s for _, s in _members(conn, team_no)]
            reason = join_block_reason(Team(team_no, members), me)
            if reason:
                return f"막힘: {reason}"
            if not members:
                conn.execute(
                    "insert into tf_applications (team_id, student_id, status, decided_at)"
                    " values (%s, %s, '승인', now())",
                    (team_no, sid),
                )
                _add_member(conn, team_no, sid)
                return f"승인: 팀{team_no}에 들어감"
            conn.execute(
                "insert into tf_applications (team_id, student_id, status) values (%s, %s, '대기')", (team_no, sid)
            )
            return "대기: 팀원의 투표를 기다림"
    except errors.UniqueViolation as e:
        # 동시에 눌렀을 때 DB 유일성 제약이 먼저 도착한 쪽만 남긴다(공고 3장).
        if e.diag.constraint_name == "tf_applications_one_pending":
            return "막힘: 결과를 기다리는 지원이 있음"
        return "거절: 다른 학생이 먼저 자리에 들어감"


def _latest_status(conn: psycopg.Connection, student_id: int) -> str:
    row = conn.execute(
        "select status, reason, team_id from tf_applications where student_id = %s order by id desc limit 1",
        (student_id,),
    ).fetchone()
    if row is None:
        return "막힘: 대기 중인 지원이 없음"
    status, reason, team_no = row
    if status == "승인":
        return f"승인: 팀{team_no}에 들어감"
    return f"거절: {reason}"


def vote(conn: psycopg.Connection, voter_no: str, applicant_no: str, yes: bool) -> str:
    """찬성이나 거부. 그 지원의 지금 상태(승인, 대기, 거절)를 돌려준다."""
    with conn.transaction():
        if _closed(conn):
            return "막힘: 모집이 마감됨"
        voter_id, _ = _student(conn, voter_no)
        applicant_id, applicant = _student(conn, applicant_no)
        row = conn.execute(
            "select id, team_id from tf_applications where student_id = %s and status = '대기'", (applicant_id,)
        ).fetchone()
        if row is None:
            return _latest_status(conn, applicant_id)
        app_id, team_no = row
        _lock_team(conn, team_no)
        # 잠근 뒤 다시 읽는다. 그 사이에 결과가 났을 수 있다.
        status = conn.execute("select status from tf_applications where id = %s for update", (app_id,)).fetchone()[0]
        if status != "대기":
            return _latest_status(conn, applicant_id)
        members = _members(conn, team_no)
        if voter_id not in [mid for mid, _ in members]:
            return "막힘: 이 팀의 팀원만 투표할 수 있음"
        inserted = conn.execute(
            "insert into tf_votes (application_id, voter_id, vote) values (%s, %s, %s)"
            " on conflict do nothing returning 1",
            (app_id, voter_id, "찬성" if yes else "거부"),
        ).fetchone()
        if inserted is None:
            return "막힘: 이미 투표함"
        if not yes:
            _decide(conn, app_id, "거절", "팀원이 거부함")
            return "거절: 팀원이 거부함"
        agreed = {
            r[0]
            for r in conn.execute("select voter_id from tf_votes where application_id = %s and vote = '찬성'", (app_id,))
        }
        # 투표할 사람은 투표하는 때의 팀원이다(공고 2.4절).
        if any(mid not in agreed for mid, _ in members):
            return "대기: 아직 투표하지 않은 팀원이 있음"
        # 승인 직전 재검사(공고 3장 어려운 해결). 처리 순서는 투표가 끝난 순서다.
        reason = join_block_reason(Team(team_no, [s for _, s in members]), applicant)
        if reason:
            _decide(conn, app_id, "거절", f"승인 직전 검사: {reason}")
            return f"거절: 승인 직전 검사: {reason}"
        _add_member(conn, team_no, applicant_id)
        _decide(conn, app_id, "승인", None)
        return f"승인: 팀{team_no}에 들어감"


def close_recruitment(conn: psycopg.Connection, user: User) -> str:
    """모집 마감(공고 2.5절 1~2항): 마감 표시, 대기 지원 거절, 1명뿐인 팀의 학생을 팀에서 뺌."""
    require_admin(user)
    with conn.transaction():
        conn.execute("select id from tf_teams order by id for update")
        if _closed(conn):
            return "막힘: 이미 마감됨"
        conn.execute(
            "insert into tf_settings (key, value) values ('closed', 'true')"
            " on conflict (key) do update set value = 'true'"
        )
        rejected = conn.execute(
            "update tf_applications set status = '거절', reason = '모집 마감', decided_at = now()"
            " where status = '대기' returning id"
        ).fetchall()
        removed = conn.execute(
            "delete from tf_members where team_id in"
            " (select team_id from tf_members group by team_id having count(*) = 1) returning student_id"
        ).fetchall()
    return f"승인: 모집을 마감함(대기 지원 {len(rejected)}건 거절, {len(removed)}명이 팀에서 빠짐)"


def confirm_assignment(conn: psycopg.Connection, user: User, assignment: dict[str, int]) -> str:
    """배정안 확정(공고 2.5절 7항). 저장 직전에 지금 상태로 다시 검사한다."""
    require_admin(user)
    with conn.transaction():
        conn.execute("select id from tf_teams order by id for update")
        state = load_state(conn)
        if not state.closed:
            return "막힘: 먼저 모집을 마감해야 함"
        errors = validate_assignment(state.teams, state.unassigned, assignment)
        if errors:
            return f"막힘: 배정안이 지금 상태와 맞지 않음({errors[0]})"
        for no, team_no in assignment.items():
            _add_member(conn, team_no, _student(conn, no)[0])
    return f"승인: 배정을 확정함({len(assignment)}명)"
