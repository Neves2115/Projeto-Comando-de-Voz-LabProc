"""Matriz de LEDs 8x8 acionada por dois 74HC595 encadeados.

A matriz e multiplexada: so uma linha fica acesa por vez, e a persistencia da
retina faz parecer uma imagem inteira. Por isso existe uma thread de refresh.

Desligada por padrao (`[matrix] enabled = false`) porque a fiacao dos shift
registers muda entre versoes do kit. Confira docs/ligacoes.md antes de ligar.
"""

from __future__ import annotations

import threading
import time
from typing import Iterable, Sequence

from .base import Peripheral

ICONS: dict[str, tuple[str, ...]] = {
    "ok": (
        "........",
        "......#.",
        ".....##.",
        "#...##..",
        "##.##...",
        ".###....",
        "..#.....",
        "........",
    ),
    "alerta": (
        "...##...",
        "...##...",
        "...##...",
        "...##...",
        "...##...",
        "........",
        "...##...",
        "........",
    ),
    "ouvindo": (
        "...##...",
        "..####..",
        "..####..",
        "..####..",
        "...##...",
        "..####..",
        "...##...",
        "........",
    ),
    "erro": (
        "#......#",
        ".#....#.",
        "..#..#..",
        "...##...",
        "...##...",
        "..#..#..",
        ".#....#.",
        "#......#",
    ),
    "coracao": (
        "........",
        ".##..##.",
        "########",
        "########",
        ".######.",
        "..####..",
        "...##...",
        "........",
    ),
    "casa": (
        "...##...",
        "..####..",
        ".######.",
        "########",
        ".#....#.",
        ".#.##.#.",
        ".#.##.#.",
        "........",
    ),
}


def pattern_to_rows(pattern: Iterable[str]) -> list[int]:
    """Converte 8 strings de '#'/'.' em 8 bytes."""
    rows: list[int] = []
    for line in pattern:
        value = 0
        for column, char in enumerate(line[:8].ljust(8, ".")):
            if char not in ".  0":
                value |= 1 << (7 - column)
        rows.append(value)
    if len(rows) != 8:
        raise ValueError("O padrao precisa ter exatamente 8 linhas.")
    return rows


class LedMatrix(Peripheral):
    name = "matriz"

    def __init__(self) -> None:
        self._rows = [0] * 8

    def show_pattern(self, pattern: Iterable[str]) -> None:
        self.show_rows(pattern_to_rows(pattern))

    def show_rows(self, rows: Sequence[int]) -> None:
        self._rows = list(rows)[:8]
        self._apply()

    def show_icon(self, name: str) -> None:
        self.show_pattern(ICONS.get(name, ICONS["ok"]))

    def clear(self) -> None:
        self.show_rows([0] * 8)

    def render(self) -> list[str]:
        return [
            "".join("#" if row & (1 << (7 - col)) else "." for col in range(8))
            for row in self._rows
        ]

    def _apply(self) -> None:
        pass

    def close(self) -> None:
        self.clear()


class MockMatrix(LedMatrix):
    simulated = True

    def _apply(self) -> None:
        self._log("\n%s", "\n".join(self.render()))


class ShiftRegisterMatrix(LedMatrix):
    """Bit-bang em dois 74HC595 (um para colunas, um para linhas)."""

    simulated = False

    def __init__(
        self,
        data_pin: int,
        clock_pin: int,
        latch_pin: int,
        gpiozero_module,
        refresh_hz: float = 160.0,
    ) -> None:
        super().__init__()
        self._ser = gpiozero_module.OutputDevice(data_pin)
        self._srclk = gpiozero_module.OutputDevice(clock_pin)
        self._rclk = gpiozero_module.OutputDevice(latch_pin)
        self._frame_time = 1.0 / max(30.0, refresh_hz)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._thread.start()
        self._log("data=%s clock=%s latch=%s", data_pin, clock_pin, latch_pin)

    def _shift_out(self, byte: int) -> None:
        for bit in range(8):
            self._ser.value = (byte >> (7 - bit)) & 1
            self._srclk.on()
            self._srclk.off()

    def _refresh_loop(self) -> None:
        row_time = self._frame_time / 8.0
        while not self._stop.is_set():
            with self._lock:
                rows = list(self._rows)
            for index, value in enumerate(rows):
                if self._stop.is_set():
                    break
                try:
                    self._shift_out(value)                     # colunas (anodo)
                    self._shift_out(~(1 << index) & 0xFF)      # linha ativa em nivel baixo
                    self._rclk.on()
                    self._rclk.off()
                except Exception:
                    self._stop.set()
                    break
                time.sleep(row_time)

    def show_rows(self, rows: Sequence[int]) -> None:
        with self._lock:
            self._rows = list(rows)[:8]

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)
        for device in (self._ser, self._srclk, self._rclk):
            try:
                device.off()
                device.close()
            except Exception:
                pass
