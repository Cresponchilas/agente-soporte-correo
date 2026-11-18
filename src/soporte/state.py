"""El estado del grafo: el contrato entre todos los nodos.

Cada nodo lee lo que necesita y devuelve SOLO las claves que cambia.
"""

import operator
from typing import Annotated, Literal

from pydantic import BaseModel, Field
from typing_extensions import NotRequired, TypedDict

Intencion = Literal["especificacion", "cotizacion", "reemplazo", "garantia", "complejo"]
Urgencia = Literal["baja", "media", "alta", "critica"]


class Clasificacion(BaseModel):
    """Esquema que el LLM debe devolver (structured output)."""

    intencion: Intencion = Field(
        description="especificacion, cotizacion, reemplazo, garantia, o complejo si no encaja en ninguna"
    )
    urgencia: Urgencia = Field(description="baja, media, alta o critica")
    tema: str = Field(description="Tema principal en pocas palabras, útil como consulta de búsqueda; incluye los números de pieza que mencione el cliente")
    resumen: str = Field(description="Resumen del correo en una frase")


class ClasificacionDict(TypedDict):
    """La misma clasificación, guardada en el estado como dict."""

    intencion: Intencion
    urgencia: Urgencia
    tema: str
    resumen: str


class Fragmento(TypedDict):
    """Un pedazo de la base de conocimiento recuperado por el RAG."""

    fuente: str  # archivo y sección, para citar
    texto: str
    origen: NotRequired[str]  # vectorial, exacta o ambas (cuando se combinan las búsquedas)


class EntradaCorreo(TypedDict):
    """Lo único que el usuario debe enviar al grafo. Studio usa este esquema para
    mostrar el formulario de entrada."""

    remitente: str
    asunto: str
    cuerpo: str
    correo_id: NotRequired[str]


class EstadoCorreo(TypedDict, total=False):
    # Entrada
    correo_id: str
    remitente: str
    asunto: str
    cuerpo: str

    # Intermedios
    clasificacion: ClasificacionDict
    fragmentos: list[Fragmento]  # búsqueda vectorial (RAG)
    busqueda_exacta: dict  # números de pieza del correo buscados literalmente en el catálogo
    fragmentos_exactos: list[Fragmento]
    contexto: list[Fragmento]  # lo que de verdad vio el modelo: las dos búsquedas combinadas
    historial_cliente: dict
    ticket_id: str | None

    # Salida
    borrador: str
    verificacion: dict  # resultado de verificar el borrador contra el catálogo
    motivos_revision: list[str]  # por qué pasa (o no) por revisión humana
    decision_humana: str | None  # aprobado, editado o rechazado
    enviado: bool

    # Bitácora: varios nodos (algunos en paralelo) escriben aquí, así que usa
    # un reductor que concatena en vez de reemplazar.
    pasos: Annotated[list[str], operator.add]
