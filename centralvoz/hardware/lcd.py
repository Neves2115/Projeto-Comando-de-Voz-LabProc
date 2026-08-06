"""LCD 16x2 com backpack I2C (PCF8574 -> HD44780).

Esse e o modulo de 4 fios do kit Freenove: VCC, GND, SDA (GPIO2), SCL (GPIO3).
Habilite o I2C antes de usar:

    sudo raspi-config   ->  Interface Options  ->  I2C  ->  Yes
    sudo apt install -y i2c-tools python3-smbus2
    i2cdetect -y 1      ->  deve mostrar 27 ou 3f

Alem do driver, esta classe resolve um problema pratico: uma frase ditada nao
cabe em 16x2. `show_text()` quebra o texto em paginas e passa sozinho.
"""

from __future__ import annotations

import threading
import time
from typing import Sequence

from ..utils import fit, paginate
from .base import Peripheral

# --------------------------------------------------------------------------- #
# Comandos do HD44780
# --------------------------------------------------------------------------- #
CMD_CLEAR = 0x01
CMD_HOME = 0x02
CMD_ENTRY_MODE = 0x04
CMD_DISPLAY_CTRL = 0x08
CMD_FUNCTION_SET = 0x20
CMD_SET_DDRAM = 0x80

ENTRY_LEFT = 0x02
DISPLAY_ON = 0x04
MODE_4BIT_2LINE_5x8 = 0x08

# Mapeamento dos bits do PCF8574 (padrao dos backpacks baratos)
BIT_RS = 0x01
BIT_RW = 0x02
BIT_EN = 0x04
BIT_BACKLIGHT = 0x08

ROW_OFFSETS = (0x00, 0x40, 0x14, 0x54)
COMMON_ADDRESSES = (0x27, 0x3F, 0x26, 0x3E, 0x20, 0x38)


class LcdDisplay(Peripheral):
    """Interface comum de display."""

    name = "lcd"

    def __init__(self, cols: int = 16, rows: int = 2, page_delay_s: float = 2.2) -> None:
        self.cols = cols
        self.rows = rows
        self.page_delay_s = page_delay_s
        self._buffer = [" " * cols for _ in range(rows)]
        self._pager: threading.Thread | None = None
        self._stop_pager = threading.Event()
        self._lock = threading.RLock()

    # -- API publica -------------------------------------------------- #

    def clear(self) -> None:
        self._stop_paging()
        with self._lock:
            self._buffer = [" " * self.cols for _ in range(self.rows)]
            self._render(self._buffer)

    def show_lines(self, *lines: str) -> None:
        """Escreve linhas fixas, cortando no tamanho do display."""
        self._stop_paging()
        self._write_page([fit(line, self.cols) for line in lines[: self.rows]])

    def show_text(self, text: str, *, loop: bool = False) -> None:
        """Mostra texto de qualquer tamanho, paginando em segundo plano."""
        self._stop_paging()
        pages = paginate(text, self.cols, self.rows)

        if len(pages) == 1:
            self._write_page(pages[0])
            return

        self._stop_pager.clear()
        self._pager = threading.Thread(
            target=self._page_loop, args=(pages, loop), daemon=True
        )
        self._pager.start()

    def show_status(self, title: str, detail: str = "") -> None:
        """Atalho para o padrao 'titulo em cima, detalhe embaixo'."""
        self.show_lines(title, detail)

    def render(self) -> list[str]:
        """Conteudo atual do display. Usado nos testes."""
        with self._lock:
            return list(self._buffer)

    # -- interno ------------------------------------------------------ #

    def _page_loop(self, pages: Sequence[list[str]], loop: bool) -> None:
        while not self._stop_pager.is_set():
            for page in pages:
                if self._stop_pager.is_set():
                    return
                self._write_page(page)
                if self._stop_pager.wait(self.page_delay_s):
                    return
            if not loop:
                return

    def _stop_paging(self) -> None:
        self._stop_pager.set()
        pager = self._pager
        if pager is not None and pager is not threading.current_thread():
            pager.join(timeout=1.0)
        self._pager = None

    def _write_page(self, lines: Sequence[str]) -> None:
        page = [fit(line, self.cols) for line in lines]
        page += [" " * self.cols] * (self.rows - len(page))
        with self._lock:
            self._buffer = page
            self._render(page)

    def _render(self, lines: Sequence[str]) -> None:  # pragma: no cover
        raise NotImplementedError

    def close(self) -> None:
        self._stop_paging()


class MockLcd(LcdDisplay):
    simulated = True

    def _render(self, lines: Sequence[str]) -> None:
        border = "+" + "-" * self.cols + "+"
        body = "\n".join(f"|{line}|" for line in lines)
        self._log("\n%s\n%s\n%s", border, body, border)


class I2cLcd(LcdDisplay):
    """LCD real via PCF8574."""

    simulated = False

    def __init__(
        self,
        bus_number: int = 1,
        address: int | None = None,
        cols: int = 16,
        rows: int = 2,
        page_delay_s: float = 2.2,
        backlight: bool = True,
    ) -> None:
        super().__init__(cols=cols, rows=rows, page_delay_s=page_delay_s)
        try:
            from smbus2 import SMBus  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "smbus2 nao instalado. Rode: sudo apt install -y python3-smbus2"
            ) from exc

        self._bus = SMBus(bus_number)
        self._backlight = BIT_BACKLIGHT if backlight else 0x00
        self.address = address if address is not None else self._detect_address()
        self._init_display()
        self._log("LCD %dx%d em 0x%02X (bus %d)", cols, rows, self.address, bus_number)

    # -- descoberta de endereco --------------------------------------- #

    def _detect_address(self) -> int:
        for candidate in COMMON_ADDRESSES:
            try:
                self._bus.write_quick(candidate)
                return candidate
            except OSError:
                continue
        raise RuntimeError(
            "Nenhum LCD I2C encontrado. Confira a fiacao e rode `i2cdetect -y 1`. "
            "Se aparecer um endereco diferente, coloque em config.toml: "
            "[lcd] address = '0x3f'"
        )

    # -- camada de bits ----------------------------------------------- #

    def _write_raw(self, value: int) -> None:
        self._bus.write_byte(self.address, value | self._backlight)

    def _pulse(self, value: int) -> None:
        self._write_raw(value | BIT_EN)
        time.sleep(0.0005)
        self._write_raw(value & ~BIT_EN)
        time.sleep(0.0001)

    def _write_nibble(self, value: int) -> None:
        self._write_raw(value)
        self._pulse(value)

    def _send(self, value: int, mode: int = 0) -> None:
        self._write_nibble(mode | (value & 0xF0))
        self._write_nibble(mode | ((value << 4) & 0xF0))

    def _command(self, value: int) -> None:
        self._send(value, mode=0)

    def _data(self, value: int) -> None:
        self._send(value, mode=BIT_RS)

    # -- inicializacao ------------------------------------------------ #

    def _init_display(self) -> None:
        time.sleep(0.05)
        # Sequencia obrigatoria para entrar em modo 4 bits.
        for _ in range(3):
            self._write_nibble(0x30)
            time.sleep(0.005)
        self._write_nibble(0x20)
        time.sleep(0.005)

        self._command(CMD_FUNCTION_SET | MODE_4BIT_2LINE_5x8)
        self._command(CMD_DISPLAY_CTRL | DISPLAY_ON)
        self._command(CMD_CLEAR)
        time.sleep(0.002)
        self._command(CMD_ENTRY_MODE | ENTRY_LEFT)

    # -- render ------------------------------------------------------- #

    def _render(self, lines: Sequence[str]) -> None:
        try:
            for row, line in enumerate(lines[: self.rows]):
                self._command(CMD_SET_DDRAM | ROW_OFFSETS[row])
                for char in line:
                    # O HD44780 nao tem acentos; o texto ja chega normalizado.
                    self._data(ord(char) if ord(char) < 128 else ord("?"))
        except OSError as exc:
            # Um cabo solto nao pode derrubar a central de voz inteira.
            self._log("falha de I2C: %s", exc)

    def set_backlight(self, on: bool) -> None:
        self._backlight = BIT_BACKLIGHT if on else 0x00
        try:
            self._write_raw(0x00)
        except OSError:
            pass

    def close(self) -> None:
        super().close()
        try:
            self._command(CMD_CLEAR)
            self.set_backlight(False)
            self._bus.close()
        except Exception:  # noqa: BLE001
            pass
