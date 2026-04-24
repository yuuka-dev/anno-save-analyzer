"""``TuiState`` を pandas DataFrame に変換する中核ユーティリティ．

4 本の正規化された DataFrame を持つ ``AnalysisFrames`` を出力する．
後続の analyzer (deficit map / correlation / route ranking / forecast /
MILP) は全てこの DataFrame 表現を入力に取る．

``islands`` — 1 row = 1 island (AreaManager)．

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - column
     - type
     - description
   * - ``area_manager``
     - str
     - ``AreaManager_<N>`` タグ名 (join キー)
   * - ``city_name``
     - str / None
     - プレイヤー島なら設定．NPC は None
   * - ``is_player``
     - bool
     - ``city_name`` の有無で判定
   * - ``session_key``
     - str / None
     - ``session.anno1800.cape_trelawney`` など
   * - ``session_display``
     - str / None
     - Localizer 解決後 (「トレローニー岬」)
   * - ``resident_total``
     - int
     - 島の全人口
   * - ``residence_count``
     - int
     - 住居総数
   * - ``avg_saturation_mean``
     - float
     - 平均需要満足度 (residents-weighted)
   * - ``deficit_count``
     - int
     - balance table で赤字の物資数

``tiers`` — 1 row = 1 (island, tier)．

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - column
     - type
     - description
   * - ``area_manager``
     - str
     - join キー
   * - ``city_name``
     - str / None
     -
   * - ``tier``
     - str
     - ``farmer`` / ``worker`` / ... / ``unknown``
   * - ``residence_count``
     - int
     -
   * - ``resident_total``
     - int
     -
   * - ``avg_saturation_mean``
     - float
     - tier 単位の saturation

``balance`` — 1 row = 1 (island, product)．島の供給消費バランス．

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - column
     - type
     - description
   * - ``area_manager``
     - str
     -
   * - ``city_name``
     - str / None
     -
   * - ``product_guid``
     - int
     -
   * - ``product_name``
     - str
     - locale 適用後
   * - ``produced_per_minute``
     - float
     -
   * - ``consumed_per_minute``
     - float
     -
   * - ``delta_per_minute``
     - float
     - 負=赤字
   * - ``is_deficit``
     - bool
     -

``trade_events`` — 1 row = 1 TradeEvent．時系列分析の入力．

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - column
     - type
     - description
   * - ``timestamp_tick``
     - Int64
     - nullable integer．分単位変換は後続
   * - ``product_guid``
     - int
     -
   * - ``product_name``
     - str
     -
   * - ``amount``
     - int
     -
   * - ``total_price``
     - int
     -
   * - ``session_id``
     - str / None
     -
   * - ``island_name``
     - str / None
     -
   * - ``route_id``
     - str / None
     - ``str`` 化して ``route:123`` 形式で統一
   * - ``route_name``
     - str / None
     -
   * - ``partner_id``
     - str / None
     -
   * - ``partner_kind``
     - str / None
     - ``route`` / ``passive`` / ``unknown``
   * - ``source_method``
     - str
     - ``history`` 等
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from anno_save_analyzer.tui.i18n import Localizer
from anno_save_analyzer.tui.state import TuiState

_ISLANDS_COLUMNS = (
    "area_manager",
    "city_name",
    "is_player",
    "session_key",
    "session_display",
    "resident_total",
    "residence_count",
    "avg_saturation_mean",
    "deficit_count",
)
_TIERS_COLUMNS = (
    "area_manager",
    "city_name",
    "tier",
    "residence_count",
    "resident_total",
    "avg_saturation_mean",
)
_BALANCE_COLUMNS = (
    "area_manager",
    "city_name",
    "product_guid",
    "product_name",
    "produced_per_minute",
    "consumed_per_minute",
    "delta_per_minute",
    "is_deficit",
)
_TRADE_EVENT_COLUMNS = (
    "timestamp_tick",
    "product_guid",
    "product_name",
    "amount",
    "total_price",
    "session_id",
    "island_name",
    "route_id",
    "route_name",
    "partner_id",
    "partner_kind",
    "source_method",
)


@dataclass(frozen=True)
class AnalysisFrames:
    """分析層 4 本の DataFrame を保持．

    pandas DataFrame 自体は mutable なので dataclass の frozen は **参照
    差し替え禁止** 程度の保護 (中の値は書換可能)．分析 pipeline は純関数
    で書くこと．
    """

    islands: pd.DataFrame
    tiers: pd.DataFrame
    balance: pd.DataFrame
    trade_events: pd.DataFrame


def to_frames(state: TuiState, *, localizer: Localizer | None = None) -> AnalysisFrames:
    """``TuiState`` を ``AnalysisFrames`` に変換する．

    ``localizer`` 省略時は ``state.locale`` に対応する Localizer を load．
    後続の analyzer は pandas の ``groupby`` / ``pivot`` / ``merge`` で
    記述できる．
    """
    loc = localizer or Localizer.load(state.locale)
    islands_df = _islands_df(state, loc)
    tiers_df = _tiers_df(state, islands_df)
    balance_df = _balance_df(state, islands_df)
    events_df = _trade_events_df(state)
    return AnalysisFrames(
        islands=islands_df,
        tiers=tiers_df,
        balance=balance_df,
        trade_events=events_df,
    )


def _islands_df(state: TuiState, localizer: Localizer) -> pd.DataFrame:
    balance = state.balance_table
    # AreaManager → ResidenceAggregate lookup (city_name 無い島も拾いたいので
    # population_by_city よりも直接抽出の方が漏れないが現 state 経由が簡単)
    residences_by_am = {agg.area_manager: agg for agg in state.population_by_city.values()}

    rows: list[dict] = []
    if balance is not None:
        for isl in balance.islands:
            city_name = state.area_manager_to_city.get(isl.area_manager) or isl.city_name
            session_key = state.area_manager_to_session_key.get(isl.area_manager)
            session_display = localizer.t(session_key) if session_key else None
            residence = residences_by_am.get(isl.area_manager)
            rows.append(
                {
                    "area_manager": isl.area_manager,
                    "city_name": city_name,
                    "is_player": city_name is not None,
                    "session_key": session_key,
                    "session_display": session_display,
                    "resident_total": isl.resident_total,
                    "residence_count": (residence.residence_count if residence is not None else 0),
                    "avg_saturation_mean": (
                        residence.avg_saturation_mean if residence is not None else float("nan")
                    ),
                    "deficit_count": sum(1 for p in isl.products if p.is_deficit),
                }
            )
    return _make_df(rows, _ISLANDS_COLUMNS)


def _tiers_df(state: TuiState, islands_df: pd.DataFrame) -> pd.DataFrame:
    residences_by_am = {agg.area_manager: agg for agg in state.population_by_city.values()}
    # city_name lookup 用に islands_df を使う (join より明示的)
    city_by_am = dict(zip(islands_df["area_manager"], islands_df["city_name"], strict=False))

    rows: list[dict] = []
    for am, agg in residences_by_am.items():
        for ts in agg.tier_breakdown:
            rows.append(
                {
                    "area_manager": am,
                    "city_name": city_by_am.get(am),
                    "tier": ts.tier,
                    "residence_count": ts.residence_count,
                    "resident_total": ts.resident_total,
                    "avg_saturation_mean": ts.avg_saturation_mean,
                }
            )
    return _make_df(rows, _TIERS_COLUMNS)


def _balance_df(state: TuiState, islands_df: pd.DataFrame) -> pd.DataFrame:
    balance = state.balance_table
    if balance is None:
        return _make_df([], _BALANCE_COLUMNS)
    city_by_am = dict(zip(islands_df["area_manager"], islands_df["city_name"], strict=False))

    rows: list[dict] = []
    for isl in balance.islands:
        for p in isl.products:
            item = state.items[p.product_guid]
            name = item.display_name(state.locale) or f"Good_{p.product_guid}"
            rows.append(
                {
                    "area_manager": isl.area_manager,
                    "city_name": city_by_am.get(isl.area_manager),
                    "product_guid": p.product_guid,
                    "product_name": name,
                    "produced_per_minute": p.produced_per_minute,
                    "consumed_per_minute": p.consumed_per_minute,
                    "delta_per_minute": p.delta_per_minute,
                    "is_deficit": p.is_deficit,
                }
            )
    return _make_df(rows, _BALANCE_COLUMNS)


def _trade_events_df(state: TuiState) -> pd.DataFrame:
    rows: list[dict] = []
    for ev in state.events:
        item_name = ev.item.display_name(state.locale) or f"Good_{ev.item.guid}"
        rows.append(
            {
                "timestamp_tick": ev.timestamp_tick,
                "product_guid": ev.item.guid,
                "product_name": item_name,
                "amount": ev.amount,
                "total_price": ev.total_price,
                "session_id": ev.session_id,
                "island_name": ev.island_name,
                "route_id": ev.route_id,
                "route_name": ev.route_name,
                "partner_id": ev.partner.id if ev.partner else None,
                "partner_kind": ev.partner.kind if ev.partner else None,
                "source_method": ev.source_method,
            }
        )
    df = _make_df(rows, _TRADE_EVENT_COLUMNS)
    # timestamp_tick は NaN 混ざりうるので pandas の nullable Int64 に揃える
    if not df.empty:
        df = df.astype({"timestamp_tick": "Int64"})
    return df


def _make_df(rows: list[dict], columns: tuple[str, ...]) -> pd.DataFrame:
    """空でも column schema を保持する DataFrame を返す．"""
    if not rows:
        return pd.DataFrame(columns=list(columns))
    return pd.DataFrame(rows, columns=list(columns))
