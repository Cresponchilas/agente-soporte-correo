from soporte import config, kb


def test_cada_seccion_es_un_fragmento_con_fuente():
    documentos = kb.cargar_documentos(config.CARPETA_KB)
    fuentes = [d.metadata["fuente"] for d in documentos]

    assert "cobros-y-facturacion#Cobro duplicado" in fuentes
    assert len(fuentes) == len(set(fuentes))  # sin secciones repetidas
    assert all(not d.page_content.startswith("#") for d in documentos)  # sin el título del archivo


def test_buscar_devuelve_k_fragmentos():
    fragmentos = kb.buscar("me cobraron dos veces", k=2)
    assert len(fragmentos) == 2
    assert set(fragmentos[0]) == {"fuente", "texto"}
