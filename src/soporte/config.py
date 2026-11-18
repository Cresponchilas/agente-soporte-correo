"""Configuración: qué modelo de chat y qué embeddings usar.

Todo sale de variables de entorno para poder cambiar de modelo (o de proveedor)
sin tocar el código. Esa es la ventaja de init_chat_model: el string
"proveedor:modelo" decide la clase concreta.
"""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.embeddings import init_embeddings

load_dotenv()

RAIZ = Path(__file__).resolve().parents[2]
CARPETA_KB = RAIZ / "data" / "kb"
ARCHIVO_CLIENTES = RAIZ / "data" / "clientes.json"

MODELO_CHAT = os.getenv("MODELO_CHAT", "openai:gpt-4.1-mini")
MODELO_EMBEDDINGS = os.getenv("MODELO_EMBEDDINGS", "openai:text-embedding-3-small")


@lru_cache
def modelo_chat():
    # temperature=0: para clasificar y redactar soporte queremos respuestas estables.
    # max_tokens limita el costo de cada llamada; timeout y max_retries evitan que una
    # llamada colgada bloquee el grafo indefinidamente.
    return init_chat_model(MODELO_CHAT, temperature=0, max_tokens=700, timeout=30, max_retries=2)


@lru_cache
def embeddings():
    return init_embeddings(MODELO_EMBEDDINGS)
