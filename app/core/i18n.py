# app/core/i18n.py
"""Minimal internationalization. JSON-backed, restart-to-apply.

 ponytail: no gettext/Babel — one dict + one function. New language = drop a
 JSON file in app/assets/locales/ and add its code to AVAILABLE_LANGUAGES.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.utils.logger_utils import logger

_LOCALES_DIR = Path(__file__).resolve().parent.parent / "assets" / "locales"

#: Code -> human label (shown in the language combo).
AVAILABLE_LANGUAGES: dict[str, str] = {
    "en": "English",
    "zh": "中文",
}

DEFAULT_LANGUAGE = "zh"

_current_language: str = DEFAULT_LANGUAGE
_translations: dict[str, str] = {}


def _load_translations(lang: str) -> dict[str, str]:
    path = _LOCALES_DIR / f"{lang}.json"
    if not path.is_file():
        logger.warning(f"Locale file not found: {path}. Falling back to '{DEFAULT_LANGUAGE}'.")
        path = _LOCALES_DIR / f"{DEFAULT_LANGUAGE}.json"
        if not path.is_file():
            return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.error(f"Locale file {path} is not a JSON object.")
            return {}
        return data
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Failed to load locale {path}: {e}")
        return {}


def set_language(lang: str) -> None:
    """Switch the active language. Applies to all subsequent tr() calls."""
    global _current_language, _translations
    if lang not in AVAILABLE_LANGUAGES:
        logger.warning(f"Unknown language '{lang}'. Falling back to '{DEFAULT_LANGUAGE}'.")
        lang = DEFAULT_LANGUAGE
    _current_language = lang
    _translations = _load_translations(lang)
    logger.info(f"Active language set to '{lang}' ({len(_translations)} keys).")


def get_current_language() -> str:
    return _current_language


def tr(key: str, **fmt: Any) -> str:
    """Look up *key* in the active locale, format with **fmt, fall back to en then key."""
    value = _translations.get(key)
    if value is None:
        # Fall back to English, then to the key itself.
        en = _load_translations("en")
        value = en.get(key, key)
    try:
        return value.format(**fmt) if fmt else value
    except (KeyError, IndexError):
        return value


# Initialize immediately so importing modules see the default language.
set_language(DEFAULT_LANGUAGE)


if __name__ == "__main__":
    # Self-check (ponytail: one runnable check, no framework).
    set_language("en")
    assert tr("common.cancel") == "Cancel", tr("common.cancel")
    set_language("zh")
    assert tr("common.cancel") == "取消", tr("common.cancel")

    # Key parity: en and zh must expose identical key sets.
    en_keys = set(_load_translations("en").keys())
    zh_keys = set(_load_translations("zh").keys())
    missing_in_zh = en_keys - zh_keys
    missing_in_en = zh_keys - en_keys
    assert not missing_in_zh, f"Keys missing in zh.json: {sorted(missing_in_zh)}"
    assert not missing_in_en, f"Keys missing in en.json: {sorted(missing_in_en)}"

    # Format interpolation.
    set_language("en")
    assert tr("vm.moved", name="Foo") == "Moved 'Foo' successfully.", tr("vm.moved", name="Foo")
    set_language("zh")
    assert tr("vm.moved", name="Foo") == "已成功移动“Foo”。", tr("vm.moved", name="Foo")

    # Unknown language falls back.
    set_language("fr")
    assert get_current_language() == "zh"  # fell back to default

    # Unknown key returns the key.
    set_language("en")
    assert tr("does.not.exist") == "does.not.exist"

    print("i18n self-check OK")