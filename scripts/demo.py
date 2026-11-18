"""Demo por consola: procesa los correos de ejemplo y te pide aprobación cuando
el grafo se pausa en revision_humana.

    python scripts/demo.py            # todos los correos
    python scripts/demo.py 1          # solo el correo #1 (empieza en 0)
"""

import json
import sys
import uuid

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from soporte import config
from soporte.graph import construir_grafo


def pedir_decision(pausa: dict) -> dict:
    print("\n--- REVISIÓN HUMANA ---")
    print(f"De: {pausa['remitente']} | urgencia: {pausa['urgencia']} | intención: {pausa['intencion']} | ticket: {pausa['ticket_id']}")
    print(f"\nBorrador:\n{pausa['borrador']}\n")
    opcion = input("[a]probar, [e]ditar, [r]echazar: ").strip().lower()
    if opcion.startswith("e"):
        return {"accion": "editar", "texto": input("Nuevo texto: ")}
    if opcion.startswith("r"):
        return {"accion": "rechazar"}
    return {"accion": "aprobar"}


def main() -> None:
    correos = json.loads((config.RAIZ / "data" / "correos_ejemplo.json").read_text(encoding="utf-8"))
    if len(sys.argv) > 1:
        correos = [correos[int(sys.argv[1])]]

    grafo = construir_grafo(checkpointer=InMemorySaver())
    for i, ejemplo in enumerate(correos):
        # Un thread por correo: cada uno tiene su propio historial de checkpoints.
        cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
        entrada = {**ejemplo["entrada"], "correo_id": f"correo-{i}"}
        print(f"\n===== {entrada['asunto']} ({entrada['remitente']}) =====")

        resultado = grafo.invoke(entrada, cfg)
        while "__interrupt__" in resultado:
            decision = pedir_decision(resultado["__interrupt__"][0].value)
            resultado = grafo.invoke(Command(resume=decision), cfg)

        print(f"Pasos: {' -> '.join(resultado['pasos'])}")
        print(f"Fuentes del RAG: {[f['fuente'] for f in resultado.get('fragmentos', [])]}")
        print(f"Enviado: {resultado.get('enviado', False)} | decisión humana: {resultado.get('decision_humana')}")
        if resultado.get("enviado"):
            print(f"\nRespuesta enviada:\n{resultado['borrador']}")


if __name__ == "__main__":
    main()
