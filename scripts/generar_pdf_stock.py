"""Genera el PDF de stock diario de ejemplo (data/inventario/stock-AAAA-MM-DD.pdf).

En la vida real este PDF lo manda el cliente cada mañana por correo. Aquí se
genera con reportlab para tener un archivo de prueba con una tabla de varias páginas.

    pip install reportlab
    python scripts/generar_pdf_stock.py 2026-11-18
"""

import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

from soporte import config

STOCK = [
    ("SI-M12-04P", "Medellín", 12), ("SI-M12-04P", "Bogotá", 3),
    ("SI-M12-04N", "Medellín", 5),
    ("SI-M18-08P", "Medellín", 8),
    ("SI-M30-15P", "Medellín", 0),
    ("SF-R2M-P", "Medellín", 6),
    ("SF-D60-P", "Medellín", 4),
    ("RF-50", "Medellín", 30),
    ("VN-52-18-24D", "Medellín", 15),
    ("VN-52-14-24D", "Medellín", 7), ("VN-52-14-24D", "Bogotá", 5),
    ("VN-52-18-110A", "Medellín", 0),
    ("VN-52-14-110A", "Medellín", 0),
    ("FP-24-5", "Medellín", 9),
    ("FP-24-10", "Medellín", 0),
]


def main(fecha: str) -> None:
    ruta = config.CARPETA_INVENTARIO / f"stock-{fecha}.pdf"
    filas = [["Código", "Bodega", "Unidades"]] + [[c, b, str(u)] for c, b, u in STOCK]
    tabla = Table(filas, repeatRows=1, colWidths=[160, 120, 80])
    tabla.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey)]))
    estilos = getSampleStyleSheet()
    SimpleDocTemplate(str(ruta), pagesize=letter).build(
        [Paragraph(f"Inventario al {fecha}", estilos["Title"]), Paragraph("Andina Automatización - stock por bodega", estilos["Normal"]), tabla]
    )
    print(f"Generado {ruta}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "2026-11-18")
