"""locale-split YAML からなる Item 辞書ローダ．

レイアウト::

    data/items_<title>.<locale>.yaml

例:

- ``items_anno117.en.yaml`` — canonical．``name`` + ``category`` を持つ
- ``items_anno117.ja.yaml`` — name only

Loader は ``en`` ファイルをベースに他 locale を name のみマージする．
"""

from __future__ import annotations

from collections.abc import Iterable
from importlib import resources
from pathlib import Path
from typing import cast

import yaml

from .models import GameTitle, Item, Locale

_DATA_PACKAGE = "anno_save_analyzer.data"


class ItemDictionary:
    """GUID → Item の lookup テーブル．未登録 GUID は ``Good_<guid>`` で生成．"""

    def __init__(self, items: dict[int, Item]) -> None:
        self._items: dict[int, Item] = dict(items)

    def __getitem__(self, guid: int) -> Item:
        if guid not in self._items:
            self._items[guid] = Item(guid=guid, names={})
        return self._items[guid]

    def __contains__(self, guid: int) -> bool:
        return guid in self._items

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterable[Item]:
        return iter(self._items.values())

    @classmethod
    def load(
        cls,
        title: GameTitle | str,
        locales: Iterable[Locale] = ("en",),
        *,
        data_dir: Path | None = None,
    ) -> ItemDictionary:
        """指定 title / locale 群を読み込んで辞書を構築する．

        ``data_dir`` が指定されればそこから，未指定なら同梱 data パッケージから読む．
        ``en`` は category 等のメタも持つため必ず先に読む．
        """
        title_value = title.value if isinstance(title, GameTitle) else str(title)
        locale_list = list(locales)
        if "en" not in locale_list:
            locale_list = ["en", *locale_list]
        else:
            # en を先頭に
            locale_list.remove("en")
            locale_list = ["en", *locale_list]

        accumulated: dict[int, dict] = {}
        for locale in locale_list:
            payload = _load_yaml(title_value, locale, data_dir)
            for guid, entry in payload.items():
                bucket = accumulated.setdefault(guid, {"names": {}})
                if "name" in entry:
                    bucket["names"][locale] = entry["name"]
                if locale == "en" and "category" in entry:
                    bucket["category"] = entry["category"]

        items = {
            guid: Item(
                guid=guid,
                names=cast(dict[str, str], bucket["names"]),
                category=bucket.get("category"),
            )
            for guid, bucket in accumulated.items()
        }
        return cls(items)


def _load_yaml(title: str, locale: Locale, data_dir: Path | None) -> dict[int, dict]:
    """``items_<title>.<locale>.yaml`` を読む．存在しなければ空辞書を返す．"""
    filename = f"items_{title}.{locale}.yaml"
    raw: str | None = None
    if data_dir is not None:
        path = data_dir / filename
        if path.is_file():
            raw = path.read_text(encoding="utf-8")
    else:
        try:
            raw = (resources.files(_DATA_PACKAGE) / filename).read_text(encoding="utf-8")
        except (FileNotFoundError, ModuleNotFoundError):
            raw = None

    if raw is None:
        return {}
    parsed = yaml.safe_load(raw) or {}
    # GUID キーを int に揃える（YAML の数値キーは int だが文字列で書かれる場合の互換）
    return {int(k): (v or {}) for k, v in parsed.items()}
