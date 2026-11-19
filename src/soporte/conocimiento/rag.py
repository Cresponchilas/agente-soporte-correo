"""RAG sobre la base de conocimiento (data/kb/*.md).

Pasos clásicos de RAG:
1. Cargar documentos.
2. Partirlos en fragmentos (aquí, una sección "## " = un fragmento, porque cada
   sección responde una sola pregunta).
3. Convertir cada fragmento en un vector (embeddings) y guardarlo en un vector store.
4. Al consultar, convertir la consulta en vector y traer los k fragmentos más parecidos.
"""

from functools import lru_cache
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore

from soporte import config
from soporte.agente.estado import Fragmento


def partir_markdown(ruta: Path) -> list[Document]:
    """Divide un archivo markdown en un Document por cada sección '## '."""
    texto = ruta.read_text(encoding="utf-8")
    titulo_doc = ruta.stem
    documentos = []
    for bloque in texto.split("\n## ")[1:]:  # lo anterior al primer '## ' es el título
        titulo_seccion, _, contenido = bloque.partition("\n")
        documentos.append(
            Document(
                page_content=f"{titulo_seccion.strip()}\n{contenido.strip()}",
                metadata={"fuente": f"{titulo_doc}#{titulo_seccion.strip()}"},
            )
        )
    return documentos


def cargar_documentos(carpeta: Path = config.CARPETA_KB) -> list[Document]:
    documentos = []
    for ruta in sorted(carpeta.glob("*.md")):
        documentos.extend(partir_markdown(ruta))
    return documentos


def construir_indice(embeddings: Embeddings, carpeta: Path = config.CARPETA_KB) -> InMemoryVectorStore:
    return InMemoryVectorStore.from_documents(cargar_documentos(carpeta), embeddings)


@lru_cache
def indice() -> InMemoryVectorStore:
    # Se construye una sola vez por proceso: los embeddings de ~22 secciones
    # cuestan una fracción de centavo.
    return construir_indice(config.embeddings())


def buscar(consulta: str, k: int = 3) -> list[Fragmento]:
    resultados = indice().similarity_search(consulta, k=k)
    return [Fragmento(fuente=d.metadata["fuente"], texto=d.page_content) for d in resultados]


@lru_cache
def catalogo() -> list[Fragmento]:
    """Todas las secciones como texto plano, para la búsqueda exacta (sin embeddings)."""
    return [Fragmento(fuente=d.metadata["fuente"], texto=d.page_content) for d in cargar_documentos()]
