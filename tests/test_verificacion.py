"""Búsqueda exacta y verificación: funciones puras, se prueban con texto."""

import pytest

from soporte.conocimiento import fuentes, rag
from soporte.conocimiento.busqueda import busqueda_exacta, combinar_contexto, contiene, extraer_codigos, extraer_datos, normalizar
from soporte.conocimiento.verificacion import armar_verificacion, buscar_en_catalogo, comprobar_literal

SIN_REVISION = {"afirmaciones": [], "busquedas": []}


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
    resultado, fragmentos = busqueda_exacta("¿Tienen el SI-M18-08P y el SI-M12-06P?", rag.catalogo())
    assert resultado["encontrados"] == {"SI-M18-08P": ["sensores-inductivos#SI-M18-08P"]}
    assert resultado["inexistentes"] == ["SI-M12-06P"]
    assert [f["fuente"] for f in fragmentos] == ["sensores-inductivos#SI-M18-08P"]


def test_busqueda_exacta_no_encuentra_combinaciones_que_no_existen():
    resultado, _ = busqueda_exacta("Cotícenme la VN-52-38-24D", rag.catalogo())
    assert resultado["inexistentes"] == ["VN-52-38-24D"]


def test_combinar_contexto_marca_el_origen_y_no_repite():
    a = {"fuente": "a#1", "texto": "x"}
    b = {"fuente": "b#1", "texto": "y"}
    c = {"fuente": "c#1", "texto": "z"}
    combinado = combinar_contexto(vectorial=[a, b], exacta=[b, c])
    assert [(f["fuente"], f["origen"]) for f in combinado] == [("b#1", "ambas"), ("c#1", "exacta"), ("a#1", "vectorial")]


# ---------- Piso literal ----------


def test_piso_respalda_lo_que_esta_en_lo_que_vio_el_modelo():
    vistos = [f for f in fuentes.todas() if f["fuente"] in ("sensores-inductivos#SI-M18-08P", "inventario#SI-M18-08P")]
    piso = comprobar_literal("El SI-M18-08P detecta a 8 mm y cuesta USD 46.", vistos, fuentes.todas())
    assert {a["estado"] for a in piso} == {"respaldado"}


def test_piso_bloquea_una_pieza_inventada():
    piso = comprobar_literal("Le recomendamos el SI-M12-99P a USD 40.", [], fuentes.todas())
    resultado = armar_verificacion(piso, SIN_REVISION, codigos_inexistentes=[])
    assert {a["texto"]: a["estado"] for a in piso}["SI-M12-99P"] == "no_encontrado"
    assert resultado["aprobada"] is False
    assert any("SI-M12-99P" in m for m in resultado["motivos"])


def test_piso_distingue_datos_reales_que_el_modelo_no_vio():
    piso = comprobar_literal("La fuente FP-24-10 da 10 A.", [], rag.catalogo())
    assert {a["estado"] for a in piso} == {"fuera_de_contexto"}  # es real: se informa, no se bloquea
    assert armar_verificacion(piso, SIN_REVISION, codigos_inexistentes=[])["aprobada"] is True


def test_el_piso_no_ve_un_dato_real_atribuido_a_otra_pieza():
    """El límite del piso, y la razón del verificador agente: los dos términos
    existen en el catálogo, pero 8 mm es del SI-M18-08P, no del SI-M12-04P."""
    piso = comprobar_literal("El SI-M12-04P detecta a 8 mm.", [], rag.catalogo())
    assert armar_verificacion(piso, SIN_REVISION, codigos_inexistentes=[])["aprobada"] is True


# ---------- Herramienta del verificador ----------


def test_buscar_en_catalogo_devuelve_las_secciones_con_su_fuente():
    resultado = buscar_en_catalogo("SI-M12-04P", rag.catalogo())
    assert resultado["fuentes"][0] == "sensores-inductivos#SI-M12-04P"
    assert "[sensores-inductivos#SI-M12-04P]" in resultado["texto"]
    assert "Distancia de detección: 4 mm" in resultado["texto"]


def test_buscar_en_catalogo_dice_cuando_no_hay_nada():
    resultado = buscar_en_catalogo("SI-M12-06P", rag.catalogo())
    assert resultado["fuentes"] == []
    assert "Sin coincidencias" in resultado["texto"]


def test_buscar_en_catalogo_recorta_las_busquedas_muy_amplias():
    resultado = buscar_en_catalogo("USD", fuentes.todas(), maximo=2)
    assert len(resultado["fuentes"]) > 2
    assert resultado["texto"].count("[") == 2
    assert "secciones más" in resultado["texto"]


# ---------- Cómo se juzga lo que dice el verificador agente ----------

BUSQUEDA_04P = {"termino": "SI-M12-04P", "fuentes": ["sensores-inductivos#SI-M12-04P"]}


def revisada(veredicto, fuente="sensores-inductivos#SI-M12-04P"):
    return {"afirmacion": "El SI-M12-04P detecta a 8 mm", "veredicto": veredicto, "fuente": fuente, "explicacion": "La ficha dice 4 mm."}


def test_una_contradiccion_del_verificador_bloquea_el_envio():
    revision = {"afirmaciones": [revisada("contradicha")], "busquedas": [BUSQUEDA_04P]}
    resultado = armar_verificacion([], revision, codigos_inexistentes=[])
    assert resultado["aprobada"] is False
    assert resultado["motivos"] == ["«El SI-M12-04P detecta a 8 mm» contradice el catálogo: La ficha dice 4 mm."]


def test_respaldada_solo_si_cita_una_seccion_que_la_herramienta_devolvio():
    revision = {"afirmaciones": [revisada("respaldada", fuente="sensores-inductivos#SI-M18-08P")], "busquedas": [BUSQUEDA_04P]}
    resultado = armar_verificacion([], revision, codigos_inexistentes=[])
    assert resultado["revisadas"][0]["veredicto"] == "sin_respaldo"  # citó algo que nunca buscó
    assert resultado["aprobada"] is False


def test_respaldada_con_evidencia_se_aprueba():
    revision = {"afirmaciones": [revisada("respaldada")], "busquedas": [BUSQUEDA_04P]}
    assert armar_verificacion([], revision, codigos_inexistentes=[])["aprobada"] is True


def test_el_verificador_no_puede_quitar_lo_que_bloquea_el_piso():
    piso = comprobar_literal("Le sirve el SI-M12-99P.", [], rag.catalogo())
    revision = {"afirmaciones": [revisada("respaldada")], "busquedas": [BUSQUEDA_04P]}
    assert armar_verificacion(piso, revision, codigos_inexistentes=[])["aprobada"] is False


def test_si_el_verificador_falla_decide_una_persona():
    resultado = armar_verificacion([], SIN_REVISION, codigos_inexistentes=[], error="timeout")
    assert resultado["aprobada"] is False
    assert resultado["error"] == "timeout"


def test_la_pieza_inexistente_que_pide_el_cliente_se_avisa_una_sola_vez():
    piso = comprobar_literal("No encontramos el SI-M12-06P; un asesor le confirmará.", [], rag.catalogo())
    resultado = armar_verificacion(piso, SIN_REVISION, codigos_inexistentes=["SI-M12-06P"])
    assert resultado["motivos"] == ["El cliente pide SI-M12-06P, que no existe en el catálogo."]


def test_el_piso_no_bloquea_repetir_un_dato_que_dio_el_cliente():
    piso = comprobar_literal(
        "Las 25 unidades del SI-M12-04P se piden a fábrica.", [], fuentes.todas(), correo="Necesito 25 unidades del SI-M12-04P."
    )
    estados = {a["texto"]: a["estado"] for a in piso}
    assert estados["25 unidades"] == "del_correo"
    assert armar_verificacion(piso, SIN_REVISION, codigos_inexistentes=[])["aprobada"] is True


def test_el_piso_bloquea_un_stock_que_no_esta_en_el_inventario():
    # Medellín tiene 12 unidades del SI-M12-04P; "40 unidades" no aparece en ninguna fuente.
    piso = comprobar_literal("Tenemos 40 unidades del SI-M12-04P en Medellín.", [], fuentes.todas(), correo="¿Tienen stock?")
    assert {a["texto"]: a["estado"] for a in piso}["40 unidades"] == "no_encontrado"
