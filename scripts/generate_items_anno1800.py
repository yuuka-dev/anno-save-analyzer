"""Anno 1800 の ``items_anno1800.<locale>.yaml`` をゲーム本体から自動生成する．

使い方:

    python scripts/generate_items_anno1800.py \\
        --install "/mnt/c/Program Files (x86)/Steam/steamapps/common/Anno 1800" \\
        --data-dir src/anno_save_analyzer/data

前提:

- 利用者がローカルに Anno 1800 のインストールを持ってる
- ``<install>/maindata/dataN.rda`` (N=0..33+) のうち最新のものに:
    - ``data/config/export/main/asset/assets.xml`` (Product 定義 + OasisId)
    - ``data/config/gui/texts_<language>.xml`` (OasisId → 多言語 UI テキスト)
  が入ってる (実測確認済 2026-04-22 時点で data33 が最新 full snapshot)

仕様:

Anno 117 (config.rda 1 本) と違って **Anno 1800 は dataN.rda が複数** に分かれて
おり，後の N ほど後発パッチで，毎回 assets.xml を full overwrite しとる
(実測: data0 = 91MB → data33 = 289MB と単調増加)．したがって最大 N の
RDA から各ファイルを取れば「最新の game state」になる．

抽出ロジック自体は 117 版と同一:

- ``<Asset><Template>Product</Template>`` の全件について
  ``Standard/GUID`` と ``Text/OasisId`` を拾う
- ``texts_english.xml`` / ``texts_japanese.xml`` から OasisId → text の map を引く
- ``items_anno1800.en.yaml`` / ``items_anno1800.ja.yaml`` を GUID 昇順で書き出す
- UI 表記 (texts_*.xml) が内部名 (``"Good Wood"``) より優先．UI テキスト無い場合は
  内部 name から prefix (``"Good "`` 等) を剥いてフォールバック
- 既存 YAML の category フィールドは保存される

出力:

- ``<data-dir>/items_anno1800.en.yaml`` および ``items_anno1800.ja.yaml`` を生成
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml
from lxml import etree

from anno_save_analyzer.parser.rda import RDAArchive

_ASSETS_XML = "data/config/export/main/asset/assets.xml"
_TEXTS_XML_TMPL = "data/config/gui/texts_{lang}.xml"
_PREFIXES_TO_STRIP = ("Good ", "Service ", "Workforce ")
_DATA_RDA_RE = re.compile(r"data(\d+)\.rda")

# locale code → texts_<lang>.xml の <lang> 部 (Anno 1800 命名規則．117 と同一)
_LOCALE_TO_LANG = {
    "en": "english",
    "ja": "japanese",
    "de": "german",
    "fr": "french",
    "zh": "chinese",  # 117 は "simplified_chinese" だが 1800 は "chinese"
    "ko": "korean",
    "it": "italian",
    "es": "spanish",
    "pl": "polish",
    "ru": "russian",
    "pt": "brazilian",
    "tw": "taiwanese",
}


def find_latest_rda_for(maindata: Path, member: str) -> Path:
    """``maindata/dataN.rda`` のうち ``member`` を含む最大 N の RDA を返す．

    Anno 1800 のパッチは後発 N ほど新しい full snapshot．最大 N に member が
    無ければ降順に走査して最初に見つかったやつを使う．
    """
    candidates: list[tuple[int, Path]] = []
    for rda in maindata.glob("data*.rda"):
        m = _DATA_RDA_RE.fullmatch(rda.name)
        if m:
            candidates.append((int(m.group(1)), rda))
    candidates.sort(reverse=True)
    for _, rda in candidates:
        with RDAArchive(rda) as ar:
            if any(e.filename == member for e in ar.entries):
                return rda
    raise FileNotFoundError(f"no dataN.rda contains {member!r} under {maindata}")


def _strip_internal_prefix(name: str) -> str:
    for prefix in _PREFIXES_TO_STRIP:
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


def _build_text_map(xml_bytes: bytes) -> dict[int, str]:
    """texts_<lang>.xml の ``<Text><GUID>..</GUID><Text>..</Text></Text>`` を map 化．

    Anno 117 は ``<LineId>`` だが Anno 1800 は ``<GUID>`` 派．構造はそれ以外同じ．
    """
    parser = etree.XMLParser(huge_tree=True, recover=True)
    root = etree.fromstring(xml_bytes, parser=parser)
    out: dict[int, str] = {}
    for el in root.iter("Text"):
        gid = el.find("GUID")
        tx = el.find("Text")
        if gid is None or tx is None or not gid.text:
            continue
        try:
            key = int(gid.text)
        except ValueError:
            continue
        # Anno の日本語テキストには U+200B (zero-width space) が入っとるので除去
        value = (tx.text or "").replace("\u200b", "")
        out[key] = value
    return out


def extract_products(config_data: bytes) -> list[dict[str, Any]]:
    """assets.xml から Product asset の GUID + internal name を抽出．

    Anno 1800 の Product は次の形:

        <Asset>
          <Template>Product</Template>
          <Values>
            <Standard><GUID>..</GUID><Name>..</Name>...</Standard>
            <Text>
              <LocaText><English><Text>Coins</Text></English></LocaText>
              <LineID>14965</LineID>
            </Text>
          </Values>
        </Asset>

    **重要**: Anno 1800 では Product の localized name は **Product GUID 自身**を
    key にして texts_<lang>.xml から引く (117 の OasisId / 1800 の LineID は
    誤参照がある)．実測で 280 Products 全件が GUID-direct で en/ja ともヒットする
    ため，LineID 系は完全に無視してよい．
    """
    parser = etree.XMLParser(huge_tree=True, recover=True)
    root = etree.fromstring(config_data, parser=parser)
    products: list[dict[str, Any]] = []
    for asset in root.iter("Asset"):
        tpl = asset.find("Template")
        if tpl is None or tpl.text != "Product":
            continue
        guid_el = asset.find("Values/Standard/GUID")
        name_el = asset.find("Values/Standard/Name")
        if guid_el is None or name_el is None or not guid_el.text or not name_el.text:
            continue
        try:
            guid = int(guid_el.text)
        except ValueError:
            continue
        products.append({"guid": guid, "internal_name": name_el.text})
    products.sort(key=lambda p: p["guid"])
    return products


def resolve_localized_name(
    product: dict[str, Any],
    text_map: dict[int, str],
) -> str:
    """Product の localized name を取得．

    ``texts_<lang>.xml`` は Product GUID 自身を key に持つ (例: ``<GUID>1010566</GUID>
    <Text>Oil</Text>``)．実測で 280 Products 全件 en/ja ともヒットするため GUID-direct
    参照のみで済む．欠損時は内部 name の prefix 剥きにフォールバック．
    """
    guid = product["guid"]
    if guid in text_map and text_map[guid]:
        return text_map[guid]
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
        f"# Anno 1800 — item dictionary ({locale}).",
        "# Auto-generated from maindata/dataN.rda (latest)/assets.xml + texts_<lang>.xml",
        "# by scripts/generate_items_anno1800.py. Re-run after game updates.",
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
        help="Anno 1800 install directory (contains maindata/)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="output directory (where items_anno1800.<locale>.yaml go)",
    )
    parser.add_argument(
        "--locales",
        nargs="+",
        default=["en", "ja"],
        help="locale codes to generate (default: en ja)",
    )
    args = parser.parse_args()

    maindata = args.install / "maindata"
    if not maindata.is_dir():
        raise FileNotFoundError(f"maindata/ not found at {maindata}")

    assets_rda = find_latest_rda_for(maindata, _ASSETS_XML)
    print(f"using {assets_rda.name} for assets.xml")
    with RDAArchive(assets_rda) as ar:
        assets_data = ar.read(_ASSETS_XML)

    text_maps: dict[str, dict[int, str]] = {}
    for loc in args.locales:
        lang = _LOCALE_TO_LANG.get(loc)
        if lang is None:
            print(f"  skipping unknown locale {loc!r} (not in _LOCALE_TO_LANG)")
            continue
        texts_path = _TEXTS_XML_TMPL.format(lang=lang)
        try:
            texts_rda = find_latest_rda_for(maindata, texts_path)
        except FileNotFoundError:
            print(f"  warning: {texts_path} not in any dataN.rda (locale {loc!r})")
            continue
        if texts_rda.name != assets_rda.name:
            print(f"  using {texts_rda.name} for {texts_path}")
        with RDAArchive(texts_rda) as ar:
            text_maps[loc] = _build_text_map(ar.read(texts_path))

    products = extract_products(assets_data)
    print(f"extracted {len(products)} Products")

    for loc, text_map in text_maps.items():
        out = args.data_dir / f"items_anno1800.{loc}.yaml"
        existing = load_existing_categories(out)
        write_items_yaml(products, text_map, out, loc, existing)
        print(f"  wrote {out}  ({len(text_map):,} text entries merged)")


if __name__ == "__main__":
    main()
