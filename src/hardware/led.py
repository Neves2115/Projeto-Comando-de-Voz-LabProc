from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .base import MockDevice

try:
    from gpiozero import LED as GpioLED
except Exception:  # pragma: no cover - fallback
    GpioLED = None

@dataclass
class LedController:
    """Controla um ou mais LEDs discretos."""
    pins: tuple[int, ...]
    mock: bool = False

    def __post_init__(self) -> None:
        self._leds = []
        if self.mock or GpioLED is None:
            self._mock = MockDevice("LED")
            return
        for pin in self.pins:
            self._leds.append(GpioLED(pin))
        self._mock = None

    def on(self) -> None:
        if self._mock:
            self._mock._log("on")
            return
        for led in self._leds:
            led.on()

    def off(self) -> None:
        if self._mock:
            self._mock._log("off")
            return
        for led in self._leds:
            led.off()

    def toggle(self) -> None:
        if self._mock:
            self._mock._log("toggle")
            return
        for led in self._leds:
            led.toggle()

    def blink(self, on_time: float = 0.2, off_time: float = 0.2, n: int = 1) -> None:
        if self._mock:
            self._mock._log(f"blink on_time={on_time} off_time={off_time} n={n}")
            return
        for led in self._leds:
            led.blink(on_time=on_time, off_time=off_time, n=n)

    def close(self) -> None:
        self.off()
