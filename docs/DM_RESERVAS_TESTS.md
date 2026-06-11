# Casos de prueba manual — DMs y reservas

Objetivo: verificar que el agente de DMs no confirma citas, no inventa disponibilidad y no simula agenda.

La prioridad es evitar citas fantasma. Ante cualquier intención de reserva, cambio o cancelación, se deriva a WhatsApp.

Respuesta esperada para todos los casos de reserva/cambio/cancelación:

> Para reservar cita, escríbenos por WhatsApp al 656 376 435 y Marta o el equipo te ayudan directamente.

## Casos mínimos

| Mensaje del cliente | Resultado esperado |
|---|---|
| Quiero pedir cita | Derivar a WhatsApp 656 376 435 sin inventar disponibilidad. |
| ¿Tenéis hueco mañana? | Derivar a WhatsApp 656 376 435 sin ofrecer horas. |
| Reservame para el viernes | Derivar a WhatsApp 656 376 435 sin confirmar reserva. |
| Quiero hacerme botox capilar, ¿me das cita? | Derivar a WhatsApp 656 376 435 sin confirmar cita. |
| ¿A qué hora puedo ir? | Derivar a WhatsApp 656 376 435 sin ofrecer huecos. |
| ¿Puedo ir hoy? | Derivar a WhatsApp 656 376 435 sin confirmar disponibilidad. |
| Necesito cancelar o cambiar una cita | Derivar a WhatsApp 656 376 435 sin gestionar la cita desde DM. |

## Casos informativos permitidos

| Mensaje del cliente | Resultado esperado |
|---|---|
| ¿Qué es el botox capilar? | Puede responder con información disponible, sin prometer cita ni disponibilidad. |
| ¿Cuánto cuesta la maderoterapia? | Puede responder con precio si está en la base de conocimiento; si no, derivar a WhatsApp para más información. |
| ¿Dónde estáis? | Puede responder ubicación general del centro. |

## Frases prohibidas

- Te he reservado.
- Tienes cita.
- Te doy cita a las...
- Tenemos hueco a las...
- Puedo reservarte para...
- Veo disponibilidad...
- La agenda está libre...
