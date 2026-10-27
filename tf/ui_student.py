# 2026-10-27 16:12 KST
"""학생 화면: 팀 목록, 지원, 내 팀에 들어온 지원에 투표(공고 2.4절, 2.8절)."""
import streamlit as st

from tf.auth import User
from tf.config import REFRESH_SEC
from tf.db import get_pool
from tf.service import apply, load_state, my_pending_team_no, my_team_no, pending_for_team, vote
from tf.ui_common import render_teams, run_action, student_line


def _act(action) -> None:
    """단추를 처리한 뒤 다시 그려서 바뀐 팀 목록과 result를 함께 보여 준다."""
    run_action(action)
    st.rerun()


def render(user: User) -> None:
    st.caption(f"화면은 {REFRESH_SEC}초마다 저절로 바뀜")
    _live(user)


@st.fragment(run_every=REFRESH_SEC)
def _live(user: User) -> None:
    """다른 사람의 변경 보기(공고 3장 어려운 해결): 이 부분만 몇 초마다 다시 그린다.

    result는 이 조각 밖(화면 위쪽)에 있고 세션에 저장되어 있어서 다시 그려도 사라지지 않는다.
    단추를 누르면 _act가 앱 전체를 다시 그려 result와 팀 목록을 함께 바꾼다.
    """
    me = user.student_no
    with get_pool().connection() as conn:
        state = load_state(conn)
        my_team = my_team_no(conn, me)
        pending_team = my_pending_team_no(conn, me)
        incoming = pending_for_team(conn, my_team, me) if my_team else []

    status = "마감" if state.closed else "모집 중"
    st.write(f"모집 상태: **{status}**, 내 팀: **{f'팀{my_team}' if my_team else '아직 팀이 없음'}**")

    if my_team:
        st.subheader("내 팀에 들어온 지원")
        if not incoming:
            st.write("대기 중인 지원 없음")
        for app in incoming:
            s = app.applicant
            cols = st.columns([6, 1, 1])
            cols[0].write(f"{student_line(s)} (학번 {s.student_no})")
            if app.my_vote:
                cols[1].write(f"내 투표: {app.my_vote}")
            else:
                if cols[1].button("찬성", key=f"vote_yes_{s.student_no}"):
                    _act(lambda conn, no=s.student_no: vote(conn, me, no, True))
                if cols[2].button("거부", key=f"vote_no_{s.student_no}"):
                    _act(lambda conn, no=s.student_no: vote(conn, me, no, False))

    # 이미 팀이 있음, 결과를 기다리는 지원이 있음, 모집 마감이면 지원 단추를 비활성화한다(공고 2.8절).
    if my_team:
        why = f"이미 팀{my_team}에 속해 있음"
    elif pending_team:
        why = f"팀{pending_team}에 낸 지원이 대기 중임. 결과가 나온 뒤 다시 지원할 수 있음"
    elif state.closed:
        why = "모집이 마감됨"
    else:
        why = None

    st.subheader("팀 목록")
    if why:
        st.caption(f"지원 단추를 쓸 수 없음: {why}")

    def apply_button(team_no: int) -> None:
        if st.button(f"팀{team_no}에 지원", key=f"apply_{team_no}", disabled=why is not None):
            _act(lambda conn: apply(conn, me, team_no))

    render_teams(state.teams, my_team, apply_button)
