"""Anno 117 の ``items_anno117.<locale>.yaml`` をゲーム本体から自動生成する．

使い方:

    python scripts/generate_items_anno117.py \
        --install "/mnt/d/SteamLibrary/steamapps/common/Anno 117 - Pax Romana" \
        --data-dir src/anno_save_analyzer/data

前提:

- 書記長 (or 利用者) がローカルに Anno 117 Pax Romana のインストールを持ってる
- ``<install>/maindata/config.rda`` 内部に:
    - ``data/base/config/export/assets.xml`` (Product 定義 + OasisId)
    - ``data/base/config/gui/texts_<language>.xml`` (OasisId → 多言語 UI テキスト)
  が入ってる (確認済)

仕様:

- ``<Asset><Template>Product</Template>`` の全件について
  ``Standard/GUID`` と ``Text/OasisId`` を拾う
- ``texts_english.xml`` / ``texts_japanese.xml`` から OasisId → text の map を引く
- ``items_anno117.en.yaml`` / ``items_anno117.ja.yaml`` を GUID 昇順で書き出す
- UI 表記 (texts_*.xml) が内部名 (``"Good Flax"``) より優先．UI にテキスト無い (OasisId が
  texts に無い) 場合は内部 name から prefix (``"Good "``) を剥いてフォールバック
- 既存 YAML の category フィールドは保存される

出力:

- ``<data-dir>/items_anno117.en.yaml`` および ``items_anno117.ja.yaml`` を生成
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml
from lxml import etree

from anno_save_analyzer.parser.rda import RDAArchive

_ASSETS_XML = "data/base/config/export/assets.xml"
_TEXTS_XML_TMPL = "data/base/config/gui/texts_{lang}.xml"
_PREFIXES_TO_STRIP = ("Good ", "Service ", "Workforce ")

# locale code → texts_<lang>.xml の <lang> 部 (Anno 117 命名規則に合わせる)
_LOCALE_TO_LANG = {
    "en": "english",
    "ja": "japanese",
    "de": "german",
    "fr": "french",
    "zh": "simplified_chinese",
    "ko": "korean",
    "it": "italian",
    "es": "spanish",
    "pl": "polish",
    "ru": "russian",
    "pt": "brazilian",
    "zh_tw": "traditional_chinese",
}


def _strip_internal_prefix(name: str) -> str:
    for prefix in _PREFIXES_TO_STRIP:
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


def _build_text_map(xml_bytes: bytes) -> dict[int, str]:
    """texts_<lang>.xml の ``<Text><LineId>..</LineId><Text>..</Text></Text>`` を map 化．"""
    parser = etree.XMLParser(huge_tree=True, recover=True)
    root = etree.fromstring(xml_bytes, parser=parser)
    out: dict[int, str] = {}
    for el in root.iter("Text"):
        lid = el.find("LineId")
        tx = el.find("Text")
        if lid is None or tx is None or not lid.text:
            continue
        try:
            key = int(lid.text)
        except ValueError:
            continue
        # Anno の日本語テキストには U+200B (zero-width space) が入ってるので除去
        value = (tx.text or "").replace("\u200b", "")
        out[key] = value
    return out


def extract_products(config_data: bytes) -> list[dict[str, Any]]:
    """assets.xml から Product asset のメタ情報を抽出．"""
    parser = etree.XMLParser(huge_tree=True, recover=True)
    root = etree.fromstring(config_data, parser=parser)
    products: list[dict[str, Any]] = []
    for asset in root.iter("Asset"):
        tpl = asset.find("Template")
        if tpl is None or tpl.text != "Product":
            continue
        guid_el = asset.find("Values/Standard/GUID")
        name_el = asset.find("Values/Standard/Name")
        oasis_el = asset.find("Values/Text/OasisId")
        if guid_el is None or name_el is None or not guid_el.text or not name_el.text:
            continue
        try:
            guid = int(guid_el.text)
            oid = int(oasis_el.text) if oasis_el is not None and oasis_el.text else None
        except ValueError:
            continue
        products.append(
            {
                "guid": guid,
                "internal_name": name_el.text,
                "oasis_id": oid,
            }
        )
    products.sort(key=lambda p: p["guid"])
    return products


def resolve_localized_name(product: dict[str, Any], text_map: dict[int, str]) -> str:
    """Product の OasisId を使って localized name を取得．無ければ内部名の prefix 剥き．"""
    oid = product["oasis_id"]
    if oid is not None and oid in text_map and text_map[oid]:
        return text_map[oid]
    return _strip_internal_prefix(product["internal_name"])


def load_existing_categories(path: Path) -> dict[int, str]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        int(guid): entry["category"]
        for guid, entry in raw.items()
        if isinstance(entry, dict) and entry.get("category")
    }


def write_items_yaml(
    products: list[dict[str, Any]],
    text_map: dict[int, str],
    output: Path,
    locale: str,
    existing_cat: dict[int, str],
) -> None:
    header = [
        f"# Anno 117: Pax Romana — item dictionary ({locale}).",
        "# Auto-generated from config.rda/assets.xml + texts_<lang>.xml",
        "# by scripts/generate_items_anno117.py. Re-run after game updates.",
        "",
    ]
    lines: list[str] = list(header)
    for p in products:
        name = resolve_localized_name(p, text_map)
        lines.append(f"{p['guid']}:")
        lines.append(f"  name: {_yaml_quote(name)}")
        cat = existing_cat.get(p["guid"])
        if cat:
            lines.append(f"  category: {_yaml_quote(cat)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _yaml_quote(s: str) -> str:
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--install",
        type=Path,
        required=True,
        help="Anno 117 install directory (contains maindata/)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="output directory (where items_anno117.<locale>.yaml go)",
    )
    parser.add_argument(
        "--locales",
        nargs="+",
        default=["en", "ja"],
        help="locale codes to generate (default: en ja)",
    )
    args = parser.parse_args()

    config_rda = args.install / "maindata" / "config.rda"
    if not config_rda.exists():
        raise FileNotFoundError(f"config.rda not found at {config_rda}")

    with RDAArchive(config_rda) as ar:
        assets_data = ar.read(_ASSETS_XML)
        text_maps: dict[str, dict[int, str]] = {}
        for loc in args.locales:
            lang = _LOCALE_TO_LANG.get(loc)
            if lang is None:
                print(f"  skipping unknown locale {loc!r} (not in _LOCALE_TO_LANG)")
                continue
            texts_path = _TEXTS_XML_TMPL.format(lang=lang)
            try:
                text_maps[loc] = _build_text_map(ar.read(texts_path))
            except KeyError:
                print(f"  warning: {texts_path} not in config.rda (locale {loc!r})")

    products = extract_products(assets_data)
    print(f"extracted {len(products)} Products")

    for loc, text_map in text_maps.items():
        out = args.data_dir / f"items_anno117.{loc}.yaml"
        existing = load_existing_categories(out)
        write_items_yaml(products, text_map, out, loc, existing)
        print(f"  wrote {out}  ({len(text_map):,} text entries merged)")


if __name__ == "__main__":
    main()
