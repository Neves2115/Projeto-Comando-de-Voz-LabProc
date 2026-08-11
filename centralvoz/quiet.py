"""Silenciamento dos avisos que poluem o terminal.

Nada aqui esconde erro de verdade. O que se cala e ruido conhecido e inofensivo:

* **ALSA/JACK.** Ao abrir o PortAudio, a biblioteca C do ALSA despeja dezenas de
  linhas em stderr sobre placas inexistentes (`snd_pcm_open`, `Unknown PCM
  cards.pcm.rear`, `jack server is not running`). Sao avisos de configuracao
  padrao do Debian, nao problemas do projeto. Como saem da camada C, `logging`
  nao alcanca: e preciso desviar o descritor 2 no nivel do sistema operacional.

* **gpiozero.** Emite `PinFactoryFallback` para cada backend que tenta antes de
  achar um que funcione. Como o projeto ja escolhe a fabrica explicitamente em
  `gpio_setup`, esses avisos so confundem.

* **Vosk/Kaldi.** `SetLogLevel(-1)` cobre a maior parte, mas o carregamento do
  modelo ainda escreve em stderr.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
import warnings
from typing import Iterator

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def suppress_native_stderr() -> Iterator[None]:
    """Desvia o stderr do SISTEMA (fd 2) para /dev/null temporariamente.

    Precisa ser no nivel do descritor porque quem escreve e codigo C (ALSA,
    PortAudio, Kaldi). Trocar `sys.stderr` no Python nao afetaria nada.

    Excecoes continuam funcionando: elas sobem pelo Python, nao pelo fd 2.
    """
    try:
        original = os.dup(2)
    except OSError:  # pragma: no cover - sem fd 2 (raro)
        yield
        return

    devnull = None
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        sys.stderr.flush()
        os.dup2(devnull, 2)
        yield
    finally:
        try:
            sys.stderr.flush()
            os.dup2(original, 2)
        finally:
            os.close(original)
            if devnull is not None:
                os.close(devnull)


def quiet_libraries() -> None:
    """Reduz o barulho das bibliotecas de terceiros. Chamar cedo, uma vez."""
    # gpiozero: o fallback de pin factory ja e tratado por gpio_setup.
    warnings.filterwarnings("ignore", message=".*Falling back from.*")
    warnings.filterwarnings("ignore", module="gpiozero")

    for nome, nivel in (
        ("gpiozero", logging.ERROR),
        ("vosk", logging.ERROR),
        ("sounddevice", logging.WARNING),
        ("smbus2", logging.WARNING),
        ("asyncio", logging.WARNING),
    ):
        logging.getLogger(nome).setLevel(nivel)

    # Faz o ALSA parar de reclamar de placas que nao existem nesta maquina.
    os.environ.setdefault("ALSA_CARD", os.environ.get("ALSA_CARD", ""))
    os.environ.setdefault("JACK_NO_START_SERVER", "1")
    os.environ.setdefault("PYTHONWARNINGS", "ignore")
