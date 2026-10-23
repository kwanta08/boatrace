"""LZH（番組表 B・競走成績 K）の取得と 7-Zip での解凍。

URL は `{lzh_base}/B/YYYYMM/bYYMMDD.lzh`、`{lzh_base}/K/YYYYMM/kYYMMDD.lzh`
（spec「データソース」）。
保存先は `data/raw/B/YYYYMM/bYYMMDD.lzh`、`data/raw/K/YYYYMM/kYYMMDD.lzh`。
解凍は 7-Zip を subprocess で呼ぶ（lhafile は使わない）。7z のパスは config から受け取り、
このモジュールには書かない。
"""

from __future__ import annotations

import contextlib
import datetime as dt
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boatev.fetch import Fetcher

KINDS = ("B", "K")
EXTRACT_TIMEOUT_SEC = 120.0
_STDERR_TAIL_CHARS = 500
# LZH のヘッダは、オフセット 2 から 5 バイトが圧縮方式（`-lh5-` など。`-lh` + 1 文字 + `-`）
_LZH_METHOD = re.compile(rb"-lh.-", re.DOTALL)


class LzhError(Exception):
    """LZH の取得・解凍の失敗の基底。"""


class DownloadError(LzhError):
    """HTTP ステータスが 200 以外、本文が空、または本文が LZH の形をしていない。"""

    def __init__(self, message: str, url: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.url = url
        self.status_code = status_code


class SevenZipNotFound(LzhError):
    """7z の実行ファイルが見つからない。"""


class ExtractError(LzhError):
    """7z の非 0 終了、タイムアウト、または何も解凍されなかった。"""


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    downloaded: bool  # False は取得済みで飛ばした
    url: str


def _check_kind(kind: str) -> str:
    if kind not in KINDS:
        raise ValueError(f"kind は {KINDS} のどちらか: {kind!r}")
    return kind


def lzh_filename(kind: str, date: dt.date) -> str:
    """`bYYMMDD.lzh` / `kYYMMDD.lzh`。"""
    return f"{_check_kind(kind).lower()}{date:%y%m%d}.lzh"


def lzh_url(kind: str, date: dt.date, base: str) -> str:
    """LZH の URL。base は config の urls.lzh_base（必須。コードに URL を直書きしない）。"""
    return f"{base.rstrip('/')}/{_check_kind(kind)}/{date:%Y%m}/{lzh_filename(kind, date)}"


def lzh_path(data_dir: Path, kind: str, date: dt.date) -> Path:
    """保存先 `data_dir/raw/<kind>/YYYYMM/<kind小文字>YYMMDD.lzh`。"""
    return Path(data_dir) / "raw" / _check_kind(kind) / f"{date:%Y%m}" / lzh_filename(kind, date)


def download_lzh(
    fetcher: Fetcher,
    base: str,
    data_dir: Path,
    kind: str,
    date: dt.date,
    *,
    force: bool = False,
) -> DownloadResult:
    """LZH 1 件を保存する。取得済みなら再取得しない（force=True で再取得）。

    HTTP 200 以外・空の本文・LZH の形でない本文（HTTP 200 のエラーページなど）は
    DownloadError で、保存しない。一時ファイルに書いてから置き換えるので、
    失敗しても壊れたファイルや（force 時の）既存ファイルの破損は残らない。
    """
    url = lzh_url(kind, date, base)
    dest = lzh_path(data_dir, kind, date)
    if dest.is_file() and not force:
        return DownloadResult(dest, False, url)

    resp = fetcher.get_lzh(url)
    if resp.status_code != 200:
        raise DownloadError(f"HTTP {resp.status_code}: {url}", url, resp.status_code)
    body = resp.content
    if not body:
        raise DownloadError(f"本文が空: {url}", url, resp.status_code)
    if not _LZH_METHOD.fullmatch(body[2:7]):
        raise DownloadError(
            f"本文が LZH ではない（オフセット 2 が -lh?- でない、{len(body)} バイト）: {url}",
            url,
            resp.status_code,
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.", suffix=".part")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(body)
        os.replace(tmp, dest)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    return DownloadResult(dest, True, url)


def find_sevenzip(sevenzip: str | Path) -> Path | None:
    """7z の実行ファイルを返す。ファイルとして実在すればそれ、無ければ PATH から探す。"""
    p = Path(sevenzip)
    if p.is_file():
        return p
    found = shutil.which(str(sevenzip))
    return Path(found) if found else None


def extract_lzh(sevenzip: str | Path, lzh_file: Path, out_dir: Path) -> list[Path]:
    """`7z x -y -o<dir> <lzh>` で解凍し、out_dir に置いたファイルのパス一覧（ソート済み）を返す。

    7z は out_dir 内の新しい作業ディレクトリに解凍させ、そこにあるファイルを out_dir へ
    移す。戻り値は作業ディレクトリの中身から決めるので、out_dir に既存のファイル
    （LZH 自身や他の日のファイル）があっても正しい。同名の既存ファイルは上書きする。
    7z の失敗時は out_dir に何も置かない。
    """
    exe = find_sevenzip(sevenzip)
    if exe is None:
        raise SevenZipNotFound(f"7-Zip が見つかりません（config の tools.sevenzip）: {sevenzip}")
    lzh_file = Path(lzh_file).resolve()
    if not lzh_file.is_file():
        raise ExtractError(f"LZH がありません: {lzh_file}")
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=out_dir, prefix=".extract-") as stage_name:
        stage = Path(stage_name)
        try:
            proc = subprocess.run(
                [str(exe), "x", "-y", f"-o{stage}", str(lzh_file)],
                check=False,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=EXTRACT_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired as e:
            raise ExtractError(f"7z がタイムアウト（{EXTRACT_TIMEOUT_SEC} 秒）: {lzh_file}") from e
        except OSError as e:
            raise ExtractError(f"7z を起動できません: {exe} ({e})") from e
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip()[-_STDERR_TAIL_CHARS:]
            raise ExtractError(f"7z が終了コード {proc.returncode}: {lzh_file}\n{tail}")

        extracted = sorted(p for p in stage.rglob("*") if p.is_file())
        if not extracted:
            raise ExtractError(f"解凍されたファイルがありません: {lzh_file}")
        placed: list[Path] = []
        for src in extracted:
            dest = out_dir / src.relative_to(stage)
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dest)
            placed.append(dest)
    return sorted(placed)
