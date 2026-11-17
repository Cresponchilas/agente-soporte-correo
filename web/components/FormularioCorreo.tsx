import type { Correo } from "@/lib/tipos";

// Las mismas reglas que valida la API (src/soporte/api/esquemas.py), para avisar
// antes de enviar. La API igual valida: el navegador no es de fiar.
export function erroresDeCorreo(correo: Correo): Partial<Record<keyof Correo, string>> {
  const errores: Partial<Record<keyof Correo, string>> = {};
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(correo.remitente.trim())) errores.remitente = "Escribe un correo válido, como ana@empresa.co";
  if (correo.cuerpo.trim().length < 5) errores.cuerpo = "Escribe al menos una frase";
  if (correo.cuerpo.length > 4000) errores.cuerpo = "Máximo 4.000 caracteres";
  if (correo.asunto.length > 200) errores.asunto = "Máximo 200 caracteres";
  return errores;
}

interface Props {
  correo: Correo;
  alCambiar: (correo: Correo) => void;
  mostrarErrores: boolean;
}

export function FormularioCorreo({ correo, alCambiar, mostrarErrores }: Props) {
  const errores = mostrarErrores ? erroresDeCorreo(correo) : {};
  const campo = (nombre: keyof Correo) => ({
    id: `correo-${nombre}`,
    value: correo[nombre],
    "aria-invalid": Boolean(errores[nombre]),
    "aria-describedby": errores[nombre] ? `error-${nombre}` : undefined,
    onChange: (e: { target: { value: string } }) => alCambiar({ ...correo, [nombre]: e.target.value }),
  });

  return (
    <div className="formulario">
      <label htmlFor="correo-remitente">De</label>
      <input type="email" placeholder="cliente@empresa.co" autoComplete="off" {...campo("remitente")} />
      {errores.remitente && <p id="error-remitente" className="formulario__error">{errores.remitente}</p>}

      <label htmlFor="correo-asunto">Asunto</label>
      <input type="text" placeholder="Ej.: No puedo descargar mis facturas" {...campo("asunto")} />
      {errores.asunto && <p id="error-asunto" className="formulario__error">{errores.asunto}</p>}

      <label htmlFor="correo-cuerpo">Mensaje</label>
      <textarea rows={6} placeholder="Escribe el correo como lo enviaría un cliente" {...campo("cuerpo")} />
      {errores.cuerpo && <p id="error-cuerpo" className="formulario__error">{errores.cuerpo}</p>}
    </div>
  );
}
