"""Tarefas longas em segundo plano.

Existe por causa de um bug real: o comando "monitorar distancia" rodava um laco
de 15 s **dentro do handler**, bloqueando o loop principal. Tres consequencias:

1. A central ficava surda durante todo o monitoramento.
2. Com gatilho de teclado, cada ENTER apertado nesse intervalo ficava na fila do
   stdin. Ao terminar, o loop consumia todos de uma vez, disparando capturas
   vazias em sequencia -- o "loop" de "Nao ouvi nada" que parecia travamento.
3. Nao havia como cancelar: so restava Ctrl+C.

Agora tarefas longas rodam aqui, com evento de cancelamento, e qualquer comando
novo interrompe a anterior.

Fica no pacote raiz, e nao em `app/`, de proposito: `commands.handlers` precisa
dele, e `app` importa `commands` -- um modulo de tarefas dentro de `app` criaria
um ciclo de importacao.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

logger = logging.getLogger(__name__)

#: A funcao recebe um Event: deve checar `cancel.is_set()` e sair quando marcado.
TaskFunc = Callable[[threading.Event], None]


class BackgroundTask:
    """Uma tarefa longa por vez. Iniciar outra cancela a anterior."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._label = ""

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def label(self) -> str:
        return self._label if self.running else ""

    def start(self, label: str, func: TaskFunc) -> None:
        self.cancel()
        self._cancel = threading.Event()
        self._label = label
        cancel = self._cancel

        def alvo() -> None:
            try:
                func(cancel)
            except Exception:
                logger.exception("Tarefa '%s' falhou", label)

        self._thread = threading.Thread(target=alvo, name=f"task-{label}", daemon=True)
        self._thread.start()
        logger.debug("Tarefa '%s' iniciada", label)

    def cancel(self, timeout: float = 2.0) -> bool:
        """Pede parada e espera. True se havia algo rodando."""
        if not self.running:
            self._label = ""
            return False

        logger.info("Cancelando tarefa '%s'", self._label)
        self._cancel.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=timeout)
            if thread.is_alive():
                logger.warning("Tarefa '%s' nao parou a tempo", self._label)
        self._thread = None
        self._label = ""
        return True
