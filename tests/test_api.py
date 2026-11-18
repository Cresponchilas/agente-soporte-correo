"""Tests de la API: contratos, streaming de eventos, reanudación y manejo de errores.
Usan el LLM falso de conftest.py, así que no gastan tokens."""

import json

import pytest
from fastapi.testclient import TestClient

from soporte import llm
from soporte.api.ajustes import Ajustes
from soporte.api.app import crear_app

CORREO = {"remitente": "ana.ruiz@panaderialaespiga.co", "asunto": "Facturas", "cuerpo": "¿Dónde descargo mis facturas?"}


def leer_eventos(respuesta) -> list[dict]:
    """Convierte el texto SSE en una lista de eventos (los bloques 'data: ...')."""
    return [json.loads(linea.removeprefix("data: ")) for linea in respuesta.text.splitlines() if linea.startswith("data: ")]


def tipos(eventos: list[dict]) -> list[str]:
    return [e["tipo"] for e in eventos]


@pytest.fixture
def cliente():
    with TestClient(crear_app(Ajustes())) as c:
        yield c


def test_salud_indica_persistencia_en_memoria(cliente):
    respuesta = cliente.get("/api/salud")
    assert respuesta.status_code == 200
    assert respuesta.json()["persistencia"] == "memoria"


def test_casos_de_prueba_disponibles(cliente):
    casos = cliente.get("/api/casos").json()
    assert len(casos) == 8
    assert {"id", "entrada", "esperado"} <= set(casos[0])


def test_corrida_simple_transmite_cada_nodo_y_termina(cliente, clasificacion_falsa):
    clasificacion_falsa(intencion="pregunta", urgencia="baja")
    respuesta = cliente.post("/api/corridas", json=CORREO)

    assert respuesta.headers["content-type"].startswith("text/event-stream")
    eventos = leer_eventos(respuesta)
    assert eventos[0]["tipo"] == "inicio" and eventos[-1]["tipo"] == "fin"
    nodos_terminados = [e["nodo"] for e in eventos if e["tipo"] == "nodo_fin"]
    assert nodos_terminados[:2] == ["recibir_correo", "clasificar"]
    assert nodos_terminados[-1] == "enviar_respuesta"
    assert all(e["duracion_ms"] >= 0 for e in eventos if e["tipo"] == "nodo_fin")
    assert eventos[-1]["estado"]["enviado"] is True


def test_corrida_urgente_pausa_y_se_reanuda_con_la_decision(cliente, clasificacion_falsa):
    clasificacion_falsa(intencion="facturacion", urgencia="alta")
    eventos = leer_eventos(cliente.post("/api/corridas", json=CORREO))
    assert "pausa" in tipos(eventos)
    assert eventos[-1]["estado"]["pausado_en"] == ["revision_humana"]
    thread_id = eventos[0]["thread_id"]

    eventos = leer_eventos(cliente.post(f"/api/corridas/{thread_id}/decision", json={"accion": "editar", "texto": "Texto final"}))
    assert eventos[0]["reanudacion"] is True
    final = eventos[-1]["estado"]
    assert final["decision_humana"] == "editado"
    assert final["borrador"] == "Texto final"
    assert final["enviado"] is True

    assert cliente.get(f"/api/corridas/{thread_id}").json()["estado"]["enviado"] is True


def test_decision_sobre_corrida_inexistente_da_404(cliente):
    respuesta = cliente.post("/api/corridas/no-existe/decision", json={"accion": "aprobar"})
    assert respuesta.status_code == 404
    assert "error" in respuesta.json()


def test_decision_sobre_corrida_terminada_da_409(cliente, clasificacion_falsa):
    clasificacion_falsa(intencion="pregunta", urgencia="baja")
    thread_id = leer_eventos(cliente.post("/api/corridas", json=CORREO))[0]["thread_id"]
    assert cliente.post(f"/api/corridas/{thread_id}/decision", json={"accion": "aprobar"}).status_code == 409


@pytest.mark.parametrize(
    "cuerpo, campo",
    [
        ({**CORREO, "remitente": "no-es-un-correo"}, "remitente"),
        ({**CORREO, "cuerpo": ""}, "cuerpo"),
        ({**CORREO, "cuerpo": "x" * 5000}, "cuerpo"),
    ],
)
def test_entrada_invalida_da_422_con_el_campo(cliente, cuerpo, campo):
    respuesta = cliente.post("/api/corridas", json=cuerpo)
    assert respuesta.status_code == 422
    assert respuesta.json()["detalles"][0]["campo"] == campo


def test_editar_sin_texto_da_422(cliente):
    respuesta = cliente.post("/api/corridas/x/decision", json={"accion": "editar"})
    assert respuesta.status_code == 422
    assert "texto" in respuesta.json()["detalles"][0]["mensaje"]


def test_fallo_del_modelo_llega_como_evento_de_error(cliente, monkeypatch):
    def falla(*args, **kwargs):
        raise RuntimeError("detalle interno que no debe filtrarse")

    monkeypatch.setattr(llm, "clasificar_con_llm", falla)
    eventos = leer_eventos(cliente.post("/api/corridas", json=CORREO))

    assert eventos[-1]["tipo"] == "error"
    assert eventos[-1]["mensaje"] == "Error interno procesando el correo."
    assert "detalle interno" not in json.dumps(eventos)


def test_el_dashboard_se_sirve_en_la_raiz(cliente):
    respuesta = cliente.get("/")
    assert respuesta.status_code == 200
    assert "Mesa de soporte" in respuesta.text
    assert cliente.get("/js/main.js").status_code == 200


def test_corrida_pausada_sobrevive_a_un_reinicio_con_sqlite(tmp_path, clasificacion_falsa):
    clasificacion_falsa(intencion="bug", urgencia="critica")
    ajustes = Ajustes(archivo_checkpoints=tmp_path / "checkpoints.sqlite")

    with TestClient(crear_app(ajustes)) as primer_servidor:
        assert primer_servidor.get("/api/salud").json()["persistencia"] == "sqlite"
        thread_id = leer_eventos(primer_servidor.post("/api/corridas", json=CORREO))[0]["thread_id"]

    with TestClient(crear_app(ajustes)) as segundo_servidor:  # proceso nuevo, mismo archivo
        eventos = leer_eventos(segundo_servidor.post(f"/api/corridas/{thread_id}/decision", json={"accion": "aprobar"}))

    assert eventos[-1]["tipo"] == "fin"
    assert eventos[-1]["estado"]["enviado"] is True
