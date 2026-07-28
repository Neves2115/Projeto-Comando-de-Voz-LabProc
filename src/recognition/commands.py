from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from ..utils import normalize_text

class Intent(str, Enum):
    LED_ON = "led_on"
    LED_OFF = "led_off"
    SERVO_OPEN = "servo_open"
    SERVO_CLOSE = "servo_close"
    READ_DISTANCE = "read_distance"
    ALERT_MODE = "alert_mode"
    CLEAR = "clear"
    RECORD = "record"
    UNKNOWN = "unknown"

@dataclass(frozen=True)
class Command:
    intent: Intent
    phrase: str

class CommandRouter:
    """Converte texto reconhecido em intenções do sistema."""
    def __init__(self) -> None:
        self._rules: list[tuple[Intent, tuple[str, ...]]] = [
            (Intent.LED_ON, ("ligar led", "acender led", "ligar luz")),
            (Intent.LED_OFF, ("desligar led", "apagar led", "apagar luz")),
            (Intent.SERVO_OPEN, ("abrir servo", "girar servo", "servo abrir")),
            (Intent.SERVO_CLOSE, ("fechar servo", "servo fechar", "voltar servo")),
            (Intent.READ_DISTANCE, ("mostrar distancia", "ler distancia", "ver distancia")),
            (Intent.ALERT_MODE, ("modo alerta", "ativar alerta", "entrar em alerta")),
            (Intent.CLEAR, ("limpar tela", "limpar display", "apagar display")),
            (Intent.RECORD, ("registrar comando", "salvar recado", "anotar texto")),
        ]

    def route(self, text: str) -> Command:
        normalized = normalize_text(text)
        for intent, phrases in self._rules:
            if any(normalize_text(phrase) in normalized for phrase in phrases):
                return Command(intent=intent, phrase=text)
        return Command(intent=Intent.UNKNOWN, phrase=text)
