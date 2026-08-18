"""Exemplo 3 - LCD 16x2 I2C, incluindo texto que nao cabe no display."""

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
    hardware.lcd.show_lines("Central de Voz", "pronto")
    time.sleep(2)

    # Texto longo pagina sozinho, em segundo plano.
    hardware.lcd.show_text(
        "Esta frase e bem maior que dezesseis colunas e por isso "
        "o display vai passar as paginas sozinho."
    )
    time.sleep(8)
    hardware.lcd.clear()
