# review-code W4 (1周目)

VERDICT: APPROVE
BLOCKER: 0 / MAJOR: 0

検証（評価側で再実行）: ruff check 緑 / ruff format --check 緑 (36 files) / pytest 150 passed, skip 0 (1.97s)。テストに実ネットワークへ出る経路は無い（run_precheck は FakeSession 注入、CLI テストは run_precheck を差し替え、設定欠落・日付拒否・引数エラーは取得前に終わる）。boatev precheck は実行していない。

## 受入基準の対応
| 受入基準 | 実装箇所 | 担保するテスト | 判定 |
|---|---|---|---|
| A8 `--date` 複数、日付ごとに LZH 取得・解凍 | boatev/precheck.py:207-233 `run_precheck`、:97-119 `_process_lzh`（cfg.lzh_base を渡す） | test_exec_saves_pages_and_summary, test_multi_date_intervals_hold_across_dates_with_one_fetcher, test_end_to_end_with_real_sevenzip（実 7z） | 満たす |
| A8 ページを数件取得し `data/raw/pages/{odds,beforeinfo}/YYYYMMDD/<jcd>_<rno>.html` に保存 | precheck.py:74-80 `page_url`/`page_path`、:122-153 `_fetch_page`（200 のときだけ生バイトで上書き） | test_page_url_and_path, test_exec_saves_pages_and_summary（8 件の保存先と中身）, test_page_errors_recorded_and_others_saved | 満たす |
| A8 要約 JSON（URL・HTTP ステータス・バイト数・保存先）を `data/raw/precheck/precheck_<実行時刻>.json` | precheck.py:156-165, 264-280 | test_exec_saves_pages_and_summary（url/status_code/bytes/path/final_url）, test_summary_file_not_overwritten_in_same_second | 満たす（LZH 側の項目は下の所見） |
| A8 ページ 3 秒・LZH 2 秒の間隔、Fetcher 1 つ | precheck.py:186-191 | test_multi_date_intervals_hold_across_dates_with_one_fetcher（created == [1]、3 日分で LZH 間隔 >= 2.0、ページ >= 3.0） | 満たす |
| A8 リクエスト総数（数件） | 解釈 3 の既定（2 場 × 2R × 2 種） | test_exec_saves_pages_and_summary（LZH 2 + ページ 8）, test_jcd_rno_max_venues_options | 満たす |
| A9（前半）dev ではページを飛ばす | precheck.py:194, 250 | test_dev_role_never_requests_pages（get_page を例外に差し替え、セッションに来た全 URL が lzh_base、race_page_base は 0 件、html 0 件、要約と標準出力に飛ばした旨） | 満たす |
| A10 開発PCで LZH 1 日分の実取得と解凍 | — | 本体の手動実行（終了コード 0、要約 data/raw/precheck/precheck_20261024_005352.json を評価側で読んだ: B/K とも downloaded true・extracted 1 件・error null、venues 04,06、pages_skipped true） | 満たす |
| A11 案内表示（tests/fixtures/real/ に持ってくるファイル） | precheck.py:291-297 | test_exec_saves_pages_and_summary（LZH と HTML のパスが出る）, test_dev_role_never_requests_pages | 満たす |
| 解釈 3 開催場は B の `NNBBGN`、先頭 max_venues 場、--jcd/--rno | precheck.py:41, 65-71, 235-248、cli.py `_jcds`/`_rnos`/`_positive` | test_venues_from_b_text_*（全角・行頭）, test_real_b_file_venue_detection（実 b261001 で 14 場）, test_jcd_rno_max_venues_options, test_cli_passes_options, test_cli_defaults, test_cli_bad_arguments_exit_2 | 満たす |
| 解釈 4 ページ URL、base は config | precheck.py:74-75（cfg.race_page_base） | test_page_url_and_path | 満たす |
| 解釈 5 複数日付、ステータスとサイズを残す、中身は判定しない | precheck.py:138-150 | test_page_errors_recorded_and_others_saved（503 は bytes を残し保存しない）, test_page_redirect_final_url_recorded | 満たす |
| 解釈 6 LZH は取得済みを飛ばし --force で再取得、ページは毎回取り直す | precheck.py:112 | test_rerun_skips_downloaded_lzh_and_force_refetches | 満たす |
| 失敗時の扱い（落ちずに要約へ、次の日付へ、終了コード 1） | precheck.py:116-118, 151-152, 241-247, 298 | test_download_error_recorded_and_next_date_continues, test_extract_error_recorded_with_force_hint, test_no_marker_in_b_is_error, test_sevenzip_missing_is_recorded, test_page_errors_recorded_and_others_saved | 満たす |
| CLI（--config、設定エラー・今日以降の日付は 2、未知の引数を捨てない） | cli.py:67-110 | test_cli_config_option, test_cli_missing_config_exit_2, test_cli_rejects_today_and_future, test_cli_bad_arguments_exit_2、test_cli.py のスタブ 8 本 | 満たす |
| W2 持ち込み: Fetcher 1 つ / dev でページ URL 0 件 | 上記 | test_multi_date_..., test_dev_role_never_requests_pages | 解消 |
| W3 持ち込み: 200 で非 LZH 本文 | boatev/lzh.py:30, 108-113（オフセット 2 の `-lh?-`、保存しない） | test_lzh.py::test_download_non_lzh_body_raises_and_saves_nothing（5 種）, test_download_accepts_lh_methods, test_non_lzh_force_refetch_keeps_existing_file | 解消 |
| W3 持ち込み: lzh_url の既定 base | lzh.py:72-74（base 必須、URL の直書きは grep で 0 件） | test_url_base_is_required, test_url_uses_config_base_without_double_slash | 解消 |
| W3 持ち込み: ExtractError を要約に残し --force を案内 | precheck.py:227-231, 289-290 | test_extract_error_recorded_with_force_hint（DownloadError では案内しないことも test_download_error_... で確認） | 解消 |

## 指摘
なし。

## 非ブロックの所見（後続ステップで拾えば足りる）
- 解凍に失敗した LZH もサンプル候補に出る。precheck.py:232-233 はファイルが在れば成否を見ずに sample_lzh に入れる。評価側で b240105.lzh の解凍を失敗させて実行したところ、案内に `b240105.lzh -> tests/fixtures/real/lzh/b240105.lzh` が出た。案内どおりコピーすると、開発PCで test_extract_real_fixture が赤になる。`entry["error"] is None` のときだけ案内に入れれば足りる。
- 標準出力が cp932 のとき、エラー文に cp932 で表せない文字があると最後の表示で落ちる。lzh.py の 7z 出力は `errors="replace"` で読むので U+FFFD が入りうる。評価側で ExtractError の文に U+FFFD を入れ、cp932 の TextIOWrapper に print させたところ UnicodeEncodeError になった。要約 JSON はその前に書かれるのでデータは失われない。このPCの python は出力をパイプに流すと sys.stdout が cp932（utf8_mode 0）になる。7z の出力が実際に cp932 で読めないかは確かめていない。
- LZH の要約エントリには HTTP ステータスとバイト数が無い（url・path・downloaded・extracted・error だけ）。A8 の項目一覧は解釈 5 の「各ページ」に当たるので基準は満たすと判断した。ただ、dev の要約は LZH だけなので、取得の可否は error の文字列からしか読めない（例「HTTP 404: …」）。ステップ 3 の download で status_code と bytes の項目を足すとよい。
- 解釈 3 の「先頭 max_venues 場」は、jcd の昇順で取る実装になっている（ファイルに出てくる順ではない）。テストも昇順を前提にしている。サンプルとしてはどちらでも足りる。
- 間隔はプロセスの中でしか効かない（W2 の設計どおり）。シェルのループで `boatev precheck --date X --force` を続けて呼ぶと、前のプロセスの最後の K と次のプロセスの最初の B の間隔は保証されない。複数日付は `--date` を重ねて 1 プロセスで渡すように案内するか、ステップ 3 の download で考える。
- precheck.EXIT_USAGE は使われていない（cli.EXIT_USAGE と重複）。

## 評価側で確かめたこと（オフライン）
- dev で 3 日分を実行すると、LZH 6 件の開始間隔は [2.0, 2.0, 2.0, 2.0, 2.0] で、日付をまたいでも 2 秒を割らない（偽の時計、リクエスト所要 0.1 秒）。
- data/raw/B/202610/B261001.TXT と B261002.TXT は同じ 153,666 バイトだが中身は違う（固定幅。場は 03,04,… と 04,06,… で、どちらも 14 場）。K も同様。解凍の取り違えではない。
- lzh_url・download_lzh の呼び出し元は precheck.py とテストだけで、どれも base を渡している。

## 確認できなかったこと
- 実行PC（role: exec）での実ページ取得、boatrace.jp が過去日付・欠場場に返すステータスと本文 — 規約によりネットワークに出ていない。precheck.py:138-150 の扱いをモックで見ただけ。
- mbrace が欠損日に返す本文が `-lh?-` 検査で弾けるか — lzh.py:108-113 とテストの合成本文だけで見た。
- 開発PCの手動実行の標準出力そのもの — 本体の報告と要約 JSON だけを見た。

## 前周指摘の解消状況
W4 は 1 周目のため該当なし（W2・W3 評価からの持ち込み 4 件は上の表で解消を確認）。
