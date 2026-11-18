"""Fixtures: reemplazan el LLM y los embeddings para que los tests no gasten tokens
ni necesiten llaves de API."""

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

from soporte import kb, llm
from soporte.state import Clasificacion


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
    indice_falso = kb.construir_indice(DeterministicFakeEmbedding(size=64))
    monkeypatch.setattr(kb, "indice", lambda: indice_falso)
