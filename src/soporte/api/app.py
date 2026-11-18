"""Aplicación FastAPI: la API en /api y el dashboard en /.

    python -m soporte.api        # abre http://localhost:8000
"""

import json
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command

from soporte import config
from soporte.api.ajustes import Ajustes
from soporte.api.corridas import configuracion, esta_pausada_en_revision, transmitir
from soporte.api.esquemas import CasoDePrueba, CorreoEntrante, DecisionHumana, Salud
from soporte.api.eventos import resumen_del_estado
from soporte.api.persistencia import abrir_checkpointer
from soporte.graph import construir_grafo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

CARPETA_WEB = Path(__file__).resolve().parents[1] / "web"
CABECERAS_SSE = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def cargar_casos() -> list[CasoDePrueba]:
    datos = json.loads((config.RAIZ / "data" / "correos_ejemplo.json").read_text(encoding="utf-8"))
    return [CasoDePrueba(id=f"caso-{i}", entrada=d["entrada"], esperado=d["esperado"]) for i, d in enumerate(datos)]


def crear_app(ajustes: Ajustes | None = None) -> FastAPI:
    ajustes = ajustes or Ajustes()

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        async with abrir_checkpointer(ajustes.archivo_checkpoints) as (checkpointer, tipo):
            app.state.grafo = construir_grafo(checkpointer)
            app.state.persistencia = tipo
            yield

    app = FastAPI(title="Agente de soporte por correo", version="2.0.0", lifespan=ciclo_de_vida)
    app.state.casos = cargar_casos()
    _registrar_manejadores_de_error(app)
    app.include_router(_rutas_api(), prefix="/api")
    # El dashboard se monta al final: las rutas /api tienen prioridad.
    app.mount("/", StaticFiles(directory=CARPETA_WEB, html=True), name="dashboard")
    return app


def _registrar_manejadores_de_error(app: FastAPI) -> None:
    """Toda respuesta de error tiene la misma forma: {"error": "...", "detalles": [...]}"""

    @app.exception_handler(RequestValidationError)
    async def datos_invalidos(_: Request, error: RequestValidationError):
        detalles = [
            {"campo": ".".join(str(p) for p in e["loc"] if p != "body"), "mensaje": e["msg"].removeprefix("Value error, ")}
            for e in error.errors()
        ]
        return JSONResponse(status_code=422, content={"error": "Datos inválidos", "detalles": detalles})

    @app.exception_handler(HTTPException)
    async def error_http(_: Request, error: HTTPException):
        return JSONResponse(status_code=error.status_code, content={"error": error.detail}, headers=error.headers)

    @app.exception_handler(Exception)
    async def error_inesperado(_: Request, error: Exception):
        logging.getLogger(__name__).exception("Error no controlado")
        return JSONResponse(status_code=500, content={"error": "Error interno del servidor"})


def _rutas_api() -> APIRouter:
    rutas = APIRouter()

    @rutas.get("/salud", response_model=Salud)
    async def salud(request: Request):
        return Salud(estado="ok", persistencia=request.app.state.persistencia, modelo=config.MODELO_CHAT)

    @rutas.get("/casos", response_model=list[CasoDePrueba])
    async def casos(request: Request):
        return request.app.state.casos

    @rutas.post("/corridas")
    async def nueva_corrida(correo: CorreoEntrante, request: Request):
        thread_id = str(uuid.uuid4())
        entrada = {**correo.model_dump(), "correo_id": thread_id}
        return StreamingResponse(
            transmitir(request.app.state.grafo, entrada, thread_id), media_type="text/event-stream", headers=CABECERAS_SSE
        )

    @rutas.post("/corridas/{thread_id}/decision")
    async def decidir(thread_id: str, decision: DecisionHumana, request: Request):
        grafo = request.app.state.grafo
        pausada = await esta_pausada_en_revision(grafo, thread_id)
        if pausada is None:
            raise HTTPException(404, "No existe esa corrida.")
        if not pausada:
            raise HTTPException(409, "Esa corrida no está esperando una decisión.")

        comando = Command(resume=decision.model_dump(exclude_none=True))
        return StreamingResponse(transmitir(grafo, comando, thread_id), media_type="text/event-stream", headers=CABECERAS_SSE)

    @rutas.get("/corridas/{thread_id}")
    async def estado_de_corrida(thread_id: str, request: Request):
        instantanea = await request.app.state.grafo.aget_state(configuracion(thread_id))
        if not instantanea.values:
            raise HTTPException(404, "No existe esa corrida.")
        return {"thread_id": thread_id, "estado": resumen_del_estado(instantanea.values, instantanea.next)}

    return rutas


def crear_app_desde_entorno() -> FastAPI:
    """Fábrica para uvicorn (`--factory`) y para `python -m soporte.api`."""
    return crear_app(Ajustes.desde_entorno())
