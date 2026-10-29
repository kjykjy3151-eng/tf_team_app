# 2026-10-29 23:32 KST
"""한 번에 읽은 상태(Snapshot)로 만든 화면 값이, 하나씩 읽던 함수의 값과 같은지 본다."""
from pathlib import Path

from tf.auth import User
from tf.roster import parse_roster, reset_with_roster
from tf.service import (
    all_applications,
    apply,
    close_recruitment,
    load_snapshot,
    load_state,
    my_applications,
    my_pending_team_no,
    my_team_no,
    pending_for_team,
    vote,
)

ADMIN = User("admin", "관리자", True)
REF = Path(__file__).resolve().parent.parent / "참고자료"


def s(k: int) -> str:
    return f"2026{k}"


def assert_same(conn) -> None:
    snap = load_snapshot(conn)
    assert snap.state == load_state(conn)
    assert snap.all_applications() == all_applications(conn)
    for team in snap.state.teams:
        for m in team.members:
            assert snap.pending_for_team(team.no, m.student_no) == pending_for_team(conn, team.no, m.student_no)
    for no in [st.student_no for st in snap.state.unassigned] + [m.student_no for t in snap.state.teams for m in t.members]:
        assert snap.my_team_no(no) == my_team_no(conn, no)
        assert snap.my_pending_team_no(no) == my_pending_team_no(conn, no)
        assert snap.my_applications(no) == my_applications(conn, no)


def test_snapshot_matches_queries_through_hard_scenario(conn):
    reset_with_roster(conn, ADMIN, parse_roster((REF / "어려움.csv").read_bytes()), 4)
    assert_same(conn)  # 처음 상태
    apply(conn, s(301), 1)
    apply(conn, s(304), 1); vote(conn, s(301), s(304), True)
    apply(conn, s(302), 2)
    apply(conn, s(308), 2); vote(conn, s(302), s(308), True)
    apply(conn, s(305), 2); apply(conn, s(306), 2)  # 둘 다 대기
    vote(conn, s(302), s(305), True)  # 305는 한 표만 받아 대기, 302의 투표가 보여야 함
    assert_same(conn)
    vote(conn, s(308), s(305), True)  # 305 승인
    vote(conn, s(302), s(306), True); vote(conn, s(308), s(306), True); vote(conn, s(305), s(306), True)  # 승인 직전 검사로 거절
    apply(conn, s(310), 4)
    apply(conn, s(313), 1); vote(conn, s(301), s(313), True)  # 대기
    assert_same(conn)
    close_recruitment(conn, ADMIN)  # 313 거절, 310 빠짐
    assert_same(conn)
