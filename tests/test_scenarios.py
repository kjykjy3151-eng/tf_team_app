# 2026-10-27 16:47 KST
"""공고 부록의 연습용 시나리오 3개를 단계 순서대로 실행해 result의 첫 단어를 기대 결과와 비교한다.

시나리오의 학번과 순서는 이 테스트에만 있다. 앱 코드에는 넣지 않는다(공고 6.3절 19번).
실제 AI는 부르지 않는다(앱 배정 또는 가짜 응답).
"""
import json
from pathlib import Path

from tf.ai import assign
from tf.auth import User
from tf.roster import parse_roster, reset_with_roster
from tf.rules import validate_assignment
from tf.service import apply, close_recruitment, confirm_assignment, load_state, vote

ADMIN = User("admin", "관리자", True)
REF = Path(__file__).resolve().parent.parent / "참고자료"


def s(k: int) -> str:
    return f"2026{k}"


def start(conn, csv: str, teams: int) -> None:
    reset_with_roster(conn, ADMIN, parse_roster((REF / csv).read_bytes()), teams)


def word(msg: str) -> str:
    return msg.split(":")[0]


def yes(conn, voters: list[int], applicant: int) -> str:
    """적힌 차례대로 찬성하고 마지막 결과를 돌려준다."""
    msg = ""
    for v in voters:
        msg = vote(conn, s(v), s(applicant), True)
    return msg


def names(students) -> set[str]:
    return {x.name for x in students}


def finish_and_check(conn, use_ai=False, **kw) -> str:
    out = assign(conn, ADMIN, use_ai=use_ai, on_status=lambda m: None, **kw)
    assert word(out.message) == "승인"
    assert word(confirm_assignment(conn, ADMIN, out.assignment)) == "승인"
    state = load_state(conn)
    assert state.unassigned == []
    assert validate_assignment(state.teams, [], {}) == []  # 확정한 팀 구성이 규칙을 모두 지킴
    return out.message


def test_easy_scenario(conn):
    start(conn, "쉬움 (1).csv", 3)
    # 1. 3명 모두 바로 승인
    assert [word(apply(conn, s(a), t)) for a, t in [(101, 1), (102, 2), (103, 3)]] == ["승인"] * 3
    # 2. 승인
    assert word(apply(conn, s(104), 1)) == "대기"
    assert word(yes(conn, [101], 104)) == "승인"
    # 3. 승인
    apply(conn, s(105), 2)
    assert word(yes(conn, [102], 105)) == "승인"
    # 4. 거절(학생1 찬성 뒤엔 아직 대기)
    apply(conn, s(107), 1)
    assert word(yes(conn, [101], 107)) == "대기"
    assert word(vote(conn, s(104), s(107), False)) == "거절"
    # 5. 승인
    apply(conn, s(106), 3)
    assert word(yes(conn, [103], 106)) == "승인"
    # 6. 마감, 배정, 확정
    assert word(close_recruitment(conn, ADMIN)) == "승인"
    assert names(load_state(conn).unassigned) == {"학생7(FD;PT)", "학생8(TT;RW;PT)"}
    finish_and_check(conn)


def test_medium_scenario(conn):
    start(conn, "중간.csv", 4)
    assert word(apply(conn, s(201), 1)) == "승인"  # 1
    apply(conn, s(205), 1)
    assert word(yes(conn, [201], 205)) == "승인"  # 2
    msg = apply(conn, s(202), 1)  # 3. 막힘(주 역할 중복)
    assert word(msg) == "막힘" and "같은 주 역할" in msg
    assert word(apply(conn, s(206), 2)) == "승인"  # 4
    apply(conn, s(209), 2)
    assert word(yes(conn, [206], 209)) == "승인"  # 5
    apply(conn, s(210), 2)  # 6. 거절
    yes(conn, [206], 210)
    assert word(vote(conn, s(209), s(210), False)) == "거절"
    assert [word(apply(conn, s(a), t)) for a, t in [(203, 3), (211, 4)]] == ["승인", "승인"]  # 7
    assert word(apply(conn, s(212), 4)) == "대기"  # 8. 팀4 지원은 대기, 팀3 지원은 막힘
    assert word(apply(conn, s(212), 3)) == "막힘"
    assert word(close_recruitment(conn, ADMIN)) == "승인"  # 9
    unassigned = names(load_state(conn).unassigned)
    assert {"학생3(PL;RW)", "학생11(RW)", "학생12(PT;RW;FD)"} <= unassigned
    msg = apply(conn, s(202), 3)  # 10. 막힘(마감)
    assert word(msg) == "막힘" and "마감" in msg
    finish_and_check(conn)  # 11


def test_hard_scenario(conn):
    start(conn, "어려움.csv", 4)
    assert word(apply(conn, s(301), 1)) == "승인"  # 1
    apply(conn, s(304), 1)
    assert word(yes(conn, [301], 304)) == "승인"  # 2
    apply(conn, s(307), 1)
    assert word(yes(conn, [301, 304], 307)) == "승인"  # 3
    assert word(apply(conn, s(302), 2)) == "승인"  # 4
    apply(conn, s(308), 2)
    assert word(yes(conn, [302], 308)) == "승인"  # 5
    assert [word(apply(conn, s(a), 2)) for a in (305, 306)] == ["대기", "대기"]  # 6
    assert word(yes(conn, [302, 308], 305)) == "승인"  # 7
    msg = yes(conn, [302, 308, 305], 306)  # 8. 거절(승인 직전 검사)
    assert word(msg) == "거절" and "승인 직전 검사" in msg
    assert word(apply(conn, s(311), 3)) == "승인"  # 9
    apply(conn, s(315), 3)
    assert word(yes(conn, [311], 315)) == "승인"  # 10
    msg = apply(conn, s(314), 3)  # 11. 막힘(필수 포함 역할 자리)
    assert word(msg) == "막힘" and "필수 포함 역할" in msg
    assert word(apply(conn, s(310), 4)) == "승인"  # 12
    apply(conn, s(313), 1)
    assert word(yes(conn, [301], 313)) == "대기"  # 13
    assert word(close_recruitment(conn, ADMIN)) == "승인"  # 14
    assert {"학생10(TT;RW)", "학생13(RW;PT;FD)"} <= names(load_state(conn).unassigned)
    finish_and_check(conn)  # 15


def test_ai_fake_response_used_in_hard(conn):
    """어려움 14단계 뒤, 1차 모델이 검사를 통과하는 배정안을 낸 경우."""
    start(conn, "어려움.csv", 4)
    for a, t, voters in [(301, 1, []), (304, 1, [301]), (307, 1, [301, 304]), (302, 2, []), (308, 2, [302]),
                         (305, 2, [302, 308]), (311, 3, []), (315, 3, [311]), (310, 4, [])]:
        apply(conn, s(a), t)
        yes(conn, voters, a)
    close_recruitment(conn, ADMIN)

    from tf.rules import solve_assignment

    state = load_state(conn)
    good = solve_assignment(state.teams, state.unassigned)
    reply = json.dumps({"assignments": [{"student_no": no, "team": t} for no, t in good.items()]})
    calls = []

    def caller(model, prompt, *, api_key):
        calls.append(model)
        return f"배정안입니다.\n```json\n{reply}\n```"

    msg = finish_and_check(conn, use_ai=True, caller=caller, models=("m1:free", "m2:free", "m3:free"), api_key="x")
    assert msg == "승인: 1차 모델의 배정안이 검사를 통과함"
    assert calls == ["m1:free"]
