"""Um handler por intencao.

Substitui a cadeia de nove `if command.intent == ...` do codigo antigo por um
registro por decorator. Adicionar um comando novo agora e escrever uma funcao e
uma linha de frases no router -- sem tocar no controlador.
"""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..config import AppConfig
from ..hardware.factory import HardwareSet
from ..storage.db import Storage
from ..utils import humanize_seconds
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
    #: Ultimo conteudo util (transcricao, leitura, hora), para o "repetir".
    #: Precisa ser separado de `heard`, senao dizer "repetir" apagaria
    #: justamente o que deveria ser repetido.
    last_content: str = ""


Handler = Callable[[Context], Reply]
HANDLERS: dict[Intent, Handler] = {}


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
    ctx.hardware.leds.on()
    return Reply("LED ligado", "LED", "ligado", icon="ok")


@handles(Intent.LED_OFF)
def _led_off(ctx: Context) -> Reply:
    ctx.hardware.leds.off()
    return Reply("LED desligado", "LED", "desligado", icon="ok")


@handles(Intent.LED_BLINK)
def _led_blink(ctx: Context) -> Reply:
    ctx.hardware.leds.blink_async(times=5)
    return Reply("LED piscando", "LED", "piscando", icon="ok")


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


@handles(Intent.SERVO_SWEEP)
def _servo_sweep(ctx: Context) -> Reply:
    ctx.hardware.servo.sweep_async()
    return Reply("Varrendo o servo", "Servo", "varrendo...", icon="ok")


# --------------------------------------------------------------------------- #
# Distancia
# --------------------------------------------------------------------------- #


@handles(Intent.DISTANCE_READ)
def _distance_read(ctx: Context) -> Reply:
    value = ctx.hardware.distance.read_cm()
    close = value <= ctx.config.behavior.distance_warning_cm
    return Reply(
        f"Distancia: {value:.1f} cm",
        "Distancia",
        f"{value:.1f} cm",
        icon="alerta" if close else "ok",
        repeatable=True,
    )


@handles(Intent.DISTANCE_MONITOR)
def _distance_monitor(ctx: Context) -> Reply:
    """Vigia o sensor por alguns segundos, avisando com LED e matriz."""
    behavior = ctx.config.behavior
    hardware = ctx.hardware
    deadline = time.monotonic() + behavior.monitor_duration_s
    alerts = 0
    closest = float("inf")

    hardware.lcd.show_lines("Monitorando...", "")
    while time.monotonic() < deadline:
        value = hardware.distance.read_cm()
        closest = min(closest, value)
        if value <= behavior.distance_warning_cm:
            alerts += 1
            hardware.leds.on()
            hardware.matrix.show_icon("alerta")
            hardware.lcd.show_lines("ALERTA perto!", f"{value:.1f} cm")
        else:
            hardware.leds.off()
            hardware.matrix.show_icon("ok")
            hardware.lcd.show_lines("Monitorando", f"{value:.1f} cm")
        time.sleep(0.4)

    hardware.leds.off()
    summary = f"Monitoramento encerrado. Minimo: {closest:.1f} cm, {alerts} alertas."
    return Reply(summary, "Fim monitor", f"min {closest:.1f} cm", icon="ok", repeatable=True)


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


@handles(Intent.CLEAR)
def _clear(ctx: Context) -> Reply:
    ctx.hardware.leds.off()
    ctx.hardware.matrix.clear()
    ctx.hardware.lcd.clear()
    return Reply("Tudo limpo", "", "")


@handles(Intent.SHUTDOWN)
def _shutdown(_ctx: Context) -> Reply:
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
