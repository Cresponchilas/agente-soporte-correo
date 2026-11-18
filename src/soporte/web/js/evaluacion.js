// Compara el resultado de una corrida con lo esperado en el caso de prueba.

const siNo = (valor) => (valor ? "sí" : "no");

export function pidioRevision(resumen) {
  return resumen.pausado_en.includes("revision_humana") || resumen.decision_humana != null;
}

export function evaluar(esperado, resumen) {
  const validas = Array.isArray(esperado.intencion) ? esperado.intencion : [esperado.intencion];
  const intencion = resumen.clasificacion?.intencion ?? "—";
  const revision = pidioRevision(resumen);

  return {
    intencion: { esperado: validas.join(" o "), obtenido: intencion, acierto: validas.includes(intencion) },
    revision: { esperado: siNo(esperado.necesita_revision), obtenido: siNo(revision), acierto: revision === esperado.necesita_revision },
  };
}
