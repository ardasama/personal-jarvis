"""Offline expressive Turkish speech using Pocket TTS Turkish (CC-BY-4.0).

No API key, network synthesis or GPU required once model weights are cached.
Load lazily so opening JARVIS never blocks on model initialization.
"""
from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

import numpy as np

from jarvis.core.protocols import AudioChunk

_CACHED_REPO = "wite-tech/pocket-tts-turkish"


def _cached_model_folder() -> str:
    """Locate already cached model assets without using the network."""
    from pathlib import Path
    from huggingface_hub import snapshot_download

    try:
        folder = Path(snapshot_download(
            repo_id=_CACHED_REPO,
            local_files_only=True,
            allow_patterns=["config.yaml", "model.safetensors", "tokenizer.model", "voices/*.wav"],
        ))
    except (FileNotFoundError, OSError) as exc:
        raise RuntimeError(
            "Turkish voice model is not cached; authorized installation is required"
        ) from exc
    required = ("config.yaml", "model.safetensors", "tokenizer.model")
    if any(not (folder / name).is_file() for name in required) or not any(
        (folder / "voices").glob("*.wav")
    ):
        raise RuntimeError("Turkish voice model cache is incomplete; no download attempted")
    return str(folder)


_VOICES = frozenset({"male_1", "male_2", "male_3", "female_1", "female_2", "female_3"})


class PocketTurkishTTS:
    name = "pocket-turkish"
    supports_streaming = True
    runs_on_device = True
    last_voice: str | None = None
    last_voice_provider: str | None = None

    def __init__(self, *, voice: str = "male_1", emotion: str = "sakin") -> None:
        self._voice = voice if voice in _VOICES else "male_1"
        self._emotion = emotion if emotion in {"sakin", "mutlu", "şaşkın", "üzgün", "kızgın"} else "sakin"  # i18n-allow: explicit Turkish emotion voice labels
        self._model: Any | None = None
        self._load_lock = asyncio.Lock()
        self._synthesis_lock = asyncio.Lock()
        self._active_stop: threading.Event | None = None

    async def _load(self) -> Any:
        if self._model is not None:
            return self._model
        async with self._load_lock:
            if self._model is None:
                def create() -> Any:
                    local_model = _cached_model_folder()
                    import torch
                    from pocket_tts_turkish import TurkishTTS
                    torch.set_num_threads(2)
                    return TurkishTTS.from_pretrained(local_model, device="cpu")
                self._model = await asyncio.to_thread(create)
        return self._model

    async def _ensure_client(self) -> None:
        # Deliberately lazy. A voice is loaded only when a user asks to speak.
        return None

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        language_code: str | None = None,
    ) -> AsyncIterator[AudioChunk]:
        spoken = (text or "").strip()
        if not spoken:
            return
        if language_code and not language_code.lower().startswith("tr"):
            # Reject unsupported languages before loading heavy local weights.
            raise ValueError("pocket-turkish only supports Turkish text")
        model = await self._load()
        selected = voice if voice in _VOICES else self._voice
        end = object()
        chunks: queue.Queue[bytes | object] = queue.Queue(maxsize=8)
        stop = threading.Event()
        failure: list[Exception] = []
        rate = int(model.sample_rate)
        if rate <= 0:
            raise RuntimeError("Turkish speech engine returned an invalid sample rate")

        def produce() -> None:
            try:
                for part in model.stream(spoken, voice=selected, emotion=self._emotion):
                    if stop.is_set():
                        break
                    arr = np.asarray(part, dtype=np.float32)
                    if not arr.size:
                        continue
                    if not np.isfinite(arr).all():
                        raise RuntimeError("Turkish speech output is not finite")
                    payload = (np.clip(arr, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
                    while not stop.is_set():
                        try:
                            chunks.put(payload, timeout=0.05)
                            break
                        except queue.Full:  # Expected bounded backpressure; retry until STOP.
                            continue
            except Exception as exc:  # Save worker failure; consumer re-raises after drain.
                failure.append(exc)
            finally:
                while not stop.is_set():
                    try:
                        chunks.put(end, timeout=0.05)
                        break
                    except queue.Full:  # Expected bounded backpressure; retry until STOP.
                        continue

        self.last_voice = selected
        self.last_voice_provider = self.name
        async with self._synthesis_lock:
            self._active_stop = stop
            worker = asyncio.create_task(asyncio.to_thread(produce), name="pocket-tr-speech")
            emitted = False
            try:
                while not stop.is_set():
                    try:
                        # Timeout prevents an orphaned queue.get thread on STOP.
                        item = await asyncio.to_thread(chunks.get, True, 0.05)
                    except queue.Empty:  # Expected short polling timeout; inspect worker state.
                        if worker.done() and chunks.empty():
                            break
                        continue
                    if item is end:
                        break
                    if stop.is_set():
                        break
                    assert isinstance(item, bytes)
                    emitted = True
                    yield AudioChunk(pcm=item, sample_rate=rate, timestamp_ns=0, channels=1)
                if stop.is_set():
                    return
                await worker
                if failure:
                    raise failure[0]
                if not emitted:
                    raise RuntimeError("Turkish speech produced no audio")
            finally:
                stop.set()
                self._active_stop = None
                if not worker.done():
                    with suppress(TimeoutError):
                        await asyncio.wait_for(asyncio.shield(worker), timeout=1.0)

    async def aclose(self) -> None:
        # STOP must interrupt a currently active stream, not just unload weights.
        if self._active_stop is not None:
            self._active_stop.set()
        self._model = None
