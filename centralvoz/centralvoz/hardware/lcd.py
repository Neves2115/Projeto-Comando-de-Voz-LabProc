"""LCD 16x2 com backpack I2C (PCF8574 -> HD44780).

Esse e o modulo de 4 fios do kit Freenove: VCC, GND, SDA (GPIO2), SCL (GPIO3).
Habilite o I2C antes de usar:

    sudo raspi-config   ->  Interface Options  ->  I2C  ->  Yes
    sudo apt install -y i2c-tools python3-smbus2
    i2cdetect -y 1      ->  deve mostrar 27 ou 3f

Alem do driver, esta classe resolve um problema pratico: uma frase ditada nao
cabe em 16x2. `show_text()` quebra o texto em paginas e passa sozinho.

ARQUITETURA -- por que existe uma thread de escrita
====================================================
Escrever uma tela inteira custa ~32 caracteres x 4 transacoes I2C cada. Antes
isso rodava na thread que chamava `show_lines()` -- ou seja, no loop principal
-- segurando um lock durante todas as escritas.

Se o barramento I2C engasga (contencao entre threads, clock stretching do
PCF8574, um jumper mal encaixado), a escrita nao retorna. O lock nunca e
liberado e QUALQUER `show_lines()` posterior, de qualquer thread, bloqueia para
sempre. Na pratica: o display congelava em "Processando..." e a central inteira
parava junto -- o travamento visto no monitoramento de distancia.

Agora `show_lines()` e `show_text()` apenas publicam o quadro desejado e
retornam na hora. Uma unica thread consome a fila e escreve no barramento. Se o
I2C travar, quem trava e essa thread: o resto do programa segue vivo, o tempo de
escrita e monitorado e o driver tenta reinicializar o display.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Sequence

from ..utils import fit, paginate
from .base import Peripheral

logger = logging.getLogger(__name__)

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

#: Acima disso, considera-se que o barramento engasgou.
SLOW_WRITE_S = 1.5


class LcdDisplay(Peripheral):
    """Interface comum de display.

    Contrato importante: nenhum metodo publico bloqueia por I/O. O quadro e
    publicado numa fila e escrito por outra thread.
    """

    name = "lcd"

    def __init__(self, cols: int = 16, rows: int = 2, page_delay_s: float = 2.2) -> None:
        self.cols = cols
        self.rows = rows
        self.page_delay_s = page_delay_s

        self._buffer = [" " * cols for _ in range(rows)]
        self._buffer_lock = threading.Lock()  # protege so o buffer, nunca o I/O

        # Fila de tamanho 1: quadro novo substitui o antigo ainda nao escrito.
        # Nao adianta desenhar telas que ja estao desatualizadas.
        self._frames: queue.Queue[list[str]] = queue.Queue(maxsize=1)
        self._stop = threading.Event()
        self._writer = threading.Thread(
            target=self._writer_loop, name="lcd-writer", daemon=True
        )
        self._writer.start()

        self._pager: threading.Thread | None = None
        self._stop_pager = threading.Event()

    # -- API publica -------------------------------------------------- #

    def clear(self) -> None:
        self._stop_paging()
        self._publish([" " * self.cols for _ in range(self.rows)])

    def show_lines(self, *lines: str) -> None:
        """Escreve linhas fixas, cortando no tamanho do display."""
        self._stop_paging()
        self._publish([fit(line, self.cols) for line in lines[: self.rows]])

    def show_text(self, text: str, *, loop: bool = False) -> None:
        """Mostra texto de qualquer tamanho, paginando em segundo plano."""
        self._stop_paging()
        pages = paginate(text, self.cols, self.rows)

        if len(pages) == 1:
            self._publish(pages[0])
            return

        # Evento novo a cada paginacao: assim `_stop_paging` nunca precisa
        # esperar a thread antiga terminar para liberar quem chamou.
        self._stop_pager = threading.Event()
        self._pager = threading.Thread(
            target=self._page_loop,
            args=(pages, loop, self._stop_pager),
            name="lcd-pager",
            daemon=True,
        )
        self._pager.start()

    def show_status(self, title: str, detail: str = "") -> None:
        """Atalho para o padrao 'titulo em cima, detalhe embaixo'."""
        self.show_lines(title, detail)

    def render(self) -> list[str]:
        """Conteudo atual do display. Usado nos testes."""
        with self._buffer_lock:
            return list(self._buffer)

    def flush(self, timeout: float = 2.0) -> bool:
        """Espera o quadro pendente ser escrito. Usado nos testes e no selftest."""
        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            if self._frames.empty():
                return True
            time.sleep(0.02)
        return False

    # -- interno ------------------------------------------------------ #

    def _publish(self, lines: Sequence[str]) -> None:
        """Registra o quadro e acorda a thread de escrita. NUNCA bloqueia."""
        page = [fit(line, self.cols) for line in lines]
        page += [" " * self.cols] * (self.rows - len(page))

        with self._buffer_lock:
            self._buffer = page

        # Descarta o quadro anterior ainda nao escrito: so o mais recente importa.
        try:
            self._frames.get_nowait()
        except queue.Empty:
            pass
        try:
            self._frames.put_nowait(page)
        except queue.Full:  # pragma: no cover - corrida rara, quadro seguinte cobre
            pass

    def _writer_loop(self) -> None:
        while not self._stop.is_set():
            try:
                page = self._frames.get(timeout=0.2)
            except queue.Empty:
                continue

            inicio = time.monotonic()
            try:
                self._render(page)
            except Exception as exc:  # noqa: BLE001 - I/O nunca derruba o programa
                logger.warning("Falha ao escrever no LCD: %s", exc)
                self._on_write_error(exc)

            gasto = time.monotonic() - inicio
            if gasto > SLOW_WRITE_S:
                logger.warning(
                    "Escrita no LCD levou %.1f s (barramento I2C engasgado?)", gasto
                )

    def _page_loop(
        self, pages: Sequence[list[str]], loop: bool, stop: threading.Event
    ) -> None:
        while not stop.is_set():
            for page in pages:
                if stop.is_set():
                    return
                self._publish(page)
                if stop.wait(self.page_delay_s):
                    return
            if not loop:
                return

    def _stop_paging(self) -> None:
        """Sinaliza a paginacao para parar. Nao espera: ela e daemon."""
        self._stop_pager.set()
        self._pager = None

    def _render(self, lines: Sequence[str]) -> None:  # pragma: no cover
        raise NotImplementedError

    def _on_write_error(self, exc: Exception) -> None:
        """Gancho para o driver real tentar se recuperar."""

    def close(self) -> None:
        self._stop_paging()
        self._stop.set()
        if self._writer.is_alive() and self._writer is not threading.current_thread():
            self._writer.join(timeout=2.0)


class MockLcd(LcdDisplay):
    simulated = True

    def _render(self, lines: Sequence[str]) -> None:
        border = "+" + "-" * self.cols + "+"
        body = "\n".join(f"|{line}|" for line in lines)
        self._log("\n%s\n%s\n%s", border, body, border)


class I2cLcd(LcdDisplay):
    """LCD real via PCF8574."""

    simulated = False

    #: Erros consecutivos antes de tentar reinicializar o display.
    MAX_ERRORS = 3

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
            from smbus2 import SMBus
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "smbus2 nao instalado. Rode: sudo apt install -y python3-smbus2"
            ) from exc

        self._bus = SMBus(bus_number)
        self._backlight = BIT_BACKLIGHT if backlight else 0x00
        self.address = address if address is not None else self._detect_address()
        self._init_display()
        self._log_setup("LCD %dx%d em 0x%02X (bus %d)", cols, rows, self.address, bus_number)

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
        except Exception:
            pass
