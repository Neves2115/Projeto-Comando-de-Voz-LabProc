"""Captura de audio em streaming.

O codigo antigo usava `sd.rec()`, que grava um bloco de duracao fixa e so
entrega tudo no final. Isso e ruim para comando de voz: voce fica esperando o
tempo acabar mesmo tendo dito "ligar led" em meio segundo.

Aqui usamos `RawInputStream`, que entrega blocos de ~250 ms enquanto voce fala.

**Negociacao de formato.** Muitos microfones USB (Fifine, Blue Snowball, webcams)
nao aceitam 16 kHz: o conversor interno deles trabalha em 44,1 ou 48 kHz e o
PortAudio responde `Invalid sample rate [PaErrorCode -9997]`. Alguns tambem so
abrem em estereo. Em vez de exigir um formato fixo, esta classe testa o que o
dispositivo aceita e se adapta:

* a taxa efetiva e repassada ao Vosk, que reamostra para 16 kHz internamente;
* audio estereo e convertido para mono aqui mesmo, sem numpy nem audioop
  (este ultimo foi removido do Python 3.13).
"""

from __future__ import annotations

import array
import logging
import math
import queue
import wave
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ..config import AudioConfig
from ..utils import ensure_dir, timestamp_slug

logger = logging.getLogger(__name__)

SAMPLE_WIDTH_BYTES = 2  # int16

#: Taxas testadas, nesta ordem. 16 kHz e o formato nativo do Vosk.
#: Quando ele nao esta disponivel, multiplos exatos de 16000 (48k, 32k) sao
#: preferidos a 44100: a reamostragem 3:1 e limpa, enquanto 44100 -> 16000 tem
#: razao 2,75625 e introduz mais artefato -- que o modelo pequeno sente.
CANDIDATE_RATES = (16000, 48000, 32000, 44100, 22050, 8000)


class AudioUnavailable(RuntimeError):
    """Sem microfone ou sem a biblioteca de audio."""


def _import_sounddevice():
    try:
        import sounddevice
    except ImportError as exc:
        raise AudioUnavailable(
            "sounddevice nao instalado.\n"
            "    sudo apt install -y libportaudio2\n"
            "    pip install sounddevice"
        ) from exc
    except OSError as exc:  # PortAudio ausente no sistema
        raise AudioUnavailable(
            f"PortAudio nao encontrado ({exc}). Rode: sudo apt install -y libportaudio2"
        ) from exc
    return sounddevice


def supported_rates(device: int | str | None, channels: int = 1) -> list[int]:
    """Quais taxas de amostragem o dispositivo aceita."""
    sd = _import_sounddevice()
    aceitas = []
    for rate in CANDIDATE_RATES:
        try:
            sd.check_input_settings(
                device=device, channels=channels, samplerate=rate, dtype="int16"
            )
            aceitas.append(rate)
        except Exception:
            continue
    return aceitas


def list_input_devices() -> list[dict]:
    """Dispositivos de entrada disponiveis. Usado por `voz devices`."""
    sd = _import_sounddevice()
    devices = []
    for index, info in enumerate(sd.query_devices()):
        if info.get("max_input_channels", 0) > 0:
            devices.append(
                {
                    "index": index,
                    "name": info.get("name", "?"),
                    "channels": info.get("max_input_channels"),
                    "default_samplerate": info.get("default_samplerate"),
                    "rates": supported_rates(index),
                }
            )
    return devices


def _to_mono(data: bytes, channels: int) -> bytes:
    """Mistura canais intercalados em mono (int16 little-endian).

    Faz a MEDIA dos canais em vez de pegar so o primeiro. Muitos adaptadores
    USB baratos (CM108 e afins) expoem entrada estereo com o microfone ligado
    em apenas um dos canais -- pegando so o canal 0 voce pode acabar gravando
    silencio puro. A media tambem ganha ~3 dB de relacao sinal/ruido quando os
    dois canais tem o mesmo sinal.
    """
    if channels <= 1:
        return data

    amostras = array.array("h")
    amostras.frombytes(data)
    quadros = len(amostras) // channels
    saida = array.array("h", bytes(2 * quadros))
    for i in range(quadros):
        base = i * channels
        saida[i] = sum(amostras[base : base + channels]) // channels
    return saida.tobytes()


def analyze_levels(data: bytes, channels: int = 1) -> list[dict]:
    """Nivel de cada canal: RMS em dBFS, pico e amostras saturadas."""
    amostras = array.array("h")
    amostras.frombytes(data)

    resultados = []
    for canal in range(channels):
        fatia = amostras[canal::channels]
        if not fatia:
            resultados.append({"rms_dbfs": -120.0, "peak_dbfs": -120.0, "clip_pct": 0.0})
            continue
        soma = sum(v * v for v in fatia)
        rms = (soma / len(fatia)) ** 0.5
        pico = max(abs(v) for v in fatia)
        saturadas = sum(1 for v in fatia if abs(v) >= 32000)
        resultados.append(
            {
                "rms_dbfs": 20 * math.log10(rms / 32768) if rms > 0 else -120.0,
                "peak_dbfs": 20 * math.log10(pico / 32768) if pico > 0 else -120.0,
                "clip_pct": 100.0 * saturadas / len(fatia),
            }
        )
    return resultados


class Microphone:
    """Fonte de blocos de audio PCM 16 bits mono.

    Depois de `check()`, `sample_rate` guarda a taxa que o dispositivo aceitou
    de verdade -- que pode nao ser a pedida na configuracao. Use sempre esse
    valor ao criar o reconhecedor.
    """

    def __init__(self, config: AudioConfig) -> None:
        self.config = config
        self.sample_rate = config.sample_rate
        self.device_channels = config.channels
        self._sd = None

    # ------------------------------------------------------------------ #

    def check(self) -> None:
        """Negocia taxa e canais com o dispositivo. Levanta AudioUnavailable."""
        self._sd = _import_sounddevice()
        device = self.config.input_device

        try:
            info = (
                self._sd.query_devices(device, "input")
                if device is not None
                else self._sd.query_devices(kind="input")
            )
        except Exception as exc:
            raise AudioUnavailable(
                f"Nao consegui consultar o dispositivo de entrada ({exc}).\n"
                "Liste as opcoes com: voz devices"
            ) from exc

        nome = info.get("name", "?")
        max_canais = int(info.get("max_input_channels") or 1)
        taxa_padrao = int(info.get("default_samplerate") or 0)

        # Ordem de tentativa: o que foi pedido, o padrao do proprio dispositivo,
        # depois a lista de candidatas.
        taxas = list(
            dict.fromkeys(
                [self.config.sample_rate]
                + ([taxa_padrao] if taxa_padrao else [])
                + list(CANDIDATE_RATES)
            )
        )
        canais = list(dict.fromkeys([self.config.channels, max_canais]))

        erros: list[str] = []
        for taxa in taxas:
            for n_canais in canais:
                if n_canais > max_canais:
                    continue
                try:
                    self._sd.check_input_settings(
                        device=device,
                        channels=n_canais,
                        samplerate=taxa,
                        dtype="int16",
                    )
                except Exception as exc:
                    erros.append(f"{taxa} Hz x {n_canais}ch: {exc}")
                    continue

                self.sample_rate = taxa
                self.device_channels = n_canais
                if taxa != self.config.sample_rate:
                    logger.info(
                        "'%s' nao aceita %d Hz. Capturando a %d Hz; "
                        "o Vosk reamostra internamente.",
                        nome,
                        self.config.sample_rate,
                        taxa,
                    )
                if n_canais > 1:
                    logger.info(
                        "'%s' so abre com %d canais. Convertendo para mono.",
                        nome,
                        n_canais,
                    )
                logger.info("Microfone: %s (%d Hz, %d canal(is))", nome, taxa, n_canais)
                return

        detalhe = "\n    ".join(erros[:6])
        raise AudioUnavailable(
            f"O dispositivo '{nome}' nao aceitou nenhum formato testado.\n"
            f"    {detalhe}\n\n"
            "Liste os dispositivos com `voz devices` e escolha outro em config.toml:\n"
            "    [audio]\n    input_device = 2\n\n"
            "Se o microfone estiver ocupado por outro programa (navegador, "
            "pulseaudio), feche-o e tente de novo."
        )

    # ------------------------------------------------------------------ #

    @contextmanager
    def stream(self, mono: bool = True) -> Iterator[queue.Queue]:
        """Abre o microfone e entrega uma fila de blocos de audio.

        `mono=False` entrega os canais como vieram -- usado so pelo `voz mic`,
        que precisa medir cada canal separadamente.
        """
        sd = self._sd or _import_sounddevice()
        blocks: queue.Queue = queue.Queue()
        canais = self.device_channels

        def callback(indata, _frames, _time, status) -> None:
            if status:
                logger.debug("Status do stream de audio: %s", status)
            bruto = bytes(indata)
            blocks.put(_to_mono(bruto, canais) if mono else bruto)

        # O tamanho do bloco escala com a taxa para manter ~250 ms por bloco.
        block_size = max(
            1024, int(self.config.block_size * self.sample_rate / self.config.sample_rate)
        )

        stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=block_size,
            device=self.config.input_device,
            dtype="int16",
            channels=canais,
            callback=callback,
        )
        with stream:
            logger.debug(
                "Microfone aberto (%d Hz, %d ch, blocos de %d)",
                self.sample_rate,
                canais,
                block_size,
            )
            yield blocks

    # ------------------------------------------------------------------ #

    def measure(self, seconds: float = 4.0) -> dict:
        """Grava alguns segundos e mede o nivel de cada canal."""
        import time as _time

        pedacos: list[bytes] = []
        with self.stream(mono=False) as blocos:
            fim = _time.monotonic() + seconds
            while _time.monotonic() < fim:
                try:
                    pedacos.append(blocos.get(timeout=0.2))
                except queue.Empty:
                    continue

        bruto = b"".join(pedacos)
        return {
            "sample_rate": self.sample_rate,
            "channels": self.device_channels,
            "seconds": (len(bruto) / SAMPLE_WIDTH_BYTES / max(1, self.device_channels))
            / max(1, self.sample_rate),
            "levels": analyze_levels(bruto, self.device_channels),
            "raw": bruto,
        }

    def duration_of(self, chunks: list[bytes]) -> float:
        """Duracao em segundos do audio ja convertido para mono."""
        total = sum(len(chunk) for chunk in chunks)
        return (total / SAMPLE_WIDTH_BYTES) / max(1, self.sample_rate)

    def save_wav(self, chunks: list[bytes], directory: Path) -> Path:
        """Grava o audio capturado (util para depurar reconhecimento ruim)."""
        ensure_dir(directory)
        path = directory / f"audio_{timestamp_slug()}.wav"
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)  # ja foi convertido para mono
            handle.setsampwidth(SAMPLE_WIDTH_BYTES)
            handle.setframerate(self.sample_rate)
            handle.writeframes(b"".join(chunks))
        return path
