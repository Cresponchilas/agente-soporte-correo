// Cliente HTTP de la API. Todo error se convierte en ErrorDeApi con un mensaje
// que se puede mostrar tal cual al usuario.

import { crearLectorSSE } from "./sse.js";

export class ErrorDeApi extends Error {
  constructor(mensaje, estado = undefined, detalles = []) {
    super(mensaje);
    this.name = "ErrorDeApi";
    this.estado = estado;
    this.detalles = detalles;
  }
}

const SIN_CONEXION = "No se pudo conectar con el servidor. ¿Sigue corriendo `python -m soporte.api`?";

async function errorDesdeRespuesta(respuesta) {
  let cuerpo = {};
  try {
    cuerpo = await respuesta.json();
  } catch {
    // la respuesta no era JSON; se usa el mensaje genérico de abajo
  }
  return new ErrorDeApi(cuerpo.error ?? `El servidor respondió con el código ${respuesta.status}.`, respuesta.status, cuerpo.detalles ?? []);
}

export async function pedirJSON(ruta, timeoutMs = 10_000) {
  let respuesta;
  try {
    respuesta = await fetch(`/api${ruta}`, { signal: AbortSignal.timeout(timeoutMs) });
  } catch {
    throw new ErrorDeApi(SIN_CONEXION);
  }
  if (!respuesta.ok) throw await errorDesdeRespuesta(respuesta);
  return respuesta.json();
}

/**
 * Envía un POST y entrega cada evento de la respuesta en streaming.
 * Si la transmisión se corta sin un evento final ("fin" o "error"), lo informa como error.
 */
export async function transmitir(ruta, cuerpo, alRecibir, senal) {
  let respuesta;
  try {
    respuesta = await fetch(`/api${ruta}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo),
      signal: senal,
    });
  } catch (error) {
    if (senal?.aborted) throw error;
    throw new ErrorDeApi(SIN_CONEXION);
  }
  if (!respuesta.ok) throw await errorDesdeRespuesta(respuesta);

  const lector = crearLectorSSE();
  const decodificador = new TextDecoder();
  const flujo = respuesta.body.getReader();
  let terminoBien = false;

  try {
    for (;;) {
      const { done, value } = await flujo.read();
      if (done) break;
      for (const evento of lector.leer(decodificador.decode(value, { stream: true }))) {
        if (evento.tipo === "fin" || evento.tipo === "error") terminoBien = true;
        alRecibir(evento);
      }
    }
  } catch (error) {
    if (senal?.aborted) throw error;
    throw new ErrorDeApi("Se perdió la conexión con el servidor mientras procesaba el correo.");
  }
  if (!terminoBien) throw new ErrorDeApi("La transmisión terminó antes de tiempo. Intenta de nuevo.");
}

export function mensajeDeError(error) {
  if (error instanceof ErrorDeApi) {
    const campos = error.detalles.map((d) => `${d.campo}: ${d.mensaje}`).join("; ");
    return campos ? `${error.message} (${campos})` : error.message;
  }
  return "Algo salió mal en el navegador. Recarga la página e intenta de nuevo.";
}
