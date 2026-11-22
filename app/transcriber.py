"""Real-time speech-to-text using faster-whisper."""
from __future__ import annotations

import queue
from queue import Queue
from typing import Callable

import numpy as np

import config


class Transcriber:
    def __init__(
        self,
        on_text: Callable[[str], None],
        model_size: str = config.WHISPER_MODEL,
        device: str = config.WHISPER_DEVICE,
        compute_type: str = config.WHISPER_COMPUTE,
    ) -> None:
        self.on_text = on_text
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._queue: Queue[np.ndarray | None] = Queue(maxsize=8)
        self._thread: threading.Thread | None = None
        self._model = None
        self.ready = False

    def load(self) -> None:
        from faster_whisper import WhisperModel

        print(f"[whisper] loading model '{self.model_size}' on {self.device}...")
        self._model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
        )
        self.ready = True
        print("[whisper] ready")

    def start(self) -> None:
        if not self.ready:
            self.load()
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._worker, name="Transcriber", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def submit(self, audio: np.ndarray) -> None:
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except Exception:  # noqa: BLE001
                pass
        try:
            self._queue.put_nowait(audio.astype(np.float32, copy=False))
        except Exception:  # noqa: BLE001
            pass

    def _worker(self) -> None:
        assert self._model is not None
        while True:
            item = self._queue.get()
            if item is None:
                break
            try:
                segments, _info = self._model.transcribe(
                    item,
                    language="en",
                    beam_size=1,
                    vad_filter=True,
                    without_timestamps=True,
                )
                text = " ".join(seg.text.strip() for seg in segments).strip()
                if text:
                    self.on_text(text)
            except Exception as exc:  # noqa: BLE001
                print(f"[whisper] error: {exc}")
