# boatrace

ボートレース単勝の期待値予測システム（Python パッケージ `boatev`）。仕様の正は `docs/spec.md`。

## 進め方
自分の入力が不要なステップは進め続ける。状況報告は次のアクションと同じメッセージに入れる。
止まって聞くのは、自分なしでは進めないときと、破壊的操作（データ削除、既存データを壊すマイグレーション、force-push、リポジトリ外の変更）の前だけ。
複数ステップの実装は autonomous-dev-loop スキルで回す。
実行の最後は「要判断 / 変更 / 発見」の 3 つの見出しで締める。

## 環境と検証コマンド
Python は 3.14 に固定する（spec「前提と制約」）。素の `python` や `pytest` は使わず、venv の python を直接呼ぶ（activate しない）。パスは Bash / PowerShell 共通で書ける `/` 区切り。Mac では `.venv/Scripts/python` を `.venv/bin/python` に読み替える。

- venv 作成: `py -3.14 -m venv .venv`（このPCの `py` は旧ランチャーなので `py -V:3.14` は「No suitable Python runtime found」で失敗する）
- 依存の導入: `.venv/Scripts/python -m pip install -r requirements-dev.txt` のあと `.venv/Scripts/python -m pip install -e . --no-deps`
  - 依存は `pyproject.toml` に書き、`requirements.txt`（実行用）と `requirements-dev.txt`（`-r requirements.txt` ＋ ruff・pytest）に `==` で固定する。両PCで同じファイルから入れる
- lint: `.venv/Scripts/python -m ruff check .` と `.venv/Scripts/python -m ruff format --check .`
- テスト: `.venv/Scripts/python -m pytest`
- 検証ゲート（緑の条件）: 上の lint 2 本とテストがすべて通ること

## このプロジェクトの決まり
- 仕様は `docs/spec.md` が正。このPCは開発PC、データ取得・学習・当日運用の本番は実行PC。
- 取得は並列化しない。LZH は 2 秒に 1 件、オッズ・直前情報ページは 3 秒に 1 件以上の間隔。間隔はコードで強制し、テストで確かめる。
- 開発PCからオッズ・直前情報ページには一切アクセスしない。パーサーやテストは保存済み HTML で作る。LZH は動作確認用に数週間分まで取得してよい。
- テストはネットワークに出ない。HTTP はモックする。
- `data/`、`models/`、`reports/`、`config.yaml`、`tests/fixtures/real/` は .gitignore。公式データとモデルはリポジトリに入れない。設定は `config.example.yaml` をコミットし、PC ごとに `config.yaml` を作る。
- 実データのサンプルは `tests/fixtures/real/`（git 外、実行PCから手で持ってくる）に置き、無ければそのテストは skip する。合成した小さなフィクスチャは `tests/fixtures/` にコミットしてよい。
- モデルは LightGBM のテキスト形式、T・α・β は JSON で保存する。pickle は使わない。
- テスト期間（spec.md「検証」の表）のデータでバックテストを実行しない。テスト期間の実行は利用者が実行PCで一度だけ行う。
- 自動投票はしない。投票サイトへのアクセスやログインを実装しない。月の賭け金上限 10,000 円を超える買い目を出さない。
- Python は spec.md の範囲のバージョン（3.14）に固定し、依存はバージョン固定ファイルから入れる。パスは pathlib。
- ステップが完了の定義を満たしたら `feature/boatev` にコミットして push してよい。main への merge は利用者がする。

## 実装の注意
- LZH の解凍は 7-Zip を `subprocess` で呼ぶ。実行ファイルのパスは `config.yaml` から読み、ハードコードしない（Windows の既定は `C:\Program Files\7-Zip\7z.exe`、PATH には無い。Mac は `7zz`）。`lhafile` は 3.14 の Windows 用 wheel が無くビルドも通らないので依存に入れない
- 公式データは Shift_JIS で全角数字・全角スペースが混ざる。パース前に正規化する。番組表の連結列（`57.14158` 型）は桁数指定の正規表現で切り出す
- 特徴量はリーク防止の時点ルール（spec「特徴量設計」）に従い、オッズは勝率モデルの特徴量に入れない

# Compact instructions
要約するときは次を必ず残す。
- `.claude/loop/ROADMAP.md` のパス
- 現在のフェーズの `state.md` のパス（`.claude/loop/<TASK>/state.md`）
- 現在の work-item（番号と内容、どこまで進んだか）
