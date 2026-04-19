"""DOM イベントを lxml ``Element`` ツリーに変換する．

Attrib の content は bytes のまま hex エンコードして保持する（interpreter 層で
型変換する想定）．Tag / Attrib の名前は ``TagSection`` で解決される．
名前未定義の ID は ``Tag_{id}`` / ``Attrib_{id}`` のフォールバックを使う．
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from .dictionary import TagSection, parse_tag_section
from .dom import DomEvent, EventKind, iter_dom
from .exceptions import FileDBParseError
from .version import FileDBVersion, detect_version

if TYPE_CHECKING:
    from collections.abc import Iterable


_ROOT_TAG = "FileDBDocument"


def _safe_name(raw: str | None, prefix: str, id_: int) -> str:
    if raw is None or raw == "":
        return f"{prefix}_{id_}"
    # XML 名として不正な文字を簡易にサニタイズ．本実装は spec 層なので
    # 先頭英字保証と空白 / 記号の排除のみ．
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in raw)
    if not cleaned or not (cleaned[0].isalpha() or cleaned[0] == "_"):
        cleaned = f"_{cleaned}"
    return cleaned


def build_xml_from_events(
    events: Iterable[DomEvent],
    tag_section: TagSection | None = None,
) -> etree._Element:
    """DOM イベント列から lxml ``Element`` ツリーを組み上げる．

    ルート要素 ``<FileDBDocument>`` の直下に DOM の各ルートタグが並ぶ．
    Attrib は子要素 ``<attrib name="..." id="..." hex="..."/>`` として表現する．
    """
    root = etree.Element(_ROOT_TAG)
    stack: list[etree._Element] = [root]

    for ev in events:
        if ev.kind is EventKind.TAG:
            parent = stack[-1]
            name = _safe_name(ev.name, "Tag", ev.id_)
            node = etree.SubElement(parent, name)
            node.set("id", str(ev.id_))
            stack.append(node)
            continue
        if ev.kind is EventKind.ATTRIB:
            parent = stack[-1]
            name = _safe_name(ev.name, "Attrib", ev.id_)
            node = etree.SubElement(parent, name)
            node.set("id", str(ev.id_))
            node.set("hex", ev.content.hex())
            continue
        # Terminator
        if len(stack) <= 1:
            # ルートレベルでの余分な terminator は DOM セクション終了マーカ．
            continue
        stack.pop()

    return root


def build_xml(
    data: bytes | memoryview,
    version: FileDBVersion | None = None,
) -> etree._Element:
    """FileDB バイト列から一発で lxml ``Element`` を作るワンショット API．

    辞書解決つき．メモリ上にツリー全体を構築するため巨大ファイルには向かない
    （その場合は ``iter_dom`` を直接使う）．
    """
    if version is None:
        version = detect_version(data)
    if version is FileDBVersion.V1:
        raise FileDBParseError("FileDB V1 XML building is not supported in v0.2")
    section = parse_tag_section(data, version)
    events = iter_dom(data, version, tag_section=section)
    return build_xml_from_events(events, section)
