# 2026-10-27 16:47 KST
import time

from tf.rules import Student, Team, no_solution_reason, solve_assignment, validate_assignment

PL, WP, FD, TT, RW, PT = "기획자", "웹 프로그래머", "프론트엔드 디자이너", "테스터", "보고서 작성자", "발표자"


def s(no: str, main: str, *subs: str) -> Student:
    return Student(no, f"이름{no}", main, subs)


def teams_and_free():
    # 팀1: 기획자, 웹 프로그래머 / 팀2: 기획자 / 팀3: 빈 팀
    teams = [Team(1, [s("a", PL), s("b", WP)]), Team(2, [s("c", PL)]), Team(3, [])]
    free = [s("d", WP), s("e", PL), s("f", WP, TT), s("g", FD)]
    return teams, free


def test_validate_passes_good_assignment():
    teams, free = teams_and_free()
    assert validate_assignment(teams, free, {"d": 2, "e": 3, "f": 3, "g": 1}) == []


def test_validate_reports_each_of_five_checks():
    teams, free = teams_and_free()
    # 1. 빠진 학생
    assert any("이름g이(가) 배정되지 않음" in e for e in validate_assignment(teams, free, {"d": 2, "e": 3, "f": 3}))
    # 2. 없는 팀
    assert any("팀9은 없는 팀임" in e for e in validate_assignment(teams, free, {"d": 2, "e": 3, "f": 3, "g": 9}))
    # 3. 인원
    errors = validate_assignment(teams, free, {"d": 1, "e": 1, "f": 1, "g": 1})
    assert "팀1이 6명임(2~4명이어야 함)" in errors
    assert "팀3이 0명임(2~4명이어야 함)" in errors
    # 4. 주 역할 중복
    errors = validate_assignment(teams, free, {"d": 2, "e": 2, "f": 3, "g": 3})
    assert "팀2에 주 역할 기획자이(가) 겹침" in errors
    # 5. 필수 포함 역할
    assert "팀3에 기획자를 맡을 학생이 없음" in errors
    errors = validate_assignment(teams, free, {"d": 2, "e": 3, "f": 1, "g": 3})
    assert "팀3에 웹 프로그래머를 맡을 학생이 없음" in errors


def test_validate_one_student_cannot_take_both_roles():
    teams = [Team(1, [s("a", PL, WP)])]
    errors = validate_assignment(teams, [s("b", FD)], {"b": 1})
    assert errors == ["팀1에 기획자와 웹 프로그래머를 따로 맡을 학생이 없음"]


def test_validate_rejects_moving_existing_member():
    teams, free = teams_and_free()
    errors = validate_assignment(teams, free, {"a": 3, "d": 2, "e": 3, "f": 3, "g": 1})
    assert any("a은(는) 팀이 없는 학생이 아님" in e for e in errors)


def test_solver_finds_assignment_using_sub_roles():
    # 웹 프로그래머는 보조 역할로만 채울 수 있다.
    teams = [Team(1, [s("a", PL)]), Team(2, [s("b", PL)])]
    free = [s("c", TT, WP), s("d", FD, WP)]
    plan = solve_assignment(teams, free)
    assert plan is not None
    assert validate_assignment(teams, free, plan) == []


def test_solver_returns_none_when_impossible():
    teams = [Team(1, [s("a", PL), s("b", WP)]), Team(2, [s("c", PL)]), Team(3, [s("d", FD), s("e", TT), s("f", RW), s("g", PT)])]
    assert solve_assignment(teams, [s("h", WP)]) is None


def test_no_solution_reason_names_team_and_role():
    teams = [Team(1, [s("a", PL), s("b", WP)]), Team(2, [s("c", PL)]), Team(3, [s("d", FD), s("e", TT), s("f", RW), s("g", PT)])]
    assert no_solution_reason(teams, [s("h", WP)]) == "팀3에 기획자를 맡을 학생이 없음"


def test_no_solution_reason_other_cases():
    assert no_solution_reason([Team(1, []), Team(2, [])], [s("a", PL), s("b", WP)]) == (
        "학생이 모자라 모든 팀을 2명 이상으로 만들 수 없음"
    )
    assert no_solution_reason([Team(1, [s("a", PL)])], [s("b", WP), s("c", FD), s("d", TT), s("e", RW)]) == (
        "남은 자리가 팀이 없는 학생보다 적음"
    )
    # 팀마다 따로 보면 채울 수 있지만, 웹 프로그래머가 한 명뿐이라 두 팀을 함께 채울 수 없음
    teams = [Team(1, [s("a", PL)]), Team(2, [s("b", PL)])]
    assert no_solution_reason(teams, [s("c", WP), s("d", FD)]) == "모든 경우를 따져도 규칙을 지키는 배정이 없음"


def test_solver_fast_at_max_size():
    # 공고 6.2절: 팀이 없는 학생은 8명을 넘지 않음, 팀은 3~4개
    teams = [Team(1, [s("a", PL), s("b", WP), s("c", FD)]), Team(2, [s("d", PL), s("e", FD), s("f", TT)]), Team(3, []), Team(4, [])]
    free = [s("g", WP), s("h", PL), s("i", TT, WP), s("j", RW, PL), s("k", PT), s("l", FD), s("m", RW), s("n", PT, WP)]
    start = time.monotonic()
    plan = solve_assignment(teams, free)
    assert time.monotonic() - start < 1
    assert plan is not None and validate_assignment(teams, free, plan) == []


def test_solver_exhausts_impossible_case_fast():
    teams = [Team(1, [s("a", PL), s("b", FD), s("c", TT)]), Team(2, []), Team(3, []), Team(4, [])]
    free = [s(f"x{i}", r) for i, r in enumerate([RW, PT, FD, TT, RW, PT, FD, TT])]
    start = time.monotonic()
    assert solve_assignment(teams, free) is None
    assert time.monotonic() - start < 2


def test_solver_does_not_depend_on_names():
    teams, free = teams_and_free()
    renamed = [Student(f"9{i}", f"다른이름{i}", x.main_role, x.sub_roles) for i, x in enumerate(free)]
    plan = solve_assignment(teams, renamed)
    assert plan is not None and validate_assignment(teams, renamed, plan) == []
