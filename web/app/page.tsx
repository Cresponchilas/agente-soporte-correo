"use client";

import { useState } from "react";
import { Bandeja, CLAVE_PROPIO } from "@/components/Bandeja";
import { DetalleCorrida } from "@/components/DetalleCorrida";
import { EstadoApi } from "@/components/EstadoApi";
import { PanelTransito } from "@/components/PanelTransito";
import { useCasos } from "@/hooks/useCasos";
import { useCorridas } from "@/hooks/useCorridas";
import { useSalud } from "@/hooks/useSalud";
import type { Correo } from "@/lib/tipos";

const CORREO_VACIO: Correo = { remitente: "", asunto: "", cuerpo: "" };

export default function Panel() {
  const salud = useSalud();
  const apiLista = salud.estado === "lista";
  const { casos, error: errorCasos } = useCasos(apiLista);
  const { corridas, procesar, decidir, probarTodos } = useCorridas();

  const [seleccionado, setSeleccionado] = useState<string>(CLAVE_PROPIO);
  const [correoPropio, setCorreoPropio] = useState<Correo>(CORREO_VACIO);
  const [probandoTodos, setProbandoTodos] = useState(false);

  const caso = casos.find((c) => c.id === seleccionado);
  const corrida = corridas[seleccionado];

  const alProbarTodos = async () => {
    setProbandoTodos(true);
    try {
      await probarTodos(casos);
    } finally {
      setProbandoTodos(false);
    }
  };

  return (
    <div className="aplicacion">
      <header className="cabecera">
        <div>
          <h1 className="cabecera__titulo">Mesa de soporte Contaflux</h1>
          <p className="cabecera__subtitulo">Un agente de LangGraph clasifica, investiga y responde; tú apruebas lo delicado.</p>
        </div>
        <EstadoApi estado={salud.estado} info={salud.info} alReintentar={salud.reintentar} />
      </header>

      {salud.estado === "caida" && (
        <p className="aviso aviso--error cabecera__aviso" role="alert">
          No hay conexión con la API. Si acaba de desplegarse, espera un minuto y pulsa Reintentar.
        </p>
      )}

      <div className="tablero">
        <Bandeja
          casos={casos}
          errorCasos={errorCasos}
          corridas={corridas}
          seleccionado={seleccionado}
          alSeleccionar={setSeleccionado}
          alProbarTodos={alProbarTodos}
          ocupada={probandoTodos}
          apiLista={apiLista}
        />
        <main className="centro">
          <DetalleCorrida
            key={seleccionado}
            caso={caso}
            correoPropio={correoPropio}
            alCambiarCorreoPropio={setCorreoPropio}
            corrida={corrida}
            apiLista={apiLista}
            alProcesar={(correo) => procesar(seleccionado, correo)}
            alDecidir={(accion, texto) => corrida?.threadId && decidir(seleccionado, corrida.threadId, accion, texto)}
          />
        </main>
        <PanelTransito corrida={corrida} />
      </div>
    </div>
  );
}
