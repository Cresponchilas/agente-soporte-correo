import type { Corrida } from "@/lib/corrida";
import { evaluar } from "@/lib/evaluacion";
import type { CasoDePrueba } from "@/lib/tipos";

export const CLAVE_PROPIO = "propio";

interface Props {
  casos: CasoDePrueba[];
  errorCasos: string | null;
  corridas: Record<string, Corrida>;
  seleccionado: string;
  alSeleccionar: (clave: string) => void;
  alProbarTodos: () => void;
  ocupada: boolean;
  apiLista: boolean;
}

function marcaDeResultado(caso: CasoDePrueba, corrida?: Corrida) {
  if (!corrida || corrida.fase === "sin_iniciar") return null;
  if (corrida.fase === "corriendo") return <span className="marca marca--corriendo" aria-label="Procesando" />;
  if (corrida.fase === "error") return <span className="marca marca--error" title={corrida.error}>!</span>;
  if (!corrida.resumen) return null;
  const { intencion, revision } = evaluar(caso.esperado, corrida.resumen);
  const acierto = intencion.acierto && revision.acierto;
  return (
    <span className={`marca ${acierto ? "marca--ok" : "marca--falla"}`} title={acierto ? "Coincide con lo esperado" : "No coincide"}>
      {acierto ? "✓" : "✗"}
    </span>
  );
}

function Marcador({ casos, corridas }: Pick<Props, "casos" | "corridas">) {
  const evaluados = casos.flatMap((caso) => {
    const resumen = corridas[caso.id]?.resumen;
    return resumen ? [evaluar(caso.esperado, resumen)] : [];
  });
  if (evaluados.length === 0) return null;
  const intencion = evaluados.filter((e) => e.intencion.acierto).length;
  const revision = evaluados.filter((e) => e.revision.acierto).length;
  return (
    <dl className="marcador">
      <div>
        <dt>Intención correcta</dt>
        <dd>
          {intencion}/{evaluados.length}
        </dd>
      </div>
      <div>
        <dt>Revisión correcta</dt>
        <dd>
          {revision}/{evaluados.length}
        </dd>
      </div>
    </dl>
  );
}

export function Bandeja(props: Props) {
  const { casos, errorCasos, corridas, seleccionado, alSeleccionar, alProbarTodos, ocupada, apiLista } = props;

  return (
    <nav className="bandeja" aria-label="Correos">
      <button
        type="button"
        className={`bandeja__item bandeja__item--propio ${seleccionado === CLAVE_PROPIO ? "es-activo" : ""}`}
        onClick={() => alSeleccionar(CLAVE_PROPIO)}
      >
        <span className="bandeja__asunto">Escribir un correo</span>
        <span className="bandeja__remitente">Prueba el agente con tu propio texto</span>
      </button>

      <div className="bandeja__encabezado">
        <h2>Casos de prueba</h2>
        <button type="button" className="boton boton--chico" onClick={alProbarTodos} disabled={ocupada || !apiLista || casos.length === 0}>
          {ocupada ? "Probando…" : `Probar los ${casos.length || 8}`}
        </button>
      </div>
      <p className="bandeja__nota">Cada caso trae la intención esperada y si debería pasar por revisión humana.</p>

      {errorCasos && <p className="aviso aviso--error">{errorCasos}</p>}
      {!errorCasos && apiLista && casos.length === 0 && <p className="bandeja__nota">Cargando casos…</p>}

      <ul className="bandeja__lista">
        {casos.map((caso) => (
          <li key={caso.id}>
            <button
              type="button"
              className={`bandeja__item ${seleccionado === caso.id ? "es-activo" : ""}`}
              onClick={() => alSeleccionar(caso.id)}
            >
              <span className="bandeja__asunto">{caso.entrada.asunto}</span>
              <span className="bandeja__remitente">{caso.entrada.remitente}</span>
              <span className="bandeja__marca">{marcaDeResultado(caso, corridas[caso.id])}</span>
            </button>
          </li>
        ))}
      </ul>
      <Marcador casos={casos} corridas={corridas} />
    </nav>
  );
}
