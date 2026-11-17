"""Configuración de la API, leída una sola vez desde variables de entorno."""

import os
from dataclasses import dataclass, field


def _lista(valor: str) -> list[str]:
    return [parte.strip().rstrip("/") for parte in valor.split(",") if parte.strip()]


@dataclass(frozen=True)
class Ajustes:
    # Orígenes que pueden llamar a la API desde el navegador (CORS).
    origenes_permitidos: list[str] = field(default_factory=lambda: ["http://localhost:3000"])
    # Si está vacío, el checkpointer vive en memoria (se pierde al reiniciar).
    database_url: str | None = None
    # Protección de costos: la demo es pública y cada correo gasta tokens de OpenAI.
    corridas_por_ip_por_hora: int = 15
    corridas_por_dia: int = 300

    @classmethod
    def desde_entorno(cls) -> "Ajustes":
        return cls(
            origenes_permitidos=_lista(os.getenv("FRONTEND_ORIGINS", "http://localhost:3000")),
            database_url=os.getenv("DATABASE_URL") or None,
            corridas_por_ip_por_hora=int(os.getenv("CORRIDAS_POR_IP_POR_HORA", "15")),
            corridas_por_dia=int(os.getenv("CORRIDAS_POR_DIA", "300")),
        )
