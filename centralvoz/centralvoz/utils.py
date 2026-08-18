"""Funcoes auxiliares sem dependencia de hardware."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path
from textwrap import wrap

_NON_ALNUM = re.compile(r"[^a-z0-9\s]")
_SPACES = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Minusculas, sem acento e sem pontuacao. Usado em toda comparacao."""
    text = unicodedata.normalize("NFKD", text.strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = _NON_ALNUM.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def to_ascii(text: str) -> str:
    """Remove acentos preservando maiusculas e pontuacao.

    O controlador HD44780 do LCD nao tem 'ç' nem vogais acentuadas na ROM.
    """
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return "".join(ch if ord(ch) < 128 else "?" for ch in stripped)


_NON_WORD_ACCENTED = re.compile(r"[^0-9a-zà-öø-ÿ\s]", re.IGNORECASE)


def for_grammar(text: str) -> str:
    """Minusculas e sem pontuacao, MAS preservando os acentos.

    A gramatica do Vosk so funciona com palavras que existem no lexico do
    modelo. O modelo de portugues tem "coracao" grafado como "coração": mandar
    a versao sem acento cria uma palavra desconhecida, que o decodificador
    nunca consegue produzir -- e que pode fazer o Vosk rejeitar a gramatica
    inteira.

    Por isso a normalizacao agressiva (`normalize_text`, que tira acentos) serve
    para COMPARAR o que foi ouvido, e esta aqui serve para MONTAR a gramatica.
    """
    limpo = _NON_WORD_ACCENTED.sub(" ", (text or "").strip().lower())
    return _SPACES.sub(" ", limpo).strip()


def tokens(text: str) -> list[str]:
    normalized = normalize_text(text)
    return normalized.split() if normalized else []


def timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def fit(text: str, width: int) -> str:
    """Corta e completa com espacos para caber exatamente em `width` colunas."""
    return (text or "")[:width].ljust(width)


def paginate(text: str, cols: int, rows: int) -> list[list[str]]:
    """Quebra um texto longo em paginas de `rows` linhas de `cols` colunas.

    Usado pelo LCD: uma frase ditada quase nunca cabe em 16x2.
    """
    if not text or not text.strip():
        return [[""] * rows]

    lines = wrap(text.strip(), cols) or [""]
    pages: list[list[str]] = []
    for index in range(0, len(lines), rows):
        page = lines[index : index + rows]
        page += [""] * (rows - len(page))
        pages.append(page)
    return pages


def humanize_seconds(seconds: float) -> str:
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"
