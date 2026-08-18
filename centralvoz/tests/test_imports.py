"""Cada modulo tem que importar sozinho, em qualquer ordem.

Regressao: `commands.handlers` importava `app.tasks`, e `app/__init__` importava
`controller`, que importava `commands.handlers` -- ciclo. A suite nao pegava
porque os outros testes sempre importavam `app.controller` primeiro, que e a
ordem que funciona por acaso.
"""

import importlib
import subprocess
import sys

import pytest

MODULOS = [
    "centralvoz",
    "centralvoz.cli",
    "centralvoz.config",
    "centralvoz.doctor",
    "centralvoz.gpio_setup",
    "centralvoz.logging_setup",
    "centralvoz.tasks",
    "centralvoz.utils",
    "centralvoz.app",
    "centralvoz.app.controller",
    "centralvoz.app.runner",
    "centralvoz.audio",
    "centralvoz.commands",
    "centralvoz.commands.handlers",
    "centralvoz.commands.intents",
    "centralvoz.commands.numbers",
    "centralvoz.commands.router",
    "centralvoz.hardware",
    "centralvoz.hardware.factory",
    "centralvoz.hardware.rgb",
    "centralvoz.speech",
    "centralvoz.storage",
]


@pytest.mark.parametrize("modulo", MODULOS)
def test_importa_isolado(modulo: str) -> None:
    """Num interpretador novo, sem nenhum outro import antes."""
    resultado = subprocess.run(
        [sys.executable, "-c", f"import {modulo}"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert resultado.returncode == 0, resultado.stderr


def test_todos_os_handlers_estao_registrados() -> None:
    """Toda intencao precisa de handler, senao cai em UNKNOWN silenciosamente."""
    from centralvoz.commands.handlers import HANDLERS
    from centralvoz.commands.intents import Intent

    faltando = [i.value for i in Intent if i not in HANDLERS]
    assert not faltando, f"Intencoes sem handler: {faltando}"


def test_toda_intencao_tem_pelo_menos_uma_frase() -> None:
    from centralvoz.commands.intents import Intent
    from centralvoz.commands.router import CommandRouter

    router = CommandRouter()
    com_frase = {rule.intent for rule in router.rules}
    faltando = [
        i.value for i in Intent if i is not Intent.UNKNOWN and i not in com_frase
    ]
    assert not faltando, f"Intencoes sem frase: {faltando}"


def test_config_exemplo_e_valido(tmp_path) -> None:
    """Regressao: o config.example.toml ficou desatualizado apos trocar os pinos."""
    import shutil
    from pathlib import Path

    from centralvoz.config import AppConfig

    destino = tmp_path / "config.toml"
    shutil.copy(Path("config.example.toml"), destino)
    AppConfig.load(destino)  # levanta ValueError se houver chave invalida


def test_pinos_nao_conflitam() -> None:
    """Dois perifericos no mesmo GPIO e curto-circuito logico garantido."""
    from centralvoz.config import PinConfig

    pinos = PinConfig()
    usados = [
        pinos.rgb_red, pinos.rgb_green, pinos.rgb_blue,
        pinos.servo, pinos.button,
        pinos.distance_trigger, pinos.distance_echo,
        pinos.matrix_data, pinos.matrix_clock, pinos.matrix_latch,
    ]
    duplicados = {p for p in usados if usados.count(p) > 1}
    assert not duplicados, f"Pinos repetidos na configuracao padrao: {duplicados}"

    # GPIO2/GPIO3 sao exclusivos do I2C (LCD).
    assert 2 not in usados and 3 not in usados
