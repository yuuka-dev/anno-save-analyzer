"""Anno 1800 の ``buildings_anno1800.<locale>.yaml`` をゲーム本体から自動生成する．

Residence / Factory / Farm / Warehouse / PublicService / BuffFactory 等の
建物 asset を ``maindata/dataN.rda`` 内 ``assets.xml`` から抽出し，
``{guid: {name, kind, tier?}}`` の形式で YAML に書き出す．

MVP 範囲:

- name (en/ja) — texts_<lang>.xml から GUID-direct lookup (items と同パターン)
- kind — ``residence`` / ``factory`` / ``farm`` / ``warehouse`` /
  ``public_service`` / ``buff_factory``
- tier — Residence のみ．internal Name ``residence_tier0N`` から 1..7 を推定

**非 MVP**: workforce_provided / workforce_required / inputs / outputs /
production chain は別 issue (#66, #12) で FactoryBase / ProductionChain
の深掘りと併せて対応する．

Usage::

    python scripts/generate_buildings_anno1800.py \\
        --install "/mnt/c/Program Files (x86)/Steam/steamapps/common/Anno 1800" \\
        --data-dir src/anno_save_analyzer/data
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from lxml import etree

from anno_save_analyzer.parser.rda import RDAArchive

# 隣接 script の helper を再利用．``scripts/`` は Python package ではないので
# ``sys.path`` 経由で直接 load する．
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_items_anno1800 import (  # noqa: E402
    _ASSETS_XML,
    _LOCALE_TO_LANG,
    _TEXTS_XML_TMPL,
    _build_text_map,
    find_latest_rda_for,
)

# Template 名 → kind の正規化．先頭一致ベース．
_KIND_RULES: tuple[tuple[str, str], ...] = (
    ("ResidenceBuilding", "residence"),
    ("FarmBuilding", "farm"),
    ("Farmfield", "farmfield"),
    ("RecipeFarm", "farm"),
    ("HeavyFactoryBuilding", "factory"),
    ("FactoryBuilding", "factory"),
    ("SlotFactoryBuilding", "factory"),
    ("BuffFactory", "buff_factory"),
    ("HarborWarehouse", "warehouse"),
    ("Warehouse", "warehouse"),
    ("PublicServiceBuilding", "public_service"),
    ("Market", "market"),
    ("VisitorPier", "pier"),
)

# Residence tier 番号 → 正規 tier key．Anno 1800 は 5 tier (+ DLC で 6, 7)．
_RES_TIER_RE = re.compile(r"residence_tier(\d{2})")
_TIER_KEY = {
    1: "farmer",
    2: "worker",
    3: "artisan",
    4: "engineer",
    5: "investor",
    # DLC
    6: "jornaleros",
    7: "obreros",
}


def _kind_for(template: str) -> str | None:
    for prefix, kind in _KIND_RULES:
        if template.startswith(prefix):
            return kind
    return None


def _tier_for(internal_name: str) -> str | None:
    match = _RES_TIER_RE.search(internal_name.lower())
    if not match:
        return None
    return _TIER_KEY.get(int(match.group(1)))


def extract_buildings(config_data: bytes) -> list[dict[str, Any]]:
    """assets.xml から建物 asset の guid / internal_name / kind / tier を抽出．"""
    parser = etree.XMLParser(huge_tree=True, recover=True)
    root = etree.fromstring(config_data, parser=parser)
    out: list[dict[str, Any]] = []
    for asset in root.iter("Asset"):
        tpl = asset.find("Template")
        if tpl is None or not tpl.text:
            continue
        kind = _kind_for(tpl.text)
        if kind is None:
            continue
        guid_el = asset.find("Values/Standard/GUID")
        name_el = asset.find("Values/Standard/Name")
        if guid_el is None or name_el is None or not guid_el.text or not name_el.text:
            continue
        try:
            guid = int(guid_el.text)
        except ValueError:
            continue
        entry: dict[str, Any] = {
            "guid": guid,
            "internal_name": name_el.text,
            "template": tpl.text,
            "kind": kind,
        }
        if kind == "residence":
            tier = _tier_for(name_el.text)
            if tier is not None:
                entry["tier"] = tier
        out.append(entry)
    out.sort(key=lambda e: e["guid"])
    return out


def resolve_localized_name(guid: int, internal_name: str, text_map: dict[int, str]) -> str:
    if guid in text_map and text_map[guid]:
        return text_map[guid]
    return internal_name


def _write_en_yaml(buildings: list[dict[str, Any]], text_map: dict[int, str], output: Path) -> None:
    header = [
        "# Anno 1800 — building dictionary (en, canonical).",
        "# Auto-generated from maindata/dataN.rda (latest)/assets.xml + texts_english.xml",
        "# by scripts/generate_buildings_anno1800.py. Re-run after game updates.",
        "",
    ]
    lines: list[str] = list(header)
    for b in buildings:
        name = resolve_localized_name(b["guid"], b["internal_name"], text_map)
        lines.append(f"{b['guid']}:")
        lines.append(f"  name: {_yaml_quote(name)}")
        lines.append(f"  kind: {b['kind']}")
        lines.append(f"  template: {_yaml_quote(b['template'])}")
        if "tier" in b:
            lines.append(f"  tier: {b['tier']}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_locale_name_yaml(
    buildings: list[dict[str, Any]],
    text_map: dict[int, str],
    output: Path,
    locale: str,
) -> None:
    header = [
        f"# Anno 1800 — building dictionary ({locale}, names only).",
        "# Generated alongside buildings_anno1800.en.yaml.",
        "",
    ]
    lines: list[str] = list(header)
    for b in buildings:
        name = text_map.get(b["guid"])
        if not name:
            continue
        lines.append(f"{b['guid']}:")
        lines.append(f"  name: {_yaml_quote(name)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _yaml_quote(s: str) -> str:
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _read_xml_from_rda(maindata: Path, member: str) -> bytes:
    rda_path = find_latest_rda_for(maindata, member)
    with RDAArchive(rda_path) as ar:
        return ar.read(member)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--install",
        type=Path,
        required=True,
        help="Anno 1800 install directory (contains maindata/)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="output directory (where buildings_anno1800.<locale>.yaml go)",
    )
    parser.add_argument("--locales", nargs="+", default=["en", "ja"])
    args = parser.parse_args()

    maindata = args.install / "maindata"
    if not maindata.is_dir():
        raise FileNotFoundError(f"maindata/ not found at {maindata}")

    assets_data = _read_xml_from_rda(maindata, _ASSETS_XML)
    buildings = extract_buildings(assets_data)
    print(f"extracted {len(buildings)} buildings")

    text_maps: dict[str, dict[int, str]] = {}
    for loc in args.locales:
        lang = _LOCALE_TO_LANG.get(loc)
        if lang is None:
            print(f"  skipping unknown locale {loc!r}")
            continue
        texts_path = _TEXTS_XML_TMPL.format(lang=lang)
        try:
            data = _read_xml_from_rda(maindata, texts_path)
        except FileNotFoundError:
            print(f"  warning: {texts_path} not found in maindata")
            continue
        text_maps[loc] = _build_text_map(data)

    en_out = args.data_dir / "buildings_anno1800.en.yaml"
    _write_en_yaml(buildings, text_maps.get("en", {}), en_out)
    print(f"  wrote {en_out}")
    for loc, tm in text_maps.items():
        if loc == "en":
            continue
        out = args.data_dir / f"buildings_anno1800.{loc}.yaml"
        _write_locale_name_yaml(buildings, tm, out, loc)
        print(f"  wrote {out}")


if __name__ == "__main__":
    main()
