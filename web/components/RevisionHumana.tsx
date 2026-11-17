import { useState } from "react";
import type { Accion, SolicitudDeRevision } from "@/lib/tipos";

interface Props {
  solicitud: SolicitudDeRevision;
  alDecidir: (accion: Accion, texto?: string) => void;
}

export function RevisionHumana({ solicitud, alDecidir }: Props) {
  const [texto, setTexto] = useState(solicitud.borrador);
  const [enviando, setEnviando] = useState(false); // evita decidir dos veces con doble clic
  const editado = texto.trim() !== solicitud.borrador.trim();

  const decidir = (accion: Accion, textoNuevo?: string) => {
    setEnviando(true);
    alDecidir(accion, textoNuevo);
  };

  return (
    <section className="revision" aria-labelledby="titulo-revision">
      <h3 id="titulo-revision">Necesita tu aprobación</h3>
      <p className="revision__motivo">
        El agente se detuvo antes de enviar: urgencia {solicitud.urgencia}, intención {solicitud.intencion}
        {solicitud.ticket_id ? `, ticket ${solicitud.ticket_id}` : ""}. Puedes ajustar el texto antes de decidir.
      </p>
      <label htmlFor="texto-revision" className="sr-only">
        Respuesta que se enviará
      </label>
      <textarea id="texto-revision" rows={9} value={texto} onChange={(e) => setTexto(e.target.value)} disabled={enviando} />
      <div className="revision__acciones">
        {editado ? (
          <button type="button" className="boton boton--primario" disabled={enviando || !texto.trim()} onClick={() => decidir("editar", texto)}>
            Enviar con mis cambios
          </button>
        ) : (
          <button type="button" className="boton boton--primario" disabled={enviando} onClick={() => decidir("aprobar")}>
            Aprobar y enviar
          </button>
        )}
        {editado && (
          <button type="button" className="boton" disabled={enviando} onClick={() => setTexto(solicitud.borrador)}>
            Deshacer cambios
          </button>
        )}
        <button type="button" className="boton boton--peligro" disabled={enviando} onClick={() => decidir("rechazar")}>
          Rechazar
        </button>
      </div>
    </section>
  );
}
