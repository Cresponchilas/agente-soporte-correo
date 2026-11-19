# Agente de soporte por correo (LangGraph + LangSmith)

> Corre todo en tu computador con un solo comando: `python -m soporte.api` abre el dashboard en
> http://localhost:8000. Solo necesitas una llave de OpenAI (y una de LangSmith para ver las trazas).

Atiende los correos de clientes de **Andina Automatización**, un distribuidor ficticio de componentes de
automatización industrial (sensores, válvulas neumáticas, fuentes de poder), con un catálogo de números de pieza:

1. **Clasifica** el correo (intención y urgencia) con salida estructurada.
2. **Junta contexto en paralelo:**
   - **búsqueda vectorial** (RAG) en el catálogo;
   - **búsqueda exacta**: cada número de pieza del correo se busca literalmente en el catálogo (como `grep`);
   - consulta el historial del cliente;
   - abre un caso si es una garantía o la línea del cliente está parada.
3. **Redacta** una respuesta usando solo lo que encontraron las dos búsquedas.
4. **Verifica** el borrador en dos capas: un piso literal sin LLM (cada número de pieza y dato con unidad
   tiene que existir en el catálogo) y un **verificador agente**, un segundo LLM que elige qué más comprobar
   y busca en el catálogo con una herramienta determinista.
5. **Decide con código** si una persona debe revisarla: por la verificación o por reglas de negocio. Si sí,
   **se pausa** con `interrupt()` y espera a que alguien apruebe, edite o rechace, viendo el motivo.
6. **Envía** la respuesta (simulado).

Todo queda trazado en LangSmith, y hay evals con evaluadores de código y un LLM como juez.

## La idea: no confiar en la similitud para lo que tiene que ser exacto

Un RAG vectorial encuentra textos *parecidos*. Para un catálogo eso es un riesgo: `SI-M12-04P` y
`SI-M12-06P` se parecen mucho como vectores, pero la segunda pieza no existe. Un modelo que recibe la ficha
de la primera puede contestar sobre la segunda con total seguridad.

Por eso la búsqueda literal (`conocimiento/busqueda.py` y `conocimiento/verificacion.py`, en la línea de "grep is all you need") aparece en
dos momentos con trabajos distintos: uno **previene** y el otro **detecta**.

| Paso | Cuándo | Qué hace | Para qué |
|---|---|---|---|
| Búsqueda exacta | En paralelo con la vectorial, antes de redactar | Busca literalmente los números de pieza del correo | **Previene:** el modelo recibe la ficha correcta aunque la vectorial no la traiga, y se sabe si el cliente pide una pieza que no existe |
| Piso literal | Después de redactar | Extrae números de pieza y datos con unidad del borrador y los busca tal cual | **Detecta** referencias, precios o medidas inventadas |
| Verificador agente | Después de redactar | Un LLM elige qué afirmaciones comprobar y las busca con la herramienta `buscar_en_catalogo` | **Detecta** lo que una regex no ve: un dato real atribuido a otra pieza, compatibilidades, políticas |

### Por qué hay un verificador agente

El piso literal tiene un punto ciego: comprueba que cada término exista, no a qué pieza pertenece.
"El SI-M12-04P detecta a 8 mm" pasa el piso, porque `SI-M12-04P` y `8 mm` existen en el catálogo, pero
8 mm es del SI-M18-08P. El verificador agente lee la ficha que devuelve su búsqueda y marca la afirmación
como contradicha.

Cómo se reparte el trabajo:

- **El LLM decide qué buscar; la herramienta decide qué hay.** `buscar_en_catalogo` es la misma búsqueda
  literal, sin LLM. El modelo no puede "encontrar" algo que no está.
- **El piso no se negocia.** El verificador puede agregar comprobaciones, pero no quitar las del piso.
- **No se le cree sin evidencia.** Una afirmación solo cuenta como respaldada si cita una sección que la
  herramienta de verdad devolvió en esa verificación; si no, el código la baja a "sin respaldo".
- **El código decide.** Cualquier contradicción, afirmación sin respaldo o falla del verificador (timeout,
  veredicto mal formado, se le acabaron las vueltas) manda la respuesta a revisión humana. Lo peor que puede
  pasar es revisar de más, no dejar pasar un invento.
- **Es un agente con tope.** Un loop de herramientas de máximo 5 vueltas con `tool_choice="any"`: en cada vuelta
  tiene que buscar o entregar el veredicto (que es otra herramienta con esquema Pydantic), así que nunca
  responde en texto libre. Si entrega el veredicto en la misma vuelta en que pide búsquedas, no se acepta:
  lo escribió antes de leer los resultados.

En el piso literal, cada dato del borrador queda en uno de tres estados:

- **respaldado:** está en lo que el modelo vio;
- **fuera de contexto:** existe en el catálogo, pero el modelo no lo vio (se informa, no se bloquea);
- **no encontrado:** no aparece en ninguna parte del catálogo. Bloquea el envío y lo manda a revisión humana con el motivo.

La comparación es literal pero cuidadosa: `SI-M12-04P` no coincide dentro de `SI-M12-04P-L`, `8 bar` no coincide
dentro de `18 bar`, y `$54`, `54 USD` y `USD 54` cuentan como el mismo precio. Sus límites, a propósito: no
entiende sinónimos ni paráfrasis (solo comprueba lo que se puede comprobar literalmente) y no valida cálculos;
por eso el prompt pide no calcular totales.

## El grafo

```mermaid
graph TD
    START([START]) --> recibir_correo --> clasificar
    clasificar -.-> buscar_documentacion
    clasificar -.-> busqueda_exacta
    clasificar -.-> consultar_historial
    clasificar -.-> crear_ticket
    buscar_documentacion --> redactar_respuesta
    busqueda_exacta --> redactar_respuesta
    consultar_historial --> redactar_respuesta
    crear_ticket --> redactar_respuesta
    redactar_respuesta --> verificar_respuesta
    verificar_respuesta -.-> revision_humana
    verificar_respuesta -.-> enviar_respuesta
    revision_humana -.-> enviar_respuesta
    revision_humana -.-> END([END])
    enviar_respuesta --> END
```

Las líneas punteadas son rutas condicionales.

| Concepto | Dónde está |
|---|---|
| Estado compartido y reductor (`operator.add`) | `agente/estado.py`, clave `pasos` |
| Salida estructurada (Pydantic) | `agente/llm.py`, `clasificar_con_llm` |
| RAG: fragmentar, hacer embeddings y buscar | `conocimiento/rag.py` |
| Búsqueda exacta (el "grep") | `conocimiento/busqueda.py`, nodo `busqueda_exacta` |
| Verificación: piso literal y reglas que juzgan al verificador | `conocimiento/verificacion.py`, nodo `verificar_respuesta` |
| Agente con herramientas (loop con tope, `bind_tools`, `tool_choice`) | `agente/verificador.py`, `tests/test_verificador_agente.py` |
| Arista condicional con varias ramas en paralelo | `nodos.rutas_tras_clasificar` + `agente/flujo.py` |
| `Command` (actualizar estado y enrutar a la vez) | `nodos.verificar_respuesta`, `nodos.revision_humana` |
| Human in the loop con `interrupt()` | `nodos.revision_humana` |
| Checkpointer (SQLite) y `thread_id` | `api/persistencia.py`, `tests/test_api.py` |
| Errores guardados en el estado, sin tumbar el grafo | `nodos.buscar_documentacion` |
| Evals: código + LLM juez estrecho y binario | `evals/run_evals.py` |

## Mapa del código

```
src/soporte/
├── config.py              modelos y rutas, desde variables de entorno
├── servicios.py           sistemas externos simulados: CRM, tickets, envío de correo
├── agente/                el agente: qué pasos da y en qué orden
│   ├── estado.py          el estado compartido (el contrato entre nodos) y los esquemas Pydantic
│   ├── flujo.py           el grafo de LangGraph: nodos y aristas (flujo de control)
│   ├── nodos.py           lo que hace cada paso
│   ├── prompts.py         los prompts
│   ├── llm.py             clasificar y redactar: las llamadas directas al modelo
│   └── verificador.py     el verificador agente: un LLM con una herramienta de búsqueda
├── conocimiento/          de dónde saca el agente lo que sabe
│   ├── rag.py             búsqueda vectorial sobre data/kb
│   ├── busqueda.py        búsqueda literal y búsqueda exacta de códigos
│   └── verificacion.py    piso literal y reglas que juzgan al verificador
├── api/                   FastAPI: transmite el grafo como eventos al dashboard
└── web/                   el dashboard (HTML, CSS y JavaScript sin compilar)
```

Regla de dependencias: `agente/` usa a `conocimiento/`, nunca al revés (salvo los tipos
de `agente/estado.py`). Así lo que sabe el agente se puede probar sin el agente.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate          # En Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env               # llena OPENAI_API_KEY y LANGSMITH_API_KEY
```

## Cómo usarlo

```bash
python -m soporte.api              # dashboard en http://localhost:8000 y API en /docs (abre el navegador)
pytest                             # tests del backend, sin llaves y sin gastar tokens (LLM falso)
node --test tests/js/logica.test.mjs   # opcional, si tienes Node: tests de la lógica del dashboard
python scripts/demo.py             # procesa los 8 correos de ejemplo y te pide aprobar en consola
python scripts/demo.py 4           # solo el correo #4 (línea parada, pide revisión)
langgraph dev --allow-blocking     # abre LangGraph Studio con el grafo
python evals/run_evals.py          # crea el dataset en LangSmith y corre el experimento
```

### En LangGraph Studio

1. Corre `langgraph dev --allow-blocking` y abre el enlace de Studio que aparece en la terminal.
   (`--allow-blocking` evita que el servidor de desarrollo bloquee el tracer de LangSmith, que hace
   llamadas síncronas al iniciar; sin él, las corridas de Studio no aparecen en LangSmith.)
2. En *Input* llena `remitente`, `asunto` y `cuerpo` (el grafo declara ese esquema de entrada), por ejemplo:
   ```json
   {"remitente": "mantenimiento@textilesandes.com", "asunto": "Línea parada", "cuerpo": "El sensor SI-M12-04P dejó de detectar y tenemos la línea parada."}
   ```
3. Mira cómo corren en paralelo las ramas de contexto y cómo el grafo se detiene en `revision_humana`.
4. Reanuda con `{"accion": "aprobar"}`, `{"accion": "editar", "texto": "..."}` o `{"accion": "rechazar"}`.
5. Abre la traza en LangSmith para ver el prompt, los fragmentos recuperados y los tokens de cada paso.

## El dashboard y la API

`python -m soporte.api` levanta un solo servidor (FastAPI) que sirve dos cosas:

- **El dashboard** en `/`: HTML, CSS y JavaScript sin compilar (`src/soporte/web/`). Bandeja de casos de prueba,
  detalle con la revisión humana y un panel de tránsito con cada nodo del grafo en vivo.
- **La API** en `/api`, que transmite cada paso del grafo como Server-Sent Events:

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/salud` | Estado del servidor y dónde guarda los checkpoints (sqlite o memoria) |
| GET | `/api/casos` | Los correos de prueba con su resultado esperado |
| POST | `/api/corridas` | Procesa un correo y transmite eventos: `inicio`, `nodo_inicio`, `nodo_fin`, `pausa`, `fin`, `error` |
| POST | `/api/corridas/{id}/decision` | Reanuda una corrida pausada con `aprobar`, `editar` o `rechazar` |
| GET | `/api/corridas/{id}` | Estado actual de una corrida |

Los checkpoints del grafo se guardan en `data/checkpoints.sqlite`: si cierras el servidor con una corrida
esperando revisión, al volver a abrirlo (y recargar la página) puedes aprobarla. Con `CHECKPOINTS=memoria`
en `.env` se guardan en memoria.

Cómo falla de forma controlada:

- **Entradas inválidas:** 422 con el campo y el mensaje (`{"error": ..., "detalles": [...]}`).
- **Errores a mitad del grafo:** llegan como evento `error` con un mensaje para el usuario; el detalle técnico solo va al log.
- **Corrida inexistente o que no espera decisión:** 404 o 409.
- **Servidor apagado:** el dashboard lo indica y ofrece reintentar.
- **Llamadas al modelo:** con timeout y reintentos.

## Costo

Por defecto se usa `gpt-4.1-mini` y `text-embedding-3-small`; los dos se cambian en `.env`. Con los precios publicados por OpenAI (revísalos antes de usar), un correo cuesta del orden de **un décimo de centavo de dólar**: clasificar, redactar y dos o tres vueltas del verificador. Una corrida completa de evals (8 correos más el juez) cuesta unos **2 centavos**. Configura un límite de gasto en el panel de OpenAI.

## Decisiones de diseño

- **Workflow, no agente libre.** El camino se conoce de antemano, así que un grafo explícito es más predecible y fácil de probar que un loop ReAct que decide solo.
- **El LLM clasifica, redacta y opina; el código decide.** Quién revisa lo deciden `motivos_de_negocio` y `armar_verificacion`, no el prompt.
- **Un agente solo donde hace falta.** El flujo general es un workflow; el único paso con autonomía es elegir qué comprobar, y tiene tope de vueltas, herramientas deterministas y la decisión final fuera del modelo.
- **Lo exacto se comprueba con búsqueda exacta.** Los embeddings sirven para encontrar; para confirmar un número de pieza o un precio se usa comparación literal.
- **`interrupt()` al inicio del nodo.** Al reanudar, el nodo se ejecuta otra vez desde el principio; nada costoso o con efectos va antes de la pausa.
- **Estado con tipos simples.** La clasificación se guarda como dict para que serialice bien en el checkpointer y se lea fácil en Studio.
- **LLM aislado en `agente/llm.py` y `agente/verificador.py`.** Los tests lo reemplazan con `monkeypatch`, así que corren sin red y sin costo.
- **Un fragmento por sección del markdown.** Cada sección responde una sola pregunta, y la fuente (`archivo#sección`) se puede citar.

## Cómo se construyó

En PRs apilados; cada uno parte del anterior y deja los tests en verde:

1. `pr/01-flujo-basico`: flujo lineal y salida estructurada.
2. `pr/02-rag-y-contexto`: RAG, historial y tickets en paralelo.
3. `pr/03-revision-humana`: `interrupt()` y `Command`.
4. `pr/04-evals-y-demo`: evals en LangSmith, la demo y esta documentación.
5. `pr/05-ajustes-studio-y-tests`: correcciones tras probarlo en Windows (numpy faltante,
   esquema de entrada para Studio, prompt que usa los datos concretos de la documentación).
6. `pr/06-api`: API FastAPI con streaming, checkpointer Postgres y límites de uso.
7. `pr/07-dashboard`: dashboard en Next.js con panel de tránsito en vivo y casos de prueba.
8. `pr/08-ejecucion-local`: todo local con un comando: SQLite en vez de Postgres y dashboard sin compilar
   servido por la misma API (sin Neon, Render, Vercel ni Node).
9. `pr/09-catalogo-industrial`: los datos pasan a un distribuidor de piezas industriales con números de pieza,
   equivalencias y reglas de configuración; incluye dos casos trampa (una pieza y una combinación que no existen).
10. `pr/10-verificacion-exacta`: búsqueda exacta de números de pieza en paralelo con la vectorial y verificación
    determinística del borrador antes de enviarlo; el dashboard muestra de dónde salió cada fuente y qué se verificó.
11. `pr/11-verificador-agente`: un segundo LLM con la herramienta `buscar_en_catalogo` revisa lo que la regex no ve;
    la regex queda como piso, el código valida la evidencia que cita el modelo y decide la ruta. Se quita el aviso
    duplicado de la pieza inexistente.

12. `pr/12-ordenar-por-responsabilidades`: el código pasa a dos paquetes, `agente/` (estado, flujo, nodos, llamadas al
    modelo) y `conocimiento/` (RAG, búsqueda literal, verificación), sin cambiar el comportamiento.
## Siguientes pasos

- Reintento de la búsqueda cuando falla, con una arista de vuelta a `buscar_documentacion`.
- Evals online y automatizaciones en LangSmith sobre tráfico real.
