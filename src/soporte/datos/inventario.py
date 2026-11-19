"""Precios y stock en una base de datos SQL (SQLite), no en el RAG.

Por qué: el precio y el stock cambian seguido. Si vivieran en los fragmentos que se
vectorizan, el agente podría leer un dato viejo y decir "hay 2 en stock" cuando hay 0.
Para cada dato hay UNA fuente de verdad, y para estos es esta base.

De dónde salen los datos (como los manda el cliente):
- precios.csv: la lista de precios que se actualiza una vez al mes.
- stock-AAAA-MM-DD.pdf: el PDF diario con la tabla de stock por bodega.

Las dos cargas validan antes de tocar la base y reemplazan los datos dentro de una
transacción: si algo falla, queda lo de ayer, completo y con su fecha.

    python -m soporte.datos.inventario        # reconstruye la base desde data/inventario/
"""

import csv
import logging
import re
import sqlite3
import threading
from contextlib import closing
from datetime import date
from pathlib import Path

import pdfplumber
from typing_extensions import TypedDict

from soporte import config
from soporte.agente.estado import Fragmento

logger = logging.getLogger(__name__)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS productos (
    codigo              TEXT PRIMARY KEY,
    precio_usd          REAL    NOT NULL CHECK (precio_usd > 0),
    plazo_a_pedido_dias INTEGER NOT NULL CHECK (plazo_a_pedido_dias >= 0),
    vigente_desde       TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS stock (
    codigo   TEXT    NOT NULL REFERENCES productos(codigo),
    bodega   TEXT    NOT NULL,
    unidades INTEGER NOT NULL CHECK (unidades >= 0),
    fecha    TEXT    NOT NULL,
    PRIMARY KEY (codigo, bodega)
);
"""

COLUMNAS_PRECIOS = {"codigo", "precio_usd", "plazo_a_pedido_dias", "vigente_desde"}
COLUMNAS_STOCK = {"Código", "Bodega", "Unidades"}  # las que se necesitan; si el PDF trae más, se ignoran
_FECHA_DEL_PDF = re.compile(r"Inventario al (\d{4}-\d{2}-\d{2})")


class ErrorDeCarga(ValueError):
    """El archivo del cliente no tiene el formato esperado. No se cambia nada en la base."""


class Existencias(TypedDict):
    codigo: str
    precio_usd: float
    plazo_a_pedido_dias: int
    vigente_desde: str
    stock: dict[str, int]  # bodega -> unidades
    fecha_stock: str | None


# ---------- Conexión ----------


def conectar(archivo: Path | None = None) -> sqlite3.Connection:
    conexion = sqlite3.connect(archivo or config.ARCHIVO_INVENTARIO)
    conexion.row_factory = sqlite3.Row
    # SQLite no revisa las llaves foráneas si no se le pide: así se rechaza stock de
    # una pieza que no está en la lista de precios.
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.executescript(ESQUEMA)
    return conexion


# ---------- Cargas (validar primero, después reemplazar en una transacción) ----------


def leer_precios(ruta: Path) -> list[dict]:
    with ruta.open(encoding="utf-8", newline="") as archivo:
        filas = list(csv.DictReader(archivo))
    if not filas or not COLUMNAS_PRECIOS <= set(filas[0]):
        raise ErrorDeCarga(f"{ruta.name}: faltan columnas; se esperan {sorted(COLUMNAS_PRECIOS)}")
    try:
        return [
            {
                "codigo": f["codigo"].strip(),
                "precio_usd": float(f["precio_usd"]),
                "plazo_a_pedido_dias": int(f["plazo_a_pedido_dias"]),
                "vigente_desde": date.fromisoformat(f["vigente_desde"].strip()).isoformat(),
            }
            for f in filas
        ]
    except ValueError as error:
        raise ErrorDeCarga(f"{ruta.name}: un valor no tiene el tipo esperado ({error})") from error


def leer_stock_pdf(ruta: Path) -> tuple[str, list[dict]]:
    """Extrae la tabla del PDF como tabla (no como texto partido en fragmentos), página
    por página. Devuelve la fecha del inventario y una fila por pieza y bodega.

    pdfplumber encuentra las tablas por sus líneas: sirve porque el PDF del cliente
    siempre trae la tabla con bordes. Un PDF escaneado no tendría texto y necesitaría OCR."""
    filas: list[dict] = []
    with pdfplumber.open(ruta) as pdf:
        encontrada = _FECHA_DEL_PDF.search(pdf.pages[0].extract_text() or "")
        if not encontrada:
            raise ErrorDeCarga(f"{ruta.name}: no se encontró la fecha 'Inventario al AAAA-MM-DD'")
        encabezado: list[str] | None = None
        for pagina in pdf.pages:
            for tabla in pagina.extract_tables():
                if tabla and COLUMNAS_STOCK <= set(tabla[0]):
                    encabezado, tabla = tabla[0], tabla[1:]  # página con encabezado
                if encabezado is None:
                    raise ErrorDeCarga(f"{ruta.name}: la tabla no trae las columnas {sorted(COLUMNAS_STOCK)}")
                filas += [dict(zip(encabezado, fila)) for fila in tabla]  # si no lo repite, se usa el anterior
    if not filas:
        raise ErrorDeCarga(f"{ruta.name}: no se encontró una tabla de stock con filas")
    try:
        return encontrada.group(1), [
            {"codigo": f["Código"].strip(), "bodega": f["Bodega"].strip(), "unidades": int(f["Unidades"])} for f in filas
        ]
    except (TypeError, ValueError) as error:
        raise ErrorDeCarga(f"{ruta.name}: una fila no tiene el formato esperado ({error})") from error


def cargar_precios(conexion: sqlite3.Connection, ruta: Path) -> int:
    filas = leer_precios(ruta)  # si el archivo está mal, falla aquí, antes de tocar la base
    with conexion:  # una transacción: todo o nada
        conexion.execute("DELETE FROM stock")  # el stock depende de los productos
        conexion.execute("DELETE FROM productos")
        conexion.executemany(
            "INSERT INTO productos VALUES (:codigo, :precio_usd, :plazo_a_pedido_dias, :vigente_desde)", filas
        )
    return len(filas)


def cargar_stock(conexion: sqlite3.Connection, ruta: Path) -> int:
    fecha, filas = leer_stock_pdf(ruta)
    try:
        with conexion:
            # Borrar y volver a cargar dentro de la misma transacción: quien consulte
            # mientras tanto sigue viendo el stock de ayer, nunca una tabla vacía.
            conexion.execute("DELETE FROM stock")
            conexion.executemany(
                "INSERT INTO stock VALUES (:codigo, :bodega, :unidades, :fecha)",
                [{**f, "fecha": fecha} for f in filas],
            )
    except sqlite3.IntegrityError as error:  # pieza desconocida, unidades negativas, fila repetida
        raise ErrorDeCarga(f"{ruta.name}: {error}; se conserva el stock anterior") from error
    return len(filas)


def ultimo_pdf_de_stock(carpeta: Path) -> Path:
    pdfs = sorted(carpeta.glob("stock-*.pdf"))  # el nombre lleva la fecha: el último es el más reciente
    if not pdfs:
        raise ErrorDeCarga(f"No hay PDFs de stock en {carpeta}")
    return pdfs[-1]


def construir(archivo: Path | None = None, carpeta: Path | None = None) -> None:
    carpeta = carpeta or config.CARPETA_INVENTARIO
    with closing(conectar(archivo)) as conexion:
        productos = cargar_precios(conexion, carpeta / "precios.csv")
        filas = cargar_stock(conexion, ultimo_pdf_de_stock(carpeta))
    logger.info("Inventario cargado: %s productos, %s filas de stock", productos, filas)


_candado = threading.Lock()


def asegurar_base() -> None:
    """Crea la base la primera vez. Con candado porque varias ramas del grafo corren
    en paralelo y no deben construirla dos veces a la vez."""
    with _candado:
        with closing(conectar()) as conexion:
            vacia = conexion.execute("SELECT COUNT(*) FROM productos").fetchone()[0] == 0
        if vacia:
            construir()


# ---------- Consultas (siempre con parámetros) ----------


def consultar(codigos: list[str], archivo: Path | None = None) -> list[Existencias]:
    """Precio y stock por bodega de las piezas pedidas.

    Los códigos llegan desde el correo del cliente, así que van como parámetros (?):
    el motor los trata como datos, nunca como SQL. Pegarlos en el texto de la consulta
    permitiría que un correo con  x'; DROP TABLE stock; --  borrara la tabla.
    """
    if not codigos:
        return []
    marcadores = ", ".join("?" for _ in codigos)  # un ? por código; los valores van aparte
    consulta = f"""
        SELECT p.codigo, p.precio_usd, p.plazo_a_pedido_dias, p.vigente_desde,
               s.bodega, s.unidades, s.fecha
        FROM productos p
        LEFT JOIN stock s ON s.codigo = p.codigo
        WHERE p.codigo IN ({marcadores})
        ORDER BY p.codigo, s.bodega
    """
    existencias: dict[str, Existencias] = {}
    with closing(conectar(archivo)) as conexion:
        for fila in conexion.execute(consulta, codigos):
            item = existencias.setdefault(
                fila["codigo"],
                Existencias(
                    codigo=fila["codigo"],
                    precio_usd=fila["precio_usd"],
                    plazo_a_pedido_dias=fila["plazo_a_pedido_dias"],
                    vigente_desde=fila["vigente_desde"],
                    stock={},
                    fecha_stock=fila["fecha"],
                ),
            )
            if fila["bodega"] is not None:
                item["stock"][fila["bodega"]] = fila["unidades"]
    return list(existencias.values())


def todos_los_codigos(archivo: Path | None = None) -> list[str]:
    with closing(conectar(archivo)) as conexion:
        return [fila["codigo"] for fila in conexion.execute("SELECT codigo FROM productos ORDER BY codigo")]


# ---------- Como texto para el agente ----------


def _precio(valor: float) -> str:
    return f"USD {valor:g}"


def como_fragmento(e: Existencias) -> Fragmento:
    """Lo que ve el modelo de cada pieza: precio y stock con su fecha, para que pueda
    decir "según el inventario del 18 de noviembre" en vez de prometer."""
    lineas = [e["codigo"], f"- Precio: {_precio(e['precio_usd'])} por unidad (lista vigente desde {e['vigente_desde']})"]
    con_unidades = {bodega: n for bodega, n in e["stock"].items() if n > 0}
    if e["fecha_stock"] is None:
        lineas.append("- Stock: no aparece en el último inventario; un asesor debe confirmarlo")
    elif con_unidades:
        detalle = ", ".join(f"{bodega} {n} unidades" for bodega, n in con_unidades.items())
        lineas.append(f"- Stock al {e['fecha_stock']}: {detalle}")
    else:
        lineas.append(f"- Stock al {e['fecha_stock']}: sin unidades; a pedido, entrega en {e['plazo_a_pedido_dias']} días hábiles")
    return Fragmento(fuente=f"inventario#{e['codigo']}", texto="\n".join(lineas))


def fragmentos(codigos: list[str] | None = None) -> list[Fragmento]:
    asegurar_base()
    return [como_fragmento(e) for e in consultar(codigos if codigos is not None else todos_los_codigos())]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    config.ARCHIVO_INVENTARIO.unlink(missing_ok=True)
    construir()
