"""Deteccao de plataforma e escolha da *pin factory* do gpiozero.

Este modulo existe por causa de um erro concreto e muito comum:

    PinFactoryFallback: Falling back from lgpio: No module named 'lgpio'
    PinPWMUnsupported: PWM is not supported on pin GPIO18

O gpiozero 2.x tenta as fabricas nesta ordem: lgpio -> RPi.GPIO -> pigpio -> native.
Se nenhuma das tres primeiras estiver instalada ele cai na `native`, que so faz
GPIO digital. Ai o LED ate acende, mas o servo (que precisa de PWM) explode.

Em vez de deixar isso acontecer silenciosamente, aqui a gente checa antes e
falha com uma mensagem que diz exatamente o que instalar.
"""

from __future__ import annotations

import importlib.util
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Ordem de preferencia. lgpio primeiro porque funciona no Raspberry Pi OS
# Bookworm/Trixie sem daemon nenhum. pigpio da PWM com timing de hardware
# (servo sem tremer), mas exige `pigpiod` rodando.
FACTORY_MODULES = {
    "lgpio": "lgpio",
    "pigpio": "pigpio",
    "rpigpio": "RPi.GPIO",
    "native": None,  # sempre "disponivel", mas nao faz PWM
}
PREFERRED_ORDER = ("lgpio", "pigpio", "rpigpio")

INSTALL_HINT = """\
Nenhum backend de GPIO com suporte a PWM foi encontrado.

No Raspberry Pi OS (Bookworm/Trixie), instale o lgpio:

    sudo apt update && sudo apt install -y python3-lgpio

Se voce usa um ambiente virtual, o pacote do apt NAO e enxergado por ele.
Recrie o venv com acesso aos pacotes do sistema:

    python3 -m venv --system-site-packages .venv

ou instale pelo pip dentro do venv:

    pip install lgpio

Alternativa com PWM de hardware (servo mais estavel):

    sudo apt install -y pigpio python3-pigpio
    sudo systemctl enable --now pigpiod
    export CENTRALVOZ_PIN_FACTORY=pigpio

Para so testar a logica sem hardware nenhum, rode com --mock.
"""


class GpioUnavailable(RuntimeError):
    """Nao da para falar com o GPIO real neste ambiente."""


@dataclass(frozen=True)
class PlatformInfo:
    is_raspberry_pi: bool
    model: str | None
    available_factories: tuple[str, ...]

    @property
    def has_pwm_backend(self) -> bool:
        return any(name in self.available_factories for name in PREFERRED_ORDER)


def _module_installed(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def read_pi_model() -> str | None:
    """Le o modelo da placa. Retorna None fora de um Raspberry Pi."""
    device_tree = Path("/proc/device-tree/model")
    if device_tree.is_file():
        try:
            return device_tree.read_bytes().decode("utf-8", "ignore").strip("\x00 \n")
        except OSError:
            pass

    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        try:
            for line in cpuinfo.read_text(errors="ignore").splitlines():
                if line.lower().startswith("model") and "raspberry" in line.lower():
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass
    return None


def inspect_platform() -> PlatformInfo:
    model = read_pi_model()
    available = tuple(
        name
        for name, module in FACTORY_MODULES.items()
        if module is None or _module_installed(module)
    )
    return PlatformInfo(
        is_raspberry_pi=bool(model and "raspberry" in model.lower()),
        model=model,
        available_factories=available,
    )


def configure_pin_factory(preferred: str | None = None) -> str:
    """Define GPIOZERO_PIN_FACTORY *antes* do gpiozero criar a fabrica padrao.

    Retorna o nome da fabrica escolhida. Levanta GpioUnavailable com instrucoes
    se nao houver backend com PWM.
    """
    info = inspect_platform()

    if not info.is_raspberry_pi:
        raise GpioUnavailable(
            "Este sistema nao parece ser um Raspberry Pi "
            f"(modelo detectado: {info.model or 'desconhecido'}). "
            "Use --mock para rodar em modo simulado."
        )

    if preferred:
        if preferred not in FACTORY_MODULES:
            raise GpioUnavailable(f"Pin factory desconhecida: {preferred!r}")
        if preferred not in info.available_factories:
            raise GpioUnavailable(
                f"A pin factory {preferred!r} foi pedida mas o modulo "
                f"{FACTORY_MODULES[preferred]!r} nao esta instalado.\n\n{INSTALL_HINT}"
            )
        chosen = preferred
    else:
        chosen = next(
            (name for name in PREFERRED_ORDER if name in info.available_factories),
            "",
        )
        if not chosen:
            raise GpioUnavailable(INSTALL_HINT)

    os.environ["GPIOZERO_PIN_FACTORY"] = chosen
    logger.info("Pin factory do gpiozero: %s (%s)", chosen, info.model)
    return chosen


def import_gpiozero(preferred: str | None = None):
    """Configura a fabrica e devolve o modulo gpiozero ja pronto."""
    configure_pin_factory(preferred)
    try:
        import gpiozero  # noqa: PLC0415  (import tardio e proposital)
    except ImportError as exc:  # pragma: no cover
        raise GpioUnavailable(
            "gpiozero nao esta instalado. Rode: pip install 'centralvoz[pi]'"
        ) from exc
    return gpiozero
