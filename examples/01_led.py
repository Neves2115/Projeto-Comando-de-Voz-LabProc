"""Exemplo 1 - LED RGB. Rode com: python examples/01_led.py"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from centralvoz.config import AppConfig
from centralvoz.hardware.factory import build_hardware
from centralvoz.hardware.rgb import COLORS

# Troque para mock=False depois de conferir a fiacao (e o `voz doctor`).
config = AppConfig(mock=True)

with build_hardware(config) as hardware:
    for nome in ("vermelho", "verde", "azul", "amarelo", "ciano", "magenta", "branco"):
        print(f"{nome:10} rgb{COLORS[nome]}")
        hardware.leds.set_named(nome)
        time.sleep(0.6)

    print("piscando...")
    hardware.leds.blink(times=3, color="laranja")

    print("brilho em 30%")
    hardware.leds.set_named("verde")
    hardware.leds.brightness(0.3)
    time.sleep(1)

    hardware.leds.off()
