import { describe, expect, it } from "vitest";
import { contactosPrevios, formatearMs } from "./texto";

describe("texto", () => {
  it("usa singular y plural", () => {
    expect(contactosPrevios(0)).toBe("sin contactos previos");
    expect(contactosPrevios(1)).toBe("1 contacto previo");
    expect(contactosPrevios(3)).toBe("3 contactos previos");
  });

  it("formatea duraciones", () => {
    expect(formatearMs(42.4)).toBe("42 ms");
    expect(formatearMs(1250)).toBe("1,3 s");
  });
});
