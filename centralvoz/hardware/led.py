"""LEDs discretos."""

from __future__ import annotations

import threading
import time
from typing import Sequence

from .base import Peripheral


class LedController(Peripheral):
    """Interface comum. Use `MockLeds` ou `GpioLeds`."""

    name = "led"

    def __init__(self, pins: Sequence[int]) -> None:
        self.pins = tuple(pins)
        self._state = False

    @property
    def is_on(self) -> bool:
        return self._state

    def on(self) -> None:
        self._state = True
        self._apply(True)

    def off(self) -> None:
        self._state = False
        self._apply(False)

    def toggle(self) -> None:
        self.off() if self._state else self.on()

    def blink(self, on_time: float = 0.15, off_time: float = 0.15, times: int = 3) -> None:
        """Pisca de forma sincrona (bloqueia). Use `blink_async` no loop principal."""
        for _ in range(max(1, times)):
            self._apply(True)
            time.sleep(on_time)
            self._apply(False)
            time.sleep(off_time)
        self._apply(self._state)

    def blink_async(self, on_time: float = 0.15, off_time: float = 0.15, times: int = 3) -> None:
        threading.Thread(
            target=self.blink, args=(on_time, off_time, times), daemon=True
        ).start()

    def _apply(self, value: bool) -> None:  # pragma: no cover - sobrescrito
        raise NotImplementedError

    def close(self) -> None:
        self.off()


class MockLeds(LedController):
    simulated = True

    def _apply(self, value: bool) -> None:
        self._log("pinos %s -> %s", self.pins, "ACESO" if value else "apagado")


class GpioLeds(LedController):
    simulated = False

    def __init__(self, pins: Sequence[int], gpiozero_module) -> None:
        super().__init__(pins)
        self._devices = [gpiozero_module.LED(pin) for pin in self.pins]
        self._log("inicializado nos pinos %s", self.pins)

    def _apply(self, value: bool) -> None:
        for device in self._devices:
            device.on() if value else device.off()

    def close(self) -> None:
        for device in self._devices:
            try:
                device.off()
                device.close()
            except Exception:  # noqa: BLE001 - cleanup nunca deve derrubar o programa
                pass
        self._devices.clear()
