# 2026-10-27 16:12 KST
"""DB를 모르는 규칙 판단."""
from dataclasses import dataclass

from tf.config import REQUIRED_ROLES, TEAM_MAX


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
