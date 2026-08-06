"""Sensor ultrassonico HC-SR04.

ATENCAO ELETRICA: o pino ECHO entrega 5 V e o GPIO do Pi so aceita 3,3 V.
Use um divisor de tensao (ex.: 1 kOhm + 2 kOhm) entre ECHO e o GPIO.
"""

from __future__ import annotations

import random
from statistics import median

from .base import Peripheral

MAX_DISTANCE_M = 2.0


class DistanceSensor(Peripheral):
    name = "distancia"

    def __init__(self, trigger_pin: int, echo_pin: int) -> None:
        self.trigger_pin = trigger_pin
        self.echo_pin = echo_pin

    def read_cm(self, samples: int = 3) -> float:
        """Mediana de N leituras: descarta os picos absurdos do HC-SR04."""
        values = [self._read_once() for _ in range(max(1, samples))]
        return round(median(values), 1)

    def is_close(self, threshold_cm: float) -> bool:
        return self.read_cm() <= threshold_cm

    def _read_once(self) -> float:  # pragma: no cover - sobrescrito
        raise NotImplementedError

    def close(self) -> None:
        pass


class MockDistanceSensor(DistanceSensor):
    simulated = True

    def __init__(self, trigger_pin: int, echo_pin: int, value_cm: float = 42.0) -> None:
        super().__init__(trigger_pin, echo_pin)
        self.value_cm = value_cm

    def set_value(self, value_cm: float) -> None:
        """Permite que os testes forcem um cenario de alerta."""
        self.value_cm = value_cm

    def _read_once(self) -> float:
        # Um pouco de ruido deixa a simulacao mais parecida com o sensor real.
        return max(2.0, self.value_cm + random.uniform(-0.6, 0.6))


class GpioDistanceSensor(DistanceSensor):
    simulated = False

    def __init__(self, trigger_pin: int, echo_pin: int, gpiozero_module) -> None:
        super().__init__(trigger_pin, echo_pin)
        self._device = gpiozero_module.DistanceSensor(
            echo=echo_pin,
            trigger=trigger_pin,
            max_distance=MAX_DISTANCE_M,
            queue_len=5,
        )
        self._log("trigger=%s echo=%s", trigger_pin, echo_pin)

    def _read_once(self) -> float:
        # gpiozero devolve metros.
        return float(self._device.distance) * 100.0

    def close(self) -> None:
        try:
            self._device.close()
        except Exception:  # noqa: BLE001
            pass
