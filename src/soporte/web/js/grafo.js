// Forma del grafo del agente, para dibujarlo en el panel de tránsito.
// Debe coincidir con src/soporte/graph.py.

export const NOMBRES = {
  recibir_correo: "Recibir correo",
  clasificar: "Clasificar",
  buscar_documentacion: "Búsqueda vectorial",
  busqueda_exacta: "Búsqueda exacta",
  consultar_inventario: "Precio y stock (SQL)",
  consultar_historial: "Consultar historial",
  crear_ticket: "Abrir caso",
  redactar_respuesta: "Redactar respuesta",
  verificar_respuesta: "Verificar contra el catálogo",
  revision_humana: "Revisión humana",
  enviar_respuesta: "Enviar respuesta",
};

const NOMBRES_CORTOS = {
  buscar_documentacion: "Vectorial",
  busqueda_exacta: "Exacta",
  consultar_historial: "Historial",
  crear_ticket: "Caso",
};

/** Cada fila es un superstep; los nodos de una misma fila pueden correr en paralelo. */
export const FILAS = [
  ["recibir_correo"],
  ["clasificar"],
  ["buscar_documentacion", "busqueda_exacta", "consultar_historial", "crear_ticket"],
  ["consultar_inventario"],
  ["redactar_respuesta"],
  ["verificar_respuesta"],
  ["revision_humana"],
  ["enviar_respuesta"],
];

export const nombreDeNodo = (nodo) => NOMBRES[nodo] ?? nodo;
export const nombreCorto = (nodo) => NOMBRES_CORTOS[nodo] ?? nombreDeNodo(nodo);
