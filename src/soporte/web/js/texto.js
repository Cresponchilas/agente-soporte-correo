// Utilidades para mostrar datos en español, y para meter texto en HTML sin riesgo.

export function contactosPrevios(n) {
  if (n === 0) return "sin contactos previos";
  return n === 1 ? "1 contacto previo" : `${n} contactos previos`;
}

export function formatearMs(ms) {
  return ms < 1000 ? `${Math.max(0, Math.round(ms))} ms` : `${(ms / 1000).toFixed(1).replace(".", ",")} s`;
}

/** Escapa texto antes de ponerlo en HTML: el correo lo escribe el usuario. */
export function esc(valor) {
  return String(valor ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
