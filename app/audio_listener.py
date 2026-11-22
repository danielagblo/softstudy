"""Capture system (loopback) or microphone audio for live transcription."""
from __future__ import annotations

import threading
from collections import deque
from typing import Callable

import numpy as np
import sounddevice as sc

import config


class AudioListener:
    """
    Continuously records audio and emits fixed-length float32 mono chunks.

    Prefer WASAPI loopback (speaker output) so Zoom/Meet audio is captured.
    Falls back to the default microphone if loopback is unavailable.
    """

    def __init__(
        self,
        on_chunk: Callable[[np.ndarray], None],
        sample_rate: int = config.SAMPLE_RATE,
        chunk_seconds: float = config.CHUNK_SECONDS,
        prefer_loopback: bool = True,
    ) -> None:
        self.on_chunk = on_chunk
        self.sample_rate = sample_rate
        self.chunk_seconds = chunk_seconds
        self.prefer_loopback = prefer_loopback
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.device_name = "unknown"
        self.mode = "mic"

    def list_devices(self) -> list[str]:
        lines: list[str] = []
        for mic in sc.all_microphones(include_loopback=True):
            tag = " [loopback]" if getattr(mic, "isloopback", False) else ""
            lines.append(f"{mic.name}{tag}")
        return lines

    def _pick_mic(self):
        if self.prefer_loopback:
            loopbacks = [m for m in sc.all_microphones(include_loopback=True) if getattr(m, "isloopback", False)]
            if loopbacks:
                # Prefer default speaker loopback when possible
                try:
                    default_speaker = sc.default_speaker()
                    for m in loopbacks:
                        if default_speaker and default_speaker.name in m.name:
                            self.mode = "loopback"
                            return m
                except Exception:  # noqa: BLE001
                    pass
                self.mode = "loopback"
                return loopbacks[0]
        self.mode = "mic"
        return sc.default_microphone()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="AudioListener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def _run(self) -> None:
        mic = self._pick_mic()
        self.device_name = mic.name
        print(f"[audio] using {self.mode}: {self.device_name}")

        frames_needed = int(self.sample_rate * self.chunk_seconds)
        # Record in small blocks, assemble into chunk_seconds buffers
        block = int(self.sample_rate * 0.25)
        buffer: deque[np.ndarray] = deque()
        buffered = 0

        try:
            with mic.recorder(samplerate=self.sample_rate, channels=1, blocksize=block) as recorder:
                while not self._stop.is_set():
                    data = recorder.record(numframes=block)
                    mono = np.asarray(data, dtype=np.float32).reshape(-1)
                    buffer.append(mono)
                    buffered += mono.size
                    while buffered >= frames_needed:
                        # Concatenate enough frames
                        parts: list[np.ndarray] = []
                        take = 0
                        while take < frames_needed and buffer:
                            part = buffer.popleft()
                            if take + part.size <= frames_needed:
                                parts.append(part)
                                take += part.size
                                buffered -= part.size
                            else:
                                need = frames_needed - take
                                parts.append(part[:need])
                                buffer.appendleft(part[need:])
                                buffered -= need
                                take += need
                        chunk = np.concatenate(parts) if parts else np.zeros(frames_needed, dtype=np.float32)
                        # Skip near-silence
                        if float(np.sqrt(np.mean(chunk**2))) < 0.003:
                            continue
                        try:
                            self.on_chunk(chunk)
                        except Exception as exc:  # noqa: BLE001
                            print(f"[audio] chunk handler error: {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"[audio] capture failed: {exc}")
            print("[audio] Tip: on Windows, enable Stereo Mix or use a virtual cable if loopback fails.")
