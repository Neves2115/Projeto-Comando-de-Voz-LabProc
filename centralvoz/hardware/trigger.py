"""Gatilho de escuta (push-to-talk).

Duas implementacoes com a mesma interface:

* `GpioButton`  - botao fisico entre o GPIO e o GND. Segure para falar.
* `KeyboardTrigger` - fallback sem hardware: ENTER comeca, ENTER termina.

O loop principal so conhece a interface, entao trocar um pelo outro nao muda
nenhuma linha do resto do programa.
"""

from __future__ import annotations

import queue
import sys
import threading

from .base import Peripheral


class Trigger(Peripheral):
    name = "gatilho"

    #: Texto mostrado ao usuario ("Segure o botao", "Aperte ENTER"...).
    prompt = "Aguardando"

    def wait_for_activation(self, timeout: float | None = None) -> bool:
        """Bloqueia ate o usuario iniciar a fala. False se estourou o timeout."""
        raise NotImplementedError

    def is_active(self) -> bool:
        """True enquanto o usuario ainda esta falando."""
        raise NotImplementedError

    def flush(self) -> None:
        """Descarta ativacoes acumuladas.

        Chamado depois de operacoes longas: sem isso, cada ENTER apertado
        durante um comando demorado vira uma captura vazia quando o loop
        principal volta a rodar.
        """

    def close(self) -> None:
        pass


class GpioButton(Trigger):
    simulated = False
    prompt = "Segure o botao e fale"

    def __init__(self, pin: int, gpiozero_module) -> None:
        self._button = gpiozero_module.Button(pin, pull_up=True, bounce_time=0.05)
        self._log_setup("botao push-to-talk no pino %s (para o GND)", pin)

    def wait_for_activation(self, timeout: float | None = None) -> bool:
        return bool(self._button.wait_for_press(timeout=timeout))

    def is_active(self) -> bool:
        return bool(self._button.is_pressed)

    def flush(self) -> None:
        # O gpiozero nao enfileira eventos de wait_for_press, entao nada a fazer.
        pass

    def close(self) -> None:
        try:
            self._button.close()
        except Exception:
            pass


class KeyboardTrigger(Trigger):
    """ENTER liga, ENTER desliga. Roda a leitura do stdin numa thread."""

    simulated = True
    prompt = "Aperte ENTER para falar, ENTER de novo para parar"

    def __init__(self) -> None:
        self._events: queue.Queue[str] = queue.Queue()
        self._active = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _ensure_reader(self) -> None:
        """A thread so nasce no primeiro uso.

        Sem isso, o modo `voz text` teria duas leituras concorrentes do stdin:
        esta thread e o `input()` do loop de comandos digitados.
        """
        if self._thread is None:
            self._thread = threading.Thread(target=self._read_stdin, daemon=True)
            self._thread.start()

    def _read_stdin(self) -> None:
        while not self._stop.is_set():
            try:
                line = sys.stdin.readline()
            except (ValueError, OSError):
                return
            if not line:  # EOF
                self._events.put("quit")
                return
            self._events.put(line.strip().lower())

    def wait_for_activation(self, timeout: float | None = None) -> bool:
        self._ensure_reader()
        try:
            command = self._events.get(timeout=timeout)
        except queue.Empty:
            return False
        if command in {"sair", "quit", "exit"}:
            raise KeyboardInterrupt
        self._active.set()
        return True

    def is_active(self) -> bool:
        # Qualquer nova linha durante a fala encerra a captura.
        try:
            self._events.get_nowait()
            self._active.clear()
        except queue.Empty:
            pass
        return self._active.is_set()

    def stop_active(self) -> None:
        self._active.clear()

    def flush(self) -> None:
        self._active.clear()
        while True:
            try:
                self._events.get_nowait()
            except queue.Empty:
                return

    def close(self) -> None:
        self._stop.set()
        self._active.clear()
