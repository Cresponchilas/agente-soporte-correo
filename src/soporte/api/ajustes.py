"""Configuración de la API, leída una sola vez desde variables de entorno."""

import os
from dataclasses import dataclass
from pathlib import Path

from soporte import config

ARCHIVO_CHECKPOINTS_POR_DEFECTO = config.RAIZ / "data" / "checkpoints.sqlite"


@dataclass(frozen=True)
class Ajustes:
    # Archivo SQLite donde el grafo guarda sus checkpoints. None = en memoria
    # (se pierde al cerrar el servidor; útil para tests).
    archivo_checkpoints: Path | None = None

    @classmethod
    def desde_entorno(cls) -> "Ajustes":
        valor = os.getenv("CHECKPOINTS", str(ARCHIVO_CHECKPOINTS_POR_DEFECTO))
        return cls(archivo_checkpoints=None if valor == "memoria" else Path(valor))
