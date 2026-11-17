import type { EstadoApi as Estado } from "@/hooks/useSalud";
import type { Salud } from "@/lib/tipos";

const TEXTOS: Record<Estado, string> = {
  comprobando: "Conectando con la API",
  lista: "API lista",
  despertando: "Despertando la API (puede tardar un minuto)",
  caida: "La API no responde",
};

export function EstadoApi({ estado, info, alReintentar }: { estado: Estado; info: Salud | null; alReintentar: () => void }) {
  return (
    <div className="estado-api" data-estado={estado} role="status">
      <span className="estado-api__luz" aria-hidden />
      <span>{TEXTOS[estado]}</span>
      {estado === "lista" && info && (
        <span className="estado-api__detalle">
          {info.modelo.replace("openai:", "")}, estado en {info.persistencia === "postgres" ? "Postgres" : "memoria"}
        </span>
      )}
      {estado === "caida" && (
        <button type="button" className="boton boton--chico" onClick={alReintentar}>
          Reintentar
        </button>
      )}
    </div>
  );
}
