# ADR-001 - Railway y PostgreSQL para persistencia

## Estado

Aceptada como arquitectura actual.

## Contexto

El agente de DMs y el modulo de comentarios necesitan persistencia fuera del proceso web. Railway ya hospeda el servicio Flask/gunicorn y proporciona PostgreSQL dentro del mismo entorno operativo.

La tabla `dm_context` conserva continuidad conversacional mediante un puntero `response_id`. El modulo de comentarios usa PostgreSQL para registrar eventos, estados y anti-bucle.

## Decision

Usar PostgreSQL en Railway como capa de persistencia operativa para:

- contexto minimo de DMs;
- eventos de comentarios;
- estados necesarios para evitar duplicados o bucles.

## Razones

- Esta disponible en el mismo proyecto Railway.
- Evita depender de archivos locales o SQLite en produccion.
- Permite consultas operativas y futuras migraciones.
- Es suficiente para el volumen actual.

## Consecuencias

- La disponibilidad de DMs depende tambien de PostgreSQL.
- La memoria actual es minima y requiere evolucion de esquema para escalar.
- Hay que documentar migraciones y claves antes de multiperfiles.

## Alternativas descartadas

- SQLite local: no adecuado para despliegue Railway con procesos efimeros.
- Solo memoria en proceso: se pierde en reinicios y no escala.
- CRM completo en esta fase: demasiado amplio para la necesidad actual.
- Guardar todo el historial privado: mayor riesgo de privacidad y no necesario para la fase actual.

## Fecha

2026-06-19
