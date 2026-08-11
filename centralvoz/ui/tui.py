"""Interface de terminal do Jarvis.

Usa apenas `curses`, da biblioteca padrao -- nada para instalar no Pi.

Layout:

    +--------------------------------------------------------------+
    |  J A R V I S            [ pronto ]        14:32:05           |  cabecalho
    +---------------------------+----------------------------------+
    |  COMANDOS                 |  DETALHE                         |
    |   > Luz                   |   "acender <cor>"                |
    |     Servo                 |   Acende o LED RGB na cor dita.  |
    |     Distancia             |   Aceita 15 cores...             |
    |     ...                   |                                  |
    +---------------------------+----------------------------------+
    |  ATIVIDADE                                                   |
    |  14:31:58  ouvi "acender azul" -> led_color (1.00)           |
    +--------------------------------------------------------------+
    |  ENTER falar   ↑↓ navegar   TAB secao   / buscar   q sair    |
    +--------------------------------------------------------------+

O loop de voz roda numa thread; a interface fica na principal e apenas le
estado. Nada de I/O de hardware aqui dentro.
"""

from __future__ import annotations

import curses
import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from ..commands.intents import Intent
from ..commands.router import CommandRouter

TITLE = "J A R V I S"
SUBTITLE = "central de comandos por voz"

#: Agrupamento dos comandos no painel esquerdo, com uma explicacao curta de cada
#: grupo. A lista de frases vem do proprio roteador, entao nunca desatualiza.
GROUPS: tuple[tuple[str, tuple[Intent, ...], str], ...] = (
    (
        "Luz RGB",
        (
            Intent.LED_ON, Intent.LED_OFF, Intent.LED_COLOR,
            Intent.LED_BLINK, Intent.LED_BLINK_N,
            Intent.LED_CYCLE, Intent.LED_BRIGHTNESS,
        ),
        "LED RGB de anodo comum. Aceita 15 cores, incluindo misturas "
        "como amarelo, laranja e turquesa.",
    ),
    (
        "Servo",
        (
            Intent.SERVO_OPEN, Intent.SERVO_CLOSE,
            Intent.SERVO_SWEEP, Intent.SERVO_ANGLE,
        ),
        "Servomotor no GPIO18 (PWM por hardware). Solta o pulso sozinho "
        "depois de parar, para nao zumbir.",
    ),
    (
        "Distancia",
        (Intent.DISTANCE_READ, Intent.DISTANCE_MONITOR),
        "HC-SR04. O monitoramento funciona como sensor de re: cor e ritmo "
        "do bipe acompanham a proximidade.",
    ),
    (
        "Som",
        (
            Intent.BUZZER_BEEP, Intent.BUZZER_MELODY,
            Intent.BUZZER_ALARM, Intent.BUZZER_SILENCE,
        ),
        "Dois buzzers: o ativo da bipes, o passivo toca melodias "
        "(so ele consegue variar a frequencia).",
    ),
    (
        "Desenhos",
        (Intent.MATRIX_DRAW,),
        "Matriz 8x8 via 74HC595. Coracao, sorriso, triste, estrela, casa, "
        "gato, seta, nota musical e mais.",
    ),
    (
        "Ditado",
        (
            Intent.DICTATION_START, Intent.DICTATION_STOP,
            Intent.NOTES_LIST, Intent.NOTES_CLEAR, Intent.REPEAT_LAST,
        ),
        "No ditado o reconhecimento fica livre e o texto vai para o LCD "
        "e para o banco. Diga 'parar ditado' para sair.",
    ),
    (
        "Sistema",
        (
            Intent.CLOCK, Intent.SYSTEM_STATUS, Intent.HELP,
            Intent.PARTY_MODE, Intent.CLEAR, Intent.STOP_TASK,
            Intent.SHUTDOWN,
        ),
        "Relogio, temperatura da CPU, modo festa e o comando 'parar', "
        "que cancela qualquer tarefa em andamento.",
    ),
)


@dataclass
class UiState:
    """Estado compartilhado entre o loop de voz e a interface."""

    status: str = "iniciando"
    partial: str = ""
    last_heard: str = ""
    last_intent: str = ""
    last_score: float = 0.0
    mode: str = "comando"
    task: str = ""
    hardware: str = ""
    events: deque = field(default_factory=lambda: deque(maxlen=200))
    #: Linhas cruas vindas do Vosk/ALSA (stderr nativo capturado).
    engine_lines: deque = field(default_factory=lambda: deque(maxlen=100))
    lock: threading.Lock = field(default_factory=threading.Lock)

    def set_status(self, status: str) -> None:
        with self.lock:
            self.status = status

    def log(self, texto: str, tipo: str = "info") -> None:
        with self.lock:
            self.events.append((datetime.now(), texto, tipo))

    def log_engine(self, texto: str) -> None:
        """Linha crua do Vosk ou do ALSA, capturada do stderr nativo."""
        with self.lock:
            self.engine_lines.append((datetime.now(), texto))

    def set_recognition(self, heard: str, intent: str, score: float) -> None:
        with self.lock:
            self.last_heard = heard
            self.last_intent = intent
            self.last_score = score

    def set_partial(self, texto: str) -> None:
        with self.lock:
            self.partial = texto

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "status": self.status,
                "partial": self.partial,
                "last_heard": self.last_heard,
                "last_intent": self.last_intent,
                "last_score": self.last_score,
                "mode": self.mode,
                "task": self.task,
                "hardware": self.hardware,
                "events": list(self.events),
                "engine_lines": list(self.engine_lines),
            }


class UiLogHandler(logging.Handler):
    """Manda WARNING+ para o painel de atividade em vez do terminal."""

    def __init__(self, state: UiState) -> None:
        super().__init__(level=logging.WARNING)
        self.state = state

    def emit(self, record: logging.LogRecord) -> None:
        try:
            tipo = "erro" if record.levelno >= logging.ERROR else "aviso"
            self.state.log(record.getMessage().split("\n")[0][:200], tipo)
        except Exception:  # noqa: BLE001 - log nunca derruba o programa
            pass


# --------------------------------------------------------------------------- #
# Desenho
# --------------------------------------------------------------------------- #

C_TITLE, C_ACCENT, C_DIM, C_OK, C_WARN, C_ERR, C_SEL, C_BAR = range(1, 9)


def _init_colors() -> None:
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_TITLE, curses.COLOR_CYAN, -1)
    curses.init_pair(C_ACCENT, curses.COLOR_MAGENTA, -1)
    curses.init_pair(C_DIM, curses.COLOR_WHITE, -1)
    curses.init_pair(C_OK, curses.COLOR_GREEN, -1)
    curses.init_pair(C_WARN, curses.COLOR_YELLOW, -1)
    curses.init_pair(C_ERR, curses.COLOR_RED, -1)
    curses.init_pair(C_SEL, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(C_BAR, curses.COLOR_CYAN, -1)


STATUS_COLORS = {
    "ouvindo": C_OK,
    "processando": C_WARN,
    "executando": C_ACCENT,
    "pronto": C_TITLE,
    "erro": C_ERR,
}


class JarvisUi:
    """Desenha a interface e trata o teclado."""

    def __init__(self, state: UiState, trigger, on_quit) -> None:
        self.state = state
        self.trigger = trigger
        self.on_quit = on_quit
        self.router = CommandRouter()

        self.grupo = 0
        self.item = 0
        self.foco = "grupos"  # "grupos" ou "comandos"
        self.busca = ""
        self.modo_busca = False
        #: Pede um redesenho completo no proximo quadro.
        self.redesenhar = False
        self._quadros = 0
        #: Aba do painel inferior: "eventos" ou "motor".
        self.aba = "eventos"

    # -- dados ---------------------------------------------------------- #

    def _frases(self, intent: Intent) -> list[str]:
        return [f for regra in self.router.rules if regra.intent is intent
                for f in regra.phrases if regra.in_grammar]

    def _comandos_do_grupo(self, indice: int) -> list[tuple[Intent, str, str]]:
        _, intents, _ = GROUPS[indice]
        saida = []
        for intent in intents:
            frases = self._frases(intent)
            if not frases:
                continue
            ajuda = next(
                (r.help_text for r in self.router.rules
                 if r.intent is intent and r.help_text),
                frases[0],
            )
            saida.append((intent, ajuda, " / ".join(frases[:6])))
        if self.busca:
            alvo = self.busca.lower()
            saida = [c for c in saida if alvo in c[1].lower() or alvo in c[2].lower()]
        return saida

    # -- desenho -------------------------------------------------------- #

    def draw(self, tela) -> None:
        # Redesenho completo periodico. Se algo escapou para o terminal por
        # baixo do curses (uma biblioteca em C, um print de outra thread), o
        # curses nao sabe que a tela mudou e continua fazendo atualizacoes
        # parciais sobre lixo. Repintar tudo de vez em quando conserta sozinho.
        self._quadros += 1
        if self.redesenhar or self._quadros % 100 == 0:
            self.redesenhar = False
            try:
                tela.redrawwin()
            except curses.error:
                pass

        tela.erase()
        altura, largura = tela.getmaxyx()
        if altura < 14 or largura < 60:
            _put(tela, 0, 0, "Aumente a janela (minimo 60x14)")
            tela.refresh()
            return

        dados = self.state.snapshot()
        self._header(tela, largura, dados)

        topo = 4
        rodape = 1
        reconhecimento = 4
        atividade = max(5, (altura - topo - rodape - reconhecimento) // 3)
        corpo = altura - topo - rodape - atividade - reconhecimento

        meio = max(22, largura // 3)
        self._painel_comandos(tela, topo, 0, corpo, meio)
        self._painel_detalhe(tela, topo, meio, corpo, largura - meio, dados)
        self._painel_reconhecimento(tela, topo + corpo, largura, reconhecimento, dados)
        self._painel_atividade(
            tela, topo + corpo + reconhecimento, largura, atividade, dados
        )
        self._rodape(tela, altura - 1, largura)

        tela.refresh()

    def _header(self, tela, largura: int, dados: dict) -> None:
        _put(tela, 0, 0, "═" * largura, curses.color_pair(C_BAR))

        titulo = f" {TITLE} "
        _put(tela, 1, 2, titulo, curses.color_pair(C_TITLE) | curses.A_BOLD)
        if largura > 50:
            _put(tela, 1, 2 + len(titulo) + 1, SUBTITLE, curses.color_pair(C_DIM) | curses.A_DIM)

        status = dados["status"]
        cor = curses.color_pair(STATUS_COLORS.get(status, C_DIM))
        rotulo = f"[ {status.upper()} ]"
        if dados["mode"] == "ditado":
            rotulo = f"[ DITADO • {status.upper()} ]"

        coluna = largura - len(rotulo) - 12
        if coluna > 0:
            _put(tela, 1, coluna, rotulo, cor | curses.A_BOLD)
        _put(tela, 1, largura - 10, datetime.now().strftime("%H:%M:%S"),
                    curses.color_pair(C_DIM))

        linha = dados["partial"] or dados["task"] or dados["hardware"]
        if linha:
            _put(tela, 2, 2, linha[: largura - 4], curses.color_pair(C_DIM) | curses.A_DIM)
        _put(tela, 3, 0, "═" * largura, curses.color_pair(C_BAR))

    def _painel_comandos(self, tela, y: int, x: int, altura: int, largura: int) -> None:
        destaque = curses.A_BOLD if self.foco == "grupos" else curses.A_DIM
        _put(tela, y, x + 1, "COMANDOS", curses.color_pair(C_ACCENT) | destaque)

        for indice, (nome, _, _) in enumerate(GROUPS):
            linha = y + 2 + indice
            if linha >= y + altura:
                break
            selecionado = indice == self.grupo
            marca = "▸ " if selecionado else "  "
            estilo = (
                curses.color_pair(C_SEL)
                if selecionado and self.foco == "grupos"
                else curses.color_pair(C_TITLE if selecionado else C_DIM)
            )
            _put(tela, linha, x + 1, f"{marca}{nome}".ljust(largura - 2)[: largura - 2], estilo)

        for i in range(altura):
            if y + i < y + altura:
                _put(tela, y + i, x + largura - 1, "│", curses.color_pair(C_BAR))

    def _painel_detalhe(self, tela, y: int, x: int, altura: int, largura: int, dados: dict) -> None:
        nome, _, descricao = GROUPS[self.grupo]
        destaque = curses.A_BOLD if self.foco == "comandos" else curses.A_DIM
        _put(tela, y, x + 2, nome.upper(), curses.color_pair(C_ACCENT) | destaque)

        linha = y + 2
        for pedaco in _wrap(descricao, largura - 4):
            if linha >= y + altura - 1:
                break
            _put(tela, linha, x + 2, pedaco, curses.color_pair(C_DIM) | curses.A_DIM)
            linha += 1
        linha += 1

        comandos = self._comandos_do_grupo(self.grupo)
        self.item = max(0, min(self.item, max(0, len(comandos) - 1)))

        for indice, (_, ajuda, frases) in enumerate(comandos):
            if linha >= y + altura - 1:
                break
            selecionado = indice == self.item and self.foco == "comandos"
            estilo = curses.color_pair(C_SEL) if selecionado else curses.color_pair(C_OK)
            texto = f'  "{ajuda}"'
            _put(tela, linha, x + 2, texto[: largura - 4], estilo | curses.A_BOLD)
            linha += 1

            if selecionado and linha < y + altura - 1:
                for pedaco in _wrap(f"também: {frases}", largura - 8):
                    if linha >= y + altura - 1:
                        break
                    _put(tela, linha, x + 6, pedaco, curses.color_pair(C_DIM) | curses.A_DIM)
                    linha += 1

    def _painel_reconhecimento(self, tela, y: int, largura: int, altura: int, dados: dict) -> None:
        """O que o Vosk esta ouvindo agora e o que entendeu da ultima vez."""
        _put(tela, y, 0, "═" * largura, curses.color_pair(C_BAR))
        _put(tela, y, 2, " RECONHECIMENTO ", curses.color_pair(C_ACCENT) | curses.A_BOLD)

        status = dados["status"]
        parcial = dados["partial"]

        # Linha 1: o que esta sendo ouvido em tempo real.
        if status == "ouvindo":
            texto = parcial or "(fale agora)"
            _put(tela, y + 1, 2, "♪ ", curses.color_pair(C_OK) | curses.A_BOLD)
            _put(tela, y + 1, 4, texto[: largura - 6],
                 curses.color_pair(C_OK) | curses.A_BOLD)
        elif status == "processando":
            _put(tela, y + 1, 2, "… processando o áudio",
                 curses.color_pair(C_WARN) | curses.A_BOLD)
        elif dados["last_heard"]:
            _put(tela, y + 1, 2, f'"{dados["last_heard"]}"'[: largura - 4],
                 curses.color_pair(C_TITLE) | curses.A_BOLD)
        else:
            _put(tela, y + 1, 2, "aguardando — ENTER para falar",
                 curses.color_pair(C_DIM) | curses.A_DIM)

        # Linha 2: intencao reconhecida e barra de confianca.
        if dados["last_intent"]:
            score = dados["last_score"]
            rotulo = f"→ {dados['last_intent']}"
            _put(tela, y + 2, 2, rotulo[: largura - 24], curses.color_pair(C_ACCENT))

            largura_barra = 12
            preenchido = int(round(score * largura_barra))
            cor = C_OK if score >= 0.85 else (C_WARN if score >= 0.7 else C_ERR)
            coluna = max(len(rotulo) + 4, largura - largura_barra - 12)
            _put(tela, y + 2, coluna, "█" * preenchido, curses.color_pair(cor))
            _put(tela, y + 2, coluna + preenchido, "░" * (largura_barra - preenchido),
                 curses.color_pair(C_DIM) | curses.A_DIM)
            _put(tela, y + 2, coluna + largura_barra + 1, f"{score:.2f}",
                 curses.color_pair(cor) | curses.A_BOLD)

    def _painel_atividade(self, tela, y: int, largura: int, altura: int, dados: dict) -> None:
        _put(tela, y, 0, "═" * largura, curses.color_pair(C_BAR))

        abas = (("ATIVIDADE", "eventos"), ("MOTOR DE VOZ", "motor"))
        coluna = 2
        for rotulo, chave in abas:
            ativa = self.aba == chave
            estilo = (
                curses.color_pair(C_ACCENT) | curses.A_BOLD
                if ativa
                else curses.color_pair(C_DIM) | curses.A_DIM
            )
            _put(tela, y, coluna, f" {rotulo} ", estilo)
            coluna += len(rotulo) + 3

        if self.aba == "eventos":
            linhas = [
                (q, t, tipo) for q, t, tipo in dados["events"][-(altura - 1):]
            ]
        else:
            linhas = [(q, t, "motor") for q, t in dados["engine_lines"][-(altura - 1):]]
            if not linhas:
                linhas = [(datetime.now(), "sem saída do Vosk ainda", "info")]

        for indice, (quando, texto, tipo) in enumerate(linhas):
            linha = y + 1 + indice
            if linha >= y + altura:
                break
            cor = {"erro": C_ERR, "aviso": C_WARN, "ok": C_OK, "motor": C_TITLE}.get(
                tipo, C_DIM
            )
            _put(tela, linha, 2, quando.strftime("%H:%M:%S"),
                 curses.color_pair(C_DIM) | curses.A_DIM)
            _put(tela, linha, 11, texto[: largura - 13], curses.color_pair(cor))

    def _rodape(self, tela, y: int, largura: int) -> None:
        if self.modo_busca:
            _put(tela, y, 2, f"buscar: {self.busca}_", curses.color_pair(C_WARN))
            return

        atalhos = [
            ("ENTER", "falar"), ("↑↓", "navegar"), ("TAB", "seção"),
            ("m", "motor"), ("/", "buscar"), ("q", "sair"),
        ]
        coluna = 2
        for tecla, rotulo in atalhos:
            if coluna + len(tecla) + len(rotulo) + 3 >= largura:
                break
            _put(tela, y, coluna, tecla, curses.color_pair(C_TITLE) | curses.A_BOLD)
            coluna += len(tecla) + 1
            _put(tela, y, coluna, rotulo, curses.color_pair(C_DIM) | curses.A_DIM)
            coluna += len(rotulo) + 3

    # -- teclado --------------------------------------------------------- #

    def handle_key(self, tecla: int) -> bool:
        """Retorna False para encerrar."""
        if self.modo_busca:
            return self._tecla_busca(tecla)

        if tecla in (ord("q"), ord("Q")):
            self.on_quit()
            return False

        if tecla == ord("/"):
            self.modo_busca = True
            self.busca = ""
        elif tecla == ord("\t"):
            self.foco = "comandos" if self.foco == "grupos" else "grupos"
        elif tecla in (curses.KEY_UP, ord("k")):
            self._mover(-1)
        elif tecla in (curses.KEY_DOWN, ord("j")):
            self._mover(1)
        elif tecla in (curses.KEY_RIGHT, ord("l")):
            self.foco = "comandos"
        elif tecla in (curses.KEY_LEFT, ord("h")):
            self.foco = "grupos"
        elif tecla in (ord("m"), ord("M")):
            self.aba = "motor" if self.aba == "eventos" else "eventos"
        elif tecla == curses.KEY_RESIZE:
            # Janela redimensionada: descarta a tela antiga por inteiro.
            self.redesenhar = True
        elif tecla in (curses.KEY_ENTER, 10, 13):
            self.trigger.toggle()
        return True

    def _tecla_busca(self, tecla: int) -> bool:
        if tecla in (27,):  # ESC
            self.modo_busca = False
            self.busca = ""
        elif tecla in (curses.KEY_ENTER, 10, 13):
            self.modo_busca = False
        elif tecla in (curses.KEY_BACKSPACE, 127, 8):
            self.busca = self.busca[:-1]
        elif 32 <= tecla < 127:
            self.busca += chr(tecla)
        return True

    def _mover(self, passo: int) -> None:
        if self.foco == "grupos":
            self.grupo = (self.grupo + passo) % len(GROUPS)
            self.item = 0
        else:
            total = len(self._comandos_do_grupo(self.grupo))
            if total:
                self.item = (self.item + passo) % total


def _put(tela, y: int, x: int, texto: str, estilo: int = 0) -> None:
    """addstr que nunca levanta excecao.

    O curses estoura ao escrever na ultima celula da tela (canto inferior
    direito) e ao receber coordenada fora da janela. Numa interface que se
    redesenha 20 vezes por segundo enquanto o usuario redimensiona o terminal,
    isso derrubaria o programa -- por isso todo desenho passa por aqui.
    """
    if y < 0 or x < 0 or not texto:
        return
    altura, largura = tela.getmaxyx()
    if y >= altura or x >= largura:
        return
    # Deixa a ultima celula em branco: escrever nela move o cursor para fora.
    disponivel = largura - x - (1 if y == altura - 1 else 0)
    if disponivel <= 0:
        return
    try:
        tela.addstr(y, x, texto[:disponivel], estilo)
    except curses.error:
        pass


def _wrap(texto: str, largura: int) -> list[str]:
    from textwrap import wrap

    return wrap(texto, max(10, largura)) if texto else []
