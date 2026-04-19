# RDA File Format Specification (V2.0 / V2.2)

> 本ドキュメントは lysannschlegel/RDAExplorer の C# 実装（`refs/RDAExplorer/src/RDAExplorer/`）を精読し，
> 自力で再構成した RDA アーカイブフォーマット仕様書．clean-room 実装の根拠資料．
>
> 対象: Anno 1404 / 2070 / 2205 / 1800 が採用する `.rda` コンテナ（`.a7s` セーブも同形式）．
> 本プロジェクト（anno-save-analyzer）の v0.1.5 では **V2.2 の読取のみ**を実装する．

## 1. 全体構造

RDA は **「固定ヘッダ → データ領域 → ブロックチェーン」** の 3 層構造．
ブロックは末尾ではなく自身の直前に自分のディレクトリ（DirEntry 配列）を持ち，`nextBlock` で次のブロックへ連結される片方向リンクリスト．

```
+------------------------------------------------+  file offset 0
| FileHeader                                     |
|   magic (18B)   "Resource File V2.2" (UTF-8)   |
|   unknown (766B)  全 0 パディング              |
|   firstBlockOffset (8B uint64, LE)             |
+------------------------------------------------+  header 終端 (V2.2 = 792B)
| File data area                                 |
|   - 各 DirEntry.offset が指す生バイト          |
|   - 圧縮 / 暗号化はブロック flag 依存          |
|                                                |
| Directory #1 (可変長, DirEntry[fileCount])     |
| BlockInfo #1 (32B, firstBlockOffset が指す)    |
|                                                |
| Directory #2                                    |
| BlockInfo #2 (BlockInfo#1.nextBlock が指す)    |
|                                                |
| ...                                             |
|                                                |
| Directory #N                                    |
| BlockInfo #N (nextBlock == filesize で終端)    |
+------------------------------------------------+  EOF
```

**重要**: BlockInfo は常に自身の直前にディレクトリを置く．
したがって Directory の先頭 = `blockOffset - directorySize`．
`MemoryResident` flag が立つ場合は更に `directorySize - (2 * uintSize)` 分遡って packed data の header を読む．

## 2. バイト順・型

| 項目 | 値 |
|---|---|
| バイトオーダ | Little Endian 固定 |
| 文字列（ファイル名） | UTF-16LE, null padded, 固定 520B |
| 文字列（magic, V2.2） | UTF-8, `"Resource File V2.2"` |
| 文字列（magic, V2.0） | UTF-16LE, `"Resource File V2.0"` |
| UInt (V2.2) | uint64 (8B) |
| UInt (V2.0) | uint32 (4B) |
| Timestamp | UInt (V2.2=uint64), Unix epoch seconds |

magic の encoding 差異はバージョン判別の核心．先頭 2 バイトで判定可能:

- `52 00` (`R\0`) → UTF-16LE → V2.0
- `52 65` (`Re`) → UTF-8 → V2.2

## 3. FileHeader

```
Offset  Size  Field               値（V2.2）
------  ----  ------------------  ------------------------------------
0x000   18    magic               "Resource File V2.2" (UTF-8)
0x012   766   unknown             用途不明・全0で可
0x310   8     firstBlockOffset    最初の BlockInfo の file offset
------  ----
計 792B (V2.2) / 1030B (V2.0, unknown=1008, uint=4)
```

### バージョン別差異

| Version | magic encoding | magic bytes | unknown size | uint size | Header size |
|---------|----------------|-------------|--------------|-----------|-------------|
| V2.0    | UTF-16LE       | 36B         | 1008B        | 4B (u32)  | 1048B       |
| V2.2    | UTF-8          | 18B         | 766B         | 8B (u64)  | 792B        |

※ 上表で「Header size」は magic + unknown + firstBlockOffset の合計．

## 4. BlockInfo

ファイル中の任意位置（末尾ではない点に注意）に置かれる 32B (V2.2) / 20B (V2.0) の構造体．

```
Offset  Size  Field             備考
------  ----  ----------------  -----------------------------------------
0x00    4     flags             uint32, ビットフラグ（下記）
0x04    4     fileCount         uint32, このブロックに属する DirEntry 数
0x08    8     directorySize     uint64, 直前にある directory 領域の実サイズ (バイト)
0x10    8     decompressedSize  uint64, directory 展開後サイズ
0x18    8     nextBlock         uint64, 次ブロックの file offset (EOF = チェーン終端)
------  ----
計 32B (V2.2)
```

### flags ビット定義

| bit | 値 | 名前 | 意味 |
|---|---|---|---|
| 0 | 1 | Compressed | directory と各 file データが zlib 圧縮 |
| 1 | 2 | Encrypted | directory と各 file データが XOR LCG 暗号化 |
| 2 | 4 | MemoryResident | ブロック内全ファイルを一塊で圧縮（packed） |
| 3 | 8 | Deleted | 削除マーカ．ブロック自体を skip（directory もデータも読まない） |

- `Deleted` が立つ場合: このブロックは読み飛ばし，`nextBlock` だけ辿る．
- `MemoryResident` が立つ場合:
  - Compressed/Encrypted は通常ファイル flag として扱わず，packed 全体の属性として扱う．
  - `offset - directorySize - (2 * uintSize)` を起点に `compressedSize, uncompressedSize` を読んで packed data の位置を特定．
  - 各 DirEntry.offset は **packed data 内の相対 offset**．

## 5. DirEntry

ディレクトリ領域は `DirEntry` 構造体の配列．
ブロックの flags に Compressed/Encrypted が立っていれば，directory 全体も zlib / XOR で変換されているため読取時に復号・解凍が必要．

```
Offset  Size   Field        備考
------  -----  -----------  -----------------------------------------
0x000   520    filename     UTF-16LE, null padding, 最大 260 文字
0x208   8      offset       uint64, ファイルデータの file offset (packed の場合は相対)
0x210   8      compressed   uint64, 実バイト数
0x218   8      filesize     uint64, 展開後サイズ (非圧縮時は compressed と一致)
0x220   8      timestamp    uint64, Unix epoch seconds (UTC)
0x228   8      unknown      uint64, 用途不明
------  -----
計 560B (V2.2)
```

### ディレクトリサイズ整合性

```
fileCount * sizeof(DirEntry) == decompressedSize  （展開後）
```

これが満たされない場合は壊れたアーカイブと判断する．

## 6. zlib 圧縮

- C# 実装は `zlib.DLL` の `uncompress` を使う．Python では `zlib.decompress(data)` で置き換え可．
- 圧縮は **raw zlib stream**（先頭 `0x78 0x9C` などの zlib header あり）．gzip header なし．
- Anno 1800 セーブ内の `data.a7s` は FileDB コンテナを zlib で包んだもので，本ライブラリの責務は**一段外側の zlib 展開のみ**．

## 7. XOR LCG 暗号化 (Encrypted flag)

`Misc/BinaryExtension.cs` 参照．2 バイト単位の LCG ベース XOR．

```c
seed = 0x71C71C71  // V2.2
for each int16 word in buffer:
    seed = seed * 214013 + 2531011
    key  = (seed >> 16) & 0x7FFF
    out_word = in_word XOR key
```

バッファ長が奇数の場合，末尾 1 バイトはそのまま付け足す．

セーブファイル（`.a7s`）では通常 Encrypted は立たない想定だが，実装時は検出したらエラー or 警告で後回しで良い．

## 8. 読取アルゴリズム（Python 移植用疑似コード）

```python
def read_rda(path):
    with open(path, "rb") as f:
        # 1. Magic 判定
        first2 = f.read(2); f.seek(0)
        if first2 == b"R\x00":      version = V2_0
        elif first2 == b"Re":        version = V2_2
        else: raise RDAParseError

        # 2. Header
        f.read(magic_size)   # 18 or 36
        f.read(unknown_size) # 766 or 1008
        first_block_offset = read_uint(f, version)

        # 3. Block chain 走査
        entries = []
        block_offset = first_block_offset
        file_size = file_end(f)
        while block_offset < file_size:
            f.seek(block_offset)
            block = BlockInfo.read(f, version)

            if block.flags & 0x08:       # Deleted
                block_offset = block.nextBlock
                continue
            if block.flags & 0x02:       # Encrypted (v0.1.5 では未対応)
                raise NotImplementedError

            # directory 読取
            dir_start = block_offset - block.directorySize
            if block.flags & 0x04:       # MemoryResident: さらに 2*uintSize 分前
                dir_start -= 2 * uint_size(version)
            f.seek(dir_start)
            dir_bytes = f.read(block.directorySize)
            if block.flags & 0x01:       # Compressed
                dir_bytes = zlib.decompress(dir_bytes)

            # MemoryResident 補助情報
            mrm = None
            if block.flags & 0x04:
                f.seek(block_offset - block.directorySize - 2 * uint_size(version))
                compressed_size = read_uint(f, version)
                uncompressed_size = read_uint(f, version)
                mrm = MemoryResident(
                    base_offset = block_offset - block.directorySize - compressed_size,
                    ...,
                )

            # DirEntry 展開
            for i in range(block.fileCount):
                e = DirEntry.read(dir_bytes[i * dir_entry_size : ...])
                entries.append(RDAFile(e, block, mrm, version))

            block_offset = block.nextBlock

    return entries
```

## 9. ファイルデータ取り出し

```python
def read_file(rda_file):
    f.seek(rda_file.offset)
    raw = f.read(rda_file.compressed_size)
    if rda_file.encrypted:
        raw = xor_decrypt(raw, seed)
    if rda_file.compressed:
        raw = zlib.decompress(raw, bufsize=rda_file.uncompressed_size)
    return raw
```

MemoryResident の場合，base は packed data の先頭 offset，`rda_file.offset` は相対値．

## 10. sample.a7s 実測値

本プロジェクト同梱の `sample.a7s` （Anno 1800 の実セーブ）を検証用リファレンスとして利用:

| 項目 | 値 |
|---|---|
| ファイル size | 3,732,794 B |
| magic | `"Resource File V2.2"` (V2.2) |
| header 末尾 (`0x310`) の firstBlockOffset | `0x5F1 = 1521` |
| 末尾 32B の BlockInfo | flags=0, fileCount=1, directorySize=0x230=560, decompressedSize=0x230, nextBlock=0x38F53A (=EOF) |

末尾ブロックは非圧縮・非暗号化で DirEntry 1 件分（560B）のみ．最終ブロックの `nextBlock` がファイル末尾を指してチェーンが切れる．
先頭ブロックから順に辿って DirEntry を集積し，期待される 4 エントリ (`meta.a7s`, `header.a7s`, `gamesetup.a7s`, `data.a7s`) を得る想定．

## 11. 実装時の注意点

1. **バイトオーダはすべて LE**（C# `BinaryReader` 既定）．Python では `struct.unpack("<Q", ...)` 等．
2. **ファイル名は固定 520B の UTF-16LE**．decode 後 `\x00` を strip する．
3. **BlockInfo は自分の offset の直前 directoryBytes 分が directory 本体**（トリッキー）．
4. **uint サイズはバージョン依存**．V2.0 は uint32，V2.2 は uint64．
5. **Deleted ブロックも nextBlock は有効**．skip しつつ chain を継続．
6. **MemoryResident は v0.1.5 では最小限対応**．セーブデータ（`.a7s`）では通常不要だが，万一遭遇したらエラー出す．
7. **暗号化ブロックは v0.1.5 では未対応**．遭遇したら明示的に NotImplementedError．
8. **Streaming**: セーブは数百 MB になりうるため，`mmap` もしくは個別 seek で読み，全部を bytes に載せない．
9. **directorySize == 0** の空ブロック（fileCount=0）は，C# 側は空ディレクトリとして普通に処理する．同じ扱いで良い．

## 12. 参考

- 上流: https://github.com/lysannschlegel/RDAExplorer (GPL-v3)
- 本実装はフォーマット仕様のみ学習し clean-room で書き直す．ソースは転載しない．
- 謝辞: README に `Based on the reverse engineering work of @lysannschlegel's RDAExplorer` を記載．
