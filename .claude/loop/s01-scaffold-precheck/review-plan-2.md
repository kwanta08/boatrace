VERDICT: APPROVE
BLOCKER: 0 / MAJOR: 0

## 受入基準の対応
| 受入基準 | work-item | テスト | 判定 |
|---|---|---|---|
| 起動1: 雛形が揃い、空のテストと lint が緑 | W1（A1〜A3） | 検証ゲート、test_packages_explicit、test_requirements_pinned、test_pins_match_installed、test_gitignore_entries | OK |
| 起動1: boatev に spec の各サブコマンドが未実装スタブで並ぶ | W1（A5） | test_cli.py | OK |
| 設定ローダ（7z はハードコードしない） | W1（A4） | test_config.py | OK |
| 起動2: precheck がページ数件と LZH 1 日分を取得・保存・解凍し、間隔と保存先をモックで確認 | W2〜W4（A6〜A8） | test_fetch / test_lzh / test_precheck | OK |
| 開発PCからページに一切アクセスしない | W2・W4（A9） | test_dev_role_never_requests_pages / test_page_fetch_refused_on_dev | OK |
| 起動3: 開発PCで LZH 1 日分の実取得と解凍 | W3・W4（A10）、「順序」節 | 手動実行（ネットに出るのでテストにはできない）。-lh0- の結合テストと test_extract_real_fixture で補う | OK（lhafile を使わないのは spec に合う。起動プロンプトとの食い違いは利用者に報告すること） |
| spec 手順 1「両PCで同じ環境が入る」 | W1（A1・A2） | test_packages_explicit、test_pins_match_installed | OK |
| spec 手順 2「保存した HTML と LZH がテスト用サンプルになる」 | W3（A11）、W4（案内表示） | test_extract_real_fixture（skip 付き）。HTML 側はステップ 7 で作る（A11 に理由あり） | OK |
| spec 手順 2「取得できる期間が分かる」 | W4（解釈 5） | test_precheck.py | OK |
| 起動4: 全体緑・コード評価 APPROVE・Vault 記録 | （プロセス） | state.md | OK |

## 指摘
なし

## 確認できなかったこと
- `test_pins_match_installed` は venv に入っているものと完全一致を求める。利用者が venv に別のツールを足すと赤になり、それは意図どおりの挙動になる。後のステップで依存を足すときは、固定ファイルを作り直す必要がある。plan が決めた範囲なので指摘にはしない。確かめた前提は二つで、現在の venv には pip しか入っていないこと（`pip list`）と、build isolation のため setuptools が venv に残らないこと。
- 実 LZH をいつ `tests/fixtures/real/lzh/` にコピーするかが、A11 の「A10 のあと」と「順序」節の「W3 のあと・W4 の前」で食い違っている。どちらで実行しても結果は同じなので、実害は無い。
- 補足（指摘には入れない。前周から変わっていない）: ROADMAP.md のフェーズ 1 はまだ `scaffold` のままで、このタスク（手順 1・2 をまとめたもの）とフェーズ 2・3（download / pagefetch）の範囲の重なりが直っていない（ROADMAP.md 27 行目）。fetch.py と lzh.py を後で作り直さないよう、ROADMAP を更新しておくこと。

## 前周指摘の解消状況
- MAJOR-1（setuptools のフラットレイアウト自動検出）：解消。A1 に `[tool.setuptools] packages = ["boatev"]` の明示と build-system の setuptools の `==` 固定が入り、それを見る `test_packages_explicit` と、data/ models/ reports/ がある状態での再インストール確認も加わった。前周に再現した失敗は、packages を明示すれば起きない。
- MAJOR-2（推移的依存の固定を確かめていない）：解消。固定ファイルを `pip freeze --exclude-editable` から作ると明記された。`test_pins_match_installed` が、固定ファイル（`-r` を辿る）の名前と版を、導入済みの一覧（名前は正規化、pip と boatev は除く）と突き合わせる。抜けや版のずれがあれば赤になる。
- MAJOR-3（テスト用サンプルの受け口が無い）：解消。A11 として、skip 付きの実 LZH 解凍テスト（-lh5- を補う）、`tests/fixtures/real/lzh/` へのコピー手順、precheck の案内表示が加わった。保存 HTML のテストは、パーサーが無く今は書けないので、理由を付けてステップ 7 に回している。
- 前周の「確認できなかったこと」：7z のパス（テスト）は、config.yaml、なければ config.example.yaml の値を使い、実在しなければ skip すると明記された。場マーカーの形は、W4 の前に実 B ファイルで確かめる順序になった。どちらも解消。
