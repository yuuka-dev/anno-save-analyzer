"""FileDB (BBDom) V3 parser — clean-room port of anno-mods/FileDBReader．

公開 API:

- ``FileDBVersion`` : V1 / V2 / V3 列挙
- ``detect_version(data: bytes)`` : 末尾マジックから version 判定
- ``TagDictionary`` : tag / attrib name 辞書
- ``parse_tag_section(data, version)`` : 末尾からの辞書ペア取り出し
- ``iter_dom(data, version)`` : streaming iterator（Tag / Attrib / Terminator イベント）
- ``build_xml(data)`` : lxml ``Element`` ツリー構築（ワンショット．将来的に streaming 対応予定）
"""

from .dictionary import TagDictionary, TagSection, parse_tag_section
from .dom import Attrib, DomEvent, EventKind, Tag, Terminator, iter_dom
from .exceptions import FileDBParseError, UnsupportedFileDBVersion
from .version import FileDBVersion, detect_version
from .xml import build_xml

__all__ = [
    "FileDBVersion",
    "detect_version",
    "TagDictionary",
    "TagSection",
    "parse_tag_section",
    "iter_dom",
    "DomEvent",
    "EventKind",
    "Tag",
    "Attrib",
    "Terminator",
    "build_xml",
    "FileDBParseError",
    "UnsupportedFileDBVersion",
]
