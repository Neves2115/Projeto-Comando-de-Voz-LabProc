"""Exemplo 5 - Pipeline completo, sem microfone: texto -> intencao -> hardware.

Mostra o que o roteador faz com fala imperfeita, com negacao e com o modo ditado.
"""

import sys
from pathlib import Path

# Permite rodar os exemplos direto (python examples/01_led.py) mesmo sem
# ter feito `pip install -e .` ainda.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from centralvoz.app.controller import VoiceCommandController
from centralvoz.config import AppConfig
from centralvoz.hardware.factory import build_hardware
from centralvoz.storage.db import Storage

config = AppConfig(mock=True)

falas = [
    "ligar led",
    "liga a luz",              # variacao: o roteador tolera
    "nao ligar led",           # negacao: NAO deve acionar nada
    "abre o servo",
    "qual a distancia",
    "que horas sao",
    "transcrever",             # entra no modo ditado
    "lembrar de levar o relatorio impresso na sexta",
    "parar ditado",
    "ler recados",
    "faz um bolo de cenoura",  # desconhecido
]

with build_hardware(config) as hardware, Storage(config.db_path) as storage:
    controller = VoiceCommandController(config, hardware, storage)

    for fala in falas:
        match = controller.router.route(fala)
        reply = controller.handle_text(fala)
        print(
            f"{fala!r:<50} -> {match.intent.value:<16} "
            f"(conf {match.score:.2f})  {reply.message}"
        )
