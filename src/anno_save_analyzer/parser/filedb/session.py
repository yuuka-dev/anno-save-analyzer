"""SessionData / BinaryData の再帰 FileDB 抽出ヘルパ + 島メタデータ抽出．

Anno 1800 セーブ内部の FileDB V3 DOM には ``<SessionData>`` タグが複数含まれ，
各 SessionData 配下に ``<BinaryData>`` Attrib として **再び完全な FileDB V3 文書**が
封入されている．本モジュールはその抽出と，内側 Session DOM からの島メタデータ
(AreaManager 一覧 / プレイヤー命名済の島) 抽出を提供する．
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from .dictionary import TagSection, parse_tag_section
from .dom import EventKind, iter_dom
from .exceptions import FileDBParseError
from .version import FileDBVersion, detect_version

_AREA_MANAGER_PREFIX = "AreaManager_"
_AREA_INFO_TAG = "AreaInfo"
_CITY_NAME_ATTRIB = "CityName"


@dataclass(frozen=True)
class PlayerIsland:
    """プレイヤー命名済（= 保有）の島メタ．

    ``city_name`` はゲーム内で書記長が手動入力した名前（例: "大阪民国"）．
    今後 owner profile / area_manager_id / 人口 等を追加する余地あり．
    """

    city_name: str


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


def list_player_islands(inner_session: bytes) -> tuple[PlayerIsland, ...]:
    """内側 Session DOM から「プレイヤー保有島」のリストを抽出する．

    判別基準: ``GameSessionManager > AreaInfo > <1>`` 配下に ``CityName`` attrib
    が存在するエントリ．Anno 117 では命名 = 保有のため，これでプレイヤー所有島
    と未命名（NPC / 空島）を区別できる．書記長の sample 例: 大阪民国 / ジョウト地方
    等．
    """
    if not inner_session:
        return ()
    version = detect_version(inner_session)
    section = parse_tag_section(inner_session, version)
    area_info_tag_id = next(
        (tid for tid, name in section.tags.entries.items() if name == _AREA_INFO_TAG),
        None,
    )
    if area_info_tag_id is None:
        return ()
    return tuple(_iter_player_islands(inner_session, version, section, area_info_tag_id))


def _iter_player_islands(
    inner_session: bytes,
    version: FileDBVersion,
    section: TagSection,
    area_info_tag_id: int,
) -> Iterator[PlayerIsland]:
    """``AreaInfo`` 配下を walk して ``CityName`` 持ちエントリだけ yield．"""
    in_area_info_depth = -1  # AreaInfo に入った時の stack 長
    in_entry = False
    pending_city_name: bytes | None = None
    stack_depth = 0

    for ev in iter_dom(inner_session, version, tag_section=section):
        if ev.kind is EventKind.TAG:
            stack_depth += 1
            if ev.id_ == area_info_tag_id and in_area_info_depth < 0:
                in_area_info_depth = stack_depth
                continue
            if in_area_info_depth >= 0 and stack_depth == in_area_info_depth + 1:
                in_entry = True
                pending_city_name = None
            continue

        if ev.kind is EventKind.ATTRIB:
            if in_entry and ev.name == _CITY_NAME_ATTRIB:
                pending_city_name = ev.content
            continue

        # Terminator
        if stack_depth == 0:
            continue
        if in_entry and in_area_info_depth >= 0 and stack_depth == in_area_info_depth + 1:
            if pending_city_name is not None:
                yield PlayerIsland(city_name=_decode_utf16le(pending_city_name))
            in_entry = False
            pending_city_name = None
        if in_area_info_depth >= 0 and stack_depth == in_area_info_depth:
            in_area_info_depth = -1
        stack_depth -= 1


def _decode_utf16le(buf: bytes) -> str:
    return buf.decode("utf-16-le", errors="replace").rstrip("\x00")
