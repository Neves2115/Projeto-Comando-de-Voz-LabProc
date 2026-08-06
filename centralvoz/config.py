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

    leds: tuple[int, ...] = (17,)
    servo: int = 18  # GPIO18 = pino de PWM por hardware, o melhor para servo
    button: int = 26  # botao push-to-talk, ligado entre o GPIO e o GND
    distance_trigger: int = 23
    distance_echo: int = 24  # ATENCAO: use divisor de tensao, o echo do HC-SR04 e 5V
    # Matriz 8x8 com dois 74HC595 encadeados (opcional).
    matrix_data: int = 5
    matrix_clock: int = 6
    matrix_latch: int = 13


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
    # Desligado por padrao: a fiacao dos 74HC595 varia entre versoes do kit.
    # Ligue depois de conferir os pinos em docs/ligacoes.md.
    enabled: bool = False
    refresh_hz: float = 160.0


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
    monitor_duration_s: float = 15.0
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
