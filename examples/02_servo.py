"""Exemplo 2 - Servo."""

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
    for angulo in (0, 45, 90, 135, 180, 90):
        print(f"servo -> {angulo} graus")
        hardware.servo.move_to(angulo)
        time.sleep(0.4)
    hardware.servo.release()  # sem isso o servo fica zumbindo e esquenta
