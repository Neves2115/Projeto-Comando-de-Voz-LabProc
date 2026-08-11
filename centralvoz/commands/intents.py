"""Intencoes reconhecidas pela central."""

from __future__ import annotations

from enum import Enum


class Intent(str, Enum):
    LED_ON = "led_on"
    LED_COLOR = "led_color"
    LED_CYCLE = "led_cycle"
    LED_BRIGHTNESS = "led_brightness"
    LED_OFF = "led_off"
    LED_BLINK = "led_blink"
    LED_BLINK_N = "led_blink_n"

    SERVO_OPEN = "servo_open"
    SERVO_CLOSE = "servo_close"
    SERVO_SWEEP = "servo_sweep"
    SERVO_ANGLE = "servo_angle"

    DISTANCE_READ = "distance_read"
    DISTANCE_MONITOR = "distance_monitor"
    STOP_TASK = "stop_task"

    DICTATION_START = "dictation_start"
    DICTATION_STOP = "dictation_stop"
    NOTES_LIST = "notes_list"
    NOTES_CLEAR = "notes_clear"
    REPEAT_LAST = "repeat_last"

    CLOCK = "clock"
    SYSTEM_STATUS = "system_status"
    HELP = "help"
    PARTY_MODE = "party_mode"
    MATRIX_DRAW = "matrix_draw"
    CLEAR = "clear"
    SHUTDOWN = "shutdown"

    UNKNOWN = "unknown"


class AppMode(str, Enum):
    """Modo do loop principal."""

    COMMAND = "command"  # reconhecimento com gramatica restrita
    DICTATION = "dictation"  # reconhecimento livre, texto vai para o LCD
