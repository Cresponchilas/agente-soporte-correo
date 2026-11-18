"""Arranca la demo completa con un solo comando:

    python -m soporte.api              # http://localhost:8000
    python -m soporte.api --puerto 8080
"""

import argparse
import threading
import webbrowser

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo del agente de soporte por correo")
    parser.add_argument("--puerto", type=int, default=8000)
    parser.add_argument("--sin-navegador", action="store_true", help="No abrir el navegador al arrancar")
    args = parser.parse_args()

    url = f"http://localhost:{args.puerto}"
    print(f"\n  Dashboard: {url}\n  API:       {url}/docs\n")
    if not args.sin_navegador:
        # Se abre un momento después, cuando el servidor ya está escuchando.
        threading.Timer(1.5, webbrowser.open, args=[url]).start()
    uvicorn.run("soporte.api.app:crear_app_desde_entorno", factory=True, host="127.0.0.1", port=args.puerto)


if __name__ == "__main__":
    main()
