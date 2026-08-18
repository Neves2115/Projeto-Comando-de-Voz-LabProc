"""Base comum dos perifericos.

Decisao de design importante: o backend (real ou simulado) e escolhido *uma vez*,
por quem constroi o objeto, e sempre registrado no log. O codigo antigo fazia
`if self.mock or GpioLED is None:` dentro de cada classe, o que transformava
"gpiozero quebrou" em "modo simulado" silenciosamente. Isso e a pior falha
possivel num projeto de hardware: voce acha que esta acionando o pino e nao esta.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class Peripheral(ABC):
    """Um dispositivo fisico (ou sua simulacao)."""

    #: Nome curto usado nos logs.
    name: str = "device"

    #: True quando o objeto fala com hardware de verdade.
    simulated: bool = True

    def describe(self) -> str:
        return f"{self.name} [{'simulado' if self.simulated else 'real'}]"

    def _log(self, message: str, *args: object) -> None:
        """Detalhe de periferico: DEBUG, nao INFO.

        Antes cada acionamento de LED, servo e matriz virava uma linha no
        terminal -- e o desenho da matriz saia como oito linhas de '#' a cada
        icone. Quem quiser ver isso usa `voz run -v`.
        """
        prefix = "SIM" if self.simulated else "HW "
        logger.debug("%s %-9s " + message, prefix, self.name, *args)

    def _log_setup(self, message: str, *args: object) -> None:
        """Inicializacao de periferico: essa vale INFO, acontece uma vez so."""
        prefix = "SIM" if self.simulated else "HW "
        logger.info("%s %-9s " + message, prefix, self.name, *args)

    @abstractmethod
    def close(self) -> None:
        """Libera o recurso. Deve poder ser chamado mais de uma vez."""


class NullPeripheral(Peripheral):
    """Perifero ausente ou desligado na configuracao. Absorve chamadas."""

    simulated = True

    def __init__(self, name: str, reason: str = "desativado") -> None:
        self.name = name
        self.reason = reason

    def close(self) -> None:  # pragma: no cover - trivial
        pass

    #: Atributos que devem responder com um VALOR, nao com uma funcao.
    #: Sem isso, `if hardware.leds.is_on:` seria sempre verdadeiro (uma funcao
    #: e truthy), e handlers tomariam decisoes erradas quando o periferico
    #: estivesse ausente.
    _VALUE_ATTRS = {
        "is_on": False,
        "simulated": True,
        "color": (0.0, 0.0, 0.0),
        "color_name": "preto",
        "angle": 0.0,
        "prompt": "indisponivel",
    }

    def __getattr__(self, item: str):
        if item in self._VALUE_ATTRS:
            return self._VALUE_ATTRS[item]

        def _noop(*_args: object, **_kwargs: object) -> None:
            logger.debug("%s ausente (%s): ignorando %s()", self.name, self.reason, item)

        return _noop
