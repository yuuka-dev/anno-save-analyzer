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

### v0.3 — 貿易履歴ビューア（Anno 117 ドッグフーディング）

> **2026-04 にスコープ変更**: 元の SessionData/BinaryData 解読は v0.2 でほぼ
> 副産物として完了（再帰 FileDB 仮説確定）し，より差し迫った dogfooding
> ニーズに優先順位を譲った — Anno 117 はゲーム内貿易履歴 UI が無く，
> 書記長が困っとる．

目標: `.a8s` (Anno 117) と `.a7s` (Anno 1800) のセーブから貿易活動を抽出し，物資別 / ルート別の集計を CLI と Textual TUI で見せる．

- タイトル横断の抽象データモデル (`TradeEvent`, `Item`, `Route` など)
- Method A: セーブ内の履歴フィールドから抽出 (`<TradedGoods>` 等)
- Method B: 履歴が薄いタイトル向けの snapshot 差分推定
- Anno 1800 統計画面準拠の 3 カラム Textual TUI
- `textual-plotext` でインライン折れ線グラフ
- 英日併記 (`name_en` + `name_ja`) の GUID 辞書 YAML

詳細仕様: [`v0.3-trade-history-design.ja.md`](./v0.3-trade-history-design.ja.md)（英語正本: [`v0.3-trade-history-design.md`](./v0.3-trade-history-design.md)）．

元 v0.3 の SessionData ドメインモデル化（島 / 建物 / 人口の完全スキーマ）は **v0.6** に移管．

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

### v0.6 — 島 / 建物 / 人口スキーマ深掘り

> **2026-04 にスコープ変更**: 元の「Textual TUI ダッシュボード」は v0.3 の
> 貿易履歴ビューアに前倒しで取り込み済．v0.6 の枠は v0.4 サプライチェーン
> 計算と v0.5 ルート最適化が必要とするドメインスキーマの整備に再利用．

目標: SessionData 内側 FileDB の「島」「建物」「人口」レイヤを Pydantic モデル化．バイト抽出は v0.2 / v0.3 で済んでるので，v0.6 では typed domain object に昇格させる．

- `Island*` / `AreaManager_*` / `AreaPopulationManager` のスキーマ
- 建物カタログ（建物種別ごとの生産・消費）
- 人口階層別の breakdown（Anno 117 ならローマ人 / イタリック人 等）
- 匿名 attrib (`id=0x8000`) のコンテキスト依存型解釈
- Anno 1800 ↔ Anno 117 のスキーマ差分ドキュメント

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
