"""Verificación final del borrador, antes de enviarlo.

Tiene dos capas que se suman:
- el piso literal (sin LLM): todo número de pieza y dato con unidad del borrador
  tiene que existir en el catálogo. Se comprueba siempre;
- el verificador agente (agente/verificador.py): un LLM con la herramienta
  buscar_en_catalogo elige qué más comprobar, como a qué pieza pertenece cada dato.

Este módulo tiene el piso, la herramienta y las reglas que juzgan lo que devuelve el
verificador agente. El LLM puede agregar comprobaciones, pero no quitar las del piso,
y la decisión final (enviar o revisar) la toma este código, no el modelo.
"""

from typing import Literal

from typing_extensions import NotRequired, TypedDict

from soporte.agente.estado import Fragmento
from soporte.conocimiento.busqueda import buscar_en, extraer_codigos, extraer_datos

EstadoAfirmacion = Literal["respaldado", "fuera_de_contexto", "del_correo", "no_encontrado"]


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


def comprobar_literal(
    borrador: str, vistos: list[Fragmento], catalogo: list[Fragmento], correo: str = ""
) -> list[Afirmacion]:
    """El piso: cada número de pieza y dato del borrador, buscado tal cual.

    - respaldado: aparece en lo que vio el modelo (`vistos`).
    - fuera_de_contexto: no estaba en lo que vio, pero sí existe en el catálogo o el
      inventario (es real, aunque el modelo no lo vio: se informa, no se bloquea).
    - del_correo: un dato que no está en las fuentes pero lo escribió el cliente, como
      "necesito 4 unidades". Repetirlo no es inventar; se informa, no se bloquea. Si
      el cliente cita un dato falso, lo detecta el verificador agente, no este piso.
    - no_encontrado: no aparece en ninguna parte: posible invento.
    """
    candidatos = [(c, "codigo") for c in extraer_codigos(borrador)] + [(d, "dato") for d in extraer_datos(borrador)]
    correo_como_fuente = [Fragmento(fuente="correo del cliente", texto=correo)]
    afirmaciones: list[Afirmacion] = []
    for texto, tipo in candidatos:
        en_vistos = buscar_en(vistos, texto)
        en_catalogo = en_vistos or buscar_en(catalogo, texto)
        en_correo = tipo == "dato" and not en_catalogo and buscar_en(correo_como_fuente, texto)
        if en_vistos:
            estado: EstadoAfirmacion = "respaldado"
        elif en_catalogo:
            estado = "fuera_de_contexto"
        elif en_correo:
            estado = "del_correo"
        else:
            estado = "no_encontrado"
        fuente = en_catalogo[0] if en_catalogo else "correo del cliente" if en_correo else None
        afirmaciones.append(Afirmacion(texto=texto, tipo=tipo, estado=estado, fuente=fuente))
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
