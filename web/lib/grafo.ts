// Forma del grafo del agente, para dibujarlo en el panel de tránsito.
// Debe coincidir con src/soporte/graph.py.

export const NOMBRES: Record<string, string> = {
  recibir_correo: "Recibir correo",
  clasificar: "Clasificar",
  buscar_documentacion: "Buscar documentación",
  consultar_historial: "Consultar historial",
  crear_ticket: "Crear ticket",
  redactar_respuesta: "Redactar respuesta",
  revision_humana: "Revisión humana",
  enviar_respuesta: "Enviar respuesta",
};

/** Nombres cortos para el mapa, donde tres nodos comparten una fila. */
export const NOMBRES_CORTOS: Record<string, string> = {
  buscar_documentacion: "Documentos",
  consultar_historial: "Historial",
  crear_ticket: "Ticket",
};

/** Cada fila es un superstep; los nodos de una misma fila pueden correr en paralelo. */
export const FILAS: string[][] = [
  ["recibir_correo"],
  ["clasificar"],
  ["buscar_documentacion", "consultar_historial", "crear_ticket"],
  ["redactar_respuesta"],
  ["revision_humana"],
  ["enviar_respuesta"],
];

export function nombreDeNodo(nodo: string): string {
  return NOMBRES[nodo] ?? nodo;
}

export function nombreCorto(nodo: string): string {
  return NOMBRES_CORTOS[nodo] ?? nombreDeNodo(nodo);
}
