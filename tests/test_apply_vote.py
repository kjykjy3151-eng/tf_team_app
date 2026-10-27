# 2026-10-27 16:31 KST
import threading

import pytest

from tf.auth import User
from tf.roster import reset_with_roster
from tf.rules import Student
from tf.service import apply, load_state, my_pending_team_no, my_team_no, pending_for_team, vote

ADMIN = User("admin", "관리자", True)
PL, WP, FD, TT, RW, PT = "기획자", "웹 프로그래머", "프론트엔드 디자이너", "테스터", "보고서 작성자", "발표자"


def setup(conn, roles: dict[str, tuple[str, ...]], teams: int = 3) -> None:
    """roles: {학번: (주 역할, 보조 역할...)}. 이름은 '이름'+학번."""
    students = [Student(no, f"이름{no}", r[0], tuple(r[1:])) for no, r in roles.items()]
    reset_with_roster(conn, ADMIN, students, teams)


def word(msg: str) -> str:
    return msg.split(":")[0]


def status_of(conn, no: str) -> str:
    return conn.execute(
        "select a.status from tf_applications a join tf_students s on s.id = a.student_id"
        " where s.student_no = %s order by a.id desc limit 1",
        (no,),
    ).fetchone()[0]


def test_apply_empty_team_approved(conn):
    setup(conn, {"A": (PL,)})
    assert apply(conn, "A", 1) == "승인: 팀1에 들어감"
    assert my_team_no(conn, "A") == 1


def test_apply_team_with_members_waits(conn):
    setup(conn, {"A": (PL,), "B": (WP,)})
    apply(conn, "A", 1)
    assert apply(conn, "B", 1) == "대기: 팀원의 투표를 기다림"
    assert my_pending_team_no(conn, "B") == 1


def test_all_yes_approves(conn):
    setup(conn, {"A": (PL,), "B": (WP,), "C": (FD,)})
    apply(conn, "A", 1); apply(conn, "B", 1); vote(conn, "A", "B", True)
    apply(conn, "C", 1)
    assert word(vote(conn, "A", "C", True)) == "대기"
    assert vote(conn, "B", "C", True) == "승인: 팀1에 들어감"
    assert [m.student_no for m in load_state(conn).teams[0].members] == ["A", "B", "C"]


def test_one_no_rejects_immediately(conn):
    setup(conn, {"A": (PL,), "B": (WP,), "C": (FD,)})
    apply(conn, "A", 1); apply(conn, "B", 1); vote(conn, "A", "B", True)
    apply(conn, "C", 1)
    assert vote(conn, "A", "C", False) == "거절: 팀원이 거부함"
    # 다른 팀원을 기다리지 않고 이미 거절됨. 그 팀원이 눌러도 지금 상태를 알려 준다.
    assert vote(conn, "B", "C", True) == "거절: 팀원이 거부함"


def test_waiting_until_everyone_votes(conn):
    setup(conn, {"A": (PL,), "B": (WP,), "C": (FD,)})
    apply(conn, "A", 1); apply(conn, "B", 1); vote(conn, "A", "B", True)
    apply(conn, "C", 1)
    assert vote(conn, "B", "C", True) == "대기: 아직 투표하지 않은 팀원이 있음"


def test_new_member_must_also_vote(conn):
    setup(conn, {"A": (PL,), "X": (WP,), "Y": (FD,)})
    apply(conn, "A", 1)
    apply(conn, "X", 1); apply(conn, "Y", 1)
    assert vote(conn, "A", "X", True) == "승인: 팀1에 들어감"
    # Y가 지원한 뒤 X가 팀원이 되었으므로 X의 찬성도 있어야 한다.
    assert word(vote(conn, "A", "Y", True)) == "대기"
    assert vote(conn, "X", "Y", True) == "승인: 팀1에 들어감"


def test_recheck_before_approval_rejects(conn):
    setup(conn, {"A": (PL,), "X": (WP,), "Y": (WP, RW)})
    apply(conn, "A", 1); apply(conn, "X", 1); apply(conn, "Y", 1)
    vote(conn, "A", "X", True)
    vote(conn, "A", "Y", True)
    assert vote(conn, "X", "Y", True) == "거절: 승인 직전 검사: 같은 주 역할의 팀원이 있음"


def test_recheck_order_is_vote_end_order(conn):
    setup(conn, {"A": (PL,), "X": (WP,), "Y": (WP, TT)})
    apply(conn, "A", 1); apply(conn, "X", 1); apply(conn, "Y", 1)
    # 먼저 지원한 X보다 Y의 투표가 먼저 끝나면 Y가 승인된다.
    assert word(vote(conn, "A", "Y", True)) == "승인"
    assert word(vote(conn, "Y", "X", True)) == "대기"
    assert vote(conn, "A", "X", True) == "거절: 승인 직전 검사: 같은 주 역할의 팀원이 있음"


def test_pending_not_rejected_early(conn):
    setup(conn, {"A": (PL,), "X": (WP,), "Y": (WP, TT)})
    apply(conn, "A", 1); apply(conn, "X", 1); apply(conn, "Y", 1)
    vote(conn, "A", "X", True)
    assert status_of(conn, "Y") == "대기"


def test_block_when_pending_elsewhere(conn):
    setup(conn, {"A": (PL,), "B": (WP,)})
    apply(conn, "A", 1); apply(conn, "B", 1)
    assert apply(conn, "B", 2) == "막힘: 결과를 기다리는 지원이 있음"


def test_can_apply_again_after_rejection(conn):
    setup(conn, {"A": (PL,), "B": (WP,)})
    apply(conn, "A", 1); apply(conn, "B", 1); vote(conn, "A", "B", False)
    assert apply(conn, "B", 2) == "승인: 팀2에 들어감"


def test_block_when_already_in_team(conn):
    setup(conn, {"A": (PL,)})
    apply(conn, "A", 1)
    assert apply(conn, "A", 2) == "막힘: 이미 팀이 있음"


def join(conn, no: str, team: int) -> str:
    """no가 team에 지원하고 지금 팀원 모두가 찬성한다. 마지막 결과를 돌려준다."""
    msg = apply(conn, no, team)
    for voter in [m.student_no for m in load_state(conn).teams[team - 1].members]:
        msg = vote(conn, voter, no, True)
    return msg


def test_block_full_and_same_role(conn):
    setup(conn, {"A": (PL,), "B": (WP,), "C": (FD,), "D": (TT,), "E": (RW,), "G": (PT,), "H": (RW, FD)})
    for no in ["A", "B", "C", "D"]:
        assert word(join(conn, no, 1)) == "승인"
    assert apply(conn, "E", 1) == "막힘: 팀이 꽉 참"
    assert word(join(conn, "G", 3)) == "승인"
    assert word(join(conn, "H", 3)) == "승인"
    assert apply(conn, "E", 3) == "막힘: 같은 주 역할의 팀원이 있음"
    blocked = conn.execute(
        "select count(*) from tf_applications a join tf_students s on s.id = a.student_id where s.student_no = 'E'"
    ).fetchone()[0]
    assert blocked == 0  # 막힌 지원은 기록하지 않는다


def test_block_required_seat_in_db(conn):
    setup(conn, {"A": (TT,), "B": (PT,), "C": (RW,)})
    apply(conn, "A", 1); apply(conn, "B", 1); vote(conn, "A", "B", True)
    assert apply(conn, "C", 1) == "막힘: 필수 포함 역할을 맡을 학생의 자리가 모자람"


def test_vote_cannot_change(conn):
    setup(conn, {"A": (PL,), "B": (WP,), "C": (FD,)})
    apply(conn, "A", 1); apply(conn, "B", 1); vote(conn, "A", "B", True)
    apply(conn, "C", 1)
    vote(conn, "A", "C", True)
    assert vote(conn, "A", "C", False) == "막힘: 이미 투표함"
    assert pending_for_team(conn, 1, "A")[0].my_vote == "찬성"


def test_non_member_cannot_vote(conn):
    setup(conn, {"A": (PL,), "B": (WP,), "C": (FD,)})
    apply(conn, "A", 1); apply(conn, "C", 2); apply(conn, "B", 1)
    assert vote(conn, "C", "B", True) == "막힘: 이 팀의 팀원만 투표할 수 있음"


def test_pending_for_team_lists_applicants(conn):
    setup(conn, {"A": (PL,), "B": (WP, FD), "C": (FD,)})
    apply(conn, "A", 1); apply(conn, "B", 1); apply(conn, "C", 1)
    apps = pending_for_team(conn, 1, "A")
    assert [(p.applicant.student_no, p.applicant.sub_roles, p.my_vote) for p in apps] == [
        ("B", ("프론트엔드 디자이너",), None),
        ("C", (), None),
    ]


def test_simultaneous_last_seat(conn, connect):
    setup(conn, {"A": (PL,), "B": (WP,)})
    results = []

    def go(no):
        c = connect()
        results.append(apply(c, no, 1))

    threads = [threading.Thread(target=go, args=(no,)) for no in ["A", "B"]]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(load_state(conn).teams[0].members) == 1
    assert sorted(word(r) for r in results) in (["대기", "승인"], ["거절", "승인"])


def test_application_history(conn):
    from tf.service import all_applications, my_applications

    setup(conn, {"A": (PL,), "B": (WP,)})
    apply(conn, "A", 1); apply(conn, "B", 1); vote(conn, "A", "B", False); apply(conn, "B", 2)
    mine = my_applications(conn, "B")
    assert [(r["team_no"], r["status"], r["reason"]) for r in mine] == [(2, "승인", None), (1, "거절", "팀원이 거부함")]
    assert mine[0]["created_at"] is not None
    everyone = all_applications(conn)
    assert [(r["name"], r["team_no"], r["status"]) for r in everyone] == [
        ("이름B", 2, "승인"), ("이름B", 1, "거절"), ("이름A", 1, "승인"),
    ]


def test_pending_has_applied_time(conn):
    setup(conn, {"A": (PL,), "B": (WP,)})
    apply(conn, "A", 1); apply(conn, "B", 1)
    assert pending_for_team(conn, 1, "A")[0].applied_at is not None
