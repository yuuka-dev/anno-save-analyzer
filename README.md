# anno-save-analyzer

> **一言で説明**: Anno 1800 / 117: Pax Romana のセーブデータ (`.a7s` / `.a8s`) を解析し，サプライチェーン最適化・可視化・統計ダッシュボードを提供するツール．

## 概要

### なぜ作ったのか

Anno 1800 のサプライチェーン最適化を手作業でやるのが辛くなったため，セーブデータを直接読んで島ごとの収支・ルート効率・クエスト進捗を可視化する専用ツールとして起ち上げた．既存の [Anno1800SavegameVisualizer](https://github.com/NiHoel/Anno1800SavegameVisualizer) などは .NET 前提でローカル環境との相性が悪く，Python + WSL2 で完結する独自実装を選んだ．

## 主な機能

- `.a7s` RDA コンテナの Python ネイティブ解凍（**v0.1.5 で実装中**）
- FileDB (V1/V2/V3) バイナリの解析
- サプライチェーン balance 表・ルート最適化提案（将来）
- Anno 117 (`.a8s`) 対応（将来）

## 技術スタック

| カテゴリ | 技術 |
|---|---|
| 言語 | Python 3.12+ |
| パッケージ管理 | uv |
| XML パーサ | lxml (`huge_tree=True`) |
| データモデル | pydantic v2 |
| 集計 | pandas |
| 最適化 | OR-tools (optional) |

## アーキテクチャ

"""
sample.a7s (RDA container, V2.2)
    └─ data.a7s (zlib compressed)
        └─ FileDB binary (V1/V2/V3)
            └─ data.xml (lxml, 219万行超)
                └─ <SessionData><BinaryData> (未解読)
"""

詳細は [docs/rda_format_spec.md](docs/rda_format_spec.md) を参照．

## はじめ方

### 前提条件

- Python 3.12 以上
- uv（推奨）または pip

### セットアップ

```bash
uv sync
```

### テスト

```bash
uv run pytest
```

## 謝辞

- Based on the reverse engineering work of [@lysannschlegel's RDAExplorer](https://github.com/lysannschlegel/RDAExplorer).
- FileDB フォーマット調査は [anno-mods/FileDBReader](https://github.com/anno-mods/FileDBReader) を参照．

## ライセンス

MIT License．詳細は LICENSE を参照．
本ツールは Ubisoft / Blue Byte / Anno シリーズと一切関係のない非公式ツールです．
