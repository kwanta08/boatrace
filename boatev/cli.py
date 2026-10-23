"""boatev コマンド。precheck だけ実装済みで、ほかのサブコマンドは未実装スタブ。"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

COMMANDS: dict[str, str] = {
    "download": "番組表・成績の LZH を取得する",
    "parse": "LZH を解凍・パースして Parquet に保存する",
    "odds": "単勝オッズを取得する",
    "beforeinfo": "直前情報を取得する",
    "features": "特徴量テーブルを作成する",
    "train": "勝率モデルを学習し T・α・β を推定する",
    "backtest": "回収率レポートを出力する",
    "today": "当日の買い目候補を表示する",
    "precheck": "取得できるデータの事前確認をする",
}

EXIT_NOT_IMPLEMENTED = 2
EXIT_USAGE = 2
DEFAULT_CONFIG = Path("config.yaml")  # 既定はカレントディレクトリの config.yaml


def _date(s: str) -> dt.date:
    try:
        return dt.datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"YYYY-MM-DD の形式で指定する: {s!r}") from None


def _csv_ints(s: str, name: str, lo: int, hi: int) -> list[int]:
    try:
        values = [int(x) for x in s.split(",")]
    except ValueError:
        raise argparse.ArgumentTypeError(f"{name} は整数のカンマ区切り: {s!r}") from None
    if not values or any(not lo <= v <= hi for v in values):
        raise argparse.ArgumentTypeError(f"{name} は {lo}〜{hi} の整数: {s!r}")
    return list(dict.fromkeys(values))


def _jcds(s: str) -> list[str]:
    return [f"{v:02d}" for v in _csv_ints(s, "--jcd", 1, 24)]


def _rnos(s: str) -> list[int]:
    return _csv_ints(s, "--rno", 1, 12)


def _positive(s: str) -> int:
    try:
        v = int(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"整数で指定する: {s!r}") from None
    if v < 1:
        raise argparse.ArgumentTypeError(f"1 以上で指定する: {s!r}")
    return v


def _add_precheck_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--date",
        dest="dates",
        action="append",
        required=True,
        type=_date,
        metavar="YYYY-MM-DD",
        help="確認する過去の日付（複数指定可。今日・未来は不可）",
    )
    p.add_argument(
        "--jcd", type=_jcds, help="場コードをカンマ区切りで（例 01,02）。無ければ B から決める"
    )
    p.add_argument("--rno", type=_rnos, default=[1, 12], help="レース番号（既定 1,12）")
    p.add_argument("--max-venues", type=_positive, default=2, help="B から決める場の数（既定 2）")
    p.add_argument("--force", action="store_true", help="取得済みの LZH も取り直す")
    p.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG, help="設定ファイル（既定 ./config.yaml）"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="boatev", description="ボートレース単勝の期待値予測")
    sub = parser.add_subparsers(dest="command", metavar="<command>", required=True)
    for name, help_text in COMMANDS.items():
        p = sub.add_parser(name, help=help_text, description=help_text)
        if name == "precheck":
            _add_precheck_args(p)
    return parser


def _run_precheck(args: argparse.Namespace) -> int:
    # 遅延 import：スタブのコマンドや --help で requests などを読み込まない
    from boatev import precheck
    from boatev.config import ConfigError, load_config

    try:
        dates = precheck.check_past_dates(args.dates, dt.date.today())
    except precheck.DateRejected as e:
        print(f"boatev precheck: {e}", file=sys.stderr)
        return EXIT_USAGE
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"boatev precheck: 設定エラー: {e}", file=sys.stderr)
        return EXIT_USAGE
    return precheck.run_precheck(
        cfg,
        dates,
        jcds=args.jcd,
        rnos=args.rno,
        max_venues=args.max_venues,
        force=args.force,
    )


def _make_output_lossless() -> None:
    """stdout・stderr を、表せない文字を置換して出す設定にする。

    stdout が cp932 のとき、7z の出力（U+FFFD を含みうる）を含むエラー文の表示で
    UnicodeEncodeError にならないようにする。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


def main(argv: list[str] | None = None) -> int:
    _make_output_lossless()
    parser = build_parser()
    args, unknown = parser.parse_known_args(argv)
    if args.command == "precheck":
        if unknown:  # 実装済みのコマンドは未知の引数を黙って捨てない
            parser.error(f"unrecognized arguments: {' '.join(unknown)}")
        return _run_precheck(args)
    print(f"boatev {args.command}: 未実装", file=sys.stderr)
    return EXIT_NOT_IMPLEMENTED
