"""Los nodos del grafo. Cada nodo es una función: recibe el estado y devuelve
solo las claves que actualiza."""

from soporte import llm, prompts, servicios
from soporte.state import EstadoCorreo


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


def redactar_respuesta(estado: EstadoCorreo) -> dict:
    c = estado["clasificacion"]
    prompt = prompts.REDACTAR.format(
        nombre="cliente",
        remitente=estado["remitente"],
        historial="sin consultar",
        intencion=c["intencion"],
        urgencia=c["urgencia"],
        ticket="no aplica",
        cuerpo=estado["cuerpo"],
        documentacion="Sin documentación.",  # el RAG llega en el siguiente PR
    )
    return {"borrador": llm.redactar_con_llm(prompt), "pasos": ["redactar_respuesta"]}


def enviar_respuesta(estado: EstadoCorreo) -> dict:
    asunto = f"Re: {estado.get('asunto') or 'Tu solicitud'}"
    servicios.enviar_correo(estado["remitente"], asunto, estado["borrador"])
    return {"enviado": True, "pasos": ["enviar_respuesta"]}
