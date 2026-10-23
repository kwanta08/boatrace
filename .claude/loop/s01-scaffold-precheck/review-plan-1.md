VERDICT: REVISE
BLOCKER: 0 / MAJOR: 3

## 受入基準の対応
| 受入基準 | work-item | テスト | 判定 |
|---|---|---|---|
| 起動1: 雛形（ディレクトリ構成・config.example.yaml・固定依存・.gitignore・pytest/ruff）で空テストと lint が緑 | W1（A1〜A3） | 検証ゲート、test_scaffold.py | 部分的（MAJOR-1: data/ 等があると `pip install -e .` が失敗。MAJOR-2: 推移的依存の固定を確かめるテストが無い） |
| 起動1: boatev に spec の各サブコマンドが未実装スタブで並ぶ | W1（A5） | test_cli.py | OK |
| 設定ローダ（パス・7z・間隔・閾値・予算、7z はハードコードしない） | W1（A4） | test_config.py | OK |
| 起動2: precheck がページを数件取得して data/raw/ に保存、LZH 1 日分を取得・解凍、間隔と保存先はモックで確認 | W2〜W4（A6〜A8） | test_fetch.py / test_lzh.py / test_precheck.py | OK |
| 開発PCからページに一切アクセスしない | W2・W4（A9） | test_dev_role_never_requests_pages / test_page_fetch_refused_on_dev | OK |
| 起動3: 開発PCで LZH 1 日分の実取得と解凍（lhafile、失敗時 7-Zip） | W4（A10）、解釈 1 | 手動実行（ネットに出るのでテストにはできない）。-lh0- 合成 LZH で 7z の結合テスト | OK（lhafile を使わないのは spec と CLAUDE.md に合う。起動プロンプトとの食い違いは利用者への報告が要る） |
| spec 手順 1「両PCで同じ環境が入る」 | W1（A1・A2） | test_requirements_pinned | 部分的（MAJOR-1、MAJOR-2） |
| spec 手順 2「保存した HTML と LZH がテスト用サンプルになる」 | 無し | 無し | 未対応（MAJOR-3） |
| spec 手順 2「取得できる期間が分かる」 | W4（解釈 5） | test_precheck.py（要約 JSON） | OK（中身の判定は人が見る。HTML 構造が分からないので妥当） |
| 起動4: 全体が緑・コード評価 APPROVE・Vault に記録 | （プロセス） | state.md の進捗 | OK |

## 指摘

### [MAJOR] MAJOR-1: pyproject.toml でパッケージを明示していないので、data/ models/ reports/ があると `pip install -e .` が失敗する
- 該当: plan W1 の pyproject.toml の内容（name・requires-python・console script・ruff/pytest 設定だけ）、A1。
- 理由: リポジトリはフラットレイアウト（`boatev/` が直下）。setuptools の自動検出では `data` `models` `reports` もトップレベルのパッケージと見なされ（PEP 420 の名前空間扱い。`tests` `docs` と `.` で始まるものだけが除外される）、ビルドが止まる。開発PCでも A10 を実行すると data/ ができ、そのあとの再インストールが失敗する。実行PCには常に data/ があるので、作り直したときや `git pull` 後に入れ直したときに spec 手順 1 の「両PCで同じ環境が入る」を満たせない。
- 示し方: スクラッチに同じ構成（`boatev/__init__.py`、`data/raw/B/`、`models/`、`reports/`、`tests/`、setuptools バックエンドの pyproject）を作り、`py -3.14` の venv で `pip install -e . --no-deps` を実行すると `error: Multiple top-level packages discovered in a flat-layout: ['data', 'boatev', 'models', 'reports']` になる。3 つのディレクトリを消すと通る（2026-10-24 確認、setuptools は最新版）。
- 取りうる選択肢: (a) `[tool.setuptools] packages = ["boatev"]`（または `[tool.setuptools.packages.find] include = ["boatev*"]`）を W1 に明記する。(b) hatchling などに替え、`packages = ["boatev"]` を明示する。どちらでも、`[build-system] requires` のバックエンドのバージョンも固定する（「依存はバージョン固定ファイルから入れる」の趣旨）。あわせて A1 に「data/ models/ reports/ がある状態で `pip install -e . --no-deps` が通る」を足すか、それを確かめるテストを置く。

### [MAJOR] MAJOR-2: A2 の「推移的依存も含めすべて `==`」を確かめるテストが無い
- 該当: A2 のテスト `test_requirements_pinned`（全行が `==` か `-r` かだけを見る）、A1 の導入手順（`pip install -r requirements-dev.txt` は依存解決を有効にしたまま入れる）。
- 理由: 推移的依存（requests なら certifi・charset-normalizer・idna・urllib3、pytest なら iniconfig・packaging・pluggy・pygments・colorama）の行が抜けていても、pip が固定していない最新版を黙って入れるので、検証ゲートは緑のまま通る。PC ごとに入る版がずれ、spec 手順 1 の「両PCで同じ環境が入る」と CLAUDE.md の「両PCで同じファイルから入れる」をテストで担保できない。固定の一覧をどう作るか（入れてから freeze するのか）も plan に無い。
- 示し方: requirements.txt を `requests==X` と `PyYAML==Y` の 2 行だけにしても `test_requirements_pinned` は通る。そのあと `pip install -r requirements-dev.txt` も成功する。
- 取りうる選択肢: (a) テストで固定ファイルの全パッケージ名を集め（`-r` も辿る）、venv に入っている配布物の一覧（`importlib.metadata.distributions()`。pip と boatev 自身は除く）と比べ、名前と版が一致することを確かめる。(b) 導入手順を `pip install --no-deps -r requirements-dev.txt` のあとに `pip check` を実行する形に変え、抜けがあれば失敗させる。どちらでも、固定ファイルの作り方（導入してから `pip freeze --exclude-editable` で書き出す）を W1 に書く。

### [MAJOR] MAJOR-3: spec 手順 2 の完了条件「保存した HTML と LZH がテスト用サンプルになる」に対応する受入基準もテストも無い
- 該当: plan の受入基準表（A1〜A10）、「やらないこと」。spec「実装順序」手順 2 の完了条件の原文は「取得できる期間が分かる。保存したHTMLとLZHがテスト用サンプルになる。Windowsで7-Zipを使って解凍できる」。
- 理由: plan は保存（data/raw/）までで止まっていて、それをどうサンプルにするか（`tests/fixtures/real/` への受け渡し、それを読む skip 付きテスト）が書かれていない。「やらないこと」にも挙がっていない。もう一つ、実データの LZH は通常 -lh5- で圧縮されているが、自動テストは無圧縮の -lh0- しか扱わない。圧縮された実ファイルを 7-Zip で解凍できることは、A10 の 1 回の手動確認でしか裏付けられず、繰り返し確かめる手段が無い。ステップ 6・7 で、サンプルが無いことに気づいて作り直すことになる。
- 示し方: 受入基準表と W1〜W4 の変更対象に `tests/fixtures/real/` が一度も出てこない。CLAUDE.md は「実データのサンプルは tests/fixtures/real/ に置き、無ければそのテストは skip」と決めている。
- 取りうる選択肢: (a) 受入基準を 1 つ足す。`tests/fixtures/real/` に実 LZH（B・K）があれば 7-Zip で解凍し、`B*.TXT` / `K*.TXT` ができて 0 バイトでないことを確かめるテスト（無ければ skip）を W3 に入れる。A10 のあと、開発PCで取った 1 日分をそこにコピーする手順を加える（git 外なのでコミットはされない）。precheck の終了メッセージに、サンプルとして持ってくるファイルのパスを出す。(b) ステップ 6・7 に送るなら、「やらないこと」に理由付きで書き、要判断として利用者に返す。spec の完了条件を外すことになるので、黙って省かない。

## 確認できなかったこと
- B ファイルの場の開始マーカーが `NNBBGN`（例 `01BBGN`）の形かどうか — 実ファイルがリポジトリにも tests/fixtures/real/ にも無い。spec と context.md にも書かれていない。違っていても `--jcd` で回避でき、影響は実行PCでの precheck のページ部分だけ。A10 で取得した実 B ファイルで先に確かめるのが安全。
- A7 の結合テストが 7z.exe をどう見つけるか（config.yaml は git 外なので、テスト環境に無いことがある）— plan の W3 には書かれていない。テスト側で既定パスを固定して書くのか、環境変数か config.example.yaml の値を使うのかを決めておかないと、いつも skip になりうる。
- -lh0- のレベル 2 ヘッダ（CRC16 付き）を 7-Zip が解凍できるか — スクラッチで自作した 62 バイトの LZH を `C:/Program Files/7-Zip/7z.exe x` で展開し、終了コード 0 と中身の一致を確かめた。W3 のテストヘルパーの前提は成り立つ。
- その他に確かめたこと: 7-Zip が実在すること（`C:/Program Files/7-Zip/7z.exe`）、venv が 3.14.6 で pip しか入っていないこと、リポジトリにコードもコミットも無いこと（plan の「既存挙動なし」と合う）。
- 補足（指摘には入れない）: ROADMAP.md のフェーズ表はまだ `scaffold`（1）、`download`（2、手順 2・3）、`pagefetch`（3、事前確認スクリプト）に分かれていて、このタスク s01-scaffold-precheck（手順 1・2 をまとめたもの）と合っていない。W2 の fetch.py と W3 の lzh.py は後のフェーズで使い回す前提になるので、ROADMAP を直しておかないとフェーズ 2・3 で同じものを作り直すおそれがある。間隔を「前のリクエストの開始から」測るのは spec の「3秒に1件」を満たしている。
