// Pequeñas utilidades para mostrar datos en español.

export function contactosPrevios(n: number): string {
  if (n === 0) return "sin contactos previos";
  return n === 1 ? "1 contacto previo" : `${n} contactos previos`;
}

export function formatearMs(ms: number): string {
  return ms < 1000 ? `${Math.max(0, Math.round(ms))} ms` : `${(ms / 1000).toFixed(1).replace(".", ",")} s`;
}
