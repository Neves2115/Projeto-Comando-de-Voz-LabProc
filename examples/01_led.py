"""Exemplo 1 - LED. Rode com: python examples/01_led.py"""

import sys
from pathlib import Path

# Permite rodar os exemplos direto (python examples/01_led.py) mesmo sem
# ter feito `pip install -e .` ainda.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from centralvoz.config import AppConfig
from centralvoz.hardware.factory import build_hardware

# Troque para mock=False depois de conferir a fiacao (e o `voz doctor`).
config = AppConfig(mock=True)

with build_hardware(config) as hardware:
    hardware.leds.on()
    hardware.leds.blink(times=3)
    hardware.leds.off()
