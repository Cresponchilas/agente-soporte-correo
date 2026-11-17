# Despliegue: Neon (Postgres) + Render (API) + Vercel (dashboard)

Orden recomendado: base de datos, luego API, luego dashboard. Todo cabe en los planes gratuitos.

## 1. Base de datos en Neon

1. Crea una cuenta en https://neon.tech y un proyecto (región cercana, por ejemplo `us-east`).
2. En *Connection details*, copia la cadena de conexión **con pooling** (`...-pooler...`). Se ve así:
   `postgresql://usuario:clave@ep-xxxx-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require`
3. No hace falta crear tablas: la API las crea al arrancar (`checkpointer.setup()`).

## 2. API en Render

1. En https://render.com: *New → Blueprint* y elige el repositorio. Render lee `render.yaml`.
2. Cuando pida las variables marcadas `sync: false`, llena:
   - `OPENAI_API_KEY`: tu llave de OpenAI.
   - `DATABASE_URL`: la cadena de Neon del paso 1.
   - `FRONTEND_ORIGINS`: por ahora `http://localhost:3000`; en el paso 3 le agregas la URL de Vercel.
   - `LANGSMITH_API_KEY`: opcional, para ver las trazas.
3. Espera el primer despliegue y abre `https://TU-SERVICIO.onrender.com/salud`. Debe decir `"persistencia":"postgres"`.
4. Abre `https://TU-SERVICIO.onrender.com/docs` para probar la API a mano.

El plan gratuito duerme el servicio tras 15 minutos sin uso; la primera petición tarda hasta un minuto.
El dashboard lo muestra como "Despertando la API". Antes de una demo, abre `/salud` unos minutos antes.

## 3. Dashboard en Vercel

1. En https://vercel.com: *Add New → Project* y elige el repositorio.
2. **Root Directory: `web`** (importante: el frontend vive en esa carpeta).
3. Variable de entorno: `NEXT_PUBLIC_API_URL` = `https://TU-SERVICIO.onrender.com` (sin `/` al final).
4. Despliega y copia la URL final (por ejemplo `https://agente-soporte.vercel.app`).
5. Vuelve a Render y cambia `FRONTEND_ORIGINS` a
   `https://agente-soporte.vercel.app,http://localhost:3000`. Render redespliega solo.

## 4. Protege tu saldo

- En OpenAI, *Settings → Limits*: pon un límite mensual (por ejemplo 5 USD).
- La API limita a 15 correos por IP por hora y 300 por día (`CORRIDAS_POR_IP_POR_HORA`, `CORRIDAS_POR_DIA`).
  "Probar los 8" gasta 8 de esos 15.

## Problemas comunes

| Síntoma | Causa probable |
|---|---|
| El dashboard dice "La API no responde" | URL mal escrita en `NEXT_PUBLIC_API_URL`, o el servicio de Render falló al arrancar (revisa *Logs*) |
| Error de CORS en la consola del navegador | La URL de Vercel no está en `FRONTEND_ORIGINS` (exacta, con `https://` y sin `/` final) |
| `/salud` dice `memoria` | `DATABASE_URL` vacía en Render |
| Evento de error "La llave de OpenAI del servidor no es válida." | `OPENAI_API_KEY` mal copiada en Render |
| Los cambios de `NEXT_PUBLIC_API_URL` no se notan | Vercel la incrusta al compilar: hay que redesplegar |

## Local, sin desplegar nada

```bash
# Terminal 1 (raíz del repo): API en http://localhost:8000, estado en memoria
uvicorn soporte.api.app:app --reload

# Terminal 2: dashboard en http://localhost:3000
cd web
npm install
npm run dev
```

En Windows deja `DATABASE_URL` vacía en local: el driver asíncrono de Postgres no funciona con el
event loop por defecto de Windows. En Render (Linux) no hay problema.
