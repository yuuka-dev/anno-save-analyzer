"""RDA パーサ用例外クラス．"""

from __future__ import annotations


class RDAParseError(Exception):
    """RDA ファイルの構造破損や仕様違反を検出したときに送出する汎用例外．"""


class UnsupportedVersionError(RDAParseError):
    """magic は読めたが本実装が対応していないバージョンだった場合に送出．"""


class EncryptedBlockError(RDAParseError):
    """Encrypted flag の付いたブロックに遭遇した場合に送出．v0.1.0 では未対応．"""
