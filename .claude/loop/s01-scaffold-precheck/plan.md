---
task: s01-scaffold-precheck
status: approved
risk: mid
---

# plan — s01-scaffold-precheck（spec「実装順序」ステップ 1・2）

仕様の正は `docs/spec.md`。該当節：「前提と制約」（開発・実行環境を含む）、「データソース」、「システム構成」、「実装順序」1・2。リポジトリ規約は `CLAUDE.md`。

## 受入基準と受入テスト

| # | 受入基準 | 受入テスト |
|---|---|---|
| A1 | `py -3.14 -m venv .venv` → `pip install -r requirements-dev.txt` → `pip install -e . --no-deps` で入り、`ruff check .`・`ruff format --check .`・`pytest` が緑。`data/` `models/` `reports/` がある状態でも `pip install -e .` が通る（フラットレイアウトの自動検出に頼らず `[tool.setuptools] packages = ["boatev"]` を明示し、`[build-system] requires` の setuptools を `==` で固定） | 検証ゲート／`tests/test_scaffold.py::test_packages_explicit`（pyproject を tomllib で読み、packages が `["boatev"]`、build-system の requires が `==`）／本体が data/ models/ reports/ を作った状態で `pip install -e . --no-deps` を再実行 |
| A2 | 依存は `pyproject.toml` に書き、`requirements.txt`（実行用、推移的依存も含めすべて `==`）と `requirements-dev.txt`（`-r requirements.txt` ＋ ruff・pytest とその推移的依存、`==`）に固定。固定ファイルは導入後に `pip freeze --exclude-editable` の出力から作る | `tests/test_scaffold.py::test_requirements_pinned`（全行が `==` か `-r`）／`test_pins_match_installed`（`-r` を辿った固定ファイルの名前と版の集合が、`importlib.metadata.distributions()` の導入済み一覧（pip と boatev を除く、名前は正規化）と一致。推移的依存の抜けや版ずれで赤になる） |
| A3 | spec「システム構成」のディレクトリ構成：`boatev/` パッケージ、`config.example.yaml`、`tests/`。`data/` `models/` `reports/` `config.yaml` `tests/fixtures/real/` `.venv` `.env` は `.gitignore` | `tests/test_scaffold.py::test_gitignore_entries` |
| A4 | `config.yaml` を読む設定ローダ。データ・モデル・レポートの保存先、7-Zip のパス、アクセス間隔、閾値・ケリー係数・予算を持つ。パスは pathlib。7z のパスはコードにハードコードしない（既定値も config.example.yaml にだけ書く） | `tests/test_config.py`：example を読める／相対パスは config ファイルの位置基準で解決／LZH 間隔 < 2 秒・ページ間隔 < 3 秒は `ConfigError`／必須キー欠落は `ConfigError` |
| A5 | `boatev` コマンドに spec のサブコマンド `download` `parse` `odds` `beforeinfo` `features` `train` `backtest` `today` が未実装スタブとして並び、加えて `precheck` がある | `tests/test_cli.py`：`boatev --help` に 9 つが出る／各スタブは「未実装」を stderr に出して終了コード 2 |
| A6 | 取得の間隔をコードで強制：LZH は 2 秒、ページは 3 秒以上。直列のみ | `tests/test_fetch.py`：偽の時計で、同じ種別の連続リクエストの間隔が下限以上（2 回目以降は不足分だけ sleep）／初回は待たない／種別ごとに独立 |
| A7 | LZH 1 日分（B と K）を `data/raw/B/YYYYMM/bYYMMDD.lzh` `data/raw/K/YYYYMM/kYYMMDD.lzh` に保存し、7-Zip（config のパス）で同じフォルダに解凍。7z が無ければ明示的なエラー | `tests/test_lzh.py`：URL 生成／保存先／取得済みは再取得しない（`--force` で再取得）／subprocess に渡す引数／7z 不在で `SevenZipNotFound`／7z の非 0 終了で例外。7z が実在するときだけ、テスト内で生成した無圧縮（-lh0-）LZH を実際に解凍する結合テスト（無ければ skip） |
| A8 | `boatev precheck --date YYYY-MM-DD [--date ...]` が、各日付について LZH を取得・解凍し、単勝オッズページと直前情報ページを数件取得して生 HTML を `data/raw/pages/{odds,beforeinfo}/YYYYMMDD/<jcd>_<rno>.html` に保存し、結果の要約（URL・HTTP ステータス・バイト数・保存先）を `data/raw/precheck/precheck_<実行時刻>.json` に出す | `tests/test_precheck.py`：HTTP をモックして、保存先・要約の中身・ページの 3 秒間隔・LZH の 2 秒間隔・リクエスト総数（数件に収まる）を確認 |
| A9 | 開発PCからはオッズ・直前情報ページに一切アクセスしない：config の `machine.role` が `dev` のとき precheck はページ取得を飛ばし、ページ取得関数自体も `dev` では例外 | `tests/test_precheck.py::test_dev_role_never_requests_pages`、`tests/test_fetch.py::test_page_fetch_refused_on_dev` |
| A10 | 開発PCで LZH 1 日分の実取得と 7-Zip での解凍ができる | 本体が手で実行（ループ内の確認、テストではない）：`.venv/Scripts/python -m boatev precheck --date <過去日>`（role=dev）で B/K の LZH と解凍した TXT ができる |

| A11 | spec ステップ 2「保存した HTML と LZH がテスト用サンプルになる」の受け口：`tests/fixtures/real/lzh/` に実 LZH（`b*.lzh` `k*.lzh`）があれば 7-Zip で解凍し、TXT ができて 0 バイトでないことを確かめる（実ファイルは -lh5- 圧縮なので -lh0- の合成テストを補う）。無ければ skip。precheck は終了時に「テスト用サンプルとして `tests/fixtures/real/` に持ってくるファイル」のパスを出す | `tests/test_lzh.py::test_extract_real_fixture`（skip 付き）。本体が W3 のあと（「順序」節）実取得した 1 日分を `tests/fixtures/real/lzh/` にコピーし、開発PCではこのテストが skip されず緑になることを確かめる。保存 HTML 側のテスト（`tests/fixtures/real/pages/`）はパーサーと一緒にステップ 7 で書く（HTML 構造が分からず、今書けるテストが無い） |

テストはネットワークに出ない（HTTP は偽のセッションを注入してモック）。

**7-Zip のパス（テスト）**：実際に 7z を呼ぶテスト（A7 の結合テスト、A11）は、`config.yaml` があればその `tools.sevenzip`、無ければ `config.example.yaml` の値を使い、そのパスが実在しなければ skip。コード本体と同じく、テストにも 7z のパスを直書きしない

## 仮決めした解釈

1. **lhafile は使わない**：起動プロンプトは「lhafile、失敗時 7-Zip」だが、spec「前提と制約」と CLAUDE.md は lhafile 不採用・7-Zip のみと明記。正である spec に従う。外れた場合は解凍関数に lhafile の分岐を足すだけ（他に影響なし）
2. **開発PCの判定は config の `machine.role`（`dev` | `exec`）**：config.example.yaml の既定は `dev`（安全側）。実行PCで `exec` に書き換えたときだけページ取得が動く。外れた場合（ホスト名判定など）も判定関数 1 か所の差し替え
3. **precheck の対象レース**：`--jcd` 指定が無ければ、取得した B ファイルの場の開始マーカー（`NNBBGN` の想定。W3 のあと本体が実 B ファイルで形を確かめ、W4 に渡す）から開催場を拾い、先頭 `--max-venues`（既定 2）場の `--rno`（既定 `1,12`）を取る。1 日あたりページ 2 場 × 2R × 2 種 = 8 件、3 秒間隔で約 24 秒。番組表の本格的なパースはステップ 6
4. **ページの URL**：単勝 `https://www.boatrace.jp/owpc/pc/race/oddstf?rno=<R>&jcd=<jcd2桁>&hd=<YYYYMMDD>`、直前情報 `https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno=<R>&jcd=<jcd>&hd=<YYYYMMDD>`（spec の出典の Zenn 記事の形式）。ベース URL は config に置く。開発PCからは確かめない
5. **「取得できる期間が分かる」**：precheck は複数の `--date` を受け、各ページの HTTP ステータスとサイズを要約 JSON に残す。中身の判定（データがあるか）は保存 HTML を人が見る。HTML 構造は未知なので自動判定はしない
6. **取得済みの扱い**：LZH は保存先にあれば飛ばす（`--force` で再取得）。ページは precheck では毎回取り直して上書き（件数が少なく、取得可否の確認が目的）
7. **解凍先**：LZH と同じフォルダ（`data/raw/B/YYYYMM/` に `B<YYMMDD>.TXT` など）。spec「元の LZH は data/raw/ にそのまま残す」に合う。ステップ 3 で変えるなら解凍関数の出力先引数だけ
8. **依存**：実行用は `requests`・`PyYAML`（＋推移的依存）だけ。pandas・pyarrow・lightgbm は使うステップで足す
9. **未実装スタブの終了コード**：2（argparse の使い方エラーと同じ値だが、メッセージ「未実装」で区別できる）
10. **User-Agent**：`boatev/<version> (private use)` を付け、タイムアウト 30 秒。リトライはしない（失敗は要約に残す）

## 制約

- 既存 ADR / Gotcha：なし（Vault `projects/boatrace/_boatrace_index.md`）
- CLAUDE.md：venv の python を直接呼ぶ、pathlib、並列化しない、間隔はコードで強制しテストで確かめる、テストはネットワークに出ない、pickle 不使用、`data/` 等は gitignore
- spec：7z は外部コマンド、Windows 既定 `C:\Program Files\7-Zip\7z.exe`（PATH 外）、Mac は `7zz`

## work-item

### W1 雛形・設定ローダ・CLI スタブ（risk: low）
- 変更対象：`pyproject.toml`（name `boatev`、`requires-python = ">=3.14,<3.15"`、console script `boatev = "boatev.cli:main"`、ruff・pytest 設定）、`requirements.txt`、`requirements-dev.txt`、`.gitignore`、`config.example.yaml`、`boatev/__init__.py`（`__version__`）、`boatev/__main__.py`、`boatev/config.py`、`boatev/cli.py`、spec の各モジュールの空ファイル（`download.py` `parse.py` `odds.py` `features.py` `model.py` `backtest.py` `today.py`、中身は docstring のみ）、`tests/test_scaffold.py` `tests/test_config.py` `tests/test_cli.py`
- config.example.yaml のキー：`machine.role`、`paths.{data_dir,models_dir,reports_dir}`、`tools.sevenzip`、`fetch.{lzh_interval_sec: 2.0, page_interval_sec: 3.0, timeout_sec, user_agent}`、`urls.{lzh_base, race_page_base}`、`betting.{ev_min: 1.10, p_min: 0.05, odds_max: 50, kelly: 0.25, bet_cap_fraction: 0.02, bet_cap_yen（仮置き、spec「決めること」）, unit_yen: 100}`、`budget.{monthly_yen: 10000, daily_stop_fraction: 0.10}`
- 満たす受入基準：A1〜A5
- 壊しうる既存挙動：なし（新規）

### W2 間隔を強制する取得層（risk: mid）
- 変更対象：`boatev/fetch.py`（`RateLimiter`：種別ごとに最後のリクエスト時刻を持ち、`time.monotonic` と `time.sleep` を注入可能／`Fetcher`：`requests.Session` を注入可能、`get_lzh(url)` と `get_page(url)` が各 limiter を通る、`get_page` は role=dev で `PageFetchForbidden`）、`tests/test_fetch.py`
- 間隔は「前のリクエストの開始時刻から」測る。config の間隔が下限未満なら W1 のローダで弾く（二重に、Fetcher 側でも下限で max を取る）
- 満たす受入基準：A6、A9（後半）
- 壊しうる既存挙動：なし

### W3 LZH の取得と 7-Zip での解凍（risk: mid）
- 変更対象（W3 は A11 も満たす）：`boatev/lzh.py`（`lzh_url(kind, date)`、`lzh_path(data_dir, kind, date)`、`download_lzh(fetcher, ..., force=False)`、`extract_lzh(sevenzip_path, lzh_file, out_dir)` は `subprocess.run([7z, "x", "-y", f"-o{out_dir}", lzh_file], check=False)` で、7z の実在を先に確かめ不在なら `SevenZipNotFound`、非 0 終了なら `ExtractError`（stderr の要点付き）、解凍されたファイルのパス一覧を返す）、`tests/test_lzh.py`、テスト用の -lh0- LZH 生成ヘルパー（`tests/lzh_builder.py` など、レベル 2 ヘッダ＋CRC16）
- 満たす受入基準：A7、A11
- 壊しうる既存挙動：なし

### W4 `boatev precheck`（risk: mid）
- 変更対象：`boatev/precheck.py`（日付ごとに B・K の LZH 取得と解凍 → role が exec ならページ取得 → 要約 JSON）、`boatev/cli.py` の `precheck` サブコマンド（`--date` 複数可、`--jcd`、`--rno`、`--max-venues`、`--force`、`--config`）、`tests/test_precheck.py`
- 実行の最後に、保存先と要約 JSON のパス、role=dev でページを飛ばしたことを標準出力に出す
- 満たす受入基準：A8、A9（前半）、A10（本体が実行）
- 壊しうる既存挙動：W1 の CLI（precheck がスタブから実装に変わる）

## 順序

W1 → W2 → W3 → **本体が W3 の関数で LZH 1 日分（B・K）を実取得・解凍（A10 の前半）し、`tests/fixtures/real/lzh/` にコピー、B ファイルの場マーカーの形を確かめる** → W4 → 本体が `boatev precheck`（role=dev）を実行（A10）。

## 指摘への対応（review-plan-1）

- MAJOR-1：A1 に setuptools の packages 明示と build-system の固定、テスト `test_packages_explicit`、data/ 等がある状態での再インストール確認を追加
- MAJOR-2：A2 に `pip freeze` からの生成と、導入済みとの突き合わせテスト `test_pins_match_installed` を追加
- MAJOR-3：A11（実 LZH の skip 付きテスト、fixtures/real へのコピー手順、precheck の案内表示）を追加。保存 HTML 側のテストはステップ 7 に送る理由を A11 に記載
- 確認できなかったこと：7z のパスの探し方を明記、場マーカーは W4 の前に実ファイルで確かめる順序にした

## スキーマ変更

なし（Parquet のテーブルはステップ 6 以降）。

## やらないこと

- `download` の日付範囲・再開（ステップ 3）、`odds`・`beforeinfo` の本実装（ステップ 4）、パーサー（ステップ 6・7）
- 開発PCからのオッズ・直前情報ページの実取得（precheck のページ部分は実行PCで利用者が実行する）
- HTML の中身の自動判定、リトライ・バックオフ
- lhafile の導入
