"""タイトル横断の貿易データモデル．

すべての TradeEvent は title-agnostic．Anno 117 / Anno 1800 の差は
``trade.interpreter`` で吸収する．
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Locale code．"en" は必須サポート，他は任意．
Locale = str

PartnerKind = Literal["passive", "active", "route", "unknown"]
SourceMethod = Literal["history", "diff"]


class GameTitle(StrEnum):
    """対応タイトル．interpreter 切替の primary key．

    値は YAML ファイル名（``items_<title>.<locale>.yaml``）の `<title>` 部に
    そのまま使われるため，アンダースコア無しで統一する．
    """

    ANNO_1800 = "anno1800"
    ANNO_117 = "anno117"


class Item(BaseModel):
    """物資（GoodGuid に対応）．names は locale → name の dict．"""

    guid: int = Field(..., description="raw GoodGuid (int32)")
    names: dict[Locale, str] = Field(default_factory=dict)
    category: str | None = None

    model_config = {"frozen": True}

    @field_validator("names")
    @classmethod
    def _strip_empty_names(cls, value: dict[Locale, str]) -> dict[Locale, str]:
        return {k: v for k, v in value.items() if v}

    def display_name(self, locale: Locale) -> str:
        """指定 locale の名前．無ければ en にフォールバック，それも無ければ ``Good_<guid>``．"""
        return self.names.get(locale) or self.names.get("en") or f"Good_{self.guid}"


class TradingPartner(BaseModel):
    """貿易相手．プレイヤー所有ルート / NPC trader / passive partner を統合表現．"""

    id: str
    display_name: str
    kind: PartnerKind = "unknown"

    model_config = {"frozen": True}


class TradeEvent(BaseModel):
    """貿易台帳の 1 行．Method A / B 共通．"""

    timestamp_tick: int | None = None
    """ゲーム内 tick．未取得時は None．"""

    item: Item
    amount: int = Field(..., description="正=購入 / 負=売却")
    total_price: int = Field(..., description="正=金入 / 負=金出")
    partner: TradingPartner | None = None
    route_id: str | None = None
    session_id: str | None = None
    island_name: str | None = None
    """この取引が帰属するプレイヤー保有島の ``CityName``．NPC 同士の取引は
    interpreter 側で除外済みのためここに載るのは全てプレイヤー所有．
    TUI 側の Tree filter (島単位 / セッション単位) の key．
    """
    route_name: str | None = None
    """書記長がゲーム内で命名したトレードルート名．``partner_kind='route'`` の
    ときのみ意味を持つ．表示では ``route_name`` 優先，無ければ ``route_id`` を
    fallback．
    """
    source_method: SourceMethod = "history"

    model_config = {"frozen": True}

    @property
    def is_buy(self) -> bool:
        return self.amount > 0

    @property
    def is_sell(self) -> bool:
        return self.amount < 0
