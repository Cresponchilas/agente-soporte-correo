"""Memoria de largo plazo por cliente, con el Store de LangGraph.

Corto plazo vs. largo plazo:
- Corto plazo: el estado de UN hilo (un correo), guardado por el checkpointer con su
  thread_id. Permite pausar y reanudar esa corrida. Un correo nuevo es un hilo nuevo
  y empieza vacío.
- Largo plazo: lo que sobrevive ENTRE hilos. Vive en un Store, organizado por
  namespace (como carpetas) y key. Aquí: ("clientes", <id del cliente>).

Qué se recuerda (memoria semántica: hechos sobre el cliente):
- "piezas": cuántas veces consultó cada pieza.
- "preferencias": un patrón, como "siempre pide salida PNP". Un solo correo no dice
  "siempre": se concluye solo con varias consultas que coinciden, y lo calcula el
  código desde las especificaciones, no el LLM.

Cuándo se escribe: SOLO después de enviar la respuesta (directo o aprobada por una
persona). Si el revisor la rechaza, no se recuerda nada: no se guarda lo que no se
confirmó. En producción esto podría correr en un proceso aparte, en segundo plano;
aquí es el último nodo, después de enviar, así que no retrasa la respuesta.

El id del cliente es el dominio de su correo con "_" en vez de puntos ("empresa_com"):
los namespaces del Store no aceptan puntos, y así la llave no guarda el correo de una
persona.
"""

import re
from collections import Counter
from datetime import UTC, datetime

from langgraph.store.base import BaseStore
from typing_extensions import TypedDict

from soporte.conocimiento import grafo_de_equivalencias

NAMESPACE = "clientes"
MINIMO_PARA_PREFERENCIA = 2  # con una sola consulta no hay patrón


class MemoriaCliente(TypedDict, total=False):
    piezas: dict[str, int]  # código -> veces que lo consultó
    preferencias: dict[str, str]  # p. ej. {"salida": "PNP"}
    actualizada: str


def id_cliente(remitente: str) -> str:
    dominio = remitente.strip().lower().rsplit("@", 1)[-1]
    return re.sub(r"[^a-z0-9]+", "_", dominio).strip("_")


def leer(store: BaseStore | None, remitente: str) -> MemoriaCliente:
    if store is None:  # el grafo se compiló sin Store (por ejemplo, en algunos tests)
        return MemoriaCliente()
    memoria = MemoriaCliente()
    for item in store.search((NAMESPACE, id_cliente(remitente))):
        memoria[item.key] = item.value
    return memoria


def consolidar(piezas: dict[str, int]) -> dict[str, str]:
    """De las piezas consultadas, saca los patrones que ya se pueden afirmar. Por ahora
    uno: la salida (PNP o NPN) de los sensores, si todas las consultas coinciden."""
    salida_de = {e["codigo"]: e["salida"] for e in grafo_de_equivalencias.especificaciones() if e["salida"]}
    salidas = Counter()
    for codigo, veces in piezas.items():
        if codigo in salida_de:
            salidas[salida_de[codigo]] += veces
    if len(salidas) == 1:
        salida, veces = salidas.most_common(1)[0]
        if veces >= MINIMO_PARA_PREFERENCIA:
            return {"salida": salida}
    return {}


def recordar(store: BaseStore, remitente: str, codigos: list[str]) -> MemoriaCliente:
    """Suma las piezas de este correo a lo que ya se sabía y recalcula las preferencias.
    Las llaves son fijas ("piezas", "preferencias"): cada escritura REEMPLAZA el valor,
    así una preferencia que cambia se actualiza en vez de duplicarse."""
    namespace = (NAMESPACE, id_cliente(remitente))
    piezas = Counter(leer(store, remitente).get("piezas", {}))
    piezas.update(codigos)
    preferencias = consolidar(dict(piezas))
    store.put(namespace, "piezas", dict(piezas))
    store.put(namespace, "preferencias", preferencias)
    store.put(namespace, "actualizada", {"fecha": datetime.now(UTC).date().isoformat()})
    return MemoriaCliente(piezas=dict(piezas), preferencias=preferencias)


def como_texto(memoria: MemoriaCliente) -> str:
    if not memoria.get("piezas"):
        return "Sin consultas anteriores registradas."
    piezas = ", ".join(f"{codigo} ({veces} {'vez' if veces == 1 else 'veces'})" for codigo, veces in memoria["piezas"].items())
    texto = f"Piezas consultadas antes: {piezas}."
    if salida := memoria.get("preferencias", {}).get("salida"):
        texto += f" Suele pedir sensores con salida {salida}."
    return texto
