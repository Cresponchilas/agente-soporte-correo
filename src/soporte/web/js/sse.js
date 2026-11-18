// Lector incremental de Server-Sent Events. Los datos llegan en pedazos arbitrarios
// de la red: un evento puede venir partido en dos pedazos, o varios en uno solo.

export function crearLectorSSE() {
  let pendiente = "";

  return {
    /** Recibe un pedazo de texto y devuelve los eventos completos que ya se pueden leer. */
    leer(pedazo) {
      pendiente += pedazo.replace(/\r\n/g, "\n");
      const bloques = pendiente.split("\n\n");
      pendiente = bloques.pop() ?? ""; // el último puede estar incompleto

      return bloques.flatMap((bloque) => {
        const datos = bloque
          .split("\n")
          .filter((linea) => linea.startsWith("data:"))
          .map((linea) => linea.slice(5).trimStart())
          .join("\n");
        if (!datos) return [];
        try {
          return [JSON.parse(datos)];
        } catch {
          return []; // un bloque corrupto no debe tumbar toda la transmisión
        }
      });
    },
  };
}
