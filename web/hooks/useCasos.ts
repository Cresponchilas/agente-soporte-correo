"use client";

import { useEffect, useState } from "react";
import { ErrorDeApi, pedirJSON } from "@/lib/api";
import type { CasoDePrueba } from "@/lib/tipos";

/** Carga los casos de prueba cuando la API está lista. */
export function useCasos(apiLista: boolean) {
  const [casos, setCasos] = useState<CasoDePrueba[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!apiLista) return;
    let cancelado = false;
    pedirJSON<CasoDePrueba[]>("/casos")
      .then((datos) => !cancelado && (setCasos(datos), setError(null)))
      .catch((e: unknown) => !cancelado && setError(e instanceof ErrorDeApi ? e.message : "No se pudieron cargar los casos."));
    return () => {
      cancelado = true;
    };
  }, [apiLista]);

  return { casos, error };
}
