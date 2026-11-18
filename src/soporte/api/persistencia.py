"""Elige el checkpointer: un archivo SQLite local o la memoria.

Con SQLite, una corrida pausada en revisión humana sobrevive a que cierres y
vuelvas a abrir el servidor, sin instalar ni configurar ninguna base de datos.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

logger = logging.getLogger(__name__)

TipoPersistencia = Literal["sqlite", "memoria"]


@asynccontextmanager
async def abrir_checkpointer(archivo: Path | None) -> AsyncIterator[tuple[BaseCheckpointSaver, TipoPersistencia]]:
    if archivo is None:
        logger.warning("Checkpoints en memoria: las corridas se pierden al reiniciar el servidor.")
        yield InMemorySaver(), "memoria"
        return

    archivo.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(archivo)) as checkpointer:
        await checkpointer.setup()  # crea las tablas la primera vez
        logger.info("Checkpoints en %s", archivo)
        yield checkpointer, "sqlite"
