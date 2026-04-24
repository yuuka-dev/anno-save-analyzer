# anno-save-analyzer

[![CI](https://github.com/yuuka-dev/anno-save-analyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/yuuka-dev/anno-save-analyzer/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/yuuka-dev/anno-save-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/yuuka-dev/anno-save-analyzer)
[![release](https://img.shields.io/github/v/release/yuuka-dev/anno-save-analyzer?include_prereleases)](https://github.com/yuuka-dev/anno-save-analyzer/releases/latest)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: alpha](https://img.shields.io/badge/status-alpha-orange)](docs/source/ja/roadmap.md)

> **一言で説明**: Anno 1800 / Anno 117: Pax Romana のセーブファイルを開いて，ゲーム内 UI に出てこない**貿易履歴**と**島ごとの在庫推移**をターミナルで見られるようにするツールです．

> **状態**: v0.4.2 リリース済．PyPI 配信は v1.0 で予定，現状は Git tag からインストール．English README: [README.md](README.md).

---

## どんな画面？

| 起動直後 (Overview 画面) |
| --- |
| ![Overview 画面．セーブのサマリ表示](docs/screenshots/tui-overview.png) |
| 読み込み終わった直後．取引イベント数 / ルート数 / セッション一覧 / 累計収支 g を一望できる． |

| 貿易履歴 (items タブ) | 島在庫 (inventory タブ) |
| --- | --- |
| ![items テーブル + sparkline + Partners pane + 累積チャート](docs/screenshots/tui-trade.png) | ![島ごとの在庫テーブル + 推移 chart](docs/screenshots/tui-inventory.png) |
| 物資ごとに買った量 / 売った量 / 純収支 / 取引先内訳 / 累積チャートを並べる．行選択で右側チャート + Partners pane が同期更新． | 島ごとの StorageTrends (最新 / ピーク / 平均 / 傾き + スパークライン)．行選択で直近の在庫推移を折れ線表示． |

---

## なぜ作ったか

Anno やっとるとよく困るやつ：

- **「このルート，実際いくら稼いでんの？」** — ゲーム内 UI では出えへん．
- **「どの島がどの物資を吸い込んでる？」** — 倉庫バー目視でがんばるしかない．
- **「Ubisoft AI と組んだ貿易，結局ペイした？」** — あとから確認する術がない．

これ全部セーブデータに入っとる．ただ独自の `.a7s` / `.a8s` アーカイブ→ zlib 圧縮→ FileDB バイナリ→さらに入れ子の FileDB という 4 重マトリョーシカに埋まっとるだけや．本プロジェクトは各層を Python で素通しで剥がして，TUI + CLI で読めるようにする．

---

## インストール

### 前提

Python **3.12 以上**．確認：

```bash
python --version
```

入ってなければ [uv](https://github.com/astral-sh/uv) 入れるんが一番ラク．Python 本体の用意まで uv がやってくれる．

### 1 行インストール (推奨)

```bash
# TUI + CLI を standalone tool として入れる (venv 管理不要)
uv tool install "anno-save-analyzer[tui] @ git+https://github.com/yuuka-dev/anno-save-analyzer@v0.4.2"
```

これで `anno-save-analyzer` コマンドがどこからでも使える．

### 代替: plain pip

```bash
pip install "anno-save-analyzer[tui] @ git+https://github.com/yuuka-dev/anno-save-analyzer@v0.4.2"
```

### 代替: ローカル clone (開発者向け)

```bash
git clone https://github.com/yuuka-dev/anno-save-analyzer.git
cd anno-save-analyzer
uv sync --extra tui        # または: python -m venv .venv && .venv/bin/pip install -e '.[tui]'
```

> `[tui]` extra で Textual + textual-plotext が入る．CLI / ライブラリだけで良ければ外して可．

---

## 初回実行 — 手順

### 1. セーブファイルの場所を確認

Anno のセーブはユーザードキュメント配下にある：

| ゲーム | デフォルト保存先 (Windows) |
| --- | --- |
| Anno 1800 | `%USERPROFILE%\Documents\Anno 1800\accounts\<アカウント ID>\savegame\` |
| Anno 117 | `%USERPROFILE%\Documents\Anno 117 - Pax Romana\accounts\<アカウント ID>\savegame\` |

`.a7s` (Anno 1800) か `.a8s` (Anno 117) を任意の場所にコピーしておく．**本ツールは読み取り専用，セーブを書き換えることは絶対にない**から元ファイル直読みでも問題ないが，念のためコピーを触るのが安全．

### 2. TUI 起動

```bash
# Anno 117 のセーブ
anno-save-analyzer tui path/to/your_save.a8s --title anno117 --locale ja

# Anno 1800 のセーブ
anno-save-analyzer tui path/to/your_save.a7s --title anno1800 --locale ja
```

5 段階のロードゲージが流れて Overview 画面 (1 枚目のスクショ) が出る．

### 3. 操作

ホットキーは footer に常時表示．主要なもの：

| キー | 動作 |
| --- | --- |
| `Ctrl+T` | **Overview** と **Statistics** 画面の切替 |
| `Ctrl+L` | 英語 / 日本語切替 |
| `Ctrl+R` | chart 時間窓を cycle (直近 120 分 → 4 h → 12 h → 24 h → 全期間) |
| `Ctrl+P` | 直近取引 pane の時間窓を選択 (60 / 120 / 360 分 / 24 h / 全期間) |
| `Ctrl+O` | 現在のビューを CSV に export |
| `Ctrl+G` | ヘルプ画面 |
| `Ctrl+X` | 終了 |

**Statistics** 画面では左の tree でセッション / 島をクリックすると，中央テーブル・Partners pane・チャート・CSV export すべてがその粒度に絞り込まれる．

### 4. (任意) JSON / CSV でデータを取り出す

notebook や表計算に流したい場合：

```bash
# 個別 trade を全部 JSON で stdout
anno-save-analyzer trade list your_save.a8s --title anno117

# 物資別 / ルート別集計
anno-save-analyzer trade summary your_save.a8s --title anno117 --by item
anno-save-analyzer trade summary your_save.a8s --title anno117 --by route

# 2 セーブ間差分
anno-save-analyzer trade diff before.a8s after.a8s --title anno117
```

全サブコマンド stdout に JSON を吐くので `jq` / pandas / DuckDB にそのまま流せる．

---

## 分析 (v0.5 preview)

v0.5 で **pandas ベースの SCM 分析層**を追加．書記長の Decision Matrix に
沿って 7 個の analyzer が並ぶ：「どこが不足か / 慢性か / どのルートが弱いか
/ 何をすべきか」．

### 全 state を JSON に (notebook 用 one-liner)

```bash
anno-save-analyzer state sample_anno1800.a7s --title anno1800 --locale ja \
    --out state.json
```

overview + islands + tier breakdown + balance + 全 TradeEvent を 1 JSON に
ダンプ．書記長の岡山帝国サイズで `~970 KB`．`pandas.read_json` /
`pandas.json_normalize` で即分析可能．

### DataFrame 層 (Python)

```python
from anno_save_analyzer.analysis import to_frames
from anno_save_analyzer.tui.state import load_state
from anno_save_analyzer.trade.models import GameTitle

state = load_state("sample_anno1800.a7s", title=GameTitle.ANNO_1800, locale="ja")
f = to_frames(state)

# 島別 赤字物資数ランキング
f.islands[["city_name", "deficit_count", "resident_total"]] \
    .sort_values("deficit_count", ascending=False).head(10)

# tier ピボット (島 × tier の人口マトリクス)
f.tiers.pivot_table(values="resident_total", index="city_name",
                    columns="tier", fill_value=0)
```

### Decision Matrix (書記長本命の処方箋エンジン)

```python
from anno_save_analyzer.analysis.prescribe import diagnose, Thresholds

rx = diagnose(f, storage_by_island=state.storage_by_island)

print(rx["category"].value_counts())
# increase_production    慢性 deficit × 高満足度 × 航路あり → 生産増一択
# rebalance_mix          航路強いのに delta<0 → 商品構成見直し
# trade_flex             一過性 deficit × 低相関 × 航路弱い → 取引・融通
# ok                     黒字
# monitor                rule 適用外 → 継続観察

# 岡山の処方箋
rx[rx["city_name"] == "大都会岡山"] \
    [["product_name", "category", "action", "rationale"]].head(20)
```

閾値チューニング: `diagnose(f, thresholds=Thresholds(high_saturation=0.60))`．

### 他の analyzer

| module | function | 用途 |
|---|---|---|
| `analysis.deficit` | `deficit_heatmap`, `pareto` | 島×物資マトリクス + ABC/Pareto |
| `analysis.correlation` | `saturation_vs_deficit` | 物資別 Pearson + Spearman |
| `analysis.routes` | `rank_routes` | route ごと tons/min, gold/min |
| `analysis.persistence` | `classify_deficit` | chronic / transient / stable |
| `analysis.sensitivity` | `route_leave_one_out` | 「船 1 隻減らすならどこ？」 |
| `analysis.forecast` | `consumption_forecast`, `population_capacity_proxy` | 短期線形投影 |

全 analyzer が **Anno 117 / Anno 1800 両対応** (title 非依存 pandas in/out)．

---

## 機能一覧 (v0.4.2)

### Textual TUI

- **3 カラム構成**: セッション / 島 tree · items / routes / inventory テーブル · Partners pane + 時系列チャート
- **Tree フィルタ**: session / island ノードをクリックすると全 pane が絞り込まれる
- **Inventory タブ**: 島ごとの StorageTrends を latest / peak / mean / slope + sparkline で表示．行選択で時系列チャート
- **可変レイアウト**: wide (≥120) / mid (80–119) / narrow (<80) breakpoint で列を自動出し分け
- **カスタムルート名**: Anno 117 セーブからゲーム内ルート名を抽出．生の `route_id` ではなく書記長が付けた名前で表示
- **直近取引 pane**: 物資を選ぶと Partners pane 下に最新 50 件が「N 分前 / N 時間前」ラベル付きで並ぶ
- **Chart 時間窓** (`Ctrl+R`): デフォルト直近 120 分．200 時間級セーブでも最近の動きが見える
- **Sparkline 列** (`▁▂▃▄▅▆▇█`) で累積推移
- **英 / 日ロケール切替**，セッション名も翻訳
- **テーマ** (`--theme ussr` で赤黒 + ☭ prefix)
- **設定永続化**: locale / theme / 各種窓を `~/.config/anno-save-analyzer/config.toml` に保存 (XDG 準拠，Windows は `%APPDATA%`)．`ANNO_SAVE_ANALYZER_CONFIG` で任意パスに上書き可

### CLI

- `trade list <save>` — 全 TradeEvent を JSON (`--island` / `--session` フィルタ)
- `trade summary <save> --by item|route` — 集計
- `trade diff <before> <after>` — 2 セーブ間 added / removed / changed / unchanged
- `tui <save>` — TUI 起動

### Parser

- **RDA V2.2** コンテナ parser ([@lysannschlegel/RDAExplorer](https://github.com/lysannschlegel/RDAExplorer) の clean-room port)．`.a7s` / `.a8s` 両対応．
- **FileDB V3** streaming DOM + tag/attrib 辞書 + SessionData 再帰抽出
- **Anno 117 interpreter**: `PassiveTrade > History > {TradeRouteEntries,PassiveTradeEntries}` + `ConstructionAI > TradeRoute > TradeRoutes` (idle route 含む)
- NPC 同士の取引は `AreaInfo > CityName` ゲートで除外

### データパイプライン

- `items_anno117.{en,ja}.yaml` をゲーム本体の `config.rda/assets.xml` + `texts_japanese.xml` から自動生成 (151 Products × 33,146 翻訳行)．ゲームアップデート時は `scripts/generate_items_anno117.py` で再生成．

### テスト

- 400+ tests，**branch coverage 下限 90%** を CI で強制 (`pyproject.toml` の `fail_under = 90`)．純関数層 (`parser/*` / `trade.*`) は実質 100% を維持．90% 下限は async Textual UI の `pragma: no cover` 戦いを緩和するための余白．
- Python 3.12 / 3.13 両対応．

---

## 内部構造

Anno のセーブは入れ子コンテナ：

1. `.a7s` / `.a8s` — RDA V2.2 アーカイブ (Anno 1404 / 2070 / 2205 / 1800 / 117 共通)
2. 内部の `data.a7s` — zlib 圧縮ストリーム
3. 解凍後: FileDB V3 バイナリ
4. `<SessionData><BinaryData>` — 各ゲームセッション (ラティウム / アルビオン / 旧世界 …) に対応した FileDB V3 ドキュメントが丸ごと埋まっている
5. 内側: `AreaInfo` / `PassiveTrade > History` / `ConstructionAI > TradeRoute` 等

```text
sample_anno117.a8s  (RDA V2.2 コンテナ)
└─ data.a7s  (内部の zlib ストリーム)
   └─ outer FileDB V3
      ├─ <SessionData><BinaryData>  (セッション単位．再帰的 FileDB V3)
      │  ├─ AreaInfo > <1> > AreaEconomy > StorageTrends  (在庫時系列)
      │  ├─ AreaInfo > <1> > PassiveTrade > History > TradeRouteEntries / PassiveTradeEntries > …
      │  └─ ConstructionAI > TradeRoute > TradeRoutes > <1>  (idle 含む route 定義)
      └─ meta / header / gamesetup.a7s  (RDAArchive 層)
```

詳細は [docs/source/reference/rda_format_spec.md](docs/source/reference/rda_format_spec.md) / [docs/source/reference/filedb_format_investigation.md](docs/source/reference/filedb_format_investigation.md) を参照．

---

## ロードマップ

| 版 | スコープ | 状態 |
| --- | --- | --- |
| v0.1.0 | RDA V2.2 native parser | ✅ 完了 |
| v0.2.x | FileDB V3 parser，recursive SessionData，島メタ | ✅ 完了 (0.3.0 に統合) |
| v0.3.0 | Trade history viewer (Textual TUI + CLI + snapshot diff) | ✅ リリース済 |
| v0.4.0 | 島ごと在庫推移 + Tree filter + 可変レイアウト | ✅ リリース済 |
| v0.4.1 | 在庫 chart x 軸を相対時間表記に | ✅ リリース済 |
| **v0.4.2** | **ルート名表示 + chart 時間窓 + 直近取引 pane + 設定永続化** | ✅ **リリース済** |
| v0.4+ | データ量連動 progress gauge ([#26](https://github.com/yuuka-dev/anno-save-analyzer/issues/26))，Anno 1800 parity ([#24](https://github.com/yuuka-dev/anno-save-analyzer/issues/24)) | 計画中 |
| v0.5 | OR-Tools MILP ルート最適化 | 計画中 |
| v0.6 | DOM 全域の Pydantic 型化 (Island / Building / Population) | 計画中 |
| v1.0 | PyPI 配信，英語ドキュメント完備，API 安定化 | 計画中 |

詳細は [docs/source/ja/roadmap.md](docs/source/ja/roadmap.md) / [docs/source/roadmap.md](docs/source/roadmap.md) と [GitHub Milestones](https://github.com/yuuka-dev/anno-save-analyzer/milestones)．

---

## 技術スタック

| カテゴリ | 採用 |
| --- | --- |
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

---

## テスト / 開発

```bash
uv run pytest --cov=anno_save_analyzer --cov-branch --cov-config=pyproject.toml
uv run ruff check src tests
uv run ruff format --check src tests
```

`fail_under` は `pyproject.toml` から読まれる (現状 90%)．

実セーブ要のテストは save が無ければ auto-skip．`sample.a7s` / `sample_anno117.a8s` を repo root に置くか，`SAMPLE_A7S` / `SAMPLE_A8S` を指定．

---

## トラブルシュート

- **`anno-save-analyzer: command not found`** — `uv tool install` が PATH に bin dir を足してないパターン．`uv tool update-shell` 実行 (ターミナル再起動要) か `uv run anno-save-analyzer ...` で起動．
- **画面が真っ黒 / 崩れる** — Textual は TTY 必須．Windows なら Windows Terminal か最新 PowerShell を使う．`cmd.exe` はアカン．
- **`ValueError: unsupported RDA version`** — そのファイルは Anno 1800 / 117 のセーブじゃない (mod かもしくは他の Anno タイトル)．V2.2 コンテナしか対応してない．
- **trade 一覧が空** — `--title` 間違い．アイテム名 / セッション名が生 GUID フォールバックになって，trade extractor が interpreter を引けてない状態．セーブ元のゲームに合わせて `--title` 指定．

---

## コントリビューション

PR 歓迎．[CONTRIBUTING.md](CONTRIBUTING.md) にブランチ戦略・コミットメッセージ規約（英語 subject + 任意の日本語本文）・Copilot レビュー方針・カバレッジ下限を記載．要点：

- Feature 作業は `feature/*` → `dev` → `release/*` → `main`
- 全 PR は Copilot レビューを通し，CI 緑 + branch coverage ≥ 90% を維持
- パーサ追加時は format reference を `docs/` に書くこと

---

## 免責事項

本プロジェクトは Ubisoft / Blue Byte / Anno フランチャイズとは**一切無関係**の third-party 読み取り専用解析ツールです．*Anno*, *Anno 1800*, *Anno 117: Pax Romana*, *Ubisoft*, *Blue Byte* は各社の商標です．

## 謝辞

- RDA V2.2 フォーマット: [@lysannschlegel/RDAExplorer](https://github.com/lysannschlegel/RDAExplorer)
- FileDB フォーマット: [anno-mods/FileDBReader](https://github.com/anno-mods/FileDBReader)
- 先行実装: [Anno1800SavegameVisualizer](https://github.com/NiHoel/Anno1800SavegameVisualizer), [AnnoSavegameViewer](https://github.com/Veraatversus/AnnoSavegameViewer), [anno1800-save-game-explorer](https://github.com/RobertLeePrice/anno1800-save-game-explorer)

## ライセンス

MIT — [LICENSE](LICENSE) 参照．
