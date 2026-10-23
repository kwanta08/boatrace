# review-code W3 (1周目)

VERDICT: APPROVE
BLOCKER: 0 / MAJOR: 0

検証（評価側で再実行）: ruff check 緑 / ruff format --check 緑 (33 files) / pytest 104 passed, skip 0 (0.69s)。7-Zip は C:/Program Files/7-Zip/7z.exe に実在し、test_extract_synthetic_lh0・test_extract_corrupt_lzh_raises_for_real・test_extract_real_fixture は skip されずに実行された。テストに実ネットワークへ出る経路は無い（FakeFetcher／偽セッションのみ、conftest は config を読むだけ）。

## 受入基準の対応
| 受入基準 | 実装箇所 | 担保するテスト | 判定 |
|---|---|---|---|
| A7 URL 生成 | boatev/lzh.py:64-71 `lzh_filename`/`lzh_url`（base は引数、末尾 `/` を除く） | test_url_b_and_k, test_url_uses_config_base_without_double_slash, test_url_zero_pads_and_two_digit_year, test_bad_kind | 満たす |
| A7 保存先 `data/raw/{B,K}/YYYYMM/{b,k}YYMMDD.lzh` | lzh.py:74-76 `lzh_path` | test_path_layout, test_download_saves_file | 満たす |
| A7 取得済みは再取得しない／force で再取得（解釈 6） | lzh.py:95-96 | test_download_skips_existing_and_force_refetches | 満たす |
| A7 取得失敗の扱い（非 200・空本文・書き込み失敗・通信例外で壊れたファイルを残さない、force 失敗で既存を壊さない） | lzh.py:98-116（一時ファイル→os.replace） | test_download_non_200_raises_and_saves_nothing（5 種）, test_download_empty_body_raises, test_failed_force_refetch_keeps_existing_file, test_write_failure_leaves_no_partial_file, test_network_error_propagates_and_saves_nothing | 満たす |
| A7 subprocess に渡す引数 `7z x -y -o<dir> <lzh>`、check=False | lzh.py:148-155（-o は out_dir 内の作業ディレクトリ） | test_extract_passes_expected_arguments | 満たす |
| A7 同じフォルダに解凍（解釈 7）、既存ファイルがあっても戻り値が正しい | lzh.py:145-173 | test_extract_passes_expected_arguments, test_extract_returns_only_extracted_files_when_dir_has_others, test_extract_overwrites_same_name_and_returns_it, test_extract_into_separate_dir | 満たす |
| A7 7z 不在で SevenZipNotFound（subprocess を呼ぶ前） | lzh.py:119-138 `find_sevenzip` | test_extract_missing_sevenzip（calls == []）, test_find_sevenzip_falls_back_to_path | 満たす |
| A7 7z の非 0 終了で例外（stderr の要点付き、何も置かない） | lzh.py:160-162 | test_extract_nonzero_exit_raises_with_stderr_and_places_nothing, test_extract_timeout_is_extract_error, test_extract_nothing_extracted_raises, test_extract_missing_lzh, test_extract_corrupt_lzh_raises_for_real（実 7z） | 満たす |
| A7 -lh0- 合成 LZH の結合テスト（7z 実在時のみ） | tests/lzh_builder.py（レベル 2 ヘッダ＋CRC-16/ARC） | test_crc16_known_value（0xBB3D）, test_extract_synthetic_lh0（cp932 本文がバイト一致、既存ファイル温存） | 満たす |
| A11 実 LZH（tests/fixtures/real/lzh/）を解凍し TXT が 0 バイトでない、無ければ skip | test_lzh.py:329-344 | test_extract_real_fixture（開発PCで skip されず緑を確認） | 満たす（precheck の案内表示は W4） |
| 7-Zip のパス（テスト）: config.yaml → 無ければ config.example.yaml、実在しなければ skip、直書きしない | tests/conftest.py `sevenzip_exe` | 上記 3 本の結合テストが使用 | 満たす |
| 解釈 1 lhafile 不使用 | lzh.py は subprocess のみ、依存にも無い | （grep で確認） | 満たす |
| W2 所見の持ち込み: fetch.timeout_sec の検証 | boatev/config.py:111-113（有限かつ > 0） | test_config.py::test_timeout_must_be_positive_finite（0, -1, -0.5, nan, inf, -inf）, test_timeout_positive_ok | 解消 |
| W2 所見の持ち込み: 既定 clock/sleep のテスト | fetch.py:40-41, 75-76, 93-94 | test_fetch.py::test_default_clock_and_sleep_are_monotonic_and_time_sleep（RateLimiter・Fetcher・from_config の 3 経路） | 解消 |

## 指摘
なし。

## 非ブロックの所見（W4 以降で拾えば足りる）
- HTTP 200 で LZH でない本文（HTML のエラーページ等）が返ると、そのまま `.lzh` として保存され、次回からは取得済みとして飛ばされる。評価側で偽 Fetcher（200 + `<html>not found</html>`）を使って確認した。extract_lzh は ExtractError で落ちるので黙って通ることはなく、`--force` で直せる。mbrace が欠損日に 200 の HTML を返すかどうかは確かめていない（ネットワークに出ていない）。W4 では ExtractError を要約に残し、`--force` を案内するとよい。先頭バイトの `-lh?-`（オフセット 2）を見て DownloadError にする方法もある。
- `lzh_url` の既定引数に `https://www1.mbrace.or.jp/od2` が直書きされていて、config の urls.lzh_base と二重管理になっている。W4 は必ず cfg.lzh_base を渡すこと（download_lzh は base 必須なので経路上は問題ない）。
- extract_lzh の作業ディレクトリ `.extract-*` は out_dir（data/raw/B/YYYYMM/）の中に作られる。プロセスが強制終了されると残る。ステップ 6 のパーサーが `rglob("*.TXT")` で拾うと、古いコピーを二重に読むおそれがある。パーサーは `glob`（直下だけ）にするか、`.` で始まるディレクトリを除くこと。
- 複数ファイルの移動（os.replace のループ）の途中で失敗すると、一部だけが out_dir に置かれる。実際の B/K は 1 ファイルなので影響はない。

## 評価側で確かめたこと（オフライン）
- 実 b261001.lzh を data/raw/B/202610/ と同じ形の一時フォルダで、LZH と同じフォルダに 2 回解凍した。戻り値は 2 回とも [B261001.TXT] で、フォルダの中身は B261001.TXT と b261001.lzh だけだった（作業ディレクトリは残らない。冪等）。
- 相対パスの LZH・out_dir でも解凍でき、絶対パスが返る。

## 確認できなかったこと
- mbrace が欠損日・未来日に返すステータスと本文 — ネットワークには出ていない（指示どおり）。lzh.py:98-103 の判定は status と空本文だけ。
- Mac（7zz）での実行 — find_sevenzip の PATH フォールバックは shutil.which のモック（test_find_sevenzip_falls_back_to_path）だけで見た。
- 7z が終了コード 1（警告）を返す LZH — 実物が無い。コード上はエラーとして扱われる（厳しい側なので問題はない）。

## 前周指摘の解消状況
1周目のため該当なし（W2 評価の持ち込み 2 件は上の表で解消を確認）。
