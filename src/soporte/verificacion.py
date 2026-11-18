"""Búsqueda exacta y verificación determinística (al estilo grep).

El RAG vectorial encuentra textos *parecidos*; eso sirve para preguntas, pero falla
justo con lo que más importa en un catálogo: los códigos exactos. "SI-M12-04P" y
"SI-M12-06P" se parecen mucho como vectores y son piezas distintas (una no existe).

Por eso hay dos pasos con búsqueda literal de texto:

1. Búsqueda exacta (previene): los números de pieza que escribe el cliente se buscan
   tal cual en el catálogo, ANTES de redactar, para que el modelo reciba la ficha
   correcta aunque la búsqueda vectorial no la traiga.
2. Verificación final (detecta): antes de enviar, un piso literal comprueba cada
   número de pieza y dato con unidad del borrador, y un verificador agente (un LLM
   con la herramienta `buscar_en_catalogo`) comprueba lo que la regex no ve. Lo que
   no tiene respaldo manda la respuesta a revisión humana.

Todo aquí son funciones puras: mismas entradas, mismo resultado, sin red. El LLM del
verificador vive en llm.py; aquí solo están su herramienta y las reglas que juzgan
lo que devuelve.
"""

import re
import unicodedata
from typing import Literal

from typing_extensions import NotRequired, TypedDict

from soporte.state import Fragmento

# Un número de pieza: 2 o 3 letras, guion y uno o más bloques alfanuméricos
# separados por guiones. Ej.: SI-M12-04P, SF-R2M-P, RF-50, VN-52-14-24D, FP-24-10.
PATRON_CODIGO = re.compile(r"(?<![A-Z0-9-])[A-Z]{2,3}(?:-[A-Z0-9]+)+(?![A-Z0-9-])")

# Un dato verificable: un número con unidad o un precio en dólares.
_UNIDADES = r"mm|m|VDC|VAC|A|bar|°C|%|días hábiles|días calendario|días|meses"
PATRON_DATO = re.compile(rf"USD\s?\d+(?:[.,]\d+)?|\d+(?:[.,]\d+)?\s?(?:{_UNIDADES})(?![A-Za-z])")
_PRECIO_SUELTO = re.compile(r"(?:US\$|\$)\s?(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s?(?:USD|dólares)")

EstadoAfirmacion = Literal["respaldado", "fuera_de_contexto", "no_encontrado"]


class Afirmacion(TypedDict):
    texto: str
    tipo: Literal["codigo", "dato"]
    estado: EstadoAfirmacion
    fuente: str | None  # sección donde se encontró, si se encontró


Veredicto = Literal["respaldada", "contradicha", "sin_respaldo"]


class AfirmacionRevisada(TypedDict):
    """Una afirmación que el verificador agente eligió comprobar."""

    afirmacion: str
    veredicto: Veredicto
    fuente: str | None
    explicacion: str


class Busqueda(TypedDict):
    termino: str
    fuentes: list[str]
    texto: NotRequired[str]  # lo que leyó el modelo; no se guarda en el estado


class RevisionDelVerificador(TypedDict):
    afirmaciones: list[AfirmacionRevisada]
    busquedas: list[Busqueda]  # registradas por el código, no reportadas por el modelo


class Verificacion(TypedDict):
    aprobada: bool
    afirmaciones: list[Afirmacion]  # el piso literal
    revisadas: list[AfirmacionRevisada]  # lo que eligió comprobar el verificador agente
    busquedas: list[Busqueda]
    error: str | None
    motivos: list[str]  # por qué no se aprueba; vacío si se aprueba


class ResultadoBusquedaExacta(TypedDict):
    codigos: list[str]
    encontrados: dict[str, list[str]]  # código -> fuentes donde aparece
    inexistentes: list[str]


# ---------- Normalización y búsqueda literal ----------


def normalizar(texto: str) -> str:
    """Deja el texto comparable: espacios normales, coma decimal como punto y
    precios escritos de varias formas ("$54", "54 USD") como "USD 54"."""
    texto = unicodedata.normalize("NFC", texto).replace(" ", " ")
    texto = _PRECIO_SUELTO.sub(lambda m: f"USD {m.group(1) or m.group(2)}", texto)
    texto = re.sub(r"(\d),(\d)", r"\1.\2", texto)
    return re.sub(r"\s+", " ", texto)


def contiene(texto: str, termino: str) -> bool:
    """¿Aparece el término en el texto como unidad completa? Así "SI-M12-04P" no
    coincide dentro de "SI-M12-04P-L", ni "8 bar" dentro de "18 bar"."""
    patron = rf"(?<![0-9A-Za-z-]){re.escape(normalizar(termino).casefold())}(?!-?[0-9A-Za-z])"
    return re.search(patron, normalizar(texto).casefold()) is not None


def buscar_en(fragmentos: list[Fragmento], termino: str) -> list[str]:
    """Fuentes de los fragmentos que contienen el término (el "grep"). Primero la sección
    cuyo título es el término (la ficha de la pieza), luego las que solo lo mencionan."""
    fuentes = [f["fuente"] for f in fragmentos if contiene(f["texto"], termino)]
    return sorted(fuentes, key=lambda fuente: not contiene(fuente.split("#")[-1], termino))


# ---------- Extracción ----------


def _sin_repetir(elementos: list[str]) -> list[str]:
    return list(dict.fromkeys(elementos))


def extraer_codigos(texto: str) -> list[str]:
    return _sin_repetir(PATRON_CODIGO.findall(normalizar(texto)))


def extraer_datos(texto: str) -> list[str]:
    return _sin_repetir(m.strip() for m in PATRON_DATO.findall(normalizar(texto)))


# ---------- Paso 1: búsqueda exacta ----------


def busqueda_exacta(correo: str, catalogo: list[Fragmento]) -> tuple[ResultadoBusquedaExacta, list[Fragmento]]:
    """Busca literalmente en el catálogo cada número de pieza del correo del cliente.
    Devuelve el resumen de la búsqueda y las secciones encontradas."""
    codigos = extraer_codigos(correo)
    encontrados = {codigo: buscar_en(catalogo, codigo) for codigo in codigos}
    fuentes = {fuente for lista in encontrados.values() for fuente in lista}
    resultado = ResultadoBusquedaExacta(
        codigos=codigos,
        encontrados={codigo: lista for codigo, lista in encontrados.items() if lista},
        inexistentes=[codigo for codigo, lista in encontrados.items() if not lista],
    )
    return resultado, [f for f in catalogo if f["fuente"] in fuentes]


def combinar_contexto(vectorial: list[Fragmento], exacta: list[Fragmento]) -> list[Fragmento]:
    """Une los resultados de las dos búsquedas sin repetir y marca de dónde salió cada
    fragmento. Los de la búsqueda exacta van primero: son coincidencias seguras."""
    fuentes_vectorial = {f["fuente"] for f in vectorial}
    fuentes_exacta = {f["fuente"] for f in exacta}
    combinados: dict[str, Fragmento] = {}
    for fragmento in [*exacta, *vectorial]:
        fuente = fragmento["fuente"]
        if fuente in combinados:
            continue
        en_ambas = fuente in fuentes_vectorial and fuente in fuentes_exacta
        origen = "ambas" if en_ambas else "exacta" if fuente in fuentes_exacta else "vectorial"
        combinados[fuente] = {**fragmento, "origen": origen}
    return list(combinados.values())


# ---------- Paso 2: verificación final ----------
#
# Tiene dos partes que se suman:
# - el piso literal (sin LLM): todo número de pieza y dato con unidad del borrador
#   tiene que existir en el catálogo. Se comprueba siempre.
# - el verificador agente (LLM con la herramienta buscar_en_catalogo): elige qué más
#   comprobar, como a qué pieza pertenece cada dato o una política de garantía.
# El LLM puede agregar comprobaciones, pero no quitar las del piso, y la decisión
# final (enviar o revisar) la toma este código, no el modelo.


def comprobar_literal(borrador: str, vistos: list[Fragmento], catalogo: list[Fragmento]) -> list[Afirmacion]:
    """El piso: cada número de pieza y dato del borrador, buscado tal cual.

    - respaldado: aparece en lo que vio el modelo (`vistos`).
    - fuera_de_contexto: no estaba en lo que vio, pero sí existe en el catálogo
      (es real, aunque el modelo no tenía cómo saberlo: se informa, no se bloquea).
    - no_encontrado: no aparece en ninguna parte del catálogo: posible invento.
    """
    candidatos = [(c, "codigo") for c in extraer_codigos(borrador)] + [(d, "dato") for d in extraer_datos(borrador)]
    afirmaciones: list[Afirmacion] = []
    for texto, tipo in candidatos:
        en_vistos = buscar_en(vistos, texto)
        en_catalogo = en_vistos or buscar_en(catalogo, texto)
        estado: EstadoAfirmacion = "respaldado" if en_vistos else "fuera_de_contexto" if en_catalogo else "no_encontrado"
        afirmaciones.append(Afirmacion(texto=texto, tipo=tipo, estado=estado, fuente=en_catalogo[0] if en_catalogo else None))
    return afirmaciones


def buscar_en_catalogo(termino: str, catalogo: list[Fragmento], maximo: int = 4) -> Busqueda:
    """La herramienta del verificador: el mismo "grep", con el texto de cada sección
    encontrada para que el modelo pueda comparar. Es determinista: el LLM solo
    decide QUÉ buscar; qué hay en el catálogo lo responde siempre este código."""
    fuentes = buscar_en(catalogo, termino)
    if not fuentes:
        return Busqueda(termino=termino, fuentes=[], texto=f'Sin coincidencias para "{termino}" en el catálogo.')
    por_fuente = {f["fuente"]: f["texto"] for f in catalogo}
    partes = [f"[{fuente}]\n{por_fuente[fuente]}" for fuente in fuentes[:maximo]]
    if len(fuentes) > maximo:
        partes.append(f"(y {len(fuentes) - maximo} secciones más; usa un término más específico)")
    return Busqueda(termino=termino, fuentes=fuentes, texto="\n\n".join(partes))


def validar_revision(revisadas: list[AfirmacionRevisada], busquedas: list[Busqueda]) -> list[AfirmacionRevisada]:
    """No se le cree al LLM sin evidencia: una afirmación solo cuenta como respaldada
    si cita una sección que la herramienta de verdad devolvió en esta verificación."""
    devueltas = {fuente for b in busquedas for fuente in b["fuentes"]}
    validadas = []
    for a in revisadas:
        if a["veredicto"] == "respaldada" and a.get("fuente") not in devueltas:
            a = {**a, "veredicto": "sin_respaldo", "explicacion": "El verificador la dio por buena, pero no citó una sección que haya encontrado."}
        validadas.append(a)
    return validadas


def armar_verificacion(
    piso: list[Afirmacion],
    revision: RevisionDelVerificador,
    codigos_inexistentes: list[str],
    error: str | None = None,
) -> Verificacion:
    """Junta el piso literal, la revisión del agente y la búsqueda exacta en un solo
    resultado, con un motivo por cada problema (sin repetir ninguno)."""
    revisadas = validar_revision(revision["afirmaciones"], revision["busquedas"])

    motivos = [f"El cliente pide {codigo}, que no existe en el catálogo." for codigo in codigos_inexistentes]
    motivos += [
        f"La respuesta menciona {a['texto']}, que no aparece en el catálogo."
        for a in piso
        if a["estado"] == "no_encontrado" and a["texto"] not in codigos_inexistentes  # ya avisado arriba
    ]
    for a in revisadas:
        if a["veredicto"] == "contradicha":
            motivos.append(f"«{a['afirmacion']}» contradice el catálogo: {a['explicacion']}")
        elif a["veredicto"] == "sin_respaldo":
            motivos.append(f"«{a['afirmacion']}» no tiene respaldo en el catálogo.")
    if error:
        # Falla de forma segura: si no se pudo verificar, decide una persona.
        motivos.append("No se pudo completar la revisión del verificador; revísala tú.")

    return Verificacion(
        aprobada=not motivos,
        afirmaciones=piso,
        revisadas=revisadas,
        busquedas=[Busqueda(termino=b["termino"], fuentes=b["fuentes"]) for b in revision["busquedas"]],
        error=error,
        motivos=motivos,
    )
