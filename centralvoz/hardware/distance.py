"""Sensor ultrassonico HC-SR04.

ATENCAO ELETRICA: o pino ECHO entrega 5 V e o GPIO do Pi so aceita 3,3 V.
Use um divisor de tensao (ex.: 1 kOhm + 2 kOhm) entre ECHO e o GPIO.

POR QUE TODA LEITURA TEM TIMEOUT
=================================
O `DistanceSensor` do gpiozero mede o tempo entre o pulso no TRIGGER e a borda
de subida no ECHO. Se o ECHO nunca sobe -- fio solto, divisor de tensao mal
montado, sensor sem os 5 V, pino trocado -- a leitura simplesmente nao retorna.

Isso e pior do que parece: a chamada bloqueia a thread que a fez, e nem Ctrl+C
resolve. O tratador de SIGINT roda, imprime "Encerrando...", retorna, e a
chamada bloqueada continua bloqueada. O programa fica impossivel de fechar sem
`kill`.

Por isso nenhuma leitura aqui e feita direto: ela roda numa thread daemon e o
chamador espera com prazo. Estourou o prazo, devolve None e o handler mostra um
diagnostico util em vez de congelar a central.
"""

from __future__ import annotations

import logging
import random
import threading
from statistics import median

from .base import Peripheral

logger = logging.getLogger(__name__)

MAX_DISTANCE_M = 2.0

#: Uma medicao honesta do HC-SR04 leva menos de 60 ms (2 m ida e volta ~12 ms).
#: Um segundo e folga generosa; alem disso, algo esta errado na fiacao.
READ_TIMEOUT_S = 1.0

FIACAO_HINT = (
    "O sensor nao respondeu. Verifique:\n"
    "  - VCC do HC-SR04 nos 5 V (pino 2 ou 4), nao nos 3,3 V\n"
    "  - GND comum com o Pi\n"
    "  - TRIG no GPIO23 e ECHO no GPIO24 (conferir se nao estao trocados)\n"
    "  - divisor de tensao no ECHO (1k + 2k): sem ele o pino nao le direito\n"
    "Teste isolado:  voz say 'mostrar distancia' -v"
)


class DistanceTimeout(RuntimeError):
    """O sensor nao respondeu dentro do prazo."""


class DistanceSensor(Peripheral):
    name = "distancia"

    def __init__(self, trigger_pin: int, echo_pin: int) -> None:
        self.trigger_pin = trigger_pin
        self.echo_pin = echo_pin
        #: Fica True depois do primeiro timeout, para nao repetir a espera toda
        #: vez que o monitoramento roda.
        self.faulty = False

    # -- API ----------------------------------------------------------- #

    def read_cm(self, samples: int = 3) -> float | None:
        """Mediana de N leituras. None se o sensor nao respondeu.

        A mediana descarta os picos absurdos que o HC-SR04 produz quando o eco
        bate em quina ou superficie macia.
        """
        valores: list[float] = []
        for _ in range(max(1, samples)):
            valor = self._read_with_timeout()
            if valor is None:
                return None
            valores.append(valor)
        return round(median(valores), 1)

    def is_close(self, threshold_cm: float) -> bool:
        valor = self.read_cm()
        return valor is not None and valor <= threshold_cm

    # -- interno -------------------------------------------------------- #

    def _read_with_timeout(self) -> float | None:
        """Roda `_read_once` numa thread daemon e espera com prazo.

        A thread e daemon de proposito: se o gpiozero travar de vez, ela fica
        pendurada mas nao impede o programa de encerrar.
        """
        resultado: list[float] = []
        erro: list[BaseException] = []

        def alvo() -> None:
            try:
                resultado.append(self._read_once())
            except BaseException as exc:  # noqa: BLE001
                erro.append(exc)

        thread = threading.Thread(target=alvo, daemon=True, name="distance-read")
        thread.start()
        thread.join(timeout=READ_TIMEOUT_S)

        if thread.is_alive():
            if not self.faulty:
                logger.error(
                    "Leitura de distancia nao retornou em %.1f s.\n%s",
                    READ_TIMEOUT_S,
                    FIACAO_HINT,
                )
            self.faulty = True
            return None

        if erro:
            if not self.faulty:
                logger.error("Falha ao ler o sensor: %s\n%s", erro[0], FIACAO_HINT)
            self.faulty = True
            return None

        self.faulty = False
        return resultado[0] if resultado else None

    def _read_once(self) -> float:  # pragma: no cover - sobrescrito
        raise NotImplementedError

    def close(self) -> None:
        pass


class MockDistanceSensor(DistanceSensor):
    simulated = True

    def __init__(self, trigger_pin: int, echo_pin: int, value_cm: float = 42.0) -> None:
        super().__init__(trigger_pin, echo_pin)
        self.value_cm = value_cm
        #: Permite que os testes simulem um sensor que nao responde.
        self.simulate_timeout = False

    def set_value(self, value_cm: float) -> None:
        """Permite que os testes forcem um cenario de alerta."""
        self.value_cm = value_cm

    def _read_once(self) -> float:
        if self.simulate_timeout:
            threading.Event().wait()  # bloqueia para sempre, como o sensor real
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
            # queue_len=1 + partial=True: sem isso a PRIMEIRA leitura bloqueia
            # ate a fila interna encher com N medicoes. Com o ECHO mudo, isso
            # nunca acontece e a chamada nao volta.
            queue_len=1,
            partial=True,
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
