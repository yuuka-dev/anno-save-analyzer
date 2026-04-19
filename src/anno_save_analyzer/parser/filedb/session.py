"""SessionData / BinaryData の再帰 FileDB 抽出ヘルパ．

Anno 1800 セーブ内部の FileDB V3 DOM には ``<SessionData>`` タグが複数含まれ，
各 SessionData 配下に ``<BinaryData>`` Attrib として **再び完全な FileDB V3 文書**が
封入されている（2026-04-19 の調査で実測確認）．

本モジュールは外側 FileDB バイト列を受け取り，5 セッション分の内部 FileDB バイト列を
抜き出して ``list[bytes]`` として返す．呼び出し側は各要素を再度 :mod:`parser.filedb`
で parse することで，島 / 建物 / 人口などの階層データを取得できる．

加えて，内側 Session の tag 辞書から島管理単位（``AreaManager_*``）の internal ID
列を取り出すヘルパも提供する．
"""

from __future__ import annotations

from .dictionary import TagSection, parse_tag_section
from .dom import EventKind, iter_dom
from .exceptions import FileDBParseError
from .version import FileDBVersion, detect_version

_AREA_MANAGER_PREFIX = "AreaManager_"

_SESSION_TAG_NAME = "SessionData"
_BINARY_ATTRIB_NAME = "BinaryData"


def _resolve_session_ids(section: TagSection) -> tuple[int, int]:
    session_tag_id: int | None = next(
        (tid for tid, name in section.tags.entries.items() if name == _SESSION_TAG_NAME),
        None,
    )
    binary_attrib_id: int | None = next(
        (aid for aid, name in section.attribs.entries.items() if name == _BINARY_ATTRIB_NAME),
        None,
    )
    if session_tag_id is None or binary_attrib_id is None:
        raise FileDBParseError(
            "outer FileDB does not expose SessionData / BinaryData names in its dictionary"
        )
    return session_tag_id, binary_attrib_id


def extract_sessions(
    outer: bytes | memoryview,
    version: FileDBVersion | None = None,
    tag_section: TagSection | None = None,
) -> list[bytes]:
    """外側 FileDB の DOM を走査し ``<SessionData><BinaryData>`` の content を全件返す．

    ``version`` / ``tag_section`` を呼び出し側で既に取得済なら引数で渡せる（再計算を避ける）．
    """
    if version is None:
        version = detect_version(outer)
    if tag_section is None:
        tag_section = parse_tag_section(outer, version)

    session_tag_id, binary_attrib_id = _resolve_session_ids(tag_section)

    sessions: list[bytes] = []
    depth_in_session = 0
    for ev in iter_dom(outer, version, tag_section=tag_section):
        if ev.kind is EventKind.TAG and ev.id_ == session_tag_id:
            depth_in_session += 1
            continue
        if ev.kind is EventKind.TERMINATOR and depth_in_session > 0:
            depth_in_session -= 1
            continue
        if ev.kind is EventKind.ATTRIB and ev.id_ == binary_attrib_id and depth_in_session > 0:
            sessions.append(ev.content)
    return sessions


def list_inner_area_managers(inner_session: bytes) -> tuple[int, ...]:
    """内側 Session FileDB の tag 辞書から ``AreaManager_<N>`` の N（int）を昇順で返す．

    Anno のセーブでは各島が 1 つの ``AreaManager`` で管理される．辞書を見るだけで
    DOM 走査は不要なため，書記長のセーブ規模でもほぼ瞬時．
    """
    if not inner_session:
        return ()
    version = detect_version(inner_session)
    section = parse_tag_section(inner_session, version)
    ids: list[int] = []
    for name in section.tags.entries.values():
        if not name.startswith(_AREA_MANAGER_PREFIX):
            continue
        suffix = name[len(_AREA_MANAGER_PREFIX) :]
        if suffix.isdigit():
            ids.append(int(suffix))
    ids.sort()
    return tuple(ids)
