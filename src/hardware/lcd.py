from __future__ import annotations

from dataclasses import dataclass
from textwrap import wrap

from .base import MockDevice

@dataclass
class LcdDisplay:
    """Interface simples para LCD 16x2/20x4 em modo modular."""
    cols: int = 16
    lines: int = 2
    mock: bool = False

    def __post_init__(self) -> None:
        self._mock = MockDevice("LCD") if self.mock else None
        self._buffer = [" " * self.cols for _ in range(self.lines)]

    def clear(self) -> None:
        self._buffer = [" " * self.cols for _ in range(self.lines)]
        if self._mock:
            self._mock._log("clear")
            return
        # Aqui entra a implementação do driver real (I2C ou paralelo), conforme o hardware do kit.

    def show_message(self, line1: str = "", line2: str = "", clear_first: bool = True) -> None:
        if clear_first:
            self.clear()
        lines = [line1, line2]
        for i in range(min(self.lines, len(lines))):
            self._buffer[i] = (lines[i] or "")[: self.cols].ljust(self.cols)
        if self._mock:
            self._mock._log(f"show_message line1='{line1}' line2='{line2}'")
            return
        # Substituir pelo driver real do LCD.

    def show_centered(self, text: str) -> None:
        lines = wrap(text, self.cols)
        self.show_message(lines[0] if lines else "", lines[1] if len(lines) > 1 else "")

    def render(self) -> list[str]:
        return list(self._buffer)
