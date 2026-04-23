# Factory / Residence Extraction Spike (Anno 1800)

> 調査日: 2026-04-23．対象: ``sample_anno1800.a7s`` (4,782,934 B)．
>
> 目的: v0.4 「島ごとサプライチェーン balance 表」(#12) および「Residence tier
> breakdown」(#64) 着手前に，Anno 1800 セーブ内部の **工場稼働率** と **住居
> 階層** がどの DOM パスに存在し，どの attrib 型で格納されているかを確定する．

## TL;DR

- **Residence 抽出は既存 ``trade/population.py`` が Anno 1800 でそのまま動く**．
  改修不要．実測で書記長の 18 島中 17 島 (Arctic 未開発のため 1 島欠) を正しく
  集計できることを確認した．
- **Factory 抽出は新規実装が必要**だが DOM パターンは Residence7 と同形．
  ``_walk_residences`` を ``_walk_factories`` に置き換える差分で実装できる．
- **工場稼働率 ``CurrentProductivity`` は f32 (0.0–2.0)** で，200% バフ (取引所
  効率アイテム等) を表現できる範囲．UI 側で ``* 100`` で % に換算する．
- **建物 GUID は objects > <1> 直下の ``guid`` attrib** (i32) にあり，
  Factory7 / Residence7 自身には乗っていない．items.yaml 参照で名前解決できる．

## 1. 事前条件 (既存実装で確定済)

``parser/filedb/session.py`` の ``extract_sessions`` で外側 FileDB → 5 件の
``SessionData > BinaryData`` → 各 session の inner FileDB V3 に再帰展開できる．
v0.3 で実装済み．今回の spike は **inner session を所与** として内部構造を
調査するフェーズ．

Anno 1800 の session 順は ``trade/sessions.py`` の通り:

| index | session | 書記長 save 実測 AreaManager 数 | PlayerIsland |
|---|---|---|---|
| 0 | Cape Trelawney | 57 | 5 |
| 1 | Old World | 76 | 4 |
| 2 | Enbesa | 44 | 3 |
| 3 | New World | 60 | 6 |
| 4 | Arctic | 68 | 0 (未開発) |

## 2. Residence 抽出の動作確認

既存 ``list_residence_aggregates(inner_session)`` を 5 session 全てに適用．

### session 0 (Cape Trelawney) の結果抜粋

```
AM AreaManager_8706  residences=320  residents= 7119  products=26  avgSat=0.504
AM AreaManager_8642  residences=144  residents= 3234  products=16  avgSat=0.522
AM AreaManager_8578  residences=228  residents= 2352  products=11  avgSat=0.376
AM AreaManager_8962  residences= 94  residents= 1470  products=11  avgSat=0.496
AM AreaManager_8514  residences=154  residents= 1348  products= 8  avgSat=0.357
```

各 AM に対して ``PlayerIsland`` (``CityName``) の数と一致する件数が得られ，
``CityAreaMatch`` の jaccard 結合も機能する見込み．書記長の島名 (``大都会岡山``
等) がそのまま ``PlayerIsland.city_name`` として取得できることを確認した．

### 結論

``trade/population.py`` は**ゲームタイトル非依存**として使える．Anno 117 と
Anno 1800 の DOM 構造は Residence7 階層で完全同形．

## 3. Factory DOM 構造の特定

### 3.1 objects > <1> 子タグの出現パターン

session 0 の最大都市 ``AreaManager_8706`` 配下で ``GameObject > objects > <1>``
(= 1 建造物) の直下子タグ集合をユニーク count した結果 (上位)：

| n | 子タグ set |
|---:|---|
| 3007 | ``Building, BuildingModule, FeedbackController, Mesh, ParticipantID`` |
|  414 | ``... Residence7 ...`` |
|  243 | ``BezierPath, ...`` (道路・装飾) |
|   41 | ``... Electric, Factory7 ...`` |
|   34 | ``... Warehouse ...`` |
|   30 | ``... Factory7 ...`` (非電化) |
|   27 | ``... BuffFactory ...`` (Pub / Market 類) |
|   22 | ``... Factory7, ModuleOwner, Motorizable ...`` (石炭/原油依存) |

**Factory7** は 41 + 30 + 22 + 22 = **約 115 工場** (書記長最大都市のみ)．
session 0 全 AreaManager 合計では **250 件**確認．全 session では 1,000+ 想定．

派生形として:

- ``Electric`` 兄弟 → 電力消費系
- ``Motorizable`` 兄弟 → モーター化可能 (石炭/原油バフ対象)
- ``BuffFactory`` → 住民需要を満たすタイプ (Pub / Variety Theater 等)．
  Factory7 とは別タグで表現される

### 3.2 Factory7 ノード内部

3 インスタンスで実測し同一構造を確認．

```
Factory7                                    (tag)
├─ A CurrentProductivity           f32 (4B)  ← 現在の生産効率
└─ ProductionState                 (tag)
    ├─ A InProgress                u8  (1B)  bool
    ├─ A RemainingTime             f32 (4B)  次サイクルまでの残秒 (game tick)
    └─ A Productivity              f32 (4B)  履歴用の累積 productivity
```

### 3.3 CurrentProductivity の型確定

session 0 の Factory7 250 件での実測:

| 読み方 | min | max | mean | 妥当性 |
|---|---|---|---|---|
| i32 | -2,147,483,648 | 1,088,421,888 | 440,518,428 | ✗ (明らかに overflow) |
| f32 | 0.0 | 2.0 | 〜0.51 | ✓ (Anno の 200% バフ上限に一致) |

**``CurrentProductivity`` は f32 で確定**．UI 層で ``* 100`` → 整数 % 表示する．

### 3.4 親エントリとの関係

``Factory7`` 自身には建物 GUID が乗っていない．建物を特定するには親の
``objects > <1>`` 直下の ``guid`` attrib を読む必要がある:

```
AreaManager_<N>                             (depth 2)
└─ GameObject                               (depth 3)
    └─ objects                              (depth 4)
        └─ <1>                              (depth 5)
            ├─ A guid              i32 (4B)   ← 建物 GUID (items.yaml key)
            ├─ A ID                u64 (8B)   ← 個別インスタンス ID
            ├─ A ObjectFolderID    i32 (4B)
            ├─ A Position          vec3 (12B)
            ├─ A Direction         f32 (4B)
            ├─ ParticipantID                   (子タグ)
            ├─ Building                        (子タグ．中身は建物 metadata)
            ├─ Pausable                        (子タグ．停止状態)
            ├─ Factory7                        (子タグ．生産コンポ)
            ├─ LogisticNode                    (子タグ．倉庫接続)
            ├─ Maintenance                     (子タグ．維持費)
            ├─ Electric                        (子タグ．電力消費，任意)
            └─ ...
```

Residence7 の場合も同じ階層に ``guid`` attrib があり，そこで住居 GUID を
取得できる (tier 判定に使用)．

## 4. Residence Tier Breakdown (仮説)

Anno 1800 の住居階層は 5 種類:

| Tier | 英名 | 日本語 |
|---|---|---|
| 1 | Farmer | 農民 |
| 2 | Worker | 労働者 |
| 3 | Artisan | 職人 |
| 4 | Engineer | エンジニア |
| 5 | Investor | 投資家 |

(+ DLC で Jornalero / Obrero / Shepherd / Elder / Explorer / Technician /
Scholar 等の New World / Arctic / Enbesa 固有階層)

### 4.1 判定ロジック

``objects > <1>`` 直下の ``guid`` を読み，items.yaml で
``Template = Residence*`` に該当する GUID を tier ごとに分類する．

### 4.2 ブロッカー

現行の ``data/items_anno1800.*.yaml`` は **Product GUID のみ**収録している
(``scripts/generate_items_anno1800.py`` が ``Template=Product`` で絞っているため)．
住居建物 GUID は**含まれていない**．

対策として別ファイル ``data/buildings_anno1800.*.yaml`` を
``scripts/generate_buildings_anno1800.py`` で生成する．``Template`` フィールドを
保持する形式にして，tier 判定 / factory 種別判定を一元化する．

## 5. 未確認事項 (今回の spike 範囲外)

### 5.1 生産物と消費物の解決

Factory7 直下には生産品目 (output) の GUID が**直接記録されていない**．
建物 GUID → ``assets.xml`` の ``FactoryBase > RawMaterial`` / ``Product`` から
推定する形になる．これも buildings YAML の生成時に解決して埋め込む．

### 5.2 労働力 (Workforce)

各工場が要求する workforce は ``ProductionChain`` / ``Workforce`` 兄弟タグ
候補が複数ある．residence tier から供給される workforce と突合するには追加
spike が必要．**v0.4 の MVP では workforce 制約は後回し** (Calculator 本家も
手動入力扱いなので同等で良い)．

### 5.3 Warehouse / BuffFactory

- ``Warehouse`` 子タグを持つ建物は**在庫バッファ**．StorageTrends は既存実装で
  取得できているので balance engine 側で参照するだけ
- ``BuffFactory`` (Pub / Market / Variety Theater 等) は Factory7 と別系統．
  住民需要の "public service" 系の満足度に寄与するため，need saturation 側
  (既存の ``AverageNeedSaturation``) で既にカバーされている

### 5.4 AI player の工場

NPC session (session 4 Arctic 等) でも AreaManager_* が存在する．AI プレイヤー
の工場データも取得可能だが，プレイヤー vs NPC 判定は ``CityName`` attrib の
有無で行う (既存 ``list_player_islands`` と同じ手法)．

## 6. 実装への示唆

### 6.1 モジュール配置

新規ファイル ``src/anno_save_analyzer/trade/factories.py`` を作る．``population.py``
と並置することで:

- ``list_factory_aggregates(inner_session) -> tuple[FactoryAggregate, ...]``
- ``FactoryAggregate`` Pydantic モデル: ``area_manager / building_guid / count
  / mean_productivity / paused_count``

を提供する．``population.py`` の ``_walk_residences`` とほぼ同じ state machine
で実装可能．

### 6.2 Balance Engine (#12 本体)

依存関係:

```
factories.py   (新)  ──┐
population.py  (既)  ──┼─→ balance.py (新)
buildings yaml (新)  ──┤         │
products yaml  (既)  ──┘         ▼
                           SupplyBalanceTable
                           (island × product → produce / consume / delta)
```

消費レートは Calculator の ``consumption.js`` (tier × product の per-minute
rate) を Node 実行で抽出して ``data/consumption_anno1800.yaml`` に commit．
生産レートは ``assets.xml`` から直接抽出して ``buildings_anno1800.yaml`` に
同梱する (Calculator は二次ソースとして参照のみ)．

### 6.3 テスト戦略

- ``tests/trade/test_factories.py`` — unit (合成 inner bytes で state machine)
- ``tests/trade/test_anno1800_factories_smoke.py`` — 実 save で件数・平均値
  アサーション (tests/trade/test_anno1800_smoke.py と同形式)
- 新設 ``tests/integration/`` — save → factories + population + balance の
  end-to-end パイプライン確認

### 6.4 Coverage 維持

純関数層 (factories.py / balance.py) は 100% を死守．TUI / GUI 追加で
90% ゲートを下回らないように pragma: no cover を UI イベントループ内
callback に限定する (既存方針継続)．

## 7. 参考

- 既存実装: ``src/anno_save_analyzer/trade/population.py`` (本 spike の骨格)
- 類似 spike: ``docs/session_binary_investigation.md`` (SessionData 再帰展開の発見)
- ``docs/filedb_format_investigation.md`` (FileDB V3 仕様)
- Anno1800Calculator (NiHoel, MIT): https://github.com/NiHoel/Anno1800Calculator
  — ``js/consumption.js`` + ``js/params.js`` に tier × product 消費レート
