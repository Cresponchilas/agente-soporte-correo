"""Elige dónde guarda el grafo sus dos memorias: archivos SQLite locales o la RAM.

- Checkpointer (corto plazo): con SQLite, una corrida pausada en revisión humana
  sobrevive a que cierres y vuelvas a abrir el servidor.
- Store (largo plazo): lo que se recuerda de cada cliente, en memoria.sqlite junto
  al archivo de checkpoints.

Ninguno necesita instalar ni configurar una base de datos.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from langgraph.store.sqlite import SqliteStore

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


@asynccontextmanager
async def abrir_store(archivo_checkpoints: Path | None) -> AsyncIterator[BaseStore]:
    """El Store va junto a los checkpoints: si estos van en memoria, el Store también."""
    if archivo_checkpoints is None:
        yield InMemoryStore()
        return

    archivo = archivo_checkpoints.with_name("memoria.sqlite")
    archivo.parent.mkdir(parents=True, exist_ok=True)
    # Un SqliteStore síncrono basta: lo usan nodos síncronos, que LangGraph corre en
    # hilos aparte; por eso la conexión se comparte entre hilos.
    with SqliteStore.from_conn_string(str(archivo)) as store:
        store.setup()
        logger.info("Memoria de largo plazo en %s", archivo)
        yield store
