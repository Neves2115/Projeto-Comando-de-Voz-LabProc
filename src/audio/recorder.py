from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

from ..utils import ensure_parent, timestamp_slug

try:
    import sounddevice as sd
except Exception:  # pragma: no cover - fallback
    sd = None

@dataclass
class AudioRecorder:
    """Grava trechos curtos do microfone."""
    sample_rate: int = 16000
    channels: int = 1

    def record_to_wav(self, duration_s: float, output_dir: Path) -> Path:
        if sd is None:
            raise RuntimeError("sounddevice não está disponível neste ambiente.")
        ensure_parent(output_dir / "dummy")
        output_path = output_dir / f"audio_{timestamp_slug()}.wav"

        frames = sd.rec(
            int(duration_s * self.sample_rate),
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
        )
        sd.wait()

        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(frames.tobytes())

        return output_path
