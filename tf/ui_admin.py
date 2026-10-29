# 2026-10-27 16:14 KST
"""관리자 화면: 명단 올리기, 마감과 배정, 현황(공고 2.5절, 2.6절, 2.7절)."""
import psycopg
import streamlit as st

from tf.ai import AiError, assign, recent_logs
from tf.auth import User
from tf.config import REFRESH_SEC, to_kst
from tf.db import get_pool
from tf.roster import parse_roster, reset_with_roster
from tf.service import assignment_applied, close_recruitment, confirm_assignment
from tf.ui_common import get_snapshot, render_teams, run_action, set_result


def _act(action, clear_draft: bool = False) -> None:
    """단추를 처리한 뒤 다시 그려서 바뀐 현황과 result를 함께 보여 준다."""
    run_action(action)
    if clear_draft:
        st.session_state.pop("draft", None)
        st.session_state.pop("assign_status", None)
    st.rerun()


def _roster_section(user: User) -> None:
    st.header("명단 올리기")
    st.caption(
        "명단 CSV(UTF-8, 머리글 `student_no,name,main_role,sub_roles`)와 팀 수를 넣고 단추를 누르면 "
        "지원, 투표, 팀원, 마감 표시를 모두 지우고 처음 상태를 만듭니다."
    )
    file = st.file_uploader("명단 CSV", type="csv", key="admin_roster_file")
    team_count = st.number_input("팀 수", min_value=1, step=1, value=3, key="admin_team_count")
    if st.button("명단으로 처음 상태 만들기", key="admin_start"):
        if file is None:
            set_result("막힘: 명단 CSV를 올려야 함")
        else:
            def start(conn):
                students = parse_roster(file.getvalue())
                reset_with_roster(conn, user, students, int(team_count))
                return f"승인: 학생 {len(students)}명, 팀 {int(team_count)}개로 처음 상태를 만듦"

            _act(start, clear_draft=True)


def _run_assign(user: User, use_ai: bool, status_slot) -> None:
    """AI 배정을 실행한다. 기다리는 동안 몇 차 모델을 기다리는지 assign_status에 보여 준다."""
    try:
        with get_pool().connection() as conn:
            out = assign(conn, user, use_ai=use_ai, on_status=lambda msg: status_slot.info(msg))
        set_result(out.message)
        st.session_state["draft"] = out.assignment
        st.session_state["assign_status"] = out.status
        st.session_state["draft_source"] = out.source
    except PermissionError as e:
        set_result(str(e))
    except (psycopg.Error, AiError) as e:
        set_result(f"막힘: 배정 중 오류({type(e).__name__})")


def _assign_section(user: User, state) -> None:
    st.header("마감과 배정")
    st.write(f"모집 상태: **{'마감' if state.closed else '모집 중'}**")
    if st.button("모집 마감", key="admin_close", type="primary"):
        _act(lambda conn: close_recruitment(conn, user), clear_draft=True)

    use_ai = st.checkbox("AI를 부름(끄면 앱이 바로 배정함)", value=True, key="admin_use_ai")
    if st.button("AI 배정", key="admin_assign", type="primary"):
        # 다음 실행에서 배정한다. 그 실행은 처음부터 배정만 하므로 다른 다시 그리기와 겹치지 않는다.
        st.session_state["assign_requested"] = True
        st.session_state.pop("draft", None)
        st.session_state.pop("assign_status", None)
        st.rerun()

    with st.container(key="assign_status"):
        slot = st.empty()
        if st.session_state.pop("assign_requested", False):
            _run_assign(user, use_ai, slot)
            st.rerun()
        msg = st.session_state.get("assign_status")
        if msg:
            slot.info(msg)
        else:
            slot.markdown("&nbsp;")

    draft = st.session_state.get("draft")
    if draft and assignment_applied(state, draft):
        # 확정은 저장됐는데 화면이 그 뒤를 못 따라온 경우, DB에 맞춰 배정안을 지우고 결과를 고친다.
        st.session_state.pop("draft", None)
        st.session_state.pop("assign_status", None)
        set_result(f"승인: 배정을 확정함({len(draft)}명)")
        draft = None
    if draft:
        by_no = {s.student_no: s for s in state.unassigned}
        st.write(f"검사를 통과한 배정안, 출처: {st.session_state.get('draft_source', '')}")
        st.table(
            [
                {
                    "이름": by_no[no].name if no in by_no else no,
                    "주 역할": by_no[no].main_role if no in by_no else "",
                    "보조 역할": ", ".join(by_no[no].sub_roles) or "없음" if no in by_no else "",
                    "배정된 팀": f"팀{team_no}",
                }
                for no, team_no in sorted(draft.items(), key=lambda x: (x[1], x[0]))
            ]
        )
    if st.button("배정안 확정", key="admin_confirm", type="primary"):
        if draft is None:
            set_result("막힘: 확정할 배정안이 없음")
        else:
            _act(lambda conn: confirm_assignment(conn, user, draft), clear_draft=True)


@st.fragment(run_every=REFRESH_SEC)
def _live() -> None:
    """현황: 팀이 없는 학생, 팀 목록, AI 기록. render가 이 부분만 몇 초마다 다시 그리게 한다."""
    snap = get_snapshot()
    state = snap.state
    history = snap.all_applications()
    with get_pool().connection() as conn:
        logs = recent_logs(conn)
    st.header("현황")
    st.caption(f"화면은 {REFRESH_SEC}초마다 저절로 바뀜")
    with st.container(key="unassigned"):
        names = ", ".join(s.name for s in state.unassigned) or "없음"
        st.write(f"팀이 없는 학생 {len(state.unassigned)}명: {names}")
    render_teams(state.teams, None, None)
    st.subheader("지원 기록")
    if history:
        st.table(
            [
                {
                    "지원자": h["name"],
                    "팀": f"팀{h['team_no']}",
                    "상태": h["status"],
                    "이유": h["reason"] or "",
                    "지원 시각": to_kst(h["created_at"], "%m-%d %H:%M:%S"),
                }
                for h in history
            ]
        )
    else:
        st.write("지원 기록 없음")
    with st.expander(f"AI 기록(최근 {len(logs)}건)"):
        if logs:
            st.table(
                [
                    {
                        "시각": to_kst(l["created_at"]),
                        "차수": f"{l['round_no']}차",
                        "모델": l["model"],
                        "결과": "성공" if l["ok"] else "실패",
                        "걸린 시간": f"{l['elapsed_sec']}초",
                        "실패 이유": l["error"] or "",
                    }
                    for l in logs
                ]
            )
        else:
            st.write("기록 없음")


def render(user: User) -> None:
    # 현황의 자동 갱신은 실행 중인 전체 실행(AI 배정 포함)을 끊지 않으므로 늘 켜 둔다.
    _roster_section(user)
    state = get_snapshot().state
    st.divider()
    _assign_section(user, state)
    st.divider()
    _live()
