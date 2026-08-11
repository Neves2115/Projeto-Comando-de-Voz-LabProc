"""Reconhecimento de fala offline com Vosk.

Dois truques importantes para o modelo pequeno de portugues rodar bem num Pi 3:

1. **Gramatica restrita.** Passando a lista de frases validas para o
   `KaldiRecognizer`, o decodificador so pode produzir aquelas palavras. A taxa
   de acerto em comandos fechados sobe muito. E exatamente o caso deste projeto.

2. **Ditado usa reconhecimento livre.** Quando o usuario pede "transcrever", a
   gramatica e desligada, senao seria impossivel ditar qualquer frase nova.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)

MODEL_HINT = """\
Modelo Vosk nao encontrado em: {path}

Baixe o modelo pequeno de portugues (~50 MB):

    bash scripts/download_model.sh

ou manualmente:

    mkdir -p models && cd models
    wget https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip
    unzip vosk-model-small-pt-0.3.zip
"""


# Os modelos Vosk vem em dois layouts diferentes, e ambos sao validos:
#
# 1. "classico" (modelos grandes):      am/  conf/  graph/  ivector/
# 2. "compilado" (modelos small, como   final.mdl  HCLr.fst  Gr.fst  mfcc.conf
#    o vosk-model-small-pt-0.3):        phones.txt  ivector/
#
# O segundo tem tudo na raiz, sem subpasta nenhuma. Validar so pelo primeiro
# fazia o projeto rejeitar um modelo perfeitamente bom.


class SpeechUnavailable(RuntimeError):
    """Vosk ausente ou modelo nao carregado."""


def looks_like_model(path: Path) -> bool:
    """True se a pasta tem a cara de um modelo Vosk extraido (qualquer layout)."""
    if not path.is_dir():
        return False

    # Layout classico: subpastas am/ e conf/.
    if (path / "am").is_dir() and (path / "conf").is_dir():
        return True
    if (path / "am" / "final.mdl").is_file():
        return True

    # Layout compilado: o modelo acustico e o grafo ficam na raiz.
    if (path / "final.mdl").is_file() and (
        (path / "HCLr.fst").is_file() or (path / "graph").is_dir()
    ):
        return True

    return False


def resolve_model_dir(path: Path) -> Path | None:
    """Encontra o modelo, inclusive quando o zip criou uma pasta a mais.

    E comum extrair `vosk-model-small-pt-0.3.zip` e acabar com
    `models/vosk-model-small-pt-0.3/vosk-model-small-pt-0.3/am/...`.
    Em vez de reclamar, a gente desce um nivel e usa o que achar.
    """
    path = Path(path)
    if looks_like_model(path):
        return path
    if not path.is_dir():
        return None
    for filho in sorted(p for p in path.iterdir() if p.is_dir()):
        if looks_like_model(filho):
            logger.info("Modelo encontrado em subpasta: %s", filho)
            return filho
    return None


class RecognitionSession:
    """Uma fala. Recebe blocos de audio e devolve texto."""

    def __init__(self, recognizer) -> None:
        self._recognizer = recognizer
        self._final: str | None = None

    def accept(self, chunk: bytes) -> str | None:
        """Alimenta o reconhecedor. Retorna texto se detectou fim de frase."""
        if self._recognizer.AcceptWaveform(chunk):
            text = json.loads(self._recognizer.Result()).get("text", "").strip()
            if text:
                self._final = text
            return text or None
        return None

    def partial(self) -> str:
        """Melhor palpite ate agora (para mostrar no LCD enquanto fala)."""
        return json.loads(self._recognizer.PartialResult()).get("partial", "").strip()

    def finish(self) -> str:
        """Encerra e devolve o texto completo."""
        tail = json.loads(self._recognizer.FinalResult()).get("text", "").strip()
        parts = [part for part in (self._final, tail) if part]
        # Evita duplicar quando o final ja tinha sido emitido.
        if len(parts) == 2 and parts[1] in parts[0]:
            parts.pop()
        return " ".join(parts).strip()


class VoskEngine:
    def __init__(self, model_path: Path, sample_rate: int = 16000) -> None:
        self.model_path = Path(model_path)
        self.sample_rate = sample_rate
        self._model = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> "VoskEngine":
        try:
            from vosk import Model, SetLogLevel  # noqa: PLC0415
        except ImportError as exc:
            raise SpeechUnavailable(
                "vosk nao instalado. Rode: pip install vosk"
            ) from exc

        resolvido = resolve_model_dir(self.model_path)
        if resolvido is None:
            raise SpeechUnavailable(MODEL_HINT.format(path=self.model_path))
        self.model_path = resolvido

        SetLogLevel(-1)  # o Kaldi e extremamente verboso por padrao
        logger.info("Carregando modelo Vosk de %s ...", self.model_path)
        self._model = Model(str(self.model_path))
        logger.info("Modelo carregado.")
        return self

    def session(self, grammar: Sequence[str] | None = None) -> RecognitionSession:
        """Cria uma sessao. `grammar=None` = reconhecimento livre (ditado)."""
        if self._model is None:
            raise SpeechUnavailable("Chame load() antes de reconhecer.")

        from vosk import KaldiRecognizer  # noqa: PLC0415

        if grammar:
            phrases = list(dict.fromkeys(grammar)) + ["[unk]"]
            try:
                recognizer = KaldiRecognizer(
                    self._model, self.sample_rate, json.dumps(phrases, ensure_ascii=False)
                )
            except Exception as exc:  # noqa: BLE001
                # Alguma palavra fora do lexico do modelo derruba a gramatica.
                logger.warning(
                    "Gramatica recusada pelo Vosk (%s). Usando reconhecimento livre.", exc
                )
                recognizer = KaldiRecognizer(self._model, self.sample_rate)
        else:
            recognizer = KaldiRecognizer(self._model, self.sample_rate)

        recognizer.SetWords(False)
        return RecognitionSession(recognizer)
