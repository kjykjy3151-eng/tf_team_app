# 2026-10-27 16:47 KST
import pytest

from tf.auth import User
from tf.roster import reset_with_roster
from tf.rules import Student
from tf.service import apply, close_recruitment, confirm_assignment, load_state, vote

ADMIN = User("admin", "관리자", True)
STUDENT = User("A", "이름A", False)
PL, WP, FD, TT, RW, PT = "기획자", "웹 프로그래머", "프론트엔드 디자이너", "테스터", "보고서 작성자", "발표자"


def setup(conn, roles: dict[str, tuple[str, ...]], teams: int) -> None:
    students = [Student(no, f"이름{no}", r[0], tuple(r[1:])) for no, r in roles.items()]
    reset_with_roster(conn, ADMIN, students, teams)


def status_of(conn, no: str) -> tuple[str, str]:
    return conn.execute(
        "select a.status, a.reason from tf_applications a join tf_students s on s.id = a.student_id"
        " where s.student_no = %s order by a.id desc limit 1",
        (no,),
    ).fetchone()


def test_close_rejects_pending_and_removes_singletons(conn):
    setup(conn, {"A": (PL,), "B": (WP,), "C": (PL,), "D": (FD,), "E": (TT,)}, 3)
    apply(conn, "A", 1); apply(conn, "B", 1)  # B 대기
    apply(conn, "C", 2); apply(conn, "D", 2)  # D 대기
    apply(conn, "E", 3)
    msg = close_recruitment(conn, ADMIN)
    assert msg == "승인: 모집을 마감함(거절한 지원: 이름B, 이름D / 팀에서 뺀 학생: 이름A, 이름C, 이름E)"
    assert status_of(conn, "B") == ("거절", "모집 마감")
    assert status_of(conn, "D") == ("거절", "모집 마감")
    state = load_state(conn)
    assert state.closed
    assert [s.student_no for s in state.unassigned] == ["A", "B", "C", "D", "E"]


def test_close_keeps_teams_with_two_or_more(conn):
    setup(conn, {"A": (PL,), "B": (WP,)}, 2)
    apply(conn, "A", 1); apply(conn, "B", 1); vote(conn, "A", "B", True)
    assert close_recruitment(conn, ADMIN) == "승인: 모집을 마감함(거절한 지원: 없음 / 팀에서 뺀 학생: 없음)"
    assert [m.student_no for m in load_state(conn).teams[0].members] == ["A", "B"]


def test_after_close_apply_and_vote_blocked(conn):
    setup(conn, {"A": (PL,), "B": (WP,), "C": (FD,)}, 2)
    apply(conn, "A", 1); apply(conn, "B", 1); vote(conn, "A", "B", True)
    close_recruitment(conn, ADMIN)
    assert apply(conn, "C", 1) == "막힘: 모집이 마감됨"
    assert vote(conn, "A", "C", True) == "막힘: 모집이 마감됨"


def test_close_twice_blocked(conn):
    setup(conn, {"A": (PL,)}, 1)
    close_recruitment(conn, ADMIN)
    assert close_recruitment(conn, ADMIN) == "막힘: 이미 마감됨"


def test_student_cannot_close_or_confirm(conn):
    setup(conn, {"A": (PL,)}, 1)
    with pytest.raises(PermissionError):
        close_recruitment(conn, STUDENT)
    with pytest.raises(PermissionError):
        confirm_assignment(conn, STUDENT, {})


def test_confirm_saves_and_rechecks(conn):
    setup(conn, {"A": (PL,), "B": (WP,), "C": (PL,), "D": (WP,)}, 2)
    apply(conn, "A", 1); apply(conn, "B", 1); vote(conn, "A", "B", True)
    assert confirm_assignment(conn, ADMIN, {"C": 2, "D": 2}) == "막힘: 먼저 모집을 마감해야 함"
    close_recruitment(conn, ADMIN)
    assert confirm_assignment(conn, ADMIN, {"C": 2}) == "막힘: 배정안이 지금 상태와 맞지 않음(이름D이(가) 배정되지 않음)"
    assert confirm_assignment(conn, ADMIN, {"C": 2, "D": 2}) == "승인: 배정을 확정함(2명)"
    state = load_state(conn)
    assert [m.student_no for m in state.teams[1].members] == ["C", "D"]
    assert state.unassigned == []
    # 한 번 확정한 뒤 같은 배정안을 또 누르면 지금 상태와 맞지 않는다.
    assert confirm_assignment(conn, ADMIN, {"C": 2, "D": 2}).startswith("막힘: 배정안이 지금 상태와 맞지 않음")
