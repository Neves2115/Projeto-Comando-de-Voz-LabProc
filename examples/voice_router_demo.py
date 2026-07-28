from central_voz_freenove.app.controller import VoiceCommandController
from central_voz_freenove.config import AppConfig
from central_voz_freenove.hardware import LedController, ServoController, LcdDisplay, DistanceSensorReader, LedMatrixController

config = AppConfig(use_mock_hardware=True)
controller = VoiceCommandController(
    config=config,
    leds=LedController((17,), mock=True),
    servo=ServoController(pin=18, mock=True),
    lcd=LcdDisplay(mock=True),
    distance=DistanceSensorReader(echo_pin=23, trigger_pin=24, mock=True),
    matrix=LedMatrixController(mock=True),
)

for cmd in ["ligar led", "abrir servo", "mostrar distancia", "modo alerta", "desligar led"]:
    print(cmd, "->", controller.handle_text(cmd))
