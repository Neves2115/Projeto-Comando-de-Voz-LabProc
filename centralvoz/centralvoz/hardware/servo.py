"""Servomotor angular (SG90 / MG90S do kit)."""

from __future__ import annotations

import threading
import time

from .base import Peripheral

# Larguras de pulso do SG90. Os defaults do gpiozero (1ms..2ms) nao cobrem
# os 180 graus completos deste servo.
MIN_PULSE_S = 0.0005
MAX_PULSE_S = 0.0025


class ServoController(Peripheral):
    name = "servo"

    def __init__(self, pin: int, min_angle: float = 0.0, max_angle: float = 180.0) -> None:
        self.pin = pin
        self.min_angle = min_angle
        self.max_angle = max_angle
        self._angle = min_angle

    @property
    def angle(self) -> float:
        return self._angle

    def set_angle(self, angle: float) -> None:
        angle = max(self.min_angle, min(self.max_angle, float(angle)))
        self._angle = angle
        self._apply(angle)

    def move_to(self, angle: float) -> float:
        self.set_angle(angle)
        return self._angle

    def sweep(
        self,
        start: float = 0.0,
        stop: float = 180.0,
        step: float = 10.0,
        delay: float = 0.06,
    ) -> None:
        angle = start
        direction = 1 if stop >= start else -1
        while (angle - stop) * direction <= 0:
            self.set_angle(angle)
            time.sleep(delay)
            angle += step * direction
        self.set_angle(stop)

    def sweep_async(self, **kwargs: float) -> None:
        threading.Thread(target=self.sweep, kwargs=kwargs, daemon=True).start()

    def release(self) -> None:
        """Para de enviar pulso. Sem isso o servo fica zumbindo e esquenta."""
        self._release()

    def _apply(self, angle: float) -> None:  # pragma: no cover - sobrescrito
        raise NotImplementedError

    def _release(self) -> None:
        pass

    def close(self) -> None:
        self.release()


class MockServo(ServoController):
    simulated = True

    def _apply(self, angle: float) -> None:
        self._log("pino %s -> %.1f graus", self.pin, angle)

    def _release(self) -> None:
        self._log("release (pulso desligado)")


class GpioServo(ServoController):
    simulated = False

    #: Segundos ate soltar o servo sozinho depois de um movimento.
    AUTO_RELEASE_S = 0.8

    def __init__(self, pin: int, gpiozero_module, **kwargs: float) -> None:
        super().__init__(pin, **kwargs)
        self._device = gpiozero_module.AngularServo(
            pin,
            min_angle=self.min_angle,
            max_angle=self.max_angle,
            min_pulse_width=MIN_PULSE_S,
            max_pulse_width=MAX_PULSE_S,
        )
        self._timer: threading.Timer | None = None
        self._log_setup("inicializado no pino %s", pin)

    def _apply(self, angle: float) -> None:
        self._device.angle = angle
        self._schedule_release()

    def _schedule_release(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(self.AUTO_RELEASE_S, self._release)
        self._timer.daemon = True
        self._timer.start()

    def _release(self) -> None:
        try:
            self._device.detach()
        except Exception:
            pass

    def close(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        try:
            self._device.detach()
            self._device.close()
        except Exception:
            pass
