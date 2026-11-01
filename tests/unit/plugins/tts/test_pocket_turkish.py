"""Offline, low-RAM contract checks for the configured Turkish Pocket voice."""
from __future__ import annotations

import asyncio

import numpy as np
import pytest

from jarvis.plugins.tts.pocket_turkish import PocketTurkishTTS


class FakeModel:
    sample_rate = 24000

    def __init__(self, output=None):
        self.output = [np.array([0.5, -0.5], dtype=np.float32)] if output is None else output
        self.calls: list[tuple[str, str, str]] = []

    def stream(self, text: str, *, voice: str, emotion: str):
        self.calls.append((text, voice, emotion))
        yield from self.output


def bind_fake_model(engine: PocketTurkishTTS, model: FakeModel) -> None:
    async def load():
        return model
    engine._load = load


async def collect(engine: PocketTurkishTTS, text: str, **kw):
    return [chunk async for chunk in engine.synthesize(text, **kw)]


def test_rejects_foreign_language_before_loading_weights() -> None:
    engine = PocketTurkishTTS()
    async def unexpected_load():
        raise AssertionError("Heavy model should not load for non-Turkish requests")
    engine._load = unexpected_load
    with pytest.raises(ValueError, match="only supports Turkish"):
        asyncio.run(collect(engine, "Hello", language_code="en-US"))


def test_empty_text_does_not_load_weights() -> None:
    engine = PocketTurkishTTS()
    async def unexpected_load():
        raise AssertionError("An empty utterance must not load a model")
    engine._load = unexpected_load
    assert asyncio.run(collect(engine, "   ", language_code="tr-TR")) == []


def test_valid_turkish_stream_yields_signed_pcm_and_correct_voice() -> None:
    engine = PocketTurkishTTS(voice="male_2", emotion="mutlu")
    model = FakeModel()
    bind_fake_model(engine, model)
    chunks = asyncio.run(collect(engine, "Merhaba dünya", language_code="tr-TR"))  # i18n-allow: Turkish speech test input
    assert len(chunks) == 1
    assert chunks[0].sample_rate == 24000
    assert chunks[0].channels == 1
    assert np.frombuffer(chunks[0].pcm, dtype=np.int16).tolist() == [16383, -16383]
    assert model.calls == [("Merhaba dünya", "male_2", "mutlu")]  # i18n-allow: Turkish speech expected values
    assert engine.last_voice_provider == "pocket-turkish"


def test_unknown_voice_falls_back_to_configured_voice() -> None:
    engine = PocketTurkishTTS(voice="female_1")
    model = FakeModel()
    bind_fake_model(engine, model)
    asyncio.run(collect(engine, "Merhaba", voice="voice-from-cloud", language_code="tr"))
    assert model.calls[0][1] == "female_1"


@pytest.mark.parametrize("bad_output", [np.array([np.nan], dtype=np.float32), np.array([np.inf], dtype=np.float32)])
def test_nonfinite_audio_is_rejected(bad_output) -> None:
    engine = PocketTurkishTTS()
    bind_fake_model(engine, FakeModel([bad_output]))
    with pytest.raises(RuntimeError, match="not finite"):
        asyncio.run(collect(engine, "Deneme", language_code="tr"))


def test_empty_stream_reports_failure_instead_of_silence() -> None:
    engine = PocketTurkishTTS()
    bind_fake_model(engine, FakeModel([]))
    with pytest.raises(RuntimeError, match="no audio"):
        asyncio.run(collect(engine, "Deneme", language_code="tr"))


def test_invalid_sample_rate_is_rejected() -> None:
    engine = PocketTurkishTTS()
    model = FakeModel()
    model.sample_rate = 0
    bind_fake_model(engine, model)
    with pytest.raises(RuntimeError, match="sample rate"):
        asyncio.run(collect(engine, "Deneme", language_code="tr"))


def test_pcm_clipped_without_wraparound() -> None:
    engine = PocketTurkishTTS()
    bind_fake_model(engine, FakeModel([np.array([9.0, -9.0], dtype=np.float32)]))
    chunks = asyncio.run(collect(engine, "Merhaba", language_code="tr"))
    assert np.frombuffer(chunks[0].pcm, dtype=np.int16).tolist() == [32767, -32767]

def test_cached_snapshot_is_strictly_offline(monkeypatch, tmp_path) -> None:
    import huggingface_hub
    from jarvis.plugins.tts import pocket_turkish

    for name in ("config.yaml", "model.safetensors", "tokenizer.model"):
        (tmp_path / name).write_bytes(b"test")
    (tmp_path / "voices").mkdir()
    (tmp_path / "voices" / "male_1.wav").write_bytes(b"test")
    observed = {}
    def fake_download(**kw):
        observed.update(kw)
        return str(tmp_path)
    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake_download)
    assert pocket_turkish._cached_model_folder() == str(tmp_path)
    assert observed["local_files_only"] is True
    assert observed["repo_id"] == "wite-tech/pocket-tts-turkish"


def test_missing_cache_refuses_network_access(monkeypatch) -> None:
    import huggingface_hub
    from jarvis.plugins.tts import pocket_turkish

    def missing(**kw):
        assert kw["local_files_only"] is True
        raise FileNotFoundError("simulated")
    monkeypatch.setattr(huggingface_hub, "snapshot_download", missing)
    with pytest.raises(RuntimeError, match="not cached"):
        pocket_turkish._cached_model_folder()


def test_incomplete_local_assets_are_rejected(monkeypatch, tmp_path) -> None:
    import huggingface_hub
    from jarvis.plugins.tts import pocket_turkish
    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda **kw: str(tmp_path))
    with pytest.raises(RuntimeError, match="incomplete"):
        pocket_turkish._cached_model_folder()


def test_stop_discards_buffered_audio() -> None:
    import time

    class ContinuousModel(FakeModel):
        def stream(self, text, *, voice, emotion):
            self.calls.append((text, voice, emotion))
            for _ in range(300):
                time.sleep(0.002)
                yield np.array([0.25], dtype=np.float32)

    async def verify():
        engine = PocketTurkishTTS()
        bind_fake_model(engine, ContinuousModel())
        stream = engine.synthesize("Dur", language_code="tr")
        first = await asyncio.wait_for(stream.__anext__(), timeout=1.0)
        assert first.pcm
        await engine.aclose()
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(stream.__anext__(), timeout=1.0)

    asyncio.run(verify())


def test_stop_before_first_audio_unblocks_consumer() -> None:
    import threading
    import time

    started = threading.Event()
    class SlowModel(FakeModel):
        def stream(self, text, *, voice, emotion):
            started.set()
            time.sleep(0.20)
            yield np.array([0.25], dtype=np.float32)

    async def verify():
        engine = PocketTurkishTTS()
        bind_fake_model(engine, SlowModel())
        stream = engine.synthesize("Dur", language_code="tr")
        pending = asyncio.create_task(stream.__anext__())
        assert await asyncio.to_thread(started.wait, 0.5)
        await engine.aclose()
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(pending, timeout=1.0)
        await stream.aclose()

    asyncio.run(verify())
