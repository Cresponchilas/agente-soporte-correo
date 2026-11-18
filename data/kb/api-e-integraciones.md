# API e integraciones

## Límites de la API
El plan Pyme permite 60 solicitudes por minuto; el plan Empresa, 600. Si se supera el límite, la API responde con el código 429 y el encabezado Retry-After.

## Errores comunes
- 401: la llave de API es inválida o fue rotada.
- 422: la factura tiene campos inválidos; la respuesta indica cuál campo falla.
- 500: error interno de Contaflux; se debe reportar a soporte con el identificador de la solicitud.

## Webhooks
Los webhooks reintentan el envío hasta 5 veces con espera exponencial si el servidor del cliente no responde con 2xx.
