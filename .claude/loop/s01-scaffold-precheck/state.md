---
task: s01-scaffold-precheck
plan: max
updated: 2026-10-24
---

# s01-scaffold-precheck

このファイルだけで再開できるように保つ。項目が終わるたびと、サブエージェントを呼ぶ直前に更新する。

## パス
- REPO: C:/Users/yoshi/boatrace / VAULT: C:/Users/yoshi/ClaudeVault/ClaudeVault / PROJ: boatrace / WORK: .claude/loop/s01-scaffold-precheck / ブランチ: feature/boatev
- 仕様: docs/spec.md「実装順序」1・2、「前提と制約」、「データソース」、「システム構成」。偵察の要点: .claude/loop/context.md
- ルーブリック: C:/Users/yoshi/.claude/skills/autonomous-dev-loop/references/rubric-plan.md / rubric-code.md

## 検証コマンドと前提
- PY: C:/Users/yoshi/boatrace/.venv/Scripts/python.exe（3.14.6、2026-10-24 作成）
- 依存の導入: `<PY> -m pip install -r requirements-dev.txt` → `<PY> -m pip install -e . --no-deps`
```
<PY> -m ruff check . --output-format concise
<PY> -m ruff format --check .
<PY> -m pytest -q --tb=short
```

## 進捗
- [x] 偵察 → context.md（既存）
- [x] plan → plan.md
- [x] plan 評価（2/3 周、R1 REVISE MAJOR 3 → R2 APPROVE）
- [x] W1 雛形・設定・CLI スタブ（low）— sonnet/medium、評価 1/3 周 APPROVE
- [x] W2 取得層（mid）— sonnet/high、評価 1/3 周 APPROVE
- [x] W3 LZH 取得と解凍（mid）— sonnet/high、評価 1/3 周 APPROVE
- [x] W4 precheck（mid）— sonnet/high、評価 1/3 周 APPROVE、所見 3 件を追加修正
- [x] 開発PCで LZH 1 日分の実取得と解凍（本体、2026-10-24）: 2026-10-01 の b261001.lzh(33,203B)→B261001.TXT(153,666B)、k261001.lzh(40,259B)→K261001.TXT(197,344B)。7-Zip 26.05 で -lh5- を解凍できた。tests/fixtures/real/lzh/ にコピーし test_extract_real_fixture が skip されず緑。場マーカーは `NNBBGN`/`NNKBGN`（この日 14 場: 24,23,22,19,16,15,14,13,12,09,07,06,04,03）。config.yaml は example のコピー（role dev）
- [x] 本体が `boatev precheck --date 2026-10-02`（role dev）を実行: 終了コード 0、B/K の LZH 取得・解凍、ページは飛ばした旨を表示、要約 JSON data/raw/precheck/precheck_20261024_005352.json。開催場は B マーカーから 04,06。10/02 分も tests/fixtures/real/lzh/ にコピー
- [x] 全体のテスト（151 passed, skip 0）と全体差分の評価（1 周 APPROVE）
- [x] Vault 記録（ADR 0001・0002、Gotcha 2 件、sessions/2026-10-24.md、_boatrace_index.md）、コミット、push

## 次にやること
- なし（タスク完了。次のステップには進まない）。利用者: 実行PCで role: exec にして `boatev precheck --date <過去日>` を実行

## 要判断
- 1 点の上限額（spec「決めること」）。config.example.yaml の betting.bet_cap_yen は仮置き 1000

## 既知の妥協

## モデル割り当て
- plan plan-reviewer opus/high R1 REVISE / R2 APPROVE
- W1 implementer sonnet/medium → DONE（本体再実行 緑 30 passed）
- W1 code-reviewer sonnet/high R1 APPROVE（非ブロック: nan 間隔、UA の版二重管理 → W2 で対応）
- W2 implementer sonnet/high → DONE（本体再実行 緑 66 passed）
- W2 code-reviewer opus/high R1 APPROVE（非ブロック: timeout 検証・既定 clock のテスト → W3、Fetcher 1 個・dev で page URL 0 件の確認 → W4）
- W3 implementer sonnet/high → DONE（本体再実行 緑 103 passed / 1 skipped）
- W3 code-reviewer opus/high R1 APPROVE（非ブロック: 200 で非 LZH 本文 → W4 で -lh?- 確認、lzh_url の既定 base 二重管理 → W4、.extract-* の残り → ステップ 6 のパーサーで . 始まりを除く）
- W4 implementer sonnet/high → DONE（本体再実行 緑 150 passed / skip 0）
- W4 code-reviewer opus/high R1 APPROVE（非ブロック: 解凍失敗 LZH のサンプル案内、cp932 stdout で UnicodeEncodeError、EXIT_USAGE 未使用 → W4 implementer に追加修正を依頼。LZH 要約のステータス/バイト数 → ステップ 3）
- W4 implementer sonnet/high 追加修正 → DONE（本体再実行 緑 151 passed）
- 全体 code-reviewer opus/high R1 APPROVE（所見は ROADMAP の申し送りへ）
- 記録 general-purpose sonnet/low → DONE（本体が ADR の却下案・Gotcha の症状名・秘密情報スキャンを確認）

## 発見（完了報告と session ログに転記する）
- 仮決めした解釈: plan.md 参照（lhafile 不採用は起動プロンプトと spec の食い違い → spec に従う）
- 評価の主な指摘: plan R1 — setuptools フラットレイアウトで data/ があると pip install -e が失敗 / 推移的依存の固定を検証していない / 実サンプルの受け口が無い
- 2 周以上かかった失敗（Gotcha 候補）: plan R1 の setuptools フラットレイアウト（Gotcha 化）、W4 所見の cp932 stdout（Gotcha 化）
- flag によるモデル切り替え: なし
- implementer の昇格: なし（全 work-item で Sonnet のまま、BLOCKED 0）
- 使用量上限で止まった時刻と再開: なし
