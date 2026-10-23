# review-code W1 (1周目)

VERDICT: APPROVE
BLOCKER: 0 / MAJOR: 0

検証: ruff check 緑 / ruff format --check 緑 (25 files) / pytest 30 passed。Python 3.14.6。

## 受入基準の対応
| 受入基準 | 実装箇所 | 担保するテスト | 判定 |
|---|---|---|---|
| A1 packages 明示・setuptools `==` 固定・data/ 等があっても入る | pyproject.toml (`packages=["boatev"]`, `setuptools==84.2.1`) | test_scaffold::test_packages_explicit。評価側で data/raw, models, reports を置いた複製で `pip wheel --no-deps` を実行し、boatev/*.py だけが入ることを確認 | 満たす |
| A2 依存の `==` 固定と導入済みとの一致 | requirements.txt, requirements-dev.txt (`pip freeze` と一致) | test_requirements_pinned, test_pins_match_installed | 満たす |
| A3 構成と .gitignore | boatev/, config.example.yaml, tests/, .gitignore | test_gitignore_entries, test_layout。`git check-ignore` で 7 項目すべて無視されることを確認 | 満たす |
| A4 設定ローダ | boatev/config.py, config.example.yaml | test_config.py (example 読込、相対パスは config 位置基準、間隔下限、欠落、role 不正、7z 直書き無し) | 満たす |
| A5 CLI スタブ 9 個 | boatev/cli.py, __main__.py | test_cli.py (一覧、--help、各スタブ rc=2 と stderr「未実装」)。`python -m boatev download` rc=2、`boatev.exe --help` も確認 | 満たす |

## 指摘
なし。

## 非ブロックの所見（W2 以降で拾えば足りる）
- boatev/config.py:100-103 `lzh_iv < 2.0` の比較は YAML の `.nan` を通す（`nan < 2.0` は False）。W2 の Fetcher が max(下限, 設定値) を取れば実害は出ないが、`not (x >= MIN)` の形にすれば二重防御になる。
- config.example.yaml の `user_agent: boatev/0.1.0` は `__version__` と二重管理。
- budget.monthly_yen は上限 10,000 円を検証していない。買い目を出す today を実装するステップで検証する。

## 確認できなかったこと
- `pip install -e . --no-deps` を data/ 等がある状態で実際に再実行すること — venv を壊さないため、複製に対する `pip wheel` で代用した。
- Mac での動作 — 見ていない。

## 前周指摘の解消状況
1周目のため該当なし。
