"""El grafo de conocimiento: las equivalencias se calculan con reglas, no con un LLM."""

from soporte.conocimiento import grafo_de_equivalencias as grafo


def sensor(codigo, marca="Andina", minimo=10, maximo=30, salida="PNP", distancia=4, estado="activo"):
    return {
        "codigo": codigo, "marca": marca, "familia": "sensor inductivo", "tamano": "M12", "distancia_mm": distancia,
        "salida": salida, "conexion": "M12 4 pines", "alimentacion_min_vdc": minimo, "alimentacion_max_vdc": maximo,
        "salida_vdc": None, "estado": estado,
    }


def test_sustituye_si_coincide_la_forma_y_cubre_la_alimentacion():
    assert grafo.puede_sustituir(sensor("PX-1", marca="Proxima", minimo=12, maximo=24), sensor("SI-1"))


def test_la_sustitucion_es_dirigida():
    # Uno de 12 a 24 VDC no sirve donde se necesitaba uno de 10 a 30 VDC.
    assert grafo.puede_sustituir(sensor("SI-1"), sensor("SI-2", minimo=12, maximo=24)) is None


def test_no_sustituye_si_cambia_la_salida_o_la_distancia():
    original = sensor("PX-1", marca="Proxima")
    assert grafo.puede_sustituir(original, sensor("SI-1", salida="NPN")) is None
    assert grafo.puede_sustituir(original, sensor("SI-1", distancia=8)) is None


def test_solo_ofrece_piezas_activas_de_la_marca_propia():
    original = sensor("SI-1")
    assert grafo.puede_sustituir(original, sensor("KT-1", marca="Kentra")) is None
    assert grafo.puede_sustituir(original, sensor("SI-2", estado="descontinuado")) is None


def test_el_json_guardado_esta_al_dia_con_las_especificaciones():
    # Si alguien edita especificaciones.csv o relaciones.json, tiene que regenerar el grafo.
    assert grafo.construir() == grafo.cargar(), "Corre: python -m soporte.conocimiento.grafo_de_equivalencias"


def test_varios_saltos_pieza_de_otra_marca_a_su_fuente():
    tipos = {(a["de"], a["tipo"], a["a"]) for a in grafo.vecindario("PX-12-4P")}
    assert ("PX-12-4P", "sustituible_por", "SI-M12-04P") in tipos
    assert ("FP-24-5", "puede_alimentar", "SI-M12-04P") in tipos  # segundo salto


def test_descontinuado_a_su_reemplazo_y_su_accesorio():
    tipos = {(a["de"], a["tipo"], a["a"]) for a in grafo.vecindario("SF-R15-P")}
    assert ("SF-R15-P", "reemplazado_por", "SF-R2M-P") in tipos  # sale del documento
    assert ("SF-R2M-P", "requiere", "RF-50") in tipos


def test_dice_cuando_no_hay_sustituto():
    texto = grafo.como_fragmento("KT-M30-20P")["texto"]
    assert "Ninguna pieza de Andina sustituye a KT-M30-20P" in texto


def test_una_pieza_desconocida_no_genera_relaciones():
    assert grafo.como_fragmento("ZZ-999") is None
