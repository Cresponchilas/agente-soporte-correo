from soporte.api.eventos import TraductorDeTareas, evento_sse


def test_traductor_mide_duracion_y_emite_pausa():
    reloj = iter([10.0, 10.25])
    traductor = TraductorDeTareas(reloj=lambda: next(reloj))

    inicio = traductor.traducir({"id": "t1", "name": "revision_humana", "input": {}, "triggers": ()})
    fin = traductor.traducir(
        {"id": "t1", "name": "revision_humana", "result": {}, "error": None, "interrupts": [{"value": {"borrador": "hola"}}]}
    )

    assert inicio == [("nodo_inicio", {"id": "t1", "nodo": "revision_humana"})]
    assert fin[0][0] == "nodo_fin" and fin[0][1]["duracion_ms"] == 250
    assert fin[1] == ("pausa", {"nodo": "revision_humana", "solicitud": {"borrador": "hola"}})


def test_evento_sse_tiene_formato_valido():
    texto = evento_sse("paso", {"nodo": "clasificar", "nota": "ñandú"})
    lineas = texto.split("\n")
    assert lineas[0] == "event: paso"
    assert lineas[1].startswith("data: {") and "ñandú" in lineas[1]
    assert texto.endswith("\n\n")
