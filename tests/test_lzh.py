import datetime as dt
import subprocess
from pathlib import Path

import pytest
from lzh_builder import build_lzh, crc16

from boatev import lzh
from boatev.config import load_config
from boatev.lzh import (
    DownloadError,
    ExtractError,
    SevenZipNotFound,
    download_lzh,
    extract_lzh,
    lzh_path,
    lzh_url,
)

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "config.example.yaml"
REAL_LZH_DIR = ROOT / "tests" / "fixtures" / "real" / "lzh"

BASE = "https://example.invalid/od2"
DAY = dt.date(2024, 1, 5)


# 先頭 2 バイトのあとに圧縮方式 -lh5- が来る、LZH らしい本文
LZH_BODY = b"\x20\x00-lh5-body"


class FakeResponse:
    def __init__(self, status_code=200, content=LZH_BODY):
        self.status_code = status_code
        self.content = content


class FakeFetcher:
    def __init__(self, response=None):
        self.response = response or FakeResponse()
        self.urls: list[str] = []

    def get_lzh(self, url):
        self.urls.append(url)
        return self.response


# --- URL・保存先 ---


def test_url_b_and_k():
    assert lzh_url("B", DAY, BASE) == f"{BASE}/B/202401/b240105.lzh"
    assert lzh_url("K", DAY, BASE) == f"{BASE}/K/202401/k240105.lzh"


def test_url_base_is_required():
    with pytest.raises(TypeError):
        lzh_url("B", DAY)  # type: ignore[call-arg]


def test_url_uses_config_base_without_double_slash():
    cfg = load_config(EXAMPLE)
    assert lzh_url("B", DAY, cfg.lzh_base) == "https://www1.mbrace.or.jp/od2/B/202401/b240105.lzh"
    assert lzh_url("K", DAY, cfg.lzh_base + "/") == lzh_url("K", DAY, cfg.lzh_base)


def test_url_zero_pads_and_two_digit_year():
    assert lzh_url("B", dt.date(2009, 3, 1), BASE) == f"{BASE}/B/200903/b090301.lzh"


def test_bad_kind():
    with pytest.raises(ValueError):
        lzh_url("X", DAY, BASE)
    with pytest.raises(ValueError):
        lzh_path(Path("data"), "b", DAY)


def test_path_layout(tmp_path):
    assert lzh_path(tmp_path, "B", DAY) == tmp_path / "raw" / "B" / "202401" / "b240105.lzh"
    assert lzh_path(tmp_path, "K", DAY) == tmp_path / "raw" / "K" / "202401" / "k240105.lzh"


# --- download ---


def test_download_saves_file(tmp_path):
    f = FakeFetcher(FakeResponse(content=LZH_BODY))
    r = download_lzh(f, BASE, tmp_path, "B", DAY)
    assert r.downloaded is True
    assert r.path == lzh_path(tmp_path, "B", DAY)
    assert r.path.read_bytes() == LZH_BODY
    assert f.urls == [f"{BASE}/B/202401/b240105.lzh"]
    assert r.url == f.urls[0]
    # 一時ファイルは残らない
    assert [p.name for p in r.path.parent.iterdir()] == ["b240105.lzh"]


def test_download_skips_existing_and_force_refetches(tmp_path):
    new = b"\x20\x00-lh0-new"
    f = FakeFetcher(FakeResponse(content=new))
    dest = lzh_path(tmp_path, "K", DAY)
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"old")

    r = download_lzh(f, BASE, tmp_path, "K", DAY)
    assert r.downloaded is False
    assert f.urls == []
    assert dest.read_bytes() == b"old"

    r = download_lzh(f, BASE, tmp_path, "K", DAY, force=True)
    assert r.downloaded is True
    assert len(f.urls) == 1
    assert dest.read_bytes() == new


@pytest.mark.parametrize("status", [404, 403, 500, 301, 204])
def test_download_non_200_raises_and_saves_nothing(tmp_path, status):
    f = FakeFetcher(FakeResponse(status_code=status, content=b"<html>error</html>"))
    with pytest.raises(DownloadError) as ei:
        download_lzh(f, BASE, tmp_path, "B", DAY)
    assert ei.value.status_code == status
    assert str(status) in str(ei.value)
    assert not lzh_path(tmp_path, "B", DAY).exists()
    assert not list(tmp_path.rglob("*.part"))


def test_download_empty_body_raises(tmp_path):
    f = FakeFetcher(FakeResponse(content=b""))
    with pytest.raises(DownloadError):
        download_lzh(f, BASE, tmp_path, "B", DAY)
    assert not lzh_path(tmp_path, "B", DAY).exists()


@pytest.mark.parametrize(
    "body",
    [
        b"<html><body>error</body></html>",  # HTTP 200 のエラーページ
        b"\x00\x00-lh5",  # 短すぎる
        b"\x00\x00-lh5x",  # 末尾が - でない
        b"\x00\x00-lz5-body",  # lh でない
        b"-lh5-body",  # オフセット 0（2 ではない）
        b"\x00\x00-lh-body",  # 方式の文字が無い
    ],
)
def test_download_non_lzh_body_raises_and_saves_nothing(tmp_path, body):
    f = FakeFetcher(FakeResponse(status_code=200, content=body))
    with pytest.raises(DownloadError) as ei:
        download_lzh(f, BASE, tmp_path, "B", DAY)
    assert ei.value.status_code == 200
    assert not lzh_path(tmp_path, "B", DAY).exists()
    assert not list(tmp_path.rglob("*.part"))


@pytest.mark.parametrize("method", [b"-lh0-", b"-lh5-", b"-lh6-", b"-lhd-"])
def test_download_accepts_lh_methods(tmp_path, method):
    body = b"\x00\x00" + method + b"rest"
    r = download_lzh(FakeFetcher(FakeResponse(content=body)), BASE, tmp_path, "B", DAY)
    assert r.path.read_bytes() == body


def test_non_lzh_force_refetch_keeps_existing_file(tmp_path):
    dest = lzh_path(tmp_path, "B", DAY)
    dest.parent.mkdir(parents=True)
    dest.write_bytes(LZH_BODY)
    f = FakeFetcher(FakeResponse(content=b"<html>maintenance</html>"))
    with pytest.raises(DownloadError):
        download_lzh(f, BASE, tmp_path, "B", DAY, force=True)
    assert dest.read_bytes() == LZH_BODY


def test_failed_force_refetch_keeps_existing_file(tmp_path):
    dest = lzh_path(tmp_path, "B", DAY)
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"old")
    f = FakeFetcher(FakeResponse(status_code=503))
    with pytest.raises(DownloadError):
        download_lzh(f, BASE, tmp_path, "B", DAY, force=True)
    assert dest.read_bytes() == b"old"


def test_write_failure_leaves_no_partial_file(tmp_path, monkeypatch):
    def boom(src, dst):
        raise OSError("disk")

    monkeypatch.setattr(lzh.os, "replace", boom)
    with pytest.raises(OSError, match="disk"):
        download_lzh(FakeFetcher(), BASE, tmp_path, "B", DAY)
    assert list(lzh_path(tmp_path, "B", DAY).parent.iterdir()) == []


def test_network_error_propagates_and_saves_nothing(tmp_path):
    class Down:
        def get_lzh(self, url):
            raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        download_lzh(Down(), BASE, tmp_path, "B", DAY)
    assert not lzh_path(tmp_path, "B", DAY).exists()


# --- extract（subprocess をモック） ---


def _fake_exe(tmp_path) -> Path:
    exe = tmp_path / "bin" / "fake7z.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    return exe


def _lzh_file(tmp_path) -> Path:
    p = tmp_path / "raw" / "B" / "202401" / "b240105.lzh"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"LZH")
    return p


def _install_fake_run(monkeypatch, files=None, returncode=0, stderr="", stdout=""):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        out = Path(next(a for a in cmd if a.startswith("-o"))[2:])
        for name, data in (files or {}).items():
            (out / name).parent.mkdir(parents=True, exist_ok=True)
            (out / name).write_bytes(data)
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(lzh.subprocess, "run", fake_run)
    return calls


def test_extract_passes_expected_arguments(tmp_path, monkeypatch):
    exe = _fake_exe(tmp_path)
    src = _lzh_file(tmp_path)
    calls = _install_fake_run(monkeypatch, {"B240105.TXT": b"data"})
    out = extract_lzh(exe, src, src.parent)

    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert cmd[:3] == [str(exe), "x", "-y"]
    assert cmd[-1] == str(src.resolve())
    assert [a for a in cmd if a.startswith("-o")] == [cmd[3]]
    assert kwargs["check"] is False
    assert kwargs["timeout"] > 0
    assert out == [src.parent / "B240105.TXT"]
    assert out[0].read_bytes() == b"data"


def test_extract_returns_only_extracted_files_when_dir_has_others(tmp_path, monkeypatch):
    exe = _fake_exe(tmp_path)
    src = _lzh_file(tmp_path)
    other = src.parent / "B240104.TXT"  # 別の日の解凍済みファイル
    other.write_bytes(b"other")
    _install_fake_run(monkeypatch, {"B240105.TXT": b"new"})
    out = extract_lzh(exe, src, src.parent)
    assert out == [src.parent / "B240105.TXT"]
    assert other.read_bytes() == b"other"
    assert src.read_bytes() == b"LZH"  # 元の LZH は残る
    assert sorted(p.name for p in src.parent.iterdir()) == [
        "B240104.TXT",
        "B240105.TXT",
        "b240105.lzh",
    ]  # 作業ディレクトリは残らない


def test_extract_overwrites_same_name_and_returns_it(tmp_path, monkeypatch):
    exe = _fake_exe(tmp_path)
    src = _lzh_file(tmp_path)
    (src.parent / "B240105.TXT").write_bytes(b"stale")
    _install_fake_run(monkeypatch, {"B240105.TXT": b"fresh"})
    out = extract_lzh(exe, src, src.parent)
    assert out == [src.parent / "B240105.TXT"]
    assert out[0].read_bytes() == b"fresh"


def test_extract_into_separate_dir(tmp_path, monkeypatch):
    exe = _fake_exe(tmp_path)
    src = _lzh_file(tmp_path)
    _install_fake_run(monkeypatch, {"a.txt": b"1", "sub/b.txt": b"2"})
    dest = tmp_path / "out" / "x"
    out = extract_lzh(exe, src, dest)
    assert out == sorted([dest / "a.txt", dest / "sub" / "b.txt"])
    assert (dest / "sub" / "b.txt").read_bytes() == b"2"


def test_extract_missing_sevenzip(tmp_path, monkeypatch):
    src = _lzh_file(tmp_path)
    calls = _install_fake_run(monkeypatch)
    with pytest.raises(SevenZipNotFound):
        extract_lzh(tmp_path / "nope" / "7z.exe", src, src.parent)
    assert calls == []


def test_extract_nonzero_exit_raises_with_stderr_and_places_nothing(tmp_path, monkeypatch):
    exe = _fake_exe(tmp_path)
    src = _lzh_file(tmp_path)
    _install_fake_run(
        monkeypatch, {"partial.TXT": b"x"}, returncode=2, stderr="ERROR: Data Error : b240105.lzh"
    )
    with pytest.raises(ExtractError) as ei:
        extract_lzh(exe, src, src.parent)
    assert "2" in str(ei.value)
    assert "Data Error" in str(ei.value)
    assert sorted(p.name for p in src.parent.iterdir()) == ["b240105.lzh"]


def test_extract_nothing_extracted_raises(tmp_path, monkeypatch):
    exe = _fake_exe(tmp_path)
    src = _lzh_file(tmp_path)
    _install_fake_run(monkeypatch, {})
    with pytest.raises(ExtractError):
        extract_lzh(exe, src, src.parent)


def test_extract_missing_lzh(tmp_path, monkeypatch):
    exe = _fake_exe(tmp_path)
    calls = _install_fake_run(monkeypatch)
    with pytest.raises(ExtractError):
        extract_lzh(exe, tmp_path / "none.lzh", tmp_path)
    assert calls == []


def test_extract_timeout_is_extract_error(tmp_path, monkeypatch):
    exe = _fake_exe(tmp_path)
    src = _lzh_file(tmp_path)

    def slow(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(lzh.subprocess, "run", slow)
    with pytest.raises(ExtractError):
        extract_lzh(exe, src, src.parent)
    assert sorted(p.name for p in src.parent.iterdir()) == ["b240105.lzh"]


def test_find_sevenzip_falls_back_to_path(tmp_path, monkeypatch):
    exe = _fake_exe(tmp_path)
    monkeypatch.setattr(lzh.shutil, "which", lambda name: str(exe) if name == "7zz" else None)
    assert lzh.find_sevenzip("7zz") == exe
    assert lzh.find_sevenzip("nothing") is None


# --- 結合テスト（7z が実在するときだけ） ---


def test_crc16_known_value():
    assert crc16(b"123456789") == 0xBB3D  # CRC-16/ARC のチェック値


def test_extract_synthetic_lh0(tmp_path, sevenzip_exe):
    body = "第01レース\r\n".encode("cp932") * 3
    src = tmp_path / "b240105.lzh"
    src.write_bytes(build_lzh({"B240105.TXT": body, "NOTE.TXT": b"hello"}))
    (tmp_path / "B240104.TXT").write_bytes(b"existing")

    out = extract_lzh(sevenzip_exe, src, tmp_path)

    assert out == sorted([tmp_path / "B240105.TXT", tmp_path / "NOTE.TXT"])
    assert (tmp_path / "B240105.TXT").read_bytes() == body
    assert (tmp_path / "NOTE.TXT").read_bytes() == b"hello"
    assert (tmp_path / "B240104.TXT").read_bytes() == b"existing"


def test_extract_corrupt_lzh_raises_for_real(tmp_path, sevenzip_exe):
    src = tmp_path / "b240105.lzh"
    src.write_bytes(b"this is not an lzh archive at all" * 4)
    with pytest.raises(ExtractError):
        extract_lzh(sevenzip_exe, src, tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["b240105.lzh"]


# --- 実ファイル（tests/fixtures/real/lzh/ に b*.lzh / k*.lzh があるときだけ） ---


def _real_lzh_files() -> list[Path]:
    if not REAL_LZH_DIR.is_dir():
        return []
    return sorted([*REAL_LZH_DIR.glob("b*.lzh"), *REAL_LZH_DIR.glob("k*.lzh")])


@pytest.mark.skipif(not _real_lzh_files(), reason="tests/fixtures/real/lzh/ に実 LZH が無い")
def test_extract_real_fixture(tmp_path, sevenzip_exe):
    files = _real_lzh_files()
    for i, f in enumerate(files):
        out_dir = tmp_path / str(i)
        out = extract_lzh(sevenzip_exe, f, out_dir)
        txts = [p for p in out if p.suffix.lower() == ".txt"]
        assert txts, f"TXT が解凍されていない: {f.name}"
        for t in txts:
            assert t.stat().st_size > 0, f"0 バイト: {t.name}"
