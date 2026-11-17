// Contratos que devuelve la API (ver src/soporte/api/eventos.py).

export type Accion = "aprobar" | "editar" | "rechazar";

export interface Correo {
  remitente: string;
  asunto: string;
  cuerpo: string;
}

export interface Esperado {
  intencion: string | string[];
  necesita_revision: boolean;
}

export interface CasoDePrueba {
  id: string;
  entrada: Correo;
  esperado: Esperado;
}

export interface Clasificacion {
  intencion: string;
  urgencia: string;
  tema: string;
  resumen: string;
}

export interface Fragmento {
  fuente: string;
  texto: string;
}

export interface ResumenEstado {
  clasificacion: Clasificacion | null;
  fragmentos: Fragmento[];
  historial_cliente: Record<string, unknown> | null;
  ticket_id: string | null;
  borrador: string | null;
  decision_humana: string | null;
  enviado: boolean;
  pasos: string[];
  pausado_en: string[];
}

export interface SolicitudDeRevision {
  remitente: string;
  correo: string;
  borrador: string;
  urgencia: string;
  intencion: string;
  ticket_id: string | null;
}

interface Base {
  momento: string;
}

export type EventoCorrida =
  | (Base & { tipo: "inicio"; thread_id: string; reanudacion: boolean })
  | (Base & { tipo: "nodo_inicio"; id: string; nodo: string })
  | (Base & { tipo: "nodo_fin"; id: string; nodo: string; actualizacion: Record<string, unknown>; duracion_ms: number; fallo: boolean })
  | (Base & { tipo: "pausa"; nodo: string; solicitud: SolicitudDeRevision })
  | (Base & { tipo: "fin"; thread_id: string; estado: ResumenEstado })
  | (Base & { tipo: "error"; mensaje: string });

export interface Salud {
  estado: "ok";
  persistencia: "postgres" | "memoria";
  modelo: string;
}
