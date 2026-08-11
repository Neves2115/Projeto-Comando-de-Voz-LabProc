"""Ligacao entre a interface Jarvis e o loop de voz."""

from __future__ import annotations

import curses
import logging
import threading
import time

from ..app.controller import VoiceCommandController
from ..app.runner import VoiceLoop
from ..audio.microphone import Microphone
from ..commands.intents import AppMode
from ..config import AppConfig
from ..hardware.factory import HardwareSet
from ..hardware.trigger import Trigger
from ..speech.vosk_engine import VoskEngine
from ..storage.db import Storage
from .tui import JarvisUi, UiLogHandler, UiState

logger = logging.getLogger(__name__)


class UiTrigger(Trigger):
    """Push-to-talk acionado pela tecla ENTER da interface.

    Implementa a mesma interface do botao no GPIO, entao o loop de voz nao sabe
    a diferenca. Se houver botao fisico, ele e consultado tambem: os dois
    funcionam ao mesmo tempo.
    """

    simulated = True
    prompt = "ENTER para falar"

    def __init__(self, physical: Trigger | None = None) -> None:
        self._active = threading.Event()
        self._pressed = threading.Event()
        self.physical = physical

    # -- chamado pela interface ----------------------------------------- #

    def toggle(self) -> None:
        if self._active.is_set():
            self._active.clear()
        else:
            self._active.set()
            self._pressed.set()

    # -- consumido pelo loop de voz -------------------------------------- #

    def wait_for_activation(self, timeout: float | None = None) -> bool:
        limite = time.monotonic() + (timeout if timeout is not None else 3600)
        while time.monotonic() < limite:
            if self._pressed.wait(0.05):
                self._pressed.clear()
                return True
            # Um botao fisico ligado continua funcionando junto com o ENTER.
            if self.physical is not None and self.physical.is_active():
                self._active.set()
                return True
        return False

    def is_active(self) -> bool:
        if self.physical is not None and self.physical.is_active():
            return True
        return self._active.is_set()

    def flush(self) -> None:
        self._active.clear()
        self._pressed.clear()

    def close(self) -> None:
        self._active.clear()
        if self.physical is not None:
            self.physical.close()


class ObservedController(VoiceCommandController):
    """Controller que publica o que acontece para a interface."""

    def __init__(self, *args, state: UiState, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.state = state

    def handle_text(self, text: str):
        self.state.set_status("executando")
        reply = super().handle_text(text)

        with self.state.lock:
            self.state.last_heard = text
            self.state.mode = "ditado" if self.mode is AppMode.DICTATION else "comando"
            self.state.task = f"tarefa: {self.task.label}" if self.task.running else ""

        tipo = "erro" if reply.icon == "erro" else "ok"
        self.state.log(f'"{text}" → {reply.message}', tipo)
        self.state.set_status("pronto")
        return reply


class ObservedLoop(VoiceLoop):
    """Loop de voz que reporta cada fase para a interface."""

    def __init__(self, *args, state: UiState, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.state = state

    def run(self) -> None:
        # A saudacao no LCD continua; o print no terminal nao, porque a tela
        # pertence ao curses agora.
        self.controller.greet()
        self.state.set_status("pronto")
        self.state.log("Jarvis pronto. ENTER para falar.", "ok")
        self._running = True

        with self.microphone.stream() as blocks:
            while self._running:
                from .runtime import _drain_queue

                _drain_queue(blocks)
                self._maybe_leave_dictation()

                try:
                    if not self.controller.hardware.trigger.wait_for_activation(timeout=0.3):
                        continue
                except KeyboardInterrupt:
                    break
                if not self._running:
                    break

                self.state.set_status("ouvindo")
                text = self._capture(blocks)
                self.controller.hardware.trigger.flush()

                with self.state.lock:
                    self.state.partial = ""

                if not text:
                    self.state.log("não ouvi nada — tente de novo", "aviso")
                    self.state.set_status("pronto")
                    continue

                self._last_activity = time.monotonic()
                reply = self.controller.handle_text(text)
                self.controller.hardware.trigger.flush()
                if reply.stop:
                    self._running = False
                    break

    def _capture(self, blocks):
        """Igual ao original, mas publicando o parcial na interface."""
        original = self.controller.hardware.lcd.show_lines

        def espelhar(*linhas: str) -> None:
            original(*linhas)
            if len(linhas) > 1 and linhas[1]:
                with self.state.lock:
                    self.state.partial = f"… {linhas[1]}"

        self.controller.hardware.lcd.show_lines = espelhar  # type: ignore[method-assign]
        try:
            self.state.set_status("processando")
            return super()._capture(blocks)
        finally:
            self.controller.hardware.lcd.show_lines = original  # type: ignore[method-assign]


def _drain_queue(fila) -> None:
    import queue

    while True:
        try:
            fila.get_nowait()
        except queue.Empty:
            return


def run_jarvis(
    config: AppConfig,
    hardware: HardwareSet,
    storage: Storage,
    engine: VoskEngine,
    microphone: Microphone,
) -> int:
    """Sobe a interface Jarvis com o loop de voz em segundo plano."""
    state = UiState()
    with state.lock:
        state.hardware = hardware.summary()

    # WARNING+ vai para o painel de atividade em vez de sujar a tela do curses.
    raiz = logging.getLogger()
    console = [h for h in raiz.handlers if isinstance(h, logging.StreamHandler)]
    for handler in console:
        raiz.removeHandler(handler)
    ui_handler = UiLogHandler(state)
    raiz.addHandler(ui_handler)

    fisico = hardware.trigger if config.trigger == "button" else None
    trigger = UiTrigger(physical=fisico)
    hardware.trigger = trigger

    controller = ObservedController(config, hardware, storage, state=state)
    loop = ObservedLoop(config, controller, engine, microphone, state=state)

    parar = threading.Event()

    def encerrar() -> None:
        parar.set()
        loop.stop()

    thread = threading.Thread(target=_rodar_loop, args=(loop, state), daemon=True)

    try:
        curses.wrapper(_curses_main, state, trigger, encerrar, thread, parar)
    finally:
        raiz.removeHandler(ui_handler)
        for handler in console:
            raiz.addHandler(handler)
        loop.stop()
        controller.close()
    return 0


def _rodar_loop(loop: ObservedLoop, state: UiState) -> None:
    try:
        loop.run()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Loop de voz falhou")
        state.log(f"loop de voz parou: {exc}", "erro")
        state.set_status("erro")


def _curses_main(tela, state: UiState, trigger, encerrar, thread, parar) -> None:
    from .tui import _init_colors

    curses.curs_set(0)
    tela.nodelay(True)
    tela.keypad(True)
    _init_colors()

    ui = JarvisUi(state, trigger, encerrar)
    thread.start()

    while not parar.is_set():
        ui.draw(tela)

        tecla = tela.getch()
        if tecla != -1 and not ui.handle_key(tecla):
            break
        # ~20 fps: suave para o relogio e o indicador de status, e leve para o Pi.
        time.sleep(0.05)
