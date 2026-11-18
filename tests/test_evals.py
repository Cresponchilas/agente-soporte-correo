"""Los evaluadores de código y la función objetivo también se prueban."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evals"))

import run_evals  # noqa: E402


def test_intencion_correcta_acepta_lista_de_validas():
    salida = {"clasificacion": {"intencion": "pregunta"}}
    assert run_evals.intencion_correcta(salida, {"intencion": ["facturacion", "pregunta"]})
    assert not run_evals.intencion_correcta(salida, {"intencion": "bug"})


def test_objetivo_reporta_si_pidio_revision(clasificacion_falsa):
    clasificacion_falsa(intencion="facturacion", urgencia="alta")
    salida = run_evals.objetivo({"remitente": "x@y.co", "asunto": "a", "cuerpo": "me cobraron dos veces"})
    assert salida["pidio_revision"] is True
    assert salida["borrador"]
    assert run_evals.revision_correcta(salida, {"necesita_revision": True})
