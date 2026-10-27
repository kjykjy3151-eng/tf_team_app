# 2026-10-27 16:12 KST
"""DB를 모르는 규칙 판단. 3단계, 4단계에서 함수를 더한다."""
from dataclasses import dataclass


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
