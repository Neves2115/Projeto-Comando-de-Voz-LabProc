"""Configuracao unica do projeto.

Regra de ouro: existe *um* lugar que decide se o hardware e real ou simulado.
A precedencia e:  argumento de linha de comando > variavel de ambiente > config.toml > default.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_FILE = Path("config.toml")


@dataclass
class PinConfig:
    """Numeracao BCM (a mesma que o gpiozero usa)."""

    # LED RGB do kit Freenove. Comum em 3,3 V => anodo comum (acende em LOW).
    rgb_red: int = 5
    rgb_green: int = 6
    rgb_blue: int = 13
    #: True se o seu modulo for de catodo comum (comum no GND).
    rgb_active_high: bool = False
    servo: int = 18  # GPIO18 = pino de PWM por hardware, o melhor para servo
    button: int = 26  # botao push-to-talk, ligado entre o GPIO e o GND
    # Buzzers do kit. O ativo so liga/desliga; o passivo toca notas (precisa PWM).
    buzzer_active: int = 12
    buzzer_passive: int = 4
    #: Alguns modulos de buzzer ativo acionam em nivel BAIXO.
    buzzer_active_high: bool = True

    # ATENCAO: GPIO14 e GPIO15 sao o UART (TXD/RXD). Funcionam como GPIO comum,
    # mas so depois de desativar o console serial:
    #     sudo raspi-config -> Interface Options -> Serial Port
    #     login shell = No,  hardware serial = Yes/No (tanto faz aqui)
    # Sem isso o kernel fica falando pela TXD e o sensor le lixo.
    distance_trigger: int = 14
    distance_echo: int = 15  # use divisor de tensao: o echo do HC-SR04 e 5V
    # Matriz 8x8 com dois 74HC595 encadeados.
    matrix_data: int = 22   # DS   / SER
    matrix_clock: int = 17  # SHCP / SRCLK
    matrix_latch: int = 27  # STCP / RCLK


    def used_pins(self) -> dict[str, int]:
        """Mapa nome -> GPIO de tudo que ocupa um pino."""
        return {
            "rgb_red": self.rgb_red,
            "rgb_green": self.rgb_green,
            "rgb_blue": self.rgb_blue,
            "servo": self.servo,
            "button": self.button,
            "buzzer_active": self.buzzer_active,
            "buzzer_passive": self.buzzer_passive,
            "distance_trigger": self.distance_trigger,
            "distance_echo": self.distance_echo,
            "matrix_data": self.matrix_data,
            "matrix_clock": self.matrix_clock,
            "matrix_latch": self.matrix_latch,
        }

    def conflicts(self) -> list[str]:
        """Problemas de pinagem, em linguagem humana.

        Dois perifericos no mesmo GPIO nao da erro nenhum ao iniciar: o
        programa sobe normalmente e os dois simplesmente se atrapalham. Por
        isso a checagem e explicita.
        """
        problemas: list[str] = []
        usados = self.used_pins()

        por_pino: dict[int, list[str]] = {}
        for nome, pino in usados.items():
            por_pino.setdefault(pino, []).append(nome)

        for pino, nomes in sorted(por_pino.items()):
            if len(nomes) > 1:
                problemas.append(
                    f"GPIO{pino} esta atribuido a {' e '.join(nomes)} ao mesmo tempo."
                )

        for nome, pino in usados.items():
            if pino in (2, 3):
                problemas.append(
                    f"{nome} usa GPIO{pino}, que e exclusivo do I2C (LCD)."
                )
            if pino in (14, 15):
                problemas.append(
                    f"{nome} usa GPIO{pino} (UART). Desative o console serial em "
                    "raspi-config, senao o kernel interfere no sinal."
                )
        return problemas


@dataclass
class LcdConfig:
    enabled: bool = True
    i2c_bus: int = 1
    address: int | None = None  # None = descobre sozinho (0x27 ou 0x3F)
    cols: int = 16
    rows: int = 2
    backlight: bool = True
    page_delay_s: float = 2.2  # tempo de cada pagina quando o texto nao cabe


@dataclass
class MatrixConfig:
    enabled: bool = True
    refresh_hz: float = 160.0


@dataclass
class BuzzerConfig:
    active_enabled: bool = True
    passive_enabled: bool = True
    #: Som ao confirmar comando, ao errar e ao alertar.
    feedback_sounds: bool = True


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    block_size: int = 4000  # ~250 ms por bloco a 16 kHz
    input_device: int | str | None = None  # None = dispositivo padrao do sistema
    max_utterance_s: float = 12.0
    min_utterance_s: float = 0.35


@dataclass
class SpeechConfig:
    model_path: Path = field(
        default_factory=lambda: Path("models/vosk-model-small-pt-0.3")
    )
    # Restringe o vocabulario do Vosk aos comandos conhecidos. Melhora MUITO a
    # acuracia no modelo small. E desligado automaticamente no modo ditado.
    use_grammar: bool = True
    # Similaridade minima (0..1) para aceitar um comando reconhecido.
    match_threshold: float = 0.70


@dataclass
class BehaviorConfig:
    servo_open_angle: float = 90.0
    servo_closed_angle: float = 0.0
    distance_warning_cm: float = 20.0
    monitor_duration_s: float = 20.0
    party_duration_s: float = 12.0
    color_cycle_step_s: float = 0.35
    dictation_timeout_s: float = 45.0


@dataclass
class AppConfig:
    mock: bool = False
    # None = escolhe sozinho (lgpio primeiro). Outras opcoes: "pigpio", "native".
    pin_factory: str | None = None
    # "button" = botao fisico no GPIO; "keyboard" = ENTER no teclado.
    # Use "keyboard" enquanto o botao ainda nao estiver soldado/ligado.
    trigger: str = "button"
    log_dir: Path = field(default_factory=lambda: Path("logs"))
    db_path: Path = field(default_factory=lambda: Path("logs/centralvoz.sqlite3"))
    recordings_dir: Path = field(default_factory=lambda: Path("recordings"))
    save_recordings: bool = False
    log_level: str = "INFO"

    pins: PinConfig = field(default_factory=PinConfig)
    lcd: LcdConfig = field(default_factory=LcdConfig)
    matrix: MatrixConfig = field(default_factory=MatrixConfig)
    buzzer: BuzzerConfig = field(default_factory=BuzzerConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    speech: SpeechConfig = field(default_factory=SpeechConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)

    # ------------------------------------------------------------------ #

    @classmethod
    def load(
        cls,
        path: Path | None = None,
        *,
        overrides: dict[str, Any] | None = None,
    ) -> "AppConfig":
        """Monta a configuracao a partir de config.toml + env + overrides."""
        config = cls()

        path = path or DEFAULT_CONFIG_FILE
        if path.is_file():
            with path.open("rb") as handle:
                _apply(config, tomllib.load(handle))

        _apply(config, _env_overrides())

        if overrides:
            _apply(config, {k: v for k, v in overrides.items() if v is not None})

        return config


def _env_overrides() -> dict[str, Any]:
    """Le as variaveis CENTRALVOZ_* mais uteis."""
    env: dict[str, Any] = {}
    if (value := os.environ.get("CENTRALVOZ_MOCK")) is not None:
        env["mock"] = value.strip().lower() in {"1", "true", "yes", "sim"}
    if value := os.environ.get("CENTRALVOZ_PIN_FACTORY"):
        env["pin_factory"] = value
    if value := os.environ.get("CENTRALVOZ_TRIGGER"):
        env["trigger"] = value
    if value := os.environ.get("CENTRALVOZ_MODEL"):
        env["speech"] = {"model_path": value}
    if value := os.environ.get("CENTRALVOZ_LOG_LEVEL"):
        env["log_level"] = value
    return env


def _apply(target: Any, data: dict[str, Any]) -> None:
    """Aplica um dicionario aninhado sobre uma arvore de dataclasses."""
    valid = {f.name: f for f in fields(target)}
    for key, value in data.items():
        if key not in valid:
            raise ValueError(f"Chave de configuracao desconhecida: {key!r}")

        current = getattr(target, key)
        if is_dataclass(current) and isinstance(value, dict):
            _apply(current, value)
            continue

        setattr(target, key, _coerce(valid[key].type, value))


def _coerce(annotation: Any, value: Any) -> Any:
    """Converte os poucos tipos que o TOML nao representa nativamente."""
    text = str(annotation)
    if "Path" in text and isinstance(value, str):
        return Path(value)
    if "tuple[int" in text and isinstance(value, (list, tuple)):
        return tuple(int(v) for v in value)
    if "int | None" in text and isinstance(value, str):
        # permite address = "0x27" no TOML
        return int(value, 0)
    return value
