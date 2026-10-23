# 偵察の要点（全フェーズ共通）

仕様の正は `docs/spec.md`（285 行、全節を読んだ）。Vault: `projects/boatrace/_boatrace_index.md`（下準備のみ、ADR/Gotcha なし。spec との食い違いなし）。

## 環境（2026-10-24 確認）
- このPC: hostname `kwa-laptop`、Windows 11。`py -3.14` → 3.14.6。`py -V:3.14` は使えない（CLAUDE.md）
- 7-Zip 26.05 (x64) を `C:\Program Files\7-Zip\7z.exe` に導入済み（2026-10-24 利用者。PATH には無い）。`7z i` で Lzh 形式の対応を確認。実 LZH の解凍はまだ試していない
- Windows 同梱の `C:\Windows\System32\tar.exe`（bsdtar 3.8.9 / libarchive）は LHA を読める → フィクスチャの切り出しにだけ使う（本体の解凍は spec どおり 7-Zip）
- robots.txt: `www1.mbrace.or.jp` / `www.boatrace.jp` とも `Disallow:` 空（全許可）。サイトポリシーは大量アクセス禁止・私的使用の範囲
- git: ブランチ `feature/boatev`、コミット 0。origin = GitHub 非公開 `kwanta08/boatrace`（2026-10-24 作成、未 push。push は最初のステップ完了時）
- 開発PC/実行PCの区別: **このPC（kwa-laptop、Windows）は開発PC**（2026-10-24 利用者指示。以前の「このWindows機が実行PC」という仮決めは撤回）。オッズ・直前情報ページにはアクセスしない。LZH は動作確認用に数週間分まで

## spec の要点
- URL: `https://www1.mbrace.or.jp/od2/B/YYYYMM/bYYMMDD.lzh`、`.../K/YYYYMM/kYYMMDD.lzh`
- 間隔: LZH 2 秒、オッズ・直前情報 3 秒以上。並列化しない
- race_id = YYYYMMDD + jcd(2) + rno(2)。Parquet、生 LZH は data/raw/ に残す。同じ日を再取得したら上書き（当日・前日は確定前の可能性）
- テーブル: races / entries / results / before_info / payouts / odds_win / bets_log（列は spec「データ仕様」）
- 時点ルール 1〜6（spec「特徴量設計」）、オッズは勝率モデルに入れない
- モデル: LightGBM 二値 → レース内 softmax(s/T)、T は検証 logloss 最小。合成 p* = softmax(α log p + β log q)
- 買い目: EV≥1.10、p*≥0.05、オッズ≤50、1R 1 点、k=0.25、1 点上限 = 資金 2% かつ上限額（未定）、100 円単位切り捨て、日次損切り = 月予算の 10%、月 1 万円上限
- 期間（仮置き）: 学習 2020-01〜2024-06 / 検証 2024-07〜2025-06 / テスト 2025-07〜2026-06
- 評価: 回収率、ベット数、的中率、最大 DD、月別、ブートストラップ 10,000 回の 95%CI、logloss 3 種、オッズ帯別。比較: 均等買い≈75%、1 号艇、q だけ
- コマンド: download / parse / odds / beforeinfo / features / train / backtest / today
