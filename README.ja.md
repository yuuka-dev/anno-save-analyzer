# anno-save-analyzer

[![CI](https://github.com/yuuka-dev/anno-save-analyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/yuuka-dev/anno-save-analyzer/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/yuuka-dev/anno-save-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/yuuka-dev/anno-save-analyzer)
[![release](https://img.shields.io/github/v/release/yuuka-dev/anno-save-analyzer?include_prereleases)](https://github.com/yuuka-dev/anno-save-analyzer/releases/latest)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Status: alpha](https://img.shields.io/badge/status-alpha-orange)](docs/ROADMAP.ja.md)

> **一言で説明**: Anno 1800 / Anno 117: Pax Romana のセーブデータ (`.a7s` / `.a8s`) から貿易履歴を抽出し，Textual TUI / CLI から眺められるようにするツール．

> **現状**: v0.3.0 リリース済 (trade history viewer)．PyPI 未配信．Git tag からインストールする．English README: [README.md](README.md).

## 概要

Anno のセーブはマトリョーシカ構造:

1. `.a7s` / `.a8s` — RDA V2.2 アーカイブ (Anno 1404 / 2070 / 2205 / 1800 / 117 共通)
2. 内部の `data.a7s` — zlib 圧縮ストリーム
3. 解凍後: FileDB V3 バイナリ
4. `<SessionData><BinaryData>` — さらに内側に丸ごと埋まっている FileDB V3 ドキュメント (ラティウム / アルビオン / 旧世界 / …)
5. 内側: `AreaInfo` / `PassiveTrade > History` / `ConstructionAI > TradeRoute` 等

本プロジェクトは各層を Python で native にはがし，生の取引イベントをプレイヤーが欲しい形（集計台帳，取引相手内訳，累積推移グラフ，スパークライン，2 セーブ差分）に落とす．

## 主な機能 (v0.3.0)

### Textual TUI (`anno-save-analyzer tui <save>`)

- 3 カラム構成: セッション > 島 Tree / items & routes DataTable / Partners pane + 時系列 chart
- nano 風ホットキー: `^X` 終了 / `^G` ヘルプ / `^T` 画面切替 / `^L` 言語 / `^O` エクスポート
- items-table の推移 sparkline 列 (`▁▂▃▄▅▆▇█`)
- 行選択で Partners pane + plotext 折れ線 chart が同時更新
- chart x 軸は spread に応じて「分前 / 時間前」を auto 切替
- en / ja ロケール切替．Anno 117 / 1800 のセッション名も翻訳
- 起動時にステージ粒度のプログレスゲージ (`[n/5] <stage>`)
- **USSR テーマ** (`--theme ussr`) — 書記長専用ジョーク枠．title に ☭ 付与

### CLI

- `trade list <save>` — 全 TradeEvent を JSON で吐く
- `trade summary <save> --by item|route` — 集計
- `trade diff <before> <after>` — 2 セーブ間 added / removed / changed / unchanged
- `tui <save>` — TUI 起動

### Parser

- **RDA V2.2** コンテナ parser ([@lysannschlegel/RDAExplorer](https://github.com/lysannschlegel/RDAExplorer) の clean-room port)．`.a7s` / `.a8s` 両対応．
- **FileDB V3** streaming DOM + tag/attrib 辞書，SessionData 再帰抽出，AreaManager / 島列挙．
- **Anno 117 interpreter** for `PassiveTrade > History > {TradeRouteEntries,PassiveTradeEntries}` と `ConstructionAI > TradeRoute > TradeRoutes` (idle route 含む)．
- NPC 同士の取引は `AreaInfo > CityName` ゲートで除外．

### データパイプライン

- `items_anno117.{en,ja}.yaml` をゲーム本体の `config.rda/assets.xml` + `texts_japanese.xml` から自動生成 (151 Products × 33,146 翻訳行)．ゲームアップデート時は `scripts/generate_items_anno117.py` で再生成．

### テスト

- 338 tests，**line + branch 100% coverage** を CI で強制 (`--cov-fail-under=100`)．
- Python 3.12 / 3.13 両対応．

## インストール

### **uv** 経由 (推奨)

[uv](https://github.com/astral-sh/uv) を使うと Python 本体の用意 + venv + 依存解決が 1 コマンドで終わる．

```bash
# 最新タグからインストール
uv pip install "anno-save-analyzer[tui] @ git+https://github.com/yuuka-dev/anno-save-analyzer@v0.3.0"

# CLI ツールとして globally install (venv 管理不要)
uv tool install "anno-save-analyzer[tui] @ git+https://github.com/yuuka-dev/anno-save-analyzer@v0.3.0"
```

`[tui]` extra で Textual + textual-plotext が入る．CLI / ライブラリだけなら外して良い．

### ローカル clone (開発)

```bash
git clone https://github.com/yuuka-dev/anno-save-analyzer.git
cd anno-save-analyzer
uv sync --extra tui    # または: python -m venv .venv && .venv/bin/pip install -e '.[tui]'
```

### uv なし (plain pip)

```bash
pip install "anno-save-analyzer[tui] @ git+https://github.com/yuuka-dev/anno-save-analyzer@v0.3.0"
```

> PyPI 配信は v1.0 予定．それまで Git tag が正式配布経路．

## 使い方

すべて `anno-save-analyzer` コマンド配下．`--title` でゲーム (``anno117`` / ``anno1800``)，
`--locale` で UI 表記 (``en`` / ``ja``) を選ぶ．

### TUI を起動

```bash
anno-save-analyzer tui sample_anno117.a8s --title anno117 --locale ja
```

- `^X` 終了 · `^G` ヘルプ · `^T` 画面切替 · `^L` 言語切替 · `^O` CSV エクスポート
- 書記長カラー欲しいときは `--theme ussr`（title に ☭ prefix）
- 起動時は 5 ステージのロードゲージが stderr に流れる

### CLI で貿易を覗く

```bash
# 全 TradeEvent を JSON
anno-save-analyzer trade list sample_anno117.a8s --title anno117

# 物資別 / ルート別集計
anno-save-analyzer trade summary sample_anno117.a8s --title anno117 --by item
anno-save-analyzer trade summary sample_anno117.a8s --title anno117 --by route

# 2 セーブ間差分（added / removed / changed / unchanged）
anno-save-analyzer trade diff before.a8s after.a8s --title anno117 --locale ja
anno-save-analyzer trade diff before.a8s after.a8s --by route --show-unchanged
```

全サブコマンド stdout に JSON を吐くので `jq` / DuckDB / ノートブックにそのまま流せる．

### ヘルプ

```bash
anno-save-analyzer --help
anno-save-analyzer trade --help
anno-save-analyzer tui --help
```

## ロードマップ

| 版 | スコープ | 状態 |
|---|---|---|
| v0.1.0 | RDA V2.2 native parser | ✅ 完了 |
| v0.2.x | FileDB V3 parser，recursive SessionData，島メタ | ✅ 完了 (0.3.0 に統合) |
| **v0.3.0** | **Trade history viewer (Textual TUI + CLI + snapshot diff)** | ✅ **リリース済** |
| v0.4 | StorageTrends (島ごとの在庫時系列) TUI 統合 ([#23](https://github.com/yuuka-dev/anno-save-analyzer/issues/23)) | 🚧 次 |
| v0.4+ | データ量連動 progress gauge ([#26](https://github.com/yuuka-dev/anno-save-analyzer/issues/26))，Anno 1800 parity ([#24](https://github.com/yuuka-dev/anno-save-analyzer/issues/24)) | 計画中 |
| v0.5 | OR-Tools MILP ルート最適化 | 計画中 |
| v0.6 | DOM 全域の Pydantic 型化 (Island / Building / Population) | 計画中 |
| v1.0 | PyPI 配信，英語ドキュメント完備，API 安定化 | 計画中 |

詳細は [docs/ROADMAP.ja.md](docs/ROADMAP.ja.md) / [docs/ROADMAP.md](docs/ROADMAP.md) と [GitHub Milestones](https://github.com/yuuka-dev/anno-save-analyzer/milestones)．

## 技術スタック

| カテゴリ | 採用 |
|---|---|
| 言語 | Python 3.12+ |
| パッケージ管理 | uv (推奨), pip 互換 |
| CLI フレームワーク | typer |
| XML パーサ | lxml (`huge_tree=True`, `recover=True`) |
| データモデル | pydantic v2 |
| 集計 | pandas |
| TUI | [Textual](https://github.com/Textualize/Textual) + [textual-plotext](https://github.com/Textualize/textual-plotext) |
| 最適化 (任意, v0.5) | OR-Tools |
| Notebook (任意) | JupyterLab (`notebooks/island_inventory.ipynb` 用) |
| CI | GitHub Actions, pytest-cov, Codecov |
| Lint / format | ruff |

## アーキテクチャ

```text
sample_anno117.a8s  (RDA V2.2 コンテナ)
└─ data.a7s  (内部の zlib ストリーム)
   └─ outer FileDB V3
      ├─ <SessionData><BinaryData>  (セッション単位．再帰的 FileDB V3)
      │  ├─ AreaInfo > <1> > AreaEconomy > StorageTrends  (在庫時系列 — v0.4)
      │  ├─ AreaInfo > <1> > PassiveTrade > History > TradeRouteEntries / PassiveTradeEntries > …
      │  └─ ConstructionAI > TradeRoute > TradeRoutes > <1>  (idle 含む route 定義)
      └─ meta / header / gamesetup.a7s  (RDAArchive 層)
```

詳細は [docs/rda_format_spec.md](docs/rda_format_spec.md) / [docs/filedb_format_investigation.md](docs/filedb_format_investigation.md) を参照．

## テスト / 開発

```bash
uv run pytest --cov=anno_save_analyzer --cov-branch --cov-fail-under=100
uv run ruff check src tests
uv run ruff format --check src tests
```

実セーブ要のテストは save が無ければ auto-skip．`sample.a7s` / `sample_anno117.a8s` を repo root に置くか，`SAMPLE_A7S` / `SAMPLE_A8S` を指定．

## コントリビューション

PR 歓迎．[CONTRIBUTING.md](CONTRIBUTING.md) にブランチ戦略・コミットメッセージ規約（英語 subject + 任意の日本語本文）・Copilot レビュー方針・100% カバレッジ維持を記載．要点:

- Feature 作業は `feature/*` → `dev` → `release/*` → `main`．
- 全 PR は Copilot レビューを通し，CI 緑 + カバレッジ 100% を維持．
- パーサ追加時は format reference を `docs/` に書くこと．

## 免責事項

本プロジェクトは Ubisoft / Blue Byte / Anno フランチャイズとは**一切無関係**の third-party 読み取り専用解析ツールです．*Anno*, *Anno 1800*, *Anno 117: Pax Romana*, *Ubisoft*, *Blue Byte* は各社の商標です．

## 謝辞

- RDA V2.2 フォーマット: [@lysannschlegel/RDAExplorer](https://github.com/lysannschlegel/RDAExplorer)
- FileDB フォーマット: [anno-mods/FileDBReader](https://github.com/anno-mods/FileDBReader)
- 先行実装: [Anno1800SavegameVisualizer](https://github.com/NiHoel/Anno1800SavegameVisualizer), [AnnoSavegameViewer](https://github.com/Veraatversus/AnnoSavegameViewer), [anno1800-save-game-explorer](https://github.com/RobertLeePrice/anno1800-save-game-explorer)

## ライセンス

MIT — [LICENSE](LICENSE) 参照（ファイル追加予定）．
