import ast
import time
from pathlib import Path

import pytest

from boatev.config import load_config
from boatev.fetch import Fetcher, PageFetchForbidden, RateLimiter

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "config.example.yaml"

LZH_URL = "https://example.invalid/od2/B/202401/b240101.lzh"
PAGE_URL = "https://example.invalid/race/oddstf?rno=1&jcd=01&hd=20240101"


class FakeClock:
    """時計と sleep。sleep は時計を進めるだけで実際には待たない。"""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, sec: float) -> None:
        self.sleeps.append(sec)
        self.now += sec

    def advance(self, sec: float) -> None:
        self.now += sec


class FakeResponse:
    def __init__(self, url: str, status_code: int = 200) -> None:
        self.url = url
        self.status_code = status_code
        self.content = b"x"


class FakeSession:
    """requests.Session の get の置き換え。呼び出し時刻と引数を記録する。"""

    def __init__(self, clock: FakeClock, duration: float = 0.0) -> None:
        self.clock = clock
        self.duration = duration
        self.calls: list[tuple[str, float, dict]] = []

    def get(self, url, **kwargs):
        self.calls.append((url, self.clock.now, kwargs))
        self.clock.advance(self.duration)  # リクエスト自体にかかる時間
        return FakeResponse(url)

    def starts(self, url_part: str) -> list[float]:
        return [t for u, t, _ in self.calls if url_part in u]


def _fetcher(role="exec", lzh=2.0, page=3.0, duration=0.0):
    clock = FakeClock()
    session = FakeSession(clock, duration)
    f = Fetcher(
        role=role,
        lzh_interval_sec=lzh,
        page_interval_sec=page,
        timeout_sec=30,
        user_agent="boatev/test",
        session=session,
        clock=clock.monotonic,
        sleep=clock.sleep,
    )
    return f, session, clock


def _gaps(times: list[float]) -> list[float]:
    return [b - a for a, b in zip(times, times[1:], strict=False)]


# --- RateLimiter ---


def test_first_request_does_not_wait():
    clock = FakeClock()
    rl = RateLimiter(2.0, 2.0, clock.monotonic, clock.sleep)
    rl.wait()
    assert clock.sleeps == []


def test_second_request_sleeps_only_the_shortfall():
    clock = FakeClock()
    rl = RateLimiter(2.0, 2.0, clock.monotonic, clock.sleep)
    rl.wait()
    clock.advance(0.5)
    rl.wait()
    assert clock.sleeps == [pytest.approx(1.5)]


def test_no_sleep_when_interval_already_elapsed():
    clock = FakeClock()
    rl = RateLimiter(2.0, 2.0, clock.monotonic, clock.sleep)
    rl.wait()
    clock.advance(2.0)
    rl.wait()
    clock.advance(10.0)
    rl.wait()
    assert clock.sleeps == []


def test_sleep_that_returns_early_is_retried():
    clock = FakeClock()
    short = []

    def early_sleep(sec):
        short.append(sec)
        clock.advance(sec / 2)  # 要求の半分しか進まない sleep

    rl = RateLimiter(2.0, 2.0, clock.monotonic, early_sleep)
    rl.wait()
    t0 = clock.now
    rl.wait()
    assert clock.now - t0 >= 2.0
    assert len(short) > 1


@pytest.mark.parametrize("bad", [0.0, 1.0, -5.0, float("nan")])
def test_ratelimiter_clamps_interval_to_floor(bad):
    clock = FakeClock()
    rl = RateLimiter(bad, 3.0, clock.monotonic, clock.sleep)
    assert rl.interval == 3.0
    rl.wait()
    rl.wait()
    assert clock.sleeps == [pytest.approx(3.0)]


def test_ratelimiter_rejects_inf():
    with pytest.raises(ValueError):
        RateLimiter(float("inf"), 3.0)


# --- Fetcher ---


def test_lzh_gaps_at_least_2_sec():
    f, session, _ = _fetcher()
    for i in range(5):
        f.get_lzh(f"{LZH_URL}?n={i}")
    starts = session.starts("lzh")
    assert len(starts) == 5
    assert all(g >= 2.0 for g in _gaps(starts))


def test_page_gaps_at_least_3_sec():
    f, session, _ = _fetcher()
    for i in range(5):
        f.get_page(f"{PAGE_URL}&n={i}")
    starts = session.starts("oddstf")
    assert len(starts) == 5
    assert all(g >= 3.0 for g in _gaps(starts))


def test_gap_is_measured_from_previous_request_start():
    # リクエスト自体に 1.2 秒かかるなら、追加で待つのは 2.0 - 1.2 秒だけ
    f, session, clock = _fetcher(duration=1.2)
    f.get_lzh(LZH_URL)
    f.get_lzh(LZH_URL)
    a, b = session.starts("lzh")
    assert b - a == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(0.8)]


def test_first_request_of_each_kind_does_not_wait():
    f, _, clock = _fetcher()
    f.get_lzh(LZH_URL)
    assert clock.sleeps == []
    f.get_page(PAGE_URL)
    assert clock.sleeps == []


def test_kinds_are_independent():
    f, session, clock = _fetcher()
    f.get_lzh(LZH_URL)
    f.get_page(PAGE_URL)
    # 種別が違えば相手の間隔に引きずられて待たない
    assert clock.sleeps == []
    assert session.starts("lzh") == session.starts("oddstf")
    # 同じ種別では待つ
    f.get_lzh(LZH_URL)
    assert clock.sleeps == [pytest.approx(2.0)]


def test_interleaved_requests_keep_each_kinds_gap():
    f, session, clock = _fetcher()
    for _ in range(3):
        f.get_lzh(LZH_URL)
        clock.advance(0.3)
        f.get_page(PAGE_URL)
        clock.advance(0.3)
    assert all(g >= 2.0 for g in _gaps(session.starts("lzh")))
    assert all(g >= 3.0 for g in _gaps(session.starts("oddstf")))


def test_configured_interval_below_floor_is_clamped():
    f, session, _ = _fetcher(lzh=0.1, page=0.5)
    for _ in range(3):
        f.get_lzh(LZH_URL)
        f.get_page(PAGE_URL)
    assert all(g >= 2.0 for g in _gaps(session.starts("lzh")))
    assert all(g >= 3.0 for g in _gaps(session.starts("oddstf")))


def test_nan_interval_is_clamped():
    f, session, _ = _fetcher(lzh=float("nan"), page=float("nan"))
    for _ in range(3):
        f.get_lzh(LZH_URL)
        f.get_page(PAGE_URL)
    assert all(g >= 2.0 for g in _gaps(session.starts("lzh")))
    assert all(g >= 3.0 for g in _gaps(session.starts("oddstf")))


def test_longer_configured_interval_is_used():
    f, session, _ = _fetcher(lzh=5.0, page=7.0)
    f.get_lzh(LZH_URL)
    f.get_lzh(LZH_URL)
    f.get_page(PAGE_URL)
    f.get_page(PAGE_URL)
    assert _gaps(session.starts("lzh")) == [pytest.approx(5.0)]
    assert _gaps(session.starts("oddstf")) == [pytest.approx(7.0)]


def test_failed_request_still_counts_for_the_interval():
    f, session, clock = _fetcher()

    def boom(url, **kwargs):
        session.calls.append((url, clock.now, kwargs))
        raise ConnectionError("down")

    session.get = boom
    with pytest.raises(ConnectionError):
        f.get_lzh(LZH_URL)
    with pytest.raises(ConnectionError):
        f.get_lzh(LZH_URL)
    assert _gaps(session.starts("lzh")) == [pytest.approx(2.0)]


def test_request_passes_timeout_and_user_agent():
    f, session, _ = _fetcher()
    resp = f.get_lzh(LZH_URL)
    assert resp.status_code == 200
    _, _, kwargs = session.calls[0]
    assert kwargs["timeout"] == 30
    assert kwargs["headers"]["User-Agent"] == "boatev/test"


def test_non_200_is_returned_not_raised():
    f, session, _ = _fetcher()
    session.get = lambda url, **kw: FakeResponse(url, 404)
    assert f.get_lzh(LZH_URL).status_code == 404


@pytest.mark.parametrize("role", ["dev", "prod", ""])
def test_page_fetch_refused_on_dev(role):
    f, session, clock = _fetcher(role=role)
    with pytest.raises(PageFetchForbidden):
        f.get_page(PAGE_URL)
    # セッションに触らず、待ちも発生しない
    assert session.calls == []
    assert clock.sleeps == []


def test_lzh_allowed_on_dev():
    f, session, _ = _fetcher(role="dev")
    assert f.get_lzh(LZH_URL).status_code == 200
    assert len(session.calls) == 1


def test_from_config_example_is_dev_and_refuses_pages():
    cfg = load_config(EXAMPLE)
    clock = FakeClock()
    session = FakeSession(clock)
    f = Fetcher.from_config(cfg, session=session, clock=clock.monotonic, sleep=clock.sleep)
    assert f.user_agent == cfg.user_agent
    assert f.timeout_sec == cfg.timeout_sec
    with pytest.raises(PageFetchForbidden):
        f.get_page(PAGE_URL)
    assert session.calls == []


def test_default_session_is_created_without_network():
    # セッションを渡さなくても生成だけではネットワークに出ない
    f = Fetcher(role="dev", user_agent="boatev/test")
    assert f.role == "dev"


def test_default_clock_and_sleep_are_monotonic_and_time_sleep():
    # 注入しない既定は本物の time.monotonic / time.sleep（壁時計や別の sleep ではない）
    rl = RateLimiter(2.0, 2.0)
    assert rl._clock is time.monotonic
    assert rl._sleep is time.sleep
    f = Fetcher(role="dev", user_agent="boatev/test")
    for limiter in (f._lzh_limiter, f._page_limiter):
        assert limiter._clock is time.monotonic
        assert limiter._sleep is time.sleep
    g = Fetcher.from_config(load_config(EXAMPLE))
    for limiter in (g._lzh_limiter, g._page_limiter):
        assert limiter._clock is time.monotonic
        assert limiter._sleep is time.sleep


def test_fetch_module_has_no_concurrency():
    # 取得は並列化しない：並列実行系のモジュールを使っていない
    tree = ast.parse((ROOT / "boatev" / "fetch.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"concurrent", "asyncio", "multiprocessing", "aiohttp", "httpx"}
