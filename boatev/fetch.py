"""間隔を強制する取得層。

LZH は 2 秒に 1 件、オッズ・直前情報ページは 3 秒に 1 件以上の間隔（spec「前提と制約」）。
間隔は「前のリクエストの開始時刻から」測る。直列のみ（並列化しない）。
開発PC（machine.role が exec 以外）ではページ取得は例外にする。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

import requests

from boatev.config import LZH_INTERVAL_MIN, PAGE_INTERVAL_MIN

if TYPE_CHECKING:
    from boatev.config import Config

DEFAULT_TIMEOUT_SEC = 30.0


class PageFetchForbidden(Exception):
    """machine.role が exec 以外（開発PC）でページ取得を呼んだ。"""


class _Session(Protocol):
    def get(self, url: str, **kwargs: Any) -> requests.Response: ...


class RateLimiter:
    """リクエスト開始の間隔を interval 秒以上に保つ。初回は待たない。"""

    def __init__(
        self,
        interval: float,
        floor: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        # 設定値が下限未満・nan でも下限を割らない（config 側の検証との二重防御）。
        # nan は max() の比較が False になるので「下限以上」の形で確かめる。
        self.interval = interval if interval >= floor else floor
        if self.interval == float("inf"):
            raise ValueError("interval は有限値")
        self._clock = clock
        self._sleep = sleep
        self._last_start: float | None = None

    def wait(self) -> None:
        """次のリクエストを開始してよい時刻まで待ち、開始時刻を記録する。"""
        if self._last_start is not None:
            while True:
                remaining = self._last_start + self.interval - self._clock()
                if remaining <= 0:
                    break
                self._sleep(remaining)
        self._last_start = self._clock()


class Fetcher:
    """LZH とページの取得。種別ごとに独立した RateLimiter を通し、直列に実行する。"""

    def __init__(
        self,
        *,
        role: str,
        lzh_interval_sec: float = LZH_INTERVAL_MIN,
        page_interval_sec: float = PAGE_INTERVAL_MIN,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        user_agent: str,
        session: _Session | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.role = role
        self.timeout_sec = timeout_sec
        self.user_agent = user_agent
        self._session: _Session = session if session is not None else requests.Session()
        self._lzh_limiter = RateLimiter(lzh_interval_sec, LZH_INTERVAL_MIN, clock, sleep)
        self._page_limiter = RateLimiter(page_interval_sec, PAGE_INTERVAL_MIN, clock, sleep)
        # 同じ種別のリクエストは同時に走らせない（待ちからリクエスト完了までを直列化）
        self._lzh_lock = threading.Lock()
        self._page_lock = threading.Lock()

    @classmethod
    def from_config(
        cls,
        cfg: Config,
        session: _Session | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> Fetcher:
        return cls(
            role=cfg.role,
            lzh_interval_sec=cfg.lzh_interval_sec,
            page_interval_sec=cfg.page_interval_sec,
            timeout_sec=cfg.timeout_sec,
            user_agent=cfg.user_agent,
            session=session,
            clock=clock,
            sleep=sleep,
        )

    def _get(self, url: str) -> requests.Response:
        return self._session.get(
            url,
            timeout=self.timeout_sec,
            headers={"User-Agent": self.user_agent},
        )

    def get_lzh(self, url: str) -> requests.Response:
        """LZH を 1 件取得する。HTTP ステータスの判定は呼び出し側。リトライしない。"""
        with self._lzh_lock:
            self._lzh_limiter.wait()
            return self._get(url)

    def get_page(self, url: str) -> requests.Response:
        """オッズ・直前情報ページを 1 件取得する。exec 以外のロールでは例外。"""
        if self.role != "exec":
            raise PageFetchForbidden(
                f"machine.role={self.role!r} ではページを取得しない（開発PCからはアクセスしない）"
            )
        with self._page_lock:
            self._page_limiter.wait()
            return self._get(url)
