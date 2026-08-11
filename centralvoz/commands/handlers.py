"""Um handler por intencao.

Substitui a cadeia de nove `if command.intent == ...` do codigo antigo por um
registro por decorator. Adicionar um comando novo agora e escrever uma funcao e
uma linha de frases no router -- sem tocar no controlador.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..tasks import BackgroundTask
from ..config import AppConfig
from ..hardware.factory import HardwareSet
from ..hardware.rgb import COLORS, RAINBOW
from ..storage.db import Storage
from ..utils import humanize_seconds, normalize_text
from .intents import AppMode, Intent


@dataclass
class Reply:
    """Resposta de um handler: o que falar, o que mostrar e para onde ir."""

    message: str
    lcd_title: str = ""
    lcd_detail: str = ""
    lcd_text: str | None = None  # texto longo: pagina sozinho no display
    icon: str | None = None
    next_mode: AppMode | None = None
    stop: bool = False
    #: True quando a resposta carrega conteudo que faz sentido ouvir de novo
    #: (uma leitura, a hora, uma transcricao). Confirmacoes como "servo aberto"
    #: nao sao conteudo, e por isso nao entram no comando "repetir".
    repeatable: bool = False


@dataclass
class Context:
    config: AppConfig
    hardware: HardwareSet
    storage: Storage
    #: Ultima fala crua, usada para dizer "nao entendi <isso>".
    heard: str = ""
    #: Numero dito no comando atual, quando houver ("servo trinta graus" -> 30).
    number: int | None = None
    #: Cor dita no comando atual ("acender azul" -> "azul").
    color: str | None = None
    #: Tarefa longa em execucao (monitoramento, festa). Injetada pelo controller.
    task: "BackgroundTask | None" = None
    #: Ultimo conteudo util (transcricao, leitura, hora), para o "repetir".
    #: Precisa ser separado de `heard`, senao dizer "repetir" apagaria
    #: justamente o que deveria ser repetido.
    last_content: str = ""


Handler = Callable[[Context], Reply]
HANDLERS: dict[Intent, Handler] = {}

logger = logging.getLogger(__name__)


def _start_task(ctx: Context, label: str, func) -> None:
    """Inicia uma tarefa longa. Sem gerenciador, roda de forma sincrona."""
    if ctx.task is not None:
        ctx.task.start(label, func)
        return
    logger.debug("Sem gerenciador de tarefas: executando '%s' de forma sincrona", label)
    func(threading.Event())


def _stop_task(ctx: Context) -> bool:
    return ctx.task.cancel() if ctx.task is not None else False


def handles(intent: Intent) -> Callable[[Handler], Handler]:
    def decorator(func: Handler) -> Handler:
        HANDLERS[intent] = func
        return func

    return decorator


# --------------------------------------------------------------------------- #
# LED
# --------------------------------------------------------------------------- #


@handles(Intent.LED_ON)
def _led_on(ctx: Context) -> Reply:
    # Se veio cor junto ("ligar luz azul"), respeita a cor mesmo que o roteador
    # tenha classificado como LED_ON.
    if ctx.color:
        return _led_color(ctx)
    ctx.hardware.leds.on()
    return Reply("Luz ligada", "Luz", "ligada", icon="ok")


@handles(Intent.LED_COLOR)
def _led_color(ctx: Context) -> Reply:
    if not ctx.color:
        nomes = ", ".join(list(COLORS)[:6])
        return Reply(
            f"Nao entendi a cor. Tente: {nomes}...", "Qual cor?", "diga a cor",
            icon="alerta",
        )
    ctx.hardware.leds.set_named(ctx.color)
    return Reply(f"Luz {ctx.color}", "Cor", ctx.color, icon="ok")


@handles(Intent.LED_CYCLE)
def _led_cycle(ctx: Context) -> Reply:
    """Passa pelas cores do arco-iris em segundo plano."""
    hardware = ctx.hardware
    passo = ctx.config.behavior.color_cycle_step_s
    duracao = ctx.config.behavior.party_duration_s

    def tarefa(cancel) -> None:
        fim = time.monotonic() + duracao
        indice = 0
        while time.monotonic() < fim and not cancel.is_set():
            nome = RAINBOW[indice % len(RAINBOW)]
            hardware.leds.set_named(nome)
            hardware.lcd.show_lines("Trocando cor", nome)
            indice += 1
            if cancel.wait(passo):
                break
        hardware.leds.off()

    _start_task(ctx, "ciclo de cores", tarefa)
    return Reply("Passando pelas cores. Diga 'parar' para interromper.",
                 "Arco-iris", "diga parar", icon="coracao")


@handles(Intent.LED_BRIGHTNESS)
def _led_brightness(ctx: Context) -> Reply:
    if ctx.number is None:
        return Reply("Diga o brilho, por exemplo: brilho cinquenta por cento.",
                     "Brilho", "diga o valor", icon="alerta")
    valor = max(0, min(100, ctx.number))
    ctx.hardware.leds.brightness(valor / 100.0)
    return Reply(f"Brilho em {valor}%", "Brilho", f"{valor}%", icon="ok")


@handles(Intent.LED_OFF)
def _led_off(ctx: Context) -> Reply:
    _stop_task(ctx)
    ctx.hardware.leds.off()
    return Reply("Luz desligada", "Luz", "desligada", icon="ok")


@handles(Intent.LED_BLINK)
def _led_blink(ctx: Context) -> Reply:
    ctx.hardware.leds.blink_async(times=5, color=ctx.color or "")
    detalhe = ctx.color or "piscando"
    return Reply("Luz piscando", "Luz", detalhe, icon="ok")


# --------------------------------------------------------------------------- #
# Servo
# --------------------------------------------------------------------------- #


@handles(Intent.SERVO_OPEN)
def _servo_open(ctx: Context) -> Reply:
    angle = ctx.hardware.servo.move_to(ctx.config.behavior.servo_open_angle)
    return Reply(f"Servo aberto ({angle:.0f} graus)", "Servo aberto", f"{angle:.0f} graus", icon="ok")


@handles(Intent.SERVO_CLOSE)
def _servo_close(ctx: Context) -> Reply:
    angle = ctx.hardware.servo.move_to(ctx.config.behavior.servo_closed_angle)
    return Reply(f"Servo fechado ({angle:.0f} graus)", "Servo fechado", f"{angle:.0f} graus", icon="ok")


@handles(Intent.LED_BLINK_N)
def _led_blink_n(ctx: Context) -> Reply:
    vezes = max(1, min(20, ctx.number or 3))
    ctx.hardware.leds.blink_async(times=vezes, color=ctx.color or "")
    return Reply(f"Piscando {vezes} vezes", "Luz", f"{vezes} vezes", icon="ok")


@handles(Intent.SERVO_ANGLE)
def _servo_angle(ctx: Context) -> Reply:
    if ctx.number is None:
        return Reply(
            "Nao entendi o angulo. Diga por exemplo: servo noventa graus.",
            "Servo", "diga o angulo", icon="alerta",
        )
    angulo = ctx.hardware.servo.move_to(ctx.number)
    return Reply(
        f"Servo em {angulo:.0f} graus", "Servo", f"{angulo:.0f} graus", icon="ok"
    )


@handles(Intent.SERVO_SWEEP)
def _servo_sweep(ctx: Context) -> Reply:
    ctx.hardware.servo.sweep_async()
    return Reply("Varrendo o servo", "Servo", "varrendo...", icon="ok")


# --------------------------------------------------------------------------- #
# Distancia
# --------------------------------------------------------------------------- #


@handles(Intent.DISTANCE_READ)
def _distance_read(ctx: Context) -> Reply:
    valor = ctx.hardware.distance.read_cm()
    if valor is None:
        return Reply(
            "O sensor de distancia nao respondeu. Confira a fiacao do HC-SR04 "
            "(VCC em 5 V, divisor de tensao no ECHO) -- veja docs/ligacoes.md.",
            "Sensor mudo",
            "veja a fiacao",
            icon="erro",
        )

    perto = valor <= ctx.config.behavior.distance_warning_cm
    return Reply(
        f"Distancia: {valor:.1f} cm",
        "Distancia",
        f"{valor:.1f} cm",
        icon="alerta" if perto else "ok",
        repeatable=True,
    )


@handles(Intent.DISTANCE_MONITOR)
def _distance_monitor(ctx: Context) -> Reply:
    """Vigia o sensor em SEGUNDO PLANO.

    Antes esse laco rodava dentro do handler e bloqueava o loop principal por
    15 s: a central ficava surda, e os ENTER apertados nesse meio-tempo se
    acumulavam na fila do stdin, disparando capturas vazias em sequencia quando
    o controle voltava. Agora roda numa thread cancelavel e o loop continua
    ouvindo -- basta dizer "parar".
    """
    behavior = ctx.config.behavior
    hardware = ctx.hardware
    limite = behavior.distance_warning_cm

    def tarefa(cancel) -> None:
        fim = time.monotonic() + behavior.monitor_duration_s
        alertas = 0
        menor = float("inf")

        while time.monotonic() < fim and not cancel.is_set():
            leitura = hardware.distance.read_cm()
            if leitura is None:
                # Sensor mudo ou ausente: nao adianta insistir por 20 s.
                hardware.leds.set_named("vermelho")
                hardware.lcd.show_lines("Sensor mudo", "veja a fiacao")
                logger.error("Monitoramento abortado: o sensor nao respondeu.")
                return

            try:
                valor = float(leitura)
            except (TypeError, ValueError):
                hardware.lcd.show_lines("Sem sensor", "de distancia")
                return

            menor = min(menor, valor)
            perto = valor <= limite
            if perto:
                alertas += 1
                hardware.leds.set_named("vermelho")
                hardware.matrix.show_icon("alerta")
                hardware.lcd.show_lines("ALERTA perto!", f"{valor:.1f} cm")
            else:
                hardware.leds.set_named("verde")
                hardware.matrix.show_icon("ok")
                hardware.lcd.show_lines("Monitorando", f"{valor:.1f} cm")

            if cancel.wait(0.4):
                break

        hardware.leds.off()
        hardware.matrix.show_icon("ok")
        if menor == float("inf"):
            hardware.lcd.show_lines("Monitor", "encerrado")
        else:
            hardware.lcd.show_lines("Fim monitor", f"min {menor:.1f} cm")
        logger.info("Monitoramento encerrado: min %.1f cm, %d alertas", menor, alertas)

    _start_task(ctx, "monitor de distancia", tarefa)
    return Reply(
        f"Monitorando por {behavior.monitor_duration_s:.0f} s. Diga 'parar' para interromper.",
        "Monitorando", "diga parar", icon="ouvindo",
    )


@handles(Intent.STOP_TASK)
def _stop_task_cmd(ctx: Context) -> Reply:
    """Cancela o que estiver rodando em segundo plano."""
    rotulo = ctx.task.label if ctx.task else ""
    parou = _stop_task(ctx)
    ctx.hardware.leds.stop_effect()

    if not parou:
        return Reply("Nada rodando no momento.", "Parar", "nada ativo", icon="ok")
    return Reply(f"Cancelado: {rotulo}", "Cancelado", rotulo[:16], icon="ok")


# --------------------------------------------------------------------------- #
# Ditado / recados
# --------------------------------------------------------------------------- #


@handles(Intent.DICTATION_START)
def _dictation_start(_ctx: Context) -> Reply:
    return Reply(
        "Modo ditado ativado. Fale e o texto aparece no LCD. Diga 'parar ditado' para sair.",
        "Modo ditado",
        "pode falar",
        icon="ouvindo",
        next_mode=AppMode.DICTATION,
    )


@handles(Intent.DICTATION_STOP)
def _dictation_stop(_ctx: Context) -> Reply:
    return Reply(
        "Modo ditado encerrado.",
        "Ditado",
        "encerrado",
        icon="ok",
        next_mode=AppMode.COMMAND,
    )


@handles(Intent.NOTES_LIST)
def _notes_list(ctx: Context) -> Reply:
    notes = ctx.storage.recent_notes(limit=5)
    if not notes:
        return Reply("Nenhum recado gravado.", "Recados", "vazio", icon="alerta")

    lines = [f"{note.created_at:%d/%m %H:%M} {note.text}" for note in notes]
    joined = " | ".join(lines)
    return Reply(f"{len(notes)} recado(s): {joined}", lcd_text=joined, icon="ok", repeatable=True)


@handles(Intent.NOTES_CLEAR)
def _notes_clear(ctx: Context) -> Reply:
    total = ctx.storage.clear_notes()
    return Reply(f"{total} recado(s) apagado(s).", "Recados", "apagados", icon="ok")


@handles(Intent.REPEAT_LAST)
def _repeat_last(ctx: Context) -> Reply:
    if not ctx.last_content:
        return Reply("Nada para repetir ainda.", "Repetir", "vazio", icon="alerta")
    return Reply(f"Repetindo: {ctx.last_content}", lcd_text=ctx.last_content, icon="ok")


# --------------------------------------------------------------------------- #
# Sistema
# --------------------------------------------------------------------------- #


@handles(Intent.CLOCK)
def _clock(_ctx: Context) -> Reply:
    now = datetime.now()
    return Reply(
        f"Agora sao {now:%H:%M} de {now:%d/%m/%Y}",
        f"{now:%H:%M:%S}",
        f"{now:%d/%m/%Y}",
        icon="ok",
        repeatable=True,
    )


@handles(Intent.SYSTEM_STATUS)
def _system_status(ctx: Context) -> Reply:
    temperature = _cpu_temperature()
    uptime = _uptime_seconds()
    ip = _local_ip()
    mode = "simulado" if ctx.hardware.simulated else "hardware"

    detail = f"{temperature:.0f}C up {humanize_seconds(uptime)}" if temperature else "sem sensor"
    full = f"Modo {mode}. CPU {temperature:.1f} C. Ligado ha {humanize_seconds(uptime)}. IP {ip}."
    return Reply(full, "Status", detail, icon="ok", repeatable=True)


@handles(Intent.HELP)
def _help(ctx: Context) -> Reply:
    from .router import CommandRouter  # import tardio: evita ciclo

    commands = CommandRouter().help_lines()
    joined = " . ".join(commands)
    return Reply(f"Comandos disponiveis: {joined}", lcd_text=joined, icon="ok", repeatable=True)


@handles(Intent.PARTY_MODE)
def _party_mode(ctx: Context) -> Reply:
    """Aciona tudo ao mesmo tempo, em segundo plano.

    Roda por `behavior.party_duration_s` (12 s por padrao). A versao anterior
    durava pouco mais de um segundo porque so percorria quatro icones.
    """
    hardware = ctx.hardware
    duracao = ctx.config.behavior.party_duration_s
    icones = ("coracao", "ok", "alerta", "casa")

    def tarefa(cancel) -> None:
        fim_festa = time.monotonic() + duracao
        passo = 0
        angulo_aberto = True

        while time.monotonic() < fim_festa and not cancel.is_set():
            hardware.leds.set_named(RAINBOW[passo % len(RAINBOW)])
            hardware.matrix.show_icon(icones[passo % len(icones)])

            # O servo se move a cada 4 passos: mais que isso vira zumbido.
            if passo % 4 == 0:
                hardware.servo.move_to(150.0 if angulo_aberto else 30.0)
                angulo_aberto = not angulo_aberto

            restante = fim_festa - time.monotonic()
            hardware.lcd.show_lines("* MODO FESTA *", f"{restante:.0f}s  :)")
            passo += 1
            if cancel.wait(0.25):
                break

        hardware.leds.off()
        hardware.servo.move_to(90.0)
        hardware.servo.release()
        hardware.matrix.show_icon("ok")
        hardware.lcd.show_lines("Fim da festa", "obrigado!")

    _start_task(ctx, "modo festa", tarefa)
    return Reply(
        f"Modo festa por {duracao:.0f} s! Diga 'parar' para interromper.",
        "* MODO FESTA *", "diga parar", icon="coracao",
    )


@handles(Intent.MATRIX_DRAW)
def _matrix_draw(ctx: Context) -> Reply:
    """O desenho vem da propria fala: 'desenhar coracao' -> icone coracao."""
    from ..hardware.matrix import ICONS

    dito = normalize_text(ctx.heard)
    nome = next((icone for icone in ICONS if icone in dito), "ok")
    ctx.hardware.matrix.show_icon(nome)
    return Reply(f"Desenhando {nome}", "Desenho", nome, icon=nome)


@handles(Intent.CLEAR)
def _clear(ctx: Context) -> Reply:
    _stop_task(ctx)
    ctx.hardware.leds.off()
    ctx.hardware.matrix.clear()
    ctx.hardware.lcd.clear()
    return Reply("Tudo limpo", "", "")


@handles(Intent.SHUTDOWN)
def _shutdown(ctx: Context) -> Reply:
    _stop_task(ctx)
    return Reply("Encerrando a central. Ate logo!", "Encerrando", "tchau", icon="ok", stop=True)


@handles(Intent.UNKNOWN)
def _unknown(ctx: Context) -> Reply:
    heard = ctx.heard or ""
    detail = heard[:16] if heard else "tente de novo"
    return Reply(f"Nao entendi: {heard!r}", "Nao entendi", detail, icon="erro")


# --------------------------------------------------------------------------- #
# Leituras do sistema operacional
# --------------------------------------------------------------------------- #


def _cpu_temperature() -> float:
    path = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        return int(path.read_text().strip()) / 1000.0
    except (OSError, ValueError):
        return 0.0


def _uptime_seconds() -> float:
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return 0.0


def _local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.2)
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
    except OSError:
        return "sem rede"
