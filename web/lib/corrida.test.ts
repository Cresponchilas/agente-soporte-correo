import { describe, expect, it } from "vitest";
import { aplicarEvento, corridaNueva, marcarError } from "./corrida";
import type { EventoCorrida, ResumenEstado } from "./tipos";

const momento = "2026-11-17T00:00:00.000Z";
const resumen = (pausado_en: string[]): ResumenEstado => ({
  clasificacion: null,
  fragmentos: [],
  historial_cliente: null,
  ticket_id: null,
  borrador: "hola",
  decision_humana: null,
  enviado: false,
  pasos: [],
  pausado_en,
});

const aplicar = (eventos: EventoCorrida[]) => eventos.reduce(aplicarEvento, corridaNueva);

describe("aplicarEvento", () => {
  it("sigue el ciclo de un nodo y termina pausada si el grafo espera revisión", () => {
    const corrida = aplicar([
      { tipo: "inicio", thread_id: "t1", reanudacion: false, momento },
      { tipo: "nodo_inicio", id: "a", nodo: "clasificar", momento },
      { tipo: "nodo_fin", id: "a", nodo: "clasificar", actualizacion: {}, duracion_ms: 40, fallo: false, momento },
      {
        tipo: "pausa",
        nodo: "revision_humana",
        momento,
        solicitud: { remitente: "x", correo: "y", borrador: "b", urgencia: "alta", intencion: "bug", ticket_id: null },
      },
      { tipo: "fin", thread_id: "t1", estado: resumen(["revision_humana"]), momento },
    ]);

    expect(corrida.fase).toBe("pausada");
    expect(corrida.threadId).toBe("t1");
    expect(corrida.nodos.clasificar).toEqual({ estado: "hecho", duracionMs: 40 });
    expect(corrida.nodos.revision_humana.estado).toBe("en_pausa");
    expect(corrida.bitacora).toHaveLength(5);
  });

  it("al reanudar limpia la pausa y conserva la bitácora", () => {
    const pausada = aplicar([{ tipo: "fin", thread_id: "t1", estado: resumen(["revision_humana"]), momento }]);
    const reanudada = aplicarEvento(pausada, { tipo: "inicio", thread_id: "t1", reanudacion: true, momento });
    expect(reanudada.fase).toBe("corriendo");
    expect(reanudada.pausa).toBeUndefined();
    expect(reanudada.bitacora).toHaveLength(2);
  });

  it("un error marca como fallidos los nodos que seguían corriendo", () => {
    const corriendo = aplicar([{ tipo: "nodo_inicio", id: "a", nodo: "clasificar", momento }]);
    const fallida = marcarError(corriendo, "sin conexión");
    expect(fallida.fase).toBe("error");
    expect(fallida.error).toBe("sin conexión");
    expect(fallida.nodos.clasificar.estado).toBe("fallo");
  });
});
