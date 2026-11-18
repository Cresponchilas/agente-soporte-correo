// Punto de entrada del dashboard: guarda el estado, conecta los eventos de la
// página con la API y decide qué región repintar. Las vistas están en vistas.js.

import { ErrorDeApi, mensajeDeError, pedirJSON, transmitir } from "./api.js";
import { aplicarEvento, corridaDesdeResumen, corridaNueva, marcarError } from "./corrida.js";
import { CLAVE_PROPIO, erroresDeCorreo, vistaAcciones, vistaBandeja, vistaCorreo, vistaEstadoApi, vistaResultado, vistaTransito } from "./vistas.js";

const CLAVE_ALMACEN = "agente-soporte:corridas-v1";

const estado = {
  salud: { estado: "comprobando", info: null },
  casos: [],
  errorCasos: null,
  corridas: {}, // clave (caso-0…caso-7 o "propio") -> corrida
  seleccionado: CLAVE_PROPIO,
  correoPropio: { remitente: "", asunto: "", cuerpo: "" },
  mostrarErrores: false,
  probandoTodos: false,
};

const controladores = new Map(); // clave -> AbortController del stream en curso
const $ = (selector) => document.querySelector(selector);

// ---------- Pintar ----------
// Cada región se repinta por separado: así escribir en el formulario o en la
// revisión no se borra cuando llega un evento de otra corrida.

const apiLista = () => estado.salud.estado === "lista";
const casoSeleccionado = () => estado.casos.find((c) => c.id === estado.seleccionado);
const corridaSeleccionada = () => estado.corridas[estado.seleccionado];
let firmaDelResultado = "";

function pintarCabecera() {
  $("#estado-api").innerHTML = vistaEstadoApi(estado.salud);
  $("#aviso-caida").hidden = estado.salud.estado !== "caida";
}

function pintarBandeja() {
  $("#bandeja").innerHTML = vistaBandeja({ ...estado, apiLista: apiLista() });
}

function pintarCorreo() {
  $("#detalle-correo").innerHTML = vistaCorreo({ caso: casoSeleccionado(), correoPropio: estado.correoPropio, mostrarErrores: estado.mostrarErrores });
  pintarAcciones();
}

function pintarAcciones() {
  $("#detalle-acciones").innerHTML = vistaAcciones({ corrida: corridaSeleccionada(), apiLista: apiLista() });
}

function pintarResultado() {
  const corrida = corridaSeleccionada();
  // Solo se repinta si la corrida cambió: no se pierde lo que escribes en la revisión.
  const firma = `${estado.seleccionado}|${corrida?.threadId}|${corrida?.fase}|${corrida?.bitacora.length}|${Boolean(corrida?.resumen)}`;
  if (firma === firmaDelResultado) return;
  firmaDelResultado = firma;
  const caso = casoSeleccionado();
  const destinatario = caso?.entrada.remitente ?? estado.correoPropio.remitente;
  $("#detalle-resultado").innerHTML = vistaResultado({ corrida, caso, destinatario });
}

function pintarTransito() {
  const panel = $("#transito");
  panel.dataset.activo = String(corridaSeleccionada()?.fase === "corriendo");
  panel.innerHTML = vistaTransito(corridaSeleccionada());
}

function pintarTodo() {
  pintarCabecera();
  pintarBandeja();
  pintarCorreo();
  pintarResultado();
  pintarTransito();
}

/** Tras cada cambio en una corrida: lo de esa corrida solo se repinta si es la que estás viendo. */
function alCambiarCorrida(clave) {
  pintarBandeja();
  if (clave !== estado.seleccionado) return;
  pintarAcciones();
  pintarResultado();
  pintarTransito();
}

// ---------- Corridas ----------

async function ejecutar(clave, ruta, cuerpo) {
  controladores.get(clave)?.abort();
  const controlador = new AbortController();
  controladores.set(clave, controlador);
  try {
    await transmitir(
      ruta,
      cuerpo,
      (evento) => {
        estado.corridas[clave] = aplicarEvento(estado.corridas[clave] ?? corridaNueva, evento);
        if (evento.tipo === "inicio") recordarCorrida(clave, evento.thread_id);
        alCambiarCorrida(clave);
      },
      controlador.signal,
    );
    return undefined;
  } catch (error) {
    if (controlador.signal.aborted) return error;
    estado.corridas[clave] = marcarError(estado.corridas[clave] ?? corridaNueva, mensajeDeError(error));
    alCambiarCorrida(clave);
    return error;
  } finally {
    if (controladores.get(clave) === controlador) controladores.delete(clave);
  }
}

function procesar(clave, correo) {
  estado.corridas[clave] = { ...corridaNueva, fase: "corriendo" };
  alCambiarCorrida(clave);
  return ejecutar(clave, "/corridas", correo);
}

function decidir(clave, accion, texto) {
  const corrida = estado.corridas[clave];
  if (!corrida?.threadId) return;
  return ejecutar(clave, `/corridas/${corrida.threadId}/decision`, accion === "editar" ? { accion, texto } : { accion });
}

async function probarTodos() {
  estado.probandoTodos = true;
  pintarBandeja();
  try {
    for (const caso of estado.casos) {
      const error = await procesar(caso.id, caso.entrada);
      // Sin servidor, los siguientes también fallarían: mejor detenerse.
      if (error instanceof ErrorDeApi && error.estado === undefined) break;
    }
  } finally {
    estado.probandoTodos = false;
    pintarBandeja();
  }
}

// ---------- Recordar corridas al recargar ----------
// Los checkpoints viven en SQLite: si recargas la página (o reinicias el
// servidor), una corrida pausada se puede seguir decidiendo.

function leerAlmacen() {
  try {
    return JSON.parse(localStorage.getItem(CLAVE_ALMACEN) ?? "{}");
  } catch {
    return {};
  }
}

function escribirAlmacen(datos) {
  try {
    localStorage.setItem(CLAVE_ALMACEN, JSON.stringify(datos));
  } catch {
    // sin almacenamiento (modo privado): la página funciona igual, solo no recuerda
  }
}

function recordarCorrida(clave, threadId) {
  const datos = leerAlmacen();
  datos[clave] = { threadId, ...(clave === CLAVE_PROPIO ? { correo: estado.correoPropio } : {}) };
  escribirAlmacen(datos);
}

async function recuperarCorridas() {
  const datos = leerAlmacen();
  for (const [clave, guardado] of Object.entries(datos)) {
    try {
      const { estado: resumen } = await pedirJSON(`/corridas/${guardado.threadId}`);
      if (clave === CLAVE_PROPIO && guardado.correo) estado.correoPropio = guardado.correo;
      const remitente = estado.casos.find((c) => c.id === clave)?.entrada.remitente ?? estado.correoPropio.remitente;
      estado.corridas[clave] = corridaDesdeResumen(guardado.threadId, resumen, remitente);
    } catch {
      delete datos[clave]; // el servidor ya no la tiene (por ejemplo, checkpoints en memoria)
    }
  }
  escribirAlmacen(datos);
}

// ---------- Arranque ----------

async function comprobarSalud(intentos = 5) {
  estado.salud = { estado: "comprobando", info: null };
  pintarCabecera();
  for (let i = 0; i < intentos; i++) {
    try {
      estado.salud = { estado: "lista", info: await pedirJSON("/salud", 5_000) };
      pintarTodo();
      return true;
    } catch {
      await new Promise((r) => setTimeout(r, 2_000));
    }
  }
  estado.salud = { estado: "caida", info: null };
  pintarTodo();
  return false;
}

async function cargarCasos() {
  try {
    estado.casos = await pedirJSON("/casos");
    estado.errorCasos = null;
  } catch (error) {
    estado.errorCasos = mensajeDeError(error);
  }
}

async function arrancar() {
  pintarTodo();
  if (!(await comprobarSalud())) return;
  await cargarCasos();
  await recuperarCorridas();
  firmaDelResultado = "";
  pintarTodo();
}

// ---------- Eventos de la página (delegados) ----------

document.addEventListener("click", (e) => {
  const boton = e.target.closest("[data-accion]");
  if (!boton || boton.disabled) return;

  switch (boton.dataset.accion) {
    case "seleccionar":
      estado.seleccionado = boton.dataset.clave;
      estado.mostrarErrores = false;
      firmaDelResultado = "";
      pintarTodo();
      break;
    case "probar-todos":
      probarTodos();
      break;
    case "procesar": {
      const caso = casoSeleccionado();
      if (!caso) {
        estado.mostrarErrores = true;
        if (Object.keys(erroresDeCorreo(estado.correoPropio)).length > 0) {
          pintarCorreo();
          return;
        }
      }
      procesar(estado.seleccionado, caso?.entrada ?? estado.correoPropio);
      break;
    }
    case "decidir": {
      document.querySelectorAll(".revision button").forEach((b) => (b.disabled = true)); // evita el doble clic
      decidir(estado.seleccionado, boton.dataset.decision, $("#texto-revision")?.value);
      break;
    }
    case "deshacer-edicion": {
      const area = $("#texto-revision");
      area.value = area.dataset.original;
      area.dispatchEvent(new Event("input", { bubbles: true }));
      break;
    }
    case "reintentar-salud":
      arrancar();
      break;
  }
});

document.addEventListener("input", (e) => {
  const campo = e.target.dataset?.campo;
  if (campo) {
    estado.correoPropio = { ...estado.correoPropio, [campo]: e.target.value };
    return;
  }
  if (e.target.id === "texto-revision") {
    // Si cambiaste el texto, el botón principal pasa a "Enviar con mis cambios".
    const editado = e.target.value.trim() !== e.target.dataset.original.trim();
    $('[data-decision="aprobar"]').hidden = editado;
    $('[data-decision="editar"]').hidden = !editado;
    $('[data-decision="editar"]').disabled = !e.target.value.trim();
    $('[data-accion="deshacer-edicion"]').hidden = !editado;
  }
});

window.addEventListener("beforeunload", () => controladores.forEach((c) => c.abort()));
window.addEventListener("error", () => {
  $("#aviso-error").hidden = false; // un fallo inesperado del navegador se informa, no deja la página muda
});

arrancar();
