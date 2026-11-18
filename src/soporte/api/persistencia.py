"""Elige el checkpointer: Postgres si hay DATABASE_URL, memoria si no.

Con Postgres, una corrida pausada en revisión humana sobrevive a reinicios del
servidor (Render reinicia los servicios gratuitos cuando se duermen).
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

logger = logging.getLogger(__name__)

TipoPersistencia = Literal["postgres", "memoria"]


@asynccontextmanager
async def abrir_checkpointer(database_url: str | None) -> AsyncIterator[tuple[BaseCheckpointSaver, TipoPersistencia]]:
    if not database_url:
        logger.warning("DATABASE_URL no está definida: las corridas se guardan en memoria y se pierden al reiniciar.")
        yield InMemorySaver(), "memoria"
        return

    # Imports aquí: psycopg solo hace falta cuando de verdad se usa Postgres.
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    # Un pool (y no una sola conexión) porque bases serverless como Neon cierran las
    # conexiones inactivas; check_connection descarta las muertas antes de usarlas.
    pool = AsyncConnectionPool(
        conninfo=database_url,
        min_size=1,
        max_size=5,
        open=False,
        check=AsyncConnectionPool.check_connection,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    # wait=True: si la base no responde, el servidor falla al arrancar con un error
    # claro, en vez de arrancar "sano" y fallar en la primera corrida.
    await pool.open(wait=True, timeout=30)
    try:
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()  # crea las tablas la primera vez; luego no hace nada
        logger.info("Checkpointer Postgres listo.")
        yield checkpointer, "postgres"
    finally:
        await pool.close()
