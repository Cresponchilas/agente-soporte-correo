// Estado de una corrida en el dashboard, construido evento a evento (reducer puro).

import type { EventoCorrida, ResumenEstado, SolicitudDeRevision } from "./tipos";

export type Fase = "sin_iniciar" | "corriendo" | "pausada" | "terminada" | "error";
export type EstadoNodo = "corriendo" | "hecho" | "fallo" | "en_pausa";

export interface Corrida {
  fase: Fase;
  threadId?: string;
  nodos: Record<string, { estado: EstadoNodo; duracionMs?: number }>;
  bitacora: EventoCorrida[];
  resumen?: ResumenEstado;
  pausa?: SolicitudDeRevision;
  error?: string;
}

export const corridaNueva: Corrida = { fase: "sin_iniciar", nodos: {}, bitacora: [] };

export function aplicarEvento(corrida: Corrida, evento: EventoCorrida): Corrida {
  const conBitacora = { ...corrida, bitacora: [...corrida.bitacora, evento] };

  switch (evento.tipo) {
    case "inicio":
      return { ...conBitacora, fase: "corriendo", threadId: evento.thread_id, pausa: undefined, error: undefined };
    case "nodo_inicio":
      return { ...conBitacora, nodos: { ...corrida.nodos, [evento.nodo]: { estado: "corriendo" } } };
    case "nodo_fin":
      return {
        ...conBitacora,
        nodos: {
          ...corrida.nodos,
          [evento.nodo]: { estado: evento.fallo ? "fallo" : "hecho", duracionMs: evento.duracion_ms },
        },
      };
    case "pausa":
      return {
        ...conBitacora,
        pausa: evento.solicitud,
        nodos: { ...corrida.nodos, [evento.nodo]: { estado: "en_pausa" } },
      };
    case "fin":
      return {
        ...conBitacora,
        resumen: evento.estado,
        fase: evento.estado.pausado_en.length > 0 ? "pausada" : "terminada",
      };
    case "error":
      return marcarError(conBitacora, evento.mensaje);
  }
}

/** Errores que no llegan como evento (red caída, 429, 422...). */
export function marcarError(corrida: Corrida, mensaje: string): Corrida {
  const nodos = Object.fromEntries(
    Object.entries(corrida.nodos).map(([nodo, info]) => [nodo, info.estado === "corriendo" ? { estado: "fallo" as const } : info]),
  );
  return { ...corrida, fase: "error", error: mensaje, nodos };
}

/**
 * Lo que se sabe del estado hasta ahora. Durante la corrida se arma con lo que
 * escribió cada nodo; al terminar, se usa el resumen que manda la API.
 */
export function estadoAcumulado(corrida: Corrida): Partial<ResumenEstado> {
  const parcial: Record<string, unknown> = {};
  for (const evento of corrida.bitacora) {
    if (evento.tipo === "nodo_fin") Object.assign(parcial, evento.actualizacion);
  }
  return { ...(parcial as Partial<ResumenEstado>), ...corrida.resumen };
}
