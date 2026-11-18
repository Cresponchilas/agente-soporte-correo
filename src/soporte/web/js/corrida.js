// Estado de una corrida, construido evento a evento (reducer puro: mismo estado y
// mismo evento dan siempre el mismo resultado, así que se prueba sin navegador).

export const corridaNueva = Object.freeze({ fase: "sin_iniciar", nodos: {}, bitacora: [] });

export function aplicarEvento(corrida, evento) {
  const conBitacora = { ...corrida, bitacora: [...corrida.bitacora, evento] };

  switch (evento.tipo) {
    case "inicio":
      return { ...conBitacora, fase: "corriendo", threadId: evento.thread_id, pausa: undefined, error: undefined };
    case "nodo_inicio":
      return { ...conBitacora, nodos: { ...corrida.nodos, [evento.nodo]: { estado: "corriendo" } } };
    case "nodo_fin":
      return {
        ...conBitacora,
        nodos: { ...corrida.nodos, [evento.nodo]: { estado: evento.fallo ? "fallo" : "hecho", duracionMs: evento.duracion_ms } },
      };
    case "pausa":
      return { ...conBitacora, pausa: evento.solicitud, nodos: { ...corrida.nodos, [evento.nodo]: { estado: "en_pausa" } } };
    case "fin":
      return { ...conBitacora, resumen: evento.estado, fase: evento.estado.pausado_en.length > 0 ? "pausada" : "terminada" };
    case "error":
      return marcarError(conBitacora, evento.mensaje);
    default:
      return corrida; // un tipo de evento desconocido no rompe la pantalla
  }
}

/** Errores que no llegan como evento (servidor caído, 422, 404...). */
export function marcarError(corrida, mensaje) {
  const nodos = Object.fromEntries(
    Object.entries(corrida.nodos).map(([nodo, info]) => [nodo, info.estado === "corriendo" ? { estado: "fallo" } : info]),
  );
  return { ...corrida, fase: "error", error: mensaje, nodos };
}

/** Lo que se sabe del estado: durante la corrida, lo escrito por cada nodo; al final, el resumen. */
export function estadoAcumulado(corrida) {
  const parcial = {};
  for (const evento of corrida.bitacora) {
    if (evento.tipo === "nodo_fin") Object.assign(parcial, evento.actualizacion);
  }
  return { ...parcial, ...corrida.resumen };
}

/**
 * Reconstruye una corrida a partir del estado guardado en el servidor (por ejemplo,
 * tras recargar la página). No hay bitácora, pero sí resultado y, si está pausada,
 * lo necesario para decidir.
 */
export function corridaDesdeResumen(threadId, resumen, remitente) {
  const pausada = resumen.pausado_en.includes("revision_humana");
  const nodos = Object.fromEntries(resumen.pasos.map((paso) => [paso, { estado: "hecho" }]));
  if (pausada) nodos.revision_humana = { estado: "en_pausa" };
  return {
    fase: pausada ? "pausada" : "terminada",
    threadId,
    nodos,
    bitacora: [],
    resumen,
    pausa: pausada
      ? {
          remitente,
          borrador: resumen.borrador ?? "",
          urgencia: resumen.clasificacion?.urgencia ?? "",
          intencion: resumen.clasificacion?.intencion ?? "",
          ticket_id: resumen.ticket_id,
          motivos: resumen.motivos_revision ?? [],
        }
      : undefined,
  };
}
