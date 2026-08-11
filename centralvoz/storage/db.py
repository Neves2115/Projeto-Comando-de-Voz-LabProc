"""Persistencia local em SQLite.

Atende o requisito do relatorio: "Registrar eventos em arquivo local ou SQLite".
Guarda tambem as transcricoes do modo ditado, que viram os "recados".
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..utils import ensure_dir

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,
    kind        TEXT    NOT NULL,
    intent      TEXT,
    heard       TEXT,
    score       REAL,
    result      TEXT
);

CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,
    text        TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
CREATE INDEX IF NOT EXISTS idx_notes_created  ON notes(created_at);
"""


@dataclass(frozen=True)
class Note:
    id: int
    created_at: datetime
    text: str


class Storage:
    """Wrapper fino sobre o sqlite3. Nunca derruba a aplicacao por erro de I/O."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: sqlite3.Connection | None = None

    def open(self) -> "Storage":
        try:
            ensure_dir(self.path.parent)
            self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
            logger.debug("Banco aberto em %s", self.path)
        except sqlite3.Error as exc:
            logger.warning("Sem persistencia: %s", exc)
            self._conn = None
        return self

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Storage":
        return self.open()

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ---------------------------------------------------------------- #

    def log_event(
        self,
        kind: str,
        *,
        intent: str | None = None,
        heard: str | None = None,
        score: float | None = None,
        result: str | None = None,
    ) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(
                "INSERT INTO events (created_at, kind, intent, heard, score, result)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (datetime.now().isoformat(timespec="seconds"), kind, intent, heard, score, result),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.warning("Falha ao gravar evento: %s", exc)

    def add_note(self, text: str) -> int | None:
        if self._conn is None or not text.strip():
            return None
        try:
            cursor = self._conn.execute(
                "INSERT INTO notes (created_at, text) VALUES (?, ?)",
                (datetime.now().isoformat(timespec="seconds"), text.strip()),
            )
            self._conn.commit()
            return int(cursor.lastrowid or 0)
        except sqlite3.Error as exc:
            logger.warning("Falha ao gravar recado: %s", exc)
            return None

    def recent_notes(self, limit: int = 5) -> list[Note]:
        if self._conn is None:
            return []
        try:
            rows = self._conn.execute(
                "SELECT id, created_at, text FROM notes ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        except sqlite3.Error as exc:
            logger.warning("Falha ao ler recados: %s", exc)
            return []
        return [
            Note(id=row[0], created_at=datetime.fromisoformat(row[1]), text=row[2])
            for row in rows
        ]

    def clear_notes(self) -> int:
        """Apaga todos os recados e devolve quantos foram removidos."""
        if self._conn is None:
            return 0
        try:
            total = self.count_notes()
            self._conn.execute("DELETE FROM notes")
            self._conn.commit()
            return total
        except sqlite3.Error as exc:
            logger.warning("Falha ao apagar recados: %s", exc)
            return 0

    def count_notes(self) -> int:
        if self._conn is None:
            return 0
        try:
            return int(self._conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0])
        except sqlite3.Error:
            return 0
