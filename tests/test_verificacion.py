"""Búsqueda exacta y verificación: funciones puras, se prueban con texto."""

import pytest

from soporte import kb
from soporte.verificacion import (
    busqueda_exacta,
    combinar_contexto,
    contiene,
    extraer_codigos,
    extraer_datos,
    normalizar,
    verificar,
)



def test_extrae_numeros_de_pieza_sin_partirlos():
    texto = "Reemplace el SI-M12-04P-L por el SI-M12-04P y use el reflector RF-50 con la VN-52-14-24D."
    assert extraer_codigos(texto) == ["SI-M12-04P-L", "SI-M12-04P", "RF-50", "VN-52-14-24D"]


def test_no_confunde_palabras_ni_medidas_con_codigos():
    assert extraer_codigos("Conector M12, protección IP67, caso RMA abierto.") == []


def test_extrae_datos_con_unidad_y_normaliza_precios():
    datos = extraer_datos("Cuesta $54 (o 49 USD la de 1/8), detecta a 8 mm, trabaja de 1,5 a 8 bar y llega en 7 días hábiles.")
    assert datos == ["USD 54", "USD 49", "8 mm", "8 bar", "7 días hábiles"]


@pytest.mark.parametrize(
    "texto, termino, esperado",
    [
        ("Reemplazo directo: SI-M12-04P.", "SI-M12-04P", True),
        ("El SI-M12-04P-L se descontinuó.", "SI-M12-04P", False),  # otra pieza, no un prefijo
        ("Presión: 1,5 a 18 bar", "8 bar", False),  # 8 dentro de 18 no cuenta
        ("Presión: 1,5 a 8 bar", "8 bar", True),
        ("Precio: USD 54", "$54", True),  # formas distintas del mismo precio
    ],
)
def test_contiene_compara_unidades_completas(texto, termino, esperado):
    assert contiene(texto, termino) is esperado


def test_normalizar_unifica_espacios_y_decimales():
    assert normalizar("1,5 a  8 bar") == "1.5 a 8 bar"


def test_busqueda_exacta_encuentra_las_piezas_y_detecta_las_que_no_existen():
    resultado, fragmentos = busqueda_exacta("¿Tienen el SI-M18-08P y el SI-M12-06P?", kb.catalogo())
    assert resultado["encontrados"] == {"SI-M18-08P": ["sensores-inductivos#SI-M18-08P"]}
    assert resultado["inexistentes"] == ["SI-M12-06P"]
    assert [f["fuente"] for f in fragmentos] == ["sensores-inductivos#SI-M18-08P"]


def test_busqueda_exacta_no_encuentra_combinaciones_que_no_existen():
    resultado, _ = busqueda_exacta("Cotícenme la VN-52-38-24D", kb.catalogo())
    assert resultado["inexistentes"] == ["VN-52-38-24D"]


def test_combinar_contexto_marca_el_origen_y_no_repite():
    a = {"fuente": "a#1", "texto": "x"}
    b = {"fuente": "b#1", "texto": "y"}
    c = {"fuente": "c#1", "texto": "z"}
    combinado = combinar_contexto(vectorial=[a, b], exacta=[b, c])
    assert [(f["fuente"], f["origen"]) for f in combinado] == [("b#1", "ambas"), ("c#1", "exacta"), ("a#1", "vectorial")]


def test_verificar_aprueba_lo_que_esta_en_lo_que_vio_el_modelo():
    vistos = [f for f in kb.catalogo() if f["fuente"] == "sensores-inductivos#SI-M18-08P"]
    resultado = verificar("El SI-M18-08P detecta a 8 mm y cuesta USD 46.", vistos, kb.catalogo(), [])
    assert resultado["aprobada"] is True
    assert {a["estado"] for a in resultado["afirmaciones"]} == {"respaldado"}


def test_verificar_bloquea_una_pieza_inventada():
    resultado = verificar("Le recomendamos el SI-M12-99P a USD 40.", [], kb.catalogo(), [])
    assert resultado["aprobada"] is False
    estados = {a["texto"]: a["estado"] for a in resultado["afirmaciones"]}
    assert estados["SI-M12-99P"] == "no_encontrado"
    assert any("SI-M12-99P" in m for m in resultado["motivos"])


def test_verificar_distingue_datos_reales_que_el_modelo_no_vio():
    resultado = verificar("La fuente FP-24-10 da 10 A.", [], kb.catalogo(), [])
    assert resultado["aprobada"] is True  # es real: se informa, no se bloquea
    assert {a["estado"] for a in resultado["afirmaciones"]} == {"fuera_de_contexto"}


def test_verificar_bloquea_si_el_cliente_pide_una_pieza_inexistente():
    resultado = verificar("No encontramos esa referencia; un asesor le confirmará.", [], kb.catalogo(), ["SI-M12-06P"])
    assert resultado["aprobada"] is False
    assert resultado["motivos"] == ["El cliente menciona SI-M12-06P, que no existe en el catálogo."]
