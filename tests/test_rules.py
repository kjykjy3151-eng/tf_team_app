# 2026-10-27 16:30 KST
from tf.rules import Student, Team, join_block_reason, unfilled_required

PL, WP, FD, TT, RW, PT = "기획자", "웹 프로그래머", "프론트엔드 디자이너", "테스터", "보고서 작성자", "발표자"


def s(main: str, *subs: str, no: str = "") -> Student:
    return Student(no or main, f"{main}학생", main, subs)


def test_unfilled_counts_one_student_once():
    # 공고 3장 예: 주 역할 기획자, 보조 역할 웹 프로그래머인 학생 혼자 있는 팀은 2개 가운데 1개만 채운 것
    assert unfilled_required([s(PL, WP)]) == 1


def test_unfilled_uses_sub_roles():
    assert unfilled_required([s(TT, PL), s(WP)]) == 0
    assert unfilled_required([s(FD), s(RW)]) == 2


def test_block_full_team():
    team = Team(1, [s(PL), s(WP), s(FD), s(TT)])
    assert join_block_reason(team, s(RW)) == "팀이 꽉 참"


def test_block_same_main_role():
    assert join_block_reason(Team(1, [s(PL)]), s(PL, WP)) == "같은 주 역할의 팀원이 있음"


def test_block_required_seat():
    # 공고 3장 예: 테스터와 발표자만 있는 팀(2명)에 보고서 작성자가 지원하면 막음
    team = Team(1, [s(TT), s(PT)])
    assert join_block_reason(team, s(RW)) == "필수 포함 역할을 맡을 학생의 자리가 모자람"


def test_allow_when_seat_left():
    assert join_block_reason(Team(1, [s(TT), s(PT)]), s(PL)) is None
    assert join_block_reason(Team(1, [s(PL), s(FD)]), s(TT)) is None


def test_block_order_full_before_role():
    team = Team(1, [s(PL), s(WP), s(FD), s(TT)])
    assert join_block_reason(team, s(PL)) == "팀이 꽉 참"
