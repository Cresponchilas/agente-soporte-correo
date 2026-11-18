import type { Corrida } from "@/lib/corrida";
import { FILAS, nombreCorto, nombreDeNodo } from "@/lib/grafo";
import { contactosPrevios, formatearMs } from "@/lib/texto";
import type { EventoCorrida } from "@/lib/tipos";

export function PanelTransito({ corrida }: { corrida?: Corrida }) {
  const activa = corrida?.fase === "corriendo";

  return (
    <aside className="transito" data-activo={activa} aria-label="Tránsito de la información">
      <div className="transito__franja" aria-hidden />
      <header className="transito__encabezado">
        <h2>Tránsito</h2>
        {corrida?.threadId && (
          <span className="transito__hilo" title={corrida.threadId}>
            Hilo {corrida.threadId.slice(0, 8)}
          </span>
        )}
      </header>

      <MapaDelGrafo corrida={corrida} />

      <h3 className="transito__subtitulo">Bitácora de eventos</h3>
      {!corrida || corrida.bitacora.length === 0 ? (
        <p className="transito__vacio">
          Procesa un correo para ver aquí cada nodo del grafo: cuándo empieza, qué escribe en el estado y cuánto tarda.
        </p>
      ) : (
        <Bitacora eventos={corrida.bitacora} />
      )}
    </aside>
  );
}

function MapaDelGrafo({ corrida }: { corrida?: Corrida }) {
  const termino = corrida?.fase === "terminada" || corrida?.fase === "pausada" || corrida?.fase === "error";

  const estadoDe = (nodo: string) => {
    const info = corrida?.nodos[nodo];
    if (info) return info.estado;
    return termino ? "omitido" : "pendiente";
  };

  return (
    <ol className="mapa" aria-label="Nodos del grafo">
      {FILAS.map((fila) => (
        <li key={fila.join()} className="mapa__fila" data-paralela={fila.length > 1}>
          {fila.map((nodo) => {
            const estado = estadoDe(nodo);
            const duracion = corrida?.nodos[nodo]?.duracionMs;
            return (
              <span key={nodo} className="mapa__nodo" data-estado={estado} title={nombreDeNodo(nodo)}>
                <span className="mapa__nombre">{nombreCorto(nodo)}</span>
                <span className="mapa__estado">{textoDeEstado(estado, duracion)}</span>
              </span>
            );
          })}
        </li>
      ))}
    </ol>
  );
}

function textoDeEstado(estado: string, duracionMs?: number): string {
  switch (estado) {
    case "corriendo":
      return "corriendo";
    case "hecho":
      return duracionMs !== undefined ? formatearMs(duracionMs) : "listo";
    case "en_pausa":
      return "esperando";
    case "fallo":
      return "falló";
    case "omitido":
      return "no aplicó";
    default:
      return "";
  }
}

function Bitacora({ eventos }: { eventos: EventoCorrida[] }) {
  const origen = Date.parse(eventos[0].momento);

  return (
    <ol className="bitacora">
      {eventos.map((evento, i) => {
        const { titulo, detalle, datos } = describir(evento);
        return (
          <li key={i} className="bitacora__evento" data-tipo={evento.tipo}>
            <span className="bitacora__tiempo">+{formatearMs(Date.parse(evento.momento) - origen)}</span>
            <div className="bitacora__cuerpo">
              <span className="bitacora__titulo">{titulo}</span>
              {detalle && <span className="bitacora__detalle">{detalle}</span>}
              {datos !== undefined && (
                <details className="bitacora__datos">
                  <summary>Ver datos</summary>
                  <pre>{JSON.stringify(datos, null, 2)}</pre>
                </details>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function describir(evento: EventoCorrida): { titulo: string; detalle?: string; datos?: unknown } {
  switch (evento.tipo) {
    case "inicio":
      return { titulo: evento.reanudacion ? "Reanudada con tu decisión" : "Corrida iniciada" };
    case "nodo_inicio":
      return { titulo: `${nombreDeNodo(evento.nodo)} empezó` };
    case "nodo_fin":
      return {
        titulo: `${nombreDeNodo(evento.nodo)} ${evento.fallo ? "falló" : "terminó"} en ${formatearMs(evento.duracion_ms)}`,
        detalle: resumirActualizacion(evento.nodo, evento.actualizacion),
        datos: evento.actualizacion,
      };
    case "pausa":
      return { titulo: "Pausa: espera revisión humana", detalle: "El grafo guardó su estado y quedó detenido.", datos: evento.solicitud };
    case "fin":
      return {
        titulo: evento.estado.pausado_en.length ? "Detenido hasta tu decisión" : "Corrida terminada",
        datos: evento.estado,
      };
    case "error":
      return { titulo: "Error", detalle: evento.mensaje };
  }
}

function resumirActualizacion(nodo: string, a: Record<string, unknown>): string | undefined {
  const clasificacion = a.clasificacion as { intencion?: string; urgencia?: string } | undefined;
  switch (nodo) {
    case "clasificar":
      return clasificacion ? `${clasificacion.intencion}, urgencia ${clasificacion.urgencia}` : undefined;
    case "buscar_documentacion": {
      const fragmentos = (a.fragmentos as { fuente: string }[] | undefined) ?? [];
      return `${fragmentos.length} fragmentos: ${fragmentos.map((f) => f.fuente.split("#")[1] ?? f.fuente).join(", ")}`;
    }
    case "consultar_historial": {
      const historial = a.historial_cliente as { contactos_previos?: number } | undefined;
      return contactosPrevios(historial?.contactos_previos ?? 0);
    }
    case "crear_ticket":
      return `Ticket ${a.ticket_id}`;
    case "redactar_respuesta":
      return typeof a.borrador === "string" ? `Borrador de ${a.borrador.split(/\s+/).length} palabras` : undefined;
    case "revision_humana":
      return a.decision_humana ? `Decisión: ${a.decision_humana}` : undefined;
    default:
      return undefined;
  }
}
