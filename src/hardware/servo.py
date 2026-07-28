from __future__ import annotations

from dataclasses import dataclass

from .base import MockDevice

try:
    from gpiozero import AngularServo as GpioAngularServo
except Exception:  # pragma: no cover - fallback
    GpioAngularServo = None

@dataclass
class ServoController:
    """Controla um servomotor em graus."""
    pin: int
    min_angle: float = 0.0
    max_angle: float = 180.0
    mock: bool = False

    def __post_init__(self) -> None:
        if self.mock or GpioAngularServo is None:
            self._servo = MockDevice("SERVO")
            self._angle = self.min_angle
            return
        self._servo = GpioAngularServo(
            self.pin,
            min_angle=self.min_angle,
            max_angle=self.max_angle,
            min_pulse_width=0.0005,
            max_pulse_width=0.0025,
        )

    def set_angle(self, angle: float) -> None:
        angle = max(self.min_angle, min(self.max_angle, float(angle)))
        if isinstance(self._servo, MockDevice):
            self._angle = angle
            self._servo._log(f"angle={angle:.1f}")
            return
        self._servo.angle = angle

    def open(self, angle: float = 90.0) -> None:
        self.set_angle(angle)

    def close(self, angle: float = 0.0) -> None:
        self.set_angle(angle)

    def sweep(self, start: float = 0.0, stop: float = 180.0, step: float = 5.0, delay: float = 0.05) -> None:
        import time
        current = start
        while current <= stop:
            self.set_angle(current)
            time.sleep(delay)
            current += step

    def release(self) -> None:
        if isinstance(self._servo, MockDevice):
            self._servo._log("release")
            return
        self._servo.detach()
