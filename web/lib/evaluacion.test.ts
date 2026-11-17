import { describe, expect, it } from "vitest";
import { evaluar } from "./evaluacion";
import type { ResumenEstado } from "./tipos";

const base: ResumenEstado = {
  clasificacion: { intencion: "pregunta", urgencia: "baja", tema: "t", resumen: "r" },
  fragmentos: [],
  historial_cliente: null,
  ticket_id: null,
  borrador: null,
  decision_humana: null,
  enviado: true,
  pasos: [],
  pausado_en: [],
};

describe("evaluar", () => {
  it("acepta cualquiera de las intenciones válidas", () => {
    const r = evaluar({ intencion: ["facturacion", "pregunta"], necesita_revision: false }, base);
    expect(r.intencion.acierto).toBe(true);
    expect(r.revision.acierto).toBe(true);
  });

  it("cuenta como revisión una corrida pausada o ya decidida", () => {
    expect(evaluar({ intencion: "pregunta", necesita_revision: true }, { ...base, pausado_en: ["revision_humana"] }).revision.acierto).toBe(true);
    expect(evaluar({ intencion: "pregunta", necesita_revision: true }, { ...base, decision_humana: "aprobado" }).revision.acierto).toBe(true);
    expect(evaluar({ intencion: "bug", necesita_revision: true }, base).intencion.acierto).toBe(false);
  });
});
