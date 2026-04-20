"""FileDB V1 / V2 / V3 判定．

末尾 8 バイトに置かれるマジックバイトでバージョンを決める．
V1 は無 magic で，``V2/V3 のいずれでもない`` ことから推定する．
"""

from __future__ import annotations

from enum import Enum

from .exceptions import FileDBParseError

# 末尾マジック（Versioning.GetMagicBytes と一致）
_MAGIC_V2 = bytes.fromhex("08000000FEFFFFFF")
_MAGIC_V3 = bytes.fromhex("08000000FDFFFFFF")

# 辞書末尾から遡って offset ペアを読む距離 (Length - OffsetToOffsets)
OFFSET_TO_OFFSETS = {
    # V1 は 4 (int32 単一)，V2/V3 は 16 (int32×2 + magic 8B)
    "V1": 4,
    "V2": 16,
    "V3": 16,
}

# Attrib content の blockspace (padded size) 計算用
BLOCK_SIZE = {
    "V1": 0,  # V1 は padding 無し
    "V2": 8,
    "V3": 8,
}


class FileDBVersion(Enum):
    """FileDB ドキュメントのバージョン．"""

    V1 = "V1"
    V2 = "V2"
    V3 = "V3"

    @property
    def offset_to_offsets(self) -> int:
        """末尾から辞書オフセットブロックまでの距離．"""
        return OFFSET_TO_OFFSETS[self.value]

    @property
    def block_size(self) -> int:
        """Attrib content の padding 単位（V2/V3=8, V1=0）．"""
        return BLOCK_SIZE[self.value]

    @property
    def uses_attrib_blocks(self) -> bool:
        """Attrib content が block アラインされるか．V1 は False．"""
        return self.block_size > 0


def detect_version(data: bytes | memoryview) -> FileDBVersion:
    """FileDB バイト列の末尾マジックからバージョンを判定する．

    V2 / V3 にマッチしなければ V1 として扱う（上流実装と同じ挙動）．
    ただし最低限 ``OffsetToOffsets`` バイトは必要．
    """
    if len(data) < 8:
        raise FileDBParseError(
            f"file too small to detect FileDB version (got {len(data)}B, need >= 8B)"
        )
    tail = bytes(data[-8:])
    if tail == _MAGIC_V3:
        return FileDBVersion.V3
    if tail == _MAGIC_V2:
        return FileDBVersion.V2
    return FileDBVersion.V1


def magic_bytes(version: FileDBVersion) -> bytes | None:
    """指定 version のマジックバイト列（V1 は ``None``）．"""
    if version is FileDBVersion.V2:
        return _MAGIC_V2
    if version is FileDBVersion.V3:
        return _MAGIC_V3
    return None
