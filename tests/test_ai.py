# 2026-10-27 16:47 KST
"""AI 배정 테스트. 실제 오픈라우터는 부르지 않는다(로컬 가짜 서버와 가짜 caller)."""
import functools
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tf.ai import AiError, assign, call_model, parse_assignment, recent_logs
from tf.auth import User
from tf.roster import reset_with_roster
from tf.rules import Student
from tf.service import apply, close_recruitment, confirm_assignment, vote

ADMIN = User("admin", "관리자", True)
PL, WP, FD, TT, RW, PT = "기획자", "웹 프로그래머", "프론트엔드 디자이너", "테스터", "보고서 작성자", "발표자"
KEY = "test-key-not-real-123"
MODELS = ("m1:free", "m2:free", "m3:free")


def sse(text: str) -> bytes:
    return f"data: {json.dumps({'choices': [{'delta': {'content': text}}]})}\n\n".encode()


class FakeServer:
    """경로로 동작을 고른다: /slow, /empty, /429, /ok."""

    def __init__(self):
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                outer.requests.append((self.path, json.loads(body), self.headers.get("Authorization")))
                if self.path == "/429":
                    self.send_response(429)
                    self.end_headers()
                    self.wfile.write(b'{"error":"rate"}')
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                try:
                    if self.path == "/slow":
                        self.wfile.write(b": OPENROUTER PROCESSING\n\n")
                        for _ in range(40):
                            self.wfile.write(sse("."))
                            self.wfile.flush()
                            time.sleep(0.5)
                    elif self.path == "/ok":
                        self.wfile.write(b": OPENROUTER PROCESSING\n\n")
                        self.wfile.write(sse('```json\n{"assignments": '))
                        self.wfile.write(sse('[{"student_no": "C", "team": 2}]}\n```'))
                    self.wfile.write(b"data: [DONE]\n\n")
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


@pytest.fixture
def server():
    s = FakeServer()
    yield s
    s.close()


def test_deadline_cuts_slow_stream(server):
    start = time.monotonic()
    with pytest.raises(AiError) as e:
        call_model("m:free", "p", api_key=KEY, deadline_sec=2, url=server.url + "/slow")
    assert e.value.reason == "2초 넘음"
    assert time.monotonic() - start < 3


def test_empty_response_is_failure(server):
    with pytest.raises(AiError) as e:
        call_model("m:free", "p", api_key=KEY, url=server.url + "/empty")
    assert e.value.reason == "빈 응답"


def test_http_429_is_failure(server):
    with pytest.raises(AiError) as e:
        call_model("m:free", "p", api_key=KEY, url=server.url + "/429")
    assert e.value.reason == "HTTP 429"


def test_request_body_and_text(server):
    text = call_model("m:free", "프롬프트", api_key=KEY, url=server.url + "/ok")
    assert parse_assignment(text) == {"C": 2}
    _, body, auth = server.requests[0]
    assert body["model"] == "m:free" and body["stream"] is True
    assert body["reasoning"] == {"effort": "low"} and body["max_tokens"] >= 4000
    assert body["temperature"] == 0
    assert auth == f"Bearer {KEY}"


def test_paid_model_never_called(server):
    for model in ["openai/gpt-4o", "openrouter/free", "openrouter/free:free"]:
        with pytest.raises(AiError) as e:
            call_model(model, "p", api_key=KEY, url=server.url + "/ok")
        assert e.value.reason == "무료 모델이 아님"
    assert server.requests == []


def test_parse_assignment_variants():
    assert parse_assignment('설명입니다 {"assignments": [{"student_no": 2026101, "team": "팀3"}]} 끝') == {"2026101": 3}
    with pytest.raises(AiError) as e:
        parse_assignment("배정할 수 없습니다")
    assert e.value.reason == "JSON 아님"


# --- assign: DB가 필요한 테스트 ---


def closed_state(conn):
    """팀1: A(기획자), B(웹 프로그래머) / 팀2: 빈 팀 / 팀이 없는 학생: C(기획자), D(웹 프로그래머)."""
    students = [Student("A", "이름A", PL), Student("B", "이름B", WP), Student("C", "이름C", PL), Student("D", "이름D", WP)]
    reset_with_roster(conn, ADMIN, students, 2)
    apply(conn, "A", 1); apply(conn, "B", 1); vote(conn, "A", "B", True)
    close_recruitment(conn, ADMIN)


def fake_caller(script):
    """script: 모델 이름 → 돌려줄 글 또는 던질 AiError."""
    calls = []

    def caller(model, prompt, *, api_key):
        calls.append(model)
        out = script[model]
        if isinstance(out, Exception):
            raise out
        return out

    caller.calls = calls
    return caller


GOOD = '{"assignments": [{"student_no": "C", "team": 2}, {"student_no": "D", "team": 2}]}'
BAD = '{"assignments": [{"student_no": "C", "team": 2}, {"student_no": "D", "team": 1}]}'


def test_assign_falls_through_to_third_then_app(conn):
    closed_state(conn)
    caller = fake_caller({"m1:free": AiError("120초 넘음"), "m2:free": AiError("빈 응답"), "m3:free": BAD})
    statuses = []
    out = assign(conn, ADMIN, use_ai=True, on_status=statuses.append, caller=caller, models=MODELS, api_key=KEY)
    assert out.message == "승인: AI 배정이 실패해 앱이 규칙을 지키는 배정을 찾음"
    assert out.assignment == {"C": 2, "D": 2}
    assert out.source == "앱 배정(3차 모델까지 실패)"
    assert [s[:2] for s in statuses] == ["1차", "2차", "3차"]
    logs = recent_logs(conn)
    assert [(l["round_no"], l["ok"]) for l in logs] == [(3, False), (2, False), (1, False)]
    assert logs[0]["error"].startswith("검사 불통과: ")


def test_assign_uses_second_model_when_first_fails(conn):
    closed_state(conn)
    caller = fake_caller({"m1:free": AiError("HTTP 429"), "m2:free": GOOD})
    out = assign(conn, ADMIN, use_ai=True, on_status=lambda s: None, caller=caller, models=MODELS, api_key=KEY)
    assert out.message == "승인: 2차 모델의 배정안이 검사를 통과함"
    assert out.assignment == {"C": 2, "D": 2}
    assert out.source == "2차 모델(m2:free)"
    assert caller.calls == ["m1:free", "m2:free"]


def test_assign_no_solution_does_not_call_ai(conn):
    students = [Student("A", "이름A", PL), Student("B", "이름B", FD), Student("C", "이름C", TT), Student("D", "이름D", RW)]
    reset_with_roster(conn, ADMIN, students, 1)
    apply(conn, "A", 1)
    close_recruitment(conn, ADMIN)  # A 혼자라 빠짐 → 4명이 남지만 웹 프로그래머가 없음
    caller = fake_caller({})
    out = assign(conn, ADMIN, use_ai=True, on_status=lambda s: None, caller=caller, models=MODELS, api_key=KEY)
    assert caller.calls == []
    assert out.message == "막힘: 규칙을 지키는 배정이 없음"
    assert out.status == "규칙을 지키는 배정이 없음: 팀1에 웹 프로그래머를 맡을 학생이 없음"


def test_assign_with_no_unassigned_does_not_call_ai(conn):
    # 마감 때 모든 학생이 규칙을 지키는 팀에 있으면 배정할 학생이 없다. 빈 배정안도 확정할 수 있어야 한다.
    students = [Student("A", "이름A", PL), Student("B", "이름B", WP)]
    reset_with_roster(conn, ADMIN, students, 1)
    apply(conn, "A", 1); apply(conn, "B", 1); vote(conn, "A", "B", True)
    close_recruitment(conn, ADMIN)
    caller = fake_caller({})
    out = assign(conn, ADMIN, use_ai=True, on_status=lambda s: None, caller=caller, models=MODELS, api_key=KEY)
    assert caller.calls == []
    assert out.assignment == {}
    assert out.message == "승인: 팀이 없는 학생이 없어 배정할 학생이 없음"
    assert confirm_assignment(conn, ADMIN, out.assignment) == "승인: 배정을 확정함(0명)"


def test_assign_without_ai(conn):
    closed_state(conn)
    caller = fake_caller({})
    out = assign(conn, ADMIN, use_ai=False, on_status=lambda s: None, caller=caller, models=MODELS, api_key=KEY)
    assert caller.calls == []
    assert out.message == "승인: 앱이 규칙을 지키는 배정을 찾음(AI를 부르지 않음)"


def test_assign_before_close_blocked(conn):
    reset_with_roster(conn, ADMIN, [Student("A", "이름A", PL)], 1)
    out = assign(conn, ADMIN, use_ai=False, on_status=lambda s: None, models=MODELS, api_key=KEY)
    assert out.message == "막힘: 먼저 모집을 마감해야 함"


def test_student_cannot_assign(conn):
    closed_state(conn)
    with pytest.raises(PermissionError):
        assign(conn, User("A", "이름A", False), use_ai=False, on_status=lambda s: None)


def test_assign_total_time_bounded(conn, server):
    closed_state(conn)
    caller = functools.partial(call_model, deadline_sec=1, url=server.url + "/slow")
    start = time.monotonic()
    out = assign(conn, ADMIN, use_ai=True, on_status=lambda s: None, caller=caller, models=MODELS, api_key=KEY)
    assert time.monotonic() - start < 6  # 모델마다 1초 제한 × 3 + 앱 배정
    assert out.message == "승인: AI 배정이 실패해 앱이 규칙을 지키는 배정을 찾음"
    assert [l["error"] for l in recent_logs(conn)] == ["1초 넘음"] * 3


def test_api_key_not_in_error_or_log(conn, server):
    closed_state(conn)
    caller = functools.partial(call_model, url=server.url + "/429")
    assign(conn, ADMIN, use_ai=True, on_status=lambda s: None, caller=caller, models=MODELS, api_key=KEY)
    logs = recent_logs(conn)
    assert logs and all(KEY not in (l["error"] or "") for l in logs)
