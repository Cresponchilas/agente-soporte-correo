// Cliente HTTP de la API. Todo error se convierte en ErrorDeApi con un mensaje
// que se puede mostrar tal cual al usuario.

import { crearLectorSSE } from "./sse";
import type { EventoCorrida } from "./tipos";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export interface DetalleDeCampo {
  campo: string;
  mensaje: string;
}

export class ErrorDeApi extends Error {
  constructor(
    mensaje: string,
    readonly estado?: number,
    readonly detalles: DetalleDeCampo[] = [],
  ) {
    super(mensaje);
    this.name = "ErrorDeApi";
  }
}

const SIN_CONEXION = "No se pudo conectar con la API. Puede estar arrancando; intenta de nuevo en unos segundos.";

async function errorDesdeRespuesta(respuesta: Response): Promise<ErrorDeApi> {
  let cuerpo: { error?: string; detalles?: DetalleDeCampo[] } = {};
  try {
    cuerpo = await respuesta.json();
  } catch {
    // la respuesta no era JSON; se usa el mensaje genérico de abajo
  }
  const mensaje = cuerpo.error ?? `La API respondió con el código ${respuesta.status}.`;
  return new ErrorDeApi(mensaje, respuesta.status, cuerpo.detalles ?? []);
}

export async function pedirJSON<T>(ruta: string, timeoutMs = 10_000): Promise<T> {
  let respuesta: Response;
  try {
    respuesta = await fetch(`${API_URL}${ruta}`, { signal: AbortSignal.timeout(timeoutMs) });
  } catch {
    throw new ErrorDeApi(SIN_CONEXION);
  }
  if (!respuesta.ok) throw await errorDesdeRespuesta(respuesta);
  return respuesta.json() as Promise<T>;
}

/**
 * Envía un POST y entrega cada evento de la respuesta en streaming.
 * Termina cuando el servidor cierra la transmisión; si se corta sin un evento
 * final ("fin" o "error"), lo informa como error de conexión.
 */
export async function transmitir(
  ruta: string,
  cuerpo: unknown,
  alRecibir: (evento: EventoCorrida) => void,
  senal?: AbortSignal,
): Promise<void> {
  let respuesta: Response;
  try {
    respuesta = await fetch(`${API_URL}${ruta}`, {
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
  if (!respuesta.body) throw new ErrorDeApi("La API no devolvió datos.");

  const lector = crearLectorSSE();
  const decodificador = new TextDecoder();
  const flujo = respuesta.body.getReader();
  let terminoBien = false;

  try {
    for (;;) {
      const { done, value } = await flujo.read();
      if (done) break;
      for (const evento of lector.leer(decodificador.decode(value, { stream: true })) as EventoCorrida[]) {
        if (evento.tipo === "fin" || evento.tipo === "error") terminoBien = true;
        alRecibir(evento);
      }
    }
  } catch (error) {
    if (senal?.aborted) throw error;
    throw new ErrorDeApi("Se perdió la conexión con la API mientras procesaba el correo.");
  }
  if (!terminoBien) throw new ErrorDeApi("La transmisión terminó antes de tiempo. Intenta de nuevo.");
}
