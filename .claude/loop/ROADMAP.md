---
updated: 2026-10-24
plan: max
spec: docs/spec.md
branch: feature/boatev
---

# ROADMAP — boatev

仕様の正は `docs/spec.md`。フェーズは spec「実装順序」（ステップ 1〜14）に沿って並べ、大きいステップは分けた。
各フェーズの作業ファイルは `.claude/loop/<TASK>/`（state.md / plan.md / review-*.md）。

## 共通の前提（全フェーズ）

- PY: `C:/Users/yoshi/boatrace/.venv/Scripts/python.exe`（3.14）。検証ゲート = `ruff check .` + `ruff format --check .` + `pytest`
- このPCは開発PC（2026-10-24 利用者指示）。取得・学習・当日運用の本番は実行PC
- テストはネットワークに出ない（HTTP はモック）。開発PCからの実サイト取得は LZH の動作確認（数週間分まで）だけ。オッズ・直前情報ページには一切アクセスしない
- アクセス間隔：LZH 2 秒、オッズ・直前情報 3 秒以上。並列化しない。間隔はコードで強制し、テストで確かめる。取得済みは飛ばす（当日・前日分のみ上書き、spec「データ仕様」）
- `data/` `models/` `reports/` `config.yaml` `tests/fixtures/real/` はコミットしない。実データのサンプルは `tests/fixtures/real/`（実行PCから手で持ってくる、無ければ skip）、合成フィクスチャは `tests/fixtures/` にコミット可
- テスト期間（spec「検証」）のデータでバックテストを実行しない（利用者が実行PCで一度だけ）
- 自動投票・投票サイトへのログインは実装しない（spec も求めていない）

## フェーズ

| # | TASK | 仕様の該当節 | 受入基準 | risk | 前提 | ネット / 長時間 | 状態 |
|---|---|---|---|---|---|---|---|
| 1 | `scaffold`（→ `s01-scaffold-precheck` で実施） | 実装順序 1、前提と制約、システム構成 | ① `py -3.14 -m venv` → requirements-dev.txt で入り、空でないスモークテストと lint が緑 ② `config.yaml` を読む設定ローダ（パス・間隔・閾値・予算。7z パスはハードコードしない）と `boatev <cmd> --help` の CLI 骨格 ③ `.gitignore` が data/ models/ reports/ config.yaml tests/fixtures/real/ .env .venv を除外し、`config.example.yaml` をコミット | low | — | なし | 完了（2026-10-24） |
| 2 | `download` | 実装順序 2・3、データソース（B/K の LZH） | ① 日付範囲の B/K LZH を 2 秒間隔・直列で取得し data/raw/ に保存、取得済みは飛ばし中断後に再開できる（当日・前日分は再取得） ② 7-Zip を config のパスで subprocess 呼び出しして解凍（7z 不在時は明示エラー） ③ 2 秒間隔の強制をテストで確かめる（HTTP はモック）。合成した小さな B/K をフィクスチャにする。実サイトでの動作確認は数週間分まで | mid | 1 | ネット（LZH 数日〜数週間分） | 未着手 |
| 3 | `pagefetch` | 実装順序 2・4、データソース（オッズ・直前情報） | ① 場・日付・R を指定して単勝オッズ・直前情報ページを 3 秒間隔で取得し生 HTML を保存、中断後に続きから再開（HTTP はモックでテスト、3 秒間隔の強制もテスト）② 事前確認スクリプト（過去日付のページを数件取得して保存）を用意し、実行は利用者が実行PCで行う ③ 取得時間の実測は実行PC | mid | 1 | なし（実サイトは実行PCのみ） | 未着手 |
| 4 | `parse` | 実装順序 6、データ仕様（races/entries/results/payouts）、データソースの注記 | ① Shift_JIS・全角を正規化し、B → races/entries、K → races（気象）/results/payouts を Parquet に出す ② 連結列（`57.14158` 型）を桁数指定の正規表現で切り出す ③ 合成フィクスチャで値を照合（払戻金、欠場・失格・F/L の扱い）。`tests/fixtures/real/` があれば実ファイルでも照合、無ければ skip | mid | 2 | なし | 未着手 |
| 5 | `pageparse` | 実装順序 7、データ仕様（odds_win/before_info） | ① 保存 HTML（`tests/fixtures/real/`、実行PCから持ってくる。無ければ要判断）→ odds_win（6 艇、snapshot、fetched_at）と before_info（source=page）② 欠場艇を判別できる ③ K からの before_info 代用（source=k_proxy、展示タイム・気象のみ）| mid | 3, 4 | なし | 未着手 |
| 6 | `features` | 実装順序 9、特徴量設計とリーク防止の時点ルール 1〜6 | ① 特徴量表の各区分（枠・期別・機材・直前・相対値・履歴・場の特性）を作る ② リーク防止テスト：履歴・場の特性は前日までの K だけ（同日の前レースも使わない）、結果列（本番進入・ST・レースタイム）とオッズを使わない ③ 日付単位の分割ユーティリティ（同日が期間をまたがない） | high | 4, 5 | なし | 未着手 |
| 7 | `train-fundamental` | 実装順序 10、モデル段階 1、検証（期間） | ① LightGBM 二値分類 → レース内 softmax、温度 T を検証期間の対数損失最小で決める ② モデルはテキスト形式、T は JSON で保存（pickle 不使用）③ 検証期間の対数損失と 10 区分の校正表を出す | mid | 6 | 学習は短時間（小データ） | 未着手 |
| 8 | `train-blend` | 実装順序 11、モデル段階 2 | ① q = 正規化した 1/o、p* = 対数重み付け合成、α・β を条件付き最尤で推定（欠場艇を除いて正規化）② 合成後・モデル単体・市場だけの対数損失を比較表に出す ③ α・β を JSON 保存 | mid | 7 | なし | 未着手 |
| 9 | `betting` | 実装順序 12、買い目決定と資金管理 | ① EV・最低勝率・オッズ上限・1 レース 1 点・ケリー k=0.25・1 点上限（資金 2% と上限額）・100 円単位切り捨て ② 月 1 万円の上限を超える買い目を出さない、日次損切り（月予算の 10%）③ 境界値テスト | mid | 8 | なし | 未着手 |
| 10 | `backtest` | 実装順序 12・13、検証（評価指標・比較対象） | ① 回収率（控除込み＝実払戻ベース）・ベット数・的中率・最大 DD・月別収支・ブートストラップ 95%CI・オッズ帯別をレポート（HTML/CSV）② 比較対象（均等買い≈75%、1 号艇、市場 q だけ）③ テスト期間は一度だけ実行できる仕組み（ゲート 1 判定の記録）。ループ内ではテスト期間のデータで実行しない | mid | 9 | なし（本番データでの実行は利用者） | 未着手 |
| 11 | `today` | 実装順序 14、当日の運用フロー | ① `today --prepare` と `today --race <場> <R>` で直前情報・オッズを 1 回ずつ取り、p・p*・EV・賭け金 or「見送り」を出す ② bets_log に追記（placed・実購入額の記録口、締切 5 分前オッズ T-5）③ 月予算・日次損切りを当日分にも適用 | mid | 3, 5, 9 | 実運用は利用者 | 未着手 |

## s01-scaffold-precheck で済んだこと・後続への申し送り（2026-10-24）

s01 は spec ステップ 1・2 をまとめて実施した（フェーズ 1 全体＋フェーズ 2・3 の一部）。後続で二重に作らないこと。

- 済み：`boatev/config.py`（role dev/exec、間隔の下限・nan/inf・timeout の検証、UA の `{version}`）、`boatev/fetch.py`（種別ごとの RateLimiter、`get_page` は role=exec 以外で `PageFetchForbidden`）、`boatev/lzh.py`（`download_lzh` 取得済みスキップ・`-lh?-` 確認・一時ファイル置換、`extract_lzh` 7-Zip）、`boatev/precheck.py`＋`boatev precheck`、実 LZH の受け口 `tests/fixtures/real/lzh/`
- フェーズ 2 `download`：①の日付ループと再開、当日・前日の再取得だけが残り。②③は lzh.py で済み。間隔の強制はプロセス内だけなので、再開を「コマンドを繰り返し呼ぶ」形にしない。1 プロセスで Fetcher を 1 つ
- フェーズ 3 `pagefetch`：②（事前確認スクリプト）は precheck で済み。`page_url`・`page_path` は precheck.py にあるので共通モジュールへ移す。保存名 `<jcd>_<rno>.html` は rno が 0 埋めなし → race_id（rno 2 桁）に合わせるか、ステップ 5 の長期取得前に決める
- フェーズ 4 `parse`：data/raw には `.extract-*`・`.part` が異常終了で残ることがあり、`data/raw/precheck/` に要約 JSON もある → `[BK]YYMMDD.TXT` の形だけ拾う。B の場マーカーは `NNBBGN`、K は `NNKBGN`（実ファイルで確認）。固定幅のため別の日でもファイルサイズが一致することがある
- フェーズ 9 `betting`：config は `budget.monthly_yen` が 10,000 を超えても受け付ける → 月 1 万円の上限はコード側でも強制する
- cli.py の precheck の既定値（`[1, 12]`、`2`）は precheck.py の定数と二重持ち（値は一致）
- 利用者の作業：実行PCで `config.yaml` を role: exec にして `boatev precheck --date <過去日> [--date ...]` を実行し、取得できる期間を確かめる。保存 HTML を `tests/fixtures/real/pages/` に持ってくる（フェーズ 5 のパーサー用）

## ループ外（利用者が実行・決定する）

- 実装順序 2（事前確認：過去日付のページ取得、Windows での 7-Zip 解凍）、5（長期取得）、8（学習期間の確定）、13（ゲート 1 の実行）は、実行PC・本番データが要るので利用者が実行する。コマンドは各フェーズの完了報告に書く
- spec「決めること」の 1 点の上限額は未定 → config に仮の値を置き、要判断に積む
