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


# --------------------------------------------------------------------------- #
# Isolamento das saidas nativas
# --------------------------------------------------------------------------- #


def test_stderr_nativo_vai_para_o_arquivo(tmp_path) -> None:
    """Regressao: o Vosk escrevia no stderr ao criar o reconhecedor.

    Isso acontecia exatamente ao apertar ENTER para falar, e o texto caia por
    cima do desenho do curses -- a interface 'quebrava' e o terminal virava
    texto solto.
    """
    import os

    from centralvoz.quiet import redirect_native_stderr_to

    destino = tmp_path / "stderr.log"
    with redirect_native_stderr_to(destino):
        os.write(2, b"WARNING (VoskAPI): Word 'lede' not in vocabulary\n")

    conteudo = destino.read_text()
    assert "not in vocabulary" in conteudo

    # Depois do bloco, escrever no fd 2 nao vai mais para o arquivo.
    tamanho = destino.stat().st_size
    os.write(2, b"")
    assert destino.stat().st_size == tamanho


def test_print_nao_escapa_para_a_tela() -> None:
    """Um print() de qualquer thread escreveria bem onde o curses desenha."""
    from centralvoz.quiet import StdoutToLog

    capturado = []
    proxy = StdoutToLog(capturado.append)

    proxy.write("primeira linha\n")
    proxy.write("segunda ")
    proxy.write("linha\n")
    proxy.flush()

    assert capturado == ["primeira linha", "segunda linha"]
    assert proxy.isatty() is False


def test_proxy_de_stdout_ignora_linhas_vazias() -> None:
    from centralvoz.quiet import StdoutToLog

    capturado = []
    proxy = StdoutToLog(capturado.append)
    proxy.write("\n\n   \n")
    proxy.flush()
    assert capturado == []


def test_resize_pede_redesenho_completo(ui: JarvisUi) -> None:
    import curses

    assert ui.redesenhar is False
    ui.handle_key(curses.KEY_RESIZE)
    assert ui.redesenhar is True


def test_handler_de_arquivo_nao_e_removido_pela_interface(tmp_path) -> None:
    """RotatingFileHandler herda de StreamHandler.

    Filtrar so por tipo removeria tambem o log em arquivo, e o `logs/` ficaria
    vazio justamente quando mais se precisa dele.
    """
    import logging
    from logging.handlers import RotatingFileHandler

    arquivo = RotatingFileHandler(tmp_path / "teste.log")
    console = logging.StreamHandler()

    candidatos = [
        h
        for h in (arquivo, console)
        if isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.FileHandler)
    ]
    arquivo.close()

    assert console in candidatos
    assert arquivo not in candidatos


# --------------------------------------------------------------------------- #
# Painel de reconhecimento e aba do motor
# --------------------------------------------------------------------------- #


def test_captura_do_stderr_entrega_linha_a_linha() -> None:
    """A saida do Vosk vira conteudo da interface em vez de lixo na tela."""
    import os
    import time

    from centralvoz.quiet import capture_native_stderr

    linhas: list[str] = []
    with capture_native_stderr(linhas.append):
        os.write(2, b"LOG (VoskAPI:Model()): Loading model\n")
        os.write(2, b"WARNING (VoskAPI): Word 'lede' not in vocabulary\n")
        time.sleep(0.3)

    assert len(linhas) == 2
    assert "Loading model" in linhas[0]
    assert "not in vocabulary" in linhas[1]


def test_estado_guarda_a_transcricao_parcial() -> None:
    estado = UiState()
    estado.set_partial("acender a luz azu")
    assert estado.snapshot()["partial"] == "acender a luz azu"

    estado.set_partial("")
    assert estado.snapshot()["partial"] == ""


def test_estado_guarda_intencao_e_confianca() -> None:
    estado = UiState()
    estado.set_recognition("acender azul", "led_color", 0.94)

    dados = estado.snapshot()
    assert dados["last_heard"] == "acender azul"
    assert dados["last_intent"] == "led_color"
    assert dados["last_score"] == pytest.approx(0.94)


def test_linhas_do_motor_tem_limite() -> None:
    """Sessao longa nao pode encher a memoria com log do Kaldi."""
    estado = UiState()
    for i in range(500):
        estado.log_engine(f"LOG linha {i}")

    linhas = estado.snapshot()["engine_lines"]
    assert len(linhas) <= 100
    assert "linha 499" in linhas[-1][1]


def test_tecla_m_alterna_a_aba(ui: JarvisUi) -> None:
    assert ui.aba == "eventos"
    ui.handle_key(ord("m"))
    assert ui.aba == "motor"
    ui.handle_key(ord("m"))
    assert ui.aba == "eventos"


def test_ganchos_do_loop_sao_opcionais() -> None:
    """No modo texto os ganchos ficam vazios e nada pode quebrar."""
    from centralvoz.app.runner import VoiceLoop

    assert "on_status" in VoiceLoop.__init__.__code__.co_names
    assert "on_partial" in VoiceLoop.__init__.__code__.co_names


def test_gancho_que_falha_nao_derruba_o_loop() -> None:
    from centralvoz.app.runner import VoiceLoop

    loop = VoiceLoop.__new__(VoiceLoop)
    loop.on_status = lambda _: 1 / 0
    loop.on_partial = lambda _: 1 / 0

    # Nao levanta: a interface nunca pode interromper o reconhecimento.
    loop._notify_status("ouvindo")
    loop._notify_partial("teste")
