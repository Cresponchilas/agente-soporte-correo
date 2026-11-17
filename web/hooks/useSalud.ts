"use client";

// Comprueba si la API está disponible. Render duerme los servicios gratuitos y
// tardan hasta un minuto en despertar, así que los primeros fallos no son "caída".

import { useCallback, useEffect, useRef, useState } from "react";
import { pedirJSON } from "@/lib/api";
import type { Salud } from "@/lib/tipos";

export type EstadoApi = "comprobando" | "lista" | "despertando" | "caida";

const PACIENCIA_MS = 90_000;
const ESPERA_ENTRE_INTENTOS_MS = 4_000;

export function useSalud() {
  const [estado, setEstado] = useState<EstadoApi>("comprobando");
  const [info, setInfo] = useState<Salud | null>(null);
  const [intento, setIntento] = useState(0);
  const inicio = useRef(Date.now());

  useEffect(() => {
    let cancelado = false;
    let temporizador: ReturnType<typeof setTimeout>;

    const comprobar = async () => {
      try {
        const salud = await pedirJSON<Salud>("/salud", 8_000);
        if (cancelado) return;
        setInfo(salud);
        setEstado("lista");
      } catch {
        if (cancelado) return;
        if (Date.now() - inicio.current < PACIENCIA_MS) {
          setEstado("despertando");
          temporizador = setTimeout(comprobar, ESPERA_ENTRE_INTENTOS_MS);
        } else {
          setEstado("caida");
        }
      }
    };

    comprobar();
    return () => {
      cancelado = true;
      clearTimeout(temporizador);
    };
  }, [intento]);

  const reintentar = useCallback(() => {
    inicio.current = Date.now();
    setEstado("comprobando");
    setIntento((n) => n + 1);
  }, []);

  return { estado, info, reintentar };
}
