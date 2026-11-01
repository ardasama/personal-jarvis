"""Check provider Turkish texts without needing a browser or an API connection."""

import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
LOCALE = ROOT / "jarvis" / "ui" / "web" / "frontend" / "src" / "i18n" / "locales"
TOKENS = re.compile(r"\{[^{}]+\}|%(?:\d+\$)?[sd]|<\/?[A-Za-z][^>]*>")


def _flatten(value: dict, prefix: str = "") -> dict:
    result = {}
    for name, item in value.items():
        key = f"{prefix}.{name}" if prefix else name
        if isinstance(item, dict):
            result.update(_flatten(item, key))
        else:
            result[key] = item
    return result


def _read(locale: str, group: str = "providers") -> dict:
    path = LOCALE / group / f"{locale}.json"
    return _flatten(json.loads(path.read_text(encoding="utf-8")))


def test_all_turkish_locale_names_and_placeholders_match_english() -> None:
    folders = [LOCALE, *(p for p in LOCALE.iterdir() if p.is_dir() and (p / "tr.json").exists())]
    assert len(folders) == 9
    for folder in folders:
        english = _flatten(json.loads((folder / "en.json").read_text(encoding="utf-8")))
        turkish = _flatten(json.loads((folder / "tr.json").read_text(encoding="utf-8")))
        allowed = {
            "languages_view.options.tr.label",
            "languages_view.reply_options.tr",
        } if folder == LOCALE else set()
        assert not (english.keys() - turkish.keys()), str(folder)
        assert turkish.keys() - english.keys() == allowed, str(folder)
        for key, value in english.items():
            translation = turkish[key]
            assert type(translation) is type(value), key
            if isinstance(value, str):
                assert sorted(TOKENS.findall(value)) == sorted(TOKENS.findall(translation)), key


@pytest.mark.parametrize("key", [
    "providers_page.subscription_desc",
    "providers_page.subscription_hint",
    "providers_page.login_waiting_browser",
    "providers_page.key_desc",
    "providers_page.key_desc_short",
    "mission_billing.title",
    "mission_billing.confirm_intro",
    "mission_billing.confirm_billing",
    "mission_billing.confirm_caps",
    "mission_billing.confirm_action",
])
def test_connection_and_billing_guidance_is_localized(key: str) -> None:
    english = _read("en")
    turkish = _read("tr")
    assert key in english
    assert key in turkish
    assert english[key] != turkish[key], key
    assert turkish[key].strip(), key