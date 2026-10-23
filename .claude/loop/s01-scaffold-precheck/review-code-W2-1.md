# review-code W2 (1周目)

VERDICT: APPROVE
BLOCKER: 0 / MAJOR: 0

検証: ruff check 緑 / ruff format --check 緑 (28 files) / pytest 66 passed (0.34s)。

## 受入基準の対応
| 受入基準 | 実装箇所 | 担保するテスト | 判定 |
|---|---|---|---|
| A6 LZH 2 秒・ページ 3 秒以上をコードで強制、直列のみ | boatev/fetch.py `RateLimiter.wait`（前回開始時刻から測る、sleep が早く戻っても再ループ）、`Fetcher.get_lzh`/`get_page`（種別ごとの limiter と Lock）、下限での clamp（nan 含む）と inf の拒否 | test_fetch.py: test_lzh_gaps_at_least_2_sec, test_page_gaps_at_least_3_sec, test_second_request_sleeps_only_the_shortfall, test_gap_is_measured_from_previous_request_start, test_first_request(_of_each_kind)_does_not_wait, test_kinds_are_independent, test_interleaved_requests_keep_each_kinds_gap, test_configured_interval_below_floor_is_clamped, test_nan_interval_is_clamped, test_ratelimiter_rejects_inf, test_sleep_that_returns_early_is_retried, test_failed_request_still_counts_for_the_interval, test_fetch_module_has_no_concurrency | 満たす |
| A9（後半）ページ取得関数自体が dev で例外 | fetch.py `get_page`（`role != "exec"` で `PageFetchForbidden`、limiter とセッションに触る前） | test_page_fetch_refused_on_dev（dev/prod/空、セッション呼び出し 0・sleep 0）, test_from_config_example_is_dev_and_refuses_pages, test_lzh_allowed_on_dev | 満たす |
| 解釈 2 role 判定は machine.role | config.py `ROLES` 検証 + fetch.py `get_page` | 上記 + test_config::test_bad_role | 満たす |
| 解釈 10 UA `boatev/<version> (private use)`、timeout 30、リトライなし | config.example.yaml `user_agent: boatev/{version} (private use)`、config.py の `{version}` 置換、fetch.py `_get` が headers/timeout を渡す、リトライ無し | test_request_passes_timeout_and_user_agent, test_user_agent_version_filled_from_package, test_user_agent_without_placeholder_kept, test_non_200_is_returned_not_raised | 満たす |
| W1 所見の持ち込み（nan 間隔、UA の版の二重管理） | config.py:105-109（isfinite かつ >= 下限）、UA のプレースホルダ | test_interval_non_finite_rejected（nan/inf/-inf × 2 キー）, test_user_agent_version_filled_from_package（example に版の直書きが無いことも確認） | 解消 |

## 指摘
なし。

## 非ブロックの所見（W3・W4 で拾えば足りる）
- limiter の状態は Fetcher インスタンスごと。評価側で Fetcher を 2 つ作って続けて get_lzh を呼ぶと開始間隔は約 3 マイクロ秒だった。W3・W4 は 1 プロセスで Fetcher を 1 つだけ作って使い回すこと（日付ごと・種別ごとに作り直すと間隔が効かない）。W4 のテストで、複数日付の precheck 全体を通した LZH の間隔を見れば担保できる。
- `get_lzh` は URL を見ない。dev で get_lzh にページの URL を渡しても通る（評価側で確認）。A9 は「ページ取得関数自体が例外」なので基準は満たすが、W4 で get_lzh にページ URL を渡す間違いを入れると dev からアクセスしてしまう。W4 の test_dev_role_never_requests_pages は、セッションに来た全 URL に race_page_base が含まれないことまで確かめるとよい。
- requests は GET のリダイレクトを既定で追う。リダイレクトの 2 回目のリクエストは limiter を通らない。1 件の取得の一部とみなせば仕様の範囲内。
- `fetch.timeout_sec` は検証されていない（W1 の範囲）。0・負・nan はリクエスト時に ValueError、inf は OverflowError になる（評価側で 127.0.0.1 に向けて確認）。黙って通るわけではないが、W4 は失敗を要約に残すので、そこでは設定の誤りではなく取得失敗に見える。ローダで `0 < timeout_sec`・有限値を弾けば早く気付ける。
- 既定の clock/sleep が `time.monotonic`/`time.sleep` であることを確かめるテストは無い（評価側で確認したところ既定値は正しい）。既定値を変えてしまっても、偽の時計のテストは全部緑のままになる。

## 確認できなかったこと
- 実サーバーで計った間隔 — テストは偽の時計だけ。CLAUDE.md の規約どおりネットワークには出ていない。A10 で本体が実取得するときにログの時刻で見るとよい。
- mbrace のリダイレクトの有無 — 見ていない。

## 前周指摘の解消状況
1周目のため該当なし（W1 評価の非ブロック所見 2 件は上の表で解消を確認）。
