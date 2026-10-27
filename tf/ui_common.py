# 2026-10-27 16:14 KST
"""여러 화면이 같이 쓰는 것: 결과 안내(result)와 동작 실행."""
from collections.abc import Callable

import psycopg
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from tf.db import get_pool
from tf.roster import RosterError

RESULT_WORDS = ("승인", "대기", "거절", "막힘")


def set_result(msg: str) -> None:
    """result 안내는 승인, 대기, 거절, 막힘 가운데 하나로 시작해야 한다."""
    assert msg.startswith(RESULT_WORDS), msg
    st.session_state["result"] = msg


def result_box() -> DeltaGenerator:
    """화면 위쪽에 result 자리를 만든다. 내용은 단추를 처리한 뒤 fill_result로 채운다."""
    return st.container(key="result")


def fill_result(box: DeltaGenerator) -> None:
    with box:
        msg = st.session_state.get("result")
        if msg:
            st.info(msg)
        else:
            # 빈 컨테이너는 화면에 그려지지 않으므로 빈칸 하나를 넣어 result 자리를 늘 둔다.
            st.markdown("&nbsp;")


def run_action(action: Callable[[psycopg.Connection], str]) -> None:
    """DB 연결을 빌려 동작을 실행하고 결과를 result에 넣는다. 오류는 종류만 보여 준다."""
    try:
        with get_pool().connection() as conn:
            msg = action(conn)
    except PermissionError as e:
        msg = str(e)
    except RosterError as e:
        msg = f"막힘: {e}"
    except psycopg.Error as e:
        msg = f"막힘: DB 오류({type(e).__name__})"
    set_result(msg)
