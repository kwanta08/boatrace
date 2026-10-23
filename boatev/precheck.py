"""`boatev precheck`：取得できるデータの事前確認（spec「実装順序」ステップ 2）。

日付ごとに B・K の LZH を取得して解凍し、開催場を決め、machine.role が exec のときだけ
単勝オッズ・直前情報ページを数件取得して生の HTML を保存する。dev ではページを取得しない
（開発PCからはオッズ・直前情報ページに一切アクセスしない）。
結果は `data/raw/precheck/precheck_<実行時刻>.json` に残す。

Fetcher は 1 回の実行で 1 つだけ作り、全日付・全種別で使い回す。間隔（LZH 2 秒、ページ 3 秒）を
日付をまたいでも守るため。LZH の取得・解凍の失敗では落ちず、その日の要約にエラーを残して次へ進む。
"""

from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import requests

from boatev.config import Config
from boatev.fetch import Fetcher, PageFetchForbidden
from boatev.lzh import (
    KINDS,
    ExtractError,
    LzhError,
    download_lzh,
    extract_lzh,
    lzh_path,
    lzh_url,
)

DEFAULT_RNOS = (1, 12)
DEFAULT_MAX_VENUES = 2
# ページ種別 → URL のパス部分（{race_page_base}/<path>?rno=..&jcd=..&hd=..）
PAGE_PATHS = {"odds": "oddstf", "beforeinfo": "beforeinfo"}
# 場の開始マーカー。NFKC で正規化した本文の行頭にある `NNBBGN`（K は `NNKBGN`）
_B_VENUE_MARKER = re.compile(r"^(\d{2})BBGN", re.MULTILINE)
_SAMPLE_DIR = "tests/fixtures/real"

EXIT_OK = 0
EXIT_ERRORS = 1


class DateRejected(ValueError):
    """未来日・今日の日付（過去日付ではない）。"""


def check_past_dates(dates: Sequence[dt.date], today: dt.date) -> list[dt.date]:
    """今日より前の日付だけを許す。重複は順序を保って 1 つにする。"""
    bad = [d for d in dates if d >= today]
    if bad:
        listed = ", ".join(d.isoformat() for d in bad)
        raise DateRejected(
            f"過去日付ではありません（今日 {today.isoformat()} 以降）: {listed}"
            "。今日・未来の日付は取得できないので指定できません"
        )
    return list(dict.fromkeys(dates))


def venues_from_b_text(text: str) -> list[str]:
    """B ファイル本文から、場の開始マーカー `NNBBGN` の jcd（2 桁）を昇順・重複なしで返す。

    全角が混ざることがあるので、NFKC で正規化してから探す。
    """
    normalized = unicodedata.normalize("NFKC", text)
    return sorted(set(_B_VENUE_MARKER.findall(normalized)))


def page_url(race_page_base: str, kind: str, jcd: str, rno: int, date: dt.date) -> str:
    return f"{race_page_base.rstrip('/')}/{PAGE_PATHS[kind]}?rno={rno}&jcd={jcd}&hd={date:%Y%m%d}"


def page_path(data_dir: Path, kind: str, jcd: str, rno: int, date: dt.date) -> Path:
    """保存先 `data_dir/raw/pages/<kind>/YYYYMMDD/<jcd>_<rno>.html`。"""
    return Path(data_dir) / "raw" / "pages" / kind / f"{date:%Y%m%d}" / f"{jcd}_{rno}.html"


def _err(e: BaseException) -> str:
    return f"{type(e).__name__}: {e}"


def _read_b_venues(files: Sequence[Path]) -> list[str]:
    found: set[str] = set()
    for f in files:
        if f.suffix.lower() != ".txt":
            continue
        text = f.read_bytes().decode("cp932", errors="replace")
        found.update(venues_from_b_text(text))
    return sorted(found)


def _process_lzh(
    fetcher: Fetcher, cfg: Config, kind: str, date: dt.date, force: bool
) -> tuple[dict[str, Any], list[Path]]:
    """LZH 1 件の取得と解凍。失敗は要約のエントリに残し、例外は外に出さない。"""
    entry: dict[str, Any] = {
        "kind": kind,
        "url": lzh_url(kind, date, cfg.lzh_base),
        "path": str(lzh_path(cfg.data_dir, kind, date)),
        "downloaded": False,
        "extracted": [],
        "error": None,
        "error_type": None,
    }
    extracted: list[Path] = []
    try:
        res = download_lzh(fetcher, cfg.lzh_base, cfg.data_dir, kind, date, force=force)
        entry["downloaded"] = res.downloaded
        extracted = extract_lzh(cfg.sevenzip, res.path, res.path.parent)
        entry["extracted"] = [str(p) for p in extracted]
    except (LzhError, requests.RequestException, OSError) as e:
        entry["error"] = _err(e)
        entry["error_type"] = type(e).__name__
    return entry, extracted


def _fetch_page(
    fetcher: Fetcher, cfg: Config, kind: str, jcd: str, rno: int, date: dt.date
) -> dict[str, Any]:
    """ページ 1 件の取得と保存。HTTP 200 のときだけ生バイトで保存する（上書き）。"""
    url = page_url(cfg.race_page_base, kind, jcd, rno, date)
    entry: dict[str, Any] = {
        "kind": kind,
        "jcd": jcd,
        "rno": rno,
        "url": url,
        "status_code": None,
        "bytes": None,
        "path": None,
        "final_url": None,
        "error": None,
    }
    try:
        resp = fetcher.get_page(url)
        entry["status_code"] = resp.status_code
        entry["final_url"] = str(getattr(resp, "url", url))
        body = resp.content
        entry["bytes"] = len(body)
        if resp.status_code != 200:
            entry["error"] = f"HTTP {resp.status_code}"
        else:
            dest = page_path(cfg.data_dir, kind, jcd, rno, date)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(body)
            entry["path"] = str(dest)
    except (requests.RequestException, PageFetchForbidden, OSError) as e:
        entry["error"] = _err(e)
    return entry


def _summary_path(data_dir: Path, now: dt.datetime) -> Path:
    base = Path(data_dir) / "raw" / "precheck"
    base.mkdir(parents=True, exist_ok=True)
    stem = f"precheck_{now:%Y%m%d_%H%M%S}"
    p = base / f"{stem}.json"
    n = 1
    while p.exists():  # 同じ秒の再実行でも前の要約を上書きしない
        p = base / f"{stem}_{n}.json"
        n += 1
    return p


def run_precheck(
    cfg: Config,
    dates: Sequence[dt.date],
    *,
    jcds: Sequence[str] | None = None,
    rnos: Sequence[int] = DEFAULT_RNOS,
    max_venues: int = DEFAULT_MAX_VENUES,
    force: bool = False,
    session: Any = None,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    now: Callable[[], dt.datetime] = dt.datetime.now,
) -> int:
    """precheck を実行し、標準出力に結果を出して終了コードを返す（全部成功 0、エラーあり 1）。

    dates は過去日付であること（`check_past_dates` で確かめ済みとする）。
    session・clock・sleep はテスト用の注入口（Fetcher は 1 つだけ作って使い回す）。
    """
    kwargs: dict[str, Any] = {"session": session}
    if clock is not None:
        kwargs["clock"] = clock
    if sleep is not None:
        kwargs["sleep"] = sleep
    fetcher = Fetcher.from_config(cfg, **kwargs)

    started = now()
    skip_pages = cfg.role != "exec"
    skip_reason = (
        f"machine.role={cfg.role!r} のためオッズ・直前情報ページの取得を飛ばした"
        "（開発PCからはアクセスしない。実行PCで role: exec にして実行する）"
        if skip_pages
        else None
    )
    days: list[dict[str, Any]] = []
    sample_lzh: list[Path] = []
    sample_pages: list[Path] = []
    force_hints: list[str] = []
    error_lines: list[str] = []

    for date in dates:
        day: dict[str, Any] = {
            "date": date.isoformat(),
            "lzh": [],
            "venues": [],
            "venue_source": None,
            "pages": [],
            "pages_skipped": skip_pages,
            "errors": [],
        }
        b_files: list[Path] = []
        b_failed = False
        for kind in KINDS:
            entry, extracted = _process_lzh(fetcher, cfg, kind, date, force)
            day["lzh"].append(entry)
            if kind == "B":
                b_files = extracted
                b_failed = entry["error"] is not None
            if entry["error"] is not None:
                day["errors"].append(f"{kind} LZH: {entry['error']}")
                if entry["error_type"] == ExtractError.__name__:
                    force_hints.append(
                        f"{date.isoformat()} {kind} の解凍に失敗した。"
                        f"取り直すには: boatev precheck --date {date.isoformat()} --force"
                    )
            # 取得・解凍とも成功したものだけ案内する（壊れた LZH を fixtures に置くと赤になる）
            if entry["error"] is None and Path(entry["path"]).is_file():
                sample_lzh.append(Path(entry["path"]))

        if jcds:
            venues = list(jcds)
            day["venue_source"] = "--jcd"
        else:
            venues = _read_b_venues(b_files)[:max_venues]
            day["venue_source"] = "B marker"
            if not venues:
                reason = (
                    "B が使えないため開催場を決められない"
                    if b_failed
                    else "B に場の開始マーカー（NNBBGN）が無い"
                )
                day["errors"].append(reason)
        day["venues"] = venues

        if not skip_pages:
            for jcd in venues:
                for rno in rnos:
                    for kind in PAGE_PATHS:
                        page = _fetch_page(fetcher, cfg, kind, jcd, rno, date)
                        day["pages"].append(page)
                        if page["error"] is not None:
                            day["errors"].append(f"{kind} {jcd}_{rno}: {page['error']}")
                        if page["path"] is not None:
                            sample_pages.append(Path(page["path"]))

        error_lines.extend(f"{date.isoformat()}: {m}" for m in day["errors"])
        days.append(day)

    summary = {
        "started_at": started.isoformat(timespec="seconds"),
        "role": cfg.role,
        "options": {
            "dates": [d.isoformat() for d in dates],
            "jcd": list(jcds) if jcds else None,
            "rno": list(rnos),
            "max_venues": max_venues,
            "force": force,
        },
        "pages_skipped": skip_pages,
        "pages_skipped_reason": skip_reason,
        "ok": not error_lines,
        "days": days,
    }
    out_path = _summary_path(cfg.data_dir, started)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"要約 JSON: {out_path}")
    if skip_reason:
        print(f"ページを飛ばした: {skip_reason}")
    if error_lines:
        print(f"エラー {len(error_lines)} 件:")
        for line in error_lines:
            print(f"  {line}")
    for hint in force_hints:
        print(hint)
    print(f"テスト用サンプルとして {_SAMPLE_DIR}/ に持ってくるファイル:")
    if not sample_lzh and not sample_pages:
        print("  （なし）")
    for p in sample_lzh:
        print(f"  {p}  ->  {_SAMPLE_DIR}/lzh/{p.name}")
    for p in sample_pages:
        print(f"  {p}  ->  {_SAMPLE_DIR}/pages/{p.parent.parent.name}/{p.parent.name}/{p.name}")
    return EXIT_ERRORS if error_lines else EXIT_OK
