# review-code all (1周目) — s01-scaffold-precheck 全体差分（結合レベル）

VERDICT: APPROVE
BLOCKER: 0 / MAJOR: 0

評価側で再実行したもの: ruff check 緑 / ruff format --check 緑 (37 files) / pytest 151 passed, skip 0。socket の connect・getaddrinfo を潰したプラグインを入れて pytest を流しても 151 passed（テストはネットワークに出ない）。実サイトにはアクセスしていない。

## 受入基準の対応
| 受入基準 | 実装箇所 | 担保するテスト | 判定 |
|---|---|---|---|
| A1 venv → requirements-dev → `pip install -e . --no-deps`、data/ 等があっても入る | pyproject.toml（`[tool.setuptools] packages = ["boatev"]`、`setuptools==84.2.1`） | test_scaffold.py::test_packages_explicit、検証ゲート。評価側で、pyproject と boatev/ を scratch に写し data/ models/ reports/（.py 入り）を作って `pip wheel . --no-deps` → 成功、wheel の中身は `boatev/` と dist-info だけ | 満たす |
| A2 依存の固定（推移的依存も `==`） | requirements.txt / requirements-dev.txt | test_requirements_pinned、test_pins_match_installed | 満たす |
| A3 ディレクトリ構成と .gitignore | boatev/（spec の 7 モジュール＋config/fetch/lzh/precheck/cli）、.gitignore | test_gitignore_entries、test_layout。`git add -n` で、コミット対象に data/・config.yaml・tests/fixtures/real/・egg-info が入らないことを確認 | 満たす |
| A4 設定ローダ（パス・7z・間隔・閾値・予算、7z 直書き無し） | boatev/config.py:79-136、config.example.yaml | test_config.py 一式、test_no_hardcoded_sevenzip_in_code | 満たす |
| A5 9 サブコマンド、スタブは「未実装」・終了コード 2 | boatev/cli.py:10-20, 130-139 | test_cli.py | 満たす |
| A6 間隔の強制（LZH 2 秒、ページ 3 秒、直列） | boatev/fetch.py:33-128（下限は config.LZH_INTERVAL_MIN / PAGE_INTERVAL_MIN の 1 か所から） | test_fetch.py、test_precheck.py::test_multi_date_intervals_hold_across_dates_with_one_fetcher | 満たす |
| A7 LZH の保存先・解凍・7z 不在・非 0 終了 | boatev/lzh.py:72-183 | test_lzh.py、test_extract_synthetic_lh0（実 7z） | 満たす |
| A8 precheck の取得・保存・要約 JSON | boatev/precheck.py:167-298、cli.py:93-115 | test_precheck.py | 満たす |
| A9 dev はページを取らない（precheck で飛ばす＋get_page が例外） | precheck.py:193,250 / fetch.py:120-125 | test_dev_role_never_requests_pages、test_page_fetch_refused_on_dev、test_from_config_example_is_dev_and_refuses_pages | 満たす |
| A10 開発PCで LZH 1 日分の実取得・解凍 | — | 本体の手動実行（state.md、要約 JSON は W4 評価が確認済み） | 満たす |
| A11 実 LZH の受け口、サンプル案内 | precheck.py:231-233, 291-297 / test_lzh.py:383 | test_extract_real_fixture（実 4 ファイルで skip されず緑）、test_extract_error_recorded_with_force_hint（解凍失敗は案内に出ない） | 満たす |

## 結合の確認（評価側でオフライン実行）
- CLI → load_config → Fetcher.from_config → download_lzh → extract_lzh（実 7z）→ 場の決定 → get_page → 要約 JSON の全経路を、`requests.Session.get` だけ差し替えて実行した（config は example の role を exec、ベース URL を .invalid に書き換え、LZH の本文は tests/fixtures/real/lzh/ の実ファイル、時計・sleep は本物）。`boatev precheck --date 2026-10-01 --date 2026-10-02 --rno 1` → 終了コード 0。
  - リクエスト開始時刻: LZH 0.0 / 2.0 / 11.06 / 13.07、ページ 2.06, 5.06, 8.06, 11.06, 14.06, 17.06, 20.07, 23.07。日付をまたいでも LZH 2 秒・ページ 3 秒を割らない（Fetcher 1 つの使い回しが本物の時計でも効く）
  - 全リクエストに timeout=30.0 と `User-Agent: boatev/0.1.0 (private use)`（config の `{version}` が __init__ の版で埋まる）
  - 場は 10/01 が 03,04、10/02 が 04,06（実 B のマーカーから）。data/raw/B/202610/ に b*.lzh と B*.TXT、`.extract-*` や `.part` の残りは無し
  - 標準出力はパイプで cp932 になったが落ちなかった（W4 後の `_make_output_lossless`）
- W4 承認後の追加修正 3 件: 解凍失敗 LZH は案内から外れる（precheck.py:231-233、テストあり）／cp932 の stdout・stderr で落ちない（cli.py:118-131、test_cli_output_survives_cp932_stdout）／precheck 側の EXIT_USAGE は削除され、cli.EXIT_USAGE だけが使われる。いずれも他モジュールとの食い違いは無い
- work-item をまたぐ前提: role 判定は config.ROLES = (dev, exec) と、fetch・precheck の `!= "exec"` で一致（未知の role は config で弾かれ、Fetcher 単体でも exec 以外は拒否）。LZH・ページのベース URL はどちらも config の urls.* からだけ渡り、コードに直書きは無い（boatev/*.py を grep）。7z のパスは config → extract_lzh → find_sevenzip の 1 経路

## 指摘
なし。

## マージを止めない所見（後続フェーズで拾えば足りる）
- ROADMAP との重なり: フェーズ 1 `scaffold` は本タスクで完了。フェーズ 2 `download` の ②（7z 解凍・不在時のエラー）と ③（2 秒間隔のテスト）の大半、フェーズ 3 `pagefetch` の ②（事前確認スクリプト）は本タスクで済んでいる。ROADMAP 更新時に受入基準から外すか「s01 で済み」と書くと、後続 plan で二重実装しにくい
- pagefetch（ステップ 4）へ: `page_url` / `page_path` は precheck.py にある。odds・beforeinfo を実装するときは共通モジュールに移し、precheck と同じ関数を使う形にすると保存先が分かれない。保存名 `<jcd>_<rno>.html` は rno がゼロ詰めでない（`03_1.html`）。実行PCで長期取得（ステップ 5）を始める前に、race_id（rno 2 桁）に合わせるかを pagefetch の plan で決めておくとよい（後から変えると保存済み HTML の名前替えが要る）
- download（ステップ 3）へ: download_lzh(fetcher, base, data_dir, kind, date, force) と extract_lzh はそのまま日付ループに使える。ただし間隔はプロセス内だけで効く（W4 所見）ので、再開を「コマンドを繰り返し呼ぶ」形にしない。当日・前日分の上書き（spec「データ仕様」）は force を日付で切り替えれば足りる
- parse（ステップ 6）へ: data/raw/B/YYYYMM/ には LZH・TXT のほか、異常終了時に `.extract-*` / `.<name>.part` が残りうる。data/raw/precheck/ に JSON もある。パーサーは `[BK]YYMMDD.TXT` の形だけを拾う
- 既定値の二重持ち: cli.py:75-76 の `default=[1, 12]` と `default=2` は precheck.DEFAULT_RNOS / DEFAULT_MAX_VENUES と同じ値を別に書いている。今は一致しているので実害なし
- config は budget.monthly_yen が 10,000 を超えても受け付ける。CLAUDE.md の「月 1 万円を超える買い目を出さない」はステップ 12（betting）で、上限の強制をコード側に持たせる（config の値だけに頼らない）とよい

## 確認できなかったこと
- 実行PC（role: exec）での実ページ取得と、boatrace.jp が返すステータス・本文 — 規約によりアクセスしていない。上の結合確認はベース URL を .invalid に替えた偽の応答で見た
- Mac（`7zz`、`.venv/bin/python`）での導入とテスト — このPCは Windows のみ。requirements-dev.txt の colorama は Mac でも純 Python で入り、test_pins_match_installed は「固定ファイル = 導入済み」なので通るはず、という読みまで
- `pip install -e . --no-deps` そのものを data/ 等がある状態で再実行したか — venv を変えないよう、scratch のコピーで `pip wheel` を作って代わりにした（ビルド経路は同じ setuptools のビルドバックエンド）

## 前周指摘の解消状況
全体評価は 1 周目のため該当なし。work-item 評価の持ち込み・W4 所見 3 件の修正は上の「結合の確認」で確認した。
