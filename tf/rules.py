# 2026-10-27 16:12 KST
"""DB를 모르는 규칙 판단."""
from dataclasses import dataclass

from tf.config import REQUIRED_ROLES, TEAM_MAX, TEAM_MIN


@dataclass(frozen=True)
class Student:
    student_no: str
    name: str
    main_role: str | None  # 관리자는 None
    sub_roles: tuple[str, ...] = ()


@dataclass
class Team:
    no: int  # 팀1의 1. tf_teams.id와 같다.
    members: list[Student]


def can_play(s: Student, role: str) -> bool:
    """주 역할이나 보조 역할로 그 역할을 맡을 수 있는지."""
    return s.main_role == role or role in s.sub_roles


def unfilled_required(members: list[Student]) -> int:
    """기획자와 웹 프로그래머 가운데 아직 채우지 못한 수(0~2).

    두 역할은 서로 다른 학생이 맡아야 하므로, 한 학생이 둘 다 할 수 있어도 하나로만 센다.
    """
    pl = [i for i, m in enumerate(members) if can_play(m, REQUIRED_ROLES[0])]
    wp = [i for i, m in enumerate(members) if can_play(m, REQUIRED_ROLES[1])]
    if any(i != j for i in pl for j in wp):
        return 0
    return 1 if pl or wp else 2


def join_block_reason(team: Team, applicant: Student) -> str | None:
    """applicant가 team에 들어가면 안 되는 첫 이유. 들어가도 되면 None.

    지원할 때와 승인 직전 재검사에 같은 함수를 쓴다(공고 2.4절, 3장).
    """
    members = team.members
    if len(members) >= TEAM_MAX:
        return "팀이 꽉 참"
    if any(m.main_role == applicant.main_role for m in members):
        return "같은 주 역할의 팀원이 있음"
    seats_left = TEAM_MAX - (len(members) + 1)
    if seats_left < unfilled_required(members + [applicant]):
        return "필수 포함 역할을 맡을 학생의 자리가 모자람"
    return None


def _role_errors(team_no: int, members: list[Student]) -> list[str]:
    pl = any(can_play(m, REQUIRED_ROLES[0]) for m in members)
    wp = any(can_play(m, REQUIRED_ROLES[1]) for m in members)
    errors = []
    if not pl:
        errors.append(f"팀{team_no}에 {REQUIRED_ROLES[0]}를 맡을 학생이 없음")
    if not wp:
        errors.append(f"팀{team_no}에 {REQUIRED_ROLES[1]}를 맡을 학생이 없음")
    if pl and wp and unfilled_required(members) > 0:
        errors.append(f"팀{team_no}에 {REQUIRED_ROLES[0]}와 {REQUIRED_ROLES[1]}를 따로 맡을 학생이 없음")
    return errors


def validate_assignment(teams: list[Team], unassigned: list[Student], assignment: dict[str, int]) -> list[str]:
    """배정안 검사 다섯 가지(공고 2.5절 4항). 어긴 것마다 한 줄, 다 지키면 빈 목록."""
    errors = []
    by_no = {s.student_no: s for s in unassigned}
    after = {t.no: list(t.members) for t in teams}
    # 1. 팀이 없는 학생이 빠짐없이 배정됨
    errors += [f"{s.name}이(가) 배정되지 않음" for s in unassigned if s.student_no not in assignment]
    # 2. 한 학생은 한 팀에만(학번당 팀 하나인 dict), 이미 팀이 있는 학생은 옮기지 않음
    for no, team_no in assignment.items():
        if no not in by_no:
            errors.append(f"{no}은(는) 팀이 없는 학생이 아님")
        elif team_no not in after:
            errors.append(f"팀{team_no}은 없는 팀임")
        else:
            after[team_no].append(by_no[no])
    for team_no, members in after.items():
        # 3. 모든 팀이 2~4명
        if not TEAM_MIN <= len(members) <= TEAM_MAX:
            errors.append(f"팀{team_no}이 {len(members)}명임({TEAM_MIN}~{TEAM_MAX}명이어야 함)")
        # 4. 팀 안에서 주 역할 중복 없음
        mains = [m.main_role for m in members]
        errors += [f"팀{team_no}에 주 역할 {r}이(가) 겹침" for r in sorted({r for r in mains if mains.count(r) > 1})]
        # 5. 필수 포함 역할 충족
        errors += _role_errors(team_no, members)
    return errors


def solve_assignment(teams: list[Team], unassigned: list[Student]) -> dict[str, int] | None:
    """검사 다섯 가지를 모두 통과하는 배정을 모든 경우를 따져 찾는다. 없으면 None.

    맡을 수 있는 역할이 적은 학생부터 넣어 보고, 규칙을 어길 수밖에 없는 가지는 일찍 버린다.
    """
    order = sorted(unassigned, key=lambda s: 1 + len(s.sub_roles))
    after = {t.no: list(t.members) for t in teams}
    plan: dict[str, int] = {}

    def place(i: int) -> bool:
        left = len(order) - i
        if sum(max(0, TEAM_MIN - len(m)) for m in after.values()) > left:
            return False
        if i == len(order):
            return validate_assignment(teams, unassigned, plan) == []
        s = order[i]
        for team_no, members in after.items():
            if len(members) >= TEAM_MAX or any(m.main_role == s.main_role for m in members):
                continue
            members.append(s)
            if TEAM_MAX - len(members) >= unfilled_required(members):
                plan[s.student_no] = team_no
                if place(i + 1):
                    return True
                del plan[s.student_no]
            members.pop()
        return False

    return dict(plan) if place(0) else None


def no_solution_reason(teams: list[Team], unassigned: list[Student]) -> str:
    """규칙을 지키는 배정이 없을 때 관리자에게 보여 줄 이유(공고 2.5절 8항)."""
    for t in teams:
        if len(t.members) >= TEAM_MAX and unfilled_required(t.members) > 0:
            return _role_errors(t.no, t.members)[0]
    seats = sum(TEAM_MAX - len(t.members) for t in teams)
    if seats < len(unassigned):
        return "남은 자리가 팀이 없는 학생보다 적음"
    if sum(len(t.members) for t in teams) + len(unassigned) < TEAM_MIN * len(teams):
        return "학생이 모자라 모든 팀을 2명 이상으로 만들 수 없음"
    for t in teams:
        candidates = [s for s in unassigned if all(m.main_role != s.main_role for m in t.members)]
        errors = _role_errors(t.no, t.members + candidates)
        if errors:
            return errors[0]
    return "모든 경우를 따져도 규칙을 지키는 배정이 없음"
