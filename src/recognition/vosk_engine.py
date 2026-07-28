from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from vosk import Model, KaldiRecognizer
except Exception:  # pragma: no cover - fallback
    Model = None
    KaldiRecognizer = None

@dataclass
class VoskSpeechRecognizer:
    """Reconhecimento offline usando Vosk."""
    model_path: Path
    sample_rate: int = 16000

    def __post_init__(self) -> None:
        if Model is None or KaldiRecognizer is None:
            self._model = None
            return
        if not self.model_path.exists():
            raise FileNotFoundError(f"Modelo Vosk não encontrado em: {self.model_path}")
        self._model = Model(str(self.model_path))

    def is_ready(self) -> bool:
        return self._model is not None

    def transcribe_wav_frames(self, frames: Iterable[bytes]) -> str:
        if self._model is None:
            raise RuntimeError("Vosk não está disponível ou o modelo não foi carregado.")
        rec = KaldiRecognizer(self._model, self.sample_rate)
        for chunk in frames:
            rec.AcceptWaveform(chunk)
        result = json.loads(rec.FinalResult())
        return result.get("text", "").strip()
