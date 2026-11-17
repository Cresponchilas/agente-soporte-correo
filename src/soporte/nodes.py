"""Los nodos del grafo. Cada nodo es una función: recibe el estado y devuelve
solo las claves que actualiza."""

from soporte import kb, llm, prompts, servicios
from soporte.state import EstadoCorreo, Fragmento

RAMAS_DE_CONTEXTO = ["buscar_documentacion", "consultar_historial", "crear_ticket"]


def recibir_correo(estado: EstadoCorreo) -> dict:
    """Normaliza la entrada. En producción aquí se parsearía el correo crudo (MIME)."""
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

    El ticket solo se crea si hay un bug o la urgencia es crítica.
    """
    c = estado["clasificacion"]
    rutas = ["buscar_documentacion", "consultar_historial"]
    if c["intencion"] == "bug" or c["urgencia"] == "critica":
        rutas.append("crear_ticket")
    return rutas


def buscar_documentacion(estado: EstadoCorreo) -> dict:
    c = estado["clasificacion"]
    try:
        fragmentos = kb.buscar(f"{c['tema']}. {c['resumen']}")
    except Exception as error:  # noqa: BLE001
        # Un agente largo no debe caerse por una búsqueda fallida: se guarda el
        # error en el estado y el redactor sabrá que no tiene documentación.
        fragmentos = [Fragmento(fuente="error", texto=f"Búsqueda no disponible: {error}")]
    return {"fragmentos": fragmentos, "pasos": ["buscar_documentacion"]}


def consultar_historial(estado: EstadoCorreo) -> dict:
    return {"historial_cliente": servicios.historial_de(estado["remitente"]), "pasos": ["consultar_historial"]}


def crear_ticket(estado: EstadoCorreo) -> dict:
    c = estado["clasificacion"]
    return {"ticket_id": servicios.crear_ticket(c["resumen"], c["urgencia"]), "pasos": ["crear_ticket"]}


def redactar_respuesta(estado: EstadoCorreo) -> dict:
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
    return {"borrador": llm.redactar_con_llm(prompt), "pasos": ["redactar_respuesta"]}


def enviar_respuesta(estado: EstadoCorreo) -> dict:
    asunto = f"Re: {estado.get('asunto') or 'Tu solicitud'}"
    servicios.enviar_correo(estado["remitente"], asunto, estado["borrador"])
    return {"enviado": True, "pasos": ["enviar_respuesta"]}
