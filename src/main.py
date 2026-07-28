from __future__ import annotations

from pathlib import Path

from .config import AppConfig
from .hardware import LedController, ServoController, LcdDisplay, DistanceSensorReader, LedMatrixController
from .app.controller import VoiceCommandController

def build_demo_controller(use_mock: bool = True) -> VoiceCommandController:
    config = AppConfig(use_mock_hardware=use_mock)
    leds = LedController((17,), mock=use_mock)
    servo = ServoController(pin=18, mock=use_mock)
    lcd = LcdDisplay(cols=config.lcd_cols, lines=config.lcd_lines, mock=use_mock)
    distance = DistanceSensorReader(echo_pin=23, trigger_pin=24, mock=use_mock)
    matrix = LedMatrixController(mock=use_mock)
    return VoiceCommandController(
        config=config,
        leds=leds,
        servo=servo,
        lcd=lcd,
        distance=distance,
        matrix=matrix,
    )

def main() -> None:
    controller = build_demo_controller(use_mock=True)
    print("Digite um comando em português. Ex.: ligar led, abrir servo, mostrar distancia, modo alerta")
    print("Digite 'sair' para encerrar.")
    while True:
        text = input("> ").strip()
        if text.lower() in {"sair", "exit", "quit"}:
            break
        result = controller.handle_text(text)
        print(result)

if __name__ == "__main__":
    main()
