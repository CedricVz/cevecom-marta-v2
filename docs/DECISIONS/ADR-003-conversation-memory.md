# ADR-003 - Memoria conversacional mediante previous_response_id

## Estado

Aceptada como continuidad actual; requiere mejora antes de multiperfiles.

## Contexto

El agente de DMs necesita mantener continuidad entre mensajes del mismo usuario. Actualmente PostgreSQL guarda solo el ultimo `response_id` por `instagram_user_id`. Ese valor se pasa a OpenAI Responses API como `previous_response_id`.

La auditoria confirmo que no se guarda resumen local, estado del lead, tratamiento consultado, perfil, proyecto, canal ni base de conocimiento usada.

## Decision

Mantener `previous_response_id` como mecanismo actual de continuidad para Marta Estetica en una sola cuenta.

Planificar una evolucion futura hacia clave compuesta:

```text
project_id
profile_id
channel
channel_account_id
external_user_id
```

No implementar todavia CRM ni memoria comercial completa.

## Razones

- El mecanismo actual ya funciona en produccion.
- Minimiza almacenamiento de mensajes privados.
- Es simple y suficiente para la fase de una sola cuenta.
- Permite posponer un CRM hasta conocer mejor el flujo comercial real.

## Consecuencias

- Si OpenAI rechaza o pierde el contexto remoto, la continuidad se rompe.
- Si se pierde una fila de PostgreSQL, no hay resumen local para reconstruir.
- No permite aislar correctamente varios proyectos, perfiles o cuentas.
- No permite una intervencion humana informada solo con datos locales.

## Alternativas descartadas

- Guardar todo el historial de DMs: mayor carga de privacidad y cumplimiento.
- Implementar CRM completo ahora: fuera del alcance de la fase actual.
- No guardar ninguna memoria: perderia continuidad incluso en el caso actual.
- Usar solo `instagram_user_id` para escalar: aceptable hoy, insuficiente para multiperfiles.

## Fecha

2026-06-19
