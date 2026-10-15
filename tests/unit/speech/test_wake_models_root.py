"""The wake-model store must resolve to an ABSOLUTE, per-instance path.

Historical defect: ``_vosk_models_root`` fell back to a bare ``"data"`` — a path
relative to the process CWD. The desktop shortcut starts in the user's home
directory, so the store was read from ``<home>/data/wake_models/vosk`` instead
of the checkout's data dir. Live boot log:

    PermissionError: [WinError 5] Access is denied: 'data\\wake_models\\vosk\\en'

The unreadable/wrong folder no longer crashes the wake plan (it falls through),
but the store still pointed at the wrong place and silently degraded the wake
word. These tests pin the resolution.
"""
from __future__ import annotations

from jarvis.speech import wake_constants, wake_model_fetch


def _clear_seams(monkeypatch) -> None:
    for var in (
        "JARVIS__MEMORY__DATA_DIR",
        "JARVIS_DATA_DIR",
        "JARVIS_INSTANCE",
    ):
        monkeypatch.delenv(var, raising=False)


def test_vosk_models_root_is_absolute(monkeypatch) -> None:
    _clear_seams(monkeypatch)
    root = wake_constants._vosk_models_root()
    assert root.is_absolute()
    assert root.parts[-2:] == ("wake_models", "vosk")
    # The default instance stores under ``<repo>/data``.
    assert root.parent.parent.name == "data"


def test_vosk_models_root_honours_explicit_override(monkeypatch, tmp_path) -> None:
    _clear_seams(monkeypatch)
    monkeypatch.setenv("JARVIS__MEMORY__DATA_DIR", str(tmp_path))
    assert wake_constants._vosk_models_root() == tmp_path / "wake_models" / "vosk"


def test_vosk_models_root_is_not_cwd_relative(monkeypatch) -> None:
    """A regression to a bare "data" would make this CWD-dependent."""
    _clear_seams(monkeypatch)
    first = wake_constants._vosk_models_root()
    monkeypatch.chdir(first.parent)
    assert wake_constants._vosk_models_root() == first


def test_vosk_models_root_follows_the_instance(monkeypatch) -> None:
    _clear_seams(monkeypatch)
    monkeypatch.setenv("JARVIS_INSTANCE", "dev")
    assert wake_constants._vosk_models_root().parent.parent.name == "data-dev"


def test_fetch_models_root_matches_wake_constants(monkeypatch) -> None:
    """The fetch target and the read target must not diverge."""
    _clear_seams(monkeypatch)
    assert wake_model_fetch._models_root(None) == wake_constants._vosk_models_root()


def test_fetch_models_root_still_honours_an_explicit_dir(tmp_path) -> None:
    assert wake_model_fetch._models_root(str(tmp_path)) == (
        tmp_path / "wake_models" / "vosk"
    )


def test_local_models_root_shares_the_same_data_base(monkeypatch) -> None:
    """The speech-model dir must sit next to the wake-store base, not in the CWD."""
    from jarvis.speech import local_models

    _clear_seams(monkeypatch)
    base = wake_constants._vosk_models_root().parent.parent
    assert local_models.models_root(None) == base / "models"


def test_local_models_root_still_honours_an_explicit_dir(tmp_path) -> None:
    from jarvis.speech import local_models

    assert local_models.models_root(str(tmp_path)) == tmp_path / "models"
