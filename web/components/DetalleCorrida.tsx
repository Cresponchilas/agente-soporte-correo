import { useState } from "react";
import { estadoAcumulado, type Corrida } from "@/lib/corrida";
import { evaluar } from "@/lib/evaluacion";
import { contactosPrevios } from "@/lib/texto";
import type { Accion, CasoDePrueba, Correo, Fragmento } from "@/lib/tipos";
import { erroresDeCorreo, FormularioCorreo } from "./FormularioCorreo";
import { RevisionHumana } from "./RevisionHumana";

interface Props {
  caso?: CasoDePrueba; // si no hay caso, es un correo escrito por el usuario
  correoPropio: Correo;
  alCambiarCorreoPropio: (correo: Correo) => void;
  corrida?: Corrida;
  apiLista: boolean;
  alProcesar: (correo: Correo) => void;
  alDecidir: (accion: Accion, texto?: string) => void;
}

export function DetalleCorrida({ caso, correoPropio, alCambiarCorreoPropio, corrida, apiLista, alProcesar, alDecidir }: Props) {
  const [intentoEnviar, setIntentoEnviar] = useState(false);
  const correo = caso?.entrada ?? correoPropio;
  const corriendo = corrida?.fase === "corriendo";

  const procesar = () => {
    if (!caso) {
      setIntentoEnviar(true);
      if (Object.keys(erroresDeCorreo(correo)).length > 0) return;
    }
    alProcesar(correo);
  };

  return (
    <article className="detalle">
      <header className="detalle__correo">
        {caso ? (
          <>
            <h2 className="detalle__asunto">{caso.entrada.asunto}</h2>
            <p className="detalle__remitente">De {caso.entrada.remitente}</p>
            <blockquote className="detalle__cuerpo">{caso.entrada.cuerpo}</blockquote>
          </>
        ) : (
          <>
            <h2 className="detalle__asunto">Escribe un correo de cliente</h2>
            <FormularioCorreo correo={correoPropio} alCambiar={alCambiarCorreoPropio} mostrarErrores={intentoEnviar} />
          </>
        )}
        <div className="detalle__acciones">
          <button type="button" className="boton boton--primario" onClick={procesar} disabled={!apiLista || corriendo}>
            {corriendo ? "Procesando…" : corrida && corrida.fase !== "sin_iniciar" ? "Procesar de nuevo" : "Procesar correo"}
          </button>
          {!apiLista && <span className="detalle__pista">Disponible cuando la API esté lista.</span>}
        </div>
      </header>

      {corrida && corrida.fase !== "sin_iniciar" && (
        <Resultado corrida={corrida} caso={caso} alDecidir={alDecidir} destinatario={correo.remitente} />
      )}
    </article>
  );
}

function Resultado({
  corrida,
  caso,
  alDecidir,
  destinatario,
}: {
  corrida: Corrida;
  caso?: CasoDePrueba;
  alDecidir: Props["alDecidir"];
  destinatario: string;
}) {
  const estado = estadoAcumulado(corrida);
  const { clasificacion, fragmentos, ticket_id, historial_cliente, borrador } = estado;

  return (
    <div className="resultado">
      {corrida.fase === "error" && (
        <div className="aviso aviso--error" role="alert">
          <strong>No se pudo completar.</strong> {corrida.error}
        </div>
      )}

      {/* Si la decisión falló antes de llegar al servidor, la corrida sigue pausada allá:
          se vuelve a mostrar el panel para reintentar. */}
      {(corrida.fase === "pausada" || corrida.fase === "error") && corrida.pausa && corrida.threadId && (
        <RevisionHumana key={`${corrida.threadId}-${corrida.bitacora.length}`} solicitud={corrida.pausa} alDecidir={alDecidir} />
      )}

      {corrida.fase === "terminada" && <Desenlace enviado={Boolean(estado.enviado)} decision={estado.decision_humana} destinatario={destinatario} />}

      {caso && corrida.resumen && <Comparacion caso={caso} corrida={corrida} />}

      <section className="resultado__seccion">
        <h3>Clasificación</h3>
        {clasificacion ? (
          <dl className="ficha">
            <div>
              <dt>Intención</dt>
              <dd>{clasificacion.intencion}</dd>
            </div>
            <div>
              <dt>Urgencia</dt>
              <dd data-urgencia={clasificacion.urgencia}>{clasificacion.urgencia}</dd>
            </div>
            <div className="ficha__ancho">
              <dt>Resumen</dt>
              <dd>{clasificacion.resumen}</dd>
            </div>
          </dl>
        ) : (
          <Pendiente corriendo={corrida.fase === "corriendo"} />
        )}
      </section>

      <section className="resultado__seccion">
        <h3>Contexto que reunió</h3>
        {fragmentos || historial_cliente ? (
          <>
            <p className="resultado__linea">
              {ticket_id ? `Ticket creado: ${ticket_id}.` : "Sin ticket (no es un bug ni algo crítico)."}{" "}
              {historialEnTexto(historial_cliente)}
            </p>
            {fragmentos && <Fuentes fragmentos={fragmentos} />}
          </>
        ) : (
          <Pendiente corriendo={corrida.fase === "corriendo"} />
        )}
      </section>

      {borrador && corrida.fase !== "pausada" && (
        <section className="resultado__seccion">
          <h3>{estado.enviado ? "Respuesta enviada" : "Borrador"}</h3>
          <div className="borrador">{borrador}</div>
        </section>
      )}
    </div>
  );
}

function Desenlace({ enviado, decision, destinatario }: { enviado: boolean; decision?: string | null; destinatario: string }) {
  if (enviado) {
    const quien = decision === "editado" ? "con tus cambios" : decision === "aprobado" ? "con tu aprobación" : "sin revisión humana";
    return <p className="aviso aviso--ok">Respuesta enviada a {destinatario} {quien}.</p>;
  }
  return <p className="aviso aviso--neutro">Rechazada: no se envió nada y el caso queda para una persona del equipo.</p>;
}

function Comparacion({ caso, corrida }: { caso: CasoDePrueba; corrida: Corrida }) {
  if (!corrida.resumen) return null;
  const { intencion, revision } = evaluar(caso.esperado, corrida.resumen);
  const filas = [
    { nombre: "Intención", comparacion: intencion },
    { nombre: "Pasa por revisión", comparacion: revision },
  ];
  return (
    <table className="comparacion">
      <caption>Contra lo esperado en el caso de prueba</caption>
      <thead>
        <tr>
          <th scope="col">Criterio</th>
          <th scope="col">Esperado</th>
          <th scope="col">Obtenido</th>
        </tr>
      </thead>
      <tbody>
        {filas.map(({ nombre, comparacion }) => (
          <tr key={nombre} data-acierto={comparacion.acierto}>
            <th scope="row">{nombre}</th>
            <td>{comparacion.esperado}</td>
            <td>
              {comparacion.obtenido}
              <span className="sr-only">{comparacion.acierto ? " (coincide)" : " (no coincide)"}</span>
              <span aria-hidden>{comparacion.acierto ? " ✓" : " ✗"}</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Fuentes({ fragmentos }: { fragmentos: Fragmento[] }) {
  return (
    <ul className="fuentes">
      {fragmentos.map((f) => (
        <li key={f.fuente}>
          <details>
            <summary>{f.fuente === "error" ? "La búsqueda falló" : f.fuente.replace("#", ", sección ")}</summary>
            <p>{f.texto}</p>
          </details>
        </li>
      ))}
    </ul>
  );
}

function Pendiente({ corriendo }: { corriendo: boolean }) {
  return <p className="resultado__pendiente">{corriendo ? "En proceso…" : "Sin datos."}</p>;
}

function historialEnTexto(historial?: Record<string, unknown> | null): string {
  if (!historial) return "";
  const nombre = typeof historial.nombre === "string" ? historial.nombre : "Cliente nuevo";
  return `${nombre}, ${contactosPrevios(Number(historial.contactos_previos ?? 0))}.`;
}
