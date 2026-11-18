"""El loop del verificador agente, con un modelo guionado: cada test decide qué
herramientas "pide" el modelo en cada vuelta. Sin red y sin tokens."""

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from soporte import config, llm

# conftest reemplaza llm.verificar_con_llm por uno falso en cada test; aquí se prueba
# el de verdad, así que se guarda antes (al importar este módulo).
verificar_con_llm = llm.verificar_con_llm


class ModeloGuionado:
    """Imita un chat model con herramientas: devuelve las respuestas en orden y
    guarda los mensajes que recibió en cada vuelta."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.recibidos = []

    def bind_tools(self, herramientas, **kwargs):
        self.herramientas = [getattr(h, "name", getattr(h, "__name__", "")) for h in herramientas]
        self.tool_choice = kwargs.get("tool_choice")
        return self

    def invoke(self, mensajes):
        self.recibidos.append(list(mensajes))
        return self.respuestas.pop(0)


def pide(*llamadas):
    return AIMessage(content="", tool_calls=[{"name": n, "args": a, "id": f"llamada-{i}"} for i, (n, a) in enumerate(llamadas)])


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
        modelo = ModeloGuionado(respuestas)
        monkeypatch.setattr(config, "modelo_chat", lambda: modelo)
        return modelo

    return _usar


def test_busca_lee_y_entrega(guion):
    modelo = guion(pide(buscar("SI-M12-04P")), pide(entregar(CONTRADICHA)))
    revision = verificar_con_llm("¿Qué alcance tiene?", "El SI-M12-04P detecta a 8 mm.")

    assert modelo.tool_choice == "any"  # siempre tiene que usar una herramienta
    assert revision["afirmaciones"][0]["veredicto"] == "contradicha"
    # La búsqueda la registra el código, con las fuentes que de verdad encontró.
    assert revision["busquedas"][0]["termino"] == "SI-M12-04P"
    assert revision["busquedas"][0]["fuentes"][0] == "sensores-inductivos#SI-M12-04P"
    # En la segunda vuelta el modelo ya tenía el texto de la ficha para comparar.
    resultado_de_la_busqueda = modelo.recibidos[1][-1]
    assert isinstance(resultado_de_la_busqueda, ToolMessage)
    assert "Distancia de detección: 4 mm" in resultado_de_la_busqueda.content


def test_no_acepta_un_veredicto_escrito_antes_de_ver_las_busquedas(guion):
    modelo = guion(
        pide(buscar("SI-M12-04P"), entregar()),  # busca y "entrega" en la misma vuelta
        pide(entregar(CONTRADICHA)),
    )
    revision = verificar_con_llm("correo", "borrador")

    assert len(modelo.recibidos) == 2
    assert revision["afirmaciones"] == [CONTRADICHA]
    assert "Todavía no" in modelo.recibidos[1][-1].content


def test_sin_veredicto_tras_el_tope_de_vueltas_falla(guion):
    guion(*[pide(buscar("USD"))] * llm.MAXIMO_VUELTAS)
    with pytest.raises(llm.VerificadorSinVeredicto):
        verificar_con_llm("correo", "borrador")


def test_un_veredicto_mal_formado_falla_en_vez_de_aprobar(guion):
    guion(pide(("EntregarVeredicto", {"afirmaciones": [{"afirmacion": "x", "veredicto": "quizas"}]})))
    with pytest.raises(ValueError):  # ValidationError de Pydantic; el nodo lo manda a revisión
        verificar_con_llm("correo", "borrador")
