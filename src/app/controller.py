from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..config import AppConfig
from ..hardware import LedController, ServoController, LcdDisplay, DistanceSensorReader, LedMatrixController
from ..recognition.commands import CommandRouter, Intent

@dataclass
class VoiceCommandController:
    """Orquestra comando de voz + hardware."""
    config: AppConfig
    leds: LedController
    servo: ServoController
    lcd: LcdDisplay
    distance: DistanceSensorReader
    matrix: LedMatrixController

    def __post_init__(self) -> None:
        self.router = CommandRouter()

    def handle_text(self, text: str) -> str:
        command = self.router.route(text)

        if command.intent == Intent.LED_ON:
            self.leds.on()
            self.matrix.show_icon("ok")
            self.lcd.show_message("LED ligado", text[:16])
            return "LED ligado"

        if command.intent == Intent.LED_OFF:
            self.leds.off()
            self.matrix.clear()
            self.lcd.show_message("LED desligado", text[:16])
            return "LED desligado"

        if command.intent == Intent.SERVO_OPEN:
            self.servo.open(self.config.servo_open_angle)
            self.lcd.show_message("Servo aberto", text[:16])
            self.matrix.show_icon("ok")
            return f"Servo aberto em {self.config.servo_open_angle:.0f} graus"

        if command.intent == Intent.SERVO_CLOSE:
            self.servo.close(self.config.servo_closed_angle)
            self.lcd.show_message("Servo fechado", text[:16])
            self.matrix.show_icon("ok")
            return f"Servo fechado em {self.config.servo_closed_angle:.0f} graus"

        if command.intent == Intent.READ_DISTANCE:
            dist = self.distance.read_cm()
            self.lcd.show_message("Distancia", f"{dist:.1f} cm")
            self.matrix.show_icon("ok")
            return f"Distancia atual: {dist:.1f} cm"

        if command.intent == Intent.ALERT_MODE:
            close = self.distance.is_close(self.config.distance_warning_cm)
            if close:
                self.leds.blink(on_time=0.1, off_time=0.1, n=3)
                self.matrix.show_icon("alerta")
                self.servo.open(self.config.servo_open_angle)
                msg = "Alerta: objeto perto"
            else:
                self.matrix.show_icon("ok")
                self.leds.on()
                msg = "Sem alerta"
            self.lcd.show_message("Modo alerta", msg[:16])
            return msg

        if command.intent == Intent.CLEAR:
            self.leds.off()
            self.matrix.clear()
            self.lcd.clear()
            return "Tela limpa"

        if command.intent == Intent.RECORD:
            self.lcd.show_message("Registro", text[:16])
            return "Comando registrado"

        self.lcd.show_message("Nao entendi", text[:16])
        self.matrix.show_icon("alerta")
        return "Comando desconhecido"
