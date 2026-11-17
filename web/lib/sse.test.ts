import { describe, expect, it } from "vitest";
import { crearLectorSSE } from "./sse";

describe("crearLectorSSE", () => {
  it("arma un evento que llega partido en dos pedazos", () => {
    const lector = crearLectorSSE();
    expect(lector.leer('event: paso\ndata: {"tipo":"pa')).toEqual([]);
    expect(lector.leer('so","n":1}\n\n')).toEqual([{ tipo: "paso", n: 1 }]);
  });

  it("separa varios eventos que llegan juntos y tolera \\r\\n", () => {
    const lector = crearLectorSSE();
    const texto = 'data: {"a":1}\r\n\r\ndata: {"a":2}\n\n';
    expect(lector.leer(texto)).toEqual([{ a: 1 }, { a: 2 }]);
  });

  it("ignora bloques corruptos sin perder los siguientes", () => {
    const lector = crearLectorSSE();
    expect(lector.leer('data: {roto\n\ndata: {"ok":true}\n\n')).toEqual([{ ok: true }]);
  });
});
