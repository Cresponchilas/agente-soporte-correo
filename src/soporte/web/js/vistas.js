// Funciones que convierten estado en HTML. No guardan estado ni hablan con la red:
// reciben datos y devuelven texto. Todo lo que viene del usuario pasa por esc().

import { estadoAcumulado } from "./corrida.js";
import { evaluar } from "./evaluacion.js";
import { FILAS, nombreCorto, nombreDeNodo } from "./grafo.js";
import { contactosPrevios, esc, formatearMs } from "./texto.js";

export const CLAVE_PROPIO = "propio";

// ---------- Cabecera ----------

const TEXTOS_SALUD = {
  comprobando: "Conectando con el servidor",
  lista: "Servidor listo",
  caida: "El servidor no responde",
};

export function vistaEstadoApi({ estado, info }) {
  const detalle =
    estado === "lista" && info
      ? `<span class="estado-api__detalle">${esc(info.modelo.replace("openai:", ""))}, checkpoints en ${info.persistencia === "sqlite" ? "SQLite" : "memoria"}</span>`
      : "";
  const reintentar = estado === "caida" ? `<button type="button" class="boton boton--chico" data-accion="reintentar-salud">Reintentar</button>` : "";
  return `<div class="estado-api" data-estado="${estado}" role="status"><span class="estado-api__luz" aria-hidden="true"></span><span>${TEXTOS_SALUD[estado]}</span>${detalle}${reintentar}</div>`;
}

// ---------- Bandeja ----------

function marcaDeResultado(caso, corrida) {
  if (!corrida || corrida.fase === "sin_iniciar") return "";
  if (corrida.fase === "corriendo") return `<span class="marca marca--corriendo" aria-label="Procesando"></span>`;
  if (corrida.fase === "error") return `<span class="marca marca--error" title="${esc(corrida.error)}">!</span>`;
  if (!corrida.resumen) return "";
  const { intencion, revision } = evaluar(caso.esperado, corrida.resumen);
  const acierto = intencion.acierto && revision.acierto;
  return `<span class="marca ${acierto ? "marca--ok" : "marca--falla"}" title="${acierto ? "Coincide con lo esperado" : "No coincide"}">${acierto ? "✓" : "✗"}</span>`;
}

function marcador(casos, corridas) {
  const evaluados = casos.flatMap((caso) => (corridas[caso.id]?.resumen ? [evaluar(caso.esperado, corridas[caso.id].resumen)] : []));
  if (evaluados.length === 0) return "";
  const intencion = evaluados.filter((e) => e.intencion.acierto).length;
  const revision = evaluados.filter((e) => e.revision.acierto).length;
  return `<dl class="marcador">
    <div><dt>Intención correcta</dt><dd>${intencion}/${evaluados.length}</dd></div>
    <div><dt>Revisión correcta</dt><dd>${revision}/${evaluados.length}</dd></div>
  </dl>`;
}

export function vistaBandeja({ casos, errorCasos, corridas, seleccionado, probandoTodos, apiLista }) {
  const items = casos
    .map(
      (caso) => `<li><button type="button" class="bandeja__item ${seleccionado === caso.id ? "es-activo" : ""}" data-accion="seleccionar" data-clave="${esc(caso.id)}">
        <span class="bandeja__asunto">${esc(caso.entrada.asunto)}</span>
        <span class="bandeja__remitente">${esc(caso.entrada.remitente)}</span>
        <span class="bandeja__marca">${marcaDeResultado(caso, corridas[caso.id])}</span>
      </button></li>`,
    )
    .join("");

  return `
    <button type="button" class="bandeja__item bandeja__item--propio ${seleccionado === CLAVE_PROPIO ? "es-activo" : ""}" data-accion="seleccionar" data-clave="${CLAVE_PROPIO}">
      <span class="bandeja__asunto">Escribir un correo</span>
      <span class="bandeja__remitente">Prueba el agente con tu propio texto</span>
    </button>
    <div class="bandeja__encabezado">
      <h2>Casos de prueba</h2>
      <button type="button" class="boton boton--chico" data-accion="probar-todos" ${probandoTodos || !apiLista || casos.length === 0 ? "disabled" : ""}>
        ${probandoTodos ? "Probando…" : `Probar los ${casos.length || 8}`}
      </button>
    </div>
    <p class="bandeja__nota">Cada caso trae la intención esperada y si debería pasar por revisión humana.</p>
    ${errorCasos ? `<p class="aviso aviso--error">${esc(errorCasos)}</p>` : ""}
    <ul class="bandeja__lista">${items}</ul>
    ${marcador(casos, corridas)}`;
}

// ---------- Correo (encabezado del centro) ----------

export function erroresDeCorreo(correo) {
  // Las mismas reglas que valida la API (esquemas.py), para avisar antes de enviar.
  const errores = {};
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(correo.remitente.trim())) errores.remitente = "Escribe un correo válido, como compras@planta.co";
  if (correo.cuerpo.trim().length < 5) errores.cuerpo = "Escribe al menos una frase";
  if (correo.cuerpo.length > 4000) errores.cuerpo = "Máximo 4.000 caracteres";
  if (correo.asunto.length > 200) errores.asunto = "Máximo 200 caracteres";
  return errores;
}

function campo(nombre, etiqueta, valor, error, { multilinea = false, placeholder = "" } = {}) {
  const atributos = `id="correo-${nombre}" data-campo="${nombre}" placeholder="${esc(placeholder)}" aria-invalid="${Boolean(error)}"`;
  const control = multilinea
    ? `<textarea rows="6" ${atributos}>${esc(valor)}</textarea>`
    : `<input type="${nombre === "remitente" ? "email" : "text"}" autocomplete="off" value="${esc(valor)}" ${atributos}>`;
  return `<label for="correo-${nombre}">${etiqueta}</label>${control}${error ? `<p class="formulario__error">${esc(error)}</p>` : ""}`;
}

export function vistaCorreo({ caso, correoPropio, mostrarErrores }) {
  if (caso) {
    return `<h2 class="detalle__asunto">${esc(caso.entrada.asunto)}</h2>
      <p class="detalle__remitente">De ${esc(caso.entrada.remitente)}</p>
      <blockquote class="detalle__cuerpo">${esc(caso.entrada.cuerpo)}</blockquote>`;
  }
  const errores = mostrarErrores ? erroresDeCorreo(correoPropio) : {};
  return `<h2 class="detalle__asunto">Escribe un correo de cliente</h2>
    <div class="formulario">
      ${campo("remitente", "De", correoPropio.remitente, errores.remitente, { placeholder: "compras@planta.co" })}
      ${campo("asunto", "Asunto", correoPropio.asunto, errores.asunto, { placeholder: "Ej.: Disponibilidad del SI-M12-04P" })}
      ${campo("cuerpo", "Mensaje", correoPropio.cuerpo, errores.cuerpo, { multilinea: true, placeholder: "Escribe el correo como lo enviaría un cliente" })}
    </div>`;
}

export function vistaAcciones({ corrida, apiLista }) {
  const corriendo = corrida?.fase === "corriendo";
  const etiqueta = corriendo ? "Procesando…" : corrida && corrida.fase !== "sin_iniciar" ? "Procesar de nuevo" : "Procesar correo";
  return `<button type="button" class="boton boton--primario" data-accion="procesar" ${!apiLista || corriendo ? "disabled" : ""}>${etiqueta}</button>
    ${apiLista ? "" : `<span class="detalle__pista">Disponible cuando el servidor esté listo.</span>`}`;
}

// ---------- Resultado ----------

export function vistaResultado({ corrida, caso, destinatario }) {
  if (!corrida || corrida.fase === "sin_iniciar") return "";
  const estado = estadoAcumulado(corrida);
  const { clasificacion, ticket_id, historial_cliente, borrador } = estado;
  const fragmentos = estado.contexto?.length ? estado.contexto : estado.fragmentos;
  const corriendo = corrida.fase === "corriendo";
  const pendiente = `<p class="resultado__pendiente">${corriendo ? "En proceso…" : "Sin datos."}</p>`;
  const mostrarRevision = (corrida.fase === "pausada" || corrida.fase === "error") && corrida.pausa && corrida.threadId;

  return `
    ${corrida.fase === "error" ? `<div class="aviso aviso--error" role="alert"><strong>No se pudo completar.</strong> ${esc(corrida.error)}</div>` : ""}
    ${mostrarRevision ? vistaRevision(corrida.pausa) : ""}
    ${corrida.fase === "terminada" ? vistaDesenlace(Boolean(estado.enviado), estado.decision_humana, destinatario) : ""}
    ${caso && corrida.resumen ? vistaComparacion(caso, corrida.resumen) : ""}
    <section class="resultado__seccion">
      <h3>Clasificación</h3>
      ${
        clasificacion
          ? `<dl class="ficha">
              <div><dt>Intención</dt><dd>${esc(clasificacion.intencion)}</dd></div>
              <div><dt>Urgencia</dt><dd data-urgencia="${esc(clasificacion.urgencia)}">${esc(clasificacion.urgencia)}</dd></div>
              <div class="ficha__ancho"><dt>Resumen</dt><dd>${esc(clasificacion.resumen)}</dd></div>
            </dl>`
          : pendiente
      }
    </section>
    <section class="resultado__seccion">
      <h3>Contexto que reunió</h3>
      ${
        fragmentos || historial_cliente
          ? `<p class="resultado__linea">${ticket_id ? `Caso abierto: ${esc(ticket_id)}.` : "Sin caso abierto."} ${esc(historialEnTexto(historial_cliente))}</p>
             ${vistaBusquedaExacta(estado.busqueda_exacta)}
             ${fragmentos ? vistaFuentes(fragmentos) : ""}`
          : pendiente
      }
    </section>
    <section class="resultado__seccion">
      <h3>Verificación contra el catálogo</h3>
      ${estado.verificacion ? vistaVerificacion(estado.verificacion) : pendiente}
    </section>
    ${
      borrador && corrida.fase !== "pausada"
        ? `<section class="resultado__seccion"><h3>${estado.enviado ? "Respuesta enviada" : "Borrador"}</h3><div class="borrador">${esc(borrador)}</div></section>`
        : ""
    }`;
}

function vistaRevision(solicitud) {
  const ticket = solicitud.ticket_id ? `, ticket ${esc(solicitud.ticket_id)}` : "";
  return `<section class="revision" aria-labelledby="titulo-revision">
    <h3 id="titulo-revision">Necesita tu aprobación</h3>
    <p class="revision__motivo">El agente se detuvo antes de enviar (intención ${esc(solicitud.intencion)}, urgencia ${esc(solicitud.urgencia)}${ticket}) por esto:</p>
    ${solicitud.motivos?.length ? `<ul class="revision__motivos">${solicitud.motivos.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>` : ""}
    <p class="revision__motivo">Puedes ajustar el texto antes de decidir.</p>
    <label for="texto-revision" class="sr-only">Respuesta que se enviará</label>
    <textarea id="texto-revision" rows="9" data-original="${esc(solicitud.borrador)}">${esc(solicitud.borrador)}</textarea>
    <div class="revision__acciones">
      <button type="button" class="boton boton--primario" data-accion="decidir" data-decision="aprobar">Aprobar y enviar</button>
      <button type="button" class="boton boton--primario" data-accion="decidir" data-decision="editar" hidden>Enviar con mis cambios</button>
      <button type="button" class="boton" data-accion="deshacer-edicion" hidden>Deshacer cambios</button>
      <button type="button" class="boton boton--peligro" data-accion="decidir" data-decision="rechazar">Rechazar</button>
    </div>
  </section>`;
}

function vistaDesenlace(enviado, decision, destinatario) {
  if (enviado) {
    const quien = decision === "editado" ? "con tus cambios" : decision === "aprobado" ? "con tu aprobación" : "sin revisión humana";
    return `<p class="aviso aviso--ok">Respuesta enviada a ${esc(destinatario)} ${quien}.</p>`;
  }
  return `<p class="aviso aviso--neutro">Rechazada: no se envió nada y el caso queda para una persona del equipo.</p>`;
}

function vistaComparacion(caso, resumen) {
  const { intencion, revision } = evaluar(caso.esperado, resumen);
  const fila = (nombre, c) =>
    `<tr data-acierto="${c.acierto}"><th scope="row">${nombre}</th><td>${esc(c.esperado)}</td><td>${esc(c.obtenido)}<span class="sr-only">${c.acierto ? " (coincide)" : " (no coincide)"}</span><span aria-hidden="true">${c.acierto ? " ✓" : " ✗"}</span></td></tr>`;
  return `<table class="comparacion">
    <caption>Contra lo esperado en el caso de prueba</caption>
    <thead><tr><th scope="col">Criterio</th><th scope="col">Esperado</th><th scope="col">Obtenido</th></tr></thead>
    <tbody>${fila("Intención", intencion)}${fila("Pasa por revisión", revision)}</tbody>
  </table>`;
}

const ORIGENES = { exacta: "búsqueda exacta", vectorial: "búsqueda vectorial", ambas: "ambas búsquedas" };

const ESTADOS_AFIRMACION = {
  respaldado: { marca: "✓", texto: "en lo que vio el modelo" },
  fuera_de_contexto: { marca: "≈", texto: "existe en el catálogo, pero el modelo no lo vio" },
  no_encontrado: { marca: "✗", texto: "no aparece en el catálogo" },
};

function vistaBusquedaExacta(busqueda) {
  if (!busqueda || busqueda.codigos.length === 0) return "";
  const partes = busqueda.codigos.map((codigo) =>
    busqueda.inexistentes.includes(codigo) ? `<strong class="texto-alerta">${esc(codigo)} no existe</strong>` : `${esc(codigo)} encontrado`,
  );
  return `<p class="resultado__linea">Búsqueda exacta de los códigos del correo: ${partes.join(", ")}.</p>`;
}

const VEREDICTOS = {
  respaldada: { marca: "✓", texto: "respaldada" },
  contradicha: { marca: "✗", texto: "contradice el catálogo" },
  sin_respaldo: { marca: "?", texto: "sin respaldo" },
};

const secciones = (n) => (n === 1 ? "1 sección" : `${n} secciones`);

function vistaVerificacion(verificacion) {
  const veredicto = verificacion.aprobada
    ? `<p class="aviso aviso--ok">Ni el piso literal ni el verificador encontraron algo sin respaldo.</p>`
    : `<div class="aviso aviso--error"><strong>No se envía sin revisión.</strong><ul>${verificacion.motivos.map((m) => `<li>${esc(m)}</li>`).join("")}</ul></div>`;
  return veredicto + vistaPiso(verificacion.afirmaciones) + vistaAgente(verificacion);
}

function vistaPiso(afirmaciones) {
  const filas = afirmaciones
    .map((a) => {
      const estado = ESTADOS_AFIRMACION[a.estado];
      return `<tr data-estado="${a.estado}"><td><span aria-hidden="true">${estado.marca}</span> ${esc(a.texto)}</td><td>${estado.texto}</td><td>${a.fuente ? esc(a.fuente.replace("#", ", ")) : "—"}</td></tr>`;
    })
    .join("");
  const contenido = afirmaciones.length
    ? `<table class="verificacion"><thead><tr><th scope="col">Lo que dice el borrador</th><th scope="col">Resultado</th><th scope="col">Dónde está</th></tr></thead><tbody>${filas}</tbody></table>`
    : `<p class="resultado__pendiente">El borrador no menciona números de pieza ni datos con unidades.</p>`;
  return `<h4 class="verificacion__capa">Piso literal, sin LLM: cada código y dato con unidad, buscado tal cual</h4>${contenido}`;
}

function vistaAgente({ revisadas = [], busquedas = [], error = null }) {
  const titulo = `<h4 class="verificacion__capa">Verificador agente: un LLM que elige qué comprobar y busca en el catálogo</h4>`;
  if (error) return `${titulo}<p class="resultado__pendiente">El verificador no pudo terminar, así que la respuesta pasa por revisión.</p>`;
  const buscado = busquedas.length
    ? `<p class="resultado__linea">Buscó ${busquedas.map((b) => `<q>${esc(b.termino)}</q> (${b.fuentes.length ? secciones(b.fuentes.length) : "nada"})`).join(", ")}.</p>`
    : `<p class="resultado__linea">No hizo búsquedas.</p>`;
  if (revisadas.length === 0) return `${titulo}${buscado}<p class="resultado__pendiente">No encontró afirmaciones que comprobar.</p>`;
  const filas = revisadas
    .map((a) => {
      const v = VEREDICTOS[a.veredicto] ?? { marca: "", texto: a.veredicto };
      const donde = a.fuente ? `${esc(a.fuente.replace("#", ", "))}. ` : "";
      return `<tr data-veredicto="${esc(a.veredicto)}"><td><span aria-hidden="true">${v.marca}</span> ${esc(a.afirmacion)}</td><td>${v.texto}</td><td>${donde}${esc(a.explicacion)}</td></tr>`;
    })
    .join("");
  return `${titulo}${buscado}<table class="verificacion"><thead><tr><th scope="col">Afirmación</th><th scope="col">Veredicto</th><th scope="col">Fuente y razón</th></tr></thead><tbody>${filas}</tbody></table>`;
}

function vistaFuentes(fragmentos) {
  const items = fragmentos
    .map(
      (f) => `<li><details><summary>${f.fuente === "error" ? "La búsqueda falló" : esc(f.fuente.replace("#", ", sección "))}${f.origen ? ` <span class="origen" data-origen="${esc(f.origen)}">${ORIGENES[f.origen] ?? esc(f.origen)}</span>` : ""}</summary><p>${esc(f.texto)}</p></details></li>`,
    )
    .join("");
  return `<ul class="fuentes">${items}</ul>`;
}

function historialEnTexto(historial) {
  if (!historial) return "";
  const nombre = typeof historial.nombre === "string" ? historial.nombre : "Cliente nuevo";
  return `${nombre}, ${contactosPrevios(Number(historial.contactos_previos ?? 0))}.`;
}

// ---------- Panel de tránsito ----------

export function vistaTransito(corrida) {
  const hilo = corrida?.threadId ? `<span class="transito__hilo" title="${esc(corrida.threadId)}">Hilo ${esc(corrida.threadId.slice(0, 8))}</span>` : "";
  const bitacora =
    !corrida || corrida.bitacora.length === 0
      ? `<p class="transito__vacio">${
          corrida?.resumen
            ? "Esta corrida se recuperó del servidor: el resultado está guardado, pero la bitácora en vivo solo existe mientras corre."
            : "Procesa un correo para ver aquí cada nodo del grafo: cuándo empieza, qué escribe en el estado y cuánto tarda."
        }</p>`
      : vistaBitacora(corrida.bitacora);

  return `<div class="transito__franja" aria-hidden="true"></div>
    <header class="transito__encabezado"><h2>Tránsito</h2>${hilo}</header>
    ${vistaMapa(corrida)}
    <h3 class="transito__subtitulo">Bitácora de eventos</h3>
    ${bitacora}`;
}

function vistaMapa(corrida) {
  const termino = ["terminada", "pausada", "error"].includes(corrida?.fase);
  const estadoDe = (nodo) => corrida?.nodos[nodo]?.estado ?? (termino ? "omitido" : "pendiente");

  const filas = FILAS.map((fila) => {
    const nodos = fila
      .map((nodo) => {
        const estado = estadoDe(nodo);
        return `<span class="mapa__nodo" data-estado="${estado}" title="${esc(nombreDeNodo(nodo))}">
          <span class="mapa__nombre">${esc(nombreCorto(nodo))}</span>
          <span class="mapa__estado">${textoDeEstado(estado, corrida?.nodos[nodo]?.duracionMs)}</span>
        </span>`;
      })
      .join("");
    return `<li class="mapa__fila">${nodos}</li>`;
  }).join("");
  return `<ol class="mapa" aria-label="Nodos del grafo">${filas}</ol>`;
}

function textoDeEstado(estado, duracionMs) {
  const textos = { corriendo: "corriendo", en_pausa: "esperando", fallo: "falló", omitido: "no aplicó", pendiente: "" };
  if (estado === "hecho") return duracionMs !== undefined ? formatearMs(duracionMs) : "listo";
  return textos[estado] ?? "";
}

function vistaBitacora(eventos) {
  const origen = Date.parse(eventos[0].momento);
  const items = eventos
    .map((evento) => {
      const { titulo, detalle, datos } = describir(evento);
      return `<li class="bitacora__evento" data-tipo="${evento.tipo}">
        <span class="bitacora__tiempo">+${formatearMs(Date.parse(evento.momento) - origen)}</span>
        <div class="bitacora__cuerpo">
          <span class="bitacora__titulo">${esc(titulo)}</span>
          ${detalle ? `<span class="bitacora__detalle">${esc(detalle)}</span>` : ""}
          ${datos !== undefined ? `<details class="bitacora__datos"><summary>Ver datos</summary><pre>${esc(JSON.stringify(datos, null, 2))}</pre></details>` : ""}
        </div>
      </li>`;
    })
    .join("");
  return `<ol class="bitacora">${items}</ol>`;
}

function describir(evento) {
  switch (evento.tipo) {
    case "inicio":
      return { titulo: evento.reanudacion ? "Reanudada con tu decisión" : "Corrida iniciada" };
    case "nodo_inicio":
      return { titulo: `${nombreDeNodo(evento.nodo)} empezó` };
    case "nodo_fin":
      return {
        titulo: `${nombreDeNodo(evento.nodo)} ${evento.fallo ? "falló" : "terminó"} en ${formatearMs(evento.duracion_ms)}`,
        detalle: resumirActualizacion(evento.nodo, evento.actualizacion),
        datos: evento.actualizacion,
      };
    case "pausa":
      return { titulo: "Pausa: espera revisión humana", detalle: "El grafo guardó su estado y quedó detenido.", datos: evento.solicitud };
    case "fin":
      return { titulo: evento.estado.pausado_en.length ? "Detenido hasta tu decisión" : "Corrida terminada", datos: evento.estado };
    case "error":
      return { titulo: "Error", detalle: evento.mensaje };
    default:
      return { titulo: evento.tipo };
  }
}

function resumirActualizacion(nodo, a) {
  switch (nodo) {
    case "clasificar":
      return a.clasificacion ? `${a.clasificacion.intencion}, urgencia ${a.clasificacion.urgencia}` : undefined;
    case "buscar_documentacion": {
      const fragmentos = a.fragmentos ?? [];
      return `${fragmentos.length} fragmentos: ${fragmentos.map((f) => f.fuente.split("#")[1] ?? f.fuente).join(", ")}`;
    }
    case "consultar_historial":
      return contactosPrevios(a.historial_cliente?.contactos_previos ?? 0);
    case "crear_ticket":
      return `Caso ${a.ticket_id}`;
    case "busqueda_exacta": {
      const b = a.busqueda_exacta;
      if (!b || b.codigos.length === 0) return "El correo no menciona números de pieza";
      const encontrados = Object.keys(b.encontrados);
      return [
        encontrados.length ? `Encontrados: ${encontrados.join(", ")}` : "",
        b.inexistentes.length ? `No existen: ${b.inexistentes.join(", ")}` : "",
      ].filter(Boolean).join(". ");
    }
    case "verificar_respuesta": {
      const v = a.verificacion;
      if (!v) return undefined;
      const literal = `${v.afirmaciones.length} datos literales`;
      const n = (v.revisadas ?? []).length;
      const k = (v.busquedas ?? []).length;
      const agente = v.error ? "el verificador falló" : `${n} ${n === 1 ? "afirmación" : "afirmaciones"} con ${k} ${k === 1 ? "búsqueda" : "búsquedas"}`;
      return `${literal}, ${agente}. ${v.aprobada ? "Todo con respaldo" : "Va a revisión"}`;
    }
    case "redactar_respuesta":
      return typeof a.borrador === "string" ? `Borrador de ${a.borrador.split(/\s+/).length} palabras` : undefined;
    case "revision_humana":
      return a.decision_humana ? `Decisión: ${a.decision_humana}` : undefined;
    default:
      return undefined;
  }
}
