# 2026-10-30 00:35 KST
"""임시 측정: 10초마다 서버 CPU 사용 비율, 화면 그리기 수, DB 읽기 시간을 로그에 남긴다(비밀값은 남기지 않음)."""
import threading
import time

_lock = threading.Lock()
_zero = {"renders": 0, "render_sec": 0.0, "render_max": 0.0, "loads": 0, "load_sec": 0.0, "wait_max": 0.0}
_stats = dict(_zero)


def add(key: str, value: float = 1) -> None:
    with _lock:
        _stats[key] += value


def peak(key: str, value: float) -> None:
    with _lock:
        _stats[key] = max(_stats[key], value)


def start() -> None:
    def loop() -> None:
        last_cpu, last_wall = time.process_time(), time.monotonic()
        while True:
            time.sleep(10)
            cpu, wall = time.process_time(), time.monotonic()
            with _lock:
                s = dict(_stats)
                _stats.update(_zero)
            avg = s["render_sec"] / s["renders"] if s["renders"] else 0
            print(
                f"[측정] CPU {100 * (cpu - last_cpu) / (wall - last_wall):.0f}% | 학생 화면 {s['renders']}회"
                f" 평균 {avg:.2f}초 최장 {s['render_max']:.2f}초 | DB 읽기 {s['loads']}회 {s['load_sec']:.2f}초"
                f" | 상태 기다림 최장 {s['wait_max']:.2f}초 | 스레드 {threading.active_count()}",
                flush=True,
            )
            last_cpu, last_wall = cpu, wall

    threading.Thread(target=loop, daemon=True, name="diag").start()
