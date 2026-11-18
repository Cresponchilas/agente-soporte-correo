# Dashboard del agente de soporte

Next.js (App Router) sin librerías de UI. Habla con la API de `src/soporte/api` y muestra:

- **Bandeja:** los 8 casos de prueba y un formulario para escribir tu propio correo. "Probar los 8" corre todos
  y cuenta cuántos coinciden con la intención y la revisión esperadas.
- **Centro:** clasificación, documentos que encontró el RAG, ticket, borrador y la revisión humana
  (aprobar, editar o rechazar).
- **Tránsito (derecha):** el grafo con el estado de cada nodo en vivo y la bitácora de eventos que llegan por
  Server-Sent Events, con duración y datos que cada nodo escribió en el estado.

```bash
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_URL
npm run dev                  # http://localhost:3000
npm test                     # lector SSE, reducer de corridas, evaluación y textos
npm run typecheck
```

Estructura:

| Carpeta | Contenido |
|---|---|
| `lib/` | Lógica pura y probada: lector SSE, reducer de una corrida, evaluación contra lo esperado, cliente HTTP |
| `hooks/` | Estado de React: salud de la API (con espera de arranque), casos y corridas |
| `components/` | Piezas de interfaz, sin llamadas a la red |
