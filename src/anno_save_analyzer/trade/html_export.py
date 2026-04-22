"""単一 HTML ダッシュボード生成．

``^O`` export に HTML を追加するための純関数．全データを JSON 埋め込みで
持ち，Plotly を CDN ロードしてクライアント側で描画する．1 ファイルだけで
書記長のブラウザでそのまま開ける．

設計方針:

- 依存を増やさない．Plotly 等は CDN 参照で良い．オフライン運用が必要に
  なったら inline bundle 化するが現状 YAGNI．
- データは ``<script type="application/json">`` に載せて JS で描画．
  markdown の表も添えて jq / Excel / pandas にコピペしやすく．
- Section: Overview / Trade / Inventory / Analysis．``^T`` 的な遷移は
  anchor link で済ます．
- セーブ由来の文字列 (島名 / ルート名 / アイテム名) は信頼できん前提で
  JS 側で textContent / createElement 経由でのみ DOM に差し込む．
  innerHTML でのエスケープ漏れは避ける．

依存は stdlib + ``html`` (escape 用) のみ．
"""

from __future__ import annotations

import html
import json
from collections.abc import Iterable
from typing import Any

from .aggregate import ItemSummary, RouteSummary
from .analysis import (
    ProductBalance,
    compute_runways,
    display_runway_rows,
    shortage_list,
    supply_demand_balance,
)
from .clock import TICKS_PER_MINUTE, latest_tick
from .items import ItemDictionary
from .models import GameTitle, Locale, TradeEvent
from .population import CityAreaMatch, ResidenceAggregate
from .storage import IslandStorageTrend

_PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"


def _localize_name(items: ItemDictionary | dict, guid: int, locale: str) -> str:
    try:
        return items[guid].display_name(locale)
    except (KeyError, AttributeError):
        return f"Good_{guid}"


def _events_payload(
    events: Iterable[TradeEvent], items: ItemDictionary, locale: str
) -> list[dict[str, Any]]:
    events_list = list(events)
    now_tick = latest_tick(e.timestamp_tick for e in events_list if e.timestamp_tick is not None)
    out: list[dict[str, Any]] = []
    for ev in events_list:
        min_ago: float | None
        if ev.timestamp_tick is None or now_tick is None:
            min_ago = None
        else:
            min_ago = round((now_tick - ev.timestamp_tick) / TICKS_PER_MINUTE, 2)
        out.append(
            {
                "tick": ev.timestamp_tick,
                "min_ago": min_ago,
                "session": ev.session_id,
                "island": ev.island_name,
                "route_id": ev.route_id,
                "route_name": ev.route_name,
                "partner_id": ev.partner.id if ev.partner else None,
                "partner_kind": ev.partner.kind if ev.partner else None,
                "item_guid": ev.item.guid,
                "item_name": _localize_name(items, ev.item.guid, locale),
                "amount": ev.amount,
                "total_price": ev.total_price,
            }
        )
    return out


def _items_payload(summaries: Iterable[ItemSummary], locale: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in summaries:
        out.append(
            {
                "guid": s.item.guid,
                "name": s.display_name(locale),
                "category": s.item.category,
                "bought": s.bought,
                "sold": s.sold,
                "net_qty": s.net_qty,
                "net_gold": s.net_gold,
                "event_count": s.event_count,
                "last_seen_tick": s.last_seen_tick,
            }
        )
    return out


def _routes_payload(
    summaries: Iterable[RouteSummary],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in summaries:
        out.append(
            {
                "route_id": s.route_id,
                "route_name": s.route_name,
                "partner_kind": s.partner_kind,
                "bought": s.bought,
                "sold": s.sold,
                "net_gold": s.net_gold,
                "event_count": s.event_count,
                "last_seen_tick": s.last_seen_tick,
            }
        )
    return out


def _inventory_payload(
    trends: Iterable[IslandStorageTrend], items: ItemDictionary, locale: str
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tr in trends:
        out.append(
            {
                "island": tr.island_name,
                "guid": tr.product_guid,
                "name": _localize_name(items, tr.product_guid, locale),
                "latest": tr.latest,
                "peak": tr.peak,
                "mean": round(tr.points.mean, 2),
                "slope_per_min": round(tr.points.slope, 3),
                "last_point_tick": tr.last_point_tick,
                "samples": list(tr.points.samples),
            }
        )
    return out


def _balance_payload(
    balances: Iterable[ProductBalance], items: ItemDictionary, locale: str
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for b in balances:
        out.append(
            {
                "guid": b.product_guid,
                "name": _localize_name(items, b.product_guid, locale),
                "net_slope_per_min": round(b.net_slope_per_min, 3),
                "surplus_islands": list(b.surplus_islands),
                "deficit_islands": list(b.deficit_islands),
            }
        )
    return out


def _population_payload(
    populations: dict[str, ResidenceAggregate],
    matches: Iterable[CityAreaMatch],
    items: ItemDictionary,
    locale: str,
) -> list[dict[str, Any]]:
    """city_name → ResidenceAggregate + match 信頼度を融合した flat row 配列．"""
    match_by_city = {m.city_name: m for m in matches}
    out: list[dict[str, Any]] = []
    for city, agg in populations.items():
        m = match_by_city.get(city)
        out.append(
            {
                "city": city,
                "residents": agg.resident_total,
                "residences": agg.residence_count,
                "residents_per_residence": round(agg.residents_per_residence, 2),
                "avg_saturation": round(agg.avg_saturation_mean, 3),
                "product_money": agg.product_money_total,
                "newspaper_money": agg.newspaper_money_total,
                "gold_per_resident": round(agg.gold_per_resident, 3),
                "goods_tracked": len(agg.product_saturations),
                "match_area_manager": m.area_manager if m else "",
                "match_jaccard": m.jaccard if m else None,
                "match_confidence": m.confidence if m else "n/a",
                "saturations": [
                    {
                        "guid": ps.product_guid,
                        "name": _localize_name(items, ps.product_guid, locale),
                        "current": round(ps.current, 3),
                        "average": round(ps.average, 3),
                    }
                    for ps in agg.product_saturations
                ],
            }
        )
    out.sort(key=lambda r: -r["residents"])
    return out


def build_dashboard_data(
    *,
    events: Iterable[TradeEvent],
    item_summaries: Iterable[ItemSummary],
    route_summaries: Iterable[RouteSummary],
    inventory_trends: Iterable[IslandStorageTrend],
    items: ItemDictionary,
    title: GameTitle,
    locale: Locale = "en",
    save_name: str = "save",
    populations: dict[str, ResidenceAggregate] | None = None,
    city_area_matches: Iterable[CityAreaMatch] = (),
) -> dict[str, Any]:
    """HTML 埋め込み用 JSON blob を組み立てる．純関数．

    ``populations`` / ``city_area_matches`` は v0.4.3 PR B で追加．未指定なら
    Population セクションは空になる (後方互換)．
    """
    trends_list = list(inventory_trends)
    runways = compute_runways(trends_list)
    shortages = shortage_list(trends_list, threshold_min=120.0)
    balances = supply_demand_balance(trends_list)

    return {
        "meta": {
            "title": str(title.value),
            "save": save_name,
            "locale": locale,
            "ticks_per_minute": TICKS_PER_MINUTE,
        },
        "events": _events_payload(events, items, locale),
        "items": _items_payload(item_summaries, locale),
        "routes": _routes_payload(route_summaries),
        "inventory": _inventory_payload(trends_list, items, locale),
        "runways": display_runway_rows(runways, items, locale),
        "shortages": display_runway_rows(shortages, items, locale),
        "balances": _balance_payload(balances, items, locale),
        "populations": _population_payload(populations or {}, city_area_matches, items, locale),
    }


def dashboard_to_html(
    data: dict[str, Any],
    *,
    title_text: str = "anno-save-analyzer dashboard",
) -> str:
    """JSON データから単一 HTML (Plotly + 表 + 埋め込み JSON) を生成．"""
    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # XSS 対策: embedded JSON 中の ``</script>`` や ``<!--`` / ``-->`` が
    # HTML parser に解釈されるのを防ぐ．後処理では JSON として常に合法な
    # escape のみを使う必要があるため、``<`` / ``>`` を Unicode escape に
    # 置換する。JSON parser は ``\\u003c`` / ``\\u003e`` を元の文字として読む。
    data_json = data_json.replace("<", "\\u003c").replace(">", "\\u003e")
    meta = data["meta"]
    title_html = html.escape(title_text)
    save_html = html.escape(meta.get("save", "save"))
    title_label = html.escape(meta.get("title", ""))
    return _TEMPLATE.format(
        title_html=title_html,
        save_html=save_html,
        title_label=title_label,
        locale=html.escape(meta.get("locale", "en")),
        plotly_cdn=_PLOTLY_CDN,
        data_json=data_json,
    )


# HTML template. Double-braced literals are .format escapes for JS.
# JS is strictly DOM-only (textContent / createElement) so save-derived strings
# are never interpolated via innerHTML.
_TEMPLATE = """<!DOCTYPE html>
<html lang="{locale}">
<head>
<meta charset="UTF-8">
<title>{title_html} — {save_html}</title>
<script src="{plotly_cdn}"></script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", sans-serif;
         margin: 0; padding: 0; color: #e0e0e0; background: #1a1a1a; }}
  header {{ padding: 1em 2em; border-bottom: 1px solid #333; display: flex; gap: 2em; align-items: baseline; }}
  header h1 {{ margin: 0; font-size: 1.4em; color: #ffd670; }}
  header .meta {{ color: #888; font-size: 0.9em; }}
  nav {{ padding: 0 2em; border-bottom: 1px solid #333; background: #222; }}
  nav a {{ display: inline-block; padding: 0.8em 1em; color: #ffd670; text-decoration: none; border-bottom: 2px solid transparent; }}
  nav a:hover {{ border-bottom-color: #ffd670; }}
  main {{ padding: 2em; max-width: 1400px; margin: 0 auto; }}
  section {{ margin-bottom: 3em; scroll-margin-top: 1em; }}
  section h2 {{ color: #ffd670; border-bottom: 1px solid #444; padding-bottom: 0.3em; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 1em; font-size: 0.9em; }}
  th, td {{ padding: 0.4em 0.8em; text-align: left; border-bottom: 1px solid #2a2a2a; }}
  th {{ background: #262626; position: sticky; top: 0; cursor: pointer; }}
  th:hover {{ background: #303030; }}
  tr:hover td {{ background: #252525; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .chart {{ background: #222; border: 1px solid #333; padding: 0.5em; border-radius: 4px; }}
  .status-depleted {{ color: #ff5555; font-weight: bold; }}
  .status-critical {{ color: #ff9955; font-weight: bold; }}
  .status-warning {{ color: #ffd670; }}
  .status-ok {{ color: #66dd66; }}
  .status-stable_or_growing {{ color: #5ba8ff; }}
  .hint {{ color: #888; font-size: 0.85em; margin-top: 0.3em; }}
  ul.stats {{ list-style: none; padding: 0; display: flex; gap: 2em; flex-wrap: wrap; }}
  ul.stats li b {{ color: #ffd670; }}
</style>
</head>
<body>
<header>
  <h1>{title_html}</h1>
  <div class="meta">save: <b>{save_html}</b> · title: <b>{title_label}</b> · locale: <b>{locale}</b></div>
</header>
<nav>
  <a href="#overview">Overview</a>
  <a href="#shortages">Shortages</a>
  <a href="#balance">Supply / Demand</a>
  <a href="#inventory">Inventory</a>
  <a href="#population">Population</a>
  <a href="#items">Items</a>
  <a href="#routes">Routes</a>
  <a href="#events">Events</a>
</nav>
<main>
  <section id="overview">
    <h2>Overview</h2>
    <ul class="stats" id="overview-stats"></ul>
    <div class="chart" id="chart-trade-volume"></div>
    <div class="hint">Trade volume over time (points per session).</div>
  </section>

  <section id="shortages">
    <h2>Shortages <span class="hint">(runway ≤ 120 min)</span></h2>
    <div class="chart" id="chart-shortages" style="min-height: 420px;"></div>
    <div id="shortages-table"></div>
  </section>

  <section id="balance">
    <h2>Supply / Demand balance per good</h2>
    <div id="balance-table"></div>
    <div class="hint">Sorted by net slope (/ min) across all islands. Positive = surplus, negative = deficit.</div>
  </section>

  <section id="inventory">
    <h2>Inventory (per island × good)</h2>
    <div id="inventory-table"></div>
  </section>

  <section id="population">
    <h2>Population & Need Saturation (per city)</h2>
    <div class="chart" id="chart-population" style="min-height: 360px;"></div>
    <div id="population-table"></div>
    <p class="hint">
      City ↔ AreaManager is joined by Jaccard overlap of product sets; low confidence
      matches (jaccard &lt; 0.15) may swap between cities of the same size.
      Click a row to see per-good saturation below.
    </p>
    <h3 id="saturation-heading" style="color:#ffd670;margin-top:1em;"></h3>
    <div id="saturation-table"></div>
  </section>

  <section id="items">
    <h2>Trade volume by item</h2>
    <div id="items-table"></div>
  </section>

  <section id="routes">
    <h2>Trade volume by route</h2>
    <div id="routes-table"></div>
  </section>

  <section id="events">
    <h2>Events (raw)</h2>
    <div class="hint">Trade events. Use browser search (Ctrl+F) or copy into a spreadsheet.</div>
    <div id="events-table"></div>
  </section>
</main>
<script type="application/json" id="dashboard-data">{data_json}</script>
<script>
(function() {{
  const raw = document.getElementById('dashboard-data').textContent;
  const D = JSON.parse(raw);

  function el(tag, props, children) {{
    const node = document.createElement(tag);
    if (props) {{
      for (const k in props) {{
        if (k === 'class') node.className = props[k];
        else if (k === 'text') node.textContent = props[k];
        else node.setAttribute(k, props[k]);
      }}
    }}
    if (children) for (const c of children) {{
      if (c == null) continue;
      node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    }}
    return node;
  }}

  function statLi(label, value) {{
    return el('li', null, [label + ': ', el('b', {{text: value}})]);
  }}

  // --- Overview stats ---
  const statsUl = document.getElementById('overview-stats');
  const nEvents = D.events.length;
  const totalGold = D.events.reduce((a, e) => a + (e.total_price || 0), 0);
  const nItems = new Set(D.events.map(e => e.item_guid)).size;
  const nRoutes = new Set(D.events.filter(e => e.route_id).map(e => e.route_id)).size;
  const nIslands = new Set(D.inventory.map(t => t.island)).size;
  [
    ['Events', nEvents.toLocaleString()],
    ['Distinct items', String(nItems)],
    ['Distinct routes', String(nRoutes)],
    ['Player islands', String(nIslands)],
    ['Net gold', totalGold.toLocaleString() + ' g'],
  ].forEach(([l, v]) => statsUl.appendChild(statLi(l, v)));

  // --- Trade volume chart ---
  const bySession = {{}};
  D.events.forEach(ev => {{
    if (ev.min_ago == null) return;
    const s = ev.session || '-';
    if (!bySession[s]) bySession[s] = {{x: [], y: []}};
    bySession[s].x.push(-ev.min_ago);
    bySession[s].y.push(Math.abs(ev.amount));
  }});
  const traces = Object.keys(bySession).sort().map(s => ({{
    x: bySession[s].x, y: bySession[s].y, mode: 'markers', type: 'scatter',
    name: 'session ' + s, marker: {{size: 4, opacity: 0.5}}
  }}));
  Plotly.newPlot('chart-trade-volume', traces, {{
    paper_bgcolor: '#222', plot_bgcolor: '#222',
    font: {{color: '#ddd'}},
    xaxis: {{title: 'minutes ago', autorange: 'reversed'}},
    yaxis: {{title: '|amount|'}},
    margin: {{t: 20, r: 20, b: 40, l: 60}},
    height: 360
  }}, {{displaylogo: false, responsive: true}});

  // --- Shortages chart ---
  const sh = D.shortages.slice(0, 40);
  Plotly.newPlot('chart-shortages', [{{
    type: 'bar', orientation: 'h',
    x: sh.map(r => r.runway_min),
    y: sh.map(r => r.product_name + ' @ ' + r.island_name),
    marker: {{color: sh.map(r => r.status === 'depleted' ? '#ff5555' : r.status === 'critical' ? '#ff9955' : '#ffd670')}},
    text: sh.map(r => String(r.runway_min) + 'm'),
    textposition: 'auto'
  }}], {{
    paper_bgcolor: '#222', plot_bgcolor: '#222',
    font: {{color: '#ddd'}},
    xaxis: {{title: 'minutes until empty'}},
    yaxis: {{automargin: true}},
    margin: {{t: 20, r: 20, b: 40, l: 20}},
  }}, {{displaylogo: false, responsive: true}});

  // --- Generic sortable table renderer (textContent only, no innerHTML) ---
  function renderTable(containerId, rows, columns) {{
    const container = document.getElementById(containerId);
    container.textContent = '';
    if (!rows.length) {{
      container.appendChild(el('p', {{class: 'hint', text: '(no rows)'}}));
      return;
    }}
    let sortKey = null, sortAsc = true;
    function buildTable() {{
      container.textContent = '';
      const sorted = sortKey ? [...rows].sort((a, b) => {{
        const av = a[sortKey], bv = b[sortKey];
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        if (typeof av === 'number' && typeof bv === 'number') return sortAsc ? av - bv : bv - av;
        return sortAsc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
      }}) : rows;
      const table = el('table');
      const thead = el('thead');
      const headerRow = el('tr');
      columns.forEach(c => {{
        const th = el('th', {{text: c.label + (sortKey === c.key ? (sortAsc ? ' ▲' : ' ▼') : '')}});
        th.addEventListener('click', () => {{
          if (sortKey === c.key) sortAsc = !sortAsc;
          else {{ sortKey = c.key; sortAsc = true; }}
          buildTable();
        }});
        headerRow.appendChild(th);
      }});
      thead.appendChild(headerRow);
      table.appendChild(thead);
      const tbody = el('tbody');
      sorted.forEach(r => {{
        const tr = el('tr');
        columns.forEach(c => {{
          const v = r[c.key];
          let disp;
          if (v == null) disp = '';
          else if (Array.isArray(v)) disp = v.join(', ');
          else if (typeof v === 'number') disp = v.toLocaleString();
          else disp = String(v);
          const td = el('td', {{text: disp}});
          if (typeof v === 'number') td.className = 'num';
          if (c.statusCol && r.status) td.className = 'status-' + r.status;
          tr.appendChild(td);
        }});
        tbody.appendChild(tr);
      }});
      table.appendChild(tbody);
      container.appendChild(table);
    }}
    buildTable();
  }}

  renderTable('shortages-table', D.shortages, [
    {{key: 'island_name', label: 'Island'}},
    {{key: 'product_name', label: 'Good'}},
    {{key: 'latest', label: 'Latest'}},
    {{key: 'slope_per_min', label: 'Slope/min'}},
    {{key: 'runway_min', label: 'Runway (min)'}},
    {{key: 'status', label: 'Status', statusCol: true}},
  ]);

  renderTable('balance-table', D.balances, [
    {{key: 'name', label: 'Good'}},
    {{key: 'net_slope_per_min', label: 'Net slope/min'}},
    {{key: 'surplus_islands', label: 'Surplus islands'}},
    {{key: 'deficit_islands', label: 'Deficit islands'}},
  ]);

  renderTable('inventory-table', D.inventory, [
    {{key: 'island', label: 'Island'}},
    {{key: 'name', label: 'Good'}},
    {{key: 'latest', label: 'Latest'}},
    {{key: 'peak', label: 'Peak'}},
    {{key: 'mean', label: 'Mean'}},
    {{key: 'slope_per_min', label: 'Slope/min'}},
  ]);

  // --- Population section ---
  const pops = D.populations || [];
  if (pops.length) {{
    // Horizontal bar chart of residents per city
    Plotly.newPlot('chart-population', [{{
      type: 'bar', orientation: 'h',
      x: pops.slice(0, 30).map(r => r.residents),
      y: pops.slice(0, 30).map(r => r.city),
      marker: {{color: pops.slice(0, 30).map(r => r.avg_saturation < 0.3 ? '#ff5555' : r.avg_saturation < 0.5 ? '#ffd670' : '#66dd66')}},
      text: pops.slice(0, 30).map(r => r.residents.toLocaleString() + ' (sat ' + (r.avg_saturation * 100).toFixed(0) + '%)'),
      textposition: 'auto'
    }}], {{
      paper_bgcolor: '#222', plot_bgcolor: '#222',
      font: {{color: '#ddd'}},
      xaxis: {{title: 'Residents'}},
      yaxis: {{automargin: true}},
      margin: {{t: 20, r: 20, b: 40, l: 20}},
    }}, {{displaylogo: false, responsive: true}});

    // Click-to-drill saturation table
    const satHeading = document.getElementById('saturation-heading');
    const satContainer = document.getElementById('saturation-table');
    function showSaturations(pop) {{
      satHeading.textContent = pop.city + ' — per-good saturation';
      renderTable('saturation-table', pop.saturations, [
        {{key: 'name', label: 'Good'}},
        {{key: 'current', label: 'Current'}},
        {{key: 'average', label: 'Average'}},
      ]);
    }}

    // Population table with row-click to drill saturations
    const popContainer = document.getElementById('population-table');
    popContainer.textContent = '';
    const popCols = [
      {{key: 'city', label: 'City'}},
      {{key: 'residents', label: 'Residents'}},
      {{key: 'residences', label: 'Residences'}},
      {{key: 'residents_per_residence', label: 'Avg /residence'}},
      {{key: 'avg_saturation', label: 'Avg saturation'}},
      {{key: 'product_money', label: 'Product $'}},
      {{key: 'gold_per_resident', label: '$ per resident'}},
      {{key: 'goods_tracked', label: '# Goods'}},
      {{key: 'match_area_manager', label: 'Matched AM'}},
      {{key: 'match_confidence', label: 'Confidence'}},
    ];
    const popTable = el('table');
    const popThead = el('thead');
    const popHeaderRow = el('tr');
    popCols.forEach(c => popHeaderRow.appendChild(el('th', {{text: c.label}})));
    popThead.appendChild(popHeaderRow);
    popTable.appendChild(popThead);
    const popTbody = el('tbody');
    pops.forEach(r => {{
      const tr = el('tr');
      popCols.forEach(c => {{
        const v = r[c.key];
        let disp = v == null ? '' : (typeof v === 'number' ? v.toLocaleString() : String(v));
        const td = el('td', {{text: disp}});
        if (typeof v === 'number') td.className = 'num';
        if (c.key === 'match_confidence' && v) {{
          td.className = (td.className ? td.className + ' ' : '') + 'status-' + (v === 'high' ? 'ok' : v === 'medium' ? 'warning' : 'critical');
        }}
        tr.appendChild(td);
      }});
      tr.style.cursor = 'pointer';
      tr.addEventListener('click', () => showSaturations(r));
      popTbody.appendChild(tr);
    }});
    popTable.appendChild(popTbody);
    popContainer.appendChild(popTable);

    // initial selection: top city
    if (pops[0]) showSaturations(pops[0]);
  }} else {{
    document.getElementById('population-table').appendChild(
      el('p', {{class: 'hint', text: '(no population data; only supported for Anno 1800 at present)'}})
    );
  }}

  renderTable('items-table', D.items, [
    {{key: 'name', label: 'Good'}},
    {{key: 'bought', label: 'Bought'}},
    {{key: 'sold', label: 'Sold'}},
    {{key: 'net_qty', label: 'Net qty'}},
    {{key: 'net_gold', label: 'Net gold'}},
    {{key: 'event_count', label: 'Events'}},
  ]);

  renderTable('routes-table', D.routes, [
    {{key: 'route_id', label: 'Route ID'}},
    {{key: 'route_name', label: 'Route name'}},
    {{key: 'partner_kind', label: 'Kind'}},
    {{key: 'bought', label: 'Bought'}},
    {{key: 'sold', label: 'Sold'}},
    {{key: 'net_gold', label: 'Net gold'}},
    {{key: 'event_count', label: 'Events'}},
  ]);

  const eventRows = D.events.slice(0, 2000);
  renderTable('events-table', eventRows, [
    {{key: 'min_ago', label: 'min ago'}},
    {{key: 'island', label: 'Island'}},
    {{key: 'route_name', label: 'Route'}},
    {{key: 'partner_kind', label: 'Kind'}},
    {{key: 'item_name', label: 'Good'}},
    {{key: 'amount', label: 'Amount'}},
    {{key: 'total_price', label: 'Gold'}},
  ]);
  if (D.events.length > 2000) {{
    const hint = el('p', {{class: 'hint',
      text: 'Showing first 2,000 of ' + D.events.length.toLocaleString() + ' events. Full data in embedded JSON.'}});
    document.getElementById('events-table').appendChild(hint);
  }}
}})();
</script>
</body>
</html>
"""
