# 2026-10-27 16:14 KST
"""여러 화면이 같이 쓰는 것: 결과 안내(result)와 동작 실행."""
from collections.abc import Callable

import psycopg
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from tf.config import TEAM_MAX
from tf.db import get_pool
from tf.roster import RosterError
from tf.rules import Student

RESULT_WORDS = ("승인", "대기", "거절", "막힘")


def set_result(msg: str) -> None:
    """result 안내는 승인, 대기, 거절, 막힘 가운데 하나로 시작해야 한다."""
    assert msg.startswith(RESULT_WORDS), msg
    st.session_state["result"] = msg


def result_box() -> DeltaGenerator:
    """화면 위쪽에 result 자리를 만들고 지금 안내를 바로 넣는다.

    실행이 중간에 st.rerun으로 멈춰도 안내가 비지 않게 한다. 단추를 처리한 뒤에는
    fill_result로 다시 채운다.
    """
    with st.container(key="result"):
        slot = st.empty()
    fill_result(slot)
    return slot


def fill_result(slot: DeltaGenerator) -> None:
    msg = st.session_state.get("result")
    if msg:
        slot.info(msg)
    else:
        # 빈 컨테이너는 화면에 그려지지 않으므로 빈칸 하나를 넣어 result 자리를 늘 둔다.
        slot.markdown("&nbsp;")


def run_action(action: Callable[[psycopg.Connection], str]) -> None:
    """DB 연결을 빌려 동작을 실행하고 결과를 result에 넣는다. 오류는 종류만 보여 준다."""
    try:
        with get_pool().connection() as conn:
            msg = action(conn)
    except PermissionError as e:
        msg = str(e)
    except RosterError as e:
        msg = f"막힘: {e}"
    except LookupError:
        msg = "막힘: 명단에 없는 학번임(명단이 바뀌었으면 다시 로그인)"
    except psycopg.Error as e:
        msg = f"막힘: DB 오류({type(e).__name__})"
    set_result(msg)


def student_line(s: Student) -> str:
    subs = ", ".join(s.sub_roles) or "없음"
    return f"{s.name} · 주 역할 {s.main_role} · 보조 역할 {subs}"


def render_teams(teams, my_team_no: int | None, apply_button: Callable[[int], None] | None) -> None:
    """팀마다 key가 team_{번호}인 컨테이너에 팀원의 이름과 역할을 보여 준다."""
    for team in teams:
        with st.container(key=f"team_{team.no}", border=True):
            mine = " `내 팀`" if team.no == my_team_no else ""
            st.markdown(f"**팀{team.no}**{mine} ({len(team.members)}/{TEAM_MAX}명)")
            if team.members:
                for m in team.members:
                    st.markdown(f"- {student_line(m)}")
            else:
                st.write("빈 팀")
            if apply_button:
                apply_button(team.no)
