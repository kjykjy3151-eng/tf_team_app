# 2026-10-27 16:14 KST
"""관리자 화면. 2단계: 명단 올리기."""
import streamlit as st

from tf.auth import User
from tf.roster import parse_roster, reset_with_roster
from tf.ui_common import run_action, set_result


def render(user: User) -> None:
    st.header("명단 올리기")
    st.caption(
        "명단 CSV(UTF-8, 머리글 `student_no,name,main_role,sub_roles`)와 팀 수를 넣고 단추를 누르면 "
        "지원, 투표, 팀원, 마감 표시를 모두 지우고 처음 상태를 만듭니다."
    )
    file =st.file_uploader("명단 CSV", type="csv", key="admin_roster_file")
    team_count = st.number_input("팀 수", min_value=1, step=1, value=3, key="admin_team_count")
    if st.button("명단으로 처음 상태 만들기", key="admin_start"):
        if file is None:
            set_result("막힘: 명단 CSV를 올려야 함")
        else:
            def start(conn):
                students = parse_roster(file.getvalue())
                reset_with_roster(conn, user, students, int(team_count))
                return f"승인: 학생 {len(students)}명, 팀 {int(team_count)}개로 처음 상태를 만듦"

            run_action(start)
