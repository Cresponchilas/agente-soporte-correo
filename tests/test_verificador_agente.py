"""El verificador agente (create_agent + middleware) con un modelo guionado: cada test
decide qué herramientas "pide" el modelo en cada vuelta. Sin red y sin tokens."""

import pytest
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from soporte import config
from soporte.agente import verificador

# conftest reemplaza verificador.revisar por uno falso en cada test; aquí se prueba
# el de verdad, así que se guarda antes (al importar este módulo).
revisar = verificador.revisar


class ModeloGuionado(BaseChatModel):
    """Un chat model de mentira: devuelve las respuestas en orden y guarda los
    mensajes que recibió en cada vuelta."""

    respuestas: list[AIMessage]
    recibidos: list = Field(default_factory=list)
    herramientas: list = Field(default_factory=list)
    tool_choice: str | None = None

    @property
    def _llm_type(self) -> str:
        return "guionado"

    def bind_tools(self, herramientas, *, tool_choice=None, **kwargs):
        self.herramientas = [getattr(h, "name", getattr(h, "__name__", "")) for h in herramientas]
        self.tool_choice = tool_choice
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.recibidos.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=self.respuestas.pop(0))])


def pide(*llamadas):
    return AIMessage(content="", tool_calls=[{"name": n, "args": a, "id": f"llamada-{n}-{i}"} for i, (n, a) in enumerate(llamadas)])


def buscar(termino):
    return ("buscar_en_catalogo", {"termino": termino})


def entregar(*afirmaciones):
    return ("EntregarVeredicto", {"afirmaciones": list(afirmaciones)})


CONTRADICHA = {
    "afirmacion": "El SI-M12-04P detecta a 8 mm",
    "veredicto": "contradicha",
    "fuente": "sensores-inductivos#SI-M12-04P",
    "explicacion": "La ficha dice 4 mm.",
}


@pytest.fixture
def guion(monkeypatch):
    def _usar(*respuestas):
        modelo = ModeloGuionado(respuestas=list(respuestas))
        monkeypatch.setattr(config, "modelo_chat", lambda: modelo)
        return modelo

    return _usar


def ultimo_resultado_de_herramienta(modelo, vuelta):
    return [m for m in modelo.recibidos[vuelta] if isinstance(m, ToolMessage)][-1]


def test_busca_lee_y_entrega(guion):
    modelo = guion(pide(buscar("SI-M12-04P")), pide(entregar(CONTRADICHA)))
    revision = revisar("¿Qué alcance tiene?", "El SI-M12-04P detecta a 8 mm.")

    assert modelo.tool_choice == "any"  # create_agent lo obliga a usar una herramienta
    assert revision["afirmaciones"] == [CONTRADICHA]
    # La búsqueda la registra el código, con las fuentes que de verdad encontró.
    assert revision["busquedas"][0]["termino"] == "SI-M12-04P"
    assert revision["busquedas"][0]["fuentes"][0] == "sensores-inductivos#SI-M12-04P"
    # En la segunda vuelta el modelo ya tenía el texto de la ficha para comparar.
    assert "Distancia de detección: 4 mm" in ultimo_resultado_de_herramienta(modelo, 1).content


def test_middleware_descarta_un_veredicto_escrito_antes_de_leer(guion):
    modelo = guion(
        pide(buscar("SI-M12-04P"), entregar()),  # busca y "entrega" en la misma vuelta
        pide(entregar(CONTRADICHA)),
    )
    revision = revisar("correo", "borrador")

    assert len(modelo.recibidos) == 2  # hubo una segunda vuelta
    assert revision["afirmaciones"] == [CONTRADICHA]  # vale el veredicto de después de leer


def test_tope_de_llamadas_al_modelo(guion):
    guion(*[pide(buscar(f"termino-{i}")) for i in range(verificador.MAXIMO_LLAMADAS + 1)])
    with pytest.raises(ModelCallLimitExceededError):
        revisar("correo", "borrador")


def test_tope_de_busquedas_deja_al_modelo_entregar_con_lo_que_tiene(guion):
    muchas = [buscar(f"SI-M12-0{i}P") for i in range(verificador.MAXIMO_BUSQUEDAS + 2)]
    modelo = guion(pide(*muchas), pide(entregar()))
    revision = revisar("correo", "borrador")

    assert len(revision["busquedas"]) == verificador.MAXIMO_BUSQUEDAS  # las de más no corrieron
    bloqueadas = [m for m in modelo.recibidos[1] if isinstance(m, ToolMessage) and m.status == "error"]
    assert len(bloqueadas) == 2  # el modelo recibe el aviso del tope y entrega en la vuelta siguiente


def test_veredicto_mal_formado_se_devuelve_al_modelo_para_corregir(guion):
    modelo = guion(
        pide(("EntregarVeredicto", {"afirmaciones": [{"afirmacion": "x", "veredicto": "quizas"}]})),
        pide(entregar(CONTRADICHA)),
    )
    revision = revisar("correo", "borrador")

    assert revision["afirmaciones"] == [CONTRADICHA]
    assert "error" in ultimo_resultado_de_herramienta(modelo, 1).content.lower()
