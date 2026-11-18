// Tests de la lógica pura del dashboard. Opcionales: necesitan Node (sin dependencias).
//     node --test tests/js/logica.test.mjs

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { aplicarEvento, corridaDesdeResumen, corridaNueva, marcarError } from "../../src/soporte/web/js/corrida.js";
import { evaluar } from "../../src/soporte/web/js/evaluacion.js";
import { crearLectorSSE } from "../../src/soporte/web/js/sse.js";
import { contactosPrevios, esc, formatearMs } from "../../src/soporte/web/js/texto.js";

const momento = "2026-11-18T00:00:00.000Z";
const resumen = (extra = {}) => ({
  clasificacion: { intencion: "pregunta", urgencia: "baja", tema: "t", resumen: "r" },
  fragmentos: [], historial_cliente: null, ticket_id: null, borrador: "hola",
  decision_humana: null, enviado: false, pasos: ["recibir_correo"], pausado_en: [], ...extra,
});

describe("lector SSE", () => {
  it("arma un evento partido en dos pedazos", () => {
    const lector = crearLectorSSE();
    assert.deepEqual(lector.leer('data: {"tipo":"pa'), []);
    assert.deepEqual(lector.leer('so"}\n\n'), [{ tipo: "paso" }]);
  });
  it("ignora bloques corruptos sin perder los siguientes", () => {
    assert.deepEqual(crearLectorSSE().leer('data: {roto\n\ndata: {"ok":true}\n\n'), [{ ok: true }]);
  });
});

describe("corrida", () => {
  it("sigue el ciclo de un nodo y termina pausada si espera revisión", () => {
    const eventos = [
      { tipo: "inicio", thread_id: "t1", reanudacion: false, momento },
      { tipo: "nodo_inicio", id: "a", nodo: "clasificar", momento },
      { tipo: "nodo_fin", id: "a", nodo: "clasificar", actualizacion: {}, duracion_ms: 40, fallo: false, momento },
      { tipo: "fin", thread_id: "t1", estado: resumen({ pausado_en: ["revision_humana"] }), momento },
    ];
    const corrida = eventos.reduce(aplicarEvento, corridaNueva);
    assert.equal(corrida.fase, "pausada");
    assert.deepEqual(corrida.nodos.clasificar, { estado: "hecho", duracionMs: 40 });
  });
  it("un error marca como fallidos los nodos que seguían corriendo", () => {
    const corriendo = aplicarEvento(corridaNueva, { tipo: "nodo_inicio", id: "a", nodo: "clasificar", momento });
    assert.equal(marcarError(corriendo, "x").nodos.clasificar.estado, "fallo");
  });
  it("se reconstruye pausada desde el servidor", () => {
    const corrida = corridaDesdeResumen("t1", resumen({ pausado_en: ["revision_humana"] }), "a@b.co");
    assert.equal(corrida.fase, "pausada");
    assert.equal(corrida.pausa.borrador, "hola");
  });
});

describe("evaluación y textos", () => {
  it("acepta cualquiera de las intenciones válidas", () => {
    assert.equal(evaluar({ intencion: ["cotizacion", "pregunta"], necesita_revision: false }, resumen()).intencion.acierto, true);
  });
  it("escapa HTML", () => assert.equal(esc('<b a="1">'), "&lt;b a=&quot;1&quot;&gt;"));
  it("usa singular y plural y formatea duraciones", () => {
    assert.equal(contactosPrevios(1), "1 contacto previo");
    assert.equal(formatearMs(1250), "1,3 s");
  });
});
