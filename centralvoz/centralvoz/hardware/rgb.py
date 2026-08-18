"""LED RGB do kit Freenove (modulo de anodo comum).

Ligacao usada por este projeto:

    R -> GPIO5     G -> GPIO6     B -> GPIO13     comum -> 3,3 V

Como o terminal comum vai no 3,3 V, o modulo e de **anodo comum**: o LED acende
quando o GPIO vai para nivel BAIXO. E por isso que `active_high=False` aparece
na construcao do `RGBLED` -- sem isso as cores saem invertidas (voce pede
vermelho e acende ciano).

Os tres pinos usam PWM por software, o que permite misturar cores. Nenhum deles
e pino de PWM por hardware, mas para LED isso nao importa: um jitter de alguns
microssegundos e invisivel. (Para servo importaria.)
"""

from __future__ import annotations

import threading
import time
from typing import Iterable

from .base import Peripheral

#: Cores nomeadas, em fracoes de 0..1 por canal (R, G, B).
#: As "misturadas" existem porque sao os pedidos mais naturais em voz:
#: ninguem diz "cem por cento vermelho e cinquenta por cento verde", diz laranja.
COLORS: dict[str, tuple[float, float, float]] = {
    "vermelho": (1.0, 0.0, 0.0),
    "verde": (0.0, 1.0, 0.0),
    "azul": (0.0, 0.0, 1.0),
    "amarelo": (1.0, 1.0, 0.0),      # vermelho + verde
    "ciano": (0.0, 1.0, 1.0),        # verde + azul
    "magenta": (1.0, 0.0, 1.0),      # vermelho + azul
    "rosa": (1.0, 0.35, 0.55),
    "laranja": (1.0, 0.45, 0.0),
    "roxo": (0.5, 0.0, 1.0),
    "violeta": (0.6, 0.1, 0.9),
    "turquesa": (0.1, 0.9, 0.7),
    "lima": (0.6, 1.0, 0.0),
    "branco": (1.0, 1.0, 1.0),
    "dourado": (1.0, 0.75, 0.1),
    "preto": (0.0, 0.0, 0.0),        # apagado
}

#: Ordem usada pelo ciclo de cores do modo festa.
RAINBOW = (
    "vermelho", "laranja", "amarelo", "lima", "verde",
    "turquesa", "ciano", "azul", "roxo", "magenta", "rosa",
)


def resolve_color(name: str) -> tuple[float, float, float] | None:
    """Cor pelo nome, tolerando plural e genero ('vermelha', 'azuis')."""
    if not name:
        return None
    chave = name.strip().lower()
    if chave in COLORS:
        return COLORS[chave]
    # "vermelha" -> "vermelho", "amarela" -> "amarelo"
    for sufixo, troca in (("a", "o"), ("as", "o"), ("os", "o"), ("es", "")):
        if chave.endswith(sufixo):
            tentativa = chave[: -len(sufixo)] + troca
            if tentativa in COLORS:
                return COLORS[tentativa]
    return None


class RgbLed(Peripheral):
    """LED RGB com mistura de cores. Substitui o LED simples do GPIO17."""

    name = "rgb"

    def __init__(self, red_pin: int, green_pin: int, blue_pin: int) -> None:
        self.pins = (red_pin, green_pin, blue_pin)
        self._color = (0.0, 0.0, 0.0)
        self._color_name = "preto"
        #: Fator de brilho (0..1) aplicado sobre o matiz atual.
        #: Guardado separado da cor para que "brilho 50%" seguido de "acender
        #: verde" mantenha os 50%, e para que mudar o brilho nao destrua a cor.
        self._brightness = 1.0
        self._effect: threading.Thread | None = None
        self._stop_effect = threading.Event()

    # -- estado -------------------------------------------------------- #

    @property
    def is_on(self) -> bool:
        return any(canal > 0 for canal in self._color)

    @property
    def color(self) -> tuple[float, float, float]:
        return self._color

    @property
    def color_name(self) -> str:
        return self._color_name

    # -- API ----------------------------------------------------------- #

    def set_color(self, color: tuple[float, float, float], name: str = "") -> None:
        self.stop_effect()
        self._set_color_raw(color, name)

    @property
    def brightness_level(self) -> float:
        return self._brightness

    def set_named(self, name: str) -> bool:
        """Acende uma cor pelo nome, no brilho corrente. False se nao existe."""
        cor = resolve_color(name)
        if cor is None:
            return False
        self.set_color(tuple(c * self._brightness for c in cor), name.lower())
        return True

    def on(self) -> None:
        """Sem cor definida, acende branco -- e o que 'ligar led' espera."""
        if self.is_on:
            return
        self.set_named("branco")

    def off(self) -> None:
        self.stop_effect()
        # O brilho volta ao maximo: senao "desligar" e depois "ligar" acenderia
        # fraco sem motivo aparente.
        self._brightness = 1.0
        self._set_color_raw((0.0, 0.0, 0.0), "preto")

    def toggle(self) -> None:
        self.off() if self.is_on else self.on()

    def brightness(self, factor: float) -> None:
        """Ajusta o brilho (0..1) preservando o matiz.

        Se a luz estiver apagada, acende em branco no brilho pedido. Antes,
        pedir brilho com o LED apagado escalava preto -- e preto vezes qualquer
        coisa continua preto, entao *qualquer* porcentagem parecia apagar a luz.
        """
        self._brightness = max(0.0, min(1.0, float(factor)))

        nome = self._color_name
        if nome == "preto" or not any(self._color):
            nome = "branco"

        base = resolve_color(nome) or (1.0, 1.0, 1.0)
        self._set_color_raw(
            tuple(canal * self._brightness for canal in base), nome
        )

    # -- efeitos em segundo plano -------------------------------------- #

    def blink(
        self,
        on_time: float = 0.15,
        off_time: float = 0.15,
        times: int = 3,
        color: str = "",
    ) -> None:
        """Pisca de forma sincrona (bloqueia)."""
        # Prioridade: a cor pedida no comando > a cor acesa > branco.
        pedida = resolve_color(color) if color else None
        if pedida is not None:
            alvo = tuple(canal * self._brightness for canal in pedida)
            nome = color.lower()
        elif self.is_on:
            alvo, nome = self._color, self._color_name
        else:
            alvo = tuple(canal * self._brightness for canal in COLORS["branco"])
            nome = "branco"

        anterior, nome_anterior = self._color, self._color_name

        for _ in range(max(1, times)):
            if self._stop_effect.is_set():
                break
            self._set_color_raw(alvo, nome)
            if self._stop_effect.wait(on_time):
                break
            self._set_color_raw((0.0, 0.0, 0.0), "preto")
            if self._stop_effect.wait(off_time):
                break
        self._set_color_raw(anterior, nome_anterior)

    def blink_async(self, **kwargs) -> None:
        self._run_effect(lambda: self.blink(**kwargs))

    def cycle(
        self,
        colors: Iterable[str] = RAINBOW,
        step_s: float = 0.35,
        duration_s: float = 6.0,
    ) -> None:
        """Passa por uma sequencia de cores ate acabar o tempo (bloqueia)."""
        paleta = [c for c in colors if resolve_color(c)]
        if not paleta:
            return
        fim = time.monotonic() + duration_s
        indice = 0
        while time.monotonic() < fim and not self._stop_effect.is_set():
            nome = paleta[indice % len(paleta)]
            self._set_color_raw(COLORS[nome], nome)
            indice += 1
            if self._stop_effect.wait(step_s):
                return

    def cycle_async(self, **kwargs) -> None:
        self._run_effect(lambda: self.cycle(**kwargs))

    def fade(self, start: str, stop: str, duration_s: float = 2.0, steps: int = 40) -> None:
        """Transicao suave entre duas cores (bloqueia)."""
        origem = resolve_color(start) or (0.0, 0.0, 0.0)
        destino = resolve_color(stop) or (0.0, 0.0, 0.0)
        pausa = duration_s / max(1, steps)
        for passo in range(steps + 1):
            if self._stop_effect.is_set():
                return
            fracao = passo / steps
            atual = tuple(
                origem[i] + (destino[i] - origem[i]) * fracao for i in range(3)
            )
            self._set_color_raw(atual, stop)
            time.sleep(pausa)

    def _run_effect(self, alvo) -> None:
        self.stop_effect()
        self._stop_effect.clear()
        self._effect = threading.Thread(target=alvo, daemon=True)
        self._effect.start()

    def stop_effect(self) -> None:
        """Interrompe qualquer efeito em andamento."""
        self._stop_effect.set()
        efeito = self._effect
        if efeito is not None and efeito is not threading.current_thread():
            efeito.join(timeout=1.5)
        self._effect = None
        self._stop_effect.clear()

    # -- interno ------------------------------------------------------- #

    def _set_color_raw(self, color: tuple[float, float, float], name: str = "") -> None:
        color = tuple(max(0.0, min(1.0, float(canal))) for canal in color)
        self._color = color
        if name:
            self._color_name = name
        self._apply(color)

    def _apply(self, color: tuple[float, float, float]) -> None:  # pragma: no cover
        raise NotImplementedError

    def close(self) -> None:
        self.stop_effect()
        self.off()


class MockRgbLed(RgbLed):
    simulated = True

    def _apply(self, color: tuple[float, float, float]) -> None:
        r, g, b = (int(canal * 255) for canal in color)
        self._log("pinos %s -> %s rgb(%3d,%3d,%3d)", self.pins, self._color_name, r, g, b)


class GpioRgbLed(RgbLed):
    simulated = False

    def __init__(
        self,
        red_pin: int,
        green_pin: int,
        blue_pin: int,
        gpiozero_module,
        active_high: bool = False,
    ) -> None:
        super().__init__(red_pin, green_pin, blue_pin)
        self._device = gpiozero_module.RGBLED(
            red=red_pin,
            green=green_pin,
            blue=blue_pin,
            active_high=active_high,  # False = anodo comum (comum no 3,3 V)
            pwm=True,
        )
        self._log(
            "R=%s G=%s B=%s (%s)",
            red_pin,
            green_pin,
            blue_pin,
            "anodo comum" if not active_high else "catodo comum",
        )
        self.off()

    def _apply(self, color: tuple[float, float, float]) -> None:
        try:
            self._device.color = color
        except Exception as exc:
            self._log("falha ao aplicar cor: %s", exc)

    def close(self) -> None:
        self.stop_effect()
        try:
            self._device.off()
            self._device.close()
        except Exception:
            pass
