from __future__ import annotations

from dataclasses import dataclass

from .base import MockDevice

try:
    from gpiozero import DistanceSensor as GpioDistanceSensor
except Exception:  # pragma: no cover - fallback
    GpioDistanceSensor = None

@dataclass
class DistanceSensorReader:
    """Lê sensor ultrassônico de distância."""
    echo_pin: int
    trigger_pin: int
    mock: bool = False

    def __post_init__(self) -> None:
        if self.mock or GpioDistanceSensor is None:
            self._sensor = MockDevice("DISTANCE")
            self._distance_cm = 42.0
            return
        self._sensor = GpioDistanceSensor(
            echo=self.echo_pin,
            trigger=self.trigger_pin,
            max_distance=2.0,
            queue_len=3,
        )

    def read_cm(self) -> float:
        if isinstance(self._sensor, MockDevice):
            self._sensor._log(f"read_cm -> {self._distance_cm:.1f}")
            return float(self._distance_cm)
        # gpiozero retorna distância normalizada em metros
        return float(self._sensor.distance * 100.0)

    def is_close(self, threshold_cm: float) -> bool:
        return self.read_cm() <= threshold_cm
