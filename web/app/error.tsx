"use client";

// Si algo falla al dibujar la página, se muestra esto en vez de una pantalla en blanco.
export default function ErrorDePagina({ reset }: { error: Error; reset: () => void }) {
  return (
    <main className="pagina-error">
      <h1>El panel tuvo un problema</h1>
      <p>La información del agente no se perdió: las corridas viven en el servidor.</p>
      <button type="button" className="boton boton--primario" onClick={reset}>
        Volver a cargar el panel
      </button>
    </main>
  );
}
