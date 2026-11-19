"""Los nodos del grafo. Cada nodo es una función: recibe el estado y devuelve
solo las claves que actualiza (o un Command, si además decide a dónde ir)."""

import logging
from typing import Literal

from langgraph.graph import END
from langgraph.types import Command, interrupt

from soporte import servicios
from soporte.agente import llm, prompts, verificador
from soporte.agente.estado import EstadoCorreo, Fragmento
from soporte.conocimiento import busqueda, rag, verificacion
from soporte.conocimiento.verificacion import RevisionDelVerificador

logger = logging.getLogger(__name__)

RAMAS_DE_CONTEXTO = ["buscar_documentacion", "busqueda_exacta", "consultar_historial", "crear_ticket"]


def recibir_correo(estado: EstadoCorreo) -> dict:
    """Valida y normaliza la entrada. En producción aquí se parsearía el correo crudo (MIME)."""
    faltantes = [campo for campo in ("remitente", "cuerpo") if not estado.get(campo)]
    if faltantes:
        raise ValueError(f"Faltan campos en la entrada: {', '.join(faltantes)}")
    return {
        "remitente": estado["remitente"].strip().lower(),
        "asunto": estado.get("asunto", "").strip(),
        "cuerpo": estado["cuerpo"].strip(),
        "pasos": ["recibir_correo"],
    }


def clasificar(estado: EstadoCorreo) -> dict:
    clasificacion = llm.clasificar_con_llm(estado["remitente"], estado.get("asunto", ""), estado["cuerpo"])
    # Se guarda como dict: el estado queda en tipos simples, fáciles de serializar
    # en el checkpointer y de leer en Studio.
    return {"clasificacion": clasificacion.model_dump(), "pasos": ["clasificar"]}


def rutas_tras_clasificar(estado: EstadoCorreo) -> list[str]:
    """Arista condicional que devuelve una LISTA: esas ramas corren en paralelo.

    Solo se abre un caso (ticket) si es una garantía o la línea del cliente está parada.
    """
    c = estado["clasificacion"]
    rutas = ["buscar_documentacion", "busqueda_exacta", "consultar_historial"]
    if c["intencion"] == "garantia" or c["urgencia"] == "critica":
        rutas.append("crear_ticket")
    return rutas


def buscar_documentacion(estado: EstadoCorreo) -> dict:
    c = estado["clasificacion"]
    try:
        fragmentos = rag.buscar(f"{c['tema']}. {c['resumen']}")
    except Exception as error:  # noqa: BLE001
        logger.warning("Falló la búsqueda en la base de conocimiento: %s", error)
        # Un agente largo no debe caerse por una búsqueda fallida: se guarda el
        # error en el estado y el redactor sabrá que no tiene documentación.
        fragmentos = [Fragmento(fuente="error", texto=f"Búsqueda no disponible: {error}")]
    return {"fragmentos": fragmentos, "pasos": ["buscar_documentacion"]}


def busqueda_exacta(estado: EstadoCorreo) -> dict:
    """El "grep": busca literalmente en el catálogo cada número de pieza del correo.
    Corre en paralelo con la búsqueda vectorial y encuentra lo que ella confunde."""
    resultado, fragmentos = busqueda.busqueda_exacta(f"{estado.get('asunto', '')}\n{estado['cuerpo']}", rag.catalogo())
    return {"busqueda_exacta": resultado, "fragmentos_exactos": fragmentos, "pasos": ["busqueda_exacta"]}


def consultar_historial(estado: EstadoCorreo) -> dict:
    return {"historial_cliente": servicios.historial_de(estado["remitente"]), "pasos": ["consultar_historial"]}


def crear_ticket(estado: EstadoCorreo) -> dict:
    c = estado["clasificacion"]
    return {"ticket_id": servicios.crear_ticket(c["resumen"], c["urgencia"]), "pasos": ["crear_ticket"]}


def motivos_de_negocio(estado: EstadoCorreo) -> list[str]:
    """Reglas de negocio para pedir revisión humana. Las decide el código, no el LLM:
    el modelo clasifica, nosotros enrutamos. Lista vacía = no hace falta revisión."""
    c = estado["clasificacion"]
    motivos = []
    if c["urgencia"] in ("alta", "critica"):
        motivos.append(f"Urgencia {c['urgencia']}.")
    if c["intencion"] == "complejo":
        motivos.append("Caso complejo: reclamo formal o varios temas.")
    if estado.get("historial_cliente", {}).get("contactos_previos", 0) >= 3:
        motivos.append("Cliente con 3 o más contactos recientes.")
    return motivos


def redactar_respuesta(estado: EstadoCorreo) -> dict:
    c = estado["clasificacion"]
    historial = estado.get("historial_cliente", {})
    # El modelo ve las dos búsquedas combinadas; la exacta primero porque es segura.
    contexto = busqueda.combinar_contexto(estado.get("fragmentos", []), estado.get("fragmentos_exactos", []))
    documentacion = "\n\n".join(f"[{f['fuente']}]\n{f['texto']}" for f in contexto) or "Sin documentación."

    prompt = prompts.REDACTAR.format(
        nombre=historial.get("nombre", "cliente"),
        remitente=estado["remitente"],
        historial=historial.get("nota", f"{historial.get('contactos_previos', 0)} contactos previos"),
        intencion=c["intencion"],
        urgencia=c["urgencia"],
        ticket=estado.get("ticket_id") or "no aplica",
        cuerpo=estado["cuerpo"],
        documentacion=documentacion,
    )
    return {"borrador": llm.redactar_con_llm(prompt), "contexto": contexto, "pasos": ["redactar_respuesta"]}


def verificar_respuesta(estado: EstadoCorreo) -> Command[Literal["revision_humana", "enviar_respuesta"]]:
    """Último control antes de enviar, en dos capas:

    1. Piso literal (sin LLM): cada número de pieza y dato del borrador tiene que
       existir tal cual en el catálogo. Se comprueba siempre.
    2. Verificador agente: un LLM con la herramienta buscar_en_catalogo elige qué más
       comprobar (a qué pieza pertenece cada dato, políticas, compatibilidades).

    El LLM solo opina; el código decide. Cualquier problema, o que el verificador
    falle, manda la respuesta a revisión humana: lo peor que puede pasar es revisar
    de más, no dejar pasar un invento.
    """
    catalogo = rag.catalogo()
    piso = verificacion.comprobar_literal(estado["borrador"], estado.get("contexto", []), catalogo)
    try:
        revision = verificador.revisar(estado["cuerpo"], estado["borrador"])
        error = None
    except Exception as falla:  # noqa: BLE001
        logger.warning("Falló el verificador agente: %s", falla)
        revision, error = RevisionDelVerificador(afirmaciones=[], busquedas=[]), str(falla)

    resultado = verificacion.armar_verificacion(
        piso,
        revision,
        codigos_inexistentes=estado.get("busqueda_exacta", {}).get("inexistentes", []),
        error=error,
    )
    motivos = resultado["motivos"] + motivos_de_negocio(estado)
    # Command = actualizar el estado y elegir el siguiente nodo en el mismo return.
    # El tipo Command[Literal[...]] permite a LangGraph dibujar las dos salidas.
    return Command(
        update={"verificacion": resultado, "motivos_revision": motivos, "pasos": ["verificar_respuesta"]},
        goto="revision_humana" if motivos else "enviar_respuesta",
    )


def revision_humana(estado: EstadoCorreo) -> Command[Literal["enviar_respuesta", "__end__"]]:
    c = estado["clasificacion"]
    # interrupt() va PRIMERO: al reanudar, el nodo se ejecuta otra vez desde el
    # inicio, así que cualquier efecto antes de esta línea se repetiría.
    respuesta = interrupt(
        {
            "correo_id": estado.get("correo_id"),
            "remitente": estado["remitente"],
            "correo": estado["cuerpo"],
            "borrador": estado["borrador"],
            "urgencia": c["urgencia"],
            "intencion": c["intencion"],
            "ticket_id": estado.get("ticket_id"),
            "motivos": estado.get("motivos_revision", []),
            "instrucciones": 'Responde {"accion": "aprobar"} | {"accion": "editar", "texto": "..."} | {"accion": "rechazar"}',
        }
    )
    if isinstance(respuesta, str):  # comodidad en Studio: permitir solo "aprobar"
        respuesta = {"accion": respuesta}

    accion = respuesta.get("accion")
    if accion == "aprobar":
        return Command(update={"decision_humana": "aprobado", "pasos": ["revision_humana"]}, goto="enviar_respuesta")
    if accion == "editar":
        return Command(
            update={"borrador": respuesta["texto"], "decision_humana": "editado", "pasos": ["revision_humana"]},
            goto="enviar_respuesta",
        )
    # Rechazado: no se envía nada; una persona atiende el caso directamente.
    return Command(update={"decision_humana": "rechazado", "pasos": ["revision_humana"]}, goto=END)


def enviar_respuesta(estado: EstadoCorreo) -> dict:
    asunto = f"Re: {estado.get('asunto') or 'Tu solicitud'}"
    servicios.enviar_correo(estado["remitente"], asunto, estado["borrador"])
    return {"enviado": True, "pasos": ["enviar_respuesta"]}
