from __future__ import annotations

class MockDevice:
    """Base para dispositivos simulados."""
    def __init__(self, name: str) -> None:
        self.name = name

    def _log(self, message: str) -> None:
        print(f"[{self.name}] {message}")
