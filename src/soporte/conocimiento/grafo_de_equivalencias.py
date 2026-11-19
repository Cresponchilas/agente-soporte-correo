"""El grafo de conocimiento de piezas: qué sustituye a qué, qué necesita qué.

Ojo con la palabra "grafo": este es un grafo de CONOCIMIENTO (cada nodo es una pieza
y cada arista una relación entre piezas). No tiene nada que ver con el grafo de
LangGraph de agente/flujo.py, que es el flujo de control del agente.

Por qué un grafo: hay preguntas que la búsqueda vectorial no responde bien porque la
respuesta está repartida en varios documentos ("varios saltos"). Por ejemplo:

    "Tengo un Proxima PX-12-4P, ¿qué fuente necesito para su reemplazo?"
    PX-12-4P --sustituible_por--> SI-M12-04P <--puede_alimentar-- FP-24-5

De dónde salen las aristas:
- origen "documento": las que solo se saben leyendo el catálogo, como que una pieza
  descontinuada fue reemplazada por otra (data/grafo/relaciones.json).
- origen "regla": las que se CALCULAN desde las especificaciones (data/grafo/
  especificaciones.csv) con una regla determinista, sin LLM. Así ningún modelo
  "adivina" una equivalencia: o las medidas coinciden, o no hay arista.

Con 14 piezas basta un JSON (data/grafo/grafo.json). Si el catálogo creciera a miles
de piezas y relaciones, el siguiente paso sería una base de datos de grafos como
Neo4j, consultada con Cypher (ver el README).

    python -m soporte.conocimiento.grafo_de_equivalencias    # regenera data/grafo/grafo.json
"""

import csv
import json
from functools import lru_cache
from pathlib import Path

from typing_extensions import NotRequired, TypedDict

from soporte import config
from soporte.agente.estado import Fragmento

CARPETA = config.RAIZ / "data" / "grafo"
MARCA_PROPIA = "Andina"  # el distribuidor solo puede ofrecer lo que vende

TIPOS = {
    "reemplazado_por": "fue reemplazado por",  # documento: la pieza se descontinuó
    "sustituible_por": "se puede sustituir por",  # regla: mismas medidas y salida, alimentación que la cubre
    "requiere": "requiere",  # documento: accesorio obligatorio
    "puede_alimentar": "puede alimentar a",  # regla: la tensión de la fuente cae en el rango del sensor
}


class Nodo(TypedDict):
    codigo: str
    marca: str | None
    familia: str | None
    estado: str | None


class Arista(TypedDict):
    de: str
    tipo: str
    a: str
    origen: str  # "documento" o "regla"
    razon: str  # por qué existe: la sección del documento o la regla que se cumplió
    fuente: NotRequired[str]


class Grafo(TypedDict):
    nodos: list[Nodo]
    aristas: list[Arista]


# ---------- Construcción (determinista) ----------


def _numero(valor: str) -> float | None:
    return float(valor) if valor.strip() else None


def leer_especificaciones(ruta: Path) -> list[dict]:
    with ruta.open(encoding="utf-8", newline="") as archivo:
        filas = list(csv.DictReader(archivo))
    for fila in filas:
        for campo in ("distancia_mm", "alimentacion_min_vdc", "alimentacion_max_vdc", "salida_vdc"):
            fila[campo] = _numero(fila[campo])
    return filas


def puede_sustituir(original: dict, candidata: dict) -> str | None:
    """La regla de equivalencia: la candidata sirve en lugar de la original si es una
    pieza activa que vendemos, con la misma forma y función (familia, tamaño, distancia,
    salida, conexión) y acepta al menos el mismo rango de alimentación. Devuelve la
    razón, o None si no sirve.

    Es dirigida: un sensor de 10 a 30 VDC puede sustituir a uno de 12 a 24 VDC, pero
    no al revés (en una máquina de 28 VDC el de 12 a 24 no funcionaría)."""
    if original["codigo"] == candidata["codigo"] or candidata["estado"] != "activo" or candidata["marca"] != MARCA_PROPIA:
        return None
    mismas = ("familia", "tamano", "distancia_mm", "salida", "conexion")
    if any(original[campo] != candidata[campo] for campo in mismas):
        return None
    if None in (original["alimentacion_min_vdc"], candidata["alimentacion_min_vdc"]):
        return None
    cubre = (
        candidata["alimentacion_min_vdc"] <= original["alimentacion_min_vdc"]
        and candidata["alimentacion_max_vdc"] >= original["alimentacion_max_vdc"]
    )
    if not cubre:
        return None
    return (
        f"mismo tamaño {original['tamano']}, {original['distancia_mm']:g} mm, salida {original['salida']}, "
        f"conexión {original['conexion']}; alimentación {candidata['alimentacion_min_vdc']:g} a "
        f"{candidata['alimentacion_max_vdc']:g} VDC cubre {original['alimentacion_min_vdc']:g} a "
        f"{original['alimentacion_max_vdc']:g} VDC"
    )


def puede_alimentar(fuente: dict, sensor: dict) -> str | None:
    if fuente["familia"] != "fuente de poder" or sensor["estado"] != "activo" or sensor["alimentacion_min_vdc"] is None:
        return None
    if sensor["alimentacion_min_vdc"] <= fuente["salida_vdc"] <= sensor["alimentacion_max_vdc"]:
        return (
            f"salida de {fuente['salida_vdc']:g} VDC dentro de {sensor['alimentacion_min_vdc']:g} a "
            f"{sensor['alimentacion_max_vdc']:g} VDC"
        )
    return None


@lru_cache
def especificaciones() -> list[dict]:
    return leer_especificaciones(CARPETA / "especificaciones.csv")


def construir(carpeta: Path = CARPETA) -> Grafo:
    especificaciones = leer_especificaciones(carpeta / "especificaciones.csv")
    documentadas = json.loads((carpeta / "relaciones.json").read_text(encoding="utf-8"))["relaciones"]

    aristas: list[Arista] = [
        Arista(de=r["de"], tipo=r["tipo"], a=r["a"], origen="documento", razon=f"documento: {r['fuente']}", fuente=r["fuente"])
        for r in documentadas
    ]
    ya_documentadas = {(a["de"], a["a"]) for a in aristas}
    for original in especificaciones:
        for otra in especificaciones:
            if (original["codigo"], otra["codigo"]) in ya_documentadas:
                continue  # lo que dice el documento manda; la regla no lo repite
            if razon := puede_sustituir(original, otra):
                aristas.append(Arista(de=original["codigo"], tipo="sustituible_por", a=otra["codigo"], origen="regla", razon=razon))
            if razon := puede_alimentar(original, otra):
                aristas.append(Arista(de=original["codigo"], tipo="puede_alimentar", a=otra["codigo"], origen="regla", razon=razon))

    nodos = {
        e["codigo"]: Nodo(codigo=e["codigo"], marca=e["marca"], familia=e["familia"], estado=e["estado"]) for e in especificaciones
    }
    for arista in aristas:  # piezas que solo aparecen en una relación documentada (RF-50, SF-R15-P)
        for codigo in (arista["de"], arista["a"]):
            nodos.setdefault(codigo, Nodo(codigo=codigo, marca=None, familia=None, estado=None))
    return Grafo(nodos=sorted(nodos.values(), key=lambda n: n["codigo"]), aristas=aristas)


def guardar(grafo: Grafo, ruta: Path = CARPETA / "grafo.json") -> None:
    ruta.write_text(json.dumps(grafo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@lru_cache
def cargar(ruta: Path = CARPETA / "grafo.json") -> Grafo:
    return json.loads(ruta.read_text(encoding="utf-8"))


# ---------- Consultas ----------


def codigos(grafo: Grafo | None = None) -> set[str]:
    return {n["codigo"] for n in (grafo or cargar())["nodos"]}


def vecindario(codigo: str, grafo: Grafo | None = None, saltos_de_sustitucion: int = 2) -> list[Arista]:
    """Las relaciones útiles alrededor de una pieza, recorriendo el grafo:

    1. Sustitutos: se siguen reemplazado_por y sustituible_por hasta 2 saltos (una
       pieza descontinuada -> su reemplazo -> el equivalente de otra marca).
    2. Para cada pieza activa de Andina en ese camino: lo que requiere y las fuentes
       que la alimentan (de una pieza de otra marca no ofrecemos accesorios).

    El recorrido está acotado a propósito: seguir TODAS las aristas en todas las
    direcciones traería medio catálogo (cada fuente alimenta a todos los sensores)."""
    grafo = grafo or cargar()
    salientes: dict[str, list[Arista]] = {}
    entrantes: dict[str, list[Arista]] = {}
    for arista in grafo["aristas"]:
        salientes.setdefault(arista["de"], []).append(arista)
        entrantes.setdefault(arista["a"], []).append(arista)

    encontradas: list[Arista] = []
    piezas, frontera = [codigo], [codigo]
    for _ in range(saltos_de_sustitucion):
        siguiente = []
        for pieza in frontera:
            for arista in salientes.get(pieza, []):
                if arista["tipo"] in ("reemplazado_por", "sustituible_por") and arista["a"] not in piezas:
                    encontradas.append(arista)
                    piezas.append(arista["a"])
                    siguiente.append(arista["a"])
        frontera = siguiente

    nodos = {n["codigo"]: n for n in grafo["nodos"]}
    for pieza in piezas:
        nodo = nodos.get(pieza, {})
        if nodo.get("marca") not in (None, MARCA_PROPIA) or nodo.get("estado") == "descontinuado":
            continue
        encontradas += [a for a in salientes.get(pieza, []) if a["tipo"] == "requiere"]
        encontradas += [a for a in entrantes.get(pieza, []) if a["tipo"] == "puede_alimentar"]
    return encontradas


def como_fragmento(codigo: str, grafo: Grafo | None = None) -> Fragmento | None:
    """Las relaciones de una pieza como texto, para el modelo. None si la pieza no está
    en el grafo (entonces no sabemos nada de ella y es mejor no decir nada)."""
    grafo = grafo or cargar()
    nodo = next((n for n in grafo["nodos"] if n["codigo"] == codigo), None)
    if nodo is None:
        return None
    marca = f" (marca {nodo['marca']})" if nodo["marca"] else ""
    lineas = [f"Relaciones de {codigo}{marca}:"]
    aristas = vecindario(codigo, grafo)
    lineas += [f"- {a['de']} {TIPOS[a['tipo']]} {a['a']} ({a['razon'] if a['origen'] == 'documento' else 'regla: ' + a['razon']})" for a in aristas]
    sustituye = any(a["tipo"] in ("reemplazado_por", "sustituible_por") for a in aristas)
    if nodo["marca"] not in (None, MARCA_PROPIA) and not sustituye:
        lineas.append(f"- Ninguna pieza de Andina sustituye a {codigo}: ninguna coincide en tamaño, distancia, salida y conexión")
    if nodo["estado"] == "descontinuado" and not sustituye:
        lineas.append(f"- {codigo} está descontinuado y no tiene sustituto en el catálogo")
    if len(lineas) == 1:
        return None
    return Fragmento(fuente=f"grafo#{codigo}", texto="\n".join(lineas))


def piezas_relacionadas(codigo: str, grafo: Grafo | None = None) -> list[str]:
    relacionadas = []
    for arista in vecindario(codigo, grafo):
        for pieza in (arista["de"], arista["a"]):
            if pieza != codigo and pieza not in relacionadas:
                relacionadas.append(pieza)
    return relacionadas


def fragmentos_de_todo(grafo: Grafo | None = None) -> list[Fragmento]:
    """Todas las relaciones, para que la verificación pueda comprobar lo que el borrador
    diga sobre ellas."""
    grafo = grafo or cargar()
    return [f for n in grafo["nodos"] if (f := como_fragmento(n["codigo"], grafo))]


if __name__ == "__main__":
    grafo = construir()
    guardar(grafo)
    print(f"Grafo guardado: {len(grafo['nodos'])} piezas y {len(grafo['aristas'])} relaciones en {CARPETA / 'grafo.json'}")
