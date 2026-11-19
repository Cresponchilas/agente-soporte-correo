"""Búsqueda literal en el catálogo (el "grep") y la búsqueda exacta de códigos.

El RAG vectorial encuentra textos *parecidos*; eso sirve para preguntas, pero falla
justo con lo que más importa en un catálogo: los códigos exactos. "SI-M12-04P" y
"SI-M12-06P" se parecen mucho como vectores y son piezas distintas (una no existe).

Aquí está la búsqueda literal que usan dos pasos del agente:
- la búsqueda exacta (antes de redactar): mete en el contexto la ficha de cada
  número de pieza que nombra el cliente y detecta los que no existen;
- la verificación final (conocimiento/verificacion.py), que comprueba el borrador.

Todo son funciones puras: mismas entradas, mismo resultado, sin red.
"""

import re
import unicodedata

from typing_extensions import TypedDict

from soporte.agente.estado import Fragmento

# Un número de pieza: 2 o 3 letras, guion y uno o más bloques alfanuméricos
# separados por guiones. Ej.: SI-M12-04P, SF-R2M-P, RF-50, VN-52-14-24D, FP-24-10.
PATRON_CODIGO = re.compile(r"(?<![A-Z0-9-])[A-Z]{2,3}(?:-[A-Z0-9]+)+(?![A-Z0-9-])")

# Un dato verificable: un número con unidad o un precio en dólares.
_UNIDADES = r"mm|m|VDC|VAC|A|bar|°C|%|días hábiles|días calendario|días|meses|unidades"
PATRON_DATO = re.compile(rf"USD\s?\d+(?:[.,]\d+)?|\d+(?:[.,]\d+)?\s?(?:{_UNIDADES})(?![A-Za-z])")
_PRECIO_SUELTO = re.compile(r"(?:US\$|\$)\s?(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s?(?:USD|dólares)")


class ResultadoBusquedaExacta(TypedDict):
    codigos: list[str]
    encontrados: dict[str, list[str]]  # código -> fuentes donde aparece
    inexistentes: list[str]


# ---------- Normalización y búsqueda literal ----------


def normalizar(texto: str) -> str:
    """Deja el texto comparable: espacios normales, coma decimal como punto y
    precios escritos de varias formas ("$54", "54 USD") como "USD 54"."""
    texto = unicodedata.normalize("NFC", texto).replace(" ", " ")
    texto = _PRECIO_SUELTO.sub(lambda m: f"USD {m.group(1) or m.group(2)}", texto)
    texto = re.sub(r"(\d),(\d)", r"\1.\2", texto)
    return re.sub(r"\s+", " ", texto)


def contiene(texto: str, termino: str) -> bool:
    """¿Aparece el término en el texto como unidad completa? Así "SI-M12-04P" no
    coincide dentro de "SI-M12-04P-L", ni "8 bar" dentro de "18 bar"."""
    patron = rf"(?<![0-9A-Za-z-]){re.escape(normalizar(termino).casefold())}(?!-?[0-9A-Za-z])"
    return re.search(patron, normalizar(texto).casefold()) is not None


def buscar_en(fragmentos: list[Fragmento], termino: str) -> list[str]:
    """Fuentes de los fragmentos que contienen el término (el "grep"). Primero la sección
    cuyo título es el término (la ficha de la pieza), luego las que solo lo mencionan."""
    fuentes = [f["fuente"] for f in fragmentos if contiene(f["texto"], termino)]
    return sorted(fuentes, key=lambda fuente: not contiene(fuente.split("#")[-1], termino))


# ---------- Extracción ----------


def _sin_repetir(elementos: list[str]) -> list[str]:
    return list(dict.fromkeys(elementos))


def extraer_codigos(texto: str) -> list[str]:
    return _sin_repetir(PATRON_CODIGO.findall(normalizar(texto)))


def extraer_datos(texto: str) -> list[str]:
    return _sin_repetir(m.strip() for m in PATRON_DATO.findall(normalizar(texto)))


# ---------- Búsqueda exacta de los códigos del correo ----------


def busqueda_exacta(correo: str, catalogo: list[Fragmento]) -> tuple[ResultadoBusquedaExacta, list[Fragmento]]:
    """Busca literalmente en el catálogo cada número de pieza del correo del cliente.
    Devuelve el resumen de la búsqueda y las secciones encontradas."""
    codigos = extraer_codigos(correo)
    encontrados = {codigo: buscar_en(catalogo, codigo) for codigo in codigos}
    fuentes = {fuente for lista in encontrados.values() for fuente in lista}
    resultado = ResultadoBusquedaExacta(
        codigos=codigos,
        encontrados={codigo: lista for codigo, lista in encontrados.items() if lista},
        inexistentes=[codigo for codigo, lista in encontrados.items() if not lista],
    )
    return resultado, [f for f in catalogo if f["fuente"] in fuentes]


def combinar_contexto(
    vectorial: list[Fragmento], exacta: list[Fragmento], inventario: list[Fragmento] = ()
) -> list[Fragmento]:
    """Une lo que encontró cada fuente sin repetir y marca de dónde salió cada
    fragmento. Primero lo seguro: la búsqueda exacta y el inventario."""
    fuentes_vectorial = {f["fuente"] for f in vectorial}
    fuentes_exacta = {f["fuente"] for f in exacta}
    combinados: dict[str, Fragmento] = {}
    for fragmento in [*exacta, *inventario, *vectorial]:
        fuente = fragmento["fuente"]
        if fuente in combinados:
            continue
        en_ambas = fuente in fuentes_vectorial and fuente in fuentes_exacta
        if fuente.startswith("inventario#"):
            origen = "inventario"
        else:
            origen = "ambas" if en_ambas else "exacta" if fuente in fuentes_exacta else "vectorial"
        combinados[fuente] = {**fragmento, "origen": origen}
    return list(combinados.values())
