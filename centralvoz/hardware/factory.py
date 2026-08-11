"""Montagem do conjunto de perifericos.

Este e o unico lugar que decide real x simulado. Cada periferico degrada
sozinho: se o LCD nao responder no I2C, o resto do sistema continua de pe com
um `NullPeripheral` no lugar dele, e o log diz o porque. Isso segue a ordem de
integracao incremental do relatorio (LED -> servo -> LCD -> sensor -> voz).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..config import AppConfig
from ..gpio_setup import GpioUnavailable, import_gpiozero
from .base import NullPeripheral, Peripheral
from .distance import DistanceSensor, GpioDistanceSensor, MockDistanceSensor
from .lcd import I2cLcd, LcdDisplay, MockLcd
from .rgb import GpioRgbLed, MockRgbLed, RgbLed
from .matrix import LedMatrix, MockMatrix, ShiftRegisterMatrix
from .servo import GpioServo, MockServo, ServoController
from .trigger import GpioButton, KeyboardTrigger, Trigger

logger = logging.getLogger(__name__)


@dataclass
class HardwareSet:
    leds: RgbLed
    servo: ServoController
    lcd: LcdDisplay
    distance: DistanceSensor
    matrix: LedMatrix
    trigger: Trigger
    simulated: bool

    def all(self) -> list[Peripheral]:
        return [self.leds, self.servo, self.lcd, self.distance, self.matrix, self.trigger]

    def summary(self) -> str:
        return " | ".join(item.describe() for item in self.all())

    def close(self) -> None:
        for item in self.all():
            try:
                item.close()
            except Exception as exc:
                logger.warning("Erro ao fechar %s: %s", item.name, exc)

    def __enter__(self) -> "HardwareSet":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def build_hardware(config: AppConfig, *, minimal: bool = False) -> HardwareSet:
    """Monta os perifericos.

    `minimal=True` liga so o LCD (I2C) e o gatilho. E o modo usado pelo
    `voz hello`: como o LCD nao passa pelo gpiozero, esse caminho funciona
    mesmo com o backend de GPIO quebrado.
    """
    if config.mock:
        logger.info("Modo simulado: nenhum pino GPIO sera tocado.")
        return _build_mock(config)

    if minimal:
        return _build_minimal(config)

    try:
        gpiozero = import_gpiozero(config.pin_factory)
    except GpioUnavailable as exc:
        # Erro claro e fatal, em vez de virar mock sem avisar.
        raise SystemExit(f"\n[ERRO DE HARDWARE]\n{exc}\n") from exc

    return _build_real(config, gpiozero)


# --------------------------------------------------------------------------- #


def _build_mock(config: AppConfig) -> HardwareSet:
    pins = config.pins
    return HardwareSet(
        leds=MockRgbLed(pins.rgb_red, pins.rgb_green, pins.rgb_blue),
        servo=MockServo(pins.servo),
        lcd=MockLcd(
            cols=config.lcd.cols,
            rows=config.lcd.rows,
            page_delay_s=config.lcd.page_delay_s,
        ),
        distance=MockDistanceSensor(pins.distance_trigger, pins.distance_echo),
        matrix=MockMatrix(),
        trigger=KeyboardTrigger(),
        simulated=True,
    )


def _build_lcd(config: AppConfig) -> LcdDisplay:
    """Só o LCD. Não depende de gpiozero nem de pin factory."""
    if not config.lcd.enabled:
        return MockLcd(cols=config.lcd.cols, rows=config.lcd.rows)
    return _safe(
        "lcd",
        lambda: I2cLcd(
            bus_number=config.lcd.i2c_bus,
            address=config.lcd.address,
            cols=config.lcd.cols,
            rows=config.lcd.rows,
            page_delay_s=config.lcd.page_delay_s,
            backlight=config.lcd.backlight,
        ),
        fallback=lambda: MockLcd(cols=config.lcd.cols, rows=config.lcd.rows),
    )


def _build_trigger(config: AppConfig) -> Trigger:
    """Botao fisico ou teclado, conforme `trigger` na configuracao.

    Importante: um `Button` do gpiozero e criado com sucesso mesmo sem nada
    ligado no pino -- ele so nunca dispara. Por isso o padrao para quem ainda
    nao ligou o botao deve ser "keyboard", e nao "descobrir na marra".
    """
    if config.trigger == "keyboard":
        logger.info("Gatilho: teclado (ENTER). Nenhum GPIO usado.")
        return KeyboardTrigger()

    try:
        gpiozero = import_gpiozero(config.pin_factory)
        return GpioButton(config.pins.button, gpiozero)
    except Exception as exc:
        logger.error(
            "Botao no GPIO%s indisponivel (%s). Caindo para o teclado (ENTER).",
            config.pins.button,
            exc,
        )
        return KeyboardTrigger()


def _build_minimal(config: AppConfig) -> HardwareSet:
    """Só LCD + gatilho. Usado pelo `voz hello`."""
    return HardwareSet(
        leds=NullPeripheral("rgb", "nao usado no modo minimo"),          # type: ignore[arg-type]
        servo=NullPeripheral("servo", "nao usado no modo minimo"),       # type: ignore[arg-type]
        lcd=_build_lcd(config),
        distance=NullPeripheral("distancia", "nao usado no modo minimo"),  # type: ignore[arg-type]
        matrix=NullPeripheral("matriz", "nao usada no modo minimo"),     # type: ignore[arg-type]
        trigger=_build_trigger(config),
        simulated=False,
    )


def _build_real(config: AppConfig, gpiozero) -> HardwareSet:
    pins = config.pins

    leds = _safe(
        "rgb",
        lambda: GpioRgbLed(
            pins.rgb_red,
            pins.rgb_green,
            pins.rgb_blue,
            gpiozero,
            active_high=pins.rgb_active_high,
        ),
        fallback=lambda: MockRgbLed(pins.rgb_red, pins.rgb_green, pins.rgb_blue),
    )
    servo = _safe(
        "servo",
        lambda: GpioServo(pins.servo, gpiozero),
        fallback=lambda: MockServo(pins.servo),
    )
    distance = _safe(
        "distancia",
        lambda: GpioDistanceSensor(pins.distance_trigger, pins.distance_echo, gpiozero),
        fallback=lambda: MockDistanceSensor(pins.distance_trigger, pins.distance_echo),
    )
    trigger = (
        KeyboardTrigger()
        if config.trigger == "keyboard"
        else _safe(
            "gatilho",
            lambda: GpioButton(pins.button, gpiozero),
            fallback=KeyboardTrigger,
        )
    )

    lcd = _build_lcd(config)

    if config.matrix.enabled:
        matrix = _safe(
            "matriz",
            lambda: ShiftRegisterMatrix(
                pins.matrix_data,
                pins.matrix_clock,
                pins.matrix_latch,
                gpiozero,
                refresh_hz=config.matrix.refresh_hz,
            ),
            fallback=MockMatrix,
        )
    else:
        matrix = NullPeripheral("matriz", "desativada em config.toml")  # type: ignore[assignment]

    return HardwareSet(
        leds=leds,
        servo=servo,
        lcd=lcd,
        distance=distance,
        matrix=matrix,
        trigger=trigger,
        simulated=False,
    )


def _safe(label: str, build, fallback):
    """Tenta o periferico real; se falhar, avisa alto e usa o substituto."""
    try:
        return build()
    except Exception as exc:
        logger.error(
            "Nao consegui inicializar '%s' (%s). Seguindo em modo simulado SO para "
            "este periferico.",
            label,
            exc,
        )
        return fallback()
