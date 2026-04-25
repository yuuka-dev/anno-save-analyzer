"""Anno 1800 tier 別消費レート (Anno1800Calculator 由来) の loader．

``data/consumption_anno1800.en.yaml`` を canonical ソースとして読み，``(tier_guid,
product_guid) → tpmin`` (tons-per-minute-per-resident) を返す ``ConsumptionTable``
を提供する．``.ja.yaml`` は tier 名の日本語ローカライズに使う．

YAML 生成は ``scripts/generate_supply_data_anno1800.py`` で再生成できる．
CI の validate-supply-data job が diff 検知するため Calculator が更新されたら
再生成してコミットする必要がある．
"""

from __future__ import annotations

from functools import cached_property
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

_DATA_PACKAGE = "anno_save_analyzer.data"
_EN_FILE = "consumption_anno1800.en.yaml"
_JA_FILE = "consumption_anno1800.ja.yaml"


class TierNeed(BaseModel):
    """1 tier が消費 (あるいは欲しがる) する 1 物資の設定．"""

    product_guid: int
    tpmin: float | None = None
    """tons-per-minute-per-resident．``None`` は物資が "need" として登録されてる
    が実消費量が未定義 (例: 共同体・公共サービス系の intangible need)．"""
    residents: int = 0
    """この need を満たしたとき 1 住居 / tier upgrade あたりで増える住民数．"""
    happiness: int = 0
    """この need を満たしたときの happiness 寄与．bonus need で使う．"""
    is_bonus_need: bool = False
    """Spirits / Rum のような住人 upgrade 不要の嗜好品系．"""
    dlcs: tuple[str, ...] = Field(default_factory=tuple)
    unlock_condition_guid: int | None = None
    """この need が unlock されるための条件 (人口閾値 + 公共施設 etc) の
    Asset GUID．現状は全 ``None``．#99 で ``assets.xml`` の
    ``UnlockCondition`` を抽出して埋める予定．埋まれば balance 側で
    「unlock 未達 need は除外」の正確な gate が効くようになる．
    """

    model_config = {"frozen": True}


class PopulationTier(BaseModel):
    """Farmer / Worker / Artisan などの住民階層 1 件．"""

    guid: int
    name: str
    """Calculator 由来の英語名 (canonical)．日本語 override は別メソッド経由．"""
    full_house: int | None = None
    """1 住居あたりの人数上限．例: Farmer=10．"""
    dlcs: tuple[str, ...] = Field(default_factory=tuple)
    needs: tuple[TierNeed, ...] = Field(default_factory=tuple)

    model_config = {"frozen": True}


class ConsumptionTable(BaseModel):
    """Tier 群の集合と locale 名 override．``load`` で YAML から構築する．"""

    tiers: tuple[PopulationTier, ...] = Field(default_factory=tuple)
    localized_names: tuple[tuple[str, tuple[tuple[int, str], ...]], ...] = Field(
        default_factory=tuple
    )
    """``((locale, ((tier_guid, 名前), ...)), ...)``．英語は ``tier.name`` を使う．"""

    model_config = {"frozen": True}

    @cached_property
    def _localized_name_lookup(self) -> dict[str, dict[int, str]]:
        return {locale: dict(entries) for locale, entries in self.localized_names}

    def get_tier(self, guid: int) -> PopulationTier | None:
        """tier guid で 1 件返す．未登録は ``None``．"""
        for tier in self.tiers:
            if tier.guid == guid:
                return tier
        return None

    def get_rate(self, tier_guid: int, product_guid: int) -> float | None:
        """``(tier, product)`` の tpmin を返す．組み合わせが無ければ ``None``．"""
        tier = self.get_tier(tier_guid)
        if tier is None:
            return None
        for need in tier.needs:
            if need.product_guid == product_guid:
                return need.tpmin
        return None

    def display_name(self, tier_guid: int, locale: str = "en") -> str | None:
        """``locale`` 優先 → 英語 fallback の順で tier 表示名を返す．"""
        if locale != "en":
            loc = self._localized_name_lookup.get(locale, {})
            if tier_guid in loc:
                return loc[tier_guid]
        tier = self.get_tier(tier_guid)
        return tier.name if tier is not None else None

    @classmethod
    def load(cls, *, data_dir: Path | None = None) -> ConsumptionTable:
        """canonical (en) + ``ja`` ローカライズ YAML を読み込む．

        ``data_dir`` が ``None`` なら同梱 ``anno_save_analyzer.data`` から読む．
        """
        if data_dir is None:
            en_text = _read_packaged(_EN_FILE)
            ja_text = _read_packaged(_JA_FILE)
        else:
            en_text = (data_dir / _EN_FILE).read_text(encoding="utf-8")
            ja_path = data_dir / _JA_FILE
            ja_text = ja_path.read_text(encoding="utf-8") if ja_path.exists() else None

        en_payload = yaml.safe_load(en_text) or {}
        ja_payload = yaml.safe_load(ja_text) if ja_text else None

        tiers = tuple(_tier_from_dict(t) for t in en_payload.get("tiers", []))
        localized: list[tuple[str, tuple[tuple[int, str], ...]]] = []
        if ja_payload:
            localized.append(
                (
                    "ja",
                    tuple(
                        (int(entry["guid"]), str(entry["name"]))
                        for entry in ja_payload.get("tiers", [])
                        if "guid" in entry and "name" in entry
                    ),
                )
            )
        return cls(tiers=tiers, localized_names=tuple(localized))


def _read_packaged(filename: str) -> str:
    return (resources.files(_DATA_PACKAGE) / filename).read_text(encoding="utf-8")


def _tier_from_dict(data: dict[str, Any]) -> PopulationTier:
    needs = tuple(_need_from_dict(n) for n in data.get("needs") or [])
    return PopulationTier(
        guid=int(data["guid"]),
        name=str(data.get("name") or ""),
        full_house=data.get("full_house"),
        dlcs=tuple(data.get("dlcs") or ()),
        needs=needs,
    )


def _need_from_dict(data: dict[str, Any]) -> TierNeed:
    raw_unlock = data.get("unlock_condition_guid")
    return TierNeed(
        product_guid=int(data["product_guid"]),
        tpmin=data.get("tpmin"),
        residents=int(data.get("residents") or 0),
        happiness=int(data.get("happiness") or 0),
        is_bonus_need=bool(data.get("is_bonus_need")),
        dlcs=tuple(data.get("dlcs") or ()),
        unlock_condition_guid=int(raw_unlock) if raw_unlock is not None else None,
    )
