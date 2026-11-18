"""Fixtures: reemplazan el LLM y los embeddings para que los tests no gasten tokens
ni necesiten llaves de API."""

import hashlib
import math

import pytest
from langchain_core.embeddings import Embeddings

from soporte import kb, llm
from soporte.state import Clasificacion


class EmbeddingsFalsos(Embeddings):
    """Embeddings deterministas sin red ni numpy: cada palabra suma 1 en una de
    64 posiciones (según su hash). Textos con palabras en común quedan cerca."""

    def _vector(self, texto: str) -> list[float]:
        vector = [0.0] * 64
        for palabra in texto.lower().split():
            vector[int(hashlib.md5(palabra.encode()).hexdigest(), 16) % 64] += 1.0
        norma = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norma for v in vector]

    def embed_documents(self, textos: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in textos]

    def embed_query(self, texto: str) -> list[float]:
        return self._vector(texto)


@pytest.fixture
def clasificacion_falsa(monkeypatch):
    """Permite que cada test decida qué 'responde' el clasificador."""

    def _configurar(intencion="pregunta", urgencia="baja", tema="tema", resumen="resumen"):
        resultado = Clasificacion(intencion=intencion, urgencia=urgencia, tema=tema, resumen=resumen)
        monkeypatch.setattr(llm, "clasificar_con_llm", lambda *args, **kwargs: resultado)
        return resultado

    return _configurar


@pytest.fixture(autouse=True)
def sin_llamadas_reales(monkeypatch):
    monkeypatch.setattr(llm, "redactar_con_llm", lambda prompt: "Hola, este es un borrador de prueba.")
    indice_falso = kb.construir_indice(EmbeddingsFalsos())
    monkeypatch.setattr(kb, "indice", lambda: indice_falso)
