"""Los nodos del grafo. Cada nodo es una función: recibe el estado y devuelve
solo las claves que actualiza (o un Command, si además decide a dónde ir)."""

import logging
from typing import Literal

from langgraph.graph import END
from langgraph.types import Command, interrupt

from soporte import kb, llm, prompts, servicios
from soporte.state import EstadoCorreo, Fragmento

logger = logging.getLogger(__name__)

RAMAS_DE_CONTEXTO = ["buscar_documentacion", "consultar_historial", "crear_ticket"]


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
    rutas = ["buscar_documentacion", "consultar_historial"]
    if c["intencion"] == "garantia" or c["urgencia"] == "critica":
        rutas.append("crear_ticket")
    return rutas


def buscar_documentacion(estado: EstadoCorreo) -> dict:
    c = estado["clasificacion"]
    try:
        fragmentos = kb.buscar(f"{c['tema']}. {c['resumen']}")
    except Exception as error:  # noqa: BLE001
        logger.warning("Falló la búsqueda en la base de conocimiento: %s", error)
        # Un agente largo no debe caerse por una búsqueda fallida: se guarda el
        # error en el estado y el redactor sabrá que no tiene documentación.
        fragmentos = [Fragmento(fuente="error", texto=f"Búsqueda no disponible: {error}")]
    return {"fragmentos": fragmentos, "pasos": ["buscar_documentacion"]}


def consultar_historial(estado: EstadoCorreo) -> dict:
    return {"historial_cliente": servicios.historial_de(estado["remitente"]), "pasos": ["consultar_historial"]}


def crear_ticket(estado: EstadoCorreo) -> dict:
    c = estado["clasificacion"]
    return {"ticket_id": servicios.crear_ticket(c["resumen"], c["urgencia"]), "pasos": ["crear_ticket"]}


def necesita_revision(estado: EstadoCorreo) -> bool:
    """La regla la decide el código, no el LLM: el modelo clasifica, nosotros enrutamos."""
    c = estado["clasificacion"]
    reincidente = estado.get("historial_cliente", {}).get("contactos_previos", 0) >= 3
    return c["urgencia"] in ("alta", "critica") or c["intencion"] == "complejo" or reincidente


def redactar_respuesta(estado: EstadoCorreo) -> Command[Literal["revision_humana", "enviar_respuesta"]]:
    c = estado["clasificacion"]
    historial = estado.get("historial_cliente", {})
    fragmentos = estado.get("fragmentos", [])
    documentacion = "\n\n".join(f"[{f['fuente']}]\n{f['texto']}" for f in fragmentos) or "Sin documentación."

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
    borrador = llm.redactar_con_llm(prompt)

    # Command = actualizar el estado y elegir el siguiente nodo en el mismo return.
    # El tipo Command[Literal[...]] permite a LangGraph dibujar las dos salidas.
    siguiente = "revision_humana" if necesita_revision(estado) else "enviar_respuesta"
    return Command(update={"borrador": borrador, "pasos": ["redactar_respuesta"]}, goto=siguiente)


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
