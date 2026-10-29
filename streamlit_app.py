# 2026-10-27 16:14 KST
"""팀 편성 앱 진입점. 로그인 여부와 관리자 여부로 화면을 나눈다."""
import streamlit as st

from tf import diag, ui_admin, ui_student
from tf.auth import ensure_admin, login
from tf.config import get_secret
from tf.db import get_pool
from tf.ui_common import fill_result, result_box, set_result

st.set_page_config(page_title="팀 편성")


@st.cache_resource
def _ensure_admin_once(password: str) -> None:
    """같은 비밀번호로는 앱 프로세스에서 한 번만 관리자 계정을 만들거나 갱신한다."""
    with get_pool().connection() as conn:
        ensure_admin(conn, password)


def init_admin() -> bool:
    """ADMIN_PASSWORD로 관리자 계정을 만들거나 비밀번호를 갱신한다.

    비밀 값이 없을 때의 결과는 저장하지 않는다. 배포 뒤에 Secrets를 넣어도 바로 반영되게 하기 위함이다.
    """
    password = get_secret("ADMIN_PASSWORD")
    if not password:
        return False
    _ensure_admin_once(password)
    return True


@st.cache_resource
def _start_diag() -> None:
    diag.start()


_start_diag()
admin_ready = init_admin()
user = st.session_state.get("user")

if user is None:
    st.title("팀 편성")
    if not admin_ready:
        st.caption("관리자 비밀번호 설정: 없음")
    with st.form("login_form"):
        student_no = st.text_input("학번", key="login_student_no")
        password = st.text_input("비밀번호", type="password", key="login_password")
        submitted = st.form_submit_button("로그인", key="login_submit")
    box = result_box()
    if submitted:
        with get_pool().connection() as conn:
            found = login(conn, student_no, password)
        if found is None:
            set_result("막힘: 학번이나 비밀번호가 틀림")
        else:
            st.session_state["user"] = found
            set_result(f"승인: {found.name} 로그인함")
            st.rerun()
    fill_result(box)
else:
    with st.sidebar:
        if st.button("로그아웃", key="logout"):
            st.session_state.clear()
            st.rerun()
    st.title("팀 편성 · 관리자" if user.is_admin else "팀 편성")
    with st.container(key="whoami"):
        st.markdown(f"로그인: **{user.name}** ({user.student_no})")
    box = result_box()
    if user.is_admin:
        ui_admin.render(user)
    else:
        ui_student.render(user)
    fill_result(box)
