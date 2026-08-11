"""Orquestracao: texto -> intencao -> handler -> feedback fisico -> log."""

from __future__ import annotations

import logging

from ..commands.handlers import HANDLERS, Context, Reply
from ..commands.intents import AppMode, Intent
from ..commands.router import CommandRouter, Match
from ..config import AppConfig
from ..hardware.factory import HardwareSet
from ..storage.db import Storage
from ..tasks import BackgroundTask
from ..utils import to_ascii

logger = logging.getLogger(__name__)


class VoiceCommandController:
    def __init__(
        self,
        config: AppConfig,
        hardware: HardwareSet,
        storage: Storage,
        router: CommandRouter | None = None,
    ) -> None:
        self.config = config
        self.hardware = hardware
        self.storage = storage
        self.router = router or CommandRouter(threshold=config.speech.match_threshold)
        self.task = BackgroundTask()
        self.context = Context(
            config=config, hardware=hardware, storage=storage, task=self.task
        )
        self.mode = AppMode.COMMAND

    # ------------------------------------------------------------------ #

    def handle_text(self, text: str) -> Reply:
        """Ponto de entrada unico: fala transcrita ou comando digitado."""
        if self.mode is AppMode.DICTATION:
            return self._handle_dictation(text)
        return self._handle_command(text)

    # ------------------------------------------------------------------ #

    def _handle_command(self, text: str) -> Reply:
        match = self.router.route(text)
        self.context.heard = text
        self.context.number = match.number
        self.context.color = match.color
        logger.info(
            "Ouvi %r -> %s (confianca %.2f)", text, match.intent.value, match.score
        )

        handler = HANDLERS.get(match.intent, HANDLERS[Intent.UNKNOWN])
        try:
            reply = handler(self.context)
        except Exception as exc:
            logger.exception("Handler de %s falhou", match.intent.value)
            reply = Reply(f"Erro ao executar: {exc}", "Erro", str(exc)[:16], icon="erro")

        self._apply(reply)
        self._remember(match, reply)
        self._record(match, reply)
        return reply

    def _handle_dictation(self, text: str) -> Reply:
        """No modo ditado, tudo vira texto no LCD -- menos o comando de sair."""
        stop = self.router.route(text)
        if stop.intent in {Intent.DICTATION_STOP, Intent.SHUTDOWN} and stop.score >= 0.85:
            return self._handle_command(text)

        clean = text.strip()
        if not clean:
            reply = Reply("Nao ouvi nada.", "Ditado", "silencio", icon="alerta")
            self._apply(reply)
            return reply

        note_id = self.storage.add_note(clean)
        self.context.heard = clean
        self.context.last_content = clean
        reply = Reply(
            f"Transcrito: {clean}",
            lcd_text=clean,
            icon="ouvindo",
            repeatable=True,
        )
        self._apply(reply)
        self.storage.log_event("dictation", heard=clean, result=f"note={note_id}")
        return reply

    # ------------------------------------------------------------------ #

    def _apply(self, reply: Reply) -> None:
        """Manda a resposta para os perifericos."""
        lcd = self.hardware.lcd
        if reply.lcd_text is not None:
            lcd.show_text(_lcd_safe(reply.lcd_text))
        elif reply.lcd_title or reply.lcd_detail:
            lcd.show_lines(_lcd_safe(reply.lcd_title), _lcd_safe(reply.lcd_detail))

        if reply.icon:
            self.hardware.matrix.show_icon(reply.icon)

        if reply.next_mode is not None and reply.next_mode is not self.mode:
            logger.info("Modo: %s -> %s", self.mode.value, reply.next_mode.value)
            self.mode = reply.next_mode

    def _remember(self, match: Match, reply: Reply) -> None:
        """Guarda o que faz sentido repetir depois.

        So respostas marcadas como `repeatable` contam. Assim nem o proprio
        'repetir' nem confirmacoes como 'servo aberto' apagam o conteudo que
        o usuario quer ouvir de novo.
        """
        if match.intent is Intent.REPEAT_LAST or not reply.repeatable:
            return
        content = reply.lcd_text or reply.message
        if content:
            self.context.last_content = content

    def _record(self, match: Match, reply: Reply) -> None:
        self.storage.log_event(
            "command",
            intent=match.intent.value,
            heard=match.heard,
            score=match.score,
            result=reply.message,
        )

    # ------------------------------------------------------------------ #

    def grammar(self) -> list[str] | None:
        """Vocabulario para o Vosk no modo atual (None = reconhecimento livre)."""
        if self.mode is AppMode.DICTATION or not self.config.speech.use_grammar:
            return None
        return self.router.vocabulary()

    def close(self) -> None:
        """Cancela qualquer tarefa em andamento. Chamado ao encerrar."""
        self.task.cancel()

    def greet(self) -> None:
        self.hardware.lcd.show_lines("Central de Voz", self.hardware.trigger.prompt[:16])
        self.hardware.matrix.show_icon("casa")


def _lcd_safe(text: str) -> str:
    """O HD44780 nao tem acentuacao na ROM: converte para ASCII antes de escrever."""
    return to_ascii(text)
