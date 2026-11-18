"use client";

// Maneja varias corridas a la vez (una por caso o correo propio), cada una con su
// propio estado construido a partir de los eventos que transmite la API.

import { useCallback, useEffect, useReducer, useRef } from "react";
import { ErrorDeApi, transmitir } from "@/lib/api";
import { aplicarEvento, corridaNueva, marcarError, type Corrida } from "@/lib/corrida";
import type { Accion, CasoDePrueba, Correo, EventoCorrida } from "@/lib/tipos";

type Corridas = Record<string, Corrida>;

type CambioDeCorridas =
  | { tipo: "reiniciar"; clave: string }
  | { tipo: "evento"; clave: string; evento: EventoCorrida }
  | { tipo: "fallo"; clave: string; mensaje: string };

function reducir(corridas: Corridas, cambio: CambioDeCorridas): Corridas {
  const actual = corridas[cambio.clave] ?? corridaNueva;
  switch (cambio.tipo) {
    case "reiniciar":
      return { ...corridas, [cambio.clave]: { ...corridaNueva, fase: "corriendo" } };
    case "evento":
      return { ...corridas, [cambio.clave]: aplicarEvento(actual, cambio.evento) };
    case "fallo":
      return { ...corridas, [cambio.clave]: marcarError(actual, cambio.mensaje) };
  }
}

function mensajeDe(error: unknown): string {
  if (error instanceof ErrorDeApi) {
    const campos = error.detalles.map((d) => `${d.campo}: ${d.mensaje}`).join("; ");
    return campos ? `${error.message} (${campos})` : error.message;
  }
  return "Algo salió mal en el navegador. Recarga la página e intenta de nuevo.";
}

export function useCorridas() {
  const [corridas, despachar] = useReducer(reducir, {});
  const controladores = useRef(new Map<string, AbortController>());

  useEffect(() => {
    const activos = controladores.current;
    return () => activos.forEach((c) => c.abort()); // al salir de la página, cortar streams
  }, []);

  /** Devuelve el error si la corrida no pudo completarse (o undefined si salió bien). */
  const ejecutar = useCallback(async (clave: string, ruta: string, cuerpo: unknown): Promise<unknown> => {
    controladores.current.get(clave)?.abort();
    const controlador = new AbortController();
    controladores.current.set(clave, controlador);
    try {
      await transmitir(ruta, cuerpo, (evento) => despachar({ tipo: "evento", clave, evento }), controlador.signal);
    } catch (error) {
      if (!controlador.signal.aborted) despachar({ tipo: "fallo", clave, mensaje: mensajeDe(error) });
      return error;
    } finally {
      if (controladores.current.get(clave) === controlador) controladores.current.delete(clave);
    }
  }, []);

  const procesar = useCallback(
    async (clave: string, correo: Correo) => {
      despachar({ tipo: "reiniciar", clave });
      return ejecutar(clave, "/corridas", correo);
    },
    [ejecutar],
  );

  const decidir = useCallback(
    async (clave: string, threadId: string, accion: Accion, texto?: string) => {
      return ejecutar(clave, `/corridas/${threadId}/decision`, { accion, texto });
    },
    [ejecutar],
  );

  /** Corre los casos uno tras otro (no en paralelo, para no gastar el límite de golpe). */
  const probarTodos = useCallback(
    async (casos: CasoDePrueba[]) => {
      for (const caso of casos) {
        const error = await procesar(caso.id, caso.entrada);
        // Si se alcanzó el límite de uso, los siguientes también fallarían.
        if (error instanceof ErrorDeApi && error.estado === 429) break;
      }
    },
    [procesar],
  );

  return { corridas, procesar, decidir, probarTodos };
}
