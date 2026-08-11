"""Buzzers do kit Freenove: um ativo e um passivo.

A diferenca importa e muda o codigo:

* **Ativo** tem oscilador proprio. Ligou, apita -- sempre na mesma frequencia.
  So da para controlar *quando* e *por quanto tempo*. Um `DigitalOutputDevice`
  resolve.
* **Passivo** e so uma bobina: nao apita sozinho. Voce precisa entregar uma onda
  quadrada na frequencia desejada. Isso permite tocar notas e melodias, e exige
  PWM (`TonalBuzzer` do gpiozero).

Os dois modulos do kit tem transistor embutido, entao o GPIO so chaveia a base.

Toda reproducao roda em thread daemon cancelavel: um alarme de 10 s nao pode
prender o loop principal -- foi exatamente esse tipo de bloqueio que travou o
sensor de distancia antes.
"""

from __future__ import annotations

import threading
from typing import Iterable, Sequence

from .base import Peripheral

#: Frequencias em Hz da quarta e quinta oitavas. Suficiente para as melodias
#: curtas que um buzzer de kit consegue reproduzir sem soar horrivel.
NOTES: dict[str, float] = {
    "do": 261.63, "do#": 277.18, "re": 293.66, "re#": 311.13,
    "mi": 329.63, "fa": 349.23, "fa#": 369.99, "sol": 392.00,
    "sol#": 415.30, "la": 440.00, "la#": 466.16, "si": 493.88,
    "do5": 523.25, "re5": 587.33, "mi5": 659.25, "fa5": 698.46,
    "sol5": 783.99, "la5": 880.00, "si5": 987.77, "do6": 1046.50,
    "pausa": 0.0,
}

#: Melodias como (nota, duracao em segundos).
Melody = Sequence[tuple[str, float]]

MELODIES: dict[str, Melody] = {
    # Sobe rapido: confirmacao de comando aceito.
    "ok": (("do5", 0.09), ("mi5", 0.09), ("sol5", 0.14)),
    # Desce: algo deu errado.
    "erro": (("sol", 0.12), ("re", 0.18)),
    # Dois bipes agudos, urgentes.
    "alerta": (("la5", 0.1), ("pausa", 0.05), ("la5", 0.1)),
    # Sirene curta para o modo alarme.
    "alarme": (
        ("do5", 0.12), ("sol5", 0.12), ("do5", 0.12), ("sol5", 0.12),
        ("do5", 0.12), ("sol5", 0.12),
    ),
    # Escala completa: bom para testar o buzzer passivo.
    "escala": (
        ("do", 0.15), ("re", 0.15), ("mi", 0.15), ("fa", 0.15),
        ("sol", 0.15), ("la", 0.15), ("si", 0.15), ("do5", 0.3),
    ),
    # Parabens pra voce, primeira frase.
    "parabens": (
        ("do", 0.2), ("do", 0.15), ("re", 0.4), ("do", 0.4),
        ("fa", 0.4), ("mi", 0.7), ("pausa", 0.15),
        ("do", 0.2), ("do", 0.15), ("re", 0.4), ("do", 0.4),
        ("sol", 0.4), ("fa", 0.7),
    ),
    # Fanfarra do modo festa.
    "festa": (
        ("do5", 0.12), ("mi5", 0.12), ("sol5", 0.12), ("do6", 0.25),
        ("sol5", 0.12), ("do6", 0.4),
    ),
    # Toque de despedida.
    "tchau": (("sol5", 0.15), ("mi5", 0.15), ("do5", 0.35)),
}


class Buzzer(Peripheral):
    """Interface comum. `tonal=False` quando o hardware so liga e desliga."""

    name = "buzzer"

    #: True quando o buzzer consegue reproduzir frequencias distintas.
    tonal = False

    def __init__(self) -> None:
        self._playing: threading.Thread | None = None
        self._stop = threading.Event()

    # -- API ------------------------------------------------------------ #

    def beep(self, times: int = 1, on_time: float = 0.1, off_time: float = 0.1) -> None:
        """Bipes simples. Funciona nos dois tipos de buzzer."""
        self.stop()
        self._stop.clear()
        for indice in range(max(1, times)):
            if self._stop.is_set():
                break
            self._tone_on(NOTES["la5"])
            if self._stop.wait(on_time):
                break
            self._tone_off()
            if indice < times - 1 and self._stop.wait(off_time):
                break
        self._tone_off()

    def beep_async(self, **kwargs) -> None:
        self._run(lambda: self.beep(**kwargs))

    def play(self, melody: Melody | str, repeat: int = 1) -> None:
        """Toca uma melodia (bloqueia). Num buzzer ativo, vira bipes ritmados."""
        notas = MELODIES.get(melody, ()) if isinstance(melody, str) else melody
        if not notas:
            return

        self._stop.clear()
        for _ in range(max(1, repeat)):
            for nome, duracao in notas:
                if self._stop.is_set():
                    self._tone_off()
                    return
                frequencia = NOTES.get(nome, 0.0)
                if frequencia > 0:
                    self._tone_on(frequencia)
                else:
                    self._tone_off()
                if self._stop.wait(duracao):
                    self._tone_off()
                    return
                self._tone_off()
                # Silencio curto entre notas: sem isso elas se fundem.
                if self._stop.wait(0.02):
                    return
        self._tone_off()

    def play_async(self, melody: Melody | str, repeat: int = 1) -> None:
        self.stop()
        self._run(lambda: self.play(melody, repeat))

    def stop(self) -> None:
        """Interrompe o que estiver tocando."""
        self._stop.set()
        tocando = self._playing
        if tocando is not None and tocando is not threading.current_thread():
            tocando.join(timeout=1.5)
        self._playing = None
        self._tone_off()
        self._stop.clear()

    # -- interno --------------------------------------------------------- #

    def _run(self, alvo) -> None:
        self._playing = threading.Thread(target=alvo, daemon=True, name="buzzer")
        self._playing.start()

    def _tone_on(self, frequency: float) -> None:  # pragma: no cover
        raise NotImplementedError

    def _tone_off(self) -> None:  # pragma: no cover
        raise NotImplementedError

    def close(self) -> None:
        self.stop()


class MockBuzzer(Buzzer):
    simulated = True
    tonal = True

    def __init__(self) -> None:
        super().__init__()
        #: Historico de frequencias tocadas, para os testes conferirem.
        self.history: list[float] = []

    def _tone_on(self, frequency: float) -> None:
        self.history.append(frequency)
        self._log("tom %.1f Hz", frequency)

    def _tone_off(self) -> None:
        pass


class ActiveBuzzer(Buzzer):
    """Buzzer ativo: oscilador proprio, so liga e desliga."""

    simulated = False
    tonal = False

    def __init__(self, pin: int, gpiozero_module, active_high: bool = True) -> None:
        super().__init__()
        self.pin = pin
        self._device = gpiozero_module.DigitalOutputDevice(
            pin, active_high=active_high, initial_value=False
        )
        self._log_setup("ativo no pino %s", pin)

    def _tone_on(self, _frequency: float) -> None:
        # A frequencia e ignorada: quem define o tom e o oscilador interno.
        self._device.on()

    def _tone_off(self) -> None:
        self._device.off()

    def close(self) -> None:
        super().close()
        try:
            self._device.close()
        except Exception:  # noqa: BLE001
            pass


class PassiveBuzzer(Buzzer):
    """Buzzer passivo: precisa de PWM, entao consegue tocar notas."""

    simulated = False
    tonal = True

    def __init__(self, pin: int, gpiozero_module) -> None:
        super().__init__()
        self.pin = pin
        # PWMOutputDevice em vez de TonalBuzzer: o TonalBuzzer limita a faixa a
        # uma oitava em torno de um tom central, o que corta as melodias.
        self._device = gpiozero_module.PWMOutputDevice(pin, frequency=440, initial_value=0)
        self._log_setup("passivo no pino %s", pin)

    def _tone_on(self, frequency: float) -> None:
        if frequency <= 0:
            self._tone_off()
            return
        try:
            self._device.frequency = int(frequency)
            # 50% de ciclo ativo = onda quadrada, o volume maximo do passivo.
            self._device.value = 0.5
        except Exception:  # noqa: BLE001
            self._tone_off()

    def _tone_off(self) -> None:
        try:
            self._device.value = 0
        except Exception:  # noqa: BLE001
            pass

    def close(self) -> None:
        super().close()
        try:
            self._device.close()
        except Exception:  # noqa: BLE001
            pass


class BuzzerPair(Peripheral):
    """Os dois buzzers juntos, com a escolha automatica de qual usar.

    Melodia com notas vai para o passivo (o unico que consegue toca-las).
    Bipe simples vai para o ativo, que e mais alto e mais seco.
    Se so um estiver configurado, ele faz tudo.
    """

    name = "buzzers"

    def __init__(self, active: Buzzer | None, passive: Buzzer | None) -> None:
        self.active = active
        self.passive = passive
        self.simulated = all(
            b.simulated for b in (active, passive) if b is not None
        )

    @property
    def available(self) -> bool:
        return self.active is not None or self.passive is not None

    def beep(self, times: int = 1, **kwargs) -> None:
        alvo = self.active or self.passive
        if alvo is not None:
            alvo.beep_async(times=times, **kwargs)

    def play(self, melody: Melody | str, repeat: int = 1) -> None:
        # Prefere o passivo: e o unico que reproduz as notas de verdade.
        alvo = self.passive or self.active
        if alvo is not None:
            alvo.play_async(melody, repeat)

    def stop(self) -> None:
        for buzzer in (self.active, self.passive):
            if buzzer is not None:
                buzzer.stop()

    def close(self) -> None:
        for buzzer in (self.active, self.passive):
            if buzzer is not None:
                buzzer.close()


def melody_from_notes(notes: Iterable[str], duration: float = 0.2) -> Melody:
    """Monta uma melodia a partir de nomes de notas, todas com a mesma duracao."""
    return tuple((nome, duration) for nome in notes if nome in NOTES)
