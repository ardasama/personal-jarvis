"""Optional Turkish TTS packaging cannot turn the standard install into Torch."""

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[4]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
LOCK = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))


def _project_lock_package() -> dict:
    return next(pkg for pkg in LOCK["package"] if pkg["name"] == "personal-jarvis")


def test_turkish_speech_requires_an_explicit_opt_in() -> None:
    optional = PYPROJECT["project"]["optional-dependencies"]
    assert optional["turkish-voice"] == ["pocket-tts-turkish==0.1.0"]
    for group in ("full", "desktop", "local-voice", "dev"):
        assert group in optional
        assert all(
            "pocket-tts" not in requirement and "turkish-voice" not in requirement
            for requirement in optional[group]
        ), group


def test_lock_is_pinned_and_extra_isolated() -> None:
    packages = {pkg["name"]: pkg for pkg in LOCK["package"]}
    assert packages["pocket-tts-turkish"]["version"] == "0.1.0"
    project = _project_lock_package()
    assert {"name": "pocket-tts-turkish"} in project["optional-dependencies"]["turkish-voice"]
    assert all("pocket" not in str(item) for item in project["dependencies"])
    for group in ("full", "desktop", "local-voice", "dev"):
        assert all("pocket-tts" not in str(item) for item in project["optional-dependencies"].get(group, []))


def test_all_supported_base_dependencies_remain_declared() -> None:
    packages = {pkg["name"] for pkg in LOCK["package"]}
    assert "personal-jarvis" in packages
    assert "faster-whisper" in packages
    assert "pocket-tts-turkish" in packages