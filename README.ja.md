# anno-save-analyzer

> **一言で説明**: Anno 1800 / 117: Pax Romana のセーブデータ (`.a7s` / `.a8s`) を解析し，サプライチェーン最適化・可視化・統計ダッシュボードを提供するツール．

> **開発中 (Work in Progress)**: 本プロジェクトは現在活発に開発中であり，コミット間で API が変更されることがあります．English README: [README.md](README.md).

## 概要

### なぜ作ったのか

Anno 1800 のサプライチェーン最適化を手作業でやるのが辛くなったため，セーブデータを直接読んで島ごとの収支・ルート効率・クエスト進捗を可視化する専用ツールとして起ち上げた．既存の [Anno1800SavegameVisualizer](https://github.com/NiHoel/Anno1800SavegameVisualizer) などは .NET 前提でローカル環境との相性が悪く，Python + WSL2 で完結する独自実装を選んだ．

## 主な機能（v0.1.0 時点）

- `.a7s` RDA V2.2 コンテナの Python ネイティブ parser
  - magic / header / block chain / directory entry / per-file zlib 解凍に対応
  - context manager API: `with RDAArchive(path) as rda: ...`
  - `entries` / `read(name)` / `extract(...)` / `extract_all(...)`
  - [lysannschlegel/RDAExplorer](https://github.com/lysannschlegel/RDAExplorer) を仕様のみ参考にした clean-room 実装
- `parser.pipeline.extract_inner_filedb` — `.a7s` から内部 FileDB バイナリを 1 コールで取り出し

## ロードマップ

| バージョン | スコープ | ステータス |
|---|---|---|
| v0.1.0 | RDA V2.2 native parser | 完了 |
| v0.2 | FileDB V1/V2/V3 parser, ルートデータのモデル化 | 次 |
| v0.3 | `SessionData` / `BinaryData` 解読（本丸） | 未着手 |
| v0.4 | 島ごとサプライチェーン balance 表 | 未着手 |
| v0.5 | OR-Tools MILP ルート最適化 | 未着手 |
| v0.6 | Tauri v2 デスクトップ GUI | 未着手 |
| v1.0 | 公開リリース，英語ドキュメント化 | 未着手 |
| v1.1 | Anno 117 (`.a8s`) 対応 | 未着手 |

## 技術スタック

| カテゴリ | 技術 |
|---|---|
| 言語 | Python 3.12+ |
| パッケージ管理 | uv（推奨），pip 互換 |
| XML パーサ | lxml (`huge_tree=True`, `recover=True`) |
| データモデル | pydantic v2 |
| 集計 | pandas |
| 最適化（optional） | OR-Tools |

## アーキテクチャ

```text
sample.a7s  (RDA V2.2 container)
    └─ data.a7s  (zlib compressed)
        └─ FileDB binary  (V1/V2/V3, Blue Byte 独自形式)
            └─ data.xml  (219万行超の XML ツリー)
                └─ <SessionData><BinaryData>  (未解読)
```

RDA V2.2 フォーマットの詳細は [docs/rda_format_spec.md](docs/rda_format_spec.md) を参照．

## はじめ方

### 前提条件

- Python 3.12 以上
- `uv`（推奨）または `pip`
- エンドツーエンド動作確認用の実セーブ（`.a7s`）．ユニットテストは合成フィクスチャで動くため実セーブ無しで通る

### インストール

```bash
git clone https://github.com/yuuka-dev/anno-save-analyzer.git
cd anno-save-analyzer
uv sync          # または: python -m venv .venv && .venv/bin/pip install -e .
```

### クイックスタート

```python
import zlib
from anno_save_analyzer.parser.rda import RDAArchive

with RDAArchive("Autosave 182.a7s") as rda:
    for e in rda.entries:
        print(e.filename, e.uncompressed_size)

    data_bytes = rda.read("data.a7s")
    filedb_bytes = zlib.decompress(data_bytes)
    # filedb_bytes は FileDB V2 バイナリ（大体の終盤セーブで 165MB 前後）
```

### テスト実行

```bash
uv run pytest
# または: .venv/bin/python -m pytest
```

実セーブが必要なテストは未配置時に自動 skip される．走らせたい場合は repo root に `sample.a7s` を置くか，環境変数 `SAMPLE_A7S` でパスを指定する．

## 免責事項

本プロジェクトは Ubisoft / Blue Byte / Anno シリーズと**一切関係のない**非公式ツールです．読み取り専用の解析ツールであり，セーブ編集や改造は行いません．*Anno*，*Anno 1800*，*Anno 117: Pax Romana*，*Ubisoft*，*Blue Byte* は各社の商標です．

## 謝辞

- Based on the reverse-engineering work of [@lysannschlegel's RDAExplorer](https://github.com/lysannschlegel/RDAExplorer).
- FileDB フォーマット調査は [anno-mods/FileDBReader](https://github.com/anno-mods/FileDBReader) を参考．
- 先行事例 / インスピレーション: [Anno1800SavegameVisualizer](https://github.com/NiHoel/Anno1800SavegameVisualizer), [AnnoSavegameViewer](https://github.com/Veraatversus/AnnoSavegameViewer), [anno1800-save-game-explorer](https://github.com/RobertLeePrice/anno1800-save-game-explorer).

## ライセンス

MIT License．詳細は [LICENSE](LICENSE)（今後追加）を参照．
