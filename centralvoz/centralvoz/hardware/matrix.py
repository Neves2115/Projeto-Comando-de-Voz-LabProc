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
    # Rosto sorrindo.
    "sorriso": (
        "..####..",
        ".#....#.",
        "#.#..#.#",
        "#......#",
        "#.#..#.#",
        "#..##..#",
        ".#....#.",
        "..####..",
    ),
    "triste": (
        "..####..",
        ".#....#.",
        "#.#..#.#",
        "#......#",
        "#..##..#",
        "#.#..#.#",
        ".#....#.",
        "..####..",
    ),
    "estrela": (
        "...##...",
        "...##...",
        "########",
        ".######.",
        "..####..",
        ".##..##.",
        ".#....#.",
        "........",
    ),
    "seta": (
        "...##...",
        "..####..",
        ".######.",
        "####.###",
        "...##...",
        "...##...",
        "...##...",
        "........",
    ),
    "gato": (
        "##....##",
        "###..###",
        "########",
        "#.####.#",
        "########",
        "#.#..#.#",
        "##.##.##",
        ".######.",
    ),
    "musica": (
        "....###.",
        "....#..#",
        "....###.",
        "....#...",
        "....#...",
        "..###...",
        ".####...",
        "..##....",
    ),
}

#: Nomes alternativos aceitos na fala. "carinha feliz" -> icone sorriso.
ICON_ALIASES: dict[str, str] = {
    "sorrindo": "sorriso",
    "feliz": "sorriso",
    "sorridente": "sorriso",
    "rosto": "sorriso",
    "carinha": "sorriso",
    "infeliz": "triste",
    "chateado": "triste",
    "nota": "musica",
    "flecha": "seta",
    "certo": "ok",
    "coracaozinho": "coracao",
}


def resolve_icon(spoken: str) -> str | None:
    """Encontra o icone citado numa frase ja normalizada (sem acento)."""
    for nome in ICONS:
        if nome in spoken:
            return nome
    for alias, nome in ICON_ALIASES.items():
        if alias in spoken:
            return nome
    return None


def rotate_ccw(rows: Sequence[int]) -> list[int]:
    """Gira 90 graus no sentido anti-horario.

    Cada linha e um byte cujo bit 7 (mais significativo) e a coluna 0.
    A formula da rotacao anti-horaria e:

        novo[i][j] = antigo[j][N - 1 - i]

    Conferindo com o canto superior esquerdo: novo[7][0] = antigo[0][0], ou
    seja, o canto de cima desce para baixo -- que e o que a rotacao
    anti-horaria faz.

    A rotacao e aplicada UMA vez, na hora de renderizar, e nao nos padroes de
    ICONS. Assim nenhum desenho pode ficar para tras quando outro for
    adicionado, e os padroes continuam legiveis no codigo-fonte.
    """
    linhas = list(rows)[:8]
    linhas += [0] * (8 - len(linhas))

    saida = []
    for i in range(8):
        valor = 0
        for j in range(8):
            if linhas[j] & (1 << (7 - (7 - i))):
                valor |= 1 << (7 - j)
        saida.append(valor)
    return saida


def rotate(rows: Sequence[int], quarter_turns: int) -> list[int]:
    """Aplica N giros de 90 graus no anti-horario (0 a 3)."""
    resultado = list(rows)
    for _ in range(quarter_turns % 4):
        resultado = rotate_ccw(resultado)
    return resultado


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

    def __init__(self, quarter_turns: int = 1) -> None:
        """`quarter_turns` = giros de 90 graus no anti-horario ao renderizar.

        Padrao 1 porque a placa fica de lado na bancada. Ajuste em config.toml:
            [matrix]
            quarter_turns = 0
        """
        self._rows = [0] * 8
        self.quarter_turns = quarter_turns % 4

    def show_pattern(self, pattern: Iterable[str]) -> None:
        self.show_rows(pattern_to_rows(pattern))

    def show_rows(self, rows: Sequence[int]) -> None:
        """Guarda o padrao ja orientado para a placa.

        A rotacao acontece aqui, num unico ponto: quem chama continua pensando
        no desenho como ele aparece no codigo.
        """
        self._rows = rotate(list(rows)[:8], self.quarter_turns)
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
        quarter_turns: int = 1,
    ) -> None:
        super().__init__(quarter_turns=quarter_turns)
        self._ser = gpiozero_module.OutputDevice(data_pin)
        self._srclk = gpiozero_module.OutputDevice(clock_pin)
        self._rclk = gpiozero_module.OutputDevice(latch_pin)
        self._frame_time = 1.0 / max(30.0, refresh_hz)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._thread.start()
        self._log_setup("data=%s clock=%s latch=%s", data_pin, clock_pin, latch_pin)

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
        girado = rotate(list(rows)[:8], self.quarter_turns)
        with self._lock:
            self._rows = girado

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)
        for device in (self._ser, self._srclk, self._rclk):
            try:
                device.off()
                device.close()
            except Exception:
                pass
