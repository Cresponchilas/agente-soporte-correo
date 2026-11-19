"""Precios y stock en SQL: la carga valida antes de tocar la base, reemplaza en una
transacción, y las consultas usan parámetros."""

import shutil
import sqlite3
from contextlib import closing

import pytest

from soporte import config
from soporte.datos import inventario


@pytest.fixture
def carpeta(tmp_path):
    """Una copia de data/inventario para poder dañar archivos sin tocar los reales."""
    destino = tmp_path / "fuentes"
    shutil.copytree(config.CARPETA_INVENTARIO, destino)
    return destino


@pytest.fixture
def base(tmp_path, carpeta):
    archivo = tmp_path / "base.sqlite"
    inventario.construir(archivo, carpeta)
    return archivo


def generar_pdf(ruta, filas, titulo="Inventario al 2026-11-19"):
    """Un PDF de stock como el que manda el cliente, con la tabla que le pasemos."""
    pytest.importorskip("reportlab")
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

    tabla = Table(filas, repeatRows=1)
    tabla.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]))  # con líneas, como el del cliente
    SimpleDocTemplate(str(ruta), pagesize=letter).build([Paragraph(titulo, getSampleStyleSheet()["Title"]), tabla])


def stock_de(base, codigo):
    return inventario.consultar([codigo], base)[0]["stock"]


# ---------- Carga ----------


def test_construye_la_base_desde_el_csv_y_el_pdf(base):
    existencias = inventario.consultar(["SI-M12-04P"], base)[0]
    assert existencias["precio_usd"] == 38
    assert existencias["stock"] == {"Bogotá": 3, "Medellín": 12}  # el PDF tiene dos bodegas
    assert existencias["fecha_stock"] == "2026-11-18"  # la fecha sale del título del PDF


def test_lee_la_tabla_del_pdf_como_tabla(carpeta):
    fecha, filas = inventario.leer_stock_pdf(inventario.ultimo_pdf_de_stock(carpeta))
    assert fecha == "2026-11-18"
    assert {"codigo": "VN-52-14-24D", "bodega": "Bogotá", "unidades": 5} in filas


def test_una_columna_nueva_no_rompe_la_carga(base, tmp_path):
    pdf = tmp_path / "con-columna-nueva.pdf"
    generar_pdf(pdf, [["Código", "Bodega", "Unidades", "Lote"], ["SI-M12-04P", "Medellín", "7", "L-01"]])
    with closing(inventario.conectar(base)) as conexion:
        inventario.cargar_stock(conexion, pdf)
    assert stock_de(base, "SI-M12-04P") == {"Medellín": 7}


def test_si_falta_una_columna_no_se_toca_el_stock(base, tmp_path):
    pdf = tmp_path / "sin-unidades.pdf"
    generar_pdf(pdf, [["Código", "Bodega"], ["SI-M12-04P", "Medellín"]])
    with closing(inventario.conectar(base)) as conexion, pytest.raises(inventario.ErrorDeCarga, match="columnas"):
        inventario.cargar_stock(conexion, pdf)
    assert stock_de(base, "SI-M12-04P") == {"Bogotá": 3, "Medellín": 12}  # queda lo de ayer


def test_una_fila_mala_deshace_toda_la_carga(base, tmp_path):
    """La primera fila es válida y la segunda tiene una pieza que no existe: la
    transacción se deshace completa, no queda la primera fila a medias."""
    pdf = tmp_path / "pieza-desconocida.pdf"
    generar_pdf(pdf, [["Código", "Bodega", "Unidades"], ["SI-M12-04P", "Medellín", "1"], ["XX-999", "Medellín", "5"]])
    with closing(inventario.conectar(base)) as conexion, pytest.raises(inventario.ErrorDeCarga, match="se conserva"):
        inventario.cargar_stock(conexion, pdf)
    assert stock_de(base, "SI-M12-04P") == {"Bogotá": 3, "Medellín": 12}


def test_un_precio_invalido_no_se_carga(base, carpeta):
    (carpeta / "precios.csv").write_text("codigo,precio_usd,plazo_a_pedido_dias,vigente_desde\nSI-M12-04P,gratis,10,2026-12-01\n")
    with closing(inventario.conectar(base)) as conexion, pytest.raises(inventario.ErrorDeCarga, match="tipo"):
        inventario.cargar_precios(conexion, carpeta / "precios.csv")
    assert inventario.consultar(["SI-M12-04P"], base)[0]["precio_usd"] == 38


def test_las_reglas_las_impone_la_base(base):
    with closing(inventario.conectar(base)) as conexion, pytest.raises(sqlite3.IntegrityError):
        conexion.execute("INSERT INTO productos VALUES ('ZZ-1', -5, 1, '2026-11-01')")  # CHECK precio > 0


# ---------- Consultas ----------


def test_consulta_con_parametros_no_ejecuta_sql_del_correo(base):
    ataque = "x'); DROP TABLE stock; --"
    assert inventario.consultar([ataque], base) == []  # se buscó como texto: no hay pieza con ese código
    assert stock_de(base, "SI-M12-04P")  # la tabla sigue ahí


def test_pieza_sin_stock_dice_el_plazo(base):
    fragmento = inventario.como_fragmento(inventario.consultar(["SI-M30-15P"], base)[0])
    assert fragmento["fuente"] == "inventario#SI-M30-15P"
    assert "sin unidades; a pedido, entrega en 10 días hábiles" in fragmento["texto"]


def test_la_base_se_crea_sola_la_primera_vez():
    # conftest apunta config.ARCHIVO_INVENTARIO a un archivo que todavía no existe.
    assert not config.ARCHIVO_INVENTARIO.exists()
    assert {f["fuente"] for f in inventario.fragmentos(["RF-50"])} == {"inventario#RF-50"}
