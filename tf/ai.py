# 2026-10-27 16:47 KST
"""AI 배정(공고 2.5절 3~8항, 4.3절, 3장).

1차, 2차, 3차 모델을 차례로 부르고, 모델마다 요청을 보낸 때부터 120초가 지나면 응답이 오는
중이어도 끊고 다음 모델로 넘어간다. AI의 배정안은 앱이 검사 다섯 가지로 다시 검사하고,
3차까지 실패하면 앱이 모든 경우를 따져 찾은 배정을 쓴다.
"""
import json
import queue
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import psycopg
import requests

from tf.auth import User, require_admin
from tf.config import AI_DEADLINE_SEC, AI_MAX_TOKENS, AI_MODELS, OPENROUTER_URL, get_secret
from tf.rules import no_solution_reason, solve_assignment, validate_assignment
from tf.service import State, load_state


class AiError(Exception):
    """AI 호출 실패. reason은 화면과 기록에 그대로 쓴다(키는 넣지 않는다)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class AssignOutcome:
    assignment: dict[str, int] | None
    message: str  # result 안내
    status: str  # assign_status 안내


def _is_free(model: str) -> bool:
    return model.endswith(":free") and not model.startswith("openrouter/free")


def _error_detail(resp: requests.Response) -> str:
    """오류 응답의 짧은 설명. 예: ': No endpoints found matching your data policy'."""
    try:
        message = resp.json()["error"]["message"]
    except Exception:
        return ""
    return f": {str(message)[:120]}"


def call_model(
    model: str, prompt: str, *, api_key: str, deadline_sec: float = AI_DEADLINE_SEC, url: str = OPENROUTER_URL
) -> str:
    """모델 하나를 불러 답의 글을 돌려준다. 실패하면 AiError.

    requests의 timeout은 한 번 읽을 때의 대기 시간이라 응답이 조금씩 오면 전체 시간을 막지 못한다.
    그래서 응답 줄을 다른 스레드가 읽어 큐에 넣고, 여기서는 남은 시간만큼만 기다린다.
    """
    if not _is_free(model):
        raise AiError("무료 모델이 아님")
    timeout_msg = f"{deadline_sec:g}초 넘음"
    deadline = time.monotonic() + deadline_sec

    def left() -> float:
        return deadline - time.monotonic()

    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "max_tokens": AI_MAX_TOKENS,
        "reasoning": {"effort": "low"},
    }
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
            stream=True,
            timeout=(min(10, max(left(), 0.1)), max(left(), 0.1)),
        )
    except requests.Timeout:
        raise AiError(timeout_msg if left() <= 0 else "연결 시간 초과")
    except requests.RequestException as e:
        raise AiError(f"연결 실패({type(e).__name__})")

    lines: queue.Queue = queue.Queue()

    def reader() -> None:
        try:
            for line in resp.iter_lines():
                lines.put(("line", line))
            lines.put(("end", None))
        except Exception as e:  # 끊으면 여기로 온다
            lines.put(("error", e))

    try:
        if resp.status_code != 200:
            raise AiError(f"HTTP {resp.status_code}{_error_detail(resp)}")
        threading.Thread(target=reader, daemon=True).start()
        parts = []
        while True:
            try:
                kind, value = lines.get(timeout=max(left(), 0))
            except queue.Empty:
                raise AiError(timeout_msg)
            if left() <= 0:
                raise AiError(timeout_msg)
            if kind == "end":
                break
            if kind == "error":
                raise AiError(f"응답 끊김({type(value).__name__})")
            if not value or value.startswith(b":") or not value.startswith(b"data: "):
                continue  # 빈 줄, ": OPENROUTER PROCESSING" 같은 주석 줄
            data = value[len(b"data: "):]
            if data == b"[DONE]":
                break
            chunk = json.loads(data)
            if "error" in chunk:
                raise AiError(f"오류 응답({chunk['error'].get('code', '')})")
            choices = chunk.get("choices") or [{}]
            parts.append((choices[0].get("delta") or {}).get("content") or "")
    finally:
        # 연결을 끊는다. close()는 읽던 스레드를 기다려 몇 초 걸릴 수 있어 뒤에서 한다.
        threading.Thread(target=resp.close, daemon=True).start()
    text = "".join(parts).strip()
    if not text:
        raise AiError("빈 응답")
    return text


def _student_text(s) -> str:
    subs = ", ".join(s.sub_roles) or "없음"
    return f"{s.student_no} {s.name}: 주 역할 {s.main_role}, 보조 역할 {subs}"


def build_prompt(state: State) -> str:
    """지금 팀 구성, 팀이 없는 학생과 그 역할, 공고 2.3절 규칙을 담는다."""
    lines = [
        "팀 프로젝트 팀 편성에서, 팀이 없는 학생을 기존 팀에 배정하라. 아래 규칙을 모두 지켜야 한다.",
        "1. 배정 뒤 모든 팀은 2~4명이어야 한다(빈 팀 없음).",
        "2. 한 팀 안에 주 역할이 같은 학생이 2명 이상이면 안 된다(보조 역할은 겹쳐도 된다).",
        "3. 모든 팀에는 기획자를 맡을 학생과 웹 프로그래머를 맡을 학생이 서로 다른 사람으로 1명씩 있어야 한다."
        " 주 역할이나 보조 역할로 맡을 수 있다.",
        "4. 이미 팀에 있는 학생은 옮기지 않는다. 팀이 없는 학생만 배정한다.",
        "5. 팀이 없는 학생은 모두 정확히 한 팀에 배정한다.",
        "",
        "지금 팀 구성:",
    ]
    for t in state.teams:
        lines.append(f"- 팀{t.no}({len(t.members)}명)")
        lines += [f"  - {_student_text(m)}" for m in t.members] or ["  - (빈 팀)"]
    lines.append("")
    lines.append("팀이 없는 학생:")
    lines += [f"- {_student_text(s)}" for s in state.unassigned]
    lines += [
        "",
        "설명 없이 JSON 하나만 출력하라. team은 팀 번호(정수)다.",
        '{"assignments": [{"student_no": "학번", "team": 1}]}',
    ]
    return "\n".join(lines)


def parse_assignment(text: str) -> dict[str, int]:
    """답에서 JSON 부분만 꺼내 {학번: 팀 번호}로 바꾼다."""
    start, end = text.find("{"), text.rfind("}")
    try:
        data = json.loads(text[start : end + 1])
        plan = {}
        for item in data["assignments"]:
            digits = re.search(r"\d+", str(item["team"]))
            plan[str(item["student_no"]).strip()] = int(digits.group())
        return plan
    except (ValueError, KeyError, TypeError, AttributeError):
        raise AiError("JSON 아님")


def log_ai_call(conn: psycopg.Connection, round_no: int, model: str, ok: bool, elapsed: float, error: str | None) -> None:
    conn.execute(
        "insert into tf_ai_logs (round_no, model, ok, elapsed_sec, error) values (%s, %s, %s, %s, %s)",
        (round_no, model, ok, round(elapsed, 1), error),
    )
    if not conn.autocommit:
        conn.commit()  # 화면이 중간에 끊겨도 기록은 남긴다


def recent_logs(conn: psycopg.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        "select created_at, round_no, model, ok, elapsed_sec, error from tf_ai_logs order by id desc limit %s",
        (limit,),
    ).fetchall()
    keys = ["created_at", "round_no", "model", "ok", "elapsed_sec", "error"]
    return [dict(zip(keys, r)) for r in rows]


def assign(
    conn: psycopg.Connection,
    user: User,
    *,
    use_ai: bool,
    on_status: Callable[[str], None],
    caller: Callable[..., str] = call_model,
    models: tuple[str, ...] = AI_MODELS,
    api_key: str | None = None,
) -> AssignOutcome:
    """AI 배정 단추. 검사를 통과한 배정안만 돌려준다(저장은 confirm_assignment가 한다)."""
    require_admin(user)
    state = load_state(conn)
    if not state.closed:
        return AssignOutcome(None, "막힘: 먼저 모집을 마감해야 함", "")
    # 규칙을 지키는 배정이 아예 없으면 AI를 부르지 않는다(공고 2.5절 8항).
    found = solve_assignment(state.teams, state.unassigned)
    if found is None:
        reason = no_solution_reason(state.teams, state.unassigned)
        return AssignOutcome(None, "막힘: 규칙을 지키는 배정이 없음", f"규칙을 지키는 배정이 없음: {reason}")
    if not use_ai:
        return AssignOutcome(found, "승인: 앱이 규칙을 지키는 배정을 찾음(AI를 부르지 않음)", "AI를 부르지 않고 앱이 배정함")

    key = api_key or get_secret("OPENROUTER_API_KEY") or ""
    prompt = build_prompt(state)
    for i, model in enumerate(models, start=1):
        on_status(f"{i}차 모델({model})의 응답을 기다리는 중")
        start = time.monotonic()
        try:
            plan = parse_assignment(caller(model, prompt, api_key=key))
            errors = validate_assignment(state.teams, state.unassigned, plan)
            if errors:
                raise AiError(f"검사 불통과: {errors[0]}")
        except AiError as e:
            log_ai_call(conn, i, model, False, time.monotonic() - start, e.reason)
            continue
        except Exception as e:  # 뜻밖의 오류도 실패로 보고 다음 모델로 넘어간다
            log_ai_call(conn, i, model, False, time.monotonic() - start, f"오류({type(e).__name__})")
            continue
        elapsed = time.monotonic() - start
        log_ai_call(conn, i, model, True, elapsed, None)
        return AssignOutcome(
            plan, f"승인: {i}차 모델의 배정안이 검사를 통과함", f"{i}차 모델({model})의 배정안이 검사를 통과함({elapsed:.0f}초)"
        )
    return AssignOutcome(
        found, "승인: AI 배정이 실패해 앱이 규칙을 지키는 배정을 찾음", f"{len(models)}차 모델까지 실패해 앱이 배정함"
    )
