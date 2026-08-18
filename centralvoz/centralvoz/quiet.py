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
import threading
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


@contextlib.contextmanager
def redirect_native_stderr_to(path) -> Iterator[None]:
    """Desvia o stderr do SISTEMA (fd 2) para um arquivo enquanto durar o bloco.

    Feito para a interface Jarvis. O curses desenha pelo fd 1; qualquer coisa
    escrita no fd 2 aparece por cima da tela e destroi o layout -- e nao ha como
    o curses saber que isso aconteceu para se redesenhar.

    Quem escreve ali e codigo C que o Python nao controla:

    * o Kaldi avisa sobre cada palavra da gramatica que nao esta no lexico,
      justamente no momento em que o reconhecedor e criado (ou seja, ao apertar
      ENTER para falar);
    * o ALSA reclama de placas inexistentes ao abrir o stream.

    Mandar tudo para um arquivo preserva a informacao para depuracao sem sujar
    a tela.
    """
    try:
        original = os.dup(2)
    except OSError:  # pragma: no cover
        yield
        return

    destino = None
    try:
        destino = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        sys.stderr.flush()
        os.dup2(destino, 2)
        yield
    finally:
        try:
            sys.stderr.flush()
            os.dup2(original, 2)
        finally:
            os.close(original)
            if destino is not None:
                os.close(destino)


@contextlib.contextmanager
def capture_native_stderr(callback) -> Iterator[None]:
    """Captura o stderr do SISTEMA (fd 2) e entrega linha a linha ao callback.

    Diferente de `redirect_native_stderr_to`, que joga tudo num arquivo, aqui a
    saida continua visivel -- so que dentro da interface, no lugar certo.

    Como funciona: o fd 2 passa a apontar para a ponta de escrita de um pipe, e
    uma thread le a outra ponta. Assim o Kaldi e o ALSA escrevem normalmente,
    achando que estao no terminal, mas quem recebe e a aplicacao.

    E o unico jeito de mostrar essas mensagens: elas vem de codigo C e nunca
    passam pelo `logging` do Python.
    """
    try:
        original = os.dup(2)
        leitura, escrita = os.pipe()
    except OSError:  # pragma: no cover
        yield
        return

    parar = threading.Event()

    def ler() -> None:
        with os.fdopen(leitura, "r", errors="replace") as fonte:
            for linha in fonte:
                if parar.is_set():
                    break
                texto = linha.rstrip()
                if texto:
                    try:
                        callback(texto)
                    except Exception:  # noqa: BLE001
                        pass

    thread = threading.Thread(target=ler, name="stderr-capture", daemon=True)
    thread.start()

    try:
        sys.stderr.flush()
        os.dup2(escrita, 2)
        os.close(escrita)
        yield
    finally:
        parar.set()
        try:
            sys.stderr.flush()
            os.dup2(original, 2)  # fecha a ponta de escrita e encerra o leitor
        finally:
            os.close(original)
        thread.join(timeout=1.0)


class StdoutToLog:
    """Substitui `sys.stdout` para que `print()` nao rasgue a tela do curses.

    Um `print()` esquecido em qualquer thread escreveria no fd 1, exatamente
    onde o curses desenha. Em vez de cacar todos os prints, redirecionamos o
    stdout do Python para o painel de atividade.

    O curses nao e afetado: ele escreve no descritor 1 direto, sem passar por
    `sys.stdout`.
    """

    def __init__(self, sink) -> None:
        self.sink = sink
        self._buffer = ""

    def write(self, texto: str) -> int:
        self._buffer += texto
        while "\n" in self._buffer:
            linha, self._buffer = self._buffer.split("\n", 1)
            if linha.strip():
                self.sink(linha.strip()[:200])
        return len(texto)

    def flush(self) -> None:
        if self._buffer.strip():
            self.sink(self._buffer.strip()[:200])
        self._buffer = ""

    def isatty(self) -> bool:
        return False


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
