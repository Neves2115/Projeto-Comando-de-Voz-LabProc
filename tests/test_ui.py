"""Testes da interface Jarvis.

Nao abrem terminal de verdade: exercitam a logica de navegacao, o estado
compartilhado e o gatilho. O desenho em si e coberto pelo teste de tamanhos
minimos, que garante que nenhuma coordenada estoura.
"""

from __future__ import annotations

import logging
import threading

import pytest

from centralvoz.commands.intents import Intent
from centralvoz.ui.tui import GROUPS, JarvisUi, UiLogHandler, UiState


class _TriggerFalso:
    def __init__(self) -> None:
        self.toques = 0

    def toggle(self) -> None:
        self.toques += 1


@pytest.fixture
def ui() -> JarvisUi:
    return JarvisUi(UiState(), _TriggerFalso(), lambda: None)


# --------------------------------------------------------------------------- #
# Estado
# --------------------------------------------------------------------------- #


def test_estado_e_seguro_entre_threads() -> None:
    estado = UiState()

    def escrever() -> None:
        for i in range(200):
            estado.log(f"evento {i}")
            estado.set_status("ouvindo")

    threads = [threading.Thread(target=escrever) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert estado.snapshot()["status"] == "ouvindo"
    # O deque tem limite: nao pode crescer sem parar numa sessao longa.
    assert len(estado.snapshot()["events"]) <= 200


def test_handler_de_log_so_captura_avisos() -> None:
    estado = UiState()
    handler = UiLogHandler(estado)
    logger = logging.getLogger("teste_ui")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    try:
        logger.debug("detalhe irrelevante")
        logger.info("informacao comum")
        logger.warning("isso o usuario precisa ver")
        logger.error("isso tambem")
    finally:
        logger.removeHandler(handler)

    eventos = estado.snapshot()["events"]
    textos = [texto for _, texto, _ in eventos]
    tipos = [tipo for _, _, tipo in eventos]

    assert "detalhe irrelevante" not in textos
    assert "informacao comum" not in textos
    assert "isso o usuario precisa ver" in textos
    assert "aviso" in tipos and "erro" in tipos


# --------------------------------------------------------------------------- #
# Navegacao
# --------------------------------------------------------------------------- #


def test_navegacao_entre_grupos_da_a_volta(ui: JarvisUi) -> None:
    import curses

    assert ui.grupo == 0
    for _ in range(len(GROUPS)):
        ui.handle_key(curses.KEY_DOWN)
    assert ui.grupo == 0  # deu a volta completa

    ui.handle_key(curses.KEY_UP)
    assert ui.grupo == len(GROUPS) - 1


def test_tab_alterna_o_foco(ui: JarvisUi) -> None:
    assert ui.foco == "grupos"
    ui.handle_key(ord("\t"))
    assert ui.foco == "comandos"
    ui.handle_key(ord("\t"))
    assert ui.foco == "grupos"


def test_enter_aciona_o_gatilho(ui: JarvisUi) -> None:
    ui.handle_key(10)
    assert ui.trigger.toques == 1


def test_q_encerra(ui: JarvisUi) -> None:
    encerrou = []
    ui.on_quit = lambda: encerrou.append(True)
    assert ui.handle_key(ord("q")) is False
    assert encerrou == [True]


def test_busca_filtra_e_esc_limpa(ui: JarvisUi) -> None:
    ui.handle_key(ord("/"))
    for letra in "cor":
        ui.handle_key(ord(letra))
    assert ui.busca == "cor"

    ui.handle_key(27)  # ESC
    assert ui.busca == ""
    assert ui.modo_busca is False


def test_busca_reduz_os_comandos_listados(ui: JarvisUi) -> None:
    grupo_luz = next(i for i, (nome, _, _) in enumerate(GROUPS) if "Luz" in nome)
    ui.grupo = grupo_luz
    total = len(ui._comandos_do_grupo(grupo_luz))

    ui.busca = "brilho"
    assert 0 < len(ui._comandos_do_grupo(grupo_luz)) < total


# --------------------------------------------------------------------------- #
# Conteudo
# --------------------------------------------------------------------------- #


def test_todo_grupo_tem_comandos(ui: JarvisUi) -> None:
    for indice, (nome, _, _) in enumerate(GROUPS):
        assert ui._comandos_do_grupo(indice), f"grupo vazio: {nome}"


def test_toda_intencao_aparece_em_algum_grupo() -> None:
    """Comando implementado que nao aparece na interface e comando invisivel."""
    mostradas = {i for _, intents, _ in GROUPS for i in intents}
    faltando = [
        i.value
        for i in Intent
        if i is not Intent.UNKNOWN and i not in mostradas
    ]
    assert not faltando, f"intencoes fora da interface: {faltando}"


def test_frases_em_ingles_ficam_fora_da_interface(ui: JarvisUi) -> None:
    """A interface mostra o que da para dizer de fato -- e a gramatica e pt."""
    for indice in range(len(GROUPS)):
        for _, _, frases in ui._comandos_do_grupo(indice):
            assert "turn on" not in frases.lower()
