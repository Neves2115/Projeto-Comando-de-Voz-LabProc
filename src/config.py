from dataclasses import dataclass, field
from pathlib import Path

@dataclass(slots=True)
class AppConfig:
    """Configurações gerais do projeto."""
    use_mock_hardware: bool = False
    log_dir: Path = field(default_factory=lambda: Path("logs"))
    record_dir: Path = field(default_factory=lambda: Path("recordings"))
    voice_language: str = "pt"
    vosk_model_path: Path = field(default_factory=lambda: Path("models/vosk-small-pt"))
    wake_word: str = "pi"
    servo_open_angle: float = 90.0
    servo_closed_angle: float = 0.0
    distance_warning_cm: float = 20.0
    lcd_lines: int = 2
    lcd_cols: int = 16
