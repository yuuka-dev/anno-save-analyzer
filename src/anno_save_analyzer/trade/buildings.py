"""Anno 1800 建物辞書 loader．

``data/buildings_anno1800.en.yaml`` を canonical に ``(guid → BuildingEntry)``
を提供する．``en`` が全メタ (name / kind / template / tier?) を持ち，他 locale
は name の override のみ．

MVP 範囲: name / kind / template / tier．workforce / inputs / outputs は
後続 issue (#66, #12) で assets.xml の FactoryBase / ProductionChain 深掘りと
併せて拡張する．
"""

from __future__ import annotations

from collections.abc import Mapping
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

_DATA_PACKAGE = "anno_save_analyzer.data"
_EN_FILE = "buildings_anno1800.en.yaml"

# kind のリテラル集合．YAML 生成側と歩調を合わせる．追加時は scripts/
# generate_buildings_anno1800.py の ``_KIND_RULES`` も更新する．
_KNOWN_KINDS = frozenset(
    {
        "residence",
        "factory",
        "farm",
        "farmfield",
        "warehouse",
        "public_service",
        "buff_factory",
        "market",
        "pier",
    }
)


class BuildingEntry(BaseModel):
    """1 建物分のメタ．``tier`` は residence 限定で，それ以外は ``None``．"""

    guid: int
    name: str
    """locale 適用後の表示名．packaged en YAML なら英語，override 済みなら当該 locale．"""
    kind: str
    """``residence`` / ``factory`` / ``farm`` / ``warehouse`` / ``public_service``
    / ``buff_factory`` / ``market`` / ``pier`` / ``farmfield``．"""
    template: str
    """元 assets.xml の ``<Template>`` 値．細分種別 (``ResidenceBuilding7_Arctic``
    等) を見たい場合はこちらを参照．"""
    tier: str | None = None
    """Residence のみ．``farmer`` / ``worker`` / ``artisan`` / ``engineer``
    / ``investor`` / ``jornaleros`` / ``obreros``．判定不能で未設定の可能性もある．"""

    model_config = {"frozen": True}


class BuildingDictionary(BaseModel):
    """GUID → BuildingEntry の lookup テーブル．"""

    entries: dict[int, BuildingEntry] = Field(default_factory=dict)

    model_config = {"frozen": True}

    def get(self, guid: int) -> BuildingEntry | None:
        return self.entries.get(guid)

    def __getitem__(self, guid: int) -> BuildingEntry:
        return self.entries[guid]

    def __contains__(self, guid: int) -> bool:
        return guid in self.entries

    def __len__(self) -> int:
        return len(self.entries)

    def by_kind(self, kind: str) -> tuple[BuildingEntry, ...]:
        """``kind`` が一致する建物を GUID 昇順で返す．"""
        return tuple(
            sorted((e for e in self.entries.values() if e.kind == kind), key=lambda e: e.guid)
        )

    def by_tier(self, tier: str) -> tuple[BuildingEntry, ...]:
        """``tier`` が一致する residence を GUID 昇順で返す．"""
        return tuple(
            sorted((e for e in self.entries.values() if e.tier == tier), key=lambda e: e.guid)
        )

    @classmethod
    def load(
        cls, *, data_dir: Path | None = None, locales: tuple[str, ...] = ("en",)
    ) -> BuildingDictionary:
        """packaged or 指定 ``data_dir`` から YAML を読み込む．

        ``locales`` は name override の優先順．先頭から順に探索して最初に見つかった
        name を採用．``en`` は canonical メタソースとして常にベースロード．
        """
        en_payload = _read_yaml(_EN_FILE, data_dir)
        locale_payloads: dict[str, dict[int, dict[str, Any]]] = {}
        for loc in locales:
            if loc == "en":
                continue
            fname = f"buildings_anno1800.{loc}.yaml"
            try:
                payload = _read_yaml(fname, data_dir)
            except FileNotFoundError:
                continue
            locale_payloads[loc] = {int(k): v for k, v in payload.items() if isinstance(v, dict)}

        entries: dict[int, BuildingEntry] = {}
        for raw_guid, raw_entry in en_payload.items():
            if not isinstance(raw_entry, dict):
                continue
            guid = int(raw_guid)
            name = _pick_localized_name(guid, raw_entry, locale_payloads, locales)
            entries[guid] = BuildingEntry(
                guid=guid,
                name=name,
                kind=str(raw_entry.get("kind") or "unknown"),
                template=str(raw_entry.get("template") or ""),
                tier=raw_entry.get("tier"),
            )
        return cls(entries=entries)


def known_kinds() -> frozenset[str]:
    """テスト / ドキュメント用に kind 集合を公開する．"""
    return _KNOWN_KINDS


def _read_yaml(filename: str, data_dir: Path | None) -> dict[Any, Any]:
    if data_dir is None:
        text = (resources.files(_DATA_PACKAGE) / filename).read_text(encoding="utf-8")
    else:
        path = data_dir / filename
        if not path.exists():
            raise FileNotFoundError(path)
        text = path.read_text(encoding="utf-8")
    payload = yaml.safe_load(text)
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise ValueError(f"YAML root must be a mapping in {filename}, got {type(payload).__name__}")
    return dict(payload)


def _pick_localized_name(
    guid: int,
    en_entry: dict[str, Any],
    locale_payloads: dict[str, dict[int, dict[str, Any]]],
    locales: tuple[str, ...],
) -> str:
    for loc in locales:
        if loc == "en":
            en_name = en_entry.get("name")
            if en_name:
                return str(en_name)
            continue
        entry = locale_payloads.get(loc, {}).get(guid)
        if entry and entry.get("name"):
            return str(entry["name"])
    return str(en_entry.get("name") or "")
