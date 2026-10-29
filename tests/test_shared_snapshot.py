# 2026-10-29 23:32 KST
"""여러 화면이 같이 쓰는 상태 캐시: 짧은 시간 안에는 다시 읽지 않고, 쓰기 뒤에는 바로 새로 읽는다."""
import threading

from tf.ui_common import SharedSnapshot


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_reuses_within_ttl_and_reloads_after():
    clock, calls = Clock(), []
    cache = SharedSnapshot(lambda: calls.append(1) or len(calls), ttl=1.0, clock=clock)
    assert cache.get() == 1
    clock.t = 0.9
    assert cache.get() == 1
    clock.t = 1.1
    assert cache.get() == 2


def test_invalidate_forces_reload():
    clock, calls = Clock(), []
    cache = SharedSnapshot(lambda: calls.append(1) or len(calls), ttl=10.0, clock=clock)
    assert cache.get() == 1
    cache.invalidate()
    assert cache.get() == 2


def test_load_started_before_invalidate_is_not_kept():
    # 다른 화면이 쓰기 전에 읽기 시작한 상태는, 쓰기 뒤에 저장되어도 다시 쓰지 않는다.
    clock = Clock()
    started, release = threading.Event(), threading.Event()
    values = iter(["old", "new"])

    def loader():
        v = next(values)
        if v == "old":
            started.set()
            release.wait(5)
        return v

    cache = SharedSnapshot(loader, ttl=10.0, clock=clock)
    out = []
    t = threading.Thread(target=lambda: out.append(cache.get()))
    t.start()
    started.wait(5)
    cache.invalidate()  # 쓰기가 끝남
    release.set()
    t.join(5)
    assert out == ["old"]  # 먼저 읽기 시작한 화면은 옛 값을 받음
    assert cache.get() == "new"  # 그 뒤에는 새로 읽음
