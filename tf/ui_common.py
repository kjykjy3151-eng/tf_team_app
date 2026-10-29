# 2026-10-27 16:14 KST
"""여러 화면이 같이 쓰는 것: 결과 안내(result)와 동작 실행."""
import threading
import time
from collections.abc import Callable

import psycopg
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from tf import diag
from tf.config import TEAM_MAX
from tf.db import get_pool
from tf.roster import RosterError
from tf.rules import Student
from tf.service import Snapshot, load_snapshot

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


class SharedSnapshot:
    """여러 화면이 같이 쓰는 상태. ttl초 안에는 DB를 다시 읽지 않고, invalidate 뒤에는 바로 새로 읽는다.

    학생마다 몇 초마다 DB를 따로 읽으면, 접속한 학생 수만큼 질의가 늘어 화면이 느려진다.
    읽기는 한 번에 하나씩만 하고, invalidate 전에 읽기 시작한 값은 저장하지 않는다.
    """

    def __init__(self, loader: Callable[[], object], ttl: float, clock: Callable[[], float] = time.monotonic):
        self._loader, self._ttl, self._clock = loader, ttl, clock
        self._lock = threading.Lock()  # 값과 세대 번호를 지킴
        self._load_lock = threading.Lock()  # 읽기를 한 번에 하나만
        self._value, self._at, self._gen = None, 0.0, 0

    def _fresh(self):
        with self._lock:
            if self._value is not None and self._clock() - self._at < self._ttl:
                return self._value
            return None

    def get(self):
        value = self._fresh()
        if value is not None:
            return value
        with self._load_lock:
            value = self._fresh()
            if value is not None:
                return value
            with self._lock:
                gen = self._gen
            value = self._loader()
            with self._lock:
                if self._gen == gen:
                    self._value, self._at = value, self._clock()
            return value

    def invalidate(self) -> None:
        with self._lock:
            self._gen += 1
            self._value = None


def _load_from_db() -> Snapshot:
    t = time.monotonic()
    with get_pool().connection() as conn:
        snap = load_snapshot(conn)
    diag.add("loads"); diag.add("load_sec", time.monotonic() - t)
    return snap


@st.cache_resource
def _shared() -> SharedSnapshot:
    return SharedSnapshot(_load_from_db, ttl=1.0)


def get_snapshot() -> Snapshot:
    """화면을 그릴 때 쓰는 상태. 1초 안에 다른 화면이 읽은 것이 있으면 그것을 쓴다."""
    t = time.monotonic()
    snap = _shared().get()
    diag.peak("wait_max", time.monotonic() - t)
    return snap


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
    finally:
        _shared().invalidate()  # 바뀐 상태를 다음 화면에서 바로 보이게 함
    set_result(msg)


def student_line(s: Student) -> str:
    subs = ", ".join(s.sub_roles) or "없음"
    return f"{s.name} · 주 역할 {s.main_role} · 보조 역할 {subs}"


def render_teams(teams, my_team_no: int | None, apply_button: Callable[[int], None] | None) -> None:
    """팀마다 key가 team_{번호}인 컨테이너에 팀원의 이름과 역할을 보여 준다."""
    for team in teams:
        with st.container(key=f"team_{team.no}", border=True):
            mine = " `내 팀`" if team.no == my_team_no else ""
            # 팀 이름과 팀원을 한 요소로 그린다. 요소가 적을수록 여러 학생이 접속했을 때 서버가 덜 바쁘다.
            lines = [f"- {student_line(m)}" for m in team.members] or ["빈 팀"]
            title = f"**팀{team.no}**{mine} ({len(team.members)}/{TEAM_MAX}명)"
            st.markdown("\n".join([title, "", *lines]))
            if apply_button:
                apply_button(team.no)
