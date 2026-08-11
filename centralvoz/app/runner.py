"""Loop principal push-to-talk.

Fluxo de uma interacao:

    botao pressionado  ->  LED acende, LCD mostra "Ouvindo"
    enquanto segurado  ->  blocos de audio vao para o Vosk, parcial no LCD
    botao solto        ->  resultado final -> roteador -> handler -> perifericos

O stream do microfone fica aberto o tempo todo e a fila e esvaziada quando
ninguem esta falando. Abrir o PortAudio a cada aperto custaria ~300 ms de
latencia no Pi 3.
"""

from __future__ import annotations

import logging
import queue
import time

from ..audio.microphone import Microphone
from ..commands.intents import AppMode
from ..config import AppConfig
from ..speech.vosk_engine import VoskEngine
from ..utils import ensure_dir
from .controller import VoiceCommandController

logger = logging.getLogger(__name__)

PARTIAL_REFRESH_S = 0.45


class VoiceLoop:
    def __init__(
        self,
        config: AppConfig,
        controller: VoiceCommandController,
        engine: VoskEngine,
        microphone: Microphone,
    ) -> None:
        self.config = config
        self.controller = controller
        self.engine = engine
        self.microphone = microphone
        self._running = False
        self._last_activity = time.monotonic()

        # Ganchos opcionais para quem quiser acompanhar o reconhecimento --
        # a interface Jarvis, por exemplo. Ficam vazios no modo texto.
        #   on_status(nome)          "ouvindo" | "processando"
        #   on_partial(texto)        melhor palpite ate agora, texto completo
        self.on_status = None
        self.on_partial = None

    def run(self) -> None:
        hardware = self.controller.hardware
        trigger = hardware.trigger

        self.controller.greet()
        print(f"\n  {trigger.prompt}.  Ctrl+C para sair.\n")
        self._running = True

        with self.microphone.stream() as blocks:
            while self._running:
                _drain(blocks)
                self._maybe_leave_dictation()

                try:
                    if not trigger.wait_for_activation(timeout=0.3):
                        continue
                except KeyboardInterrupt:
                    break

                # O stop() pode ter chegado enquanto esperavamos o gatilho.
                if not self._running:
                    break

                text = self._capture(blocks)
                # Descarta ativacoes que chegaram durante a captura: sem isso,
                # ENTER apertado enquanto o sistema processa vira uma nova
                # captura vazia assim que o loop volta.
                trigger.flush()

                if not text:
                    hardware.lcd.show_lines("Nao ouvi nada", "tente de novo")
                    hardware.matrix.show_icon("alerta")
                    continue

                self._last_activity = time.monotonic()
                reply = self.controller.handle_text(text)
                print(f"  > {reply.message}")
                trigger.flush()
                if reply.stop:
                    break

    def stop(self) -> None:
        self._running = False
        self.controller.close()

    # ------------------------------------------------------------------ #

    def _capture(self, blocks: "queue.Queue[bytes]") -> str:
        """Grava enquanto o gatilho estiver ativo e devolve a transcricao."""
        hardware = self.controller.hardware
        audio = self.config.audio

        session = self.engine.session(self.controller.grammar())
        chunks: list[bytes] = []
        started = time.monotonic()
        last_partial = 0.0

        hardware.leds.on()
        hardware.matrix.show_icon("ouvindo")
        hardware.lcd.show_lines("Ouvindo...", "")
        self._notify_status("ouvindo")

        try:
            while hardware.trigger.is_active() and self._running:
                if time.monotonic() - started > audio.max_utterance_s:
                    logger.info("Tempo maximo de fala atingido.")
                    break
                try:
                    chunk = blocks.get(timeout=0.15)
                except queue.Empty:
                    continue

                chunks.append(chunk)
                session.accept(chunk)

                now = time.monotonic()
                if now - last_partial >= PARTIAL_REFRESH_S:
                    last_partial = now
                    partial = session.partial()
                    if partial:
                        # O LCD so tem 16 colunas, mas o gancho recebe o texto
                        # inteiro: a interface tem espaco para mostrar tudo.
                        hardware.lcd.show_lines("Ouvindo...", partial[-16:])
                        self._notify_partial(partial)
        finally:
            hardware.leds.off()

        elapsed = self.microphone.duration_of(chunks)
        if elapsed < audio.min_utterance_s:
            logger.info("Fala curta demais (%.2f s), ignorando.", elapsed)
            return ""

        if self.config.save_recordings and chunks:
            path = self.microphone.save_wav(chunks, ensure_dir(self.config.recordings_dir))
            logger.debug("Audio salvo em %s", path)

        hardware.lcd.show_lines("Processando...", "")
        self._notify_status("processando")
        text = session.finish()
        logger.debug("Transcricao (%.1f s): %r", elapsed, text)
        return text

    def _notify_status(self, nome: str) -> None:
        if self.on_status is not None:
            try:
                self.on_status(nome)
            except Exception:  # noqa: BLE001 - a interface nao derruba o loop
                logger.debug("on_status falhou", exc_info=True)

    def _notify_partial(self, texto: str) -> None:
        if self.on_partial is not None:
            try:
                self.on_partial(texto)
            except Exception:  # noqa: BLE001
                logger.debug("on_partial falhou", exc_info=True)

    def _maybe_leave_dictation(self) -> None:
        """Sai do ditado sozinho depois de um tempo sem falar."""
        if self.controller.mode is not AppMode.DICTATION:
            return
        idle = time.monotonic() - self._last_activity
        if idle >= self.config.behavior.dictation_timeout_s:
            logger.info("Ditado encerrado por inatividade.")
            self.controller.mode = AppMode.COMMAND
            self.controller.hardware.lcd.show_lines("Ditado", "encerrado")
            self._last_activity = time.monotonic()


def _drain(blocks: "queue.Queue[bytes]") -> None:
    """Descarta o audio capturado enquanto ninguem estava falando."""
    while True:
        try:
            blocks.get_nowait()
        except queue.Empty:
            return
