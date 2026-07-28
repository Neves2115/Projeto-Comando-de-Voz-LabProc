from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path

def normalize_text(text: str) -> str:
    """Normaliza texto para comparação de comandos."""
    text = text.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
