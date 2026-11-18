"""Sistemas externos simulados: CRM de clientes, tickets y envío de correo.

En producción cada función llamaría a una API real. El grafo solo guarda
referencias (por ejemplo, el id del ticket): separación de responsabilidades.
"""

import json
import uuid
from functools import lru_cache

from soporte import config

BANDEJA_DE_SALIDA: list[dict] = []  # para poder inspeccionar en la demo qué se "envió"


@lru_cache
def _clientes() -> dict:
    return json.loads(config.ARCHIVO_CLIENTES.read_text(encoding="utf-8"))


def historial_de(remitente: str) -> dict:
    return _clientes().get(remitente.lower(), {"contactos_previos": 0, "nota": "Cliente sin historial"})


def crear_ticket(resumen: str, urgencia: str) -> str:
    return f"TCK-{uuid.uuid4().hex[:8].upper()}"


def enviar_correo(destinatario: str, asunto: str, cuerpo: str) -> None:
    BANDEJA_DE_SALIDA.append({"para": destinatario, "asunto": asunto, "cuerpo": cuerpo})
