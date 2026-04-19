"""UI 文字列 i18n．locale 別 YAML をキー → 翻訳に展開する．

シンプルな dict-based l10n．Pluralization 等は v0.3.x 以降に検討．
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import yaml

_LOCALE_PACKAGE = "anno_save_analyzer.tui.locales"
_DEFAULT_LOCALE = "en"


class Localizer:
    """``locale`` を切替可能な UI 文字列ルックアップ．"""

    def __init__(self, code: str, strings: dict[str, str]) -> None:
        self.code = code
        self._strings = dict(strings)

    @classmethod
    def load(
        cls,
        code: str = _DEFAULT_LOCALE,
        *,
        data_dir: Path | None = None,
    ) -> Localizer:
        strings = _load_yaml(code, data_dir)
        return cls(code=code, strings=strings)

    def t(self, key: str, **kwargs: object) -> str:
        """指定キーの翻訳を返す．未定義キーは ``key`` 自体を返す．

        ``{name}`` 形式のプレースホルダがあれば ``kwargs`` で format．
        """
        template = self._strings.get(key, key)
        if kwargs:
            return template.format(**kwargs)
        return template

    def with_locale(self, code: str, *, data_dir: Path | None = None) -> Localizer:
        """別 locale で新しい Localizer を返す（live switching 用）．"""
        return type(self).load(code, data_dir=data_dir)


def _load_yaml(code: str, data_dir: Path | None) -> dict[str, str]:
    filename = f"{code}.yaml"
    raw: str | None = None
    if data_dir is not None:
        path = data_dir / filename
        if path.is_file():
            raw = path.read_text(encoding="utf-8")
    else:
        try:
            raw = (resources.files(_LOCALE_PACKAGE) / filename).read_text(encoding="utf-8")
        except (FileNotFoundError, ModuleNotFoundError):
            raw = None
    if raw is None:
        # Fallback: empty dict．Localizer.t がキー名そのまま返すから致命的じゃない
        return {}
    parsed = yaml.safe_load(raw) or {}
    return {str(k): str(v) for k, v in parsed.items()}
