"""Traduce lo que emite el grafo (stream_mode="tasks") a eventos para el dashboard.

Con "tasks", LangGraph avisa dos veces por cada nodo: cuando arranca y cuando
termina (con lo que escribió, su error o sus interrupciones). Eso permite mostrar
en vivo qué nodo está corriendo y cuánto tardó cada uno, incluso los paralelos.

Tipos de evento que recibe el frontend:
- inicio:      se creó o reanudó la corrida (trae el thread_id).
- nodo_inicio: un nodo empezó.
- nodo_fin:    un nodo terminó; trae qué escribió en el estado y cuánto tardó.
- pausa:       el grafo se detuvo en revisión humana; trae lo que el revisor necesita.
- fin:         el grafo terminó o quedó pausado; trae el resumen del estado.
- error:       algo falló; trae un mensaje para mostrar al usuario.
"""

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import openai


def ahora_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def evento_sse(tipo: str, datos: dict[str, Any]) -> str:
    """Formato Server-Sent Events: una línea 'event', una 'data' y una línea en blanco."""
    cuerpo = json.dumps({"tipo": tipo, "momento": ahora_iso(), **datos}, ensure_ascii=False, default=str)
    return f"event: {tipo}\ndata: {cuerpo}\n\n"


class TraductorDeTareas:
    """Convierte cada evento de tarea en eventos del dashboard y mide duraciones."""

    def __init__(self, reloj: Callable[[], float] = time.perf_counter):
        self._reloj = reloj
        self._inicios: dict[str, float] = {}

    def traducir(self, tarea: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        id_tarea, nodo = tarea["id"], tarea["name"]
        es_inicio = "result" not in tarea and "error" not in tarea

        if es_inicio:
            self._inicios[id_tarea] = self._reloj()
            return [("nodo_inicio", {"id": id_tarea, "nodo": nodo})]

        ahora = self._reloj()
        inicio = self._inicios.pop(id_tarea, ahora)
        duracion_ms = round((ahora - inicio) * 1000)
        eventos: list[tuple[str, dict[str, Any]]] = [
            (
                "nodo_fin",
                {
                    "id": id_tarea,
                    "nodo": nodo,
                    "actualizacion": tarea.get("result") or {},
                    "duracion_ms": duracion_ms,
                    "fallo": tarea.get("error") is not None,
                },
            )
        ]
        for interrupcion in tarea.get("interrupts") or []:
            eventos.append(("pausa", {"nodo": nodo, "solicitud": interrupcion["value"]}))
        return eventos


def resumen_del_estado(valores: dict[str, Any], siguientes: tuple[str, ...]) -> dict[str, Any]:
    return {
        "clasificacion": valores.get("clasificacion"),
        "fragmentos": valores.get("fragmentos", []),
        "historial_cliente": valores.get("historial_cliente"),
        "ticket_id": valores.get("ticket_id"),
        "borrador": valores.get("borrador"),
        "decision_humana": valores.get("decision_humana"),
        "enviado": bool(valores.get("enviado")),
        "pasos": valores.get("pasos", []),
        "pausado_en": list(siguientes),
    }


def mensaje_para_usuario(error: BaseException) -> str:
    """Convierte excepciones en mensajes útiles, sin filtrar detalles internos."""
    if isinstance(error, openai.AuthenticationError):
        return "La llave de OpenAI del servidor no es válida."
    if isinstance(error, openai.RateLimitError):
        return "OpenAI rechazó la solicitud por límite de uso o cuota agotada."
    if isinstance(error, (openai.APITimeoutError, openai.APIConnectionError)):
        return "No se pudo contactar al modelo. Intenta de nuevo en un momento."
    if isinstance(error, ValueError):
        return str(error)
    return "Error interno procesando el correo."
