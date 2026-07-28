from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .base import MockDevice

@dataclass
class LedMatrixController:
    """Controle genérico para matriz de LEDs."""
    mock: bool = False

    def __post_init__(self) -> None:
        self._mock = MockDevice("MATRIX") if self.mock else None
        self._current = ["........" for _ in range(8)]

    def show_pattern(self, pattern: Iterable[str]) -> None:
        rows = list(pattern)
        if len(rows) != 8:
            raise ValueError("O padrão deve conter exatamente 8 linhas.")
        self._current = [row[:8].ljust(8, ".") for row in rows]
        if self._mock:
            self._mock._log("show_pattern")
            for row in self._current:
                self._mock._log(row)
            return
        # Integrar com o driver específico da matriz do kit (MAX7219 ou similar).

    def show_icon(self, name: str) -> None:
        icons = {
            "ok": [
                "........",
                "....#...",
                "...##...",
                "..#.#...",
                ".#..#...",
                "#...#...",
                "........",
                "........",
            ],
            "alerta": [
                "...##...",
                "...##...",
                "...##...",
                "...##...",
                "...##...",
                "........",
                "...##...",
                "........",
            ],
            "casa": [
                "...##...",
                "..#..#..",
                ".#....#.",
                ".#....#.",
                ".######.",
                ".#....#.",
                ".#....#.",
                "........",
            ],
        }
        self.show_pattern(icons.get(name, icons["ok"]))

    def clear(self) -> None:
        self._current = ["........" for _ in range(8)]
        if self._mock:
            self._mock._log("clear")
            return

    def render(self) -> list[str]:
        return list(self._current)
