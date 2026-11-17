"""Integración con Postgres real: una corrida pausada sobrevive a un "reinicio"
del servidor. Se salta si no hay TEST_DATABASE_URL, por ejemplo:

    TEST_DATABASE_URL=postgresql://postgres@localhost:5432/postgres pytest tests/test_api_postgres.py
"""

import os

import pytest
from fastapi.testclient import TestClient

from soporte.api.ajustes import Ajustes
from soporte.api.app import crear_app
from test_api import CORREO, leer_eventos

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL no definida")


def test_corrida_pausada_sobrevive_a_un_reinicio(clasificacion_falsa):
    clasificacion_falsa(intencion="bug", urgencia="critica")
    ajustes = Ajustes(database_url=URL)

    with TestClient(crear_app(ajustes)) as primer_servidor:
        assert primer_servidor.get("/salud").json()["persistencia"] == "postgres"
        thread_id = leer_eventos(primer_servidor.post("/corridas", json=CORREO))[0]["thread_id"]

    with TestClient(crear_app(ajustes)) as segundo_servidor:  # proceso nuevo, misma base
        eventos = leer_eventos(segundo_servidor.post(f"/corridas/{thread_id}/decision", json={"accion": "aprobar"}))

    assert eventos[-1]["tipo"] == "fin"
    assert eventos[-1]["estado"]["enviado"] is True
