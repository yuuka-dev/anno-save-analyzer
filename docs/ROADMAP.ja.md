# ロードマップ

> 最終更新: 2026-04-19. 本ロードマップは方向性であり確約ではない．*Anno 1800* のセーブ形式の解読進捗次第で優先度は前後する．English version: [ROADMAP.md](ROADMAP.md).

## 現行リリース

### v0.1.0 — RDA V2.2 native parser（リリース済）

`.a7s` 外殻 RDA コンテナの Python ネイティブ reader．

- `RDAArchive` context manager API，エントリ列挙 + per-file zlib 解凍
- `parser.pipeline.extract_inner_filedb` 1 コール unwrap
- フォーマット仕様書 [rda_format_spec.md](rda_format_spec.md)
- pytest 14 件（合成フィクスチャ + 任意の実セーブ連携）

## 計画中のマイルストーン

### v0.2 — FileDB parser

目標: `data.a7s` の中に詰まっている構造化 XML ツリーを取り出せるようにする．

- FileDB V1 / V2 / V3 のタグストリームを decode
- lxml 互換 XML ドキュメント出力（可能な限り streaming）
- ルート / 契約 / クエスト の Pydantic モデル整備
- 終盤セーブ（約 2.2M 行 / 170MB 展開済）でもメモリ上限内

依存: `lxml`（宣言済），streaming byte reader ヘルパ．

### v0.3 — `SessionData` / `BinaryData` 解読（本丸）

目標: 島ごとの建物・在庫・人口を格納している再埋め込みバイナリを解読．

- ヘッダマジック (`04000000018000001D0000…`) の逆解析
- 5 セッション（旧世界 / 新世界 / エンベサ / 北極 / Cape）の識別
- GUID / timestamp / UTF-16LE 文字列のデコード
- 島単位のデータモデル

調査量が大きいため，部分進捗を v0.3.x として段階リリースしてよい．

### v0.4 — サプライチェーン balance 表

目標: 島ごとに各物資の生産 - 消費の差分を算出．

- 入力: 島の在庫 + 建物数 × レシピ効率
- 出力: 黒字/赤字表，ボトルネック強調
- CLI: `anno-save-analyzer balance <save>`

### v0.5 — ルート最適化（OR-Tools）

目標: 遊んでる船や充足してない需要を減らすルート再配分を提案．

- 島 × 物資 × ルート で MILP 定式化
- 船の積載量，移動時間，現行割り当てを制約に
- `optimizer` extra: `pip install anno-save-analyzer[optimizer]`

### v0.6 — Textual TUI ダッシュボード

目標: 追加インストール無しでターミナル上からセーブを探索できる UI．

- [Textual](https://github.com/Textualize/Textual)（Pure Python TUI）ベース
- 画面: Overview / Islands / Routes / Quests / Balance
- Python が動く環境ならどこでも起動．Electron / Tauri / ブラウザ不要
- キーボード操作前提

### v1.0 — 公開安定版

目標: PyPI に出して英語ドキュメントで外に見せられる状態．

- 公開 API の安定化（以降 semver 遵守）
- CHANGELOG.md，MkDocs または in-repo docs 整備
- PyPI に `anno-save-analyzer` として package 配信
- サンプル notebook / セーブ匿名化ツール

## 未来（バージョン未定）

### Anno 117: Pax Romana 対応

*Anno 117: Pax Romana* は `.a8s` 拡張子を採用予定．エンジン上は Anno 1800 と 90% 程度同一フォーマットと推定しているが，実物の `.a8s` を入手して検証するまで確定できない．したがってこの対応のバージョン番号は**発売後の調査結果を受けて決定する**．

## 意図的な非目標

- GPU アクセラレーション: I/O・パース律速なので効果なし．
- Web サービス化: セーブファイルはローカルの個人資産．アップロード前提は UX を損ねる．
- チート補助 / セーブ編集: 本ツールは**読み取り専用 analyzer**．編集は [olescheller/anno1800-retroactive-dlc-activation](https://github.com/olescheller/anno1800-retroactive-dlc-activation) など別プロジェクトの領分．
- リアルタイム監視: *Anno 1800* のセーブは手動/オート保存ベースで，常時監視に実益が薄い．

## 進捗の追い方

- GitHub Milestones: https://github.com/yuuka-dev/anno-save-analyzer/milestones
- 各マイルストーンに紐づく issue が具体タスク
- CHANGELOG.md（v0.2 以降追加）に出荷差分を記録
