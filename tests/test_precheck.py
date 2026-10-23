import dataclasses
import datetime as dt
import io
import json
import shutil
import sys
from pathlib import Path

import pytest
import requests
from lzh_builder import build_lzh

from boatev import precheck
from boatev.cli import main
from boatev.config import load_config
from boatev.fetch import Fetcher
from boatev.lzh import ExtractError
from boatev.precheck import (
    DateRejected,
    check_past_dates,
    page_path,
    page_url,
    run_precheck,
    venues_from_b_text,
)

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "config.example.yaml"
REAL_LZH_DIR = ROOT / "tests" / "fixtures" / "real" / "lzh"

LZH_BASE = "https://lzh.example.invalid/od2"
PAGE_BASE = "https://page.example.invalid/race"
LZH_BODY = b"\x20\x00-lh5-body"
DAYS = [dt.date(2024, 1, 5), dt.date(2024, 1, 6), dt.date(2024, 1, 7)]

# 場の出現順は 24, 23, 03, 04（jcd の昇順は 03, 04, 23, 24）
B_TEXT = "STARTB\r\n" + "".join(
    f"{j}BBGN\r\n（番組）\r\n{j}BEND\r\n" for j in ("24", "23", "03", "04")
)
K_TEXT = "STARTK\r\n" + "".join(f"{j}KBGN\r\n（成績）\r\n{j}KEND\r\n" for j in ("24", "23", "03"))


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def monotonic(self) -> float:
        return self.now

    def sleep(self, sec: float) -> None:
        self.now += sec


class FakeResponse:
    def __init__(self, url: str, status_code: int = 200, content: bytes = b"") -> None:
        self.url = url
        self.status_code = status_code
        self.content = content


class FakeSession:
    """requests.Session の置き換え。全リクエストの URL と開始時刻を記録する。"""

    def __init__(self, clock: FakeClock, duration: float = 0.0, handler=None) -> None:
        self.clock = clock
        self.duration = duration
        self.handler = handler
        self.calls: list[tuple[str, float]] = []

    def get(self, url, **kwargs):
        self.calls.append((url, self.clock.now))
        self.clock.now += self.duration
        if self.handler is not None:
            resp = self.handler(url)
            if resp is not None:
                return resp
        if url.startswith(LZH_BASE):
            return FakeResponse(url, content=LZH_BODY)
        return FakeResponse(url, content=b"<html>" + url.encode() + b"</html>")

    def urls(self, prefix: str) -> list[str]:
        return [u for u, _ in self.calls if u.startswith(prefix)]

    def starts(self, prefix: str) -> list[float]:
        return [t for u, t in self.calls if u.startswith(prefix)]


def make_cfg(tmp_path: Path, role: str = "exec"):
    cfg = load_config(EXAMPLE)
    return dataclasses.replace(
        cfg,
        role=role,
        data_dir=tmp_path / "data",
        sevenzip=Path("unused-7z"),
        lzh_base=LZH_BASE,
        race_page_base=PAGE_BASE,
    )


def install_fake_extract(monkeypatch, fail_names=()):
    """7z を呼ばず、LZH と同じフォルダに B / K の TXT を置く。"""

    def fake(sevenzip, lzh_file, out_dir):
        if lzh_file.name in fail_names:
            raise ExtractError(f"7z が終了コード 2: {lzh_file}")
        kind = lzh_file.name[0]
        txt = Path(out_dir) / f"{kind.upper()}{lzh_file.name[1:7]}.TXT"
        txt.write_bytes((B_TEXT if kind == "b" else K_TEXT).encode("cp932"))
        return [txt]

    monkeypatch.setattr(precheck, "extract_lzh", fake)


def run(cfg, dates, session, clock, **kw):
    return run_precheck(cfg, dates, session=session, clock=clock.monotonic, sleep=clock.sleep, **kw)


def read_summary(cfg) -> dict:
    files = sorted((cfg.data_dir / "raw" / "precheck").glob("precheck_*.json"))
    assert files
    return json.loads(files[-1].read_text(encoding="utf-8"))


def gaps(times: list[float]) -> list[float]:
    return [b - a for a, b in zip(times, times[1:], strict=False)]


# --- 純粋関数 ---


def test_page_url_and_path(tmp_path):
    d = dt.date(2024, 1, 5)
    assert (
        page_url(PAGE_BASE, "odds", "03", 12, d) == f"{PAGE_BASE}/oddstf?rno=12&jcd=03&hd=20240105"
    )
    assert (
        page_url(PAGE_BASE + "/", "beforeinfo", "24", 1, d)
        == f"{PAGE_BASE}/beforeinfo?rno=1&jcd=24&hd=20240105"
    )
    assert page_path(tmp_path, "odds", "03", 12, d) == (
        tmp_path / "raw" / "pages" / "odds" / "20240105" / "03_12.html"
    )


def test_venues_from_b_text_sorted_unique_and_ignores_k():
    text = "STARTB\r\n24BBGN\r\nx\r\n24BEND\r\n03BBGN\r\n04BBGN\r\n03BBGN\r\n03KBGN\r\n05KBGN\r\n"
    assert venues_from_b_text(text) == ["03", "04", "24"]


def test_venues_from_b_text_normalizes_fullwidth_and_needs_line_start():
    text = "０９ＢＢＧＮ\r\n 12BBGN\r\nxx13BBGN\r\n07BBGN\r\n"
    assert venues_from_b_text(text) == ["07", "09"]


def test_venues_from_b_text_empty():
    assert venues_from_b_text("STARTB\r\n") == []


def test_check_past_dates_rejects_today_and_future():
    today = dt.date(2024, 1, 10)
    assert check_past_dates([dt.date(2024, 1, 9), dt.date(2024, 1, 9)], today) == [
        dt.date(2024, 1, 9)
    ]
    for bad in (today, today + dt.timedelta(days=1)):
        with pytest.raises(DateRejected) as ei:
            check_past_dates([dt.date(2024, 1, 9), bad], today)
        assert bad.isoformat() in str(ei.value)
        assert "過去日付" in str(ei.value)


# --- run_precheck：exec ---


def test_exec_saves_pages_and_summary(tmp_path, monkeypatch, capsys):
    install_fake_extract(monkeypatch)
    cfg = make_cfg(tmp_path)
    clock = FakeClock()
    session = FakeSession(clock)

    code = run(cfg, [DAYS[0]], session, clock)

    assert code == 0
    # リクエスト総数：LZH 2 + 2 場 × 2R × 2 種 = 8
    assert len(session.urls(LZH_BASE)) == 2
    assert len(session.urls(PAGE_BASE)) == 8
    assert session.urls(LZH_BASE) == [
        f"{LZH_BASE}/B/202401/b240105.lzh",
        f"{LZH_BASE}/K/202401/k240105.lzh",
    ]
    # 場は jcd の昇順で先頭 2 場（03, 04）、R は 1 と 12
    expected = {
        (kind, jcd, rno)
        for kind in ("odds", "beforeinfo")
        for jcd in ("03", "04")
        for rno in (1, 12)
    }
    saved = {
        (p.parts[-3], p.stem.split("_")[0], int(p.stem.split("_")[1]))
        for p in (cfg.data_dir / "raw" / "pages").rglob("*.html")
    }
    assert saved == expected
    f = cfg.data_dir / "raw" / "pages" / "odds" / "20240105" / "03_12.html"
    assert f.read_bytes() == (
        b"<html>" + f"{PAGE_BASE}/oddstf?rno=12&jcd=03&hd=20240105".encode() + b"</html>"
    )
    assert (cfg.data_dir / "raw" / "B" / "202401" / "b240105.lzh").read_bytes() == LZH_BODY
    assert (cfg.data_dir / "raw" / "K" / "202401" / "k240105.lzh").is_file()

    s = read_summary(cfg)
    assert s["role"] == "exec"
    assert s["pages_skipped"] is False
    assert s["ok"] is True
    (day,) = s["days"]
    assert day["date"] == "2024-01-05"
    assert day["venues"] == ["03", "04"]
    assert day["venue_source"] == "B marker"
    b, k = day["lzh"]
    assert (b["kind"], k["kind"]) == ("B", "K")
    assert b["url"] == f"{LZH_BASE}/B/202401/b240105.lzh"
    assert b["downloaded"] is True and b["error"] is None
    assert b["path"].endswith("b240105.lzh")
    assert [Path(p).name for p in b["extracted"]] == ["B240105.TXT"]
    assert len(day["pages"]) == 8
    p0 = day["pages"][0]
    assert p0["kind"] == "odds" and p0["jcd"] == "03" and p0["rno"] == 1
    assert p0["url"] == f"{PAGE_BASE}/oddstf?rno=1&jcd=03&hd=20240105"
    assert p0["status_code"] == 200
    assert p0["bytes"] == len(Path(p0["path"]).read_bytes())
    assert p0["final_url"] == p0["url"]
    assert p0["error"] is None

    out = capsys.readouterr().out
    assert "要約 JSON:" in out
    assert "tests/fixtures/real/" in out
    assert str(cfg.data_dir / "raw" / "B" / "202401" / "b240105.lzh") in out
    assert str(f) in out
    assert "ページを飛ばした" not in out


def test_jcd_rno_max_venues_options(tmp_path, monkeypatch):
    install_fake_extract(monkeypatch)
    cfg = make_cfg(tmp_path)
    clock = FakeClock()
    session = FakeSession(clock)

    run(cfg, [DAYS[0]], session, clock, jcds=["19"], rnos=[5])
    (day,) = read_summary(cfg)["days"]
    assert day["venues"] == ["19"] and day["venue_source"] == "--jcd"
    assert len(session.urls(PAGE_BASE)) == 2  # 1 場 × 1R × 2 種

    session2 = FakeSession(clock)
    run(cfg, [DAYS[1]], session2, clock, max_venues=3, rnos=[1])
    assert len(session2.urls(PAGE_BASE)) == 6  # 3 場 × 1R × 2 種
    assert {u.split("jcd=")[1][:2] for u in session2.urls(PAGE_BASE)} == {"03", "04", "23"}


def test_multi_date_intervals_hold_across_dates_with_one_fetcher(tmp_path, monkeypatch):
    install_fake_extract(monkeypatch)
    cfg = make_cfg(tmp_path)
    clock = FakeClock()
    session = FakeSession(clock, duration=0.5)
    created: list[int] = []
    orig = Fetcher.from_config
    monkeypatch.setattr(
        Fetcher,
        "from_config",
        staticmethod(lambda c, **kw: created.append(1) or orig(c, **kw)),
    )

    code = run(cfg, DAYS, session, clock)

    assert code == 0
    assert created == [1]  # Fetcher は全日付・全種別で 1 つ
    lzh = session.starts(LZH_BASE)
    pages = session.starts(PAGE_BASE)
    assert len(lzh) == 6 and len(pages) == 24
    assert all(g >= 2.0 for g in gaps(lzh)), gaps(lzh)
    assert all(g >= 3.0 for g in gaps(pages)), gaps(pages)
    assert [d["date"] for d in read_summary(cfg)["days"]] == [d.isoformat() for d in DAYS]


def test_rerun_skips_downloaded_lzh_and_force_refetches(tmp_path, monkeypatch):
    install_fake_extract(monkeypatch)
    cfg = make_cfg(tmp_path)
    clock = FakeClock()
    s1 = FakeSession(clock)
    run(cfg, [DAYS[0]], s1, clock, jcds=["01"], rnos=[1])
    assert len(s1.urls(LZH_BASE)) == 2

    s2 = FakeSession(clock)
    run(cfg, [DAYS[0]], s2, clock, jcds=["01"], rnos=[1])
    assert s2.urls(LZH_BASE) == []
    assert len(s2.urls(PAGE_BASE)) == 2  # ページは毎回取り直す
    b = read_summary(cfg)["days"][0]["lzh"][0]
    assert b["downloaded"] is False and b["error"] is None

    s3 = FakeSession(clock)
    run(cfg, [DAYS[0]], s3, clock, jcds=["01"], rnos=[1], force=True)
    assert len(s3.urls(LZH_BASE)) == 2


def test_summary_file_not_overwritten_in_same_second(tmp_path, monkeypatch):
    install_fake_extract(monkeypatch)
    cfg = make_cfg(tmp_path, role="dev")
    clock = FakeClock()
    fixed = dt.datetime(2024, 2, 1, 12, 0, 0)
    for _ in range(2):
        run(cfg, [DAYS[0]], FakeSession(clock), clock, now=lambda: fixed)
    names = sorted(p.name for p in (cfg.data_dir / "raw" / "precheck").iterdir())
    assert names == ["precheck_20240201_120000.json", "precheck_20240201_120000_1.json"]


# --- dev ---


def test_dev_role_never_requests_pages(tmp_path, monkeypatch, capsys):
    install_fake_extract(monkeypatch)

    def boom(self, url):
        raise AssertionError("dev でページ取得が呼ばれた")

    monkeypatch.setattr(Fetcher, "get_page", boom)
    cfg = make_cfg(tmp_path, role="dev")
    clock = FakeClock()
    session = FakeSession(clock)

    code = run(cfg, DAYS[:2], session, clock)

    assert code == 0
    # セッションに来た全 URL が LZH のもの。ページのベース URL は 1 件も無い
    assert session.calls
    assert not any(cfg.race_page_base in u for u, _ in session.calls)
    assert all(u.startswith(cfg.lzh_base) for u, _ in session.calls)
    assert len(session.calls) == 4
    # ページの保存ファイルが 1 つも無い
    assert not (cfg.data_dir / "raw" / "pages").exists()
    assert list(cfg.data_dir.rglob("*.html")) == []
    # 要約 JSON にページを飛ばした旨がある
    s = read_summary(cfg)
    assert s["role"] == "dev"
    assert s["pages_skipped"] is True
    assert "dev" in s["pages_skipped_reason"]
    assert all(d["pages_skipped"] is True and d["pages"] == [] for d in s["days"])
    assert s["days"][0]["venues"] == ["03", "04"]  # 場の決定までは行う
    out = capsys.readouterr().out
    assert "ページを飛ばした" in out
    assert "dev" in out
    # LZH は案内に出る
    assert str(cfg.data_dir / "raw" / "B" / "202401" / "b240105.lzh") in out


# --- エラーでも落ちない ---


def test_download_error_recorded_and_next_date_continues(tmp_path, monkeypatch, capsys):
    install_fake_extract(monkeypatch)
    cfg = make_cfg(tmp_path)
    clock = FakeClock()

    def handler(url):
        if "b240105" in url:
            return FakeResponse(url, status_code=404, content=b"not found")
        if "k240106" in url:
            raise requests.ConnectionError("down")
        return None

    session = FakeSession(clock, handler=handler)
    code = run(cfg, DAYS[:2], session, clock, jcds=["01"], rnos=[1])

    assert code == 1
    s = read_summary(cfg)
    assert s["ok"] is False
    d1, d2 = s["days"]
    assert "404" in d1["lzh"][0]["error"] and d1["lzh"][0]["error_type"] == "DownloadError"
    assert d1["lzh"][1]["error"] is None
    assert "ConnectionError" in d2["lzh"][1]["error"]
    assert len(session.urls(LZH_BASE)) == 4  # 失敗しても次へ進む
    assert not (cfg.data_dir / "raw" / "B" / "202401" / "b240105.lzh").exists()
    assert len(session.urls(PAGE_BASE)) == 4  # --jcd があるのでページは取る
    out = capsys.readouterr().out
    assert "エラー" in out
    assert "--force" not in out  # ExtractError ではないので案内しない


def test_extract_error_recorded_with_force_hint(tmp_path, monkeypatch, capsys):
    install_fake_extract(monkeypatch, fail_names=("b240105.lzh",))
    cfg = make_cfg(tmp_path)
    clock = FakeClock()
    session = FakeSession(clock)

    code = run(cfg, DAYS[:2], session, clock, max_venues=1, rnos=[1])

    assert code == 1
    d1, d2 = read_summary(cfg)["days"]
    assert d1["lzh"][0]["error_type"] == "ExtractError"
    assert d1["lzh"][0]["downloaded"] is True
    assert d1["venues"] == []
    assert any("B が使えない" in e for e in d1["errors"])
    assert d1["pages"] == []
    assert d2["venues"] == ["03"] and len(d2["pages"]) == 2  # 次の日は進む
    out = capsys.readouterr().out
    assert "--force" in out
    assert "--date 2024-01-05" in out
    # 解凍に失敗した B はサンプル案内に出ない。成功した K と次の日の B は出る
    assert "->  tests/fixtures/real/lzh/b240105.lzh" not in out
    assert "->  tests/fixtures/real/lzh/k240105.lzh" in out
    assert "->  tests/fixtures/real/lzh/b240106.lzh" in out


def test_no_marker_in_b_is_error(tmp_path, monkeypatch):
    def fake(sevenzip, lzh_file, out_dir):
        txt = Path(out_dir) / "B240105.TXT"
        txt.write_bytes(b"STARTB\r\n")
        return [txt]

    monkeypatch.setattr(precheck, "extract_lzh", fake)
    cfg = make_cfg(tmp_path)
    clock = FakeClock()
    code = run(cfg, [DAYS[0]], FakeSession(clock), clock)
    assert code == 1
    (day,) = read_summary(cfg)["days"]
    assert any("マーカー" in e for e in day["errors"])


def test_sevenzip_missing_is_recorded(tmp_path):
    cfg = make_cfg(tmp_path)  # 実在しない 7z、extract は本物
    clock = FakeClock()
    code = run(cfg, [DAYS[0]], FakeSession(clock), clock, jcds=["01"], rnos=[1])
    assert code == 1
    (day,) = read_summary(cfg)["days"]
    assert day["lzh"][0]["error_type"] == "SevenZipNotFound"


def test_page_errors_recorded_and_others_saved(tmp_path, monkeypatch):
    install_fake_extract(monkeypatch)
    cfg = make_cfg(tmp_path)
    clock = FakeClock()

    def handler(url):
        if "oddstf" in url and "jcd=03" in url and "rno=1&" in url:
            raise requests.ConnectTimeout("timeout")
        if "beforeinfo" in url and "jcd=04" in url and "rno=12" in url:
            return FakeResponse(url, status_code=503, content=b"busy")
        return None

    session = FakeSession(clock, handler=handler)
    code = run(cfg, [DAYS[0]], session, clock)

    assert code == 1
    assert len(session.urls(PAGE_BASE)) == 8  # 例外でも残りは続ける
    (day,) = read_summary(cfg)["days"]
    by_key = {(p["kind"], p["jcd"], p["rno"]): p for p in day["pages"]}
    timeout = by_key[("odds", "03", 1)]
    assert "ConnectTimeout" in timeout["error"] and timeout["path"] is None
    assert timeout["status_code"] is None
    busy = by_key[("beforeinfo", "04", 12)]
    assert busy["status_code"] == 503 and busy["error"] == "HTTP 503"
    assert busy["bytes"] == 4 and busy["path"] is None  # 200 以外は保存しない
    assert not page_path(cfg.data_dir, "beforeinfo", "04", 12, DAYS[0]).exists()
    assert sum(1 for p in day["pages"] if p["path"]) == 6


def test_page_redirect_final_url_recorded(tmp_path, monkeypatch):
    install_fake_extract(monkeypatch)
    cfg = make_cfg(tmp_path)
    clock = FakeClock()

    def handler(url):
        if url.startswith(PAGE_BASE):
            r = FakeResponse(url, content=b"x")
            r.url = "https://page.example.invalid/moved"
            return r
        return None

    run(cfg, [DAYS[0]], FakeSession(clock, handler=handler), clock, jcds=["01"], rnos=[1])
    (day,) = read_summary(cfg)["days"]
    assert day["pages"][0]["final_url"] == "https://page.example.invalid/moved"
    assert day["pages"][0]["url"] != day["pages"][0]["final_url"]


# --- 7z が実在するときの結合（実際に解凍する） ---


def test_end_to_end_with_real_sevenzip(tmp_path, sevenzip_exe):
    cfg = dataclasses.replace(make_cfg(tmp_path), sevenzip=sevenzip_exe)
    b = build_lzh({"B240105.TXT": B_TEXT.encode("cp932")})
    k = build_lzh({"K240105.TXT": K_TEXT.encode("cp932")})
    clock = FakeClock()

    def handler(url):
        if url.startswith(LZH_BASE):
            return FakeResponse(url, content=b if "/B/" in url else k)
        return None

    session = FakeSession(clock, handler=handler)
    code = run(cfg, [DAYS[0]], session, clock, rnos=[1])
    assert code == 0
    assert (cfg.data_dir / "raw" / "B" / "202401" / "B240105.TXT").is_file()
    assert (cfg.data_dir / "raw" / "K" / "202401" / "K240105.TXT").is_file()
    (day,) = read_summary(cfg)["days"]
    assert day["venues"] == ["03", "04"]


@pytest.mark.skipif(
    not (REAL_LZH_DIR / "b261001.lzh").is_file(), reason="tests/fixtures/real/lzh/ に実 B が無い"
)
def test_real_b_file_venue_detection(tmp_path, sevenzip_exe):
    from boatev.lzh import extract_lzh

    files = extract_lzh(sevenzip_exe, REAL_LZH_DIR / "b261001.lzh", tmp_path)
    text = files[0].read_bytes().decode("cp932", errors="replace")
    assert venues_from_b_text(text) == [
        "03", "04", "06", "07", "09", "12", "13", "14", "15", "16", "19", "22", "23", "24",
    ]  # fmt: skip


# --- CLI ---


@pytest.fixture
def cli_cfg(tmp_path, monkeypatch):
    """カレントディレクトリに config.yaml がある状態。run_precheck は記録するだけ。"""
    shutil.copy(EXAMPLE, tmp_path / "config.yaml")
    monkeypatch.chdir(tmp_path)
    calls: list[tuple] = []

    def fake_run(cfg, dates, **kw):
        calls.append((cfg, dates, kw))
        return 0

    monkeypatch.setattr(precheck, "run_precheck", fake_run)
    return calls


def test_cli_passes_options(cli_cfg, tmp_path):
    code = main(
        [
            "precheck",
            "--date", "2024-01-05",
            "--date", "2024-01-06",
            "--date", "2024-01-05",
            "--jcd", "1,02",
            "--rno", "1,12,6",
            "--max-venues", "3",
            "--force",
        ]
    )  # fmt: skip
    assert code == 0
    ((cfg, dates, kw),) = cli_cfg
    assert dates == [dt.date(2024, 1, 5), dt.date(2024, 1, 6)]
    assert kw == {"jcds": ["01", "02"], "rnos": [1, 12, 6], "max_venues": 3, "force": True}
    assert cfg.data_dir == (tmp_path / "data").resolve()  # カレントの config.yaml を既定で読む


def test_cli_defaults(cli_cfg):
    assert main(["precheck", "--date", "2024-01-05"]) == 0
    ((_, _, kw),) = cli_cfg
    assert kw == {"jcds": None, "rnos": [1, 12], "max_venues": 2, "force": False}


def test_cli_config_option(cli_cfg, tmp_path):
    other = tmp_path / "sub" / "my.yaml"
    other.parent.mkdir()
    other.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    assert main(["precheck", "--date", "2024-01-05", "--config", str(other)]) == 0
    ((cfg, _, _),) = cli_cfg
    assert cfg.data_dir == (other.parent / "data").resolve()


def test_cli_missing_config_exit_2(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)  # config.yaml が無い
    assert main(["precheck", "--date", "2024-01-05"]) == 2
    assert "設定" in capsys.readouterr().err


@pytest.mark.parametrize("offset", [0, 1, 30])
def test_cli_rejects_today_and_future(cli_cfg, capsys, offset):
    day = dt.date.today() + dt.timedelta(days=offset)
    assert main(["precheck", "--date", "2024-01-05", "--date", day.isoformat()]) == 2
    err = capsys.readouterr().err
    assert day.isoformat() in err and "過去日付" in err
    assert cli_cfg == []  # 何も実行しない


@pytest.mark.parametrize(
    "argv",
    [
        ["precheck"],
        ["precheck", "--date", "2024-13-01"],
        ["precheck", "--date", "yesterday"],
        ["precheck", "--date", "2024-01-05", "--jcd", "25"],
        ["precheck", "--date", "2024-01-05", "--jcd", "0"],
        ["precheck", "--date", "2024-01-05", "--jcd", "a"],
        ["precheck", "--date", "2024-01-05", "--rno", "13"],
        ["precheck", "--date", "2024-01-05", "--max-venues", "0"],
        ["precheck", "--date", "2024-01-05", "--forcee"],
    ],
)
def test_cli_bad_arguments_exit_2(cli_cfg, argv):
    with pytest.raises(SystemExit) as e:
        main(argv)
    assert e.value.code == 2
    assert cli_cfg == []


def test_cli_output_survives_cp932_stdout(cli_cfg, monkeypatch):
    """stdout・stderr が cp932 でも、表せない文字（U+FFFD など）を含む出力で落ちない。"""

    def fake_run(cfg, dates, **kw):
        print("エラー: 7z の出力 � ☃")
        print("stderr 側", file=sys.stderr)
        print("�", file=sys.stderr)
        return 1

    monkeypatch.setattr(precheck, "run_precheck", fake_run)
    out_raw, err_raw = io.BytesIO(), io.BytesIO()
    out = io.TextIOWrapper(out_raw, encoding="cp932", errors="strict", write_through=True)
    err = io.TextIOWrapper(err_raw, encoding="cp932", errors="strict", write_through=True)
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)

    assert main(["precheck", "--date", "2024-01-05"]) == 1
    assert out_raw.getvalue().decode("cp932").startswith("エラー: 7z の出力 ")
    assert b"?" in out_raw.getvalue()
    assert "stderr 側" in err_raw.getvalue().decode("cp932")
