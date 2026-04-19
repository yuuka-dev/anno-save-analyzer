# FileDB (BBDom) Format Investigation

> 調査日: 2026-04-19. 対象: `sample.a7s` の内部 `data.a7s` を zlib 解凍した後のバイナリ（173,321,048 B = 約 165 MB）．
>
> 参照: [anno-mods/FileDBReader](https://github.com/anno-mods/FileDBReader) の `FileDBSerializer` 実装．特に
> `IO/VersionDetector.cs`, `IO/Parsing/Versions/BBStructureParser_V2.cs`,
> `IO/Parsing/BBDocumentParser.cs`, `Document/Versioning.cs`．
>
> 本ドキュメントは clean-room Python 再実装に向けた spec まとめ．FileDBReader のコードは転載せず，
> 読解結果を日本語で再構成する．

## 1. バージョンとマジックバイト

FileDB は **ファイル末尾 8 バイトを magic として持つ**（先頭ではない点に注意）．

| Version | Magic (末尾 8B) | 備考 |
|---|---|---|
| V1 | （無し） | 判別不能．V2/V3 でマッチしなかった場合の fallback |
| V2 | `08 00 00 00 FE FF FF FF` | Anno 2070 / 2205 系 |
| V3 | `08 00 00 00 FD FF FF FF` | **Anno 1800 セーブはこれ** |

### sample.a7s での実測

```
file size = 173,321,048 (0x0A54AB58)
last 8 B  = 08 00 00 00 fd ff ff ff  → V3 確定
```

## 2. ファイル全体レイアウト

```
+------------------------------------------------------------+ offset 0
| DOM section                                                |
|   Tag / Attrib / Terminator のストリーム（後述）          |
|   終端は level が -1 になる余分な Terminator               |
|                                                            |
| Tag name dictionary                                        |
|   @ TagsOffset                                             |
|                                                            |
| Attrib name dictionary                                     |
|   @ AttribsOffset                                          |
+------------------------------------------------------------+ Length - 16
| OffsetToOffsets block (16 B)                               |
|   TagsOffset: int32 LE                                     |
|   AttribsOffset: int32 LE                                  |
+------------------------------------------------------------+ Length - 8
| Magic (8 B)                                                |
+------------------------------------------------------------+ Length
```

### sample.a7s での実測

| 項目 | 値 |
|---|---|
| TagsOffset | 173,302,664 (0x0A546388) |
| AttribsOffset | 173,310,912 (0x0A5483C0) |
| Tag 辞書サイズ | 8,248 B → **465 タグ** |
| Attrib 辞書サイズ | 10,120 B → **558 属性** |

## 3. Tag / Attrib 辞書の構造

V2 / V3 共通（`BBStructureParser_V2.ParseDictionary`）：

```
[Count : int32 LE]
[ID_0 : uint16 LE]
[ID_1 : uint16 LE]
...
[ID_{Count-1} : uint16 LE]
[Name_0 : UTF-8 null-terminated]
[Name_1 : UTF-8 null-terminated]
...
[Name_{Count-1} : UTF-8 null-terminated]
```

IDs と Names は同じ順序で対応する．Attrib 辞書の ID は **0x8000 (32768) 以上** の値を使うことで Tag ID と区別する（後述の DOM 走査ロジックで効く）．

### sample.a7s 辞書サンプル

#### Tag 辞書（id 昇順から 15 件）

```
id=2   MetaGameManager
id=3   NetworkSafeRandom
id=4   FunFactSettings
id=5   PlayerCounter
id=6   value
id=7   ValueType
id=8   Scope
id=9   PeerToSessionMap
id=10  OwnedScenarioItems
id=11  MetaUnlockManager
id=12  LockState
id=13  NotificationSystem
id=14  LocalPeer
id=15  Queue
id=16  NotificationType
```

#### Attrib 辞書（id 昇順から 15 件）

```
id=32769  GameCount
id=32770  GameTotal
id=32771  CreatingAccountID
id=32772  P2
id=32773  Buffer
id=32774  Counter
id=32775  id
id=32776  Value
id=32777  TextGUID
id=32778  CounterContext
id=32779  FactNumber
id=32780  StartSessionGUID
id=32781  LastActiveSession
id=32782  CurrentlyActiveSession
id=32783  value
```

#### 興味深いタグ（Area / Quest / Trade 系の抜粋）

`AreaCounter`, `AreaList`, `AreaOwner`, `AreaTriggered`, `AreaUniques`,
`CharterRouteDescription`, `CurrentTradeStatus`, `GameSessions`,
`LastTradesPerModule`, `MetaTrader`, `QuestAssignee`, `QuestBlockings`,
`QuestData`, `QuestDelays`, `QuestDifficulty`, `QuestGUID`, `QuestHistory`,
`QuestID`, `QuestInstanceFactory`, `QuestLatencies`, ...

→ **本プロジェクトの目的（ルート / クエスト / 島解析）に必要なタグは実際に存在する**ことを確認．

## 4. DOM セクションの走査

DOM は `Tag` / `Attrib` / `Terminator` のフラットなストリーム．

### 1 ノードの読み取り（`ReadNextOperation`）

```
[bytesize : int32 LE]
[id       : int32 LE]   ← 実質 uint16 として扱う（上位 16 ビットは無視）
```

### State 判定（`DetermineState`）

| id の値 | State | 意味 |
|---|---|---|
| `id >= 32768` (0x8000 以上) | **Attrib** | 属性．この後 content が続く |
| `0 < id < 32768` | **Tag** | 新しい入れ子を開く |
| `id <= 0` | **Terminator** | 現在の Tag を閉じる |
| その他 | Undefined | エラー |

### Attrib のコンテンツ読み取り

V2 / V3 では **8 バイト境界にパディング**される：

```
content_on_disk_size = ceil(bytesize / 8) * 8
content_bytes = stream.read(content_on_disk_size)[:bytesize]
```

V1 は block size = 0（パディング無し）．

### Terminator のペア規則

各 Tag は対応する Terminator（id <= 0, bytesize = 0）で閉じる．
DOM 全体の終端は `CurrentLevel` が `-1` に落ちた時点（ルートレベルの Tag を閉じる追加 Terminator）．

## 5. 実データでの走査例

sample.a7s の先頭 200 バイトを走査した結果：

```
Tag        id=2      MetaGameManager
  Attrib     id=32769  GameCount             (4B  = 0x000007C2 68)
  Attrib     id=32770  GameTotal             (8B  = 0x0307F0A0)
  Attrib     id=32771  CreatingAccountID     (36B UTF-8 GUID "499a897b-388d-4212-9179-c1ac7dc6c91c")
  Tag        id=3      NetworkSafeRandom
    Attrib     id=32772  P2                    (4B)
    Attrib     id=32773  Buffer                (68B PRNG state)
    Attrib     id=32774  Counter               (4B = 0x00B91665)
  Terminator
  Tag        id=4      FunFactSettings
    Tag        id=5      PlayerCounter
      Tag        id=6      value
        Attrib     id=32775  id                    (2B = 0x0000)
      Terminator
    ...
```

**観察**：
- `Attrib` の中身はプリミティブ型（int32 / int64 / UTF-8 / float / fixed struct）．型は tag/attrib 名から解釈する必要あり（FileDBReader では `FileFormats/*.xml` に interpreter 定義がある）．
- 入れ子は ECS / Entity-Component 的な構造．
- GUID は 36 文字の UTF-8 文字列（`"xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"`）．

## 6. エンコーディング・バイトオーダー

| 項目 | 規則 |
|---|---|
| バイトオーダー | Little Endian 固定 |
| 文字列（辞書内名前） | UTF-8 null-terminated |
| 文字列（Attrib content 内） | 主に UTF-8．GUID / path などは固定長ではなく末尾 null 有無は interpreter 側で判断 |
| 数値 | int32 / int64 / uint16 / float32 / float64 が混在．Attrib 名で切り分ける |

## 7. 未解決事項

1. **Attrib 内部の型解釈** — 生バイトの段階では raw．実用化には「このタグ配下のこの attrib は int64」という interpreter 辞書が必要．FileDBReader の `FileFormats/*.xml` 互換のマッピングを移植する or 本プロジェクトで独自の interpreter (YAML) を持つか検討．
2. **SessionData / BinaryData** — 本層（FileDB）の decode はこれで完了だが，`<SessionData><BinaryData>` タグ配下の **Attrib として埋め込まれた再バイナリ** は別形式（CLAUDE.md に既述の「マトリョーシカ」最深層）．v0.3 の課題．
3. **V1 判別の曖昧さ** — FileDBReader 自身も「V2/V3 じゃなければ V1」としてる．V1 保有 save は現行の Anno 1800 では出現しないはずだが，mod 経由の旧形式が来たら要注意．

## 8. v0.2 実装方針

| Step | 内容 | 依存 |
|---|---|---|
| 1 | `parser.filedb.version` で末尾 magic から V1/V2/V3 判定 | 既存 RDA parser |
| 2 | `parser.filedb.dictionary` で tag / attrib 辞書を decode | Step 1 |
| 3 | `parser.filedb.dom` で DOM を iterator / streaming で yield | Step 2 |
| 4 | `parser.filedb.xml` で lxml Element に変換（huge_tree=True） | Step 3 |
| 5 | Pydantic model 層（Area / Route / Quest）を docs/tag_mapping.yaml で interpreter 駆動 | Step 4 |

メモリ制約：**165MB を一気にメモリに載せず，DOM は streaming で流す** 設計が重要．lxml の SAX-like な `iterparse` 的 API を模倣する．

## 9. Anno 117: Pax Romana サンプルでの追加検証（2026-04-19 追補）

書記長所有の ``sample_anno117.a8s`` (881KB) でも同様に解析を実施．

| 項目 | Anno 1800 (`sample.a7s`) | Anno 117 (`sample_anno117.a8s`) |
|---|---|---|
| 外殻 RDA magic | ``Resource File V2.2`` | **``Resource File V2.2``（完全同一）** |
| RDA 内エントリ | 4 件（``meta/header/gamesetup/data.a7s``） | **4 件（同名）** |
| ``data.a7s`` 展開後 | 173,321,048 B | 17,715,512 B（約 10%） |
| FileDB magic | ``08 00 00 00 FD FF FF FF`` → V3 | **同一 → V3** |
| Tag 辞書件数 | 465 | 575 |
| Attrib 辞書件数 | 558 | 448 |
| DOM 先頭バイトパターン | ``00 00 00 00 02 00 00 00 04 00 00 00 01 80 00 00`` | **同一パターン** |

### 含意

- **フォーマット層（RDA → zlib → FileDB V3）は Anno 1800 / Anno 117 で完全同一**．
- 差分は **タグ / 属性の辞書（ゲーム固有の意味論）** のみ．
- 既存の v0.1.0 RDA parser は **追加実装なしで Anno 117 もそのまま読める**ことをテストで確認済み．
- v0.2 で FileDB parser を実装した時点で，**Anno 117 の DOM 走査と XML 化も自動的に可能**．interpreter 層（どのタグがどの型か）を両ゲーム分で持つだけで済む．

### ロードマップへの影響

元の roadmap では **Anno 117 対応は v1.x（バージョン未定の Future）** に置いていたが，実質的に：

- v0.2 (FileDB parser) 完了時点で，Anno 117 の構造解析は**副産物として完了**．
- 残作業は「Anno 117 固有のタグ解釈 + supply-chain の違い」程度．
- したがって **v1.0 リリース時点で Anno 117 alpha 対応は現実的**（roadmap 検討事項）．

## 10. 参考・謝辞

- **FileDBReader** (GPL-v3) by [@anno-mods](https://github.com/anno-mods/FileDBReader) — 先駆的リバースエンジニアリング．
- **First version of FileDB unpacking** by @VeraAtVersus．
- **BB 独自形式のリバースエンジニアリング** by @lysannschlegel．

本プロジェクトはこれら上流の成果を**仕様学習のみ**参照し，clean-room で Python 再実装する．`refs/FileDBReader/` は読取専用のローカル参照として配置，`.gitignore` 済で成果物に同梱しない．
