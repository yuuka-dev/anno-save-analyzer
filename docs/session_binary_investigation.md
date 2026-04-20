# SessionData / BinaryData Investigation Result

> 調査日: 2026-04-19．対象: ``sample.a7s`` を FileDB V3 parser で走査し，
> ``<SessionData>`` 配下の ``<BinaryData>`` Attrib content を抽出して解析．

## TL;DR

**仮説 1（再帰 FileDB V3）が確定．** 外側 FileDB 内の 5 個の ``<BinaryData>`` は，
いずれも**末尾マジック ``08000000FDFFFFFF`` を持つ完全な FileDB V3 文書**だった．
既存の ``parser.filedb`` を**そのまま再帰適用**するだけで，島 / 建物 / 人口系の
階層データが取得できる．

## 手順

1. 外側 ``data.a7s`` 解凍後の FileDB を parse
2. タグ辞書から ``SessionData`` (id=466) と ``BinaryData`` (attrib id=33326) を解決
3. DOM 走査中，``<SessionData>`` スコープ内の ``<BinaryData>`` attrib content を 5 件収集
4. 各 blob を ``detect_version`` → V3 確定
5. それぞれを再度 FileDB として ``parse_tag_section`` + ``iter_dom`` に食わせる

## 5 セッションの実測値

| # | サイズ | Shannon entropy (bytes) | 末尾マジック |
|---|---|---|---|
| 0 | 22,853,288 B | 0.411 | `08000000FDFFFFFF` ✅ |
| 1 | 32,038,880 B | 0.707 | `08000000FDFFFFFF` ✅ |
| 2 | 32,671,384 B | 0.879 | `08000000FDFFFFFF` ✅ |
| 3 | 37,571,112 B | 0.496 | `08000000FDFFFFFF` ✅ |
| 4 | 24,477,728 B | 0.552 | `08000000FDFFFFFF` ✅ |

全て V3 magic 一致．entropy の低さ（0.4〜0.9 bit / byte）は DOM の反復構造（``[bytesize][id]`` の規則的なパターンと大量の 0 埋め属性）で説明がつく．追加圧縮（仮説 3）の必要なし．

先頭 24 バイト共通:

```
04 00 00 00 01 80 00 00 1D 00 00 00 00 00 00 00 00 00 00 00 02 00 00 00
└─ bytesize=4 ─┘ └─ id=0x8001 ─┘ └─ content 4B ─┘ └─ bytesize=0 ─┘ └─ id=2 ─┘
        Attrib id=1 "SessionFileVersion?" = 29 (0x1D)      Tag "GameSessionManager"
```

5 セッションとも **同じ先頭パターン**から始まる．

## Session 0 の内部構造（先頭 30 op）

```
attrib  SessionFileVersion (4B)
tag     GameSessionManager
  tag     MapTemplate
    attrib  Size (8B)
    attrib  PlayableArea (16B)
    attrib  InitialPlayableArea (16B)
    tag     RandomlyPlacedThirdParties
      tag     <unknown 1>
        tag     value
          attrib  id (2B)
    attrib  Filename (174B)
    attrib  ElementCount (4B)
    tag     TemplateElement
      tag     Element
        attrib  Position (8B)
        attrib  MapFilePath (128B)
        attrib  Rotation90 (1B)
        attrib  IslandLabel (18B)
        attrib  FertilityGuids (16B)
        attrib  RandomizeFertilities (1B)
        tag     MineSlotMapping
          attrib  <unknown 32768> (8B)   ← 匿名 attrib (id=0x8000)
          ...
```

## 内部辞書の構成

Session 0 の場合:

- Tag 辞書 = **447 件**（外側 465 件と別物．session 固有 ID）
- Attrib 辞書 = **189 件**（外側 558 件．こちらも独立）
- 興味深いタグ群:
  - **104 件の ``AreaManager_*``**（動的にタグ名化された島マネージャ）
  - **62 件の ``Island*``**（``Island9``, ``Island18``, ``Island38``, ``Island47`` など具体値）
  - ``Building``, ``PassiveTradeBuilding``, ``AreaPopulationManager``
  - ``MinimumStock``, ``ExclusiveTradeGood``

→ 島単位の建物・人口・在庫データが完全に内部 FileDB として格納されている．

## Anonymous attrib (id = 0x8000 = 32768)

内部 DOM に ``<unknown 32768>`` が頻出．これは attrib 辞書に id 32768 が登録されていない
ためフォールバック名になる．BlueByte は **無名プレースホルダ attrib として id=0x8000 を予約**
している可能性が高い．``MineSlotMapping`` のような座標ペア配列でよく使われる．

v0.2 parser は未解決 ID を ``Attrib_32768`` フォールバックで処理するため decode は止まらない．
interpreter 層（v0.2 step 5）で「親タグが ``MineSlotMapping`` かつ attrib id=0x8000 なら
``(u32, u32)`` ペア配列として解釈」のルールを用意すれば良い．

## v0.3 実装方針（差分）

もともと「本丸 / 沼」想定だった v0.3 が，**v0.2 parser の副産物で実質 80% 完了**した．
残す主要課題:

- [x] 再帰 FileDB 仮説の検証（この調査で確定）
- [x] ``parser.filedb.session.extract_sessions(data)`` 実装（本 PR に同梱）
- [ ] 匿名 attrib (id=0x8000) のコンテキスト依存型解釈（interpreter 層の一部）
- [ ] 島エンティティ（``Island*`` / ``AreaManager_*`` / ``Building``）の Pydantic モデル化
- [ ] 人口 (``AreaPopulationManager``) / 在庫 (``MinimumStock``) のスキーマ調査
- [ ] 全 5 セッション（旧世界 / 新世界 / エンベサ / 北極 / Cape）の対応関係特定
  - セッションの「意味」は外側の同階層 Attrib（``SessionID`` など）で参照されているはず

## 参考

- 上流仮説: [anno-mods/FileDBReader #33](https://github.com/anno-mods/FileDBReader/issues/33) で accountdata の未解決ノードが言及されているが，SessionData が再帰 FileDB である旨は明示されていない
- CLAUDE.md v0.3 本丸章に記載した 3 仮説のうち **仮説 1 を本調査で確定**（仮説 2/3 は棄却）
- 実装は ``src/anno_save_analyzer/parser/filedb/session.py`` の ``extract_sessions`` 1 本で完結
