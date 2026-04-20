"""FileDB parser 用例外クラス．"""

from __future__ import annotations


class FileDBParseError(Exception):
    """FileDB バイナリの構造破損や仕様違反を検出したとき送出する汎用例外．"""


class UnsupportedFileDBVersion(FileDBParseError):
    """magic から判定したバージョンが実装対象外のとき送出する例外．"""
