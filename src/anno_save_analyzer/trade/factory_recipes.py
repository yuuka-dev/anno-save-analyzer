"""Anno 1800 factory template GUID → 生産レシピ loader．

``data/factory_recipes_anno1800.en.yaml`` を canonical に各 factory template
の ``tpmin`` (tons/min/factory at 100% productivity) と ``outputs`` / ``inputs``
を保持する．

save の ``objects > <1>`` 直下 ``guid`` attrib がこの recipe の ``guid`` と
一致するため，``FactoryInstance.building_guid`` → ``FactoryRecipe`` の直接
lookup ができる．

Calculator (MIT, NiHoel) の ``factories.js`` の生産量式を流用::

    生産量 (/min) = existingBuildings × productivity × tpmin

本 module は recipe の保管のみ．生産量算出は ``trade.balance`` 側の責務．
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

_DATA_PACKAGE = "anno_save_analyzer.data"
_EN_FILE = "factory_recipes_anno1800.en.yaml"


class RecipeOutput(BaseModel):
    product_guid: int
    amount: float | None = None
    """1 cycle あたりの出力個数 (通常 1)．``tpmin × amount`` が /min レート．"""
    storage_amount: int | None = None

    model_config = {"frozen": True}


class RecipeInput(BaseModel):
    product_guid: int
    amount: float | None = None

    model_config = {"frozen": True}


class FactoryRecipe(BaseModel):
    """1 factory template 分のレシピ定義．"""

    guid: int
    name: str
    tpmin: float | None = None
    """tons per minute per factory at 100% productivity．``None`` は未定義．"""
    region: int | None = None
    dlcs: tuple[str, ...] = Field(default_factory=tuple)
    outputs: tuple[RecipeOutput, ...] = Field(default_factory=tuple)
    inputs: tuple[RecipeInput, ...] = Field(default_factory=tuple)

    model_config = {"frozen": True}

    def produced_per_minute(self, productivity: float) -> dict[int, float]:
        """``productivity`` (0.0–2.0+) で 1 factory の /min 生産量を product 別に返す．

        ``tpmin`` 未定義なら空 dict．``output.amount`` が ``None`` の稀な
        ケースは 1.0 とみなす．
        """
        if self.tpmin is None:
            return {}
        out: dict[int, float] = {}
        for o in self.outputs:
            amt = o.amount if o.amount is not None else 1.0
            out[o.product_guid] = out.get(o.product_guid, 0.0) + productivity * self.tpmin * amt
        return out

    def consumed_per_minute(self, productivity: float) -> dict[int, float]:
        """``productivity`` で 1 factory の /min **入力** 消費量を product 別に返す．

        中間物資 (豚 → 缶詰肉 等) の実消費量を計算する．``produced_per_minute``
        の対称形で input 側を集計．``tpmin`` 未定義なら空．``input.amount`` が
        ``None`` の場合は 1.0 とみなす (output 側と揃える)．
        """
        if self.tpmin is None:
            return {}
        out: dict[int, float] = {}
        for i in self.inputs:
            amt = i.amount if i.amount is not None else 1.0
            out[i.product_guid] = out.get(i.product_guid, 0.0) + productivity * self.tpmin * amt
        return out


class FactoryRecipeTable(BaseModel):
    """factory GUID → FactoryRecipe のテーブル．"""

    recipes: dict[int, FactoryRecipe] = Field(default_factory=dict)

    model_config = {"frozen": True}

    def get(self, guid: int) -> FactoryRecipe | None:
        return self.recipes.get(guid)

    def __contains__(self, guid: int) -> bool:
        return guid in self.recipes

    def __len__(self) -> int:
        return len(self.recipes)

    @classmethod
    def load(
        cls, *, data_dir: Path | None = None, locales: tuple[str, ...] = ("en",)
    ) -> FactoryRecipeTable:
        en_payload = _read_yaml(_EN_FILE, data_dir)
        locale_names: dict[int, str] = {}
        for loc in locales:
            if loc == "en":
                continue
            try:
                payload = _read_yaml(f"factory_recipes_anno1800.{loc}.yaml", data_dir)
            except FileNotFoundError:
                continue
            for entry in payload.get("factories") or []:
                if "guid" in entry and entry.get("name"):
                    locale_names[int(entry["guid"])] = str(entry["name"])

        recipes: dict[int, FactoryRecipe] = {}
        for raw in en_payload.get("factories") or []:
            guid = int(raw["guid"])
            name = locale_names.get(guid) or str(raw.get("name") or "")
            recipes[guid] = FactoryRecipe(
                guid=guid,
                name=name,
                tpmin=raw.get("tpmin"),
                region=raw.get("region"),
                dlcs=tuple(raw.get("dlcs") or ()),
                outputs=tuple(_output_from(o) for o in raw.get("outputs") or ()),
                inputs=tuple(_input_from(i) for i in raw.get("inputs") or ()),
            )
        return cls(recipes=recipes)


def _read_yaml(filename: str, data_dir: Path | None) -> dict[str, Any]:
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
    if not isinstance(payload, dict):
        raise ValueError(f"YAML root must be a mapping in {filename}, got {type(payload).__name__}")
    return payload


def _output_from(data: dict[str, Any]) -> RecipeOutput:
    return RecipeOutput(
        product_guid=int(data["product_guid"]),
        amount=data.get("amount"),
        storage_amount=data.get("storage_amount"),
    )


def _input_from(data: dict[str, Any]) -> RecipeInput:
    return RecipeInput(
        product_guid=int(data["product_guid"]),
        amount=data.get("amount"),
    )
