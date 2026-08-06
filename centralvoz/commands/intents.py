"""Intencoes reconhecidas pela central."""

from __future__ import annotations

from enum import Enum


class Intent(str, Enum):
    LED_ON = "led_on"
    LED_OFF = "led_off"
    LED_BLINK = "led_blink"

    SERVO_OPEN = "servo_open"
    SERVO_CLOSE = "servo_close"
    SERVO_SWEEP = "servo_sweep"

    DISTANCE_READ = "distance_read"
    DISTANCE_MONITOR = "distance_monitor"

    DICTATION_START = "dictation_start"
    DICTATION_STOP = "dictation_stop"
    NOTES_LIST = "notes_list"
    REPEAT_LAST = "repeat_last"

    CLOCK = "clock"
    SYSTEM_STATUS = "system_status"
    HELP = "help"
    CLEAR = "clear"
    SHUTDOWN = "shutdown"

    UNKNOWN = "unknown"


class AppMode(str, Enum):
    """Modo do loop principal."""

    COMMAND = "command"  # reconhecimento com gramatica restrita
    DICTATION = "dictation"  # reconhecimento livre, texto vai para o LCD
