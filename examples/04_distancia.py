"""Exemplo 4 - Sensor ultrassonico com alerta."""

import sys
from pathlib import Path

# Permite rodar os exemplos direto (python examples/01_led.py) mesmo sem
# ter feito `pip install -e .` ainda.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import time

from centralvoz.config import AppConfig
from centralvoz.hardware.factory import build_hardware

config = AppConfig(mock=True)

with build_hardware(config) as hardware:
    for _ in range(10):
        cm = hardware.distance.read_cm()
        perto = cm <= config.behavior.distance_warning_cm
        print(f"{cm:6.1f} cm  {'<-- PERTO' if perto else ''}")
        hardware.lcd.show_lines("Distancia", f"{cm:.1f} cm")
        hardware.leds.on() if perto else hardware.leds.off()
        time.sleep(0.5)
